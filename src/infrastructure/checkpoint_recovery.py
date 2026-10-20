"""Observe current scoped source hashes against durable checkpoints without restoring bytes, inferring causality or recovering approvals."""

import hashlib
import logging
import os
import stat
import threading
from time import monotonic
from uuid import UUID

from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.checkpoints import check_work
from src.infrastructure.workspace_reader import fingerprint

logger = logging.getLogger(__name__)


def observe_checkpoint(catalog, owner, workspace, snapshot, stop=None):
    """Return a fresh bounded hash observation only; matching historical bytes are evidence, never a replayable write grant."""
    stop = stop if stop is not None else threading.Event()
    deadline = monotonic() + 5
    metadata = snapshot["metadata"]
    if (
        type(owner) is not UUID
        or type(workspace) is not UUID
        or metadata["owner_id"] != str(owner)
        or metadata["workspace_id"] != str(workspace)
    ):
        raise WorkspaceAccessError("checkpoint_not_found", 404)
    check_work(stop, deadline)
    result = dict(
        checkpoint_id=snapshot["checkpoint_id"],
        journal_state=snapshot["journal"]["state"],
        observation="source_unavailable",
        current_sha256=None,
        source_modified=False,
        recovered_approval=False,
        action_taken=False,
        causality_inferred=False,
    )
    try:
        with catalog.open(owner, workspace) as handle:
            if [handle.identity.st_dev, handle.identity.st_ino] != metadata["root"]:
                result["observation"] = "root_changed"
                return result
            with handle.entry(metadata["path"]) as descriptor:
                before = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_nlink != 1
                    or before.st_uid != os.getuid()
                    or before.st_size > 8192
                ):
                    return result
                raw = bytearray()
                while len(raw) <= 8192:
                    check_work(stop, deadline)
                    chunk = os.read(descriptor, min(4096, 8193 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                after = os.fstat(descriptor)
                if (
                    len(raw) > 8192
                    or len(raw) != before.st_size
                    or fingerprint(before) != fingerprint(after)
                ):
                    return result
            handle.validate_root()
            check_work(stop, deadline)
            sha = hashlib.sha256(raw).hexdigest()
            result["current_sha256"] = sha
            result["observation"] = (
                "observed_original"
                if sha == metadata["base_sha256"]
                else "observed_replacement"
                if sha == metadata["new_sha256"]
                else "observed_other"
            )
    except WorkspaceAccessError as error:
        if error.code in {"checkpoint_cancelled", "checkpoint_deadline"}:
            raise
    except OSError:
        pass
    finally:
        logger.info(
            "checkpoint_source_observed checkpoint_id=%s observation=%s",
            snapshot["checkpoint_id"],
            result["observation"],
        )
    return result
