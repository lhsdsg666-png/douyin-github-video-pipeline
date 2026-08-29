#!/usr/bin/env python3
"""Inventory user-provided media and judge whether it is usable for a demo."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
TEXT_EXTENSIONS = {".txt", ".md", ".json"}


def ffprobe(path: Path) -> dict[str, Any] | None:
    executable = shutil.which("ffprobe")
    if not executable:
        return None
    completed = subprocess.run(
        [
            executable,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=index,codec_type,width,height,duration",
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


def number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def inspect_file(path: Path, root: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        kind = "video"
    elif suffix in IMAGE_EXTENSIONS:
        kind = "image"
    elif suffix in TEXT_EXTENSIONS:
        kind = "text"
    else:
        kind = "other"

    item: dict[str, Any] = {
        "path": str(path.resolve()),
        "relative_path": str(path.relative_to(root)),
        "kind": kind,
        "size_bytes": path.stat().st_size,
    }
    if kind in {"video", "image"}:
        item["probe"] = ffprobe(path)
    return item


def summarize(items: list[dict[str, Any]], ffprobe_available: bool) -> dict[str, Any]:
    warnings: list[str] = []
    usable_videos = 0
    usable_images = 0

    for item in items:
        if item["size_bytes"] <= 0:
            warnings.append(f"Empty file: {item['relative_path']}")
            continue
        if item["kind"] not in {"video", "image"}:
            continue
        probe = item.get("probe")
        if probe is None:
            warnings.append("ffprobe is unavailable; media dimensions were not verified.")
            continue
        if probe.get("error"):
            warnings.append(f"Unreadable media: {item['relative_path']}: {probe['error']}")
            continue
        video_streams = [
            stream
            for stream in probe.get("streams", [])
            if stream.get("codec_type") == "video"
        ]
        if not video_streams:
            warnings.append(f"No video/image stream: {item['relative_path']}")
            continue
        width = max(int(stream.get("width") or 0) for stream in video_streams)
        height = max(int(stream.get("height") or 0) for stream in video_streams)
        if width < 720 or height < 720:
            warnings.append(
                f"Low resolution ({width}x{height}): {item['relative_path']}"
            )
        if item["kind"] == "video":
            duration = number(probe.get("format", {}).get("duration")) or 0
            if 5 <= duration <= 120:
                usable_videos += 1
            else:
                warnings.append(
                    f"Video duration should normally be 5-120s ({duration:.1f}s): "
                    f"{item['relative_path']}"
                )
        else:
            usable_images += 1

    if not items:
        warnings.append("No user assets were found.")

    return {
        "counts": {
            "total": len(items),
            "videos": sum(item["kind"] == "video" for item in items),
            "images": sum(item["kind"] == "image" for item in items),
            "texts": sum(item["kind"] == "text" for item in items),
            "other": sum(item["kind"] == "other" for item in items),
        },
        "usable_demo": usable_videos >= 1 or usable_images >= 3,
        "usable_videos": usable_videos,
        "usable_images": usable_images,
        "privacy_review_required": True,
        "ffprobe_available": ffprobe_available,
        "warnings": sorted(set(warnings)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset_directory", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    root = args.asset_directory.resolve()
    if not root.is_dir():
        raise SystemExit(f"Asset directory not found: {root}")

    files = sorted(path for path in root.rglob("*") if path.is_file())
    items = [inspect_file(path, root) for path in files]
    report = {
        "asset_directory": str(root),
        "summary": summarize(items, shutil.which("ffprobe") is not None),
        "items": items,
    }

    if args.json_output:
        output = args.json_output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    summary = report["summary"]
    print(
        f"Assets: {summary['counts']['total']} | "
        f"usable_demo={str(summary['usable_demo']).lower()} | "
        f"warnings={len(summary['warnings'])}"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if summary["usable_demo"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
