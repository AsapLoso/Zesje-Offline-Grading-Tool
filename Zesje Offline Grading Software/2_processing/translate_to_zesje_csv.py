"""Pydantic-standardized translator from AI grading outputs to per-exam Zesje CSV."""
import csv
import json
import os
import sys
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from exam_config import select_exam_config


class StandardizedGradeRow(BaseModel):
    """Canonical Pydantic schema for a single Zesje upload row."""

    case_id: str = Field(min_length=1)
    exam: str = Field(min_length=1)
    vraag: str = Field(min_length=1)
    problem_id: int = Field(ge=1)
    submission_id: int = Field(ge=1)
    adopted_option_ids: List[str] = Field(default_factory=list)
    adopted_points: Optional[float] = Field(default=None, ge=0)
    printed_max: float = Field(ge=0)
    adopted_source: str = Field(default="ai_pipeline")
    zesje_rubric_labels: List[str] = Field(default_factory=list)
    gate9_status: Literal["CLEAN", "FLAGGED", "UNRESOLVED", ""] = ""
    needs_human_review: Literal["YES", "NO"] = "NO"
    review_reasons: str = ""

    @field_validator("adopted_option_ids", "zesje_rubric_labels", mode="before")
    @classmethod
    def split_tokens(cls, v):
        """Accept space/pipe-delimited strings or lists."""
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if v is None or v == "":
            return []
        sep = "|" if "|" in str(v) else None
        return [tok.strip() for tok in str(v).split(sep) if tok.strip()]

    @field_validator("adopted_points", mode="before")
    @classmethod
    def empty_to_none(cls, v):
        """Convert blank CSV cells to None."""
        return None if v in ("", None) else v

    def to_csv_row(self) -> List[str]:
        """Serialize validated row back to zesje_upload_ready.csv format."""
        return [
            self.case_id,
            self.exam,
            self.vraag,
            str(self.problem_id),
            str(self.submission_id),
            " ".join(self.adopted_option_ids),
            "" if self.adopted_points is None else str(int(self.adopted_points) if self.adopted_points.is_integer() else self.adopted_points),
            str(int(self.printed_max) if self.printed_max.is_integer() else self.printed_max),
            self.adopted_source,
            "|".join(self.zesje_rubric_labels),
            self.gate9_status,
            self.needs_human_review,
            self.review_reasons,
        ]


CSV_HEADER = [
    "case_id", "exam", "vraag", "problem_id", "submission_id",
    "adopted_option_ids", "adopted_points", "printed_max", "adopted_source",
    "zesje_rubric_labels", "gate9_status", "needs_human_review", "review_reasons",
]


def load_source_rows(src_path: str):
    """Load rows from CSV or JSONL into dicts for Pydantic validation."""
    if src_path.endswith(".jsonl"):
        with open(src_path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    with open(src_path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def translate_file(src_path: str, out_path: str, exam_filter: Optional[str] = None):
    """Validate all rows with Pydantic and write standardized zesje_upload_ready.csv."""
    raw_rows = load_source_rows(src_path)
    validated: List[StandardizedGradeRow] = []
    for raw in raw_rows:
        if exam_filter and raw.get("exam") != exam_filter:
            continue
        validated.append(StandardizedGradeRow.model_validate(raw))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        for item in validated:
            writer.writerow(item.to_csv_row())
    print(f"[OK] Validated and wrote {len(validated)} rows -> {out_path}")


def main():
    config, data_dir = select_exam_config(REPO_ROOT)
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO_ROOT, "zesje_upload_ready.csv")
    exam_filter = config.get("pipeline_exam_name") or (f"exam_{config['exam_id']}" if config.get("exam_id") else None)
    out = os.path.join(data_dir, "zesje_upload_ready.csv")
    translate_file(src, out, exam_filter=exam_filter)


if __name__ == "__main__":
    main()
