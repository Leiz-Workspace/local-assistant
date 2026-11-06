"""Enable application audit and structured pool logs under the default Uvicorn launcher."""

import logging


def configure_application_logging() -> None:
    """Expose application INFO events while honoring existing deployment handlers."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        root.addHandler(handler)
    for namespace in ("apps.api", "src"):
        logging.getLogger(namespace).setLevel(logging.INFO)
    logging.getLogger(__name__).info("application_audit_logging_configured")
