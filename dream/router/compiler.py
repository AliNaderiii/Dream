"""Dynamic Prompt Compiler: Token budgeting, AST section assembly, and rendering."""

from __future__ import annotations

import time
from typing import Any

from dream.router.types import CompiledPrompt, ModelTier, PromptSection


class PromptCompiler:
    """Compiles structured prompt sections into token-budgeted system and user prompts."""

    # Default token budgets per model tier
    TIER_BUDGETS: dict[ModelTier, int] = {
        ModelTier.FAST_EDGE: 2048,
        ModelTier.STANDARD_CHAT: 8192,
        ModelTier.REASONING_HEAVY: 16384,
    }

    def __init__(self) -> None:
        self._templates: dict[str, list[PromptSection]] = {}
        self._init_builtin_templates()

    def _init_builtin_templates(self) -> None:
        """Initialize core Dream prompt templates."""
        self._templates["default_agent"] = [
            PromptSection(
                section_id="soul_core",
                title="Soul Core Identity",
                content="You are Dream, an ultra-intelligent, highly capable AI assistant.",
                priority=1000,
                is_mandatory=True,
            ),
            PromptSection(
                section_id="persian_excellence",
                title="Language & Cultural Nuance",
                content=(
                    "Respond fluently, naturally, and accurately in Persian "
                    "with proper Persian grammar and typography."
                ),
                priority=900,
                is_mandatory=True,
            ),
            PromptSection(
                section_id="context_calendar",
                title="Temporal Grounding",
                content=(
                    "Current Jalali Date: {jalali_date}. Always ground "
                    "chronological assertions."
                ),
                priority=700,
                is_mandatory=False,
            ),
            PromptSection(
                section_id="tool_guidelines",
                title="Tool Calling Protocol",
                content=(
                    "Use available tools judiciously. Validate arguments "
                    "before dispatching calls."
                ),
                priority=500,
                is_mandatory=False,
            ),
            PromptSection(
                section_id="extended_dialectic",
                title="Dialectic Memory Profile",
                content="User Preferences: {user_profile}. Dialectic Beliefs: {dialectic_beliefs}.",
                priority=300,
                is_mandatory=False,
            ),
        ]

    def register_template(
        self,
        name: str,
        sections: list[PromptSection],
    ) -> None:
        """Register a new modular prompt template."""
        self._templates[name] = sections

    def compile(
        self,
        template_name: str,
        target_tier: ModelTier,
        user_query: str,
        variables: dict[str, Any] | None = None,
        max_budget_tokens: int | None = None,
    ) -> CompiledPrompt:
        """Assemble and prune prompt sections according to token budget."""
        start_time = time.time()
        vars_dict = variables or {}
        budget = max_budget_tokens or self.TIER_BUDGETS.get(target_tier, 4096)

        sections = self._templates.get(template_name, self._templates["default_agent"])

        # Estimate user query tokens
        user_tokens = max(1, len(user_query) // 4)
        available_sys_tokens = max(1, budget - user_tokens)

        # Sort sections: mandatory first, then highest priority
        sorted_sections = sorted(
            sections,
            key=lambda s: (s.is_mandatory, s.priority),
            reverse=True,
        )

        included_ids: list[str] = []
        dropped_ids: list[str] = []
        rendered_blocks: list[str] = []
        current_tokens = 0

        for sec in sorted_sections:
            # Substitute variables
            raw_content = sec.content
            for k, v in vars_dict.items():
                raw_content = raw_content.replace(f"{{{k}}}", str(v))

            # Clean unresolved place-holders if optional
            if not sec.is_mandatory:
                import re

                raw_content = re.sub(r"\{[a-zA-Z0-9_]+\}", "", raw_content).strip()

            sec_tokens = max(1, len(raw_content) // 4)

            if sec.is_mandatory or (current_tokens + sec_tokens <= available_sys_tokens):
                rendered_blocks.append(raw_content)
                current_tokens += sec_tokens
                included_ids.append(sec.section_id)
            else:
                dropped_ids.append(sec.section_id)

        system_prompt = "\n\n".join(rendered_blocks)
        total_tokens = current_tokens + user_tokens
        latency_ms = (time.time() - start_time) * 1000

        return CompiledPrompt(
            template_name=template_name,
            target_tier=target_tier,
            system_prompt=system_prompt,
            user_prompt=user_query,
            total_tokens=total_tokens,
            max_budget_tokens=budget,
            included_sections=included_ids,
            dropped_sections=dropped_ids,
            compilation_time_ms=latency_ms,
        )
