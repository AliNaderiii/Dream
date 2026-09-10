"""Dialectical User Modeling: extracts evolving preferences, tone, and technical profile."""

from __future__ import annotations

import re
import time
from typing import Any

from dream.memory.models import UserPersona
from dream.memory.normalization import normalize_fa

_FA_PATTERN = re.compile(r"[\u0600-\u06FF]")
_CODE_KEYWORDS = re.compile(
    r"\b(python|def |class |async |await |typescript|react|api|docker|sql|git|test|pr|code)\b",
    re.IGNORECASE,
)
_PREFERENCE_TRIGGERS_FA = (
    "من ترجیح می‌دهم",
    "من دوست دارم",
    "لطفاً همیشه",
    "همیشه به فارسی",
    "خلاصه بگو",
    "کد بنویس",
    "توضیح بده",
)
_PREFERENCE_TRIGGERS_EN = (
    "i prefer",
    "always use",
    "keep it concise",
    "write code",
    "in persian",
    "in english",
)


class DialecticalUserTracker:
    """Extracts and maintains dynamic user personas across conversational interactions."""

    def __init__(self, user_id: str = "local") -> None:
        self.user_id = user_id
        self.persona = UserPersona(user_id=user_id)

    def analyze_turn(self, user_message: str, assistant_reply: str = "") -> UserPersona:
        """Analyze a conversation turn and update the dialectical user model."""
        if not user_message:
            return self.persona

        norm_msg = normalize_fa(user_message)
        fa_chars = len(_FA_PATTERN.findall(user_message))
        total_chars = max(1, len(user_message.strip()))

        # 1. Detect Language Preference
        if fa_chars / total_chars > 0.4:
            self.persona.language_preference = "fa"
        elif fa_chars == 0 and len(user_message) > 20:
            self.persona.language_preference = "en"
        else:
            self.persona.language_preference = "bilingual (fa/en)"

        # 2. Detect Interaction Style
        if len(user_message.splitlines()) > 5 or _CODE_KEYWORDS.search(user_message):
            self.persona.interaction_style = "code_first & analytical"
        elif "خلاصه" in norm_msg or "concise" in user_message.lower():
            self.persona.interaction_style = "concise"

        # 3. Extract Explicit Invariant Facts
        for trigger in _PREFERENCE_TRIGGERS_FA:
            if trigger in norm_msg:
                fact = user_message.strip()
                if fact not in self.persona.known_facts and len(self.persona.known_facts) < 20:
                    self.persona.known_facts.append(fact)

        for trigger in _PREFERENCE_TRIGGERS_EN:
            if trigger in user_message.lower():
                fact = user_message.strip()
                if fact not in self.persona.known_facts and len(self.persona.known_facts) < 20:
                    self.persona.known_facts.append(fact)

        self.persona.last_updated = time.time()
        return self.persona

    def sync_to_context_manager(self, context_manager: Any) -> None:
        """Render persona and update the USER.md context file."""
        user_md_content = self.persona.render_markdown()
        context_manager.update("user", user_md_content, enforce_capacity=False)
