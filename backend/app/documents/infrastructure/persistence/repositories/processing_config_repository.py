import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.domain.interfaces import ProcessingConfigRepository
from app.documents.domain.models import ProcessingConfigVersion
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyProcessingConfigVersion,
)


class SQLAlchemyProcessingConfigRepository(ProcessingConfigRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_or_create_config(
        self, config: ProcessingConfigVersion
    ) -> tuple[UUID, ProcessingConfigVersion]:
        config_id_hash = config.config_identifier
        stmt = select(SQLAlchemyProcessingConfigVersion).where(
            SQLAlchemyProcessingConfigVersion.config_identifier == config_id_hash
        )
        result = await self._db.execute(stmt)
        db_cfg = result.scalar_one_or_none()

        if not db_cfg:
            db_cfg = SQLAlchemyProcessingConfigVersion(
                id=uuid.uuid4(),
                config_identifier=config_id_hash,
                config_json=config.model_dump(),
            )
            self._db.add(db_cfg)
            await self._db.flush()
            await self._db.refresh(db_cfg)

        return db_cfg.id, ProcessingConfigVersion.model_validate(db_cfg.config_json)

    async def get_config_by_id(self, config_id: UUID) -> ProcessingConfigVersion | None:
        stmt = select(SQLAlchemyProcessingConfigVersion).where(
            SQLAlchemyProcessingConfigVersion.id == config_id
        )
        result = await self._db.execute(stmt)
        db_cfg = result.scalar_one_or_none()
        if not db_cfg:
            return None
        return ProcessingConfigVersion.model_validate(db_cfg.config_json)
