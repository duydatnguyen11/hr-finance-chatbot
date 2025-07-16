# src/config/settings.py
"""Application settings and configuration"""

import os
from typing import Optional, List
from pydantic import BaseSettings, validator
from pathlib import Path

class Settings(BaseSettings):
    """Application settings"""
    
    # API Configuration
    api_title: str = "HR Finance Chatbot"
    api_version: str = "1.0.0"
    api_description: str = "Comprehensive AI-powered chatbot for HR and Finance operations"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4
    debug: bool = False
    
    # Database Configuration
    database_url: str = "postgresql://postgres:password@localhost:5432/hrfinance"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10
    
    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"
    redis_password: Optional[str] = None
    redis_decode_responses: bool = True
    
    # Kafka Configuration
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "hr-finance-group"
    kafka_auto_offset_reset: str = "latest"
    
    # AI Models Configuration
    phi3_model_path: str = "microsoft/Phi-3-mini-4k-instruct"
    phi2_model_path: str = "microsoft/phi-2"
    embedding_model: str = "sentence-transformers/all-mpnet-base-v2"
    model_cache_dir: str = "./models"
    
    # Data Processing Configuration
    batch_size: int = 1000
    max_workers: int = 4
    data_dir: str = "./data"
    
    # Security Configuration
    secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30
    cors_origins: List[str] = ["*"]
    
    # Logging Configuration
    log_level: str = "INFO"
    log_format: str = "json"
    log_dir: str = "./logs"
    
    # Monitoring Configuration
    enable_metrics: bool = True
    metrics_port: int = 9000
    prometheus_port: int = 9090
    grafana_port: int = 3000
    
    # Feature Flags
    enable_caching: bool = True
    enable_rate_limiting: bool = True
    enable_document_processing: bool = True
    enable_real_time_streaming: bool = True
    
    @validator('secret_key')
    def validate_secret_key(cls, v):
        if v == "your-secret-key-change-in-production":
            raise ValueError('Please change the default secret key in production')
        if len(v) < 32:
            raise ValueError('Secret key must be at least 32 characters long')
        return v
    
    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of: {valid_levels}')
        return v.upper()
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

# Global settings instance
_settings: Optional[Settings] = None

def get_settings() -> Settings:
    """Get application settings (singleton pattern)"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings