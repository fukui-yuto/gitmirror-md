"""Issue を docs/issues/ に同期する."""

import logging
import os
from pathlib import Path

from scripts.common import (
    clean_orphaned_files,
    dump_front_matter,
    rewrite_upload_links,
    slugify,
    write_file_if_changed,
)
from scripts.gitlab_client import get_project, retry_on_rate_limit

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

DOCS_ISSUES_DIR = Path("docs/issues")
OPEN_DIR = DOCS_ISSUES_DIR / "open"
CLOSED_DIR = DOCS_ISSUES_DIR / "closed"


@retry_on_rate_limit
def _list_issues(project):
    return project.issues.list(state="all", get_all=True, order_by="updated_at", sort="desc")


@retry_on_rate_limit
def _list_notes(issue):
    return issue.notes.list(get_all=True, sort="asc", order_by="created_at")


def _format_issue(issue, notes, gitlab_url: str, project_path: str) -> str:
    """Issue を Markdown 文字列にフォーマットする."""
    iid = issue.iid
    state = issue.state
    title = issue.title

    # front matter
    fm_data = {
        "iid": iid,
        "state": state,
        "title": title,
        "labels": issue.labels or [],
        "assignees": [a["username"] for a in (issue.assignees or [])],
        "author": issue.author["username"] if issue.author else "",
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
        "web_url": issue.web_url,
    }

    parts: list[str] = [dump_front_matter(fm_data)]
    parts.append(f"\n# #{iid} {title}\n\n")

    # 本文
    parts.append("## 本文\n\n")
    description = issue.description or ""
    if description:
        description = rewrite_upload_links(description, gitlab_url, project_path)
        parts.append(f"{description}\n\n")
    else:
        parts.append("_(本文なし)_\n\n")

    # コメント（System Notes 除外）
    user_notes = [n for n in notes if not getattr(n, "system", False)]
    if user_notes:
        parts.append("## コメント\n\n")
        for note in user_notes:
            author = note.author["username"] if note.author else "unknown"
            created = note.created_at[:16].replace("T", " ")  # "2026-04-21T09:15" -> "2026-04-21 09:15"
            body = rewrite_upload_links(note.body or "", gitlab_url, project_path)
            parts.append(f"### @{author} — {created}\n\n{body}\n\n")

    return "".join(parts)


def main():
    """Issue 同期のエントリポイント."""
    project = get_project()
    gitlab_url = os.environ["GITLAB_URL"].rstrip("/")
    project_path = os.environ.get("CI_PROJECT_PATH", "")

    issues = _list_issues(project)
    logger.info("Issues found: %d", len(issues))

    valid_paths: set[Path] = set()

    for issue in issues:
        notes = _list_notes(issue)

        iid = issue.iid
        title = issue.title
        state = issue.state
        filename = f"{iid:04d}-{slugify(title)}.md"

        # state に応じて出力先決定
        if state == "closed":
            target_dir = CLOSED_DIR
            opposite_dir = OPEN_DIR
        else:
            target_dir = OPEN_DIR
            opposite_dir = CLOSED_DIR

        file_path = target_dir / filename
        valid_paths.add(file_path.resolve())

        # state 遷移クリーンアップ: 反対側のディレクトリに同じ iid のファイルがあれば削除
        for old_file in opposite_dir.glob(f"{iid:04d}-*.md"):
            old_file.unlink()
            logger.info("削除 (state遷移): %s", old_file)

        content = _format_issue(issue, notes, gitlab_url, project_path)
        if write_file_if_changed(file_path, content):
            logger.info("更新: %s", file_path)
        else:
            logger.info("変更なし: %s", file_path)

    # index.md 生成（iid 昇順）
    index_path = DOCS_ISSUES_DIR / "index.md"
    valid_paths.add(index_path.resolve())

    sorted_issues = sorted(issues, key=lambda i: i.iid)
    lines = [dump_front_matter({"title": "Issue 一覧", "type": "index"})]
    lines.append("\n# Issue 一覧\n\n")
    lines.append("| iid | state | title | labels | assignees | updated_at |\n")
    lines.append("|-----|-------|-------|--------|-----------|------------|\n")
    for issue in sorted_issues:
        iid = issue.iid
        state = issue.state
        title = issue.title
        labels = ", ".join(issue.labels or [])
        assignees = ", ".join(a["username"] for a in (issue.assignees or []))
        updated = issue.updated_at[:10] if issue.updated_at else ""
        subdir = "closed" if state == "closed" else "open"
        filename = f"{iid:04d}-{slugify(title)}.md"
        lines.append(
            f"| {iid} | {state} | [{title}]({subdir}/{filename}) | {labels} | {assignees} | {updated} |\n"
        )

    index_content = "".join(lines)
    if write_file_if_changed(index_path, index_content):
        logger.info("更新: %s", index_path)

    # 孤児ファイル削除（API に存在しない iid）
    deleted = clean_orphaned_files(OPEN_DIR, valid_paths)
    for d in deleted:
        logger.info("削除: %s", d)

    deleted = clean_orphaned_files(CLOSED_DIR, valid_paths)
    for d in deleted:
        logger.info("削除: %s", d)

    logger.info("Issue 同期完了")


if __name__ == "__main__":
    main()
