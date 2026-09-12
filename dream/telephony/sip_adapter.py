"""SIP Protocol Adapter and VoIP Signaling Handler."""

from __future__ import annotations

import time
import uuid
from typing import Any

from dream.telephony.types import AudioCodec, CallDirection, CallStatus, TelephonyCallRecord


class SIPAdapter:
    """Simulates and orchestrates SIP (Session Initiation Protocol) 2.0 signaling sessions."""

    def __init__(self) -> None:
        self._active_dialogs: dict[str, dict[str, Any]] = {}

    def handle_invite(
        self,
        from_uri: str,
        to_uri: str,
        sdp_payload: str = "",
    ) -> tuple[TelephonyCallRecord, dict[str, str]]:
        """Process incoming SIP INVITE and return call record and 200 OK headers."""
        call_id = f"sip_{uuid.uuid4().hex[:12]}"
        record = TelephonyCallRecord(
            call_id=call_id,
            from_number=from_uri,
            to_number=to_uri,
            direction=CallDirection.INBOUND,
            status=CallStatus.IN_PROGRESS,
            codec=AudioCodec.PCM_16KHZ,
            provider="sip_voip",
            connected_at=time.time(),
        )
        domain = to_uri.split("@")[-1] if "@" in to_uri else "127.0.0.1"
        headers = {
            "Status": "SIP/2.0 200 OK",
            "Call-ID": call_id,
            "Contact": f"<sip:dream-agent@{domain}>",
            "Content-Type": "application/sdp",
        }
        self._active_dialogs[call_id] = {"record": record, "headers": headers}
        return record, headers

    def handle_bye(self, call_id: str) -> bool:
        """Process SIP BYE request to terminate call."""
        if call_id in self._active_dialogs:
            dialog = self._active_dialogs.pop(call_id)
            record: TelephonyCallRecord = dialog["record"]
            record.status = CallStatus.COMPLETED
            record.ended_at = time.time()
            if record.connected_at:
                record.duration_sec = record.ended_at - record.connected_at
            return True
        return False
