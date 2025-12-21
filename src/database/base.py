"""
Shared SQLAlchemy Base for all database models.

This module provides a single, shared declarative base that all database models
should inherit from. This ensures that all tables are created together when
Base.metadata.create_all() is called.

Usage:
    from src.database.base import Base
    
    class MyModel(Base):
        __tablename__ = 'my_table'
        ...
"""

from sqlalchemy.orm import declarative_base

# Single shared Base for all models
Base = declarative_base()
