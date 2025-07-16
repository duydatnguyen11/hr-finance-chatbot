# src/data/transformers.py
"""Data transformation utilities"""

import polars as pl
from typing import Dict, List, Any
from datetime import datetime

class TransformationPipeline:
    """Pipeline for data transformations"""
    
    def __init__(self):
        self.transformations = []
    
    def add_transformation(self, func, **kwargs):
        """Add transformation function to pipeline"""
        self.transformations.append((func, kwargs))
        return self
    
    def execute(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """Execute all transformations in sequence"""
        result = df
        for func, kwargs in self.transformations:
            result = func(result, **kwargs)
        return result

class EmployeeTransformations:
    """Employee-specific data transformations"""
    
    @staticmethod
    def standardize_names(df: pl.LazyFrame) -> pl.LazyFrame:
        """Standardize name formatting"""
        return df.with_columns([
            pl.col("first_name").str.strip_chars().str.to_titlecase(),
            pl.col("last_name").str.strip_chars().str.to_titlecase()
        ])
    
    @staticmethod
    def calculate_age_groups(df: pl.LazyFrame) -> pl.LazyFrame:
        """Calculate age groups based on hire date"""
        return df.with_columns([
            pl.when(pl.col("tenure_years") < 1)
            .then("New Hire")
            .when(pl.col("tenure_years") < 3)
            .then("Junior")
            .when(pl.col("tenure_years") < 7)
            .then("Mid-level")
            .when(pl.col("tenure_years") < 15)
            .then("Senior")
            .otherwise("Veteran")
            .alias("experience_level")
        ])
    
    @staticmethod
    def categorize_performance(df: pl.LazyFrame) -> pl.LazyFrame:
        """Categorize performance ratings"""
        return df.with_columns([
            pl.when(pl.col("performance_rating") >= 4.5)
            .then("Exceptional")
            .when(pl.col("performance_rating") >= 4.0)
            .then("High Performer")
            .when(pl.col("performance_rating") >= 3.5)
            .then("Good Performer")
            .when(pl.col("performance_rating") >= 3.0)
            .then("Meets Expectations")
            .otherwise("Needs Improvement")
            .alias("performance_category")
        ])