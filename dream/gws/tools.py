"""Chat tools for Google Workspace. Auto-imported by dream.extensions."""

from __future__ import annotations

from dream.gws.errors import GwsError, GwsSecurityError
from dream.gws.service import get_service
from dream.tools import tool


def _run(call):  # type: ignore[no-untyped-def]
    try:
        return call()
    except (GwsSecurityError, GwsError) as exc:
        return str(exc)


@tool(risk="guarded")
def gmail_list(max_results: int = 5) -> str:
    """List recent Gmail message ids. Read-only. Requires owner Google OAuth.

    :param max_results: How many ids to list, 1 to 10.
    """
    return _run(lambda: get_service().gmail_list(max_results))


@tool(risk="guarded")
def calendar_list(max_results: int = 5) -> str:
    """List upcoming Google Calendar events. Read-only. Requires owner Google OAuth.

    :param max_results: How many events to list, 1 to 10.
    """
    return _run(lambda: get_service().calendar_list(max_results))


@tool(risk="guarded")
def drive_list(max_results: int = 5) -> str:
    """List recent Google Drive file names. Read-only. Requires owner Google OAuth.

    :param max_results: How many files to list, 1 to 10.
    """
    return _run(lambda: get_service().drive_list(max_results))


@tool(risk="dangerous")
def gmail_send(to: str, subject: str, body: str) -> str:
    """Refuse to send Gmail. Sending stays human in this cut.

    :param to: Intended recipient.
    :param subject: Intended subject.
    :param body: Intended body.
    """
    del to, subject, body
    return _run(lambda: get_service().refuse_write("gmail send"))
