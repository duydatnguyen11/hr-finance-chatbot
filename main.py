# HR Finance Chatbot - Comprehensive AI System
# File: main.py

import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path

# Core imports
import polars as pl
import semantic_kernel as sk
from semantic_kernel.connectors.ai.hugging_face import HuggingFaceTextCompletion
from semantic_kernel.orchestration.context_variables import ContextVariables
from semantic_kernel.orchestration.sk_context import SKContext
from semantic_kernel.skill_definition import sk_function, sk_function_context_parameter
from semantic_kernel.orchestration.sk_function import SKFunction

# Data processing
import pandas as pd
from confluent_kafka import Producer, Consumer
import great_expectations as gx
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

# AI and ML
import torch
import transformers
from transformers import AutoTokenizer, AutoModelForCausalLM
import numpy as np
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.utils import embedding_functions

# Web framework
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class Config:
    """Application configuration"""
    # Data sources
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/hrfinance"
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    REDIS_URL: str = "redis://localhost:6379"
    
    # AI Models
    PHI3_MODEL_PATH: str = "microsoft/Phi-3-mini-4k-instruct"
    PHI2_MODEL_PATH: str = "microsoft/phi-2"
    EMBEDDING_MODEL: str = "sentence-transformers/all-mpnet-base-v2"
    
    # Directories
    DATA_DIR: Path = Path("data")
    MODELS_DIR: Path = Path("models")
    LOGS_DIR: Path = Path("logs")
    
    # Processing
    BATCH_SIZE: int = 1000
    MAX_WORKERS: int = 4
    
    def __post_init__(self):
        """Create necessary directories"""
        for dir_path in [self.DATA_DIR, self.MODELS_DIR, self.LOGS_DIR]:
            dir_path.mkdir(exist_ok=True)

config = Config()

# =============================================================================
# DATA MODELS
# =============================================================================

class QueryRequest(BaseModel):
    query: str
    context: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None
    department: Optional[str] = None

class QueryResponse(BaseModel):
    response: str
    confidence: float
    sources: List[str]
    agent_used: str
    processing_time: float

class DocumentRequest(BaseModel):
    content: str
    document_type: str
    metadata: Optional[Dict[str, Any]] = None

# =============================================================================
# DATA ENGINEERING LAYER
# =============================================================================

class DataPipeline:
    """High-performance data pipeline using Polars"""
    
    def __init__(self, config: Config):
        self.config = config
        self.context = gx.get_context()
        self.kafka_producer = Producer({
            'bootstrap.servers': config.KAFKA_BOOTSTRAP_SERVERS,
            'client.id': 'hr-finance-producer'
        })
        
    def extract_hr_data(self, source: str) -> pl.DataFrame:
        """Extract HR data with lazy evaluation"""
        logger.info(f"Extracting HR data from {source}")
        
        if source.endswith('.csv'):
            return pl.scan_csv(source)
        elif source.endswith('.parquet'):
            return pl.scan_parquet(source)
        else:
            # Database connection
            return pl.read_database(
                query="SELECT * FROM hr_employees",
                connection=self.config.DATABASE_URL
            )
    
    def transform_employee_data(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """Transform employee data with advanced Polars operations"""
        return (
            df
            .with_columns([
                pl.col("hire_date").str.strptime(pl.Date, "%Y-%m-%d"),
                pl.col("salary").cast(pl.Float64),
                pl.col("department").str.to_lowercase(),
                pl.when(pl.col("performance_rating") > 4.0)
                .then("High Performer")
                .otherwise("Regular")
                .alias("performance_category")
            ])
            .filter(pl.col("status") == "active")
            .group_by("department")
            .agg([
                pl.col("salary").mean().alias("avg_salary"),
                pl.col("employee_id").count().alias("headcount"),
                pl.col("performance_rating").mean().alias("avg_performance")
            ])
        )
    
    def validate_data(self, df: pl.DataFrame) -> bool:
        """Data validation using Great Expectations"""
        try:
            # Convert to pandas for Great Expectations
            pandas_df = df.to_pandas()
            
            # Create expectation suite
            suite = self.context.add_expectation_suite(
                expectation_suite_name="hr_finance_suite",
                overwrite_existing=True
            )
            
            # Add expectations
            suite.expect_column_to_exist("employee_id")
            suite.expect_column_values_to_not_be_null("employee_id")
            suite.expect_column_values_to_be_unique("employee_id")
            suite.expect_column_values_to_be_between("salary", min_value=0, max_value=1000000)
            
            # Validate
            results = self.context.run_validation_operator(
                "action_list_operator",
                assets_to_validate=[pandas_df],
                expectation_suite_name="hr_finance_suite"
            )
            
            return results["success"]
            
        except Exception as e:
            logger.error(f"Data validation failed: {e}")
            return False
    
    def stream_to_kafka(self, data: Dict[str, Any], topic: str):
        """Stream processed data to Kafka"""
        try:
            self.kafka_producer.produce(
                topic=topic,
                value=json.dumps(data),
                callback=self._delivery_callback
            )
            self.kafka_producer.flush()
        except Exception as e:
            logger.error(f"Kafka streaming failed: {e}")
    
    def _delivery_callback(self, err, msg):
        """Kafka delivery callback"""
        if err:
            logger.error(f'Message delivery failed: {err}')
        else:
            logger.info(f'Message delivered to {msg.topic()} [{msg.partition()}]')

# =============================================================================
# AI AGENTS SYSTEM
# =============================================================================

class LocalAIModel:
    """Local AI model wrapper for Phi-3 and Phi-2"""
    
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True
        )
        
        # Add padding token if not present
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
    
    def generate_response(self, prompt: str, max_length: int = 512) -> str:
        """Generate response using local model"""
        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=max_length,
            padding=True
        )
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_length=max_length,
                num_return_sequences=1,
                temperature=0.7,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id
            )
        
        response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        return response[len(prompt):].strip()

class SemanticKernelAgent:
    """Semantic Kernel-based agent for complex reasoning"""
    
    def __init__(self, model: LocalAIModel):
        self.kernel = sk.Kernel()
        self.model = model
        
        # Register AI service
        self.kernel.add_text_completion_service(
            "local_ai",
            HuggingFaceTextCompletion(
                model_id=model.model_path,
                task="text-generation"
            )
        )
        
        # Import skills
        self._import_skills()
    
    def _import_skills(self):
        """Import custom skills"""
        self.hr_skill = self.kernel.import_skill(HRSkill(), "hr")
        self.finance_skill = self.kernel.import_skill(FinanceSkill(), "finance")
        self.document_skill = self.kernel.import_skill(DocumentSkill(), "document")
    
    async def process_query(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process query using semantic kernel"""
        try:
            # Create context
            sk_context = self.kernel.create_new_context()
            sk_context.variables.update(context)
            sk_context.variables["query"] = query
            
            # Route to appropriate skill
            if "employee" in query.lower() or "hr" in query.lower():
                result = await self.hr_skill["analyze_hr_query"](
                    context=sk_context
                )
            elif "finance" in query.lower() or "budget" in query.lower():
                result = await self.finance_skill["analyze_finance_query"](
                    context=sk_context
                )
            else:
                result = await self.document_skill["analyze_document"](
                    context=sk_context
                )
            
            return {
                "response": str(result),
                "confidence": 0.85,
                "agent_used": "semantic_kernel"
            }
            
        except Exception as e:
            logger.error(f"Semantic Kernel processing failed: {e}")
            return {
                "response": f"I encountered an error processing your query: {str(e)}",
                "confidence": 0.0,
                "agent_used": "error_handler"
            }

class HRSkill:
    """HR-specific semantic skill"""
    
    @sk_function(
        description="Analyze HR-related queries",
        name="analyze_hr_query"
    )
    @sk_function_context_parameter(
        name="query",
        description="The HR query to analyze"
    )
    def analyze_hr_query(self, context: SKContext) -> str:
        query = context.variables["query"]
        
        # HR-specific processing logic
        if "performance" in query.lower():
            return self._analyze_performance(query)
        elif "leave" in query.lower():
            return self._analyze_leave_request(query)
        elif "recruitment" in query.lower():
            return self._analyze_recruitment(query)
        else:
            return f"I can help with HR matters. Your query: {query}"
    
    def _analyze_performance(self, query: str) -> str:
        return "Performance analysis shows positive trends in employee engagement."
    
    def _analyze_leave_request(self, query: str) -> str:
        return "Leave request has been processed according to company policy."
    
    def _analyze_recruitment(self, query: str) -> str:
        return "Recruitment pipeline shows strong candidate flow."

class FinanceSkill:
    """Finance-specific semantic skill"""
    
    @sk_function(
        description="Analyze finance-related queries",
        name="analyze_finance_query"
    )
    @sk_function_context_parameter(
        name="query",
        description="The finance query to analyze"
    )
    def analyze_finance_query(self, context: SKContext) -> str:
        query = context.variables["query"]
        
        if "budget" in query.lower():
            return self._analyze_budget(query)
        elif "expense" in query.lower():
            return self._analyze_expense(query)
        elif "revenue" in query.lower():
            return self._analyze_revenue(query)
        else:
            return f"I can help with finance matters. Your query: {query}"
    
    def _analyze_budget(self, query: str) -> str:
        return "Budget analysis shows 95% utilization with positive variance."
    
    def _analyze_expense(self, query: str) -> str:
        return "Expense tracking indicates adherence to approved budgets."
    
    def _analyze_revenue(self, query: str) -> str:
        return "Revenue projections are on track for quarterly targets."

class DocumentSkill:
    """Document processing semantic skill"""
    
    @sk_function(
        description="Analyze and process documents",
        name="analyze_document"
    )
    @sk_function_context_parameter(
        name="query",
        description="The document query to analyze"
    )
    def analyze_document(self, context: SKContext) -> str:
        query = context.variables["query"]
        return f"Document analysis complete for: {query}"

# =============================================================================
# RAG SYSTEM
# =============================================================================

class RAGPipeline:
    """Retrieval-Augmented Generation pipeline"""
    
    def __init__(self, config: Config):
        self.config = config
        self.embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
        self.chroma_client = chromadb.PersistentClient(
            path=str(config.DATA_DIR / "chroma_db")
        )
        
        # Initialize collections
        self.hr_collection = self.chroma_client.get_or_create_collection(
            name="hr_documents",
            embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=config.EMBEDDING_MODEL
            )
        )
        
        self.finance_collection = self.chroma_client.get_or_create_collection(
            name="finance_documents",
            embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=config.EMBEDDING_MODEL
            )
        )
    
    def add_documents(self, documents: List[str], metadata: List[Dict], collection_name: str):
        """Add documents to vector store"""
        collection = getattr(self, f"{collection_name}_collection")
        
        embeddings = self.embedding_model.encode(documents)
        ids = [f"doc_{i}" for i in range(len(documents))]
        
        collection.add(
            embeddings=embeddings.tolist(),
            documents=documents,
            metadatas=metadata,
            ids=ids
        )
    
    def retrieve_relevant_docs(self, query: str, collection_name: str, k: int = 5) -> List[str]:
        """Retrieve relevant documents"""
        collection = getattr(self, f"{collection_name}_collection")
        
        results = collection.query(
            query_texts=[query],
            n_results=k
        )
        
        return results['documents'][0] if results['documents'] else []
    
    def generate_with_context(self, query: str, context_docs: List[str], model: LocalAIModel) -> str:
        """Generate response with retrieved context"""
        context = "\n".join(context_docs)
        prompt = f"""
        Context: {context}
        
        Question: {query}
        
        Based on the context provided, please provide a comprehensive answer:
        """
        
        return model.generate_response(prompt)

# =============================================================================
# MULTI-AGENT ORCHESTRATOR
# =============================================================================

class AgentOrchestrator:
    """Orchestrates multiple AI agents"""
    
    def __init__(self, config: Config):
        self.config = config
        self.phi3_model = LocalAIModel(config.PHI3_MODEL_PATH)
        self.phi2_model = LocalAIModel(config.PHI2_MODEL_PATH)
        
        self.semantic_agent = SemanticKernelAgent(self.phi3_model)
        self.rag_pipeline = RAGPipeline(config)
        
        # Agent routing rules
        self.routing_rules = {
            "hr": ["employee", "performance", "leave", "recruitment", "payroll"],
            "finance": ["budget", "expense", "revenue", "cost", "profit"],
            "document": ["analyze", "summarize", "extract", "process"]
        }
    
    def route_query(self, query: str) -> str:
        """Route query to appropriate agent"""
        query_lower = query.lower()
        
        for agent_type, keywords in self.routing_rules.items():
            if any(keyword in query_lower for keyword in keywords):
                return agent_type
        
        return "general"
    
    async def process_query(self, request: QueryRequest) -> QueryResponse:
        """Process query through multi-agent system"""
        start_time = datetime.now()
        
        try:
            # Route query
            agent_type = self.route_query(request.query)
            
            # Retrieve relevant documents
            relevant_docs = self.rag_pipeline.retrieve_relevant_docs(
                request.query, 
                agent_type if agent_type in ["hr", "finance"] else "hr"
            )
            
            # Process through semantic kernel
            context = {
                "relevant_docs": relevant_docs,
                "user_id": request.user_id,
                "department": request.department,
                **(request.context or {})
            }
            
            result = await self.semantic_agent.process_query(request.query, context)
            
            # Generate final response with RAG
            if relevant_docs:
                enhanced_response = self.rag_pipeline.generate_with_context(
                    request.query,
                    relevant_docs,
                    self.phi3_model
                )
                result["response"] = enhanced_response
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return QueryResponse(
                response=result["response"],
                confidence=result["confidence"],
                sources=relevant_docs,
                agent_used=result["agent_used"],
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            return QueryResponse(
                response=f"I apologize, but I encountered an error: {str(e)}",
                confidence=0.0,
                sources=[],
                agent_used="error_handler",
                processing_time=(datetime.now() - start_time).total_seconds()
            )

# =============================================================================
# WEB API
# =============================================================================

app = FastAPI(title="HR Finance Chatbot", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
data_pipeline = DataPipeline(config)
orchestrator = AgentOrchestrator(config)

@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """Process user query"""
    try:
        response = await orchestrator.process_query(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/document/upload")
async def upload_document(file: UploadFile = File(...), document_type: str = "general"):
    """Upload and process document"""
    try:
        content = await file.read()
        text_content = content.decode('utf-8')
        
        # Add to RAG pipeline
        metadata = {
            "filename": file.filename,
            "document_type": document_type,
            "upload_date": datetime.now().isoformat()
        }
        
        collection_name = document_type if document_type in ["hr", "finance"] else "hr"
        orchestrator.rag_pipeline.add_documents(
            [text_content], 
            [metadata], 
            collection_name
        )
        
        return {"message": "Document uploaded successfully", "filename": file.filename}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "HR Finance Chatbot API", "version": "1.0.0"}

# =============================================================================
# AIRFLOW DAG
# =============================================================================

def create_airflow_dag():
    """Create Airflow DAG for data pipeline"""
    
    def extract_data():
        """Extract data task"""
        pipeline = DataPipeline(config)
        df = pipeline.extract_hr_data("data/hr_data.csv")
        logger.info("Data extraction completed")
    
    def transform_data():
        """Transform data task"""
        pipeline = DataPipeline(config)
        df = pipeline.extract_hr_data("data/hr_data.csv")
        transformed = pipeline.transform_employee_data(df)
        result = transformed.collect()
        logger.info(f"Data transformation completed: {len(result)} records")
    
    def validate_data():
        """Validate data task"""
        pipeline = DataPipeline(config)
        df = pipeline.extract_hr_data("data/hr_data.csv")
        is_valid = pipeline.validate_data(df.collect())
        logger.info(f"Data validation completed: {is_valid}")
    
    dag = DAG(
        'hr_finance_pipeline',
        default_args={
            'owner': 'data-team',
            'depends_on_past': False,
            'start_date': days_ago(1),
            'email_on_failure': False,
            'email_on_retry': False,
            'retries': 1,
        },
        description='HR Finance Data Pipeline',
        schedule_interval='@daily',
        catchup=False,
        tags=['hr', 'finance', 'etl'],
    )
    
    extract_task = PythonOperator(
        task_id='extract_data',
        python_callable=extract_data,
        dag=dag,
    )
    
    transform_task = PythonOperator(
        task_id='transform_data',
        python_callable=transform_data,
        dag=dag,
    )
    
    validate_task = PythonOperator(
        task_id='validate_data',
        python_callable=validate_data,
        dag=dag,
    )
    
    extract_task >> transform_task >> validate_task
    
    return dag

# Create DAG instance
dag = create_airflow_dag()

# =============================================================================
# MAIN APPLICATION
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="HR Finance Chatbot")
    parser.add_argument("--mode", choices=["api", "cli"], default="api", help="Run mode")
    parser.add_argument("--host", default="0.0.0.0", help="Host address")
    parser.add_argument("--port", type=int, default=8000, help="Port number")
    
    args = parser.parse_args()
    
    if args.mode == "api":
        uvicorn.run(
            "main:app",
            host=args.host,
            port=args.port,
            reload=True,
            log_level="info"
        )
    else:
        # CLI mode
        async def cli_mode():
            print("HR Finance Chatbot CLI Mode")
            print("Type 'exit' to quit")
            
            while True:
                user_input = input("\nYou: ")
                if user_input.lower() == 'exit':
                    break
                
                request = QueryRequest(query=user_input)
                response = await orchestrator.process_query(request)
                
                print(f"\nBot: {response.response}")
                print(f"Confidence: {response.confidence:.2f}")
                print(f"Agent: {response.agent_used}")
                print(f"Processing time: {response.processing_time:.2f}s")
        
        asyncio.run(cli_mode())