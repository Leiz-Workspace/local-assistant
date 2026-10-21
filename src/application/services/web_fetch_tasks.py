"""Join only owned fetch tasks despite repeated caller cancellation without refactoring earlier accepted helpers."""

import asyncio
import logging

logger = logging.getLogger(__name__)
create_task = asyncio.create_task


def spawn_owned(pending):
    """Transfer one coroutine to a task or close it immediately if task ownership cannot be established."""
    try:
        return create_task(pending)
    except BaseException:
        pending.close()
        logger.info("web_fetch_unstarted_coroutine_closed")
        raise


async def finish_owned(task):
    """Keep an owned resolver/socket/request task pinned until its actual result or cancellation is observable."""
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.done():
                return task.result()
            logger.info("web_fetch_owned_join_retained")
