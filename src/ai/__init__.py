# src/ai/__init__.py
"""AI and Machine Learning module"""

from .models import LocalAIModel, ModelManager
from .agents import SemanticKernelAgent, AgentOrchestrator
from .skills import HRSkill, FinanceSkill, DocumentSkill
from .rag import RAGPipeline, VectorStore

__all__ = [
    "LocalAIModel", "ModelManager",
    "SemanticKernelAgent", "AgentOrchestrator", 
    "HRSkill", "FinanceSkill", "DocumentSkill",
    "RAGPipeline", "VectorStore"
]
