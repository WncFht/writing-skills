#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_paper_pdf import main as build_main
from fetch_arxiv_source import DEFAULT_ROOT, fetch_source_to_workspace
from lint_annotations import lint_workspace
from setup_paper_workspace import parse_notes_enabled, prepare_workspace


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the end-to-end paper-note workflow: fetch arXiv source, "
            "prepare the bilingual workspace, lint, quick build, and full build."
        )
    )
    parser.add_argument(
        "input",
        help="arXiv abs URL, pdf URL, or arXiv ID such as 2604.13737 / 2604.13737v1",
    )
    parser.add_argument(
        "--root",
        default=str(DEFAULT_ROOT),
        help="Root directory where the paper workspace will be created or reused.",
    )
    parser.add_argument(
        "--notes",
        choices=("on", "off"),
        default="on",
        help="Whether the generated bilingual entry enables function-block pnotes.",
    )
    parser.add_argument(
        "--force-setup",
        action="store_true",
        help="Overwrite existing generated paper-note files during setup.",
    )
    parser.add_argument(
        "--skip-full-build",
        action="store_true",
        help="Stop after lint + quick build, without running the full compile.",
    )
    return parser.parse_args()


def run_build_stage(workspace: Path, *, quick: bool) -> None:
    argv = [
        "build_paper_pdf.py",
        str(workspace),
        "--tex",
        "paper_note_bilingual.tex",
        "--refresh-entry",
    ]
    if quick:
        argv.insert(2, "--quick")
    saved_argv = sys.argv
    try:
        sys.argv = argv
        raise_code = build_main()
    finally:
        sys.argv = saved_argv
    if raise_code != 0:
        raise SystemExit(raise_code)


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    print("stage: fetch_source")
    fetch_result = fetch_source_to_workspace(args.input, root=root)
    workspace = Path(fetch_result["workspace"]).resolve()
    print(f"workspace: {workspace}")
    print(f"paper_id_with_version: {fetch_result['paper_id_with_version']}")
    print(f"source_url: {fetch_result['source_url']}")
    print(f"preprocessed_tex_files: {fetch_result['preprocessed_tex_files']}")
    print(f"removed_comment_lines: {fetch_result['removed_comment_lines']}")
    print(f"collapsed_blank_lines: {fetch_result['collapsed_blank_lines']}")
    print(f"binhex_status: {fetch_result['binhex_status']}")

    print("stage: setup_workspace")
    setup_result = prepare_workspace(
        workspace,
        force=args.force_setup,
        notes_enabled=parse_notes_enabled(args.notes),
    )
    print(f"main_tex: {Path(setup_result['main_tex']).name}")
    print(f"notes_enabled: {'on' if setup_result['notes_enabled'] else 'off'}")
    print("entry_file: paper_note_bilingual.tex")

    print("stage: lint")
    lint_issues, checked_files = lint_workspace(workspace)
    print(f"lint_checked_files: {checked_files}")
    if lint_issues:
        print("lint_status: failed")
        for issue in lint_issues:
            print(f"  - {issue.path.relative_to(workspace).as_posix()}:{issue.line}: [{issue.kind}] {issue.message}")
        return 1
    print("lint_status: clean")

    print("stage: quick_build")
    run_build_stage(workspace, quick=True)

    if args.skip_full_build:
        print("stage: full_build")
        print("status: skipped")
        print("pipeline_status: quick_checked")
        return 0

    print("stage: full_build")
    run_build_stage(workspace, quick=False)
    print("pipeline_status: compiled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
