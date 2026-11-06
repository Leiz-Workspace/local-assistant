"""Own one fixed-CORE bounded multi-query run with charged attempts, truthful partial outcomes and joined cancellation."""

import asyncio
import hashlib
import logging
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from src.application.ports.research import ResearchQuery, ResearchResult, ResearchSource
from src.application.services.research_policy import (
    MAX_PLAN_TOKENS,
    ResearchError,
    canonical_query,
    check_result,
    plan_messages,
    resolve_plan,
)
from src.application.services.search_pipeline import validate_batch
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.application.services.web_search_policy import WebSearchError, WebSearchQuota

logger = logging.getLogger(__name__)
TOTAL_SECONDS = 45
MODEL_SECONDS = 15
PROVIDER_SECONDS = 10


def cancelled():
    """Refuse publication/continued dispatch when a dependency has swallowed the owning task's cancellation."""
    if asyncio.current_task().cancelling():
        raise asyncio.CancelledError()


class ResearchService:
    """Retain nonqueued owner-bound plan/search admission until all owned backend cleanup has actually completed."""

    def __init__(self, *, provider_id, provider, inference, expected_model, quota=None):
        """Bind trusted inert dependencies and server-owned quota without an endpoint, credential, model startup or source fetch."""
        if (
            type(provider_id) is not str
            or re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", provider_id) is None
            or type(expected_model) is not str
            or not 1 <= len(expected_model) <= 128
        ):
            raise ResearchError("research_invalid")
        self.provider_id, self.provider, self.inference, self.expected_model = (
            provider_id,
            provider,
            inference,
            expected_model,
        )
        self.quota = quota if quota is not None else WebSearchQuota()
        self.admission = asyncio.Lock()
        self.operations = set()
        self.closing = False
        logger.info("research_service_initialized")

    def charge(self, owner):
        """Charge each admitted model/provider attempt once using the accepted finite principal quota and no refunds."""
        try:
            self.quota.charge(owner)
        except WebSearchError as error:
            raise ResearchError(
                "research_rate_limited"
                if error.code == "web_search_rate_limited"
                else "research_unavailable"
            ) from None

    async def run(self, owner, goal):
        """Resolve one complete fixed plan then execute at mostthree sequential queries without retries, source fetch or generated answers."""
        queries = None
        outcomes = []
        attempts = 0
        try:
            async with asyncio.timeout(TOTAL_SECONDS):
                try:
                    async with asyncio.timeout(MODEL_SECONDS) as model_deadline:
                        completion = await self.inference.complete(
                            profile="core",
                            messages=plan_messages(goal),
                            preset="fast",
                            temperature=0,
                            max_tokens=MAX_PLAN_TOKENS,
                        )
                    if model_deadline.expired():
                        raise TimeoutError()
                    cancelled()
                except TimeoutError:
                    raise ResearchError("research_model_timeout") from None
                except asyncio.CancelledError:
                    raise
                except ResearchError:
                    raise
                except Exception:
                    raise ResearchError("research_model_failed") from None
                queries = resolve_plan(completion, self.expected_model)
                for index, query in enumerate(queries, 1):
                    try:
                        self.charge(owner)
                    except ResearchError as error:
                        if error.code != "research_rate_limited":
                            raise
                        outcomes.extend(
                            ResearchQuery(
                                f"Q{other + 1}",
                                queries[other],
                                "not_run_quota",
                                False,
                                "research_rate_limited",
                                None,
                                (),
                            )
                            for other in range(index - 1, len(queries))
                        )
                        break
                    attempts += 1
                    sources = ()
                    error_code = None
                    received = None
                    try:
                        async with asyncio.timeout(
                            PROVIDER_SECONDS
                        ) as provider_deadline:
                            batch = await self.provider.search(
                                query=query, max_results=5
                            )
                        if provider_deadline.expired():
                            raise TimeoutError()
                        cancelled()
                        hits = validate_batch(batch, self.provider_id)
                        received = datetime.now(UTC)
                        sources = tuple(
                            ResearchSource(
                                f"Q{index}:S{rank}",
                                hit.title,
                                hit.url,
                                hit.snippet,
                                hashlib.sha256(hit.snippet.encode()).hexdigest(),
                            )
                            for rank, hit in enumerate(hits, 1)
                        )
                        status = "sources" if sources else "empty"
                    except TimeoutError:
                        status, error_code = "error", "research_provider_timeout"
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        status, error_code = "error", "research_provider_failed"
                    outcomes.append(
                        ResearchQuery(
                            f"Q{index}",
                            query,
                            status,
                            True,
                            error_code,
                            received,
                            sources,
                        )
                    )
                    logger.info(
                        "research_query_finished ordinal=%d status=%s", index, status
                    )
        except TimeoutError:
            if queries is None:
                raise ResearchError("research_timeout") from None
            for index in range(len(outcomes), len(queries)):
                attempted = index < attempts
                outcomes.append(
                    ResearchQuery(
                        f"Q{index + 1}",
                        queries[index],
                        "error" if attempted else "not_run_budget",
                        attempted,
                        "research_timeout",
                        None,
                        (),
                    )
                )
            logger.info("research_total_budget_exhausted")
        cancelled()
        has_sources = any(row.sources for row in outcomes)
        incomplete = any(
            row.status in {"error", "not_run_budget", "not_run_quota"}
            for row in outcomes
        )
        status = (
            "no_sources" if not has_sources else "partial" if incomplete else "complete"
        )
        return check_result(
            ResearchResult(
                uuid4(),
                owner,
                goal,
                tuple(outcomes),
                status,
                1,
                attempts,
                datetime.now(UTC),
            )
        )

    async def research(self, owner, goal):
        """Validate/charge one explicit run and shield/join its owning task before releasing admission under repeated cancellation."""
        if type(owner) is not UUID:
            raise ResearchError("research_invalid")
        goal = canonical_query(goal)
        if self.closing:
            raise ResearchError("research_closed")
        if self.provider is None or self.inference is None:
            raise ResearchError("research_unavailable")
        if self.admission.locked():
            raise ResearchError("research_busy")
        await self.admission.acquire()
        caller = asyncio.current_task()
        try:
            self.charge(owner)
            self.operations.add(caller)
            task = spawn_owned(self.run(owner, goal))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                task.cancel()
                try:
                    await finish_owned(task)
                except BaseException:
                    logger.info("research_cancelled_run_joined")
                raise
        except asyncio.CancelledError:
            raise
        except ResearchError:
            raise
        except Exception:
            raise ResearchError("research_internal") from None
        finally:
            self.operations.discard(caller)
            self.admission.release()
            logger.info("research_operation_closed")

    async def shutdown(self):
        """Reject new runs and cancel/join only this service's callers without touching shared models/provider/services."""
        self.closing = True
        tasks = [task for task in self.operations if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("research_shutdown_run_joined")
        logger.info("research_shutdown_complete")
