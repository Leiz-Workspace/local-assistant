"""Own bounded caller-policy primary lookup and unverified source comparison without granting page/model authority or changing shared services."""

import asyncio
import logging
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID

from src.application.ports.source_reconciliation import (
    PrimaryCandidate,
    PrimaryLookup,
    SourceComparison,
    SourceSpan,
)
from src.application.services.research import cancelled
from src.application.services.source_reconciliation_policy import (
    SourceComparisonError,
    canonical_goal,
    check_payload,
    comparison_messages,
    host_key,
    prepare_lookup,
    resolve_comparison,
)
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.application.services.web_search_policy import WebSearchError, WebSearchQuota

logger = logging.getLogger(__name__)
LOOKUP_SECONDS = 60
COMPARISON_SECONDS = 20
MODEL_SECONDS = 15


class SourceReconciliationService:
    """Hold one nonqueued owner-bound operation through source/model cleanup while keeping shared evidence keys/cache/model lifetime external."""

    def __init__(
        self,
        *,
        evidence,
        inference,
        expected_model,
        source_quota=None,
        model_quota=None,
    ):
        """Bind inert trusted dependencies and independent finite source/model counters without credentials, network, browser or startup."""
        if type(expected_model) is not str or not 1 <= len(expected_model) <= 128:
            raise SourceComparisonError("source_invalid")
        self.evidence, self.inference, self.expected_model = (
            evidence,
            inference,
            expected_model,
        )
        self.source_quota = (
            source_quota if source_quota is not None else WebSearchQuota()
        )
        self.model_quota = model_quota if model_quota is not None else WebSearchQuota()
        self.admission = asyncio.Lock()
        self.operations = set()
        self.closing = False
        logger.info("source_reconciliation_service_initialized")

    def charge(self, quota, owner):
        """Charge one admitted source/model attempt without refunds or granting model-selected counters/budgets."""
        try:
            quota.charge(owner)
        except WebSearchError as error:
            raise SourceComparisonError(
                "source_rate_limited"
                if error.code == "web_search_rate_limited"
                else "source_unavailable"
            ) from None

    def references(self, owner, selections):
        """Authenticate every exact caller-selected span and require at leasttwo distinct snapshots before inference or publication."""
        if (
            type(selections) is not tuple
            or not 2 <= len(selections) <= 4
            or any(type(item) is not SourceSpan for item in selections)
        ):
            raise SourceComparisonError("source_insufficient")
        try:
            result = tuple(
                self.evidence.cite(owner, item.snapshot, item.start, item.end)
                for item in selections
            )
            identities = [(ref.snapshot_id, ref.start, ref.end) for ref in result]
            if (
                len(set(identities)) != len(result)
                or len({ref.snapshot_id for ref in result}) < 2
            ):
                raise ValueError()
            return result
        except Exception:
            raise SourceComparisonError("source_proof_invalid") from None

    async def owned(self, owner, pending, *, model=False):
        """Admit/charge one operation or close its unstarted coroutine, retaining ownership under repeated caller cancellation."""
        if self.closing or self.admission.locked():
            pending.close()
            raise SourceComparisonError(
                "source_closed" if self.closing else "source_busy"
            )
        await self.admission.acquire()
        caller = asyncio.current_task()
        task = None
        try:
            if model:
                self.charge(self.model_quota, owner)
            self.operations.add(caller)
            task = spawn_owned(pending)
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                task.cancel()
                try:
                    await finish_owned(task)
                except BaseException:
                    logger.info("source_comparison_cancelled_operation_joined")
                raise
        except asyncio.CancelledError:
            raise
        except SourceComparisonError:
            raise
        except Exception:
            raise SourceComparisonError("source_internal") from None
        finally:
            if task is None:
                pending.close()
            if getattr(self.evidence, "closing", False):
                self.closing = True
                logger.warning("source_comparison_dependency_closed_admission_poisoned")
            self.operations.discard(caller)
            self.admission.release()
            logger.info("source_comparison_operation_closed")

    async def lookup(self, owner, candidates, primary_hosts):
        """Validate complete caller-selected candidate/host policy before bounded source acquisition, with no automatic private/model context."""
        if type(owner) is not UUID:
            raise SourceComparisonError("source_invalid")
        if self.evidence is None:
            raise SourceComparisonError("source_unavailable")
        prepared, allowed = prepare_lookup(candidates, primary_hosts)
        return await self.owned(owner, self.run_lookup(owner, prepared, allowed))

    async def run_lookup(self, owner, prepared, allowed):
        """Fetch at mostfour distinct eligible navigation URIs and retain excluded/duplicate/error/limit/quota/deadline states explicitly."""
        rows = []
        snapshots = []
        seen = {}
        attempts = 0
        limited = False
        position = 0
        inflight = False
        try:
            async with asyncio.timeout(LOOKUP_SECONDS) as deadline:
                for index, (raw, nav, fragment, eligible) in enumerate(prepared):
                    position = index
                    inflight = False
                    if not eligible:
                        row = PrimaryCandidate(
                            raw,
                            nav,
                            fragment,
                            "excluded_primary_policy",
                            False,
                            None,
                            None,
                        )
                    elif nav in seen:
                        identifier, confirmed = seen[nav]
                        row = PrimaryCandidate(
                            raw,
                            nav,
                            fragment,
                            "duplicate"
                            if identifier is not None and confirmed
                            else "duplicate_unconfirmed"
                            if identifier is not None
                            else "duplicate_unavailable",
                            False,
                            identifier,
                            None,
                        )
                    elif attempts >= 4:
                        row = PrimaryCandidate(
                            raw, nav, fragment, "not_run_limit", False, None, None
                        )
                    elif limited:
                        row = PrimaryCandidate(
                            raw,
                            nav,
                            fragment,
                            "not_run_quota",
                            False,
                            None,
                            "source_rate_limited",
                        )
                    else:
                        try:
                            self.charge(self.source_quota, owner)
                        except SourceComparisonError as error:
                            if error.code != "source_rate_limited":
                                raise
                            limited = True
                            rows.append(
                                PrimaryCandidate(
                                    raw,
                                    nav,
                                    fragment,
                                    "not_run_quota",
                                    False,
                                    None,
                                    error.code,
                                )
                            )
                            position = index + 1
                            continue
                        attempts += 1
                        inflight = True
                        seen[nav] = (None, False)
                        try:
                            result = await self.evidence.read(
                                owner, nav, "static", use_cache=False
                            )
                            cancelled()
                            snapshot = result.snapshot
                            self.evidence.cite(owner, snapshot, 0, 1)
                            if snapshot.requested_url != nav:
                                raise SourceComparisonError("source_proof_invalid")
                            confirmed = (
                                host_key(urlsplit(snapshot.final_url).hostname or "")
                                in allowed
                            )
                            snapshots.append(snapshot)
                            seen[nav] = (snapshot.identifier, confirmed)
                            row = PrimaryCandidate(
                                raw,
                                nav,
                                fragment,
                                "observed"
                                if confirmed
                                else "unconfirmed_redirect_host",
                                True,
                                snapshot.identifier,
                                None,
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            if getattr(self.evidence, "closing", False):
                                self.closing = True
                                raise SourceComparisonError(
                                    "source_cleanup_uncertain"
                                ) from None
                            row = PrimaryCandidate(
                                raw, nav, fragment, "error", True, None, "source_failed"
                            )
                        inflight = False
                    rows.append(row)
                    position = index + 1
                if deadline.expired():
                    raise SourceComparisonError("source_timeout")
        except TimeoutError:
            if getattr(self.evidence, "closing", False):
                self.closing = True
                raise SourceComparisonError("source_cleanup_uncertain") from None
            for index in range(position, len(prepared)):
                raw, nav, fragment, eligible = prepared[index]
                attempted = inflight and index == position
                rows.append(
                    PrimaryCandidate(
                        raw,
                        nav,
                        fragment,
                        "error"
                        if attempted
                        else "not_run_deadline"
                        if eligible
                        else "excluded_primary_policy",
                        attempted,
                        None,
                        "source_timeout" if eligible else None,
                    )
                )
            logger.info("primary_lookup_deadline_exhausted")
        cancelled()
        partial = any(
            row.status not in {"observed", "duplicate", "excluded_primary_policy"}
            for row in rows
        )
        status = (
            "no_primary_sources"
            if not snapshots
            else "partial"
            if partial
            else "complete"
        )
        logger.info(
            "primary_lookup_finished attempts=%d snapshots=%d", attempts, len(snapshots)
        )
        return check_payload(
            PrimaryLookup(
                owner,
                tuple(rows),
                tuple(snapshots),
                attempts,
                status,
                datetime.now(UTC),
            ),
            1048576,
        )

    async def reconcile(self, owner, goal, selections):
        """Authenticate complete owner-selected quote evidence before charging one fixed CORE comparison operation."""
        if type(owner) is not UUID:
            raise SourceComparisonError("source_invalid")
        if self.evidence is None or self.inference is None:
            raise SourceComparisonError("source_unavailable")
        goal = canonical_goal(goal)
        references = self.references(owner, selections)
        messages = comparison_messages(goal, references)
        return await self.owned(
            owner,
            self.run_reconcile(owner, goal, selections, references, messages),
            model=True,
        )

    async def run_reconcile(self, owner, goal, selections, references, messages):
        """Make one bounded original CORE call and revalidate source proofs before surfacing unverified side-by-side comparison groups."""
        try:
            async with asyncio.timeout(COMPARISON_SECONDS) as total:
                try:
                    async with asyncio.timeout(MODEL_SECONDS) as deadline:
                        completion = await self.inference.complete(
                            profile="core",
                            messages=messages,
                            preset="fast",
                            temperature=0,
                            max_tokens=768,
                        )
                    if deadline.expired():
                        raise TimeoutError()
                    cancelled()
                except TimeoutError:
                    raise SourceComparisonError("source_model_timeout") from None
                except asyncio.CancelledError:
                    raise
                except SourceComparisonError:
                    raise
                except Exception:
                    raise SourceComparisonError("source_model_failed") from None
                groups = resolve_comparison(completion, self.expected_model, references)
                current = self.references(owner, selections)
                if current != references:
                    raise SourceComparisonError("source_proof_invalid")
                if total.expired():
                    raise SourceComparisonError("source_timeout")
        except TimeoutError:
            raise SourceComparisonError("source_timeout") from None
        cancelled()
        return check_payload(
            SourceComparison(owner, goal, references, *groups, datetime.now(UTC)),
            131072,
        )

    async def shutdown(self):
        """Close facade admission and join only its operations without revoking shared evidence keys or stopping shared models/provider services."""
        self.closing = True
        tasks = [task for task in self.operations if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("source_comparison_shutdown_operation_joined")
        logger.info("source_comparison_shutdown_complete")
