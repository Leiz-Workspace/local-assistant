"""Start Aevra's native GTK/WebKit runtime through uv and OS Python without external browser processes."""

import json
import logging
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.desktop.runtime import dependencies, run, validate_bootstrap

LOGGER = logging.getLogger(__name__)


def main(argv=None):
    """Probe native dependencies or consume one bounded bootstrap from stdin without putting secrets in argv or logs."""
    args = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout
    )
    try:
        dependencies()
        if args == ["--check"]:
            print(
                json.dumps(
                    dict(
                        available=True,
                        product="Aevra",
                        renderer="webkitgtk-4.1",
                        external_browser=False,
                    )
                )
            )
            return 0
        if args:
            raise ValueError("unsupported_desktop_arguments")
        raw = sys.stdin.buffer.readline(2049)
        if len(raw) > 2048 or not raw.endswith(b"\n"):
            raise ValueError("invalid_desktop_bootstrap")
        value = validate_bootstrap(json.loads(raw))
        return run(value)
    except (ImportError, ValueError, OSError, KeyError, TypeError):
        LOGGER.error("aevra_desktop_runtime_unavailable")
        return 6
    except KeyboardInterrupt:
        LOGGER.info("aevra_desktop_interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
