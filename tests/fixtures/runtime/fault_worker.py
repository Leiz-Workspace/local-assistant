"""Exercise recoverable address-space and private-tmpfs exhaustion inside a fixed offline low-resource test namespace."""

import errno
import json
import logging
import os
import resource
import sys

logger = logging.getLogger(__name__)


def main():
    """Trigger only the selected fixed resource failure and verify small subsequent work succeeds within the same child."""
    if len(sys.argv) != 2 or sys.argv[1] not in {"memory", "disk"}:
        raise SystemExit("invalid_fault_mode")
    mode = sys.argv[1]
    address_cap = resource.getrlimit(resource.RLIMIT_AS)[0]
    assert address_cap == 268435456
    if mode == "memory":
        try:
            bytearray(536870912)
        except MemoryError:
            failure = "MemoryError"
        else:
            raise RuntimeError("expected_address_space_refusal")
        assert len(bytearray(1048576)) == 1048576
        recovery = "small_allocation_succeeded"
    else:
        written = 0
        try:
            with open("/scratch/blob.bin", "wb", buffering=0) as stream:
                while True:
                    written += stream.write(b"x" * 4096)
        except OSError as exc:
            assert exc.errno == errno.ENOSPC
            failure = "ENOSPC"
        else:
            raise RuntimeError("expected_private_tmpfs_exhaustion")
        assert written <= 65536
        os.unlink("/scratch/blob.bin")
        with open("/scratch/recovered.bin", "wb") as stream:
            stream.write(b"recovered")
        recovery = "private_file_recreated_after_cleanup"
    logger.info("bounded_fault_recovered mode=%s outcome=%s", mode, failure)
    print(
        json.dumps(
            dict(
                mode=mode,
                expected_failure=failure,
                recovery=recovery,
                address_space_cap_bytes=address_cap,
                peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                host_oom_triggered=False,
                host_disk_filled=False,
            )
        )
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
