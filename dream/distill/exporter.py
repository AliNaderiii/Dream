"""Dataset distillation and formatting engine for model fine-tuning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dream.distill.types import DistillFormat, TrajectoryTrace


def sanitize_trace_text(text: str) -> str:
    """Strip common sensitive tokens and keys from training samples."""
    import re

    sanitized = re.sub(r"(sk-[A-Za-z0-9_\-]{20,})", "[REDACTED_API_KEY]", text)
    sanitized = re.sub(
        r"(bearer\s+[A-Za-z0-9_\-\.]{20,})",
        "Bearer [REDACTED_TOKEN]",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized


class DatasetDistiller:
    """Formats curated trajectories into fine-tuning datasets."""

    @staticmethod
    def to_openai_format(traces: list[TrajectoryTrace]) -> list[dict[str, Any]]:
        """Export into OpenAI Fine-Tuning JSONL schema."""
        dataset = []
        for t in traces:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are Dream, a next-generation bilingual AI assistant "
                        "with tool-calling capabilities."
                    ),
                }
            ]
            for s in t.steps:
                if s.role == "user":
                    messages.append({"role": "user", "content": sanitize_trace_text(s.content)})
                elif s.role == "assistant":
                    content = s.content
                    if s.thought:
                        content = f"<thought>{s.thought}</thought>\n{content}"
                    messages.append(
                        {
                            "role": "assistant",
                            "content": sanitize_trace_text(content.strip()),
                        }
                    )
                elif s.role == "tool":
                    messages.append(
                        {
                            "role": "tool",
                            "name": s.tool_name,
                            "content": sanitize_trace_text(s.tool_result),
                        }
                    )
            # Add final answer if not duplicate
            if t.final_answer and (
                not messages or messages[-1].get("content") != t.final_answer
            ):
                messages.append(
                    {
                        "role": "assistant",
                        "content": sanitize_trace_text(t.final_answer),
                    }
                )
            dataset.append({"messages": messages})
        return dataset

    @staticmethod
    def to_sharegpt_format(traces: list[TrajectoryTrace]) -> list[dict[str, Any]]:
        """Export into ShareGPT format."""
        dataset = []
        for t in traces:
            conversations = []
            for s in t.steps:
                role_label = "human" if s.role == "user" else "gpt"
                val = s.content or s.final_answer or s.thought
                if val:
                    conversations.append(
                        {"from": role_label, "value": sanitize_trace_text(val)}
                    )
            dataset.append({"id": t.session_id, "conversations": conversations})
        return dataset

    @staticmethod
    def to_chatml_format(traces: list[TrajectoryTrace]) -> list[str]:
        """Export into ChatML formatted raw text samples."""
        samples = []
        for t in traces:
            blocks = [
                "<|im_start|>system\nYou are Dream Assistant v2.0.<|im_end|>"
            ]
            for s in t.steps:
                body = s.content
                if s.thought:
                    body = f"<thought>\n{s.thought}\n</thought>\n{body}"
                blocks.append(f"<|im_start|>{s.role}\n{sanitize_trace_text(body.strip())}<|im_end|>")
            if t.final_answer:
                blocks.append(f"<|im_start|>assistant\n{sanitize_trace_text(t.final_answer)}<|im_end|>")
            samples.append("\n".join(blocks))
        return samples

    @staticmethod
    def to_alpaca_format(traces: list[TrajectoryTrace]) -> list[dict[str, str]]:
        """Export into Alpaca instruction-following format."""
        dataset = []
        for t in traces:
            dataset.append(
                {
                    "instruction": sanitize_trace_text(t.task_prompt),
                    "input": "",
                    "output": sanitize_trace_text(t.final_answer),
                }
            )
        return dataset

    @classmethod
    def export_to_file(
        cls,
        traces: list[TrajectoryTrace],
        output_path: Path | str,
        export_format: DistillFormat | str = DistillFormat.OPENAI,
    ) -> dict[str, Any]:
        """Format and write training dataset to target file."""
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        fmt = DistillFormat(export_format)

        if fmt == DistillFormat.OPENAI:
            data = cls.to_openai_format(traces)
            lines = [json.dumps(row, ensure_ascii=False) for row in data]
            out_p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        elif fmt == DistillFormat.SHAREGPT:
            data = cls.to_sharegpt_format(traces)
            out_p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        elif fmt == DistillFormat.CHATML:
            samples = cls.to_chatml_format(traces)
            out_p.write_text("\n\n---\n\n".join(samples) + "\n", encoding="utf-8")
        elif fmt == DistillFormat.ALPACA:
            data = cls.to_alpaca_format(traces)
            out_p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "success": True,
            "format": fmt.value,
            "samples_count": len(traces),
            "output_path": str(out_p),
            "file_size_bytes": out_p.stat().st_size,
        }
