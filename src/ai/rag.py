"""Retrieval-Augmented Generation implementation"""

import asyncio
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import json
import numpy as np
import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer

from .models import EmbeddingModel
from ..config import get_settings
from ..utils import logger

settings = get_settings()

class VectorStore:
    """Vector database abstraction layer"""
    
    def __init__(self, persist_directory: str = None):
        if persist_directory is None:
            persist_directory = str(Path(settings.data_dir) / "chroma_db")
        
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.embedding_model = EmbeddingModel()
        self.logger = logger.get_logger(__name__)
        
        # Initialize collections
        self.collections = {}
        self._initialize_collections()
    
    def _initialize_collections(self):
        """Initialize document collections"""
        collection_configs = {
            "hr_documents": "HR policies, procedures, and employee information",
            "finance_documents": "Financial reports, budgets, and expense data", 
            "general_documents": "General company documents and knowledge base"
        }
        
        for name, description in collection_configs.items():
            collection = self.client.get_or_create_collection(
                name=name,
                metadata={"description": description},
                embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=settings.embedding_model
                )
            )
            self.collections[name] = collection
    
    def add_documents(
        self, 
        collection_name: str,
        documents: List[str], 
        metadata: List[Dict[str, Any]] = None,
        ids: List[str] = None
    ) -> bool:
        """Add documents to vector store"""
        try:
            if collection_name not in self.collections:
                raise ValueError(f"Collection {collection_name} not found")
            
            collection = self.collections[collection_name]
            
            # Generate IDs if not provided
            if ids is None:
                ids = [f"doc_{collection_name}_{i}" for i in range(len(documents))]
            
            # Generate metadata if not provided
            if metadata is None:
                metadata = [{"source": "unknown"} for _ in documents]
            
            # Add documents
            collection.add(
                documents=documents,
                metadatas=metadata,
                ids=ids
            )
            
            self.logger.info(f"Added {len(documents)} documents to {collection_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add documents: {e}")
            return False
    
    def search_documents(
        self,
        collection_name: str,
        query: str,
        n_results: int = 5,
        where: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Search documents in vector store"""
        try:
            if collection_name not in self.collections:
                self.logger.warning(f"Collection {collection_name} not found, using general_documents")
                collection_name = "general_documents"
            
            collection = self.collections[collection_name]
            
            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
                include=["documents", "metadatas", "distances"]
            )
            
            # Format results
            formatted_results = []
            if results["documents"] and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    formatted_results.append({
                        "content": doc,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if results["distances"] else 0.0,
                        "relevance": 1.0 - results["distances"][0][i] if results["distances"] else 1.0
                    })
            
            return formatted_results
            
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            return []
    
    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Get statistics for a collection"""
        try:
            if collection_name not in self.collections:
                return {"error": "Collection not found"}
            
            collection = self.collections[collection_name]
            count = collection.count()
            
            return {
                "name": collection_name,
                "document_count": count,
                "status": "active"
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get collection stats: {e}")
            return {"error": str(e)}

class DocumentProcessor:
    """Document processing for RAG pipeline"""
    
    @staticmethod
    def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> List[str]:
        """Split text into overlapping chunks"""
        words = text.split()
        chunks = []
        
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
            
            if i + chunk_size >= len(words):
                break
        
        return chunks
    
    @staticmethod
    def extract_metadata(text: str, filename: str = None) -> Dict[str, Any]:
        """Extract metadata from document"""
        metadata = {
            "filename": filename or "unknown",
            "word_count": len(text.split()),
            "char_count": len(text),
            "processed_at": str(np.datetime64("now"))
        }
        
        # Extract potential document type
        if any(keyword in text.lower() for keyword in ["policy", "procedure", "handbook"]):
            metadata["document_type"] = "policy"
        elif any(keyword in text.lower() for keyword in ["budget", "financial", "expense"]):
            metadata["document_type"] = "financial"
        elif any(keyword in text.lower() for keyword in ["employee", "hr", "human resources"]):
            metadata["document_type"] = "hr"
        else:
            metadata["document_type"] = "general"
        
        return metadata

class RAGPipeline:
    """Complete RAG pipeline implementation"""
    
    def __init__(self, vector_store: VectorStore = None):
        self.vector_store = vector_store or VectorStore()
        self.processor = DocumentProcessor()
        self.logger = logger.get_logger(__name__)
        
        # RAG configuration
        self.max_context_length = 2048
        self.min_relevance_threshold = 0.5
        self.max_retrieved_docs = 5
    
    async def add_document(
        self,
        content: str,
        collection_name: str = "general_documents",
        filename: str = None,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """Add document to RAG pipeline"""
        try:
            # Process document
            chunks = self.processor.chunk_text(content)
            base_metadata = self.processor.extract_metadata(content, filename)
            
            # Prepare metadata for each chunk
            chunk_metadata = []
            chunk_ids = []
            
            for i, chunk in enumerate(chunks):
                chunk_meta = base_metadata.copy()
                chunk_meta.update(metadata or {})
                chunk_meta["chunk_index"] = i
                chunk_meta["total_chunks"] = len(chunks)
                
                chunk_metadata.append(chunk_meta)
                chunk_ids.append(f"{filename or 'doc'}_{i}")
            
            # Add to vector store
            success = self.vector_store.add_documents(
                collection_name=collection_name,
                documents=chunks,
                metadata=chunk_metadata,
                ids=chunk_ids
            )
            
            if success:
                self.logger.info(f"Successfully added document with {len(chunks)} chunks")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to add document: {e}")
            return False
    
    async def retrieve_context(
        self,
        query: str,
        collection_name: str = "general_documents",
        max_docs: int = None
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant context for query"""
        if max_docs is None:
            max_docs = self.max_retrieved_docs
        
        try:
            # Search for relevant documents
            results = self.vector_store.search_documents(
                collection_name=collection_name,
                query=query,
                n_results=max_docs
            )
            
            # Filter by relevance threshold
            relevant_docs = [
                doc for doc in results 
                if doc["relevance"] >= self.min_relevance_threshold
            ]
            
            self.logger.info(f"Retrieved {len(relevant_docs)} relevant documents for query")
            return relevant_docs
            
        except Exception as e:
            self.logger.error(f"Context retrieval failed: {e}")
            return []
    
    async def generate_with_context(
        self,
        query: str,
        model,
        collection_name: str = "general_documents",
        max_context_tokens: int = None
    ) -> Tuple[str, List[str]]:
        """Generate response with retrieved context"""
        if max_context_tokens is None:
            max_context_tokens = self.max_context_length
        
        try:
            # Retrieve context
            context_docs = await self.retrieve_context(query, collection_name)
            
            if not context_docs:
                # Generate without context
                prompt = f"User Query: {query}\n\nPlease provide a helpful response:"
                response = await model.generate_response_async(prompt)
                return response, []
            
            # Build context string
            context_parts = []
            used_sources = []
            
            for doc in context_docs:
                context_parts.append(doc["content"])
                used_sources.append(doc["metadata"].get("filename", "unknown"))
                
                # Check token limit (rough estimate)
                context_text = "\n\n".join(context_parts)
                if len(context_text.split()) > max_context_tokens:
                    context_parts.pop()
                    used_sources.pop()
                    break
            
            # Build final prompt
            context_text = "\n\n".join(context_parts)
            prompt = f"""
            Context Information:
            {context_text}
            
            User Query: {query}
            
            Based on the context information provided above, please provide a comprehensive and accurate response to the user's query. If the context doesn't contain enough information to fully answer the question, please indicate what information is available and what might be missing.
            
            Response:
            """
            
            # Generate response
            response = await model.generate_response_async(prompt)
            
            return response, list(set(used_sources))
            
        except Exception as e:
            self.logger.error(f"RAG generation failed: {e}")
            return f"I encountered an error: {str(e)}", []
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get RAG pipeline statistics"""
        stats = {}
        
        for collection_name in self.vector_store.collections.keys():
            stats[collection_name] = self.vector_store.get_collection_stats(collection_name)
        
        stats["configuration"] = {
            "max_context_length": self.max_context_length,
            "min_relevance_threshold": self.min_relevance_threshold,
            "max_retrieved_docs": self.max_retrieved_docs
        }
        
        return stats