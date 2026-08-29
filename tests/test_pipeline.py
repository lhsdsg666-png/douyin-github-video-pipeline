#!/usr/bin/env python3
"""End-to-end smoke test for the deterministic episode helpers."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"


def run(command: list[str], expected: int = 0) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != expected:
        raise AssertionError(
            f"Expected exit {expected}, got {completed.returncode}\n"
            f"COMMAND: {command}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


def ffmpeg(*arguments: str) -> None:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise SystemExit("SKIP: ffmpeg is required for the end-to-end smoke test")
    run([executable, "-hide_banner", "-loglevel", "error", "-y", *arguments])


def update(manifest: Path, *arguments: str, expected: int = 0) -> None:
    run(
        [sys.executable, str(SCRIPTS / "update_episode.py"), str(manifest), *arguments],
        expected=expected,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="douyin-skill-test-") as temp_name:
        root = Path(temp_name)
        media = root / "fixtures"
        media.mkdir()

        final_video = media / "final.mp4"
        narration = media / "narration.wav"
        vertical_cover = media / "vertical.png"
        landscape_cover = media / "landscape.png"
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "color=c=0x0B1020:s=1080x1920:d=6:r=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=6",
            "-shortest",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(final_video),
        )
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=6",
            str(narration),
        )
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "color=c=0x2563EB:s=1080x1920",
            "-frames:v",
            "1",
            str(vertical_cover),
        )
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "color=c=0x2563EB:s=1440x1080",
            "-frames:v",
            "1",
            str(landscape_cover),
        )
        script = media / "script.md"
        transcript = media / "transcript.txt"
        publish_info = media / "publish.txt"
        script.write_text("一个真实演示。关注我，分享更多实用的开源项目。\n", encoding="utf-8")
        transcript.write_text("一个真实演示。关注我，分享更多实用的开源项目。\n", encoding="utf-8")
        publish_info.write_text("标题、介绍和话题已准备。\n", encoding="utf-8")

        run(
            [
                sys.executable,
                str(SCRIPTS / "init_episode.py"),
                str(root),
                "case",
                "--project-name",
                "Example",
                "--repo",
                "https://github.com/example/example",
                "--angle",
                "六秒展示核心结果",
            ]
        )
        manifest = root / "case" / "episode.json"
        common_sets = [
            "--set",
            "project.core_demo=完成一个核心任务",
            "--set",
            "project.opening_result=前三秒看到结果",
            "--set",
            'research.official_sources=["https://github.com/example/example"]',
            "--set",
            "research.cost_checked=true",
            "--set",
            f"artifacts.script={script}",
            "--set",
            f"artifacts.narration={narration}",
            "--set",
            f"artifacts.transcript={transcript}",
            "--set",
            f"artifacts.final_video={final_video}",
            "--set",
            f"artifacts.vertical_cover={vertical_cover}",
            "--set",
            f"artifacts.landscape_cover={landscape_cover}",
            "--set",
            f"artifacts.publish_info={publish_info}",
            "--set",
            "publish.title=示例项目真实演示",
            "--set",
            "publish.description=只展示已经验证的功能。",
            "--set",
            'publish.hashtags=["#开源项目","#AI工具"]',
            "--set",
            "browser.expected_account=test-account",
        ]
        update(manifest, *common_sets)
        for stage in ("demo_verified", "script_ready", "audio_ready", "rendered"):
            update(manifest, "--stage", stage, "--note", f"test {stage}")

        report = root / "case" / "verification" / "qa-report.json"
        run(
            [
                sys.executable,
                str(SCRIPTS / "verify_package.py"),
                str(manifest),
                "--report",
                str(report),
            ]
        )
        assert json.loads(report.read_text(encoding="utf-8"))["passed"] is True
        update(
            manifest,
            "--stage",
            "qa_passed",
            "--set",
            "qa.passed=true",
            "--set",
            f"qa.report={report}",
            "--set",
            "qa.checked_at=2026-08-26T16:00:00+08:00",
        )

        payload = root / "case" / "publish" / "publish-payload.json"
        run(
            [
                sys.executable,
                str(SCRIPTS / "build_publish_payload.py"),
                str(manifest),
                "--output",
                str(payload),
            ]
        )
        assert json.loads(payload.read_text(encoding="utf-8"))["status"] == "ready"

        update(
            manifest,
            "--set",
            "publish.mode=schedule",
            "--set",
            "publish.schedule_at=2030-08-26T20:00:00+08:00",
        )
        run(
            [
                sys.executable,
                str(SCRIPTS / "build_publish_payload.py"),
                str(manifest),
                "--output",
                str(payload),
            ],
            expected=3,
        )
        preview = json.loads(payload.read_text(encoding="utf-8"))
        assert preview["status"] == "confirmation_required"
        fingerprint = preview["payload_fingerprint"]
        update(
            manifest,
            "--set",
            "publish.schedule_confirmation.confirmed=true",
            "--set",
            "publish.schedule_confirmation.confirmed_at=2026-08-26T16:05:00+08:00",
            "--set",
            f"publish.schedule_confirmation.payload_fingerprint={fingerprint}",
        )
        run(
            [
                sys.executable,
                str(SCRIPTS / "build_publish_payload.py"),
                str(manifest),
                "--output",
                str(payload),
            ]
        )
        assert json.loads(payload.read_text(encoding="utf-8"))["status"] == "ready"
        update(manifest, "--stage", "uploading", "--note", "browser delivery started")
        update(
            manifest,
            "--stage",
            "scheduled",
            "--set",
            "browser.status=scheduled",
            "--set",
            'browser.evidence=["content manager shows the exact scheduled time"]',
            "--note",
            "browser readback verified",
        )

        assets = root / "case" / "user-assets"
        shutil.copy2(vertical_cover, assets / "shot-1.png")
        shutil.copy2(vertical_cover, assets / "shot-2.png")
        shutil.copy2(vertical_cover, assets / "shot-3.png")
        inventory = root / "case" / "verification" / "asset-report.json"
        run(
            [
                sys.executable,
                str(SCRIPTS / "inspect_user_assets.py"),
                str(assets),
                "--json-output",
                str(inventory),
            ]
        )
        assert json.loads(inventory.read_text(encoding="utf-8"))["summary"]["usable_demo"] is True

        run([sys.executable, str(SCRIPTS / "init_episode.py"), str(root), "resume-case"])
        resume_manifest = root / "resume-case" / "episode.json"
        update(resume_manifest, "--stage", "awaiting_selection")
        update(
            resume_manifest,
            "--stage",
            "needs_attention",
            "--note",
            "waiting for one project choice",
        )
        update(resume_manifest, "--resume", "--note", "choice received")
        assert json.loads(resume_manifest.read_text(encoding="utf-8"))["stage"] == "awaiting_selection"

    print("PASS: episode state, media QA, payload confirmation, assets, and recovery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
