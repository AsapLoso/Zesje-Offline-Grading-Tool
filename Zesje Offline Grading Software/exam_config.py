"""Resolve an exam folder and load its configuration."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable, List, Optional


DATA_DIR = Path(__file__).resolve().parent / "data"


class ExamSelectionError(Exception):
    """An exam selector cannot be resolved; includes the active exam list."""

    def __init__(self, message: str, active_exams: List[Path]):
        super().__init__(message)
        self.active_exams = active_exams


def _exam_dirs(parent: Path) -> List[Path]:
    if not parent.is_dir():
        return []
    return sorted(
        (child for child in parent.iterdir() if child.is_dir() and (child / "config.json").is_file()),
        key=lambda child: child.name.casefold(),
    )


def list_active_exams() -> List[Path]:
    return [path for path in _exam_dirs(DATA_DIR) if path.name.casefold() != "archive"]


def list_archived_exams() -> List[Path]:
    return _exam_dirs(DATA_DIR / "archive")


def _resolve_exam(exam: str) -> Path:
    selector = str(exam).strip()
    active = list_active_exams()
    archived = list_archived_exams()

    exact = [path for path in active + archived if path.name == selector]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        names = ", ".join(path.name for path in exact)
        raise ExamSelectionError(f"Exam folder name {selector!r} is ambiguous: {names}.", active)

    if selector.isdigit():
        matches = [path for path in active if path.name.endswith(f"_exam{selector}")]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            names = ", ".join(path.name for path in matches)
            raise ExamSelectionError(f"Exam number {selector} is ambiguous: {names}.", active)

    raise ExamSelectionError(f"No exam matches {selector!r}.", active)


def _choose_exam(
    *,
    interactive: Optional[bool] = None,
    input_fn: Optional[Callable[[str], str]] = None,
    output_fn: Optional[Callable[[str], None]] = None,
) -> Path:
    active = list_active_exams()
    archived = list_archived_exams()
    if interactive is None:
        interactive = bool(getattr(sys.stdin, "isatty", lambda: False)())
    if not interactive:
        raise ExamSelectionError("No exam was selected and no interactive terminal is available.", active)

    read_input = input_fn or input
    write_output = output_fn or print

    while True:
        write_output("Active exams:")
        if active:
            for number, exam_dir in enumerate(active, 1):
                write_output(f"{number}. {exam_dir.name}")
        else:
            write_output("  (none)")

        archive_option = len(active) + 1
        write_output(f"{archive_option}. Show archived exams")
        choice = read_input("Select an exam number: ").strip()
        if choice == str(archive_option):
            if not archived:
                write_output("No archived exams are available.")
                continue
            write_output("Archived exams:")
            for number, exam_dir in enumerate(archived, 1):
                write_output(f"{number}. {exam_dir.name}")
            write_output(f"{len(archived) + 1}. Back to active exams")
            archived_choice = read_input("Select an archived exam number: ").strip()
            if archived_choice == str(len(archived) + 1):
                continue
            if archived_choice.isdigit() and 1 <= int(archived_choice) <= len(archived):
                return archived[int(archived_choice) - 1]
            write_output("Invalid archived exam selection.")
            continue

        if choice.isdigit() and 1 <= int(choice) <= len(active):
            return active[int(choice) - 1]
        write_output("Invalid exam selection.")


def load_exam_config(
    exam: Optional[str] = None,
    config_path: Optional[str] = None,
    *,
    interactive: Optional[bool] = None,
    input_fn: Optional[Callable[[str], str]] = None,
    output_fn: Optional[Callable[[str], None]] = None,
) -> dict:
    """Load a selected exam's config and attach its folder as ``exam_dir``.

    An explicit config path overrides folder selection and uses that file's parent
    as the exam directory. Otherwise, ``exam`` can be an exact folder name or an
    unambiguous active exam number. With neither, the interactive picker is used.
    """
    if config_path:
        config_file = Path(config_path).expanduser().resolve()
        exam_dir = config_file.parent
    else:
        exam_dir = _resolve_exam(exam) if exam else _choose_exam(
            interactive=interactive, input_fn=input_fn, output_fn=output_fn
        )
        config_file = exam_dir / "config.json"

    with config_file.open("r", encoding="utf-8") as config_stream:
        config = json.load(config_stream)
    config["exam_dir"] = str(exam_dir.resolve())
    return config


def load_exam_config_or_exit(exam: Optional[str] = None, config_path: Optional[str] = None) -> dict:
    """CLI boundary: report selection errors with the active list, then exit 2."""
    try:
        return load_exam_config(exam, config_path)
    except ExamSelectionError as error:
        print(f"Error: {error}", file=sys.stderr)
        print("Active exams:", file=sys.stderr)
        if error.active_exams:
            for exam_dir in error.active_exams:
                print(f"  - {exam_dir.name}", file=sys.stderr)
        else:
            print("  (none)", file=sys.stderr)
        raise SystemExit(2)


def add_exam_argument(parser: argparse.ArgumentParser, include_config: bool = False) -> None:
    parser.add_argument("--exam", help="Exam folder name or unique active exam number")
    if include_config:
        parser.add_argument("--config", "-c", help="Explicit path to an exam config.json")


def load_exam_config_from_args(args: argparse.Namespace) -> dict:
    return load_exam_config_or_exit(getattr(args, "exam", None), getattr(args, "config", None))


def save_exam_config(config: dict) -> Path:
    """Save an exam config inside its selected folder, omitting runtime metadata."""
    exam_dir = Path(config["exam_dir"])
    config_path = exam_dir / "config.json"
    persisted = dict(config)
    persisted.pop("exam_dir", None)
    with config_path.open("w", encoding="utf-8") as config_stream:
        json.dump(persisted, config_stream, indent=4)
    return config_path
