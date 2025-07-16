"""API middleware components"""

import asyncio
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import redis.asyncio as redis
from collections import defaultdict, deque

from ..config import get_settings
from ..utils import logger

settings = get_settings()

class RateLimiter:
    """Advanced rate limiting middleware"""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client
        self.local_cache = defaultdict(lambda: deque())
        self.logger = logger.get_logger(__name__)
        
        # Rate limit configurations
        self.limits = {
            "anonymous": {"requests": 10, "window": 60},  # 10 requests per minute
            "user": {"requests": 100, "window": 60},      # 100 requests per minute
            "premium": {"requests": 500, "window": 60},   # 500 requests per minute
            "admin": {"requests": 1000, "window": 60}     # 1000 requests per minute
        }
    
    async def check_rate_limit(self, user_id: str, user_role: str = "user") -> bool:
        """Check if user is within rate limits"""
        try:
            # Get appropriate limit
            limit_config = self.limits.get(user_role, self.limits["user"])
            max_requests = limit_config["requests"]
            window_seconds = limit_config["window"]
            
            current_time = time.time()
            window_start = current_time - window_seconds
            
            if self.redis_client:
                # Use Redis for distributed rate limiting
                key = f"rate_limit:{user_id}"
                
                # Remove old entries
                await self.redis_client.zremrangebyscore(key, 0, window_start)
                
                # Count current requests
                current_count = await self.redis_client.zcard(key)
                
                if current_count >= max_requests:
                    raise HTTPException(
                        status_code=429,
                        detail=f"Rate limit exceeded. Max {max_requests} requests per {window_seconds} seconds"
                    )
                
                # Add current request
                await self.redis_client.zadd(key, {str(current_time): current_time})
                await self.redis_client.expire(key, window_seconds)
                
            else:
                # Use local cache for single-instance rate limiting
                user_requests = self.local_cache[user_id]
                
                # Remove old requests
                while user_requests and user_requests[0] < window_start:
                    user_requests.popleft()
                
                if len(user_requests) >= max_requests:
                    raise HTTPException(
                        status_code=429,
                        detail=f"Rate limit exceeded. Max {max_requests} requests per {window_seconds} seconds"
                    )
                
                # Add current request
                user_requests.append(current_time)
            
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Rate limiting error: {e}")
            return True  # Allow request on error

class RequestLoggingMiddleware:
    """Request logging and monitoring middleware"""
    
    def __init__(self, app: FastAPI):
        self.app = app
        self.logger = logger.get_logger(__name__)
    
    async def __call__(self, request: Request, call_next):
        start_time = time.time()
        
        # Log request
        self.logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query_params": str(request.query_params),
                "client_ip": request.client.host,
                "user_agent": request.headers.get("user-agent")
            }
        )
        
        try:
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Log response
            self.logger.info(
                f"Request completed: {request.method} {request.url.path} - {response.status_code}",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "process_time": process_time,
                    "client_ip": request.client.host
                }
            )
            
            # Add custom headers
            response.headers["X-Process-Time"] = str(process_time)
            response.headers["X-API-Version"] = "1.0.0"
            
            return response
            
        except Exception as e:
            # Log error
            process_time = time.time() - start_time
            self.logger.error(
                f"Request failed: {request.method} {request.url.path}",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e),
                    "process_time": process_time,
                    "client_ip": request.client.host
                }
            )
            raise

class SecurityHeadersMiddleware:
    """Security headers middleware"""
    
    def __init__(self, app: FastAPI):
        self.app = app
    
    async def __call__(self, request: Request, call_next):
        response = await call_next(request)
        
        # Add security headers
        response.headers.update({
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'",
        })
        
        return response

def setup_middleware(app: FastAPI):
    """Setup all middleware components"""
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Trusted host middleware
    if not settings.debug:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["localhost", "127.0.0.1", "*.yourdomain.com"]
        )
    
    # Custom middleware
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)