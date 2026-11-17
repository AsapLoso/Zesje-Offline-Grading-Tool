"""Interactive selector for Zesje differential uploads."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import exam_config as ec  # noqa: E402


def _read_exam_id(exam_dir: Path) -> tuple[str | None, bool]:
    """Return (exam_id, is_cloud_only) for an exam directory."""
    cfg_path = exam_dir / "config.json"
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return data.get("exam_id"), False
    except OSError:
        return None, True
    except json.JSONDecodeError:
        return None, False


def _is_populated(exam_dir: Path) -> bool:
    """Return True if populated upload targets exist for the exam."""
    pop_dir = exam_dir / "populated"
    try:
        return (
            (pop_dir / "per_problem_targets.json").exists()
            or (pop_dir / "populated_grades.xlsx").exists()
        )
    except OSError:
        return False


def main() -> int:
    """Prompt for an active/archived exam (or all populated active exams) and run uploader."""
    active = ec.list_active_exams()
    archived = ec.list_archived_exams()
    all_exams: list[tuple[Path, bool]] = [(p, False) for p in active] + [
        (p, True) for p in archived
    ]
    populated_active = [p for p in active if _is_populated(p)]

    print("=" * 60)
    print("  ZESJE DIFFERENTIAL UPLOADER (exam_config selector)")
    print("=" * 60)
    for idx, (exam_dir, is_archive) in enumerate(all_exams, 1):
        exam_id, cloud_only = _read_exam_id(exam_dir)
        tags: list[str] = []
        if is_archive:
            tags.append("ARCHIVE")
        if cloud_only:
            tags.append("CLOUD-ONLY")
        tag_str = f" [{' / '.join(tags)}]" if tags else ""
        eid_str = exam_id if exam_id is not None else "?"
        print(f"  {idx}. {exam_dir.name} (exam_id={eid_str}){tag_str}")

    print("  A. ALL populated active exams (Differential)")
    print("  D. Dry-run ALL populated active exams")
    print("=" * 60)

    if not all_exams:
        print("[WARN] No active or archived exams found.")
        return 1

    raw = input(f"Select [A/D/1-{len(all_exams)}, Enter=A]: ").strip().upper() or "A"

    if raw in ("A", "D"):
        targets = populated_active
        if not targets:
            print("[WARN] No populated active exams found.")
            return 1
        extra_args = ["--dry-run"] if raw == "D" else []
    elif raw.isdigit() and 1 <= int(raw) <= len(all_exams):
        selected, _ = all_exams[int(raw) - 1]
        _, cloud_only = _read_exam_id(selected)
        if cloud_only:
            print(
                f"[ERROR] {selected.name}/config.json is OneDrive cloud-only; "
                "open/sync it in Explorer first."
            )
            return 1
        targets = [selected]
        extra_args = []
    else:
        print(f"[ERROR] Invalid selection: {raw}")
        return 1

    uploader = ROOT / "4_upload" / "zesje_uploader.py"
    for exam_dir in targets:
        cmd = [
            sys.executable,
            str(uploader),
            "--config",
            str(exam_dir / "config.json"),
            *extra_args,
        ]
        subprocess.run(cmd, check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
