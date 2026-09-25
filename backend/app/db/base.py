"""
Central declarative base class for all SQLAlchemy ORM models.

In SQLAlchemy 2.0+, subclassing `DeclarativeBase` is the standard pattern
to instantiate the central ORM mapper registry and MetaData catalog, enabling
strict static type-checking (with Mypy/Pyright) and Alembic migration autogeneration.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Root declarative base class for all ORM models.
    Acts as the central MetaData and mapper registry.
    """

    pass


__all__ = ["Base"]
