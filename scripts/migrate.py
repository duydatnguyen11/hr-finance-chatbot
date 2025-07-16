#!/usr/bin/env python3
"""
Database migration script for HR Finance Chatbot
"""

import asyncio
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

import asyncpg
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseMigrator:
    """Database migration manager"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.migrations_dir = Path("migrations")
        self.migrations_dir.mkdir(exist_ok=True)
        
        # Create async engine
        async_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
        self.engine = create_async_engine(async_url)
    
    async def initialize_migration_table(self):
        """Create migration tracking table if it doesn't exist"""
        async with self.engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(255) PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                )
            """))
        logger.info("Migration table initialized")
    
    async def get_applied_migrations(self) -> List[str]:
        """Get list of applied migrations"""
        async with self.engine.begin() as conn:
            result = await conn.execute(text(
                "SELECT version FROM schema_migrations ORDER BY version"
            ))
            return [row[0] for row in result.fetchall()]
    
    def get_available_migrations(self) -> List[Dict[str, Any]]:
        """Get list of available migration files"""
        migrations = []
        
        for file_path in sorted(self.migrations_dir.glob("*.sql")):
            # Parse migration filename: 001_create_tables.sql
            parts = file_path.stem.split('_', 1)
            if len(parts) == 2:
                version, description = parts
                migrations.append({
                    "version": version,
                    "description": description.replace('_', ' ').title(),
                    "file_path": file_path
                })
        
        return migrations
    
    async def apply_migration(self, migration: Dict[str, Any]):
        """Apply a single migration"""
        logger.info(f"Applying migration {migration['version']}: {migration['description']}")
        
        # Read migration file
        with open(migration['file_path'], 'r') as f:
            sql_content = f.read()
        
        async with self.engine.begin() as conn:
            # Execute migration SQL
            await conn.execute(text(sql_content))
            
            # Record migration as applied
            await conn.execute(text("""
                INSERT INTO schema_migrations (version, description) 
                VALUES (:version, :description)
            """), {
                "version": migration['version'],
                "description": migration['description']
            })
        
        logger.info(f"Migration {migration['version']} applied successfully")
    
    async def rollback_migration(self, version: str):
        """Rollback a specific migration"""
        rollback_file = self.migrations_dir / f"{version}_rollback.sql"
        
        if not rollback_file.exists():
            raise FileNotFoundError(f"Rollback file not found: {rollback_file}")
        
        logger.info(f"Rolling back migration {version}")
        
        with open(rollback_file, 'r') as f:
            sql_content = f.read()
        
        async with self.engine.begin() as conn:
            # Execute rollback SQL
            await conn.execute(text(sql_content))
            
            # Remove migration record
            await conn.execute(text(
                "DELETE FROM schema_migrations WHERE version = :version"
            ), {"version": version})
        
        logger.info(f"Migration {version} rolled back successfully")
    
    async def migrate(self):
        """Apply all pending migrations"""
        await self.initialize_migration_table()
        
        applied_migrations = await self.get_applied_migrations()
        available_migrations = self.get_available_migrations()
        
        pending_migrations = [
            m for m in available_migrations 
            if m['version'] not in applied_migrations
        ]
        
        if not pending_migrations:
            logger.info("No pending migrations")
            return
        
        logger.info(f"Found {len(pending_migrations)} pending migrations")
        
        for migration in pending_migrations:
            await self.apply_migration(migration)
        
        logger.info("All migrations applied successfully")
    
    async def status(self):
        """Show migration status"""
        await self.initialize_migration_table()
        
        applied_migrations = await self.get_applied_migrations()
        available_migrations = self.get_available_migrations()
        
        print("\nMigration Status:")
        print("=" * 50)
        
        for migration in available_migrations:
            status = "✓ Applied" if migration['version'] in applied_migrations else "✗ Pending"
            print(f"{migration['version']}: {migration['description']} - {status}")
        
        print(f"\nTotal: {len(available_migrations)} migrations")
        print(f"Applied: {len(applied_migrations)} migrations")
        print(f"Pending: {len(available_migrations) - len(applied_migrations)} migrations")

def create_initial_migrations():
    """Create initial migration files"""
    migrations_dir = Path("migrations")
    migrations_dir.mkdir(exist_ok=True)
    
    # Migration 001: Create initial tables
    migration_001 = """-- Migration 001: Create initial tables
-- Created: 2024-01-15

-- Employees table
CREATE TABLE employees (
    employee_id SERIAL PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    department VARCHAR(100),
    position VARCHAR(100),
    hire_date DATE,
    salary DECIMAL(10,2),
    status VARCHAR(20) DEFAULT 'active',
    performance_rating DECIMAL(3,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Departments table
CREATE TABLE departments (
    department_id SERIAL PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL,
    manager_id INTEGER REFERENCES employees(employee_id),
    budget DECIMAL(12,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Expenses table
CREATE TABLE expenses (
    expense_id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(employee_id),
    department_id INTEGER REFERENCES departments(department_id),
    category VARCHAR(100),
    amount DECIMAL(10,2),
    expense_date DATE,
    description TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Documents table
CREATE TABLE documents (
    document_id SERIAL PRIMARY KEY,
    filename VARCHAR(255),
    document_type VARCHAR(100),
    content TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_employees_department ON employees(department);
CREATE INDEX idx_employees_status ON employees(status);
CREATE INDEX idx_expenses_date ON expenses(expense_date);
CREATE INDEX idx_documents_type ON documents(document_type);
"""

    # Migration 002: Add performance reviews table
    migration_002 = """-- Migration 002: Add performance reviews table
-- Created: 2024-01-15

CREATE TABLE performance_reviews (
    review_id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(employee_id),
    reviewer_id INTEGER REFERENCES employees(employee_id),
    review_period VARCHAR(20),
    rating DECIMAL(3,2),
    goals_met BOOLEAN,
    comments TEXT,
    review_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_performance_reviews_employee ON performance_reviews(employee_id);
CREATE INDEX idx_performance_reviews_date ON performance_reviews(review_date);
"""

    # Migration 003: Add budget tracking tables
    migration_003 = """-- Migration 003: Add budget tracking tables
-- Created: 2024-01-15

CREATE TABLE budgets (
    budget_id SERIAL PRIMARY KEY,
    department_id INTEGER REFERENCES departments(department_id),
    fiscal_year INTEGER,
    quarter INTEGER,
    budget_amount DECIMAL(12,2),
    allocated_amount DECIMAL(12,2) DEFAULT 0,
    spent_amount DECIMAL(12,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE budget_allocations (
    allocation_id SERIAL PRIMARY KEY,
    budget_id INTEGER REFERENCES budgets(budget_id),
    category VARCHAR(100),
    allocated_amount DECIMAL(12,2),
    spent_amount DECIMAL(12,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_budgets_department_year ON budgets(department_id, fiscal_year);
CREATE INDEX idx_budget_allocations_budget ON budget_allocations(budget_id);
"""

    # Write migration files
    migrations = [
        ("001", migration_001),
        ("002", migration_002), 
        ("003", migration_003)
    ]
    
    for version, content in migrations:
        file_path = migrations_dir / f"{version}_initial_schema.sql"
        if not file_path.exists():
            with open(file_path, 'w') as f:
                f.write(content)
            logger.info(f"Created migration file: {file_path}")

def create_sample_data_migration():
    """Create migration with sample data"""
    migrations_dir = Path("migrations")
    
    sample_data = """-- Migration 004: Insert sample data
-- Created: 2024-01-15

-- Insert sample departments
INSERT INTO departments (department_name, budget) VALUES
    ('Engineering', 500000),
    ('Finance', 300000),
    ('HR', 200000),
    ('Marketing', 250000),
    ('Sales', 400000);

-- Insert sample employees
INSERT INTO employees (first_name, last_name, email, department, position, hire_date, salary, performance_rating) VALUES
    ('John', 'Doe', 'john.doe@company.com', 'Engineering', 'Senior Developer', '2022-01-15', 85000, 4.5),
    ('Jane', 'Smith', 'jane.smith@company.com', 'Finance', 'Financial Analyst', '2021-03-10', 65000, 4.2),
    ('Bob', 'Johnson', 'bob.johnson@company.com', 'HR', 'HR Manager', '2020-05-20', 75000, 4.8),
    ('Alice', 'Brown', 'alice.brown@company.com', 'Engineering', 'Lead Developer', '2022-06-01', 90000, 4.1),
    ('Charlie', 'Wilson', 'charlie.wilson@company.com', 'Finance', 'Senior Analyst', '2021-11-15', 70000, 4.6),
    ('Diana', 'Davis', 'diana.davis@company.com', 'Marketing', 'Marketing Manager', '2021-08-03', 72000, 4.3),
    ('Edward', 'Miller', 'edward.miller@company.com', 'Sales', 'Sales Director', '2020-12-10', 95000, 4.7),
    ('Fiona', 'Garcia', 'fiona.garcia@company.com', 'Engineering', 'DevOps Engineer', '2023-02-14', 78000, 4.0);

-- Insert sample expenses
INSERT INTO expenses (employee_id, category, amount, expense_date, description, status) VALUES
    (1, 'Travel', 1200.50, '2024-01-15', 'Conference travel to San Francisco', 'approved'),
    (2, 'Office', 350.00, '2024-01-16', 'Office supplies and equipment', 'pending'),
    (3, 'Training', 800.00, '2024-01-17', 'HR certification course', 'approved'),
    (1, 'Equipment', 2500.00, '2024-01-18', 'New laptop and monitor', 'pending'),
    (2, 'Software', 199.99, '2024-01-19', 'Financial analysis software license', 'approved');

-- Insert sample performance reviews
INSERT INTO performance_reviews (employee_id, reviewer_id, review_period, rating, goals_met, comments, review_date) VALUES
    (1, 3, 'Q4 2023', 4.5, true, 'Excellent performance, exceeded all goals', '2024-01-10'),
    (2, 3, 'Q4 2023', 4.2, true, 'Strong analytical skills, good team collaboration', '2024-01-11'),
    (4, 3, 'Q4 2023', 4.1, true, 'Good technical leadership, room for improvement in communication', '2024-01-12');
"""
    
    file_path = migrations_dir / "004_sample_data.sql"
    if not file_path.exists():
        with open(file_path, 'w') as f:
            f.write(sample_data)
        logger.info(f"Created sample data migration: {file_path}")

async def main():
    """Main migration script"""
    parser = argparse.ArgumentParser(description="HR Finance Chatbot Database Migration Tool")
    parser.add_argument("--database-url", default="postgresql://postgres:password@localhost:5432/hrfinance",
                       help="Database connection URL")
    parser.add_argument("--action", choices=["migrate", "status", "rollback", "create"], 
                       default="migrate", help="Migration action")
    parser.add_argument("--version", help="Migration version for rollback")
    parser.add_argument("--create-sample", action="store_true", 
                       help="Create sample migration files")
    
    args = parser.parse_args()
    
    if args.create_sample:
        create_initial_migrations()
        create_sample_data_migration()
        return
    
    migrator = DatabaseMigrator(args.database_url)
    
    try:
        if args.action == "migrate":
            await migrator.migrate()
        elif args.action == "status":
            await migrator.status()
        elif args.action == "rollback":
            if not args.version:
                print("Error: --version required for rollback")
                return
            await migrator.rollback_migration(args.version)
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        raise
    finally:
        await migrator.engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
