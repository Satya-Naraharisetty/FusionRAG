import asyncio
import logging
import uuid
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.auth.infrastructure.persistence.models import Base, SQLAlchemyUser
from app.chat.infrastructure.persistence.models import ConversationORM
from app.chat.infrastructure.persistence.repositories import SQLAlchemyConversationRepository
from app.chat.domain.models import Conversation, ConversationSettings, ConversationState
from app.chat.domain.exceptions import ConversationConcurrentUpdateException

logging.basicConfig(level=logging.INFO)
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/hybrid_rag"

async def main():
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    
    db = SessionLocal()
    # Create user
    user_id = uuid.uuid4()
    user = SQLAlchemyUser(
        id=user_id,
        email=f"lock_test_{uuid.uuid4()}@example.com",
        hashed_password="hash",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    
    repo = SQLAlchemyConversationRepository(db)
    conv_id = uuid.uuid4()
    conv = Conversation(
        id=conv_id,
        user_id=user_id,
        title="Initial Title",
        state=ConversationState.ACTIVE,
        settings=ConversationSettings(),
        version=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        last_message_at=datetime.utcnow(),
    )
    
    created = await repo.create_conversation(conv)
    db.commit()
    print("Created version:", created.version)
    
    # Update once to increase version
    created.title = "First Update"
    updated = await repo.update_conversation(created)
    db.commit()
    print("Updated version:", updated.version)
    
    # Load stale instance
    stale = await repo.get_conversation(conv_id)
    print("Stale instance version:", stale.version)
    
    # Simulate external update to DB directly
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE conversations SET version = 3, title = 'External Update' WHERE id = :id"),
            {"id": conv_id}
        )
        conn.commit()
    print("Direct DB update completed.")
    
    # Try updating via repo in Session A
    stale.title = "Stale Update"
    try:
        await repo.update_conversation(stale)
        db.commit()
        print("Stale update succeeded somehow!")
    except Exception as e:
        print("Caught expected exception:", type(e), str(e))
        
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
