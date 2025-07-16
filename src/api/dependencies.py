"""API dependencies and dependency injection"""

import asyncio
from typing import Dict, Optional, Any
from fastapi import Depends, HTTPException, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timedelta

from ..config import get_settings, get_database
from ..ai.models import ModelManager
from ..ai.agents import MultiAgentOrchestrator
from ..ai.rag import RAGPipeline
from .middleware import RateLimiter

settings = get_settings()
security = HTTPBearer()

# Global instances (singleton pattern)
_model_manager: Optional[ModelManager] = None
_orchestrator: Optional[MultiAgentOrchestrator] = None
_rate_limiter: Optional[RateLimiter] = None

async def get_model_manager() -> ModelManager:
    """Get model manager instance"""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
        
        # Load default models
        _model_manager.load_model("phi3", settings.phi3_model_path, quantize=True)
        _model_manager.load_model("phi2", settings.phi2_model_path, optimize=True)
    
    return _model_manager

async def get_orchestrator(
    model_manager: ModelManager = Depends(get_model_manager)
) -> MultiAgentOrchestrator:
    """Get agent orchestrator instance"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MultiAgentOrchestrator(model_manager)
    
    return _orchestrator

async def get_rate_limiter() -> RateLimiter:
    """Get rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    
    return _rate_limiter

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """Get current authenticated user"""
    try:
        # Decode JWT token
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Check token expiration
        exp = payload.get("exp")
        if exp and datetime.utcnow().timestamp() > exp:
            raise HTTPException(status_code=401, detail="Token expired")
        
        return {
            "user_id": user_id,
            "role": payload.get("role", "user"),
            "department": payload.get("department"),
            "permissions": payload.get("permissions", [])
        }
        
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

async def get_optional_user(
    authorization: Optional[str] = Header(None)
) -> Optional[Dict[str, Any]]:
    """Get user if authenticated, otherwise return None"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    try:
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=authorization.split(" ")[1]
        )
        return await get_current_user(credentials)
    except:
        return None

async def get_admin_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Ensure current user has admin privileges"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

async def get_db():
    """Get database session"""
    db_config = get_database()
    async with db_config.get_session() as session:
        yield session

def create_access_token(data: Dict[str, Any], expires_delta: timedelta = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    
    to_encode.update({"exp": expire})
    
    return jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.jwt_algorithm
    )