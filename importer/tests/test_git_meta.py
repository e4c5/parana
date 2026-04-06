"""Unit tests for git_meta.py — compute_uncommitted_files_hash."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import git


def _init_repo(tmp_path: Path) -> git.Repo:
    """Create a minimal git repository with one committed file."""
    repo = git.Repo.init(tmp_path)
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()

    # Add a remote so resolve_git_origin won't raise.
    repo.create_remote("origin", "https://example.com/repo.git")

    committed = tmp_path / "committed.txt"
    committed.write_text("hello\n")
    repo.index.add(["committed.txt"])
    repo.index.commit("initial commit")
    return repo


class TestComputeUncommittedFilesHash:
    def test_clean_tree_returns_clean(self, tmp_path):
        from parana_importer.git_meta import compute_uncommitted_files_hash

        _init_repo(tmp_path)
        result = compute_uncommitted_files_hash(str(tmp_path))
        assert result == "CLEAN"

    def test_untracked_file_changes_hash(self, tmp_path):
        from parana_importer.git_meta import compute_uncommitted_files_hash

        _init_repo(tmp_path)

        # First call — clean.
        h1 = compute_uncommitted_files_hash(str(tmp_path))
        assert h1 == "CLEAN"

        # Add an untracked file.
        (tmp_path / "untracked.txt").write_text("new content\n")
        h2 = compute_uncommitted_files_hash(str(tmp_path))
        assert h2 != "CLEAN"
        assert len(h2) == 64  # SHA-256 hex

    def test_modified_tracked_file_changes_hash(self, tmp_path):
        from parana_importer.git_meta import compute_uncommitted_files_hash

        _init_repo(tmp_path)

        (tmp_path / "committed.txt").write_text("modified content\n")
        result = compute_uncommitted_files_hash(str(tmp_path))
        assert result != "CLEAN"
        assert len(result) == 64

    def test_different_untracked_content_gives_different_hash(self, tmp_path):
        from parana_importer.git_meta import compute_uncommitted_files_hash

        _init_repo(tmp_path)

        (tmp_path / "a.txt").write_text("content A\n")
        h1 = compute_uncommitted_files_hash(str(tmp_path))

        (tmp_path / "a.txt").write_text("content B\n")
        h2 = compute_uncommitted_files_hash(str(tmp_path))

        assert h1 != h2

    def test_hash_is_deterministic(self, tmp_path):
        from parana_importer.git_meta import compute_uncommitted_files_hash

        _init_repo(tmp_path)
        (tmp_path / "file.txt").write_text("stable\n")

        h1 = compute_uncommitted_files_hash(str(tmp_path))
        h2 = compute_uncommitted_files_hash(str(tmp_path))
        assert h1 == h2

    def test_ignored_files_excluded(self, tmp_path):
        from parana_importer.git_meta import compute_uncommitted_files_hash

        repo = _init_repo(tmp_path)

        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("ignored.txt\n")
        repo.index.add([".gitignore"])
        repo.index.commit("add .gitignore")

        # An ignored file should not affect the hash.
        (tmp_path / "ignored.txt").write_text("should be ignored\n")
        result = compute_uncommitted_files_hash(str(tmp_path))
        assert result == "CLEAN"


class TestResolveGitOrigin:
    def test_returns_remote_url(self, tmp_path):
        from parana_importer.git_meta import resolve_git_origin

        _init_repo(tmp_path)
        url = resolve_git_origin(str(tmp_path))
        assert url == "https://example.com/repo.git"


class TestResolveCommitHash:
    def test_returns_40_char_hex(self, tmp_path):
        from parana_importer.git_meta import resolve_commit_hash

        _init_repo(tmp_path)
        hexsha = resolve_commit_hash(str(tmp_path))
        assert len(hexsha) == 40
        assert all(c in "0123456789abcdef" for c in hexsha)


class TestResolveGitBranch:
    def test_returns_branch_name(self, tmp_path):
        from parana_importer.git_meta import resolve_git_branch

        _init_repo(tmp_path)
        branch = resolve_git_branch(str(tmp_path))
        # The default branch name varies (master / main).
        assert isinstance(branch, str)
        assert branch  # not empty
