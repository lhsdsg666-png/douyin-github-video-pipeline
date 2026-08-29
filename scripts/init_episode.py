#!/usr/bin/env python3
"""Create one recoverable episode workspace and its source-of-truth manifest."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path


SUBDIRECTORIES = (
    "research",
    "user-assets",
    "audio",
    "media",
    "captures",
    "renders",
    "covers",
    "verification",
    "publish",
    "logs",
)
INVALID_WINDOWS_CHARS = set('<>:"/\\|?*')


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_json_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def validate_episode_id(value: str) -> str:
    value = value.strip()
    if not value or value in {".", ".."}:
        raise argparse.ArgumentTypeError("episode-id 不能为空")
    if len(value) > 100 or any(char in INVALID_WINDOWS_CHARS for char in value):
        raise argparse.ArgumentTypeError("episode-id 包含 Windows 不允许的字符或过长")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="创建抖音技术视频单期目录和 episode.json")
    parser.add_argument("output_root", type=Path, help="各期项目目录的父目录")
    parser.add_argument("episode_id", type=validate_episode_id)
    parser.add_argument("--project-name")
    parser.add_argument("--repo")
    parser.add_argument("--angle")
    parser.add_argument("--mode", choices=("draft", "schedule"), default="draft")
    parser.add_argument("--schedule-at", help="带时区 ISO-8601 时间，仅 schedule 模式使用")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_root = args.output_root.expanduser().resolve()
    episode_dir = output_root / args.episode_id
    manifest_path = episode_dir / "episode.json"

    if episode_dir.exists() and any(episode_dir.iterdir()):
        print(
            json.dumps(
                {"status": "error", "error": "episode_directory_not_empty", "path": str(episode_dir)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    episode_dir.mkdir(parents=True, exist_ok=True)
    directories: dict[str, str] = {}
    for name in SUBDIRECTORIES:
        path = episode_dir / name
        path.mkdir(exist_ok=True)
        directories[name.replace("-", "_")] = str(path.resolve())

    design_source = Path(__file__).resolve().parents[1] / "assets" / "default-design.md"
    design_target = episode_dir / "DESIGN.md"
    if design_source.exists():
        shutil.copy2(design_source, design_target)

    created_at = now_iso()
    selected = bool(args.project_name and args.angle)
    manifest = {
        "schema_version": 1,
        "episode_id": args.episode_id,
        "workspace": str(episode_dir.resolve()),
        "stage": "selected" if selected else "researching",
        "blocked_from": None,
        "blocker": None,
        "created_at": created_at,
        "updated_at": created_at,
        "directories": directories,
        "project": {
            "name": args.project_name,
            "repo": args.repo,
            "version": None,
            "angle": args.angle,
            "pain_point": None,
            "core_demo": None,
            "opening_result": None,
        },
        "research": {
            "official_sources": [],
            "verified_at": None,
            "cost_checked": False,
            "demo_source": "user_preferred",
            "demo_evidence": [],
            "limitations": [],
        },
        "artifacts": {
            "script": None,
            "narration": None,
            "transcript": None,
            "subtitles": None,
            "final_video": None,
            "vertical_cover": None,
            "landscape_cover": None,
            "publish_info": None,
        },
        "publish": {
            "mode": args.mode,
            "title": None,
            "description": None,
            "hashtags": [],
            "schedule_at": args.schedule_at,
            "schedule_confirmation": {
                "confirmed": False,
                "confirmed_at": None,
                "payload_fingerprint": None,
            },
        },
        "qa": {"passed": False, "report": None, "checked_at": None},
        "browser": {
            "expected_account": None,
            "status": "not_started",
            "evidence": [],
        },
        "history": [
            {
                "at": created_at,
                "from": None,
                "to": "selected" if selected else "researching",
                "note": "episode initialized",
            }
        ],
    }
    atomic_json_write(manifest_path, manifest)
    print(
        json.dumps(
            {
                "status": "ok",
                "episode": args.episode_id,
                "stage": manifest["stage"],
                "manifest": str(manifest_path.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
