"""Telephony, VoIP, SIP, and Twilio Real-Time Voice Gateway Subsystem."""

from __future__ import annotations

from dream.telephony.engine import (
    TelephonyEngine,
    get_telephony_engine,
    reset_global_telephony_engine,
)
from dream.telephony.sip_adapter import SIPAdapter
from dream.telephony.slash import handle_telephony_command
from dream.telephony.tools import (
    get_telephony_tools,
    telephony_export_call_record,
    telephony_get_call_status,
    telephony_hangup_call,
    telephony_initiate_call,
)
from dream.telephony.twilio_gateway import TwilioMediaGateway
from dream.telephony.types import (
    AudioCodec,
    CallDirection,
    CallStatus,
    TelephonyCallRecord,
)

__all__ = [
    "AudioCodec",
    "CallDirection",
    "CallStatus",
    "SIPAdapter",
    "TelephonyCallRecord",
    "TelephonyEngine",
    "TwilioMediaGateway",
    "get_telephony_engine",
    "get_telephony_tools",
    "handle_telephony_command",
    "reset_global_telephony_engine",
    "telephony_export_call_record",
    "telephony_get_call_status",
    "telephony_hangup_call",
    "telephony_initiate_call",
]
