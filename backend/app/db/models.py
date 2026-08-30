"""Central ORM model registration.

Importing this module registers every ORM table on ``Base.metadata``.
All persistence model modules must be imported here so that
``Base.metadata.create_all()`` and Alembic autogenerate see the full
schema — in particular the chat tables (``conversations``,
``conversation_messages``, ``conversation_summaries``) referenced by
foreign keys from the documents tables.
"""

from app.auth.infrastructure.persistence import models as _auth_models  # noqa: F401
from app.chat.infrastructure.persistence import models as _chat_models  # noqa: F401
from app.db.base import Base
from app.documents.infrastructure.persistence import (
    models as _document_models,  # noqa: F401
)
from app.evaluation.infrastructure.persistence import (
    models as _evaluation_models,  # noqa: F401
)

__all__ = ["Base"]
