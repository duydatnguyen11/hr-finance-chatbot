"""Logging configuration and utilities"""

import logging
import logging.config
import json
import sys
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import structlog
from pythonjsonlogger import jsonlogger

from ..config import get_settings

settings = get_settings()

class JSONFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for structured logging"""
    
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        
        # Add custom fields
        log_record['timestamp'] = datetime.utcnow().isoformat()
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['module'] = record.module
        log_record['function'] = record.funcName
        log_record['line'] = record.lineno
        
        # Add application context
        log_record['application'] = 'hr-finance-chatbot'
        log_record['version'] = '1.0.0'

class LoggerConfig:
    """Logger configuration manager"""
    
    def __init__(self):
        self.log_dir = Path(settings.log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        self.log_level = getattr(logging, settings.log_level.upper())
        self.log_format = settings.log_format
        
        self._setup_logging()
    
    def _setup_logging(self):
        """Setup logging configuration"""
        
        # Define formatters
        formatters = {
            'json': {
                '()': JSONFormatter,
                'format': '%(timestamp)s %(level)s %(name)s %(message)s'
            },
            'standard': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            },
            'detailed': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            }
        }
        
        # Define handlers
        handlers = {
            'console': {
                'class': 'logging.StreamHandler',
                'level': self.log_level,
                'formatter': 'json' if self.log_format == 'json' else 'standard',
                'stream': sys.stdout
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': self.log_level,
                'formatter': 'json' if self.log_format == 'json' else 'detailed',
                'filename': str(self.log_dir / 'app.log'),
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5
            },
            'error_file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'ERROR',
                'formatter': 'json' if self.log_format == 'json' else 'detailed',
                'filename': str(self.log_dir / 'error.log'),
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5
            }
        }
        
        # Define loggers
        loggers = {
            '': {  # Root logger
                'level': self.log_level,
                'handlers': ['console', 'file', 'error_file'],
                'propagate': False
            },
            'src': {
                'level': self.log_level,
                'handlers': ['console', 'file', 'error_file'],
                'propagate': False
            },
            'uvicorn': {
                'level': 'INFO',
                'handlers': ['console', 'file'],
                'propagate': False
            },
            'fastapi': {
                'level': 'INFO',
                'handlers': ['console', 'file'],
                'propagate': False
            }
        }
        
        # Configuration dictionary
        config = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': formatters,
            'handlers': handlers,
            'loggers': loggers
        }
        
        # Apply configuration
        logging.config.dictConfig(config)
        
        # Setup structured logging
        if self.log_format == 'json':
            self._setup_structlog()
    
    def _setup_structlog(self):
        """Setup structured logging with structlog"""
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

# Global logger config instance
_logger_config: Optional[LoggerConfig] = None

def get_logger(name: str = None) -> logging.Logger:
    """Get logger instance with proper configuration"""
    global _logger_config
    
    if _logger_config is None:
        _logger_config = LoggerConfig()
    
    if name is None:
        name = __name__
    
    return logging.getLogger(name)

class ContextLogger:
    """Context-aware logger for request tracking"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.context = {}
    
    def set_context(self, **kwargs):
        """Set logging context"""
        self.context.update(kwargs)
    
    def clear_context(self):
        """Clear logging context"""
        self.context.clear()
    
    def _log_with_context(self, level: str, message: str, **kwargs):
        """Log message with context"""
        extra = {**self.context, **kwargs}
        getattr(self.logger, level)(message, extra=extra)
    
    def debug(self, message: str, **kwargs):
        self._log_with_context('debug', message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log_with_context('info', message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log_with_context('warning', message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log_with_context('error', message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        self._log_with_context('critical', message, **kwargs)