#!/usr/bin/env python3
"""Safely update a douyin-github-video-pipeline episode manifest."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGES = {
    "researching",
    "awaiting_selection",
    "selected",
    "demo_verified",
    "script_ready",
    "audio_ready",
    "rendered",
    "qa_passed",
    "uploading",
    "draft_saved",
    "scheduled",
    "needs_attention",
}

TRANSITIONS = {
    "researching": {"awaiting_selection", "needs_attention"},
    "awaiting_selection": {"selected", "needs_attention"},
    "selected": {"demo_verified", "awaiting_selection", "needs_attention"},
    "demo_verified": {"script_ready", "selected", "needs_attention"},
    "script_ready": {"audio_ready", "demo_verified", "needs_attention"},
    "audio_ready": {"rendered", "script_ready", "needs_attention"},
    "rendered": {"qa_passed", "audio_ready", "needs_attention"},
    "qa_passed": {"uploading", "rendered", "needs_attention"},
    "uploading": {"draft_saved", "scheduled", "needs_attention"},
    "draft_saved": {"needs_attention"},
    "scheduled": {"needs_attention"},
    "needs_attention": set(),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Manifest is invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Manifest root must be a JSON object.")
    return data


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
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


def parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def set_path(data: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = [part for part in dotted_path.split(".") if part]
    if not parts:
        raise SystemExit(f"Invalid --set path: {dotted_path!r}")
    cursor: dict[str, Any] = data
    for part in parts[:-1]:
        existing = cursor.get(part)
        if existing is None:
            cursor[part] = {}
        elif not isinstance(existing, dict):
            raise SystemExit(
                f"Cannot set {dotted_path!r}: {part!r} is not an object."
            )
        cursor = cursor[part]
    cursor[parts[-1]] = value


def validate_terminal_transition(data: dict[str, Any], target: str) -> None:
    qa_passed = data.get("qa", {}).get("passed") is True
    qa_report = data.get("qa", {}).get("report")
    mode = data.get("publish", {}).get("mode")
    browser_status = data.get("browser", {}).get("status")
    browser_evidence = data.get("browser", {}).get("evidence")
    confirmation = data.get("publish", {}).get("schedule_confirmation", {})

    if target in {"qa_passed", "uploading", "draft_saved", "scheduled"} and not qa_passed:
        raise SystemExit(f"Cannot enter {target}: qa.passed must be true.")
    if target in {"qa_passed", "uploading", "draft_saved", "scheduled"} and not qa_report:
        raise SystemExit(f"Cannot enter {target}: qa.report must be recorded.")
    if target == "draft_saved":
        if mode != "draft" or browser_status != "draft_saved":
            raise SystemExit(
                "Cannot enter draft_saved: publish.mode must be draft and "
                "browser.status must be draft_saved."
            )
        if not isinstance(browser_evidence, list) or not browser_evidence:
            raise SystemExit("Cannot enter draft_saved: browser.evidence is required.")
    if target == "scheduled":
        if mode != "schedule" or browser_status != "scheduled":
            raise SystemExit(
                "Cannot enter scheduled: publish.mode must be schedule and "
                "browser.status must be scheduled."
            )
        if confirmation.get("confirmed") is not True:
            raise SystemExit(
                "Cannot enter scheduled: schedule_confirmation.confirmed must be true."
            )
        if not confirmation.get("confirmed_at") or not confirmation.get("payload_fingerprint"):
            raise SystemExit(
                "Cannot enter scheduled: confirmed_at and payload_fingerprint are required."
            )
        if not isinstance(browser_evidence, list) or not browser_evidence:
            raise SystemExit("Cannot enter scheduled: browser.evidence is required.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Path to episode.json")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--stage", choices=sorted(STAGES))
    group.add_argument(
        "--resume",
        action="store_true",
        help="Resume a needs_attention episode from its recorded blocked stage.",
    )
    parser.add_argument("--note", default="", help="Short history or blocker note")
    parser.add_argument(
        "--set",
        dest="setters",
        action="append",
        default=[],
        metavar="PATH=VALUE",
        help="Set a dotted JSON path. VALUE is parsed as JSON when possible.",
    )
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    data = load_manifest(manifest_path)
    current = data.get("stage")
    if current not in STAGES:
        raise SystemExit(f"Manifest has unknown stage: {current!r}")

    for setter in args.setters:
        if "=" not in setter:
            raise SystemExit(f"Invalid --set value, expected PATH=VALUE: {setter!r}")
        dotted_path, raw_value = setter.split("=", 1)
        if dotted_path == "stage":
            raise SystemExit("Use --stage to change stage; do not set stage directly.")
        set_path(data, dotted_path, parse_value(raw_value))

    target = current
    if args.resume:
        if current != "needs_attention":
            raise SystemExit("--resume is only valid from needs_attention.")
        target = data.get("blocked_from")
        if target not in STAGES or target == "needs_attention":
            raise SystemExit("No valid blocked_from stage is recorded.")
        data["blocked_from"] = None
        data["blocker"] = None
    elif args.stage:
        target = args.stage
        if target != current:
            allowed = TRANSITIONS[current]
            if target not in allowed:
                raise SystemExit(f"Invalid stage transition: {current} -> {target}")
            if target == "needs_attention":
                if not args.note.strip():
                    raise SystemExit("A non-empty --note is required for needs_attention.")
                data["blocked_from"] = current
                data["blocker"] = args.note.strip()
            validate_terminal_transition(data, target)

    changed = bool(args.setters) or target != current or bool(args.note.strip())
    if not changed:
        print(f"No changes: {manifest_path}")
        return 0

    data["stage"] = target
    data["updated_at"] = now_iso()
    history = data.setdefault("history", [])
    history.append(
        {
            "at": data["updated_at"],
            "from": current,
            "to": target,
            "note": args.note.strip(),
            "updated_fields": [item.split("=", 1)[0] for item in args.setters],
        }
    )
    atomic_write(manifest_path, data)
    print(f"Updated {manifest_path} | {current} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
