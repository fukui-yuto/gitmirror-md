"""共通ユーティリティ: slug化、front matter生成、ファイルIO、リンク変換."""

import re
from pathlib import Path

import yaml


def slugify(text: str) -> str:
    """テキストを安全なファイル名に変換する.

    - 小文字化
    - 空白・アンダースコア → -
    - ファイル名禁止文字除去
    - 連続する - を1つに collapse
    - 先頭末尾の - を除去
    - 80文字制限
    """
    s = text.lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r'[<>:"/\\|?*]', "", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-")
    if len(s) > 80:
        s = s[:80].rstrip("-")
    return s


def write_file_if_changed(path: Path, content: str) -> bool:
    """既存ファイルと内容比較し、差分があるときだけ書き込む.

    Returns:
        True if file was written, False if unchanged.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing == content:
            return False
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def dump_front_matter(data: dict) -> str:
    """YAML front matter 文字列を生成する."""
    yml = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return f"---\n{yml}---\n"


def clean_orphaned_files(target_dir: Path, valid_paths: set[Path]) -> list[Path]:
    """target_dir 以下で valid_paths に含まれないファイルを削除する.

    .gitkeep は削除対象外。
    Returns:
        削除したパスのリスト.
    """
    deleted: list[Path] = []
    if not target_dir.exists():
        return deleted
    resolved_valid = {p.resolve() for p in valid_paths}
    for f in target_dir.rglob("*"):
        if f.is_file() and f.name != ".gitkeep" and f.resolve() not in resolved_valid:
            f.unlink()
            deleted.append(f)
    # 空ディレクトリを削除（.gitkeep があるものは除く）
    for d in sorted(target_dir.rglob("*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
            deleted.append(d)
    return deleted


def rewrite_upload_links(content: str, base_url: str, project_path: str) -> str:
    """GitLab の相対アップロードリンクを絶対URLに変換する.

    /uploads/xxx/image.png → {base_url}/{project_path}/uploads/xxx/image.png
    """
    if not content:
        return content
    base = base_url.rstrip("/")
    path = project_path.strip("/")
    # Markdown image/link: [text](/uploads/...) or ![alt](/uploads/...)
    content = re.sub(
        r"(\[.*?\]\()(/uploads/[^)]+)(\))",
        rf"\1{base}/{path}\2\3",
        content,
    )
    # Raw HTML img src="/uploads/..."
    content = re.sub(
        r'(src=")(/uploads/[^"]+)(")',
        rf"\1{base}/{path}\2\3",
        content,
    )
    return content
