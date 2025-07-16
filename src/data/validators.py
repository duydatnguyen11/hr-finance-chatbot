# src/data/validators.py
"""Data validation utilities"""

from typing import Dict, List, Any, Optional
import polars as pl
import re
from datetime import datetime
from ..utils import logger

class SchemaValidator:
    """Schema validation for data structures"""
    
    @staticmethod
    def validate_employee_schema(df: pl.DataFrame) -> Dict[str, Any]:
        """Validate employee data schema"""
        required_columns = [
            "employee_id", "first_name", "last_name", 
            "email", "department", "salary", "hire_date"
        ]
        
        errors = []
        warnings = []
        
        # Check required columns
        missing_columns = set(required_columns) - set(df.columns)
        if missing_columns:
            errors.append(f"Missing required columns: {missing_columns}")
        
        # Check data types
        expected_types = {
            "employee_id": [pl.Int64, pl.Int32],
            "salary": [pl.Float64, pl.Int64],
            "performance_rating": [pl.Float64],
        }
        
        for col, expected in expected_types.items():
            if col in df.columns:
                actual_type = df[col].dtype
                if actual_type not in expected:
                    warnings.append(f"Column {col} has type {actual_type}, expected one of {expected}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

class BusinessRuleValidator:
    """Business rule validation"""
    
    @staticmethod
    def validate_business_rules(df: pl.DataFrame) -> Dict[str, Any]:
        """Validate business rules for employee data"""
        errors = []
        warnings = []
        
        # Rule 1: Salary should be positive
        if "salary" in df.columns:
            negative_salaries = df.filter(pl.col("salary") <= 0).height
            if negative_salaries > 0:
                errors.append(f"Found {negative_salaries} employees with non-positive salaries")
        
        # Rule 2: Performance rating should be between 1 and 5
        if "performance_rating" in df.columns:
            invalid_ratings = df.filter(
                (pl.col("performance_rating") < 1.0) | 
                (pl.col("performance_rating") > 5.0)
            ).height
            if invalid_ratings > 0:
                errors.append(f"Found {invalid_ratings} employees with invalid performance ratings")
        
        # Rule 3: Email format validation
        if "email" in df.columns:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            invalid_emails = df.filter(
                ~pl.col("email").str.contains(email_pattern)
            ).height
            if invalid_emails > 0:
                errors.append(f"Found {invalid_emails} employees with invalid email formats")
        
        # Rule 4: Future hire dates
        if "hire_date" in df.columns:
            future_hires = df.filter(
                pl.col("hire_date") > pl.date.today()
            ).height
            if future_hires > 0:
                warnings.append(f"Found {future_hires} employees with future hire dates")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
