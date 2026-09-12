"""Multi-Format Serializer and Exporter for Synthetic Training Data."""

from __future__ import annotations

import json
import uuid

from dream.synthetic.types import (
    DatasetFormat,
    SyntheticDatasetExport,
    SyntheticSample,
)


class DatasetExporter:
    """Exports curated synthetic samples to standard JSONL formats for fine-tuning."""

    def export_to_jsonl(
        self,
        samples: list[SyntheticSample],
        target_format: DatasetFormat = DatasetFormat.DPO,
        file_path: str = "",
    ) -> SyntheticDatasetExport:
        """Serialize samples into valid JSONL lines matching target format specifications."""
        lines: list[str] = []

        for s in samples:
            if target_format == DatasetFormat.DPO:
                record = {
                    "prompt": s.prompt,
                    "chosen": s.chosen_response,
                    "rejected": s.rejected_response,
                    "metadata": {"sample_id": s.sample_id, "quality": s.quality_score},
                }
            elif target_format == DatasetFormat.SHAREGPT:
                record = {
                    "id": s.sample_id,
                    "conversations": [
                        {"from": "human", "value": s.prompt},
                        {"from": "gpt", "value": s.chosen_response},
                    ],
                }
            elif target_format == DatasetFormat.ALPACA:
                record = {
                    "instruction": s.prompt,
                    "input": "",
                    "output": s.chosen_response,
                }
            elif target_format == DatasetFormat.KTO:
                # Exports both positive and negative as KTO instances
                rec_pos = {"prompt": s.prompt, "completion": s.chosen_response, "label": True}
                lines.append(json.dumps(rec_pos, ensure_ascii=False))
                if s.rejected_response:
                    rec_neg = {
                        "prompt": s.prompt,
                        "completion": s.rejected_response,
                        "label": False,
                    }
                    lines.append(json.dumps(rec_neg, ensure_ascii=False))
                continue
            elif target_format == DatasetFormat.COT_REASONING:
                record = {
                    "question": s.prompt,
                    "thought": s.reasoning_trace,
                    "answer": s.chosen_response,
                }
            else:
                record = s.to_dict()

            lines.append(json.dumps(record, ensure_ascii=False))

        jsonl_str = "\n".join(lines)
        export_id = f"exp-{uuid.uuid4().hex[:6]}"
        summary_fa = (
            f"صادرات {len(samples)} نمونه آموزشی به فرمت `{target_format.value}` "
            f"با مجموع {len(lines)} خط JSONL."
        )

        return SyntheticDatasetExport(
            export_id=export_id,
            format=target_format,
            total_samples=len(samples),
            jsonl_content=jsonl_str,
            file_path=file_path,
            summary_fa=summary_fa,
        )
