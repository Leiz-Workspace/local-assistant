"""Join owned memory SQL/model work despite repeated parent cancellation without logging private content."""

import asyncio
import logging

from apps.api.services.files import finish_task

logger = logging.getLogger(__name__)


async def joined_memory_work(awaitable, *, timeout=None):
    """Shield an owned child, cancel it once on interruption and join its cleanup before returning."""
    work = asyncio.create_task(awaitable)
    try:
        if timeout is None:
            return await asyncio.shield(work)
        return await asyncio.wait_for(asyncio.shield(work), timeout)
    finally:
        if not work.done():
            work.cancel()
        try:
            await finish_task(work)
        except BaseException:
            logger.info("memory_owned_work_joined")
