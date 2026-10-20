"""Retain bounded private root pins and native source receipts across CORE delay without extending D34 deadlines."""

import logging
import os

from apps.api.services.workspaces import joined_work
from src.application.services.workspace_policy import WorkspaceAccessError

logger = logging.getLogger(__name__)


class SourceReceipt:
    """Own one duplicated root descriptor and immutable-by-copy source fingerprints for a selected file."""

    def __init__(self, snapshot):
        """Duplicate the authorized root only after final source validation and copy bounded native receipts."""
        self.descriptor = os.dup(snapshot.handle.fd)
        try:
            info = os.fstat(self.descriptor)
            self.root_identity = (info.st_dev, info.st_ino)
            self.receipts = {
                path: dict(value) for path, value in snapshot.receipts.items()
            }
        except BaseException:
            os.close(self.descriptor)
            self.descriptor = None
            raise
        logger.info("workspace_explanation_receipt_pinned")

    def compare(self, snapshot):
        """Reject fresh roots or source metadata/hash that differ from the still-pinned original evidence."""
        if self.descriptor is None:
            raise WorkspaceAccessError("explanation_unavailable", 503)
        info = os.fstat(snapshot.handle.fd)
        if (info.st_dev, info.st_ino) != self.root_identity:
            raise WorkspaceAccessError("workspace_root_changed", 409)
        if snapshot.receipts != self.receipts:
            raise WorkspaceAccessError("workspace_source_changed", 409)
        logger.info("workspace_explanation_receipt_matched")

    def close(self):
        """Release the owned pin exactly once without reading a repository path during cleanup."""
        if self.descriptor is not None:
            descriptor, self.descriptor = self.descriptor, None
            os.close(descriptor)
            logger.info("workspace_explanation_receipt_closed")


class WorkspaceEvidence:
    """Capture only selected D35 read receipts and revalidate them through fresh D34 operations."""

    def __init__(self, workspace, owner, identifier, selections):
        """Bind trusted scope and bounded copied selections without opening any source."""
        self.workspace = workspace
        self.owner = owner
        self.identifier = identifier
        self.selections = tuple(dict(row) for row in selections)
        self.receipts = []
        self.payload = None

    def operation(self, owner, identifier, name, parameters):
        """Delegate only scoped selected reads to actual shared workspace admission and native source guards."""
        if (
            owner != self.owner
            or identifier != self.identifier
            or name != "read"
            or len(self.receipts) >= len(self.selections)
            or parameters != self.selections[len(self.receipts)]
        ):
            raise WorkspaceAccessError("explanation_scope_invalid", 422)
        return self.workspace.operation(owner, identifier, name, parameters)

    async def validate(self, snapshot):
        """Validate actual source before joined receipt ownership transfer and root pin retention."""
        await self.workspace.validate(snapshot)
        receipt = await joined_work(
            snapshot.stop, SourceReceipt, snapshot, close_result=True
        )
        self.receipts.append(receipt)

    async def revalidate(self):
        """Use fresh short-lived admitted reads to compare every pinned source immediately before delivery."""
        if len(self.receipts) != len(self.selections):
            raise WorkspaceAccessError("explanation_sources_incomplete", 503)
        for parameters, receipt in zip(self.selections, self.receipts, strict=True):
            async with self.workspace.operation(
                self.owner, self.identifier, "read", dict(parameters)
            ) as snapshot:
                await joined_work(snapshot.stop, receipt.compare, snapshot)
                await self.workspace.validate(snapshot)
        logger.info(
            "workspace_explanation_sources_revalidated count=%d", len(self.receipts)
        )

    def close(self):
        """Attempt every independent pin cleanup before reporting a native close failure."""
        failure = None
        for receipt in self.receipts:
            try:
                receipt.close()
            except OSError as error:
                failure = error
        logger.info(
            "workspace_explanation_evidence_closed count=%d", len(self.receipts)
        )
        if failure is not None:
            raise failure
