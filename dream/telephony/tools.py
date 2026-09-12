"""LLM Agent tools for Telephony, VoIP, and Phone Call management."""

from __future__ import annotations

import logging
from typing import Any

from dream.telephony.engine import get_telephony_engine

logger = logging.getLogger(__name__)


async def telephony_initiate_call(
    to_number: str,
    from_number: str = "+982191000000",
    caller_name: str = "Dream AI Assistant",
) -> dict[str, Any]:
    """Place an automated phone call to a specified number."""
    engine = get_telephony_engine()
    record = engine.initiate_outbound_call(
        to_number=to_number,
        from_number=from_number,
        metadata={"caller_name": caller_name},
    )
    return {
        "success": True,
        "status": "success",
        "message": f"📞 تماس با شماره `{to_number}` با موفقیت برقرار شد.",
        "call": record.to_dict(),
    }


async def telephony_hangup_call(
    call_id: str,
    reason: str = "completed_normally",
) -> dict[str, Any]:
    """Terminate and hang up an active phone call."""
    engine = get_telephony_engine()
    success = engine.hangup_call(call_id, reason=reason)
    if not success:
        return {"success": False, "message": f"تماس `{call_id}` یافت نشد."}
    return {
        "success": True,
        "status": "success",
        "message": f"🛑 تماس `{call_id}` پایان یافت.",
    }


async def telephony_get_call_status(
    call_id: str,
) -> dict[str, Any]:
    """Retrieve the real-time status and metadata of a telephone call."""
    engine = get_telephony_engine()
    record = engine.get_call(call_id)
    if not record:
        return {"success": False, "message": f"تماس `{call_id}` یافت نشد."}
    return {
        "success": True,
        "call": record.to_dict(),
    }


async def telephony_export_call_record(
    call_id: str,
    format: str = "markdown",
) -> dict[str, Any]:
    """Export the transcript and audit log of a phone call."""
    engine = get_telephony_engine()
    report = engine.export_call_record(call_id, format=format)
    return {
        "success": True,
        "format": format,
        "report": report,
    }


def get_telephony_tools() -> list[dict[str, Any]]:
    """Return tool manifests for LLM registration."""
    return [
        {
            "name": "telephony_initiate_call",
            "description": "Place an automated phone call to a specified number",
            "parameters": {
                "type": "object",
                "properties": {
                    "to_number": {"type": "string"},
                    "from_number": {"type": "string", "default": "+982191000000"},
                    "caller_name": {"type": "string", "default": "Dream AI Assistant"},
                },
                "required": ["to_number"],
            },
            "handler": telephony_initiate_call,
        },
        {
            "name": "telephony_hangup_call",
            "description": "Terminate and hang up an active phone call",
            "parameters": {
                "type": "object",
                "properties": {
                    "call_id": {"type": "string"},
                    "reason": {"type": "string", "default": "completed_normally"},
                },
                "required": ["call_id"],
            },
            "handler": telephony_hangup_call,
        },
        {
            "name": "telephony_get_call_status",
            "description": "Retrieve the real-time status and metadata of a phone call",
            "parameters": {
                "type": "object",
                "properties": {
                    "call_id": {"type": "string"},
                },
                "required": ["call_id"],
            },
            "handler": telephony_get_call_status,
        },
        {
            "name": "telephony_export_call_record",
            "description": "Export the transcript and audit log of a phone call",
            "parameters": {
                "type": "object",
                "properties": {
                    "call_id": {"type": "string"},
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "default": "markdown",
                    },
                },
                "required": ["call_id"],
            },
            "handler": telephony_export_call_record,
        },
    ]
