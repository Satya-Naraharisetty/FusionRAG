import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import redis

from app.core.events.interfaces import BaseEventBus, IntegrationEvent

logger = logging.getLogger(__name__)


class RedisEventBus(BaseEventBus):
    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client
        self._handlers: dict[str, list[Callable[[Any], Any]]] = {}
        self._consumer_task: asyncio.Task | None = None
        self._is_running = False

    def _get_event_name(self, event_type: type[IntegrationEvent]) -> str:
        return event_type.__name__

    async def publish(self, event: IntegrationEvent) -> None:
        event_name = type(event).__name__
        payload = event.model_dump_json()
        try:
            # Publish to Redis Stream 'stream:events'
            self._redis.xadd(
                "stream:events",
                {"event_type": event_name, "payload": payload},
                max_len=10000,  # Approximate size capping
                approximate=True,
            )
        except Exception as e:
            logger.error(f"Failed to publish integration event {event_name} to Redis Stream: {e}")

    async def subscribe(self, event_type: type[IntegrationEvent], handler: Callable[[Any], Any]) -> None:
        event_name = self._get_event_name(event_type)
        if event_name not in self._handlers:
            self._handlers[event_name] = []
        self._handlers[event_name].append(handler)

    async def start_consumer(self) -> None:
        """Start the background consumer loop to process integration events."""
        if self._is_running:
            return
        self._is_running = True
        self._consumer_task = asyncio.create_task(self._consume_loop())
        logger.info("Redis Stream integration event bus consumer started.")

    async def stop_consumer(self) -> None:
        """Stop the background consumer loop gracefully."""
        self._is_running = False
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            logger.info("Redis Stream integration event bus consumer stopped.")

    async def _consume_loop(self) -> None:
        last_id = "$"  # Read only new events that arrive after we start
        while self._is_running:
            try:
                # Read from Redis Stream (blocking). Runs in thread to prevent blocking event loop.
                streams = await asyncio.to_thread(
                    self._redis.xread,
                    {"stream:events": last_id},
                    count=10,
                    block=1000,
                )
                if streams:
                    for _, messages in streams:
                        for msg_id, data in messages:
                            event_name = data.get("event_type")
                            payload_str = data.get("payload")
                            last_id = msg_id

                            if event_name in self._handlers and payload_str:
                                payload = json.loads(payload_str)
                                for handler in self._handlers[event_name]:
                                    try:
                                        if asyncio.iscoroutinefunction(handler):
                                            await handler(payload)
                                        else:
                                            handler(payload)
                                    except Exception as ex:
                                        logger.error(
                                            f"Error in integration event handler for {event_name}: {ex}"
                                        )
            except Exception as e:
                logger.error(f"Error in Redis EventBus consumer loop: {e}")
                await asyncio.sleep(2.0)
