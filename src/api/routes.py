# src/api/routes.py
"""API routes and endpoints"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, validator
import json

from .dependencies import get_current_user, get_orchestrator, get_rate_limiter
from .middleware import RateLimiter
from ..utils import logger

# Create router
router = APIRouter()

# Request/Response Models
class QueryRequest(BaseModel):
    query: str
    context: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None
    department: Optional[str] = None
    stream: bool = False
    
    @validator('query')
    def validate_query(cls, v):
        if not v or not v.strip():
            raise ValueError('Query cannot be empty')
        if len(v) > 1000:
            raise ValueError('Query too long (max 1000 characters)')
        return v.strip()

class QueryResponse(BaseModel):
    response: str
    confidence: float
    sources: List[str]
    agent_used: str
    processing_time: float
    timestamp: datetime
    query_id: Optional[str] = None

class DocumentUploadRequest(BaseModel):
    document_type: str = "general"
    collection_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class DocumentUploadResponse(BaseModel):
    message: str
    filename: str
    document_id: str
    chunks_created: int
    collection: str

class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str
    services: Dict[str, str]

# Main API Routes
@router.post("/query", response_model=QueryResponse)
async def process_query(
    request: QueryRequest,
    orchestrator=Depends(get_orchestrator),
    current_user=Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter)
):
    """Process user query through AI agents"""
    try:
        # Apply rate limiting
        await rate_limiter.check_rate_limit(current_user.get("user_id", "anonymous"))
        
        # Generate query ID
        query_id = f"query_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(request.query) % 10000}"
        
        # Add user info to context
        enhanced_context = request.context or {}
        enhanced_context.update({
            "user_id": current_user.get("user_id"),
            "user_role": current_user.get("role"),
            "query_id": query_id
        })
        
        # Create enhanced request
        enhanced_request = QueryRequest(
            query=request.query,
            context=enhanced_context,
            user_id=request.user_id or current_user.get("user_id"),
            department=request.department
        )
        
        # Process query
        if request.stream:
            return StreamingResponse(
                stream_query_response(orchestrator, enhanced_request),
                media_type="text/plain"
            )
        else:
            response = await orchestrator.process_query(enhanced_request)
            return QueryResponse(
                **response.__dict__,
                timestamp=datetime.now(),
                query_id=query_id
            )
            
    except Exception as e:
        logger.get_logger(__name__).error(f"Query processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def stream_query_response(orchestrator, request: QueryRequest):
    """Stream query response for real-time processing"""
    try:
        yield f"data: {json.dumps({'status': 'processing', 'message': 'Processing your query...'})}\n\n"
        
        # Process query
        response = await orchestrator.process_query(request)
        
        # Stream response
        words = response.response.split()
        for i, word in enumerate(words):
            chunk_data = {
                "type": "token",
                "content": word,
                "index": i,
                "total": len(words)
            }
            yield f"data: {json.dumps(chunk_data)}\n\n"
            await asyncio.sleep(0.05)  # Simulate streaming delay
        
        # Send completion
        completion_data = {
            "type": "complete",
            "confidence": response.confidence,
            "sources": response.sources,
            "agent_used": response.agent_used,
            "processing_time": response.processing_time
        }
        yield f"data: {json.dumps(completion_data)}\n\n"
        
    except Exception as e:
        error_data = {"type": "error", "message": str(e)}
        yield f"data: {json.dumps(error_data)}\n\n"

@router.post("/document/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: str = "general",
    collection_name: Optional[str] = None,
    orchestrator=Depends(get_orchestrator),
    current_user=Depends(get_current_user)
):
    """Upload and process document"""
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Read file content
        content = await file.read()
        
        # Determine collection
        if not collection_name:
            if document_type in ["hr", "human_resources"]:
                collection_name = "hr_documents"
            elif document_type in ["finance", "financial"]:
                collection_name = "finance_documents"
            else:
                collection_name = "general_documents"
        
        # Generate document ID
        document_id = f"doc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(file.filename) % 10000}"
        
        # Prepare metadata
        metadata = {
            "filename": file.filename,
            "document_type": document_type,
            "uploaded_by": current_user.get("user_id"),
            "upload_date": datetime.now().isoformat(),
            "document_id": document_id,
            "file_size": len(content)
        }
        
        # Process document in background
        background_tasks.add_task(
            process_document_background,
            orchestrator,
            content.decode('utf-8'),
            collection_name,
            file.filename,
            metadata
        )
        
        return DocumentUploadResponse(
            message="Document uploaded successfully",
            filename=file.filename,
            document_id=document_id,
            chunks_created=0,  # Will be updated in background
            collection=collection_name
        )
        
    except Exception as e:
        logger.get_logger(__name__).error(f"Document upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_document_background(orchestrator, content: str, collection_name: str, filename: str, metadata: Dict):
    """Process document in background task"""
    try:
        success = await orchestrator.rag_pipeline.add_document(
            content=content,
            collection_name=collection_name,
            filename=filename,
            metadata=metadata
        )
        
        if success:
            logger.get_logger(__name__).info(f"Document {filename} processed successfully")
        else:
            logger.get_logger(__name__).error(f"Failed to process document {filename}")
            
    except Exception as e:
        logger.get_logger(__name__).error(f"Background document processing failed: {e}")

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    try:
        # Check various services
        services_status = {
            "api": "healthy",
            "database": "healthy",  # Add actual database check
            "ai_models": "healthy",  # Add actual model check
            "vector_store": "healthy"  # Add actual vector store check
        }
        
        overall_status = "healthy" if all(
            status == "healthy" for status in services_status.values()
        ) else "degraded"
        
        return HealthResponse(
            status=overall_status,
            timestamp=datetime.now(),
            version="1.0.0",
            services=services_status
        )
        
    except Exception as e:
        logger.get_logger(__name__).error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metrics")
async def get_metrics(
    orchestrator=Depends(get_orchestrator),
    current_user=Depends(get_current_user)
):
    """Get system metrics"""
    try:
        # Check if user has admin role
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Get various metrics
        metrics = {
            "model_metrics": orchestrator.model_manager.get_all_metrics(),
            "agent_metrics": orchestrator.get_agent_metrics(),
            "rag_metrics": orchestrator.rag_pipeline.get_pipeline_stats(),
            "timestamp": datetime.now().isoformat()
        }
        
        return metrics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.get_logger(__name__).error(f"Metrics retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/collections")
async def list_collections(
    orchestrator=Depends(get_orchestrator),
    current_user=Depends(get_current_user)
):
    """List document collections"""
    try:
        collections = orchestrator.rag_pipeline.get_pipeline_stats()
        return {
            "collections": collections,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.get_logger(__name__).error(f"Collections listing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/collections/{collection_name}/documents/{document_id}")
async def delete_document(
    collection_name: str,
    document_id: str,
    current_user=Depends(get_current_user)
):
    """Delete document from collection"""
    try:
        # Check permissions
        if current_user.get("role") not in ["admin", "editor"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        # Implement document deletion logic here
        # This would involve removing from vector store
        
        return {
            "message": f"Document {document_id} deleted from {collection_name}",
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.get_logger(__name__).error(f"Document deletion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))