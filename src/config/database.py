# src/config/database.py
"""Database configuration and connection management"""

import asyncio
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import StaticPool
import redis.asyncio as redis
from .settings import get_settings

settings = get_settings()

# SQLAlchemy Base
Base = declarative_base()

class DatabaseConfig:
    """Database configuration manager"""
    
    def __init__(self):
        self.settings = get_settings()
        self._engine: Optional[AsyncSession] = None
        self._session_factory: Optional[async_sessionmaker] = None
        self._redis_client: Optional[redis.Redis] = None
    
    @property
    def engine(self):
        """Get database engine"""
        if self._engine is None:
            self._engine = create_async_engine(
                self.settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
                echo=self.settings.database_echo,
                pool_size=self.settings.database_pool_size,
                max_overflow=self.settings.database_max_overflow,
                poolclass=StaticPool if "sqlite" in self.settings.database_url else None,
            )
        return self._engine
    
    @property
    def session_factory(self):
        """Get session factory"""
        if self._session_factory is None:
            self._session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
        return self._session_factory
    
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session"""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def get_redis(self) -> redis.Redis:
        """Get Redis client"""
        if self._redis_client is None:
            self._redis_client = redis.from_url(
                self.settings.redis_url,
                password=self.settings.redis_password,
                decode_responses=self.settings.redis_decode_responses
            )
        return self._redis_client
    
    async def close(self):
        """Close database connections"""
        if self._engine:
            await self._engine.dispose()
        if self._redis_client:
            await self._redis_client.close()

# Global database instance
_db_config: Optional[DatabaseConfig] = None

def get_database() -> DatabaseConfig:
    """Get database configuration (singleton pattern)"""
    global _db_config
    if _db_config is None:
        _db_config = DatabaseConfig()
    return _db_config