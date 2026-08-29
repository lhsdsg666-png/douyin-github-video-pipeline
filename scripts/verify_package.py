#!/usr/bin/env python3
"""Verify a complete Douyin episode package before browser delivery."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_ARTIFACTS = (
    "script",
    "narration",
    "transcript",
    "final_video",
    "vertical_cover",
    "landscape_cover",
    "publish_info",
)
TEXT_ARTIFACTS = {"script", "transcript", "subtitles", "publish_info"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid manifest JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit("Manifest root must be a JSON object.")
    return value


def atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def resolve_artifact(value: Any, workspace: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value).expanduser()
    return (path if path.is_absolute() else workspace / path).resolve()


def probe_media(path: Path) -> dict[str, Any]:
    executable = shutil.which("ffprobe")
    if not executable:
        return {"error": "ffprobe is unavailable"}
    completed = subprocess.run(
        [
            executable,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=index,codec_type,codec_name,width,height,duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return {"error": completed.stderr.strip() or "ffprobe failed"}
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"error": "ffprobe returned invalid JSON"}


def as_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Checks:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.items.append({"name": name, "passed": bool(passed), "detail": detail})

    @property
    def passed(self) -> bool:
        return all(item["passed"] for item in self.items)


def check_text(checks: Checks, name: str, path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        checks.add(f"{name}_utf8", False, f"Not valid UTF-8: {exc}")
        return None
    except OSError as exc:
        checks.add(f"{name}_readable", False, str(exc))
        return None
    checks.add(f"{name}_utf8", "\ufffd" not in text, "UTF-8 text without replacement characters")
    checks.add(f"{name}_not_empty", bool(text.strip()), f"{len(text)} characters")
    return text


def check_cover(checks: Checks, name: str, path: Path, expected: tuple[int, int]) -> None:
    probe = probe_media(path)
    if probe.get("error"):
        checks.add(f"{name}_probe", False, str(probe["error"]))
        return
    streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]
    if not streams:
        checks.add(f"{name}_stream", False, "No image/video stream")
        return
    width = int(streams[0].get("width") or 0)
    height = int(streams[0].get("height") or 0)
    checks.add(
        f"{name}_dimensions",
        (width, height) == expected,
        f"actual={width}x{height}, expected={expected[0]}x{expected[1]}",
    )


def check_final_video(checks: Checks, path: Path) -> None:
    probe = probe_media(path)
    if probe.get("error"):
        checks.add("final_video_probe", False, str(probe["error"]))
        return
    streams = probe.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    checks.add("final_video_has_video", bool(video_streams), "Video stream present")
    checks.add("final_video_has_audio", bool(audio_streams), "Audio stream present")
    duration = as_number(probe.get("format", {}).get("duration")) or 0
    checks.add("final_video_duration", duration > 5, f"duration={duration:.3f}s")
    if video_streams:
        width = int(video_streams[0].get("width") or 0)
        height = int(video_streams[0].get("height") or 0)
        checks.add(
            "final_video_dimensions",
            (width, height) == (1080, 1920),
            f"actual={width}x{height}, expected=1080x1920",
        )
    if video_streams and audio_streams:
        video_duration = as_number(video_streams[0].get("duration"))
        audio_duration = as_number(audio_streams[0].get("duration"))
        if video_duration is not None and audio_duration is not None:
            drift = abs(video_duration - audio_duration)
            checks.add("audio_video_duration_drift", drift <= 1, f"drift={drift:.3f}s")
        else:
            checks.add(
                "audio_video_duration_drift",
                True,
                "Per-stream durations unavailable; container duration was verified.",
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    data = load_json(manifest_path)
    workspace = Path(data.get("workspace") or manifest_path.parent).resolve()
    checks = Checks()

    project = data.get("project", {})
    for field in ("name", "repo", "angle", "core_demo", "opening_result"):
        value = project.get(field)
        checks.add(f"project_{field}", bool(value), f"value={value!r}")

    research = data.get("research", {})
    official_sources = research.get("official_sources")
    checks.add(
        "official_sources",
        isinstance(official_sources, list) and len(official_sources) > 0,
        f"count={len(official_sources) if isinstance(official_sources, list) else 0}",
    )
    checks.add(
        "cost_checked",
        research.get("cost_checked") is True,
        f"value={research.get('cost_checked')!r}",
    )

    artifacts = data.get("artifacts", {})
    resolved: dict[str, Path] = {}
    text_content: dict[str, str] = {}
    for name in REQUIRED_ARTIFACTS:
        path = resolve_artifact(artifacts.get(name), workspace)
        exists = bool(path and path.is_file() and path.stat().st_size > 0)
        checks.add(
            f"artifact_{name}",
            exists,
            str(path) if path else "missing path",
        )
        if exists and path:
            resolved[name] = path
    subtitles = resolve_artifact(artifacts.get("subtitles"), workspace)
    if subtitles:
        exists = subtitles.is_file() and subtitles.stat().st_size > 0
        checks.add("artifact_subtitles", exists, str(subtitles))
        if exists:
            resolved["subtitles"] = subtitles

    for name in TEXT_ARTIFACTS:
        if name in resolved:
            text = check_text(checks, name, resolved[name])
            if text is not None:
                text_content[name] = text

    if "script" in text_content:
        checks.add("script_cta", "关注" in text_content["script"], "Must contain a follow CTA")
    if "transcript" in text_content:
        checks.add(
            "transcript_cta",
            "关注" in text_content["transcript"],
            "Actual narration transcript must contain the CTA",
        )

    if "narration" in resolved:
        probe = probe_media(resolved["narration"])
        streams = [] if probe.get("error") else probe.get("streams", [])
        duration = as_number(probe.get("format", {}).get("duration")) or 0
        checks.add(
            "narration_audio",
            any(s.get("codec_type") == "audio" for s in streams) and duration > 0,
            probe.get("error") or f"duration={duration:.3f}s",
        )
    if "final_video" in resolved:
        check_final_video(checks, resolved["final_video"])
    if "vertical_cover" in resolved:
        check_cover(checks, "vertical_cover", resolved["vertical_cover"], (1080, 1920))
    if "landscape_cover" in resolved:
        check_cover(checks, "landscape_cover", resolved["landscape_cover"], (1440, 1080))

    publish = data.get("publish", {})
    checks.add("publish_title", bool(str(publish.get("title") or "").strip()), "Title is required")
    checks.add(
        "publish_description",
        bool(str(publish.get("description") or "").strip()),
        "Description is required",
    )
    hashtags = publish.get("hashtags")
    checks.add(
        "publish_hashtags",
        isinstance(hashtags, list) and len(hashtags) > 0,
        f"count={len(hashtags) if isinstance(hashtags, list) else 0}",
    )

    report_path = (
        args.report.resolve()
        if args.report
        else (workspace / "verification" / "qa-report.json").resolve()
    )
    report = {
        "checked_at": now_iso(),
        "manifest": str(manifest_path),
        "passed": checks.passed,
        "failed_count": sum(not item["passed"] for item in checks.items),
        "checks": checks.items,
        "manual_checks_required": [
            "Inspect opening, midpoint, CTA, and ending frames for safe-zone and visual quality.",
            "Review all visible media for private data, accounts, keys, notifications, and personal paths.",
            "Confirm project claims, limitations, and paid-service disclosures match official sources.",
        ],
    }
    atomic_json_write(report_path, report)
    print(
        f"QA {'PASS' if report['passed'] else 'FAIL'} | "
        f"failed={report['failed_count']} | report={report_path}"
    )
    if not report["passed"]:
        for item in checks.items:
            if not item["passed"]:
                print(f"- {item['name']}: {item['detail']}")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
