#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from latex_compat import ensure_binhex_compat
from lint_annotations import format_issue, lint_workspace
from setup_paper_workspace import (
    ENTRY_FILE_NAME,
    detect_main_tex as detect_setup_main_tex,
    refresh_generated_entry,
)
from visual_check_pdf import run_visual_check

DEFAULT_BUILD_TARGETS = ("paper_note_bilingual.tex",)

RERUN_HINT_RE = re.compile(
    r"Label\(s\) may have changed|Rerun to get cross-references right"
)
WARNING_CATEGORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "undefined citations",
        re.compile(r"(?:Package natbib Warning:\s*)?Citation `[^']+' .* undefined"),
    ),
    (
        "undefined references",
        re.compile(r"(?:LaTeX Warning:\s*)?Reference `[^']+' .* undefined"),
    ),
    (
        "rerun needed",
        re.compile(r"Label\(s\) may have changed|Rerun to get cross-references right"),
    ),
    (
        "headheight too small",
        re.compile(r"Package fancyhdr Warning: \\\\headheight is too small"),
    ),
    (
        "missing image descriptions",
        re.compile(
            r"possible image without description|A possible image without description",
            re.I,
        ),
    ),
)
NOISY_PRE_BIB_WARNING_LABELS = {
    "undefined citations",
    "undefined references",
    "rerun needed",
}


@dataclass(frozen=True)
class CommandResult:
    label: str
    command: list[str]
    output: str


class CommandFailure(RuntimeError):
    def __init__(self, result: CommandResult):
        super().__init__(result.label)
        self.result = result


@dataclass(frozen=True)
class FatalDiagnosis:
    code: str
    summary: list[str]
    advice: list[str]
    should_retry_with_aux_cleanup: bool = False


def detect_main_tex(workspace: Path) -> Path:
    return detect_setup_main_tex(workspace)


def detect_compiler(workspace: Path) -> str:
    readme_path = workspace / "00README.json"
    if not readme_path.exists():
        return "pdflatex"
    data = json.loads(readme_path.read_text(encoding="utf-8"))
    return data.get("process", {}).get("compiler", "pdflatex")


def needs_bibtex(tex_file: Path) -> bool:
    text = tex_file.read_text(encoding="utf-8", errors="ignore")
    return r"\bibliography{" in text or r"\bibliographystyle{" in text


def relative_tex_arg(workspace: Path, tex_file: Path) -> str:
    try:
        return tex_file.relative_to(workspace).as_posix()
    except ValueError:
        return str(tex_file)


def detect_pdf_path(workspace: Path, tex_file: Path) -> Path:
    candidates = [
        tex_file.with_suffix(".pdf"),
        workspace / f"{tex_file.stem}.pdf",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def detect_log_path(workspace: Path, tex_file: Path) -> Path:
    return workspace / f"{tex_file.stem}.paper-note-build.log"


def cleanup_stale_aux_files(
    workspace: Path, tex_file: Path, *, include_aux: bool = False
) -> list[Path]:
    removed: list[Path] = []
    # Preserve the existing .aux file. Some natbib + numeric-bibliography
    # workspaces rely on state written there (for example \NAT@force@numbers)
    # and deleting it makes an otherwise healthy project fail on the next pass.
    for suffix in (".toc", ".lof", ".lot", ".out", ".loc"):
        candidate = workspace / f"{tex_file.stem}{suffix}"
        if candidate.exists():
            candidate.unlink()
            removed.append(candidate)
    if include_aux:
        aux_candidate = workspace / f"{tex_file.stem}.aux"
        if aux_candidate.exists():
            aux_candidate.unlink()
            removed.append(aux_candidate)
    return removed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile the single bilingual paper-note PDF."
    )
    parser.add_argument("workspace", help="Paper workspace directory.")
    parser.add_argument(
        "--tex",
        help="Explicit TeX filename. Defaults to the detected top-level main file.",
    )
    parser.add_argument(
        "--all-outputs",
        action="store_true",
        help=(
            "Compile the default generated entry file. "
            "This is mainly kept for CLI compatibility with older workflows."
        ),
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Only run lint and the first LaTeX preflight pass.",
    )
    parser.add_argument(
        "--refresh-entry",
        action="store_true",
        help=(
            f"Regenerate {ENTRY_FILE_NAME} from the detected top-level TeX file "
            "before lint/build."
        ),
    )
    return parser.parse_args()


def detect_default_build_targets(workspace: Path) -> list[Path]:
    targets = [
        workspace / name
        for name in DEFAULT_BUILD_TARGETS
        if (workspace / name).exists()
    ]
    if targets:
        return targets
    return [detect_main_tex(workspace)]


def detect_requested_targets(workspace: Path, args: argparse.Namespace) -> list[Path]:
    if args.tex:
        tex_file = workspace / args.tex
        if not tex_file.exists():
            raise FileNotFoundError(f"TeX file does not exist: {tex_file}")
        return [tex_file]
    if args.all_outputs:
        return detect_default_build_targets(workspace)
    default_targets = detect_default_build_targets(workspace)
    if len(default_targets) > 1:
        return default_targets
    return default_targets


def maybe_refresh_generated_entry(
    workspace: Path, targets: list[Path], *, force_refresh: bool
) -> dict[str, object] | None:
    entry_path = workspace / ENTRY_FILE_NAME
    if entry_path not in targets:
        return None
    if not entry_path.exists():
        return None

    main_tex = detect_main_tex(workspace)
    needs_refresh = force_refresh
    reason = "requested"
    if not needs_refresh and main_tex.stat().st_mtime > entry_path.stat().st_mtime:
        needs_refresh = True
        reason = "main_tex_newer"
    if not needs_refresh:
        return None

    refresh_result = refresh_generated_entry(workspace, rewrite_note_macros=False)
    refresh_result["reason"] = reason
    return refresh_result


def append_log(log_path: Path, label: str, command: list[str], output: str) -> None:
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"== {label}: {' '.join(command)} ==\n")
        handle.write(output)
        if output and not output.endswith("\n"):
            handle.write("\n")
        handle.write("\n")


def run_command(
    command: list[str], cwd: Path, log_path: Path, label: str
) -> CommandResult:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = result.stdout + result.stderr
    command_result = CommandResult(label=label, command=command, output=output)
    append_log(log_path, label, command, output)
    if result.returncode != 0:
        raise CommandFailure(command_result)
    return command_result


def summarize_warnings(
    outputs: list[str], *, suppress_labels: set[str] | None = None
) -> list[str]:
    combined = "\n".join(outputs)
    summary: list[str] = []
    matched_lines: set[str] = set()
    suppress_labels = suppress_labels or set()
    all_patterns = tuple(pattern for _, pattern in WARNING_CATEGORY_PATTERNS)

    for label, pattern in WARNING_CATEGORY_PATTERNS:
        if label in suppress_labels:
            continue
        count = len(pattern.findall(combined))
        if count:
            suffix = f": {count}" if count > 1 else ""
            summary.append(f"{label}{suffix}")

    fallback_lines: list[str] = []
    for line in combined.splitlines():
        stripped = line.strip()
        if (
            "Warning:" not in stripped
            or "Underfull" in stripped
            or "Overfull" in stripped
        ):
            continue
        if any(pattern.search(stripped) for pattern in all_patterns):
            continue
        if stripped not in matched_lines:
            matched_lines.add(stripped)
            fallback_lines.append(stripped)
    summary.extend(fallback_lines[:5])
    return summary


def summarize_final_warnings(outputs: list[str]) -> list[str]:
    if not outputs:
        return []
    return summarize_warnings([outputs[-1]])


def summarize_quick_warnings(outputs: list[str], *, has_bibtex: bool) -> list[str]:
    if not outputs:
        return []
    suppress_labels = NOISY_PRE_BIB_WARNING_LABELS if has_bibtex else set()
    return summarize_warnings([outputs[-1]], suppress_labels=suppress_labels)


def extract_fatal_summary(output: str) -> list[str]:
    summary: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("! "):
            summary.append(stripped)
        elif re.match(r"l\.\d+", stripped):
            summary.append(stripped)
        if len(summary) >= 4:
            break
    if summary:
        return summary

    tail = [line.strip() for line in output.splitlines() if line.strip()]
    return tail[-4:]


def diagnose_fatal(output: str) -> FatalDiagnosis:
    summary = extract_fatal_summary(output)
    lowered = output.lower()

    if "missing $ inserted" in lowered:
        return FatalDiagnosis(
            code="missing-dollar",
            summary=summary,
            advice=[
                r"优先检查最近改过的 \bgsent / \zh*sent / \zhtrans / \pnote / annsummary 是否写了裸数学宏。",
                r"像 \geq、\approx、\alpha、\mathbb 这类数学命令必须包进 $...$。",
            ],
        )

    if (
        "unicode character" in lowered
        and ("not set up for use with latex" in lowered or "not set up for use with pdftex" in lowered)
    ):
        should_retry = any(token in lowered for token in ("\\end{document}", ".aux", ".out"))
        return FatalDiagnosis(
            code="unicode-moving-argument",
            summary=summary,
            advice=[
                "检测到 Unicode 与 pdflatex 兼容错误；高概率是中文进入了标题、目录、书签或 .aux/.out 回写链路。",
                r"检查 \title、\section、\subsection、\paragraph 等 moving arguments，避免直接写中文或 \section{\bititle{...}{...}}。",
                r"优先改用 \bipapertitle、\bisec、\bisubsec、\bipara 这类安全双语标题宏。",
            ],
            should_retry_with_aux_cleanup=should_retry,
        )

    return FatalDiagnosis(
        code="generic",
        summary=summary,
        advice=[],
    )


def should_rerun_latex(output: str) -> bool:
    return bool(RERUN_HINT_RE.search(output))


def print_warning_summary(summary: list[str]) -> None:
    print("warning_summary:")
    if not summary:
        print("  - clean")
        return
    for item in summary:
        print(f"  - {item}")


def print_fatal_diagnosis(diagnosis: FatalDiagnosis) -> None:
    print("fatal_summary:")
    for line in diagnosis.summary:
        print(f"  - {line}")
    if diagnosis.code != "generic":
        print(f"fatal_kind: {diagnosis.code}")
    if diagnosis.advice:
        print("fatal_advice:")
        for line in diagnosis.advice:
            print(f"  - {line}")


def print_visual_check_summary(workspace: Path, pdf_path: Path) -> None:
    result = run_visual_check(workspace, pdf_path)
    print(f"visual_check_status: {result.status}")
    print(f"visual_check_note: {result.note}")
    if result.preview_dir is not None:
        print(f"visual_check_preview_dir: {result.preview_dir}")
    if result.risky_floats:
        print("visual_check_risky_floats:")
        for hit in result.risky_floats:
            print(f"  - {hit.path.as_posix()}:{hit.line}: {hit.env_name}")


def run_lint_or_exit(workspace: Path) -> int:
    issues, checked_files = lint_workspace(workspace)
    print(f"lint_checked_files: {checked_files}")
    if not issues:
        print("lint_status: clean")
        return 0

    print("lint_status: failed")
    print("lint_issues:")
    for issue in issues:
        print(f"  - {format_issue(issue, workspace)}")
    return 1


def compile_tex_file(
    workspace: Path, tex_file: Path, *, quick: bool
) -> tuple[str, str]:
    tex_arg = relative_tex_arg(workspace, tex_file)
    compiler = detect_compiler(workspace)
    if compiler not in {"pdflatex", "xelatex", "lualatex"}:
        raise ValueError(f"Unsupported compiler in 00README.json: {compiler}")

    print(f"tex: {tex_arg}")
    print(f"mode: {'quick' if quick else 'full'}")

    log_path = detect_log_path(workspace, tex_file)
    log_path.write_text("", encoding="utf-8")
    removed_aux_files = cleanup_stale_aux_files(workspace, tex_file)

    binhex_status = ensure_binhex_compat(workspace)
    compile_args = [
        compiler,
        "-interaction=nonstopmode",
        "-halt-on-error",
        tex_arg,
    ]
    outputs: list[str] = []
    has_bibtex = needs_bibtex(tex_file)
    aux_retry_removed_files: list[Path] = []

    def run_compile_sequence() -> None:
        preflight = run_command(compile_args, workspace, log_path, "latex-preflight")
        outputs.append(preflight.output)

        if quick:
            return

        if has_bibtex:
            bibtex_result = run_command(
                ["bibtex", tex_file.stem],
                workspace,
                log_path,
                "bibtex",
            )
            outputs.append(bibtex_result.output)
            second_pass = run_command(compile_args, workspace, log_path, "latex-pass-2")
            outputs.append(second_pass.output)
            third_pass = run_command(compile_args, workspace, log_path, "latex-pass-3")
            outputs.append(third_pass.output)
            if should_rerun_latex(third_pass.output):
                outputs.append(
                    run_command(
                        compile_args, workspace, log_path, "latex-pass-4"
                    ).output
                )
            return

        second_pass = run_command(compile_args, workspace, log_path, "latex-pass-2")
        outputs.append(second_pass.output)
        if should_rerun_latex(second_pass.output):
            outputs.append(
                run_command(
                    compile_args, workspace, log_path, "latex-pass-3"
                ).output
            )

    try:
        run_compile_sequence()
    except CommandFailure as error:
        diagnosis = diagnose_fatal(error.result.output)
        if diagnosis.should_retry_with_aux_cleanup:
            aux_retry_removed_files = cleanup_stale_aux_files(
                workspace, tex_file, include_aux=True
            )
            outputs.clear()
            append_log(
                log_path,
                "paper-note-recovery",
                ["cleanup-aux-retry"],
                "Detected likely Unicode aux/bookmark state. Removed stale aux files and retried.",
            )
            try:
                run_compile_sequence()
            except CommandFailure as retry_error:
                diagnosis = diagnose_fatal(retry_error.result.output)
                print(f"log: {log_path}")
                print_fatal_diagnosis(diagnosis)
                print_warning_summary(
                    summarize_final_warnings(outputs + [retry_error.result.output])
                )
                if removed_aux_files or aux_retry_removed_files:
                    print("removed_stale_aux:")
                    for path in removed_aux_files + aux_retry_removed_files:
                        print(f"  - {path}")
                print(f"binhex_status: {binhex_status}")
                print(f"status: failed at {retry_error.result.label}")
                return f"failed at {retry_error.result.label}", str(log_path)
        else:
            print(f"log: {log_path}")
            print_fatal_diagnosis(diagnosis)
            print_warning_summary(
                summarize_final_warnings(outputs + [error.result.output])
            )
            print(f"binhex_status: {binhex_status}")
            print(f"status: failed at {error.result.label}")
            return f"failed at {error.result.label}", str(log_path)

    if quick:
        print(f"log: {log_path}")
        if removed_aux_files or aux_retry_removed_files:
            print("removed_stale_aux:")
            for path in removed_aux_files + aux_retry_removed_files:
                print(f"  - {path}")
        print(f"binhex_status: {binhex_status}")
        print_warning_summary(
            summarize_quick_warnings(outputs, has_bibtex=has_bibtex)
        )
        print("status: quick_checked")
        return "quick_checked", str(log_path)

    pdf_path = detect_pdf_path(workspace, tex_file)
    print(f"log: {log_path}")
    if removed_aux_files or aux_retry_removed_files:
        print("removed_stale_aux:")
        for path in removed_aux_files + aux_retry_removed_files:
            print(f"  - {path}")
    print(f"pdf: {pdf_path}")
    print(f"binhex_status: {binhex_status}")
    print_warning_summary(summarize_final_warnings(outputs))
    print_visual_check_summary(workspace, pdf_path)
    print("status: compiled")
    return "compiled", str(pdf_path)


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    if not workspace.is_dir():
        raise NotADirectoryError(f"Workspace does not exist: {workspace}")

    print(f"workspace: {workspace}")
    targets = detect_requested_targets(workspace, args)
    print("targets:")
    for tex_file in targets:
        print(f"  - {relative_tex_arg(workspace, tex_file)}")
    refresh_result = maybe_refresh_generated_entry(
        workspace, targets, force_refresh=args.refresh_entry
    )
    if refresh_result is not None:
        reason = refresh_result["reason"]
        print(
            "entry_refresh:"
            f" {ENTRY_FILE_NAME} regenerated from {Path(refresh_result['main_tex']).name}"
            f" ({reason})"
        )
    else:
        print("entry_refresh: skipped")
    if run_lint_or_exit(workspace) != 0:
        print("status: lint_failed")
        return 1

    overall_status = 0
    for tex_file in targets:
        print("---")
        result, _ = compile_tex_file(workspace, tex_file, quick=args.quick)
        if result.startswith("failed"):
            overall_status = 1
            if not args.all_outputs and not (len(targets) > 1):
                return 1
        elif result == "quick_checked":
            continue
    if overall_status != 0:
        print("status: failed")
        return 1
    print(f"status: {'quick_checked' if args.quick else 'compiled'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
