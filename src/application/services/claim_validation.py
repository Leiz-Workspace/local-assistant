"""Own one bounded original CORE claim assessment after complete signed-source admission and revalidation, without semantic truth promotion."""

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from src.application.ports.claim_validation import ClaimEvidence, ClaimValidation
from src.application.ports.source_reconciliation import SourceSpan
from src.application.services.claim_validation_policy import (
    ClaimValidationError,
    check_result,
    claim_messages,
    prepare_claims,
    resolve_assessments,
)
from src.application.services.research import cancelled
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.application.services.web_search_policy import WebSearchError, WebSearchQuota

logger = logging.getLogger(__name__)
MODEL_SECONDS = 15
TOTAL_SECONDS = 20


class ClaimValidationService:
    """Keep claim/source integrity and model assessment separate under one nonqueued owner-bound operation and finite quota."""

    def __init__(self, *, evidence, inference, expected_model, quota=None):
        """Bind inert trusted dependencies without fetching sources, accessing private context, starting models or modifying shared services."""
        if type(expected_model) is not str or not 1 <= len(expected_model) <= 128:
            raise ClaimValidationError("claim_invalid")
        self.evidence, self.inference, self.expected_model = (
            evidence,
            inference,
            expected_model,
        )
        self.quota = quota if quota is not None else WebSearchQuota()
        self.admission = asyncio.Lock()
        self.operations = set()
        self.closing = False
        logger.info("claim_validation_service_initialized")

    def references(self, owner, selections):
        """Authenticate the entire explicit signed-span list and refuse duplicate exact source references before model work."""
        if (
            type(selections) is not tuple
            or not 1 <= len(selections) <= 4
            or any(type(item) is not SourceSpan for item in selections)
        ):
            raise ClaimValidationError("claim_proof_invalid")
        try:
            result = tuple(
                self.evidence.cite(owner, row.snapshot, row.start, row.end)
                for row in selections
            )
            if len({(ref.snapshot_id, ref.start, ref.end) for ref in result}) != len(
                result
            ):
                raise ValueError()
            return result
        except Exception:
            raise ClaimValidationError("claim_proof_invalid") from None

    def charge(self, owner):
        """Charge admitted model attempts once without refunds after errors, cancellation or failed task dispatch."""
        try:
            self.quota.charge(owner)
        except WebSearchError as error:
            raise ClaimValidationError(
                "claim_rate_limited"
                if error.code == "web_search_rate_limited"
                else "claim_unavailable"
            ) from None

    async def validate(self, owner, goal, claims, selections):
        """Validate complete input/proofs before admitting a single owned fixed-model assessment with no private/source acquisition context."""
        if type(owner) is not UUID:
            raise ClaimValidationError("claim_invalid")
        if self.evidence is None or self.inference is None:
            raise ClaimValidationError("claim_unavailable")
        if self.closing or getattr(self.evidence, "closing", False):
            self.closing = True
            raise ClaimValidationError("claim_closed")
        goal, claims = prepare_claims(goal, claims)
        references = self.references(owner, selections)
        messages = claim_messages(goal, claims, references)
        if self.admission.locked():
            raise ClaimValidationError("claim_busy")
        await self.admission.acquire()
        caller, task = asyncio.current_task(), None
        try:
            self.charge(owner)
            self.operations.add(caller)
            task = spawn_owned(
                self.run(owner, goal, claims, selections, references, messages)
            )
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                task.cancel()
                try:
                    await finish_owned(task)
                except BaseException:
                    logger.info("claim_validation_cancelled_operation_joined")
                raise
        except asyncio.CancelledError:
            raise
        except ClaimValidationError:
            raise
        except Exception:
            raise ClaimValidationError("claim_internal") from None
        finally:
            if getattr(self.evidence, "closing", False):
                self.closing = True
                logger.warning("claim_validation_dependency_closed_admission_poisoned")
            self.operations.discard(caller)
            self.admission.release()
            logger.info("claim_validation_operation_closed")

    async def run(self, owner, goal, claims, selections, references, messages):
        """Make one fixed CORE call and publish only complete schema/proof-checked results with explicit unverified support labels."""
        try:
            async with asyncio.timeout(TOTAL_SECONDS) as total:
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
                    raise ClaimValidationError("claim_model_timeout") from None
                except asyncio.CancelledError:
                    raise
                except Exception:
                    raise ClaimValidationError("claim_model_failed") from None
                assessed = resolve_assessments(
                    completion, self.expected_model, claims, references
                )
                if getattr(self.evidence, "closing", False):
                    raise ClaimValidationError("claim_cleanup_uncertain")
                if self.references(owner, selections) != references:
                    raise ClaimValidationError("claim_proof_invalid")
                if total.expired():
                    raise ClaimValidationError("claim_timeout")
        except TimeoutError:
            raise ClaimValidationError("claim_timeout") from None
        cancelled()
        return check_result(
            ClaimValidation(
                owner,
                goal,
                tuple(
                    ClaimEvidence(f"E{index}", ref)
                    for index, ref in enumerate(references, 1)
                ),
                assessed,
                datetime.now(UTC),
            )
        )

    async def shutdown(self):
        """Close admission and join only owned claim work without closing shared evidence keys/cache or original models/services."""
        self.closing = True
        callers = [
            task for task in self.operations if task is not asyncio.current_task()
        ]
        for task in callers:
            task.cancel()
        for task in callers:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("claim_validation_shutdown_operation_joined")
        logger.info("claim_validation_shutdown_complete")
