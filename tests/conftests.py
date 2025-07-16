# tests/conftest.py
import pytest
import asyncio
from typing import Generator, AsyncGenerator
from unittest.mock import Mock, patch
import polars as pl
import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import redis
from kafka import KafkaProducer
import tempfile
import os
from pathlib import Path

# Import main application
from main import app, config, DataPipeline, AgentOrchestrator

# Test database URL
TEST_DATABASE_URL = "sqlite:///./test.db"

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def client():
    """Create test client"""
    with TestClient(app) as c:
        yield c

@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    config_mock = Mock()
    config_mock.DATABASE_URL = TEST_DATABASE_URL
    config_mock.REDIS_URL = "redis://localhost:6379/1"
    config_mock.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
    config_mock.PHI3_MODEL_PATH = "microsoft/Phi-3-mini-4k-instruct"
    config_mock.PHI2_MODEL_PATH = "microsoft/phi-2"
    config_mock.EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
    config_mock.BATCH_SIZE = 100
    config_mock.MAX_WORKERS = 2
    return config_mock

@pytest.fixture
def sample_hr_data():
    """Sample HR data for testing"""
    return pl.DataFrame({
        "employee_id": [1, 2, 3, 4, 5],
        "first_name": ["John", "Jane", "Bob", "Alice", "Charlie"],
        "last_name": ["Doe", "Smith", "Johnson", "Brown", "Wilson"],
        "department": ["Engineering", "Finance", "HR", "Engineering", "Finance"],
        "salary": [85000, 65000, 75000, 90000, 70000],
        "performance_rating": [4.5, 4.2, 4.8, 4.1, 4.6],
        "hire_date": ["2022-01-15", "2021-03-10", "2020-05-20", "2022-06-01", "2021-11-15"],
        "status": ["active", "active", "active", "active", "active"]
    })

@pytest.fixture
def sample_finance_data():
    """Sample Finance data for testing"""
    return pl.DataFrame({
        "expense_id": [1, 2, 3, 4, 5],
        "employee_id": [1, 2, 3, 1, 2],
        "category": ["Travel", "Office", "Training", "Equipment", "Software"],
        "amount": [1200.50, 350.00, 800.00, 2500.00, 199.99],
        "expense_date": ["2024-01-15", "2024-01-16", "2024-01-17", "2024-01-18", "2024-01-19"],
        "status": ["approved", "pending", "approved", "pending", "approved"]
    })

@pytest.fixture
def temp_data_dir():
    """Create temporary directory for test data"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)

@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    with patch('redis.Redis') as mock:
        yield mock

@pytest.fixture
def mock_kafka():
    """Mock Kafka producer"""
    with patch('confluent_kafka.Producer') as mock:
        yield mock

@pytest.fixture
def mock_ai_model():
    """Mock AI model for testing"""
    with patch('main.LocalAIModel') as mock:
        model_instance = Mock()
        model_instance.generate_response.return_value = "Test AI response"
        mock.return_value = model_instance
        yield model_instance

# tests/test_api.py
import pytest
import json
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
from main import app

class TestAPI:
    """Test API endpoints"""
    
    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "HR Finance Chatbot API"
        assert data["version"] == "1.0.0"

    @patch('main.orchestrator')
    def test_query_endpoint_success(self, mock_orchestrator, client):
        """Test successful query processing"""
        # Mock orchestrator response
        mock_response = Mock()
        mock_response.response = "Test response"
        mock_response.confidence = 0.95
        mock_response.sources = ["source1", "source2"]
        mock_response.agent_used = "semantic_kernel"
        mock_response.processing_time = 1.5
        
        mock_orchestrator.process_query.return_value = mock_response
        
        query_data = {
            "query": "What is the average salary?",
            "user_id": "test_user",
            "department": "HR"
        }
        
        response = client.post("/query", json=query_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["response"] == "Test response"
        assert data["confidence"] == 0.95
        assert data["agent_used"] == "semantic_kernel"

    def test_query_endpoint_validation(self, client):
        """Test query endpoint validation"""
        # Test missing query
        response = client.post("/query", json={})
        assert response.status_code == 422
        
        # Test invalid query type
        response = client.post("/query", json={"query": 123})
        assert response.status_code == 422

    def test_document_upload_success(self, client):
        """Test successful document upload"""
        test_content = b"This is a test document content"
        
        with patch('main.orchestrator') as mock_orchestrator:
            mock_orchestrator.rag_pipeline.add_documents.return_value = None
            
            response = client.post(
                "/document/upload",
                files={"file": ("test.txt", test_content, "text/plain")},
                data={"document_type": "hr"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Document uploaded successfully"
            assert data["filename"] == "test.txt"

    def test_document_upload_error(self, client):
        """Test document upload error handling"""
        # Test without file
        response = client.post("/document/upload")
        assert response.status_code == 422

class TestQueryProcessing:
    """Test query processing functionality"""
    
    @pytest.mark.asyncio
    async def test_hr_query_processing(self, mock_ai_model):
        """Test HR query processing"""
        from main import QueryRequest, AgentOrchestrator
        
        orchestrator = AgentOrchestrator(config)
        
        request = QueryRequest(
            query="What is the average salary in Engineering?",
            user_id="test_user",
            department="HR"
        )
        
        with patch.object(orchestrator, 'route_query', return_value='hr'):
            response = await orchestrator.process_query(request)
            
            assert response.response is not None
            assert response.confidence >= 0.0
            assert response.agent_used is not None

    @pytest.mark.asyncio
    async def test_finance_query_processing(self, mock_ai_model):
        """Test Finance query processing"""
        from main import QueryRequest, AgentOrchestrator
        
        orchestrator = AgentOrchestrator(config)
        
        request = QueryRequest(
            query="What is the total budget for this quarter?",
            user_id="test_user",
            department="Finance"
        )
        
        with patch.object(orchestrator, 'route_query', return_value='finance'):
            response = await orchestrator.process_query(request)
            
            assert response.response is not None
            assert response.confidence >= 0.0
            assert response.agent_used is not None

    def test_query_routing(self):
        """Test query routing logic"""
        from main import AgentOrchestrator
        
        orchestrator = AgentOrchestrator(config)
        
        # Test HR routing
        hr_query = "What is the employee performance rating?"
        assert orchestrator.route_query(hr_query) == "hr"
        
        # Test Finance routing
        finance_query = "What is the budget allocation?"
        assert orchestrator.route_query(finance_query) == "finance"
        
        # Test general routing
        general_query = "How can I help you today?"
        assert orchestrator.route_query(general_query) == "general"

# tests/test_data.py
import pytest
import polars as pl
from unittest.mock import Mock, patch
from main import DataPipeline, Config

class TestDataPipeline:
    """Test data pipeline functionality"""
    
    def test_extract_hr_data_csv(self, sample_hr_data, temp_data_dir):
        """Test CSV data extraction"""
        # Save sample data to temporary CSV
        csv_path = temp_data_dir / "hr_data.csv"
        sample_hr_data.write_csv(csv_path)
        
        pipeline = DataPipeline(config)
        result = pipeline.extract_hr_data(str(csv_path))
        
        assert isinstance(result, pl.LazyFrame)
        collected = result.collect()
        assert len(collected) == 5
        assert "employee_id" in collected.columns

    def test_extract_hr_data_parquet(self, sample_hr_data, temp_data_dir):
        """Test Parquet data extraction"""
        # Save sample data to temporary Parquet
        parquet_path = temp_data_dir / "hr_data.parquet"
        sample_hr_data.write_parquet(parquet_path)
        
        pipeline = DataPipeline(config)
        result = pipeline.extract_hr_data(str(parquet_path))
        
        assert isinstance(result, pl.LazyFrame)
        collected = result.collect()
        assert len(collected) == 5

    def test_transform_employee_data(self, sample_hr_data):
        """Test employee data transformation"""
        pipeline = DataPipeline(config)
        
        # Convert to lazy frame
        lazy_df = sample_hr_data.lazy()
        
        # Transform data
        transformed = pipeline.transform_employee_data(lazy_df)
        result = transformed.collect()
        
        # Check transformations
        assert "avg_salary" in result.columns
        assert "headcount" in result.columns
        assert "avg_performance" in result.columns
        
        # Check department grouping
        departments = result.select("department").to_series().to_list()
        assert "engineering" in departments
        assert "finance" in departments
        assert "hr" in departments

    def test_data_validation_success(self, sample_hr_data):
        """Test successful data validation"""
        pipeline = DataPipeline(config)
        
        with patch.object(pipeline, 'context') as mock_context:
            mock_context.add_expectation_suite.return_value = Mock()
            mock_context.run_validation_operator.return_value = {"success": True}
            
            result = pipeline.validate_data(sample_hr_data)
            assert result is True

    def test_data_validation_failure(self, sample_hr_data):
        """Test data validation failure"""
        pipeline = DataPipeline(config)
        
        with patch.object(pipeline, 'context') as mock_context:
            mock_context.add_expectation_suite.return_value = Mock()
            mock_context.run_validation_operator.return_value = {"success": False}
            
            result = pipeline.validate_data(sample_hr_data)
            assert result is False

    def test_kafka_streaming(self, mock_kafka):
        """Test Kafka streaming functionality"""
        pipeline = DataPipeline(config)
        
        test_data = {"employee_id": 1, "salary": 85000}
        pipeline.stream_to_kafka(test_data, "hr_topic")
        
        # Verify Kafka producer was called
        mock_kafka.return_value.produce.assert_called_once()

class TestDataTransformations:
    """Test data transformation functions"""
    
    def test_salary_calculations(self, sample_hr_data):
        """Test salary calculation transformations"""
        pipeline = DataPipeline(config)
        
        # Test department salary aggregation
        lazy_df = sample_hr_data.lazy()
        transformed = pipeline.transform_employee_data(lazy_df)
        result = transformed.collect()
        
        # Check average salary calculation
        engineering_avg = result.filter(
            pl.col("department") == "engineering"
        ).select("avg_salary").item()
        
        # Engineering has 2 employees with salaries 85000 and 90000
        expected_avg = (85000 + 90000) / 2
        assert engineering_avg == expected_avg

    def test_performance_aggregation(self, sample_hr_data):
        """Test performance rating aggregation"""
        pipeline = DataPipeline(config)
        
        lazy_df = sample_hr_data.lazy()
        transformed = pipeline.transform_employee_data(lazy_df)
        result = transformed.collect()
        
        # Check performance rating calculation
        hr_performance = result.filter(
            pl.col("department") == "hr"
        ).select("avg_performance").item()
        
        # HR has 1 employee with performance 4.8
        assert hr_performance == 4.8

    def test_headcount_calculation(self, sample_hr_data):
        """Test headcount calculation"""
        pipeline = DataPipeline(config)
        
        lazy_df = sample_hr_data.lazy()
        transformed = pipeline.transform_employee_data(lazy_df)
        result = transformed.collect()
        
        # Check headcount
        total_headcount = result.select("headcount").sum().item()
        assert total_headcount == 5

# tests/test_ai.py
import pytest
from unittest.mock import Mock, patch
import torch
from main import LocalAIModel, SemanticKernelAgent, RAGPipeline, AgentOrchestrator

class TestLocalAIModel:
    """Test local AI model functionality"""
    
    @patch('main.AutoTokenizer')
    @patch('main.AutoModelForCausalLM')
    def test_model_initialization(self, mock_model, mock_tokenizer):
        """Test AI model initialization"""
        # Mock tokenizer and model
        mock_tokenizer.from_pretrained.return_value = Mock()
        mock_model.from_pretrained.return_value = Mock()
        
        model = LocalAIModel("microsoft/Phi-3-mini-4k-instruct")
        
        assert model.model_path == "microsoft/Phi-3-mini-4k-instruct"
        assert model.tokenizer is not None
        assert model.model is not None

    @patch('main.AutoTokenizer')
    @patch('main.AutoModelForCausalLM')
    def test_response_generation(self, mock_model_class, mock_tokenizer_class):
        """Test response generation"""
        # Mock tokenizer
        mock_tokenizer = Mock()
        mock_tokenizer.pad_token = None
        mock_tokenizer.eos_token = "<|endoftext|>"
        mock_tokenizer.eos_token_id = 50256
        mock_tokenizer.return_value = {
            "input_ids": torch.tensor([[1, 2, 3]]),
            "attention_mask": torch.tensor([[1, 1, 1]])
        }
        mock_tokenizer.decode.return_value = "Test prompt Test AI response"
        mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer
        
        # Mock model
        mock_model = Mock()
        mock_model.generate.return_value = torch.tensor([[1, 2, 3, 4, 5]])
        mock_model_class.from_pretrained.return_value = mock_model
        
        # Test response generation
        ai_model = LocalAIModel("microsoft/Phi-3-mini-4k-instruct")
        response = ai_model.generate_response("Test prompt")
        
        assert response == "Test AI response"

class TestSemanticKernelAgent:
    """Test Semantic Kernel agent functionality"""
    
    @patch('main.LocalAIModel')
    def test_agent_initialization(self, mock_model):
        """Test semantic kernel agent initialization"""
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance
        
        agent = SemanticKernelAgent(mock_model_instance)
        
        assert agent.model == mock_model_instance
        assert agent.kernel is not None

    @patch('main.LocalAIModel')
    @pytest.mark.asyncio
    async def test_query_processing(self, mock_model):
        """Test query processing through semantic kernel"""
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance
        
        agent = SemanticKernelAgent(mock_model_instance)
        
        # Mock skills
        with patch.object(agent, 'hr_skill') as mock_hr_skill, \
             patch.object(agent, 'finance_skill') as mock_finance_skill:
            
            mock_hr_skill.__getitem__.return_value = Mock(return_value="HR response")
            
            result = await agent.process_query(
                "What is employee performance?",
                {"user_id": "test_user"}
            )
            
            assert result["response"] is not None
            assert result["confidence"] >= 0.0
            assert result["agent_used"] == "semantic_kernel"

class TestRAGPipeline:
    """Test RAG pipeline functionality"""
    
    @patch('main.SentenceTransformer')
    @patch('main.chromadb.PersistentClient')
    def test_rag_initialization(self, mock_chroma, mock_sentence_transformer):
        """Test RAG pipeline initialization"""
        mock_client = Mock()
        mock_chroma.return_value = mock_client
        mock_client.get_or_create_collection.return_value = Mock()
        
        mock_sentence_transformer.return_value = Mock()
        
        rag = RAGPipeline(config)
        
        assert rag.embedding_model is not None
        assert rag.chroma_client is not None

    @patch('main.SentenceTransformer')
    @patch('main.chromadb.PersistentClient')
    def test_document_addition(self, mock_chroma, mock_sentence_transformer):
        """Test document addition to vector store"""
        mock_client = Mock()
        mock_collection = Mock()
        mock_chroma.return_value = mock_client
        mock_client.get_or_create_collection.return_value = mock_collection
        
        mock_embeddings = Mock()
        mock_embeddings.encode.return_value = [[0.1, 0.2, 0.3]]
        mock_sentence_transformer.return_value = mock_embeddings
        
        rag = RAGPipeline(config)
        
        documents = ["Test document content"]
        metadata = [{"type": "test"}]
        
        rag.add_documents(documents, metadata, "hr")
        
        mock_collection.add.assert_called_once()

    @patch('main.SentenceTransformer')
    @patch('main.chromadb.PersistentClient')
    def test_document_retrieval(self, mock_chroma, mock_sentence_transformer):
        """Test document retrieval from vector store"""
        mock_client = Mock()
        mock_collection = Mock()
        mock_chroma.return_value = mock_client
        mock_client.get_or_create_collection.return_value = mock_collection
        
        mock_collection.query.return_value = {
            "documents": [["Retrieved document 1", "Retrieved document 2"]]
        }
        
        mock_sentence_transformer.return_value = Mock()
        
        rag = RAGPipeline(config)
        
        results = rag.retrieve_relevant_docs("test query", "hr", k=2)
        
        assert len(results) == 2
        assert results[0] == "Retrieved document 1"

class TestAgentOrchestrator:
    """Test agent orchestrator functionality"""
    
    @patch('main.LocalAIModel')
    @patch('main.SemanticKernelAgent')
    @patch('main.RAGPipeline')
    def test_orchestrator_initialization(self, mock_rag, mock_agent, mock_model):
        """Test orchestrator initialization"""
        orchestrator = AgentOrchestrator(config)
        
        assert orchestrator.config == config
        assert orchestrator.phi3_model is not None
        assert orchestrator.semantic_agent is not None
        assert orchestrator.rag_pipeline is not None

    def test_query_routing(self):
        """Test query routing logic"""
        with patch('main.LocalAIModel'), \
             patch('main.SemanticKernelAgent'), \
             patch('main.RAGPipeline'):
            
            orchestrator = AgentOrchestrator(config)
            
            # Test HR routing
            assert orchestrator.route_query("employee performance") == "hr"
            assert orchestrator.route_query("recruitment process") == "hr"
            
            # Test Finance routing
            assert orchestrator.route_query("budget analysis") == "finance"
            assert orchestrator.route_query("expense report") == "finance"
            
            # Test general routing
            assert orchestrator.route_query("hello there") == "general"

# tests/fixtures/sample_data.csv
employee_id,first_name,last_name,department,salary,performance_rating,hire_date,status
1,John,Doe,Engineering,85000,4.5,2022-01-15,active
2,Jane,Smith,Finance,65000,4.2,2021-03-10,active
3,Bob,Johnson,HR,75000,4.8,2020-05-20,active
4,Alice,Brown,Engineering,90000,4.1,2022-06-01,active
5,Charlie,Wilson,Finance,70000,4.6,2021-11-15,active

# tests/fixtures/test_documents.txt
Employee Handbook

Section 1: Introduction
Welcome to our company. This handbook provides important information about our policies and procedures.

Section 2: HR Policies
- Performance reviews are conducted annually
- Leave requests must be submitted 2 weeks in advance
- Employee benefits include health insurance and 401k matching

Section 3: Finance Guidelines
- All expenses must be approved by department managers
- Budget allocations are reviewed quarterly
- Financial reports are due on the 15th of each month

Section 4: Code of Conduct
- Maintain professional behavior at all times
- Respect diversity and inclusion principles
- Report any violations to HR department

# tests/performance/locustfile.py
from locust import HttpUser, task, between
import json
import random

class ChatbotUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        """Called when a user starts"""
        self.client.verify = False
        
    @task(3)
    def query_hr(self):
        """Test HR queries"""
        queries = [
            "What is the average salary in Engineering?",
            "How many employees are in HR department?",
            "What is the performance rating for John Doe?",
            "Show me leave policy information",
            "What are the recruitment guidelines?"
        ]
        
        query_data = {
            "query": random.choice(queries),
            "user_id": f"test_user_{random.randint(1, 1000)}",
            "department": "HR"
        }
        
        self.client.post("/query", json=query_data)
    
    @task(2)
    def query_finance(self):
        """Test Finance queries"""
        queries = [
            "What is the total budget for this quarter?",
            "Show me expense report for last month",
            "What are the approved expenses?",
            "Budget allocation by department",
            "Revenue projections for next quarter"
        ]
        
        query_data = {
            "query": random.choice(queries),
            "user_id": f"test_user_{random.randint(1, 1000)}",
            "department": "Finance"
        }
        
        self.client.post("/query", json=query_data)
    
    @task(1)
    def health_check(self):
        """Test health endpoint"""
        self.client.get("/health")
    
    @task(1)
    def upload_document(self):
        """Test document upload"""
        files = {
            'file': ('test_doc.txt', 'This is a test document content', 'text/plain')
        }
        data = {'document_type': 'hr'}
        
        self.client.post("/document/upload", files=files, data=data)