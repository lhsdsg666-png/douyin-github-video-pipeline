#!/usr/bin/env python3
"""Build an immutable browser handoff payload after media QA passes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def resolve_required_file(value: Any, workspace: Path, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"Missing required file field: {field}")
    path = Path(value).expanduser()
    path = (path if path.is_absolute() else workspace / path).resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise SystemExit(f"Invalid required file field {field}: {path}")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_schedule(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SystemExit("schedule mode requires publish.schedule_at")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SystemExit("publish.schedule_at must be an ISO-8601 date-time") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise SystemExit("publish.schedule_at must include an explicit timezone")
    if result.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        raise SystemExit("publish.schedule_at must be in the future")
    return result


def canonical_fingerprint(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    data = load_json(manifest_path)
    if data.get("stage") not in {"qa_passed", "uploading"}:
        raise SystemExit("Manifest stage must be qa_passed or uploading.")
    if data.get("qa", {}).get("passed") is not True:
        raise SystemExit("qa.passed must be true before browser delivery.")

    workspace = Path(data.get("workspace") or manifest_path.parent).resolve()
    qa_report_value = data.get("qa", {}).get("report")
    qa_report_path = resolve_required_file(qa_report_value, workspace, "qa.report")
    qa_report = load_json(qa_report_path)
    if qa_report.get("passed") is not True:
        raise SystemExit("The recorded QA report does not have passed=true.")
    artifacts = data.get("artifacts", {})
    files = {
        name: resolve_required_file(artifacts.get(name), workspace, name)
        for name in ("final_video", "vertical_cover", "landscape_cover")
    }
    publish = data.get("publish", {})
    mode = publish.get("mode")
    if mode not in {"draft", "schedule"}:
        raise SystemExit("Only draft and schedule modes are supported; immediate publish is forbidden.")

    title = str(publish.get("title") or "").strip()
    description = str(publish.get("description") or "").strip()
    hashtags = publish.get("hashtags")
    expected_account = str(data.get("browser", {}).get("expected_account") or "").strip()
    if not title or not description or not isinstance(hashtags, list) or not hashtags:
        raise SystemExit("Publish title, description, and at least one hashtag are required.")
    if not expected_account:
        raise SystemExit("browser.expected_account is required to prevent cross-account delivery.")

    file_payload = {
        name: {"path": str(path), "sha256": sha256_file(path), "size_bytes": path.stat().st_size}
        for name, path in files.items()
    }
    fingerprint_input: dict[str, Any] = {
        "episode_id": data.get("episode_id"),
        "mode": mode,
        "title": title,
        "description": description,
        "hashtags": hashtags,
        "expected_account": expected_account,
        "files": file_payload,
        "schedule_at": None,
    }
    if mode == "schedule":
        fingerprint_input["schedule_at"] = parse_schedule(publish.get("schedule_at")).isoformat()

    fingerprint = canonical_fingerprint(fingerprint_input)
    status = "ready"
    exit_code = 0
    confirmation = publish.get("schedule_confirmation", {})
    if mode == "schedule":
        confirmed = confirmation.get("confirmed") is True
        matches = confirmation.get("payload_fingerprint") == fingerprint
        timestamped = bool(confirmation.get("confirmed_at"))
        if not (confirmed and matches and timestamped):
            status = "confirmation_required"
            exit_code = 3

    output = (
        args.output.resolve()
        if args.output
        else (workspace / "publish" / "publish-payload.json").resolve()
    )
    payload = {
        "status": status,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "manifest": str(manifest_path),
        "qa_report": str(qa_report_path),
        "payload_fingerprint": fingerprint,
        **fingerprint_input,
        "browser_rules": {
            "verify_account_before_upload": True,
            "verify_uploaded_filename_and_cover_readback": True,
            "immediate_publish_allowed": False,
            "uncertain_result_requires_external_state_check": True,
        },
    }
    atomic_json_write(output, payload)
    print(f"Payload {status} | fingerprint={fingerprint} | output={output}")
    if exit_code == 3:
        print(
            "Show the exact schedule summary and fingerprint to the user. "
            "Only after explicit confirmation, store this fingerprint and confirmed_at in episode.json."
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
