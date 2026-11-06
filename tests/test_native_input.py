"""Verify complete-byte/native-offset synchronization for real buffered/raw sources and safe borrowed-stream failure behavior."""

import io
import logging
import os

import pytest

from src.infrastructure.native_input import rewind_native_input


@pytest.mark.parametrize("kind", ["reader", "random", "raw"])
@pytest.mark.parametrize("state", ["prefix", "logical_rewind", "eof"])
def test_real_buffered_and_kernel_offsets_realign_without_losing_bytes_or_closing_caller(
    kind, state, tmp_path
):
    """Keep exact original bytes available to both a native FD reader and Python after partial/buffered/EOF reads."""
    raw = b"Original complete tiny buffered native source.\n"
    path = tmp_path / "source"
    path.write_bytes(raw)
    with path.open(
        "r+b" if kind == "random" else "rb", buffering=0 if kind == "raw" else -1
    ) as source:
        source.read(1)
        if state == "logical_rewind":
            source.seek(0)
        elif state == "eof":
            source.read()
        rewind_native_input(source)
        assert (
            source.tell() == os.lseek(source.fileno(), 0, os.SEEK_CUR) == 0
            and not source.closed
        )
        assert os.read(source.fileno(), len(raw) + 1) == raw
        rewind_native_input(source)
        assert source.read() == raw
        rewind_native_input(source)
        assert source.tell() == os.lseek(source.fileno(), 0, os.SEEK_CUR) == 0
    assert path.read_bytes() == raw
    logging.getLogger(__name__).info(
        "native_input_complete_bytes_and_offsets_verified kind=%s state=%s", kind, state
    )


def test_bytesio_compatibility_preserves_existing_controlled_native_adapter_seams():
    """Keep the accepted seekable BinaryIO contract without requiring test-only in-memory streams to invent a file descriptor."""
    source = io.BytesIO(b"complete")
    source.read(1)
    rewind_native_input(source)
    assert source.tell() == 0 and source.read() == b"complete" and not source.closed


def test_closed_source_is_rejected_without_reopening_any_path():
    """Propagate the existing invalid-source failure instead of reopening a closed descriptor by filename."""
    source = io.BytesIO(b"private")
    source.close()
    with pytest.raises(ValueError):
        rewind_native_input(source)


def test_source_seek_failure_propagates_without_inventing_success_or_losing_owner():
    """Keep a nonseekable source rejected rather than treating incomplete bytes as a valid native payload."""

    class Unseekable(io.BytesIO):
        """Expose an authored explicit seek failure without any external descriptors."""

        def seek(self, *arguments):
            """Refuse every seek to challenge fail-closed input synchronization."""
            raise OSError("controlled_source_seek_failed")

    source = Unseekable(b"complete")
    with pytest.raises(OSError, match="controlled_source_seek_failed"):
        rewind_native_input(source)
    assert not source.closed
