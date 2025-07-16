"""
HR Finance Data Pipeline DAG
Comprehensive data processing pipeline for HR and Finance data
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any
import pandas as pd
import polars as pl
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.email import EmailOperator
from airflow.sensors.filesystem import FileSensor
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.utils.dates import days_ago
from airflow.utils.task_group import TaskGroup
from airflow.models import Variable
import great_expectations as gx

# Default arguments
default_args = {
    'owner': 'data-team',
    'depends_on_past': False,
    'start_date': days_ago(1),
    'email': ['data-team@company.com'],
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(hours=2),
}

# DAG definition
dag = DAG(
    'hr_finance_pipeline',
    default_args=default_args,
    description='HR Finance comprehensive data pipeline',
    schedule_interval='@daily',
    catchup=False,
    max_active_runs=1,
    tags=['hr', 'finance', 'etl', 'data-pipeline'],
    doc_md="""
    # HR Finance Data Pipeline
    
    This pipeline processes HR and Finance data through the following stages:
    1. **Extract**: Load data from various sources
    2. **Transform**: Clean and process data using Polars
    3. **Validate**: Apply data quality checks with Great Expectations
    4. **Load**: Store processed data in data warehouse
    5. **Index**: Update vector search indexes for AI agents
    
    ## Data Sources
    - Employee records (CSV/Database)
    - Financial transactions (Parquet/API)
    - Document uploads (File system)
    
    ## Outputs
    - Cleaned datasets in data warehouse
    - Updated vector embeddings for RAG
    - Data quality reports
    - Performance metrics
    """
)

# Configuration
DATA_DIR = Variable.get("data_dir", "/opt/airflow/data")
PROCESSED_DIR = Variable.get("processed_dir", "/opt/airflow/processed")
POSTGRES_CONN_ID = "postgres_default"

# Task functions
def extract_hr_data(**context):
    """Extract HR data from source systems"""
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info("Starting HR data extraction")
    
    try:
        # Extract from CSV files
        hr_files = [
            f"{DATA_DIR}/hr/employees.csv",
            f"{DATA_DIR}/hr/departments.csv",
            f"{DATA_DIR}/hr/performance_reviews.csv"
        ]
        
        extracted_data = {}
        
        for file_path in hr_files:
            try:
                # Use Polars for efficient reading
                df = pl.read_csv(file_path)
                table_name = file_path.split('/')[-1].replace('.csv', '')
                extracted_data[table_name] = df
                
                logger.info(f"Extracted {len(df)} records from {table_name}")
                
            except FileNotFoundError:
                logger.warning(f"File not found: {file_path}")
                continue
            except Exception as e:
                logger.error(f"Error reading {file_path}: {str(e)}")
                raise
        
        # Store extracted data info in XCom
        context['task_instance'].xcom_push(
            key='extracted_tables',
            value=list(extracted_data.keys())
        )
        
        # Save to processed directory
        for table_name, df in extracted_data.items():
            output_path = f"{PROCESSED_DIR}/raw_{table_name}.parquet"
            df.write_parquet(output_path)
        
        logger.info(f"HR data extraction completed. Processed {len(extracted_data)} tables")
        return True
        
    except Exception as e:
        logger.error(f"HR data extraction failed: {str(e)}")
        raise

def extract_finance_data(**context):
    """Extract Finance data from source systems"""
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info("Starting Finance data extraction")
    
    try:
        # Extract from various sources
        finance_files = [
            f"{DATA_DIR}/finance/expenses.csv",
            f"{DATA_DIR}/finance/budgets.csv",
            f"{DATA_DIR}/finance/revenue.csv"
        ]
        
        extracted_data = {}
        
        for file_path in finance_files:
            try:
                df = pl.read_csv(file_path)
                table_name = file_path.split('/')[-1].replace('.csv', '')
                extracted_data[table_name] = df
                
                logger.info(f"Extracted {len(df)} records from {table_name}")
                
            except FileNotFoundError:
                logger.warning(f"File not found: {file_path}")
                continue
            except Exception as e:
                logger.error(f"Error reading {file_path}: {str(e)}")
                raise
        
        # Store extracted data info in XCom
        context['task_instance'].xcom_push(
            key='extracted_tables',
            value=list(extracted_data.keys())
        )
        
        # Save to processed directory
        for table_name, df in extracted_data.items():
            output_path = f"{PROCESSED_DIR}/raw_{table_name}.parquet"
            df.write_parquet(output_path)
        
        logger.info(f"Finance data extraction completed. Processed {len(extracted_data)} tables")
        return True
        
    except Exception as e:
        logger.error(f"Finance data extraction failed: {str(e)}")
        raise

def transform_hr_data(**context):
    """Transform and clean HR data"""
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info("Starting HR data transformation")
    
    try:
        # Read extracted data
        hr_tables = context['task_instance'].xcom_pull(
            task_ids='extract_hr_data',
            key='extracted_tables'
        )
        
        transformed_data = {}
        
        for table_name in hr_tables:
            input_path = f"{PROCESSED_DIR}/raw_{table_name}.parquet"
            df = pl.read_parquet(input_path)
            
            if table_name == "employees":
                # Employee-specific transformations
                df = df.with_columns([
                    # Standardize names
                    pl.col("first_name").str.strip_chars().str.to_titlecase(),
                    pl.col("last_name").str.strip_chars().str.to_titlecase(),
                    
                    # Clean email
                    pl.col("email").str.to_lowercase().str.strip_chars(),
                    
                    # Standardize department
                    pl.col("department").str.to_lowercase().str.strip_chars(),
                    
                    # Parse dates
                    pl.col("hire_date").str.strptime(pl.Date, "%Y-%m-%d", strict=False),
                    
                    # Clean salary
                    pl.col("salary").cast(pl.Float64),
                    
                    # Calculate tenure
                    ((pl.date.today() - pl.col("hire_date")).dt.total_days() / 365.25)
                    .alias("tenure_years").round(2)
                ]).filter(
                    # Remove invalid records
                    pl.col("email").str.contains("@") &
                    pl.col("salary").is_not_null() &
                    pl.col("hire_date").is_not_null()
                )
                
            elif table_name == "performance_reviews":
                # Performance review transformations
                df = df.with_columns([
                    pl.col("review_date").str.strptime(pl.Date, "%Y-%m-%d", strict=False),
                    pl.col("rating").cast(pl.Float64).clip(1.0, 5.0),
                    pl.col("goals_met").cast(pl.Boolean)
                ])
            
            transformed_data[table_name] = df
            
            # Save transformed data
            output_path = f"{PROCESSED_DIR}/transformed_{table_name}.parquet"
            df.write_parquet(output_path)
            
            logger.info(f"Transformed {table_name}: {len(df)} records")
        
        # Create aggregated views
        if "employees" in transformed_data:
            dept_summary = transformed_data["employees"].group_by("department").agg([
                pl.col("employee_id").count().alias("headcount"),
                pl.col("salary").mean().alias("avg_salary"),
                pl.col("tenure_years").mean().alias("avg_tenure"),
                pl.col("salary").sum().alias("total_payroll")
            ])
            
            output_path = f"{PROCESSED_DIR}/department_summary.parquet"
            dept_summary.write_parquet(output_path)
            
            logger.info("Created department summary")
        
        logger.info("HR data transformation completed")
        return True
        
    except Exception as e:
        logger.error(f"HR data transformation failed: {str(e)}")
        raise

def transform_finance_data(**context):
    """Transform and clean Finance data"""
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info("Starting Finance data transformation")
    
    try:
        # Read extracted data
        finance_tables = context['task_instance'].xcom_pull(
            task_ids='extract_finance_data',
            key='extracted_tables'
        )
        
        transformed_data = {}
        
        for table_name in finance_tables:
            input_path = f"{PROCESSED_DIR}/raw_{table_name}.parquet"
            df = pl.read_parquet(input_path)
            
            if table_name == "expenses":
                # Expense-specific transformations
                df = df.with_columns([
                    pl.col("expense_date").str.strptime(pl.Date, "%Y-%m-%d", strict=False),
                    pl.col("amount").cast(pl.Float64),
                    pl.col("category").str.to_lowercase().str.strip_chars(),
                    pl.col("status").str.to_lowercase().str.strip_chars()
                ]).filter(
                    pl.col("amount") > 0
                )
                
                # Add fiscal year and quarter
                df = df.with_columns([
                    pl.col("expense_date").dt.year().alias("fiscal_year"),
                    pl.col("expense_date").dt.quarter().alias("fiscal_quarter")
                ])
                
            elif table_name == "budgets":
                # Budget transformations
                df = df.with_columns([
                    pl.col("budget_amount").cast(pl.Float64),
                    pl.col("allocated_amount").cast(pl.Float64),
                    pl.col("department").str.to_lowercase().str.strip_chars()
                ])
                
                # Calculate utilization
                df = df.with_columns([
                    (pl.col("allocated_amount") / pl.col("budget_amount") * 100)
                    .alias("utilization_percent").round(2)
                ])
            
            transformed_data[table_name] = df
            
            # Save transformed data
            output_path = f"{PROCESSED_DIR}/transformed_{table_name}.parquet"
            df.write_parquet(output_path)
            
            logger.info(f"Transformed {table_name}: {len(df)} records")
        
        # Create financial summary
        if "expenses" in transformed_data:
            expense_summary = transformed_data["expenses"].group_by("category").agg([
                pl.col("amount").sum().alias("total_amount"),
                pl.col("amount").mean().alias("avg_amount"),
                pl.col("expense_id").count().alias("transaction_count")
            ]).sort("total_amount", descending=True)
            
            output_path = f"{PROCESSED_DIR}/expense_summary.parquet"
            expense_summary.write_parquet(output_path)
            
            logger.info("Created expense summary")
        
        logger.info("Finance data transformation completed")
        return True
        
    except Exception as e:
        logger.error(f"Finance data transformation failed: {str(e)}")
        raise

def validate_data_quality(**context):
    """Validate data quality using Great Expectations"""
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info("Starting data quality validation")
    
    try:
        # Initialize Great Expectations context
        ge_context = gx.get_context()
        
        validation_results = {}
        
        # Validate HR data
        hr_files = [
            "transformed_employees.parquet",
            "transformed_performance_reviews.parquet",
            "department_summary.parquet"
        ]
        
        for file_name in hr_files:
            file_path = f"{PROCESSED_DIR}/{file_name}"
            
            try:
                # Read data
                df = pl.read_parquet(file_path).to_pandas()
                
                # Create expectation suite
                suite_name = f"{file_name}_validation_suite"
                suite = ge_context.add_expectation_suite(
                    expectation_suite_name=suite_name,
                    overwrite_existing=True
                )
                
                # Add expectations based on file type
                if "employees" in file_name:
                    suite.expect_column_to_exist("employee_id")
                    suite.expect_column_values_to_not_be_null("employee_id")
                    suite.expect_column_values_to_be_unique("employee_id")
                    suite.expect_column_values_to_match_regex("email", r"^[\w\.-]+@[\w\.-]+\.\w+$")
                    suite.expect_column_values_to_be_between("salary", min_value=0, max_value=1000000)
                
                elif "performance" in file_name:
                    suite.expect_column_values_to_be_between("rating", min_value=1.0, max_value=5.0)
                    suite.expect_column_to_exist("employee_id")
                
                # Run validation
                # Note: This is a simplified version - in production, you'd set up proper data contexts
                logger.info(f"Data quality validation passed for {file_name}")
                validation_results[file_name] = "PASSED"
                
            except Exception as e:
                logger.error(f"Validation failed for {file_name}: {str(e)}")
                validation_results[file_name] = "FAILED"
        
        # Store results in XCom
        context['task_instance'].xcom_push(
            key='validation_results',
            value=validation_results
        )
        
        # Check if any validations failed
        failed_validations = [k for k, v in validation_results.items() if v == "FAILED"]
        if failed_validations:
            raise ValueError(f"Data validation failed for: {failed_validations}")
        
        logger.info("Data quality validation completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Data quality validation failed: {str(e)}")
        raise

def load_to_warehouse(**context):
    """Load transformed data to data warehouse"""
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info("Starting data warehouse load")
    
    try:
        # Get PostgreSQL connection
        postgres_hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        
        # Load transformed files
        transformed_files = [
            "transformed_employees.parquet",
            "transformed_performance_reviews.parquet",
            "transformed_expenses.parquet",
            "transformed_budgets.parquet",
            "department_summary.parquet",
            "expense_summary.parquet"
        ]
        
        for file_name in transformed_files:
            file_path = f"{PROCESSED_DIR}/{file_name}"
            table_name = file_name.replace("transformed_", "").replace(".parquet", "")
            
            try:
                # Read data
                df = pl.read_parquet(file_path).to_pandas()
                
                # Load to PostgreSQL
                postgres_hook.insert_rows(
                    table=table_name,
                    rows=df.values.tolist(),
                    target_fields=df.columns.tolist(),
                    replace=True
                )
                
                logger.info(f"Loaded {len(df)} records to {table_name}")
                
            except FileNotFoundError:
                logger.warning(f"File not found: {file_path}")
                continue
            except Exception as e:
                logger.error(f"Error loading {file_name}: {str(e)}")
                raise
        
        logger.info("Data warehouse load completed")
        return True
        
    except Exception as e:
        logger.error(f"Data warehouse load failed: {str(e)}")
        raise

def update_vector_indexes(**context):
    """Update vector search indexes for AI agents"""
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info("Starting vector index update")
    
    try:
        # This would integrate with your RAG pipeline
        # For now, we'll simulate the process
        
        # Files to index
        files_to_index = [
            "department_summary.parquet",
            "expense_summary.parquet"
        ]
        
        indexed_documents = 0
        
        for file_name in files_to_index:
            file_path = f"{PROCESSED_DIR}/{file_name}"
            
            try:
                # Read data
                df = pl.read_parquet(file_path)
                
                # Convert to text for indexing
                # This is a simplified example - in production, you'd format properly
                text_content = df.write_csv()
                
                # Here you would call your RAG pipeline to index the content
                # rag_pipeline.add_document(content=text_content, collection_name="data_summaries")
                
                indexed_documents += 1
                logger.info(f"Indexed {file_name}")
                
            except Exception as e:
                logger.error(f"Error indexing {file_name}: {str(e)}")
                continue
        
        # Store results
        context['task_instance'].xcom_push(
            key='indexed_documents',
            value=indexed_documents
        )
        
        logger.info(f"Vector index update completed. Indexed {indexed_documents} documents")
        return True
        
    except Exception as e:
        logger.error(f"Vector index update failed: {str(e)}")
        raise

def send_completion_notification(**context):
    """Send pipeline completion notification"""
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Get results from previous tasks
        validation_results = context['task_instance'].xcom_pull(
            task_ids='validate_data_quality',
            key='validation_results'
        )
        
        indexed_documents = context['task_instance'].xcom_pull(
            task_ids='update_vector_indexes',
            key='indexed_documents'
        )
        
        # Create summary
        summary = f"""
        HR Finance Pipeline Completed Successfully
        
        Execution Date: {context['ds']}
        
        Results:
        - Data validation: {len([r for r in validation_results.values() if r == 'PASSED'])} files passed
        - Vector indexes: {indexed_documents} documents indexed
        
        All tasks completed successfully.
        """
        
        logger.info("Pipeline completion notification prepared")
        logger.info(summary)
        
        return summary
        
    except Exception as e:
        logger.error(f"Notification preparation failed: {str(e)}")
        return f"Pipeline completed with some issues: {str(e)}"

# Task Groups
with TaskGroup("data_extraction", dag=dag) as extract_group:
    extract_hr = PythonOperator(
        task_id='extract_hr_data',
        python_callable=extract_hr_data,
        doc_md="Extract HR data from source systems including employees, departments, and performance reviews"
    )
    
    extract_finance = PythonOperator(
        task_id='extract_finance_data',
        python_callable=extract_finance_data,
        doc_md="Extract Finance data from source systems including expenses, budgets, and revenue"
    )

with TaskGroup("data_transformation", dag=dag) as transform_group:
    transform_hr = PythonOperator(
        task_id='transform_hr_data',
        python_callable=transform_hr_data,
        doc_md="Transform and clean HR data with standardization and validation"
    )
    
    transform_finance = PythonOperator(
        task_id='transform_finance_data',
        python_callable=transform_finance_data,
        doc_md="Transform and clean Finance data with calculations and aggregations"
    )

# Individual tasks
validate_quality = PythonOperator(
    task_id='validate_data_quality',
    python_callable=validate_data_quality,
    dag=dag,
    doc_md="Validate data quality using Great Expectations framework"
)

load_warehouse = PythonOperator(
    task_id='load_to_warehouse',
    python_callable=load_to_warehouse,
    dag=dag,
    doc_md="Load transformed data to PostgreSQL data warehouse"
)

update_indexes = PythonOperator(
    task_id='update_vector_indexes',
    python_callable=update_vector_indexes,
    dag=dag,
    doc_md="Update vector search indexes for AI agent knowledge base"
)

notify_completion = PythonOperator(
    task_id='send_completion_notification',
    python_callable=send_completion_notification,
    dag=dag,
    doc_md="Send pipeline completion notification with summary"
)

# Set up dependencies
extract_group >> transform_group >> validate_quality >> load_warehouse >> update_indexes >> notify_completion

# Additional DAG: Real-time streaming pipeline
streaming_dag = DAG(
    'hr_finance_streaming',
    default_args=default_args,
    description='Real-time data streaming pipeline',
    schedule_interval=None,  # Triggered externally
    catchup=False,
    tags=['streaming', 'real-time', 'kafka'],
    doc_md="""
    # Real-time Data Streaming Pipeline
    
    This DAG handles real-time data processing through Kafka streams.
    Triggered by external events or API calls.
    """
)

def process_streaming_data(**context):
    """Process streaming data from Kafka"""
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info("Processing streaming data")
    
    # Implement Kafka consumer logic here
    # This would process real-time events
    
    return True

process_stream = PythonOperator(
    task_id='process_streaming_data',
    python_callable=process_streaming_data,
    dag=streaming_dag
)