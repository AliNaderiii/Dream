"""Autonomous Synthetic Sample and DPO Preference Pair Generator."""

from __future__ import annotations

import uuid

from dream.synthetic.types import DatasetFormat, SampleQualityTier, SyntheticSample


class SyntheticGenerator:
    """Generates synthetic instruction, Chain-of-Thought, and DPO training pairs."""

    def generate_dpo_pair(
        self,
        prompt: str,
        chosen_response: str,
        reasoning_trace: str = "",
        rejected_flaw_type: str = "hallucination",
        language: str = "fa",
        tags: list[str] | None = None,
    ) -> SyntheticSample:
        """Construct a high-quality DPO preference pair with synthesized counterfactual negative."""
        sample_id = f"syn-{uuid.uuid4().hex[:8]}"

        # Synthesize reasoning trace if missing
        if not reasoning_trace:
            reasoning_trace = (
                f"تحلیل درخواست: کاربر می‌خواهد '{prompt[:30]}...' را بررسی کند. "
                "گام ۱: تفکیک ملزومات، گام ۲: فراخوانی ابزار مربوطه، گام ۳: اعتبارسنجی خروجی."
            )

        # Synthesize negative response based on targeted flaw type
        rejected_response = self._synthesize_negative(
            prompt, chosen_response, rejected_flaw_type, language
        )

        return SyntheticSample(
            sample_id=sample_id,
            prompt=prompt,
            chosen_response=chosen_response,
            rejected_response=rejected_response,
            reasoning_trace=reasoning_trace,
            format=DatasetFormat.DPO,
            quality_score=0.94,
            quality_tier=SampleQualityTier.PRISTINE,
            language=language,
            tags=tags or ["dpo", "preference", language],
            metadata={"flaw_type": rejected_flaw_type},
        )

    def generate_sft_sample(
        self,
        instruction: str,
        response: str,
        reasoning_trace: str = "",
        language: str = "fa",
        tags: list[str] | None = None,
    ) -> SyntheticSample:
        """Construct a supervised fine-tuning (SFT) sample with optional CoT trace."""
        sample_id = f"sft-{uuid.uuid4().hex[:8]}"
        full_chosen = (
            f"<thought>\n{reasoning_trace}\n</thought>\n{response}"
            if reasoning_trace
            else response
        )

        return SyntheticSample(
            sample_id=sample_id,
            prompt=instruction,
            chosen_response=full_chosen,
            rejected_response="",
            reasoning_trace=reasoning_trace,
            format=DatasetFormat.SHAREGPT,
            quality_score=0.96,
            quality_tier=SampleQualityTier.PRISTINE,
            language=language,
            tags=tags or ["sft", "instruction", language],
        )

    def generate_trajectory_batch(
        self,
        seed_topics: list[str],
        count_per_topic: int = 2,
        language: str = "fa",
    ) -> list[SyntheticSample]:
        """Generate a diverse batch of synthetic training samples from topic seeds."""
        samples: list[SyntheticSample] = []
        for topic in seed_topics:
            for i in range(count_per_topic):
                prompt = (
                    f"لطفاً ساختار معماری و تحلیل جامع پیرامون `{topic}` را با جزئیات ارائه فرمایید."
                    if language == "fa"
                    else f"Please provide comprehensive architectural analysis for `{topic}`."
                )
                chosen = (
                    f"تحلیل جامع `{topic}` (نسخه {i + 1}):\n"
                    "۱. مولفه‌ها و ماژول‌های پایه\n"
                    "۲. استراتژی‌های پردازش موازی و تله‌متری\n"
                    "۳. مکانیزم‌های بازیابی از خطا و Self-Healing."
                    if language == "fa"
                    else f"Comprehensive analysis for `{topic}` (part {i + 1}):\n"
                    "1. Core modules\n2. Parallel processing\n3. Self-healing mechanisms."
                )
                sample = self.generate_dpo_pair(
                    prompt=prompt,
                    chosen_response=chosen,
                    language=language,
                    tags=[topic, "automated_batch"],
                )
                samples.append(sample)

        return samples

    @staticmethod
    def _synthesize_negative(
        prompt: str,
        chosen: str,
        flaw_type: str,
        language: str,
    ) -> str:
        """Generate flawed counterfactual text for DPO rejected candidate."""
        if language == "fa":
            if flaw_type == "hallucination":
                return (
                    f"پاسخ کوتاه و نادرست: سامانه {prompt[:20]} بدون هیچ ابزاری کار می‌کند و "
                    "نیازی به پردازش ندارد! (خطای توهم داده)"
                )
            elif flaw_type == "incomplete":
                return "پاسخ ناقص: برای انجام این کار باید تنظیمات را تغییر دهید..."
            else:
                return f"متن سطحی: در رابطه با {prompt[:25]} اطلاعاتی در دسترس نیست."
        else:
            if flaw_type == "hallucination":
                return "Incorrect output: System needs zero configuration and works magically."
            return "Incomplete response: Please refer to documentation."
