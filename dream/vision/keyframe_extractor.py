"""Temporal Video Stream Keyframe Extractor and Scene Transition Analyzer."""

from __future__ import annotations

import hashlib
import math
import uuid

from dream.vision.types import KeyFrame, VideoTimeline


class KeyframeExtractor:
    """Extracts informative keyframes and identifies scene boundaries in video streams."""

    def __init__(self, entropy_threshold: float = 0.35) -> None:
        self.entropy_threshold = entropy_threshold

    def extract_from_stream(
        self,
        video_id: str,
        frames_data: list[bytes | str],
        fps: float = 30.0,
        sample_stride: int = 15,
    ) -> VideoTimeline:
        """Decompose a stream of video frames into keyframes and temporal scenes.

        Args:
            video_id: Unique identifier for video stream.
            frames_data: List of raw frame bytes or frame content descriptors.
            fps: Video framerate.
            sample_stride: Frame sampling interval.
        """
        if not frames_data:
            return VideoTimeline(
                video_id=video_id,
                duration_sec=0.0,
                total_frames=0,
                sample_rate_fps=fps,
                keyframes=[],
                narrative_summary_fa="جریان ویدیویی فاقد فریم است.",
                scene_count=0,
            )

        total_frames = len(frames_data)
        duration_sec = total_frames / max(1.0, fps)
        keyframes: list[KeyFrame] = []

        prev_hash = ""
        current_scene = 1

        for idx in range(0, total_frames, max(1, sample_stride)):
            frame_item = frames_data[idx]
            timestamp = idx / fps

            # Compute entropy and frame signature
            if isinstance(frame_item, bytes):
                frame_hash = hashlib.sha256(frame_item).hexdigest()
                entropy = self._compute_byte_entropy(frame_item)
            else:
                str_bytes = str(frame_item).encode("utf-8")
                frame_hash = hashlib.sha256(str_bytes).hexdigest()
                entropy = self._compute_byte_entropy(str_bytes)

            is_scene_change = False
            if prev_hash:
                # Hamming-like difference check on hex hashes
                diff_chars = sum(
                    c1 != c2 for c1, c2 in zip(frame_hash[:16], prev_hash[:16], strict=False)
                )
                if diff_chars > 8 or entropy > self.entropy_threshold * 1.5:
                    is_scene_change = True
                    current_scene += 1
            else:
                is_scene_change = True  # Initial frame is start of scene 1

            prev_hash = frame_hash

            caption_fa = (
                f"صحنه {current_scene}: رویداد بصری در ثانیه {timestamp:.1f}"
                if not is_scene_change
                else f"تغییر صحنه به صحنه {current_scene} در ثانیه {timestamp:.1f}"
            )

            kf = KeyFrame(
                frame_id=f"kf-{uuid.uuid4().hex[:6]}",
                timestamp_sec=timestamp,
                frame_index=idx,
                scene_id=current_scene,
                entropy_score=entropy,
                is_scene_transition=is_scene_change,
                caption_fa=caption_fa,
                detected_entities=[f"عنصر_صحنه_{current_scene}"],
                metadata={"hash_prefix": frame_hash[:8]},
            )
            keyframes.append(kf)

        summary_fa = (
            f"تجزیه و تحلیل ویدیو `{video_id}` با مدت زمان {duration_sec:.1f} ثانیه، "
            f"{total_frames} فریم و شناسایی {current_scene} صحنه مجزا."
        )

        return VideoTimeline(
            video_id=video_id,
            duration_sec=duration_sec,
            total_frames=total_frames,
            sample_rate_fps=fps,
            keyframes=keyframes,
            narrative_summary_fa=summary_fa,
            scene_count=current_scene,
            metadata={"extracted_keyframes_count": len(keyframes)},
        )

    def extract_from_simulated_video(
        self,
        video_id: str,
        duration_sec: float = 10.0,
        fps: float = 30.0,
        scene_changes_at_sec: list[float] | None = None,
    ) -> VideoTimeline:
        """Simulate video decomposition for keyframe testing and pipeline verification."""
        scene_changes = scene_changes_at_sec or [3.0, 7.5]
        total_frames = int(duration_sec * fps)
        keyframes: list[KeyFrame] = []

        # Sample at 1 fps
        current_scene = 1
        for sec in range(int(duration_sec)):
            t = float(sec)
            idx = int(t * fps)
            is_transition = False
            for sc in scene_changes:
                if abs(t - sc) < 0.8 and t >= sc:
                    is_transition = True
                    current_scene += 1
                    break

            if sec == 0:
                is_transition = True

            kf = KeyFrame(
                frame_id=f"kf-sim-{sec}",
                timestamp_sec=t,
                frame_index=idx,
                scene_id=current_scene,
                entropy_score=0.45 + (sec * 0.02),
                is_scene_transition=is_transition,
                caption_fa=f"رویداد بصری در ثانیه {t:.1f} (صحنه {current_scene})",
                detected_entities=["کاربر", "رابط کاربری", "دکمه تایید"],
            )
            keyframes.append(kf)

        summary_fa = (
            f"ویدیوی `{video_id}` به مدت {duration_sec} ثانیه و {current_scene} صحنه تفکیک شد."
        )

        return VideoTimeline(
            video_id=video_id,
            duration_sec=duration_sec,
            total_frames=total_frames,
            sample_rate_fps=fps,
            keyframes=keyframes,
            narrative_summary_fa=summary_fa,
            scene_count=current_scene,
        )

    @staticmethod
    def _compute_byte_entropy(data: bytes) -> float:
        """Calculate Shannon entropy of byte sequences."""
        if not data:
            return 0.0
        frequencies: dict[int, int] = {}
        for b in data:
            frequencies[b] = frequencies.get(b, 0) + 1

        entropy = 0.0
        total = len(data)
        for count in frequencies.values():
            p = count / total
            entropy -= p * math.log2(p)

        return min(1.0, entropy / 8.0)  # Normalize to [0.0, 1.0]
