import logging
import uuid
from datetime import UTC, datetime
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.chat.domain.events import ConversationCreated, ConversationMessageCreated
from app.chat.domain.exceptions import ConversationNotFoundException
from app.chat.domain.interfaces import (
    ConversationMemory,
    ConversationRepository,
    ConversationTitleGenerator,
    HistoryRewriter,
    MessageRepository,
    SummaryRepository,
)
from app.chat.domain.models import (
    Conversation,
    ConversationContext,
    ConversationMessage,
    ConversationSettings,
    HistoryRewriteResult,
    MessageRole,
    MessageStatus,
)
from app.chat.services.access_service import ConversationAccessService
from app.documents.domain.events import EventDispatcher
from app.documents.services.document_service import DocumentService

logger = logging.getLogger(__name__)


class ConversationManager:
    def __init__(
        self,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
        summary_repo: SummaryRepository,
        access_service: ConversationAccessService,
        memory: ConversationMemory,
        rewriter: HistoryRewriter,
        title_generator: ConversationTitleGenerator,
        event_dispatcher: EventDispatcher,
        document_service: DocumentService | None = None,
        db: Session | None = None,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        self._conversation_repo = conversation_repo
        self._message_repo = message_repo
        self._summary_repo = summary_repo
        self._access_service = access_service
        self._memory = memory
        self._rewriter = rewriter
        self._title_generator = title_generator
        self._event_dispatcher = event_dispatcher
        self._document_service = document_service
        self._db = db
        self._background_tasks = background_tasks

    async def get_or_create_conversation(
        self,
        conversation_id: UUID | None,
        user_id: UUID,
        settings: ConversationSettings | None = None,
    ) -> Conversation:
        """
        Retrieves an existing conversation (verifying ownership) or creates a new one.
        """
        if conversation_id:
            await self._access_service.verify_owner(conversation_id, user_id)
            conversation = await self._conversation_repo.get_conversation(
                conversation_id
            )
            if not conversation:
                raise ConversationNotFoundException(
                    f"Conversation {conversation_id} not found."
                )
            return conversation

        # Create new conversation
        now = datetime.now(UTC)
        new_conv = Conversation(
            id=uuid.uuid4(),
            user_id=user_id,
            title="New Conversation",
            settings=settings or ConversationSettings(),
            version=1,
            created_at=now,
            updated_at=now,
            last_message_at=now,
        )
        saved_conv = await self._conversation_repo.create_conversation(new_conv)
        self._event_dispatcher.dispatch(ConversationCreated(saved_conv.id, user_id))
        return saved_conv

    async def prepare_context(
        self,
        conversation_id: UUID,
        user_id: UUID,
        question: str,
        skip_rewrite: bool = False,
    ) -> tuple[ConversationContext, HistoryRewriteResult]:
        """
        Orchestrates memory loading and query rewriting, saves the incoming user message,
        and returns the ConversationContext before generating assistant responses.

        When ``skip_rewrite`` is True (e.g. the user has no uploaded documents
        to retrieve from), the LLM query-rewrite call is skipped and the
        original question is used as-is — the rewrite only exists to improve
        retrieval, so the extra LLM call would be wasted.
        """
        # 1. Ownership validation
        await self._access_service.verify_owner(conversation_id, user_id)

        # 2. Load memory (recent messages + summary) before appending new question
        recent_messages, summary = await self._memory.load_memory(conversation_id)

        # 3. Rewrite follow-up question
        if skip_rewrite:
            rewrite_result = HistoryRewriteResult(
                original_query=question,
                rewritten_query=question,
                rewrite_reason="No documents uploaded; query rewrite skipped.",
                rewrite_applied=False,
            )
        else:
            rewrite_result = await self._rewriter.rewrite(question, recent_messages)

        # 4. Save user message to database
        user_message = ConversationMessage(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=question,
            status=MessageStatus.COMPLETED,
            created_at=datetime.now(UTC),
        )
        await self._message_repo.add_message(user_message)

        # 5. Update last_message_at and message count in conversation details
        conversation = await self._conversation_repo.get_conversation(conversation_id)
        if conversation is None:
            raise ConversationNotFoundException(
                f"Conversation {conversation_id} not found."
            )
        conversation.last_message_at = datetime.now(UTC)
        conversation.metadata.message_count = await self._message_repo.count_messages(
            conversation_id
        )
        await self._conversation_repo.update_conversation(conversation)

        # Build Context containing loaded memory
        context = ConversationContext(
            conversation=conversation,
            recent_messages=recent_messages,
            summary=summary,
        )

        return context, rewrite_result

    async def finalize_message(
        self,
        conversation_id: UUID,
        message_id: UUID,
        assistant_content: str,
        prompt_tokens: int,
        completion_tokens: int,
        citations: list[dict] | None = None,
        metadata: dict | None = None,
    ) -> None:
        """
        Completes the assistant's message in the DB and dispatches domain events to trigger background summarization.
        Auto-generates the conversation title if this is the first turn.
        """
        # 1. Complete the message in database. Content is applied here for the
        # synchronous path; the streaming path already accumulated it via
        # append_stream_chunk (and passing the same value is idempotent).
        await self._message_repo.complete_message(
            message_id=message_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            citations=citations,
            content=assistant_content,
            metadata=metadata,
        )

        # 2. Check if we need to auto-generate the title (if conversation only has first user + assistant messages)
        conversation = await self._conversation_repo.get_conversation(conversation_id)
        if conversation and conversation.title == "New Conversation":
            # Check message count
            count = await self._message_repo.count_messages(conversation_id)
            if count == 2:
                # Retrieve the messages
                messages = await self._message_repo.get_recent_messages(
                    conversation_id, limit=2
                )
                user_msg = next(
                    (m.content for m in messages if m.role == MessageRole.USER), None
                )
                if user_msg:
                    new_title = await self._title_generator.generate_title(
                        first_user_message=user_msg,
                        assistant_answer=assistant_content,
                    )
                    conversation.title = new_title
                    conversation = await self._conversation_repo.update_conversation(
                        conversation
                    )

        # 3. Update last message metadata
        if conversation:
            conversation.metadata.last_model = conversation.settings.model
            conversation.metadata.last_provider = conversation.settings.provider
            conversation.metadata.last_tokens = prompt_tokens + completion_tokens
            conversation.metadata.message_count = (
                await self._message_repo.count_messages(conversation_id)
            )
            await self._conversation_repo.update_conversation(conversation)

        # 4. Dispatch domain event to handle background tasks (like summarization)
        self._event_dispatcher.dispatch(
            ConversationMessageCreated(
                conversation_id=conversation_id,
                message_id=message_id,
                message_role=MessageRole.ASSISTANT,
            )
        )

    async def delete_conversation(self, conversation_id: UUID, user_id: UUID) -> int:
        """
        Deletes a conversation and all associated documents durably.
        Returns the count of deleted documents.
        """
        # Verify ownership first
        await self._access_service.verify_owner(conversation_id, user_id)

        from app.core.config import settings
        from app.documents.infrastructure.persistence.models import (
            SQLAlchemyCleanupJob,
            SQLAlchemyDocument,
        )

        deleted_docs_count = 0
        job_ids = []

        if self._db:
            # Query conversation-scoped documents and their chunks before deleting them
            db_docs = (
                self._db.query(SQLAlchemyDocument)
                .filter(
                    SQLAlchemyDocument.conversation_id == conversation_id,
                    SQLAlchemyDocument.user_id == user_id,
                    SQLAlchemyDocument.scope == "CONVERSATION",
                )
                .all()
            )
            deleted_docs_count = len(db_docs)

            for doc in db_docs:
                payload = {
                    "document_id": str(doc.id),
                    "user_id": str(doc.user_id),
                    "conversation_id": str(doc.conversation_id),
                    "storage_key": doc.filename,
                    "qdrant_collection_name": settings.QDRANT_COLLECTION,
                    "qdrant_point_ids": [str(chunk.id) for chunk in doc.chunks],
                }

                # Uniqueness / Idempotency check:
                # If a job already exists for this document, reset it to PENDING.
                existing_job = (
                    self._db.query(SQLAlchemyCleanupJob)
                    .filter(
                        SQLAlchemyCleanupJob.resource_type == "document",
                        SQLAlchemyCleanupJob.resource_id == doc.id,
                    )
                    .first()
                )

                if not existing_job:
                    job = SQLAlchemyCleanupJob(
                        id=uuid.uuid4(),
                        resource_type="document",
                        resource_id=doc.id,
                        payload=payload,
                        status="PENDING",
                        attempts=0,
                    )
                    self._db.add(job)
                    job_ids.append(job.id)
                else:
                    existing_job.status = "PENDING"
                    existing_job.attempts = 0
                    existing_job.payload = payload
                    job_ids.append(existing_job.id)

                # Delete the document record from Postgres (cascades delete to chunks and embeddings)
                self._db.delete(doc)

            # Delete the conversation (soft delete)
            await self._conversation_repo.delete_conversation(conversation_id)

            self._db.flush()
            # Commit the PostgreSQL transaction atomically
            self._db.commit()

            # Trigger asynchronous external cleanup jobs after commit
            if job_ids and self._background_tasks:
                self._background_tasks.add_task(self._run_cleanup_jobs, job_ids)

        return deleted_docs_count

    async def _run_cleanup_jobs(self, job_ids: list[UUID]) -> None:
        """
        Runs the cleanup jobs in the background.
        """
        import sys

        from sqlalchemy.orm import sessionmaker

        from app.api.dependencies import (
            get_index_cache,
            get_storage_provider,
            get_vector_store,
        )
        from app.core.config import settings
        from app.db.session import init_postgres_engine
        from app.documents.services.cleanup_worker import DurableCleanupWorker

        db_url = settings.DATABASE_URL
        if "pytest" in sys.modules:
            import os

            db_url = os.environ.get(
                "TEST_DATABASE_URL",
                "postgresql://postgres:postgres@localhost:5433/hybrid_rag_test",
            )

        if not db_url:
            raise ValueError("DATABASE_URL setting is not configured.")

        engine = init_postgres_engine(db_url)
        session_factory = sessionmaker(bind=engine)
        db = session_factory()
        try:
            storage_provider = get_storage_provider(db)
            vector_store = get_vector_store()
            index_cache = get_index_cache()
            worker = DurableCleanupWorker(
                db, storage_provider, vector_store, index_cache
            )

            for jid in job_ids:
                try:
                    await worker.process_job(jid)
                except Exception as e:
                    logger.error(
                        f"Error processing cleanup job {jid} in background: {e}"
                    )
        finally:
            db.close()
