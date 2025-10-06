"""Utilities for the MCP server."""

import logging

import anyio


class SuppressClosedResourceErrors(logging.Filter):
    """Suppress noisy disconnect traces from FastMCP until upstream fix.

    FastMCP currently emits stack traces when clients close the stream.
    This filter suppresses those specific errors.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info:
            _, exc, _ = record.exc_info
            if isinstance(exc, anyio.ClosedResourceError):
                return False
        return True
