#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import tarfile
import unicodedata
from html import unescape
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from latex_compat import ensure_binhex_compat

ARXIV_ID_RE = re.compile(r"(?P<base>\d{4}\.\d{4,5})(?P<version>v\d+)?", re.I)
TITLE_RE = re.compile(
    r'<h1[^>]*class=["\']title\s+mathjax["\'][^>]*>(.*?)</h1>', re.I | re.S
)
META_TITLE_RE = re.compile(
    r'<meta[^>]+name=["\']citation_title["\'][^>]+content=["\'](.*?)["\']', re.I | re.S
)
INVALID_PATH_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
WHITESPACE_RE = re.compile(r"\s+")
MAX_TITLE_SLUG_CHARS = 140
USER_AGENT = "paper-note-skill"
DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "paper"
COMMENT_LINE_RE = re.compile(r"^\s*%(?!\s*![Tt][Ee][Xx]\b).*$", re.M)
BEGIN_ENV_RE = re.compile(r"\\begin\{([^}]+)\}")
END_ENV_RE = re.compile(r"\\end\{([^}]+)\}")
PROTECTED_ENVIRONMENTS = {
    "verbatim",
    "Verbatim",
    "BVerbatim",
    "lstlisting",
    "minted",
    "filecontents",
    "filecontents*",
}
MATH_ENVIRONMENTS = {
    "align",
    "align*",
    "aligned",
    "alignedat",
    "alignedat*",
    "equation",
    "equation*",
    "gather",
    "gather*",
    "gathered",
    "multline",
    "multline*",
    "split",
    "flalign",
    "flalign*",
}


def extract_arxiv_id(text: str) -> tuple[str, Optional[str]]:
    match = ARXIV_ID_RE.search(text)
    if match:
        return match.group("base"), match.group("version")
    path = urlparse(text).path
    match = ARXIV_ID_RE.search(path)
    if match:
        return match.group("base"), match.group("version")
    raise ValueError(f"Could not parse arXiv ID from input: {text}")


def http_get(url: str, timeout: int = 30) -> requests.Response:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response


def fetch_arxiv_abs_html(paper_id: str) -> str:
    return http_get(f"https://arxiv.org/abs/{paper_id}").text


def parse_latest_version(base_id: str, html: str) -> Optional[str]:
    candidates = re.findall(rf"{re.escape(base_id)}v(\d+)", html)
    if candidates:
        return f"v{max(int(x) for x in candidates)}"
    match = re.search(r"this version,\s*v(\d+)", html, re.I)
    if match:
        return f"v{match.group(1)}"
    return None


def parse_arxiv_title(html: str) -> Optional[str]:
    match = TITLE_RE.search(html) or META_TITLE_RE.search(html)
    if not match:
        return None
    title = re.sub(r"<[^>]+>", " ", match.group(1))
    title = unescape(title)
    title = re.sub(r"^\s*Title:\s*", "", title, flags=re.I)
    title = WHITESPACE_RE.sub(" ", title).strip()
    return title or None


def sanitize_title_for_path(title: Optional[str]) -> str:
    if not title:
        return ""
    normalized = unicodedata.normalize("NFKC", title)
    normalized = INVALID_PATH_CHARS_RE.sub(" ", normalized)
    normalized = normalized.replace("'", "").replace("`", "")
    slug = WHITESPACE_RE.sub("_", normalized).strip(" ._-")
    if len(slug) > MAX_TITLE_SLUG_CHARS:
        slug = slug[:MAX_TITLE_SLUG_CHARS].rstrip(" ._-")
    return slug


def build_workspace_name(arxiv_id: str, title: Optional[str]) -> str:
    slug = sanitize_title_for_path(title)
    return f"{arxiv_id}_{slug}" if slug else arxiv_id


def ensure_workspace(root: Path, arxiv_id: str, title: Optional[str]) -> Path:
    desired = root / build_workspace_name(arxiv_id, title)
    if desired.exists():
        return desired
    matches = sorted(path for path in root.glob(f"{arxiv_id}_*") if path.is_dir())
    if len(matches) == 1:
        return matches[0]
    desired.mkdir(parents=True, exist_ok=True)
    return desired


def safe_extract_tar(tar_path: Path, out_dir: Path) -> None:
    with tarfile.open(tar_path, "r:*") as archive:
        members = []
        for member in archive.getmembers():
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                continue
            members.append(member)
        archive.extractall(out_dir, members=members)


def update_env_stack(line: str, stack: list[str], tracked_envs: set[str]) -> None:
    for env in BEGIN_ENV_RE.findall(line):
        if env in tracked_envs:
            stack.append(env)
    for env in END_ENV_RE.findall(line):
        if stack and stack[-1] == env:
            stack.pop()
        elif env in stack:
            stack.remove(env)


def preprocess_latex_text(text: str) -> tuple[str, int, int]:
    lines = text.splitlines()
    output: list[str] = []
    protected_stack: list[str] = []
    math_stack: list[str] = []
    pending_blank = False
    removed_comment_lines = 0
    collapsed_blank_lines = 0

    for line in lines:
        if protected_stack:
            output.append(line)
            update_env_stack(line, protected_stack, PROTECTED_ENVIRONMENTS)
            continue

        if COMMENT_LINE_RE.match(line):
            removed_comment_lines += 1
            continue

        if line.strip() == "":
            if math_stack:
                collapsed_blank_lines += 1
                continue
            if output:
                if pending_blank:
                    collapsed_blank_lines += 1
                pending_blank = True
            continue

        if pending_blank:
            output.append("")
            pending_blank = False

        output.append(line)
        update_env_stack(line, protected_stack, PROTECTED_ENVIRONMENTS)
        update_env_stack(line, math_stack, MATH_ENVIRONMENTS)

    return "\n".join(output) + "\n", removed_comment_lines, collapsed_blank_lines


def preprocess_latex_sources(root: Path) -> tuple[int, int, int]:
    changed_files = 0
    removed_comment_lines = 0
    collapsed_blank_lines = 0
    for tex_path in root.rglob("*.tex"):
        original = tex_path.read_text(encoding="utf-8", errors="ignore")
        cleaned, removed_count, collapsed_count = preprocess_latex_text(original)
        if cleaned != original:
            tex_path.write_text(cleaned, encoding="utf-8")
            changed_files += 1
        removed_comment_lines += removed_count
        collapsed_blank_lines += collapsed_count
    return changed_files, removed_comment_lines, collapsed_blank_lines


def fetch_metadata(input_text: str) -> tuple[str, str, Optional[str]]:
    base_id, version = extract_arxiv_id(input_text)
    paper_id = f"{base_id}{version or ''}"
    html = fetch_arxiv_abs_html(paper_id)
    latest = version or parse_latest_version(base_id, html)
    title = parse_arxiv_title(html)
    paper_id_with_version = f"{base_id}{latest}" if latest else base_id
    return base_id, paper_id_with_version, title


def fetch_source_to_workspace(
    input_text: str, *, root: Path
) -> dict[str, object]:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)

    arxiv_id, paper_id_with_version, title = fetch_metadata(input_text)
    workspace = ensure_workspace(root, arxiv_id, title)
    tar_path = workspace / "source.tar"
    src_url = f"https://arxiv.org/src/{paper_id_with_version}"

    response = http_get(src_url, timeout=60)
    tar_path.write_bytes(response.content)
    try:
        safe_extract_tar(tar_path, workspace)
    finally:
        if tar_path.exists():
            tar_path.unlink()
    stripped_files, removed_comment_lines, collapsed_blank_lines = (
        preprocess_latex_sources(workspace)
    )
    binhex_status = ensure_binhex_compat(workspace)
    return {
        "workspace": workspace,
        "paper_id_with_version": paper_id_with_version,
        "source_url": src_url,
        "preprocessed_tex_files": stripped_files,
        "removed_comment_lines": removed_comment_lines,
        "collapsed_blank_lines": collapsed_blank_lines,
        "binhex_status": binhex_status,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download arXiv source tarball, extract it directly into "
            "{arxiv_id}_{title}/, and delete the tarball afterwards."
        )
    )
    parser.add_argument(
        "input",
        help="arXiv abs URL, pdf URL, or arXiv ID such as 2604.13737 / 2604.13737v1",
    )
    parser.add_argument(
        "--root",
        default=str(DEFAULT_ROOT),
        help="Root directory where {arxiv_id}_{title}/ will be created.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = fetch_source_to_workspace(args.input, root=Path(args.root))

    print(f"workspace: {result['workspace']}")
    print(f"paper_id_with_version: {result['paper_id_with_version']}")
    print(f"source_url: {result['source_url']}")
    print(f"preprocessed_tex_files: {result['preprocessed_tex_files']}")
    print(f"removed_comment_lines: {result['removed_comment_lines']}")
    print(f"collapsed_blank_lines: {result['collapsed_blank_lines']}")
    print(f"binhex_status: {result['binhex_status']}")
    print("status: extracted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
