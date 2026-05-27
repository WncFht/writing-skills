#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

RISKY_FLOAT_RE = re.compile(r"\\begin\{(wrapfigure|wraptable)\}")


@dataclass(frozen=True)
class FloatHit:
    path: Path
    line: int
    env_name: str


@dataclass(frozen=True)
class VisualCheckResult:
    pdf: Path
    preview_dir: Path | None
    rendered_pages: int
    risky_floats: list[FloatHit]
    status: str
    note: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render a few preview pages and scan TeX sources for float patterns "
            "that often break after bilingual inline expansion."
        )
    )
    parser.add_argument("workspace", help="Paper workspace directory.")
    parser.add_argument("pdf", help="Compiled PDF path.")
    parser.add_argument(
        "--pages",
        type=int,
        default=4,
        help="How many leading pages to render for preview.",
    )
    return parser.parse_args()


def line_number_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def collect_tex_files(workspace: Path) -> list[Path]:
    return sorted(path for path in workspace.rglob("*.tex") if path.is_file())


def scan_risky_floats(workspace: Path) -> list[FloatHit]:
    hits: list[FloatHit] = []
    for tex_path in collect_tex_files(workspace):
        text = tex_path.read_text(encoding="utf-8", errors="ignore")
        for match in RISKY_FLOAT_RE.finditer(text):
            hits.append(
                FloatHit(
                    path=tex_path.relative_to(workspace),
                    line=line_number_at(text, match.start()),
                    env_name=match.group(1),
                )
            )
    return hits


def render_preview_pages(
    workspace: Path, pdf_path: Path, *, pages: int
) -> tuple[Path | None, int, str]:
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        return None, 0, "skipped: pdftoppm not found"

    preview_dir = workspace / ".paper_note_visual_check" / pdf_path.stem
    preview_dir.mkdir(parents=True, exist_ok=True)
    output_prefix = preview_dir / "page"
    command = [
        pdftoppm,
        "-png",
        "-f",
        "1",
        "-l",
        str(max(1, pages)),
        str(pdf_path),
        str(output_prefix),
    ]
    result = subprocess.run(
        command,
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        note = (result.stdout + result.stderr).strip() or "pdftoppm failed"
        return preview_dir, 0, f"failed: {note}"

    rendered = len(sorted(preview_dir.glob("page-*.png")))
    return preview_dir, rendered, "rendered" if rendered else "failed: no preview pages"


def run_visual_check(
    workspace: Path, pdf_path: Path, *, pages: int = 4
) -> VisualCheckResult:
    risky_floats = scan_risky_floats(workspace)
    preview_dir, rendered_pages, render_note = render_preview_pages(
        workspace, pdf_path, pages=pages
    )

    status = "ok"
    notes: list[str] = []
    if risky_floats:
        status = "needs_review"
        notes.append("detected wrapfigure/wraptable in TeX sources")
    if render_note != "rendered":
        status = "needs_review" if status == "ok" else status
        notes.append(render_note)
    elif rendered_pages:
        notes.append(f"rendered {rendered_pages} preview pages")

    if not notes:
        notes.append("visual check clean")

    return VisualCheckResult(
        pdf=pdf_path,
        preview_dir=preview_dir,
        rendered_pages=rendered_pages,
        risky_floats=risky_floats,
        status=status,
        note="; ".join(notes),
    )


def result_to_dict(result: VisualCheckResult) -> dict[str, object]:
    return {
        "pdf": str(result.pdf),
        "preview_dir": str(result.preview_dir) if result.preview_dir else None,
        "rendered_pages": result.rendered_pages,
        "risky_floats": [
            {
                "path": hit.path.as_posix(),
                "line": hit.line,
                "env": hit.env_name,
            }
            for hit in result.risky_floats
        ],
        "status": result.status,
        "note": result.note,
    }


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    pdf_path = Path(args.pdf).resolve()
    if not workspace.is_dir():
        raise NotADirectoryError(f"Workspace does not exist: {workspace}")
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF does not exist: {pdf_path}")

    result = run_visual_check(workspace, pdf_path, pages=args.pages)
    print(json.dumps(result_to_dict(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
