"""Synchronize buffered Python source and kernel descriptor positions around native subprocess borrowing without reopening or changing bytes."""

import logging
import os
from typing import BinaryIO

logger = logging.getLogger(__name__)


def rewind_native_input(source: BinaryIO) -> None:
    """Invalidate buffered read-ahead via an end seek before restoring both logical and native FD cursors to the start."""
    source.seek(0, os.SEEK_END)
    source.seek(0, os.SEEK_SET)
    logger.info("native_input_buffer_and_descriptor_rewound")
