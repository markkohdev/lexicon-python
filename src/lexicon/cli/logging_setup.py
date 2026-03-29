"""Configure logging when the CLI runs with ``--verbose``."""

from __future__ import annotations

import logging
import sys

_LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"

_configured = False


def configure_verbose_logging() -> None:
    """Emit DEBUG (and above) from ``lexicon`` loggers to stderr.

    Safe to call once per process; subsequent calls are no-ops.
    """
    global _configured
    if _configured:
        return
    _configured = True

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    pkg = logging.getLogger("lexicon")
    pkg.setLevel(logging.DEBUG)
    pkg.addHandler(handler)
