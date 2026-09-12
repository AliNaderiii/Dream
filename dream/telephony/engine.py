"""Master Telephony Subsystem Engine for Inbound/Outbound Phone Calls."""

from __future__ import annotations

import time
import uuid
from typing import Any

from dream.telephony.sip_adapter import SIPAdapter
from dream.telephony.twilio_gateway import TwilioMediaGateway
from dream.telephony.types import CallDirection, CallStatus, TelephonyCallRecord


class TelephonyEngine:
    """Master engine orchestrating VoIP, SIP, and Twilio phone calls."""

    def __init__(self) -> None:
        self._calls: dict[str, TelephonyCallRecord] = {}
        self._twilio_gateways: dict[str, TwilioMediaGateway] = {}
        self._sip_adapter = SIPAdapter()

    def initiate_outbound_call(
        self,
        to_number: str,
        from_number: str = "+982191000000",
        provider: str = "twilio",
        metadata: dict[str, Any] | None = None,
    ) -> TelephonyCallRecord:
        """Place an outbound automated phone call."""
        call_id = f"call_{uuid.uuid4().hex[:12]}"
        record = TelephonyCallRecord(
            call_id=call_id,
            from_number=from_number,
            to_number=to_number,
            direction=CallDirection.OUTBOUND,
            status=CallStatus.IN_PROGRESS,
            provider=provider,
            connected_at=time.time(),
            metadata=metadata or {},
        )
        self._calls[call_id] = record
        self._twilio_gateways[call_id] = TwilioMediaGateway(record)
        return record

    def handle_inbound_webhook(
        self,
        from_number: str,
        to_number: str,
        provider: str = "twilio",
    ) -> tuple[TelephonyCallRecord, str]:
        """Handle incoming phone call webhook and return TwiML Stream XML."""
        call_id = f"call_in_{uuid.uuid4().hex[:12]}"
        record = TelephonyCallRecord(
            call_id=call_id,
            from_number=from_number,
            to_number=to_number,
            direction=CallDirection.INBOUND,
            status=CallStatus.IN_PROGRESS,
            provider=provider,
            connected_at=time.time(),
        )
        self._calls[call_id] = record
        self._twilio_gateways[call_id] = TwilioMediaGateway(record)

        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<Response>\n"
            "  <Connect>\n"
            '    <Stream url="wss://dream.agent/v1/telephony/stream">\n'
            f'      <Parameter name="call_id" value="{call_id}" />\n'
            "    </Stream>\n"
            "  </Connect>\n"
            "</Response>"
        )
        return record, twiml

    def get_call(self, call_id: str) -> TelephonyCallRecord | None:
        """Retrieve phone call record by ID."""
        return self._calls.get(call_id)

    def list_calls(self) -> list[dict[str, Any]]:
        """List all active and completed phone calls."""
        return [c.to_dict() for c in self._calls.values()]

    def hangup_call(self, call_id: str, reason: str = "normal_hangup") -> bool:
        """Terminate and hang up an active call."""
        if call_id in self._calls:
            record = self._calls[call_id]
            record.status = CallStatus.COMPLETED
            record.ended_at = time.time()
            if record.connected_at:
                record.duration_sec = record.ended_at - record.connected_at
                record.cost_estimated_usd = record.duration_sec * 0.0003
            record.metadata["hangup_reason"] = reason
            return True
        return False

    def export_call_record(self, call_id: str, format: str = "markdown") -> str:
        """Export call summary transcript and metadata."""
        record = self.get_call(call_id)
        if not record:
            return f"❌ تماس `{call_id}` یافت نشد."

        if format == "json":
            import json
            return json.dumps(record.to_dict(), indent=2, ensure_ascii=False)

        lines = [
            f"# 📞 گزارش تماس صوتی: {record.call_id}",
            f"- **شماره مبدا:** `{record.from_number}`",
            f"- **شماره مقصد:** `{record.to_number}`",
            f"- **جهت تماس:** {record.direction.value}",
            f"- **وضعیت:** {record.status.value}",
            f"- **مدت زمان:** {record.duration_sec:.1f} ثانیه",
            f"- **هزینه تقریبی:** ${record.cost_estimated_usd:.4f}",
            f"- **کلیدهای فشرده‌شده (DTMF):** `{record.dtmf_digits or 'None'}`",
        ]
        return "\n".join(lines)


_GLOBAL_TELEPHONY_ENGINE: TelephonyEngine | None = None


def get_telephony_engine() -> TelephonyEngine:
    """Retrieve global singleton TelephonyEngine."""
    global _GLOBAL_TELEPHONY_ENGINE
    if _GLOBAL_TELEPHONY_ENGINE is None:
        _GLOBAL_TELEPHONY_ENGINE = TelephonyEngine()
    return _GLOBAL_TELEPHONY_ENGINE


def reset_global_telephony_engine() -> None:
    """Reset singleton instance (used in test suites)."""
    global _GLOBAL_TELEPHONY_ENGINE
    _GLOBAL_TELEPHONY_ENGINE = None
