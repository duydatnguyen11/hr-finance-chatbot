"""AI agent implementations"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
import semantic_kernel as sk
from semantic_kernel.orchestration.context_variables import ContextVariables

from .models import ModelManager
from .skills import HRSkill, FinanceSkill, DocumentSkill
from ..config import get_settings
from ..utils import logger

settings = get_settings()

class SemanticKernelAgent:
    """Enhanced Semantic Kernel agent with advanced capabilities"""
    
    def __init__(self, model_manager: ModelManager):
        self.model_manager = model_manager
        self.kernel = sk.Kernel()
        self.logger = logger.get_logger(__name__)
        
        # Agent metadata
        self.agent_id = f"sk_agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.processing_history = []
        
        self._setup_kernel()
        self._import_skills()
    
    def _setup_kernel(self):
        """Setup semantic kernel configuration"""
        try:
            # Add text completion service
            primary_model = self.model_manager.get_model("phi3")
            if primary_model:
                # For now, we'll use a simple wrapper
                # In production, you'd implement a proper SK connector
                pass
            
            self.logger.info("Semantic Kernel setup complete")
            
        except Exception as e:
            self.logger.error(f"Kernel setup failed: {e}")
            raise
    
    def _import_skills(self):
        """Import and register skills"""
        try:
            # Import custom skills
            self.hr_skill = HRSkill()
            self.finance_skill = FinanceSkill()
            self.document_skill = DocumentSkill()
            
            # Register skills with kernel
            self.kernel.import_skill(self.hr_skill, "hr")
            self.kernel.import_skill(self.finance_skill, "finance")
            self.kernel.import_skill(self.document_skill, "document")
            
            self.logger.info("Skills imported successfully")
            
        except Exception as e:
            self.logger.error(f"Skill import failed: {e}")
            raise
    
    async def process_query(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process query using semantic kernel"""
        start_time = datetime.now()
        
        try:
            # Create context
            sk_context = self.kernel.create_new_context()
            for key, value in context.items():
                sk_context.variables[key] = str(value)
            sk_context.variables["query"] = query
            
            # Route to appropriate skill
            skill_result = await self._route_and_execute(query, sk_context)
            
            # Prepare response
            response = {
                "response": str(skill_result),
                "confidence": self._calculate_confidence(query, skill_result),
                "agent_used": self.agent_id,
                "processing_time": (datetime.now() - start_time).total_seconds(),
                "context_used": list(context.keys())
            }
            
            # Add to processing history
            self.processing_history.append({
                "timestamp": start_time.isoformat(),
                "query": query,
                "response": response,
                "context": context
            })
            
            return response
            
        except Exception as e:
            self.logger.error(f"Query processing failed: {e}")
            return {
                "response": f"I encountered an error processing your query: {str(e)}",
                "confidence": 0.0,
                "agent_used": self.agent_id,
                "error": str(e)
            }
    
    async def _route_and_execute(self, query: str, context) -> str:
        """Route query to appropriate skill and execute"""
        query_lower = query.lower()
        
        # HR routing
        if any(keyword in query_lower for keyword in ["employee", "hr", "performance", "leave", "recruitment"]):
            return await self.hr_skill.analyze_hr_query(context)
        
        # Finance routing
        elif any(keyword in query_lower for keyword in ["finance", "budget", "expense", "revenue", "cost"]):
            return await self.finance_skill.analyze_finance_query(context)
        
        # Document routing
        elif any(keyword in query_lower for keyword in ["document", "analyze", "summarize", "extract"]):
            return await self.document_skill.analyze_document(context)
        
        # Default: use general reasoning
        else:
            return await self._general_reasoning(query, context)
    
    async def _general_reasoning(self, query: str, context) -> str:
        """General reasoning for unclassified queries"""
        # Use primary model for general reasoning
        model = self.model_manager.get_model("phi3")
        if model:
            prompt = f"""
            Context: {context.variables.get('relevant_docs', 'No specific context available')}
            
            User Query: {query}
            
            Please provide a helpful and informative response based on the context and your knowledge:
            """
            return await model.generate_response_async(prompt)
        else:
            return "I'm ready to help, but I need a moment to initialize my capabilities."
    
    def _calculate_confidence(self, query: str, response: str) -> float:
        """Calculate confidence score for the response"""
        # Simple heuristic-based confidence calculation
        # In production, you'd use more sophisticated methods
        
        confidence = 0.5  # Base confidence
        
        # Increase confidence for longer, more detailed responses
        if len(response) > 100:
            confidence += 0.2
        
        # Increase confidence if response contains specific keywords
        if any(keyword in response.lower() for keyword in ["analysis", "data", "report", "according to"]):
            confidence += 0.15
        
        # Decrease confidence for error responses
        if "error" in response.lower() or "sorry" in response.lower():
            confidence -= 0.3
        
        return max(0.0, min(1.0, confidence))

class MultiAgentOrchestrator:
    """Orchestrates multiple AI agents for complex tasks"""
    
    def __init__(self, model_manager: ModelManager):
        self.model_manager = model_manager
        self.agents = {}
        self.logger = logger.get_logger(__name__)
        
        self._initialize_agents()
    
    def _initialize_agents(self):
        """Initialize different types of agents"""
        # Semantic Kernel Agent
        self.agents["semantic"] = SemanticKernelAgent(self.model_manager)
        
        # Specialized agents could be added here
        # self.agents["research"] = ResearchAgent(self.model_manager)
        # self.agents["analysis"] = AnalysisAgent(self.model_manager)
    
    async def process_complex_query(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process complex queries using multiple agents"""
        # For now, route to semantic agent
        # In future, implement sophisticated multi-agent coordination
        return await self.agents["semantic"].process_query(query, context)
    
    def get_agent_metrics(self) -> Dict[str, Any]:
        """Get metrics from all agents"""
        metrics = {}
        for name, agent in self.agents.items():
            if hasattr(agent, 'processing_history'):
                metrics[name] = {
                    "total_queries": len(agent.processing_history),
                    "avg_processing_time": sum(
                        h["response"]["processing_time"] 
                        for h in agent.processing_history
                    ) / max(len(agent.processing_history), 1),
                    "avg_confidence": sum(
                        h["response"]["confidence"] 
                        for h in agent.processing_history
                    ) / max(len(agent.processing_history), 1)
                }
        return metrics
