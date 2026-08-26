"""Space v1: bounded work surface, specialized agents, instruction docs, drafts."""

from __future__ import annotations

import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from dream.agentmodes.shell import classify_command
from dream.nl_schedule import ScheduleParseError, nl_to_cron
from dream.reliability import CancelToken, Deadline
from dream.security.injection import scan_text
from dream.security.pathsafety import is_sensitive_path
from dream.space.catalog import clamp_ceiling, get_role, list_roles
from dream.space.errors import SpaceError, SpaceSecurityError
from dream.space.store import SpaceStore, get_store, now, reset_store
from dream.workspace.errors import WorkspaceError, WorkspaceSecurityError
from dream.workspace.service import get_service as workspace_service

_DOC_CAP = 64_000
_NETWORK_ON = frozenset({"1", "true", "yes", "on"})
_SHELL_MARK = re.compile(r"(?:^|\s)!(?P<cmd>\S[^\n]{0,499})")
_WEB = re.compile(r"^https?://", re.IGNORECASE)


def _network_enabled() -> bool:
    return os.environ.get("DREAM_ALLOW_NETWORK", "").strip().lower() in _NETWORK_ON


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _bilingual(en: str, fa: str) -> str:
    return f"{en}\n{fa}"


class SpaceService:
    """Create spaces, attach folders in place, brief roles, store drafts."""

    def __init__(self, store: SpaceStore | None = None) -> None:
        self.store = store or get_store()
        self._lock = threading.RLock()

    def catalog(self) -> dict[str, Any]:
        return {"roles": list_roles(), "count": len(list_roles())}

    def create(
        self,
        name: str,
        *,
        language: str = "en",
        ceiling: str = "guarded",
    ) -> dict[str, Any]:
        title = (name or "").strip()
        if not title or len(title) > 120:
            raise SpaceError(
                _bilingual(
                    "name must be a non-empty string of at most 120 characters",
                    "نام باید رشته‌ای غیرخالی حداکثر ۱۲۰ نویسه باشد",
                )
            )
        if ceiling not in {"safe", "guarded"}:
            raise SpaceSecurityError(
                _bilingual(
                    "space risk ceiling cannot be dangerous",
                    "سقف ریسک فضا نمی‌تواند dangerous باشد",
                )
            )
        lang = "fa" if language == "fa" else "en"
        stamp = now()
        record = {
            "space_id": _new_id("spc"),
            "name": title,
            "language": lang,
            "ceiling": ceiling,
            "archived": False,
            "root_id": None,
            "folder": None,
            "copied": False,
            "imported_in_place": False,
            "instruction": None,
            "created_at": stamp,
            "updated_at": stamp,
        }
        return self.store.put_space(record)

    def list(self) -> dict[str, Any]:
        rows = self.store.list_spaces()
        return {"spaces": rows, "count": len(rows)}

    def get(self, space_id: str) -> dict[str, Any]:
        record = self.store.get_space(space_id)
        record["drafts"] = self.store.list_drafts(space_id)
        record["roles"] = [
            {**role, "effective_ceiling": clamp_ceiling(record["ceiling"], role["risk_ceiling"])}
            for role in list_roles()
        ]
        return record

    def archive(self, space_id: str) -> dict[str, Any]:
        record = self.store.get_space(space_id)
        record["archived"] = True
        record["updated_at"] = now()
        self.store.put_space(record)
        return {"archived": True, "space_id": space_id}

    def attach_folder(self, space_id: str, folder: str) -> dict[str, Any]:
        record = self.store.get_space(space_id)
        raw = (folder or "").strip()
        if not raw:
            raise SpaceError(
                _bilingual("folder must be a non-empty string", "پوشه نباید خالی باشد")
            )
        if ".." in raw.replace("\\", "/").split("/"):
            raise SpaceSecurityError(
                _bilingual(
                    "parent-directory traversal is refused",
                    "پیمایش پوشهٔ والد رد شد",
                )
            )
        try:
            imported = workspace_service().import_folder(raw, name=record["name"])
        except (WorkspaceError, WorkspaceSecurityError) as exc:
            raise SpaceSecurityError(str(exc)) from exc
        root = imported.get("root") or {}
        record["root_id"] = root.get("root_id")
        record["folder"] = root.get("path") or raw
        record["copied"] = False
        record["imported_in_place"] = True
        record["updated_at"] = now()
        self.store.put_space(record)
        return {
            "space": record,
            "root": root,
            "copied": False,
            "imported_in_place": True,
        }

    def set_instruction(
        self,
        space_id: str,
        *,
        path: str | None = None,
        text: str | None = None,
    ) -> dict[str, Any]:
        record = self.store.get_space(space_id)
        body, source = self._load_instruction_source(path, text)
        report = scan_text(body)
        override = [
            finding
            for finding in report.findings
            if finding.kind == "instruction_override"
        ]
        if override:
            from dream.security.injection import guard_untrusted

            guard_untrusted(body, source=f"space-instruction:{source}")
            raise SpaceSecurityError(
                _bilingual(
                    "instruction doc looks like a prompt injection and was quarantined",
                    "سند دستوری شبیه تزریق پرامپت است و قرنطینه شد",
                )
            )
        record["instruction"] = {
            "source": source,
            "text": report.sanitized[:_DOC_CAP],
            "bytes": len(report.sanitized.encode("utf-8")),
            "findings": [finding.kind for finding in report.findings],
            "quarantined": False,
        }
        record["updated_at"] = now()
        self.store.put_space(record)
        return {"space_id": space_id, "instruction": record["instruction"]}

    def _load_instruction_source(
        self, path: str | None, text: str | None
    ) -> tuple[str, str]:
        if text is not None:
            if not isinstance(text, str) or not text.strip():
                raise SpaceError(
                    _bilingual("instruction text must be non-empty", "متن دستور نباید خالی باشد")
                )
            if len(text) > _DOC_CAP:
                raise SpaceError(
                    _bilingual(
                        "instruction doc exceeds 64 KB",
                        "سند دستوری از ۶۴ کیلوبایت بیشتر است",
                    )
                )
            return text, "pasted"
        raw = (path or "").strip()
        if not raw:
            raise SpaceError(
                _bilingual("path or text is required", "مسیر یا متن لازم است")
            )
        if _WEB.match(raw) or urlsplit(raw).scheme in {"http", "https"}:
            if not _network_enabled():
                raise SpaceSecurityError(
                    _bilingual(
                        "web instruction sources are refused while network tools are off",
                        "منبع وب برای دستور تا وقتی ابزار شبکه خاموش است رد می‌شود",
                    )
                )
            raise SpaceSecurityError(
                _bilingual(
                    "remote instruction URLs are not loaded in Space v1",
                    "نشانی اینترنتی دستور در نسخهٔ ۱ فضا بارگذاری نمی‌شود",
                )
            )
        if ".." in raw.replace("\\", "/").split("/"):
            raise SpaceSecurityError(
                _bilingual(
                    "parent-directory traversal is refused",
                    "پیمایش پوشهٔ والد رد شد",
                )
            )
        candidate = Path(raw).expanduser()
        if candidate.is_symlink():
            raise SpaceSecurityError(
                _bilingual(
                    "instruction path must not be a symbolic link",
                    "مسیر دستور نباید پیوند نمادین باشد",
                )
            )
        if not candidate.is_file():
            raise SpaceError(
                _bilingual(
                    "instruction path must be an existing file",
                    "مسیر دستور باید فایل موجود باشد",
                )
            )
        hit = is_sensitive_path(candidate)
        if hit is not None:
            raise SpaceSecurityError(f"{hit.reason_en}\n{hit.reason_fa}")
        if candidate.stat().st_size > _DOC_CAP:
            raise SpaceError(
                _bilingual("instruction doc exceeds 64 KB", "سند دستوری از ۶۴ کیلوبایت بیشتر است")
            )
        return candidate.read_text(encoding="utf-8"), str(candidate.resolve())

    def ask(
        self,
        space_id: str,
        role_id: str,
        question: str,
        *,
        timeout: float = 8.0,
    ) -> dict[str, Any]:
        record = self.store.get_space(space_id)
        try:
            role = get_role(role_id)
        except KeyError as exc:
            raise SpaceError(
                _bilingual(f"unknown role {role_id!r}", f"نقش ناشناخته {role_id!r}")
            ) from exc
        prompt = (question or "").strip()
        if not prompt or len(prompt) > 4_000:
            raise SpaceError(
                _bilingual(
                    "question must be a non-empty string of at most 4000 characters",
                    "پرسش باید رشته‌ای غیرخالی حداکثر ۴۰۰۰ نویسه باشد",
                )
            )
        instruction = (record.get("instruction") or {}).get("text") or ""
        if not instruction:
            raise SpaceError(
                _bilingual(
                    "this space has no instruction doc yet",
                    "این فضا هنوز سند دستوری ندارد",
                )
            )
        ceiling = clamp_ceiling(record["ceiling"], role["risk_ceiling"])
        token = CancelToken(name="space.ask")
        deadline = Deadline.after(
            min(max(float(timeout), 0.2), 15.0), owner="space", step="ask"
        )
        deadline.throw_if_exceeded()
        if token.is_cancelled():
            raise SpaceError(_bilingual("ask was cancelled", "پرسش لغو شد"))
        excerpt = instruction.strip().splitlines()
        excerpt = [line for line in excerpt if line.strip()][:8]
        body = "\n".join(excerpt)[:1_200]
        if record.get("language") == "fa":
            answer = (
                f"{role['name_fa']} — {role['job_fa']}\n"
                f"سقف ریسک مؤثر: {ceiling}. این پاسخ محلی است و به مدل میزبان فرستاده نشد.\n"
                f"پرسش: {prompt}\n"
                f"از سند دستور:\n{body}"
            )
        else:
            answer = (
                f"{role['name_en']} — {role['job_en']}\n"
                f"Effective risk ceiling: {ceiling}. "
                "This is a local briefing; no hosted model was called.\n"
                f"Question: {prompt}\n"
                f"From the instruction doc:\n{body}"
            )
        return {
            "space_id": space_id,
            "role": {**role, "effective_ceiling": ceiling},
            "question": prompt,
            "answer": answer,
            "hosted": False,
            "tools": list(role["tools"]),
        }

    def propose_draft(self, space_id: str, rule: str) -> dict[str, Any]:
        record = self.store.get_space(space_id)
        text = (rule or "").strip()
        if not text or len(text) > 2_000:
            raise SpaceError(
                _bilingual(
                    "rule must be a non-empty string of at most 2000 characters",
                    "قاعده باید رشته‌ای غیرخالی حداکثر ۲۰۰۰ نویسه باشد",
                )
            )
        shell_hits = [match.group("cmd").strip() for match in _SHELL_MARK.finditer(text)]
        dangerous = False
        classified: list[dict[str, str]] = []
        for command in shell_hits:
            try:
                risk = classify_command(command)
            except Exception:
                risk = "dangerous"
            classified.append({"command": command, "risk": risk})
            if risk == "dangerous":
                dangerous = True
        cron = ""
        parse_error = ""
        try:
            cron = nl_to_cron(text)
        except ScheduleParseError as exc:
            parse_error = str(exc)
        stamp = now()
        draft = {
            "draft_id": _new_id("dft"),
            "space_id": record["space_id"],
            "rule": text,
            "status": "APPROVAL_PENDING",
            "cron": cron,
            "parse_error": parse_error,
            "shell": classified,
            "dangerous": dangerous,
            "fired": False,
            "spawned": False,
            "created_at": stamp,
            "updated_at": stamp,
        }
        return self.store.put_draft(draft)

    def list_drafts(self, space_id: str) -> dict[str, Any]:
        self.store.get_space(space_id)
        rows = self.store.list_drafts(space_id)
        return {"drafts": rows, "count": len(rows)}

    def approve_draft(self, draft_id: str) -> dict[str, Any]:
        draft = self.store.get_draft(draft_id)
        if draft["status"] == "DENIED":
            raise SpaceError(
                _bilingual("a denied draft stays idle", "پیشنویس ردشده بیکار می‌ماند")
            )
        draft["status"] = "APPROVED"
        draft["updated_at"] = now()
        draft["fired"] = False
        draft["spawned"] = False
        return self.store.put_draft(draft)

    def deny_draft(self, draft_id: str) -> dict[str, Any]:
        draft = self.store.get_draft(draft_id)
        draft["status"] = "DENIED"
        draft["updated_at"] = now()
        draft["fired"] = False
        draft["spawned"] = False
        return self.store.put_draft(draft)

    def run_draft(self, draft_id: str, *, approved: bool = False) -> dict[str, Any]:
        """Attempt to act on a draft. Dangerous shell never reaches subprocess."""
        draft = self.store.get_draft(draft_id)
        if draft["status"] != "APPROVED":
            raise SpaceError(
                _bilingual(
                    "draft is not approved; nothing was scheduled or executed",
                    "پیشنویس تأیید نشده؛ چیزی زمان‌بندی یا اجرا نشد",
                )
            )
        if not approved:
            raise SpaceError(
                _bilingual(
                    "missing approver — refuse",
                    "تأییدکننده نیست — رد شد",
                )
            )
        shells = draft.get("shell") or []
        if draft.get("dangerous") or any(row.get("risk") == "dangerous" for row in shells):
            return {
                "draft_id": draft_id,
                "executed": False,
                "spawned": False,
                "fired": False,
                "status": draft["status"],
                "reason": _bilingual(
                    "dangerous shell commands are refused",
                    "فرمان پوستهٔ خطرناک رد شد",
                ),
            }
        # Honest v1: approved non-dangerous drafts are recorded, not fired live.
        return {
            "draft_id": draft_id,
            "executed": False,
            "spawned": False,
            "fired": False,
            "status": draft["status"],
            "cron": draft.get("cron") or "",
            "reason": _bilingual(
                "approved draft stored; live scheduler wiring is a documented residual",
                "پیشنویس تأیید شد؛ اتصال به زمان‌بند زنده باقی‌ماندهٔ مستند است",
            ),
        }


_service: SpaceService | None = None
_lock = threading.Lock()


def get_service() -> SpaceService:
    global _service
    with _lock:
        if _service is None:
            _service = SpaceService()
        return _service


def reset_service(service: SpaceService | None = None) -> SpaceService | None:
    global _service
    with _lock:
        _service = service
        return _service


__all__ = ["SpaceService", "get_service", "reset_service", "reset_store"]
