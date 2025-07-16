# src/data/pipeline.py
"""Advanced data pipeline implementation"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from datetime import datetime
import polars as pl
import pandas as pd
from confluent_kafka import Producer, Consumer
import great_expectations as gx
from great_expectations.core.expectation_suite import ExpectationSuite

from ..config import get_settings
from ..utils import logger

settings = get_settings()

class DataProcessor:
    """High-performance data processor using Polars"""
    
    def __init__(self):
        self.logger = logger.get_logger(__name__)
    
    def read_csv_lazy(self, path: Union[str, Path], **kwargs) -> pl.LazyFrame:
        """Read CSV file lazily with optimizations"""
        return pl.scan_csv(
            path,
            ignore_errors=True,
            null_values=["", "NULL", "null", "N/A", "n/a"],
            try_parse_dates=True,
            **kwargs
        )
    
    def read_parquet_lazy(self, path: Union[str, Path], **kwargs) -> pl.LazyFrame:
        """Read Parquet file lazily"""
        return pl.scan_parquet(path, **kwargs)
    
    def optimize_query(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """Optimize Polars query with predicate pushdown"""
        return (
            df
            .with_columns([
                pl.col("*").shrink_dtype()  # Optimize data types
            ])
            .cache()  # Cache intermediate results
        )
    
    def batch_process(self, df: pl.LazyFrame, batch_size: int = None) -> List[pl.DataFrame]:
        """Process data in batches for memory efficiency"""
        if batch_size is None:
            batch_size = settings.batch_size
        
        collected_df = df.collect()
        total_rows = len(collected_df)
        
        batches = []
        for i in range(0, total_rows, batch_size):
            batch = collected_df.slice(i, batch_size)
            batches.append(batch)
        
        return batches

class DataTransformer:
    """Data transformation utilities"""
    
    @staticmethod
    def clean_employee_data(df: pl.LazyFrame) -> pl.LazyFrame:
        """Clean and standardize employee data"""
        return (
            df
            .with_columns([
                # Standardize names
                pl.col("first_name").str.strip_chars().str.to_titlecase(),
                pl.col("last_name").str.strip_chars().str.to_titlecase(),
                
                # Standardize email
                pl.col("email").str.to_lowercase().str.strip_chars(),
                
                # Standardize department
                pl.col("department").str.to_lowercase().str.strip_chars(),
                
                # Clean salary data
                pl.col("salary").cast(pl.Float64),
                
                # Parse dates
                pl.col("hire_date").str.strptime(pl.Date, "%Y-%m-%d", strict=False),
                
                # Clean performance rating
                pl.col("performance_rating").cast(pl.Float64).clip(0.0, 5.0),
                
                # Standardize status
                pl.col("status").str.to_lowercase().str.strip_chars()
            ])
            .filter(
                # Remove invalid records
                pl.col("email").str.contains("@") &
                pl.col("salary").is_not_null() &
                pl.col("hire_date").is_not_null()
            )
        )
    
    @staticmethod
    def aggregate_by_department(df: pl.LazyFrame) -> pl.LazyFrame:
        """Aggregate employee metrics by department"""
        return (
            df
            .group_by("department")
            .agg([
                pl.col("employee_id").count().alias("headcount"),
                pl.col("salary").mean().alias("avg_salary"),
                pl.col("salary").median().alias("median_salary"),
                pl.col("salary").min().alias("min_salary"),
                pl.col("salary").max().alias("max_salary"),
                pl.col("performance_rating").mean().alias("avg_performance"),
                pl.col("hire_date").min().alias("earliest_hire"),
                pl.col("hire_date").max().alias("latest_hire")
            ])
            .sort("avg_salary", descending=True)
        )
    
    @staticmethod
    def calculate_tenure(df: pl.LazyFrame) -> pl.LazyFrame:
        """Calculate employee tenure in years"""
        return df.with_columns([
            ((pl.date.today() - pl.col("hire_date")).dt.total_days() / 365.25)
            .alias("tenure_years")
            .round(2)
        ])

class ValidationResult:
    """Data validation result container"""
    
    def __init__(self, success: bool, errors: List[str] = None, warnings: List[str] = None):
        self.success = success
        self.errors = errors or []
        self.warnings = warnings or []
        self.timestamp = datetime.now()
    
    def __str__(self):
        status = "PASSED" if self.success else "FAILED"
        return f"Validation {status} at {self.timestamp}"

class DataValidator:
    """Data validation using Great Expectations"""
    
    def __init__(self):
        self.context = gx.get_context()
        self.logger = logger.get_logger(__name__)
    
    def create_hr_expectation_suite(self) -> ExpectationSuite:
        """Create expectation suite for HR data"""
        suite_name = "hr_data_suite"
        
        try:
            suite = self.context.get_expectation_suite(suite_name)
        except Exception:
            suite = self.context.add_expectation_suite(suite_name)
        
        # Employee ID expectations
        suite.expect_column_to_exist("employee_id")
        suite.expect_column_values_to_not_be_null("employee_id")
        suite.expect_column_values_to_be_unique("employee_id")
        
        # Name expectations
        suite.expect_column_to_exist("first_name")
        suite.expect_column_to_exist("last_name")
        suite.expect_column_values_to_not_be_null("first_name")
        suite.expect_column_values_to_not_be_null("last_name")
        
        # Email expectations
        suite.expect_column_to_exist("email")
        suite.expect_column_values_to_match_regex(
            "email", 
            r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        )
        
        # Salary expectations
        suite.expect_column_to_exist("salary")
        suite.expect_column_values_to_be_between("salary", min_value=0, max_value=1000000)
        
        # Performance rating expectations
        suite.expect_column_values_to_be_between("performance_rating", min_value=0.0, max_value=5.0)
        
        # Department expectations
        suite.expect_column_values_to_be_in_set(
            "department", 
            ["engineering", "finance", "hr", "marketing", "sales", "operations"]
        )
        
        # Status expectations
        suite.expect_column_values_to_be_in_set(
            "status",
            ["active", "inactive", "terminated", "on_leave"]
        )
        
        return suite
    
    def validate_hr_data(self, df: pl.DataFrame) -> ValidationResult:
        """Validate HR data against expectations"""
        try:
            # Convert to pandas for Great Expectations
            pandas_df = df.to_pandas()
            
            # Get or create expectation suite
            suite = self.create_hr_expectation_suite()
            
            # Create data asset
            data_asset = self.context.sources.add_pandas("hr_data_source").add_asset(
                "hr_data_asset"
            )
            
            # Run validation
            batch_request = data_asset.build_batch_request(dataframe=pandas_df)
            batch = data_asset.get_batch_list_from_batch_request(batch_request)[0]
            
            validation_result = batch.validate(expectation_suite=suite)
            
            # Parse results
            success = validation_result.success
            errors = []
            warnings = []
            
            for result in validation_result.results:
                if not result.success:
                    errors.append(result.expectation_config.expectation_type)
            
            return ValidationResult(success, errors, warnings)
            
        except Exception as e:
            self.logger.error(f"Validation failed: {str(e)}")
            return ValidationResult(False, [str(e)])

class StreamProcessor:
    """Real-time stream processing with Kafka"""
    
    def __init__(self):
        self.producer = Producer({
            'bootstrap.servers': settings.kafka_bootstrap_servers,
            'client.id': 'hr-finance-producer'
        })
        self.logger = logger.get_logger(__name__)
    
    def publish_event(self, topic: str, data: Dict[str, Any], key: str = None):
        """Publish event to Kafka topic"""
        try:
            import json
            
            self.producer.produce(
                topic=topic,
                value=json.dumps(data),
                key=key,
                callback=self._delivery_callback
            )
            self.producer.flush()
            
        except Exception as e:
            self.logger.error(f"Failed to publish event: {str(e)}")
    
    def _delivery_callback(self, err, msg):
        """Callback for message delivery confirmation"""
        if err:
            self.logger.error(f'Message delivery failed: {err}')
        else:
            self.logger.info(f'Message delivered to {msg.topic()} [{msg.partition()}]')
    
    async def consume_events(self, topics: List[str], group_id: str = None):
        """Consume events from Kafka topics"""
        if group_id is None:
            group_id = settings.kafka_group_id
        
        consumer = Consumer({
            'bootstrap.servers': settings.kafka_bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': settings.kafka_auto_offset_reset
        })
        
        consumer.subscribe(topics)
        
        try:
            while True:
                msg = consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                
                if msg.error():
                    self.logger.error(f"Consumer error: {msg.error()}")
                    continue
                
                # Process message
                await self._process_message(msg)
                
        except Exception as e:
            self.logger.error(f"Consumer error: {str(e)}")
        finally:
            consumer.close()
    
    async def _process_message(self, msg):
        """Process consumed message"""
        import json
        
        try:
            data = json.loads(msg.value())
            topic = msg.topic()
            
            self.logger.info(f"Processing message from {topic}: {data}")
            
            # Add your message processing logic here
            
        except Exception as e:
            self.logger.error(f"Failed to process message: {str(e)}")

class DataPipeline:
    """Complete data pipeline orchestrator"""
    
    def __init__(self):
        self.processor = DataProcessor()
        self.transformer = DataTransformer()
        self.validator = DataValidator()
        self.stream_processor = StreamProcessor()
        self.logger = logger.get_logger(__name__)
    
    async def execute_pipeline(self, source_path: str, target_table: str = None) -> bool:
        """Execute complete data pipeline"""
        try:
            # 1. Extract data
            self.logger.info(f"Extracting data from {source_path}")
            if source_path.endswith('.csv'):
                df = self.processor.read_csv_lazy(source_path)
            elif source_path.endswith('.parquet'):
                df = self.processor.read_parquet_lazy(source_path)
            else:
                raise ValueError(f"Unsupported file format: {source_path}")
            
            # 2. Transform data
            self.logger.info("Transforming data")
            df = self.transformer.clean_employee_data(df)
            df = self.transformer.calculate_tenure(df)
            
            # 3. Validate data
            self.logger.info("Validating data")
            collected_df = df.collect()
            validation_result = self.validator.validate_hr_data(collected_df)
            
            if not validation_result.success:
                self.logger.error(f"Data validation failed: {validation_result.errors}")
                return False
            
            # 4. Load data (if target specified)
            if target_table:
                self.logger.info(f"Loading data to {target_table}")
                # Add your data loading logic here
                pass
            
            # 5. Stream events
            self.stream_processor.publish_event(
                topic="data_pipeline_complete",
                data={
                    "source": source_path,
                    "target": target_table,
                    "records_processed": len(collected_df),
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            self.logger.info("Pipeline executed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Pipeline execution failed: {str(e)}")
            return False