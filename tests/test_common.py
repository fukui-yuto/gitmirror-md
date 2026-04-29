"""scripts/common.py の単体テスト."""

import tempfile
from pathlib import Path

from scripts.common import (
    clean_orphaned_files,
    dump_front_matter,
    rewrite_upload_links,
    slugify,
    write_file_if_changed,
)


class TestSlugify:
    def test_basic_ascii(self):
        assert slugify("Hello World") == "hello-world"

    def test_japanese(self):
        assert slugify("ログイン画面") == "ログイン画面"

    def test_underscore_to_hyphen(self):
        assert slugify("foo_bar_baz") == "foo-bar-baz"

    def test_consecutive_hyphens_collapse(self):
        assert slugify("foo--bar") == "foo-bar"
        assert slugify("foo - - bar") == "foo-bar"

    def test_strip_leading_trailing_hyphens(self):
        assert slugify("-hello-") == "hello"
        assert slugify("  hello  ") == "hello"

    def test_remove_forbidden_chars(self):
        assert slugify('file<name>:test"x') == "filenametestx"
        assert slugify("a|b?c*d") == "abcd"

    def test_slash_removed(self):
        # / はファイル名に使えないので除去される
        assert slugify("parent/child") == "parentchild"

    def test_max_length(self):
        long_text = "a" * 100
        result = slugify(long_text)
        assert len(result) == 80

    def test_max_length_no_trailing_hyphen(self):
        # 80文字目が - にならないよう rstrip
        text = "a" * 79 + " b" * 10
        result = slugify(text)
        assert len(result) <= 80
        assert not result.endswith("-")

    def test_empty_string(self):
        assert slugify("") == ""


class TestWriteFileIfChanged:
    def test_creates_new_file(self, tmp_path):
        p = tmp_path / "sub" / "test.md"
        assert write_file_if_changed(p, "hello") is True
        assert p.read_text(encoding="utf-8") == "hello"

    def test_no_write_if_unchanged(self, tmp_path):
        p = tmp_path / "test.md"
        p.write_text("hello", encoding="utf-8")
        assert write_file_if_changed(p, "hello") is False

    def test_overwrites_if_changed(self, tmp_path):
        p = tmp_path / "test.md"
        p.write_text("old", encoding="utf-8")
        assert write_file_if_changed(p, "new") is True
        assert p.read_text(encoding="utf-8") == "new"


class TestDumpFrontMatter:
    def test_basic(self):
        result = dump_front_matter({"iid": 1, "state": "opened"})
        assert result.startswith("---\n")
        assert result.endswith("---\n")
        assert "iid: 1" in result
        assert "state: opened" in result

    def test_preserves_order(self):
        result = dump_front_matter({"z_key": "last", "a_key": "first"})
        z_pos = result.index("z_key")
        a_pos = result.index("a_key")
        assert z_pos < a_pos  # sort_keys=False なので入力順を保持

    def test_japanese_value(self):
        result = dump_front_matter({"title": "テスト"})
        assert "テスト" in result


class TestCleanOrphanedFiles:
    def test_removes_orphaned_files(self, tmp_path):
        valid = tmp_path / "keep.md"
        orphan = tmp_path / "orphan.md"
        valid.write_text("keep")
        orphan.write_text("delete")

        deleted = clean_orphaned_files(tmp_path, {valid})
        assert orphan in deleted
        assert not orphan.exists()
        assert valid.exists()

    def test_preserves_gitkeep(self, tmp_path):
        gitkeep = tmp_path / ".gitkeep"
        gitkeep.write_text("")

        deleted = clean_orphaned_files(tmp_path, set())
        assert gitkeep not in deleted
        assert gitkeep.exists()

    def test_removes_empty_dirs(self, tmp_path):
        subdir = tmp_path / "empty_sub"
        subdir.mkdir()
        orphan = subdir / "file.md"
        orphan.write_text("x")

        clean_orphaned_files(tmp_path, set())
        assert not subdir.exists()

    def test_nonexistent_dir(self, tmp_path):
        result = clean_orphaned_files(tmp_path / "nonexist", set())
        assert result == []


class TestRewriteUploadLinks:
    def test_markdown_image(self):
        content = "![alt](/uploads/abc/img.png)"
        result = rewrite_upload_links(content, "http://gitlab:8080", "root/proj")
        assert result == "![alt](http://gitlab:8080/root/proj/uploads/abc/img.png)"

    def test_markdown_link(self):
        content = "[doc](/uploads/def/file.pdf)"
        result = rewrite_upload_links(content, "http://gitlab:8080", "root/proj")
        assert result == "[doc](http://gitlab:8080/root/proj/uploads/def/file.pdf)"

    def test_html_img_src(self):
        content = '<img src="/uploads/abc/img.png">'
        result = rewrite_upload_links(content, "http://gitlab:8080", "root/proj")
        assert result == '<img src="http://gitlab:8080/root/proj/uploads/abc/img.png">'

    def test_no_change_for_external_links(self):
        content = "[link](https://example.com/file.png)"
        result = rewrite_upload_links(content, "http://gitlab:8080", "root/proj")
        assert result == content

    def test_empty_content(self):
        assert rewrite_upload_links("", "http://g", "p") == ""
        assert rewrite_upload_links(None, "http://g", "p") is None

    def test_trailing_slash_normalization(self):
        content = "[f](/uploads/x/y.png)"
        result = rewrite_upload_links(content, "http://gitlab:8080/", "/root/proj/")
        assert "http://gitlab:8080/root/proj/uploads/x/y.png" in result
