"""Wiki ページを docs/wiki/ に同期する."""

import logging
import os
from pathlib import Path

from scripts.common import (
    clean_orphaned_files,
    dump_front_matter,
    rewrite_upload_links,
    write_file_if_changed,
)
from scripts.gitlab_client import get_project, retry_on_rate_limit

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

DOCS_WIKI_DIR = Path("docs/wiki")


@retry_on_rate_limit
def _list_wikis(project):
    return project.wikis.list(get_all=True)


@retry_on_rate_limit
def _get_wiki(project, slug):
    return project.wikis.get(slug)


def main():
    """Wiki 同期のエントリポイント."""
    project = get_project()
    gitlab_url = os.environ["GITLAB_URL"].rstrip("/")
    project_path = os.environ.get("CI_PROJECT_PATH", "")

    wiki_pages = _list_wikis(project)
    logger.info("Wiki pages found: %d", len(wiki_pages))

    valid_paths: set[Path] = set()

    for page_ref in wiki_pages:
        page = _get_wiki(project, page_ref.slug)
        slug = page.slug  # e.g. "parent/child"

        # slug の / をディレクトリ階層に展開
        file_path = DOCS_WIKI_DIR / f"{slug}.md"
        valid_paths.add(file_path.resolve())

        # front matter
        fm_data: dict = {
            "slug": slug,
            "title": page.title,
            "format": getattr(page, "format", "markdown"),
        }
        updated_at = getattr(page, "updated_at", None)
        if updated_at:
            fm_data["updated_at"] = updated_at

        # 本文
        content = getattr(page, "content", "") or ""
        content = rewrite_upload_links(content, gitlab_url, project_path)

        full_content = dump_front_matter(fm_data) + "\n" + content + "\n"

        if write_file_if_changed(file_path, full_content):
            logger.info("更新: %s", file_path)
        else:
            logger.info("変更なし: %s", file_path)

    # index.md 生成（slug 昇順）
    index_path = DOCS_WIKI_DIR / "index.md"
    valid_paths.add(index_path.resolve())

    sorted_pages = sorted(wiki_pages, key=lambda p: p.slug)
    lines = [dump_front_matter({"title": "Wiki ページ一覧", "type": "index"})]
    lines.append("\n# Wiki ページ一覧\n\n")
    for page_ref in sorted_pages:
        slug = page_ref.slug
        title = page_ref.title
        lines.append(f"- [{title}]({slug}.md)\n")

    index_content = "".join(lines)
    if write_file_if_changed(index_path, index_content):
        logger.info("更新: %s", index_path)

    # 孤児ファイル削除
    deleted = clean_orphaned_files(DOCS_WIKI_DIR, valid_paths)
    for d in deleted:
        logger.info("削除: %s", d)

    logger.info("Wiki 同期完了")


if __name__ == "__main__":
    main()
