#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

NOTE_COMMAND_NAME = "pnote"
PREAMBLE_FILE_NAME = "paper_note_annotations.tex"
ENTRY_FILE_NAME = "paper_note_bilingual.tex"
LEGACY_ENTRY_FILE_NAMES = (
    "paper_note_english.tex",
    "paper_note_english_clean.tex",
    "paper_note_chinese.tex",
)
LEGACY_GENERATED_DIR_NAMES = ("paper_note_zh",)
GENERATED_ENTRY_FILE_NAMES = (ENTRY_FILE_NAME,)
CURRENT_GENERATED_FILE_NAMES = {
    PREAMBLE_FILE_NAME,
    *GENERATED_ENTRY_FILE_NAMES,
}
ALL_GENERATED_FILE_NAMES = {
    *CURRENT_GENERATED_FILE_NAMES,
    *LEGACY_ENTRY_FILE_NAMES,
}
DEFAULT_PREAMBLE = (
    r"""
\makeatletter
\@ifpackageloaded{tcolorbox}{\tcbuselibrary{breakable,skins}}{\usepackage[most]{tcolorbox}}
\@ifundefined{todo}{}{\let\papernote@orig@todo\todo\let\todo\relax}
\@ifundefined{comment}{}{\let\papernote@orig@comment\comment\let\comment\relax}
\@ifundefined{endcomment}{}{\let\papernote@orig@endcomment\endcomment\let\endcomment\relax}
\@ifundefined{remark}{}{\let\papernote@orig@remark\remark\let\remark\relax}
\@ifundefined{endremark}{}{\let\papernote@orig@endremark\endremark\let\endremark\relax}
\@ifundefined{note}{}{\let\papernote@orig@note\note\let\note\relax}
\@ifpackageloaded{changes}{}{\usepackage[draft,highlightmarkup=uwave,commentmarkup=footnote,authormarkup=none,commandnameprefix=always]{changes}}
\@ifundefined{papernote@orig@todo}{}{\let\todo\papernote@orig@todo}
\@ifundefined{papernote@orig@comment}{}{\let\comment\papernote@orig@comment}
\@ifundefined{papernote@orig@endcomment}{}{\let\endcomment\papernote@orig@endcomment}
\@ifundefined{papernote@orig@remark}{}{\let\remark\papernote@orig@remark}
\@ifundefined{papernote@orig@endremark}{}{\let\endremark\papernote@orig@endremark}
\@ifundefined{papernote@orig@note}{}{\let\note\papernote@orig@note}
\@ifpackageloaded{CJKutf8}{}{\usepackage{CJKutf8}}
\@ifpackageloaded{hyperref}{\hypersetup{hidelinks}}{}
\providecommand{\texorpdfstring}[2]{#1}
\makeatother

\definecolor{FuncBg}{RGB}{52,101,164}
\definecolor{FuncGap}{RGB}{117,80,123}
\definecolor{FuncQuestion}{RGB}{173,62,122}
\definecolor{FuncMethod}{RGB}{46,125,50}
\definecolor{FuncResult}{RGB}{230,145,56}
\definecolor{FuncClaim}{RGB}{180,40,40}
\definecolor{FuncStruct}{RGB}{120,120,120}
\definecolor{FuncRelated}{RGB}{45,126,145}
\definecolor{FuncKey}{RGB}{180,140,24}
\definecolor{NoteEvalLabel}{RGB}{148,88,34}
\definecolor{NoteEvalText}{RGB}{92,68,46}
\definecolor{TransText}{RGB}{62,62,62}

\newif\ifannotnotes
\annotnotestrue

% Guardrail: keep \footnote / \footnotemark outside sentence color macros such as
% \bgsent{...} or \methodsent{...}; append the footnote command after the macro.
\newcommand{\bgsent}[1]{\chadded{\textcolor{FuncBg}{#1}}}
\newcommand{\gapsent}[1]{\chadded{\textcolor{FuncGap}{#1}}}
\newcommand{\questionsent}[1]{\chadded{\textcolor{FuncQuestion}{#1}}}
\newcommand{\methodsent}[1]{\chadded{\textcolor{FuncMethod}{#1}}}
\newcommand{\resultsent}[1]{\chadded{\textcolor{FuncResult}{#1}}}
\newcommand{\claimsent}[1]{\chadded{\textcolor{FuncClaim}{#1}}}
\newcommand{\structsent}[1]{\chadded{\textcolor{FuncStruct}{#1}}}
\newcommand{\relatedsent}[1]{\chadded{\textcolor{FuncRelated}{#1}}}
\newcommand{\keysent}[1]{\textcolor{FuncKey}{\textbf{[重点]}}\hspace{0.15em}#1}
\newcommand{\papernotezhinline}[1]{\ifhmode\hspace{0.35em}\fi{\small\chadded{#1}}}
\newcommand{\zhtrans}[1]{%
  \papernotezhinline{\textcolor{TransText}{#1}}%
}
\newcommand{\zhbgsent}[1]{\papernotezhinline{\textcolor{FuncBg}{#1}}}
\newcommand{\zhgapsent}[1]{\papernotezhinline{\textcolor{FuncGap}{#1}}}
\newcommand{\zhquestionsent}[1]{\papernotezhinline{\textcolor{FuncQuestion}{#1}}}
\newcommand{\zhmethodsent}[1]{\papernotezhinline{\textcolor{FuncMethod}{#1}}}
\newcommand{\zhresultsent}[1]{\papernotezhinline{\textcolor{FuncResult}{#1}}}
\newcommand{\zhclaimsent}[1]{\papernotezhinline{\textcolor{FuncClaim}{#1}}}
\newcommand{\zhstructsent}[1]{\papernotezhinline{\textcolor{FuncStruct}{#1}}}
\newcommand{\zhrelatedsent}[1]{\papernotezhinline{\textcolor{FuncRelated}{#1}}}
\newcommand{\zhkeysent}[1]{\papernotezhinline{\textcolor{FuncKey}{\textbf{[重点]}}\hspace{0.15em}#1}}
\newcommand{\bititle}[2]{\texorpdfstring{#1\\{\normalfont\small #2}}{#1 / #2}}
\newcommand{\papernotezhtitle}{}
\newcommand{\papernotezhheading}[1]{\par\noindent{\normalfont\small #1}\par}
\newcommand{\bipapertitle}[2]{\title{#1}\gdef\papernotezhtitle{#2}}
\newcommand{\printzhpapertitle}{%
  \begin{center}
  \small \papernotezhtitle
  \end{center}
}
\newcommand{\bipart}[2]{\part[#1]{\bititle{#1}{#2}}}
\newcommand{\bichapter}[2]{\chapter[#1]{\bititle{#1}{#2}}}
\newcommand{\bisec}[2]{\section[#1]{\bititle{#1}{#2}}}
\newcommand{\bisubsec}[2]{\subsection[#1]{\bititle{#1}{#2}}}
\newcommand{\bisubsubsec}[2]{\subsubsection[#1]{\bititle{#1}{#2}}}
\newcommand{\bipara}[2]{\paragraph[#1]{\bititle{#1}{#2}}}
\newcommand{\bisubpara}[2]{\subparagraph[#1]{\bititle{#1}{#2}}}
\newcommand{\bipartstar}[2]{\part*{#1}\papernotezhheading{#2}}
\newcommand{\bichapterstar}[2]{\chapter*{#1}\papernotezhheading{#2}}
\newcommand{\bisecstar}[2]{\section*{#1}\papernotezhheading{#2}}
\newcommand{\bisubsecstar}[2]{\subsection*{#1}\papernotezhheading{#2}}
\newcommand{\bisubsubsecstar}[2]{\subsubsection*{#1}\papernotezhheading{#2}}
\newcommand{\biparastar}[2]{\paragraph*{#1}\papernotezhheading{#2}}
\newcommand{\bisubparastar}[2]{\subparagraph*{#1}\papernotezhheading{#2}}
\newcommand{\annmarker}{\textcolor{FuncStruct}{\textsuperscript{[注]}}}
\newcommand{\annevalline}[1]{\\[-0.15em]{\textcolor{NoteEvalLabel}{\textbf{评：}}}\ {\textcolor{NoteEvalText}{#1}}}
\newcommand{\pnote}[2]{%
  \ifannotnotes
  \ifhmode\hspace{0.1em}\fi
  \annmarker
  \footnote{\textbf{【#1】}\annevalline{#2}}%
  \fi
}

\newtcolorbox{annsummary}[1][]{
  enhanced,
  breakable,
  colback=FuncStruct!4,
  colframe=FuncStruct,
  boxrule=0.5pt,
  arc=2pt,
  left=6pt,
  right=6pt,
  top=5pt,
  bottom=5pt,
  title={章节总评},
  fonttitle=\small,
  #1
}
""".strip()
    + "\n"
)

GENERATED_LINE_MARKERS = {
    rf"\input{{{PREAMBLE_FILE_NAME}}}",
    r"\annotnotestrue",
    r"\annotnotesfalse",
    r"\begin{CJK*}{UTF8}{gbsn}",
    r"\end{CJK*}",
    r"\setcounter{footnote}{0}",
    r"\renewcommand{\thefootnote}{\arabic{footnote}}",
}
LEGACY_ANNNOTE_RE = re.compile(r"\\annnote(?=\s*\{)")
LEGACY_PNOTE_RE = re.compile(r"\\pnote(?=\s*\{)")


def detect_main_tex(workspace: Path) -> Path:
    readme_path = workspace / "00README.json"
    if readme_path.exists():
        data = json.loads(readme_path.read_text(encoding="utf-8"))
        for source in data.get("sources", []):
            if source.get("usage") == "toplevel":
                candidate = workspace / source["filename"]
                if candidate.exists():
                    return candidate

    main_tex = workspace / "main.tex"
    if main_tex.exists():
        return main_tex

    tex_files = sorted(workspace.glob("*.tex"))
    for candidate in tex_files:
        text = candidate.read_text(encoding="utf-8", errors="ignore")
        if r"\documentclass" in text and r"\begin{document}" in text:
            return candidate
    raise FileNotFoundError(f"Could not detect top-level TeX file under {workspace}")


def parse_braced_group(text: str, start: int) -> tuple[str, int] | None:
    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text) or text[index] != "{":
        return None

    depth = 0
    group_start = index + 1
    cursor = index
    while cursor < len(text):
        char = text[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[group_start:cursor], cursor + 1
        cursor += 1
    return None


def parse_command_call(
    text: str, start: int, command_name: str, arg_count: int
) -> tuple[tuple[str, ...], int] | None:
    if not text.startswith("\\" + command_name, start):
        return None
    cursor = start + len(command_name) + 1
    args: list[str] = []
    for _ in range(arg_count):
        parsed = parse_braced_group(text, cursor)
        if parsed is None:
            return None
        value, cursor = parsed
        args.append(value)
    return tuple(args), cursor


def rewrite_legacy_note_macros(text: str) -> str:
    rewritten: list[str] = []
    cursor = 0
    while cursor < len(text):
        annnote_match = LEGACY_ANNNOTE_RE.search(text, cursor)
        pnote_match = LEGACY_PNOTE_RE.search(text, cursor)
        matches = [match for match in (annnote_match, pnote_match) if match is not None]
        if not matches:
            rewritten.append(text[cursor:])
            break

        match = min(matches, key=lambda item: item.start())
        rewritten.append(text[cursor : match.start()])
        if match.re is LEGACY_ANNNOTE_RE:
            parsed = parse_command_call(text, match.start(), "annnote", 4)
            if parsed is None:
                rewritten.append(text[match.start() : match.end()])
                cursor = match.end()
                continue
            args, cursor = parsed
            rewritten.append(
                rf"\{NOTE_COMMAND_NAME}{{{args[0]}|{args[1]}}}{{{args[3]}}}"
            )
            continue

        parsed_three = parse_command_call(text, match.start(), NOTE_COMMAND_NAME, 3)
        if parsed_three is not None:
            args, cursor = parsed_three
            rewritten.append(rf"\{NOTE_COMMAND_NAME}{{{args[0]}}}{{{args[2]}}}")
            continue

        parsed_two = parse_command_call(text, match.start(), NOTE_COMMAND_NAME, 2)
        if parsed_two is not None:
            _, cursor = parsed_two
            rewritten.append(text[match.start() : cursor])
            continue

        rewritten.append(text[match.start() : match.end()])
        cursor = match.end()
    return "".join(rewritten)


def strip_note_macros(text: str) -> str:
    stripped: list[str] = []
    cursor = 0
    while cursor < len(text):
        annnote_match = LEGACY_ANNNOTE_RE.search(text, cursor)
        pnote_match = LEGACY_PNOTE_RE.search(text, cursor)
        matches = [match for match in (annnote_match, pnote_match) if match is not None]
        if not matches:
            stripped.append(text[cursor:])
            break

        match = min(matches, key=lambda item: item.start())
        stripped.append(text[cursor : match.start()])
        if match.re is LEGACY_ANNNOTE_RE:
            parsed = parse_command_call(text, match.start(), "annnote", 4)
            if parsed is None:
                stripped.append(text[match.start() : match.end()])
                cursor = match.end()
                continue
            _, cursor = parsed
            continue

        parsed_three = parse_command_call(text, match.start(), NOTE_COMMAND_NAME, 3)
        if parsed_three is not None:
            _, cursor = parsed_three
            continue

        parsed_two = parse_command_call(text, match.start(), NOTE_COMMAND_NAME, 2)
        if parsed_two is not None:
            _, cursor = parsed_two
            continue

        stripped.append(text[match.start() : match.end()])
        cursor = match.end()
    return "".join(stripped)


def sanitize_main_text(text: str) -> str:
    trailing_newline = text.endswith("\n")
    kept_lines = [
        line for line in text.splitlines() if line.strip() not in GENERATED_LINE_MARKERS
    ]
    sanitized = "\n".join(kept_lines)
    if trailing_newline:
        sanitized += "\n"
    return sanitized


def ensure_annotation_preamble(text: str, *, notes_enabled: bool) -> str:
    marker_line = rf"\input{{{PREAMBLE_FILE_NAME}}}"
    toggle_line = r"\annotnotestrue" if notes_enabled else r"\annotnotesfalse"
    if marker_line in text:
        text = text.replace(marker_line, "").replace("\n\n\n", "\n\n")
    if toggle_line not in text:
        text = text.replace(
            r"\begin{document}",
            toggle_line + "\n" + r"\begin{document}",
            1,
        )
    if marker_line in text:
        return text

    insertion_markers = (
        r"\bipapertitle{",
        r"\title{",
        r"\begin{abstract}",
        r"\begin{document}",
    )
    for marker in insertion_markers:
        if marker in text:
            return text.replace(marker, marker_line + "\n" + marker, 1)
    raise ValueError(
        "Top-level TeX file does not contain a supported insertion marker for "
        "\\input{paper_note_annotations.tex}"
    )


def ensure_cjk_wrapper(text: str) -> str:
    if r"\begin{CJK*}" not in text:
        text = text.replace(
            r"\begin{document}", "\\begin{document}\n\\begin{CJK*}{UTF8}{gbsn}", 1
        )
    if r"\end{CJK*}" not in text:
        text = text.replace(r"\end{document}", "\\end{CJK*}\n\\end{document}", 1)
    return text


def maybe_reset_footnotes(text: str) -> str:
    if (
        r"\maketitle" not in text
        or r"\renewcommand{\thefootnote}{\arabic{footnote}}" in text
    ):
        return text
    reset = (
        "\\maketitle\n"
        "\\setcounter{footnote}{0}\n"
        "\\renewcommand{\\thefootnote}{\\arabic{footnote}}"
    )
    return text.replace(r"\maketitle", reset, 1)


def build_entry_text(text: str, *, notes_enabled: bool) -> str:
    entry = sanitize_main_text(text)
    entry = ensure_annotation_preamble(entry, notes_enabled=notes_enabled)
    entry = ensure_cjk_wrapper(entry)
    entry = maybe_reset_footnotes(entry)
    return entry


def is_legacy_generated_path(relative_posix: str) -> bool:
    return any(
        relative_posix == dir_name or relative_posix.startswith(dir_name + "/")
        for dir_name in LEGACY_GENERATED_DIR_NAMES
    )


def rewrite_workspace_note_macros(workspace: Path) -> list[Path]:
    modified: list[Path] = []
    for tex_path in sorted(workspace.rglob("*.tex")):
        if not tex_path.is_file():
            continue
        relative_posix = tex_path.relative_to(workspace).as_posix()
        if is_legacy_generated_path(relative_posix):
            continue
        if tex_path.name in ALL_GENERATED_FILE_NAMES:
            continue
        original = tex_path.read_text(encoding="utf-8", errors="ignore")
        rewritten = rewrite_legacy_note_macros(original)
        if rewritten != original:
            tex_path.write_text(rewritten, encoding="utf-8")
            modified.append(tex_path)
    return modified


def detect_existing_generated_paths(workspace: Path) -> list[Path]:
    candidates = [workspace / PREAMBLE_FILE_NAME]
    candidates.extend(workspace / name for name in GENERATED_ENTRY_FILE_NAMES)
    candidates.extend(workspace / name for name in LEGACY_ENTRY_FILE_NAMES)
    candidates.extend(workspace / name for name in LEGACY_GENERATED_DIR_NAMES)
    return [path for path in candidates if path.exists()]


def remove_generated_paths(paths: list[Path]) -> list[Path]:
    removed: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(path)
    return removed


def parse_notes_enabled(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    lowered = value.strip().lower()
    if lowered == "on":
        return True
    if lowered == "off":
        return False
    raise ValueError(f"Unsupported notes toggle: {value}")


def read_existing_notes_enabled(entry_path: Path) -> bool | None:
    if not entry_path.exists():
        return None
    text = entry_path.read_text(encoding="utf-8", errors="ignore")
    if r"\annotnotestrue" in text:
        return True
    if r"\annotnotesfalse" in text:
        return False
    return None


def refresh_generated_entry(
    workspace: Path,
    *,
    notes_enabled: bool | None = None,
    rewrite_note_macros: bool = False,
) -> dict[str, object]:
    main_tex = detect_main_tex(workspace)
    entry_path = workspace / ENTRY_FILE_NAME
    preamble_path = workspace / PREAMBLE_FILE_NAME

    if notes_enabled is None:
        inferred_notes_enabled = read_existing_notes_enabled(entry_path)
        notes_enabled = (
            True if inferred_notes_enabled is None else inferred_notes_enabled
        )

    upgraded_files: list[Path] = []
    if rewrite_note_macros:
        upgraded_files = rewrite_workspace_note_macros(workspace)

    preamble_path.write_text(DEFAULT_PREAMBLE, encoding="utf-8")
    normalized_main_text = main_tex.read_text(encoding="utf-8", errors="ignore")
    entry_path.write_text(
        build_entry_text(normalized_main_text, notes_enabled=notes_enabled),
        encoding="utf-8",
    )
    return {
        "main_tex": main_tex,
        "entry_path": entry_path,
        "preamble_path": preamble_path,
        "notes_enabled": notes_enabled,
        "upgraded_files": upgraded_files,
    }


def prepare_workspace(
    workspace: Path, *, force: bool, notes_enabled: bool
) -> dict[str, object]:
    existing_generated_paths = detect_existing_generated_paths(workspace)
    if existing_generated_paths and not force:
        existing_text = "\n".join(f"  - {path}" for path in existing_generated_paths)
        raise FileExistsError(
            "Generated paper-note files already exist:\n"
            f"{existing_text}\n"
            "Re-run with --force if you really want to overwrite them."
        )
    removed_generated_paths = (
        remove_generated_paths(existing_generated_paths) if force else []
    )
    refresh_result = refresh_generated_entry(
        workspace,
        notes_enabled=notes_enabled,
        rewrite_note_macros=True,
    )
    refresh_result["removed_generated_paths"] = removed_generated_paths
    return refresh_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare the original LaTeX workspace for a single bilingual paper-note output."
    )
    parser.add_argument(
        "workspace", help="Paper workspace directory created from arXiv source."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite generated paper-note files if they already exist.",
    )
    parser.add_argument(
        "--notes",
        choices=("on", "off"),
        default="on",
        help="Whether the generated bilingual entry enables function-block pnotes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    if not workspace.is_dir():
        raise NotADirectoryError(f"Workspace does not exist: {workspace}")
    refresh_result = prepare_workspace(
        workspace,
        force=args.force,
        notes_enabled=parse_notes_enabled(args.notes),
    )
    removed_generated_paths = refresh_result["removed_generated_paths"]
    main_tex = refresh_result["main_tex"]
    upgraded_files = refresh_result["upgraded_files"]

    print(f"workspace: {workspace}")
    print(f"main_tex: {main_tex.name}")
    print(f"annotation_support: {PREAMBLE_FILE_NAME}")
    print("entry_files:")
    for file_name in GENERATED_ENTRY_FILE_NAMES:
        print(f"  - {file_name}")
    print(
        r"paired_translation_macros: \zhbgsent \zhgapsent \zhquestionsent "
        r"\zhmethodsent \zhresultsent \zhclaimsent \zhstructsent \zhrelatedsent \zhkeysent"
    )
    print(
        r"fallback_translation_macro: \zhtrans{...} (only for non-sentence or non-functional translated text)"
    )
    print(f"notes_enabled: {'on' if refresh_result['notes_enabled'] else 'off'}")
    print(
        r"notes_toggle: change \annotnotestrue / \annotnotesfalse in the entry file if needed"
    )
    if removed_generated_paths:
        print("removed_generated:")
        for path in removed_generated_paths:
            print(f"  - {path.relative_to(workspace)}")
    print("upgraded_note_files:")
    if upgraded_files:
        for path in upgraded_files:
            print(f"  - {path.relative_to(workspace).as_posix()}")
    else:
        print("  - none")
    print("status: prepared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
