"""
Central declarative base class for all SQLAlchemy ORM models.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Central declarative base class for all SQLAlchemy ORM models.
    """

    pass


__all__ = ["Base"]
