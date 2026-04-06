"""Git repository metadata resolution using gitpython.

All functions accept a *repo_path* — the root directory that contains the
`.git` folder (or any path inside such a repository; gitpython will walk up
to find the `.git` directory automatically).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import git


def resolve_git_origin(repo_path: str) -> str:
    """Return the push/fetch URL of the 'origin' remote.

    Raises:
        git.InvalidGitRepositoryError: if *repo_path* is not inside a git repo.
        IndexError: if no 'origin' remote is configured.
    """
    repo = git.Repo(repo_path, search_parent_directories=True)
    return repo.remotes["origin"].url


def resolve_git_branch(repo_path: str) -> str:
    """Return the symbolic name of the current branch (e.g. 'main').

    Raises:
        git.InvalidGitRepositoryError: if *repo_path* is not inside a git repo.
        TypeError: if HEAD is detached (no branch name).
    """
    repo = git.Repo(repo_path, search_parent_directories=True)
    return repo.active_branch.name


def resolve_commit_hash(repo_path: str) -> str:
    """Return the 40-character SHA-1 hexdigest of the HEAD commit."""
    repo = git.Repo(repo_path, search_parent_directories=True)
    return repo.head.commit.hexsha


def compute_uncommitted_files_hash(repo_path: str) -> str:
    """Compute a deterministic SHA-256 hash of the uncommitted working-tree state.

    The algorithm (per §3.1.1 of the software design):
    1. Collect modified/staged/deleted *tracked* files via index diffs.
    2. Collect *untracked* files (respecting .gitignore) from repo.untracked_files.
    3. Sort both sets lexicographically by path.
    4. For each path build a line: ``<status_code> <path> <sha256_of_content>``
       — deleted files use the literal string ``DELETED`` for the content hash.
       — untracked files use status code ``?``.
    5. SHA-256 the concatenation of all lines (newline-separated).
    6. If both sets are empty return the constant ``"CLEAN"``.

    Returns:
        A 64-character lowercase hex SHA-256 string, or ``"CLEAN"``.
    """
    repo = git.Repo(repo_path, search_parent_directories=True)
    worktree = Path(repo.working_tree_dir)

    # --- tracked file changes --------------------------------------------------
    # index.diff(None)    → unstaged changes (index vs working tree)
    # index.diff("HEAD")  → staged changes   (HEAD vs index)
    changed: dict[str, str] = {}  # path → single-char status code

    for diff in repo.index.diff(None):  # unstaged
        path = diff.b_path or diff.a_path
        changed[path] = "D" if diff.deleted_file else "M"

    for diff in repo.index.diff("HEAD"):  # staged
        path = diff.b_path or diff.a_path
        # Only set if not already marked (unstaged deletion takes precedence)
        if path not in changed:
            changed[path] = "D" if diff.deleted_file else "M"

    # --- untracked files -------------------------------------------------------
    untracked: set[str] = set(repo.untracked_files)

    if not changed and not untracked:
        return "CLEAN"

    # --- build sorted entry list -----------------------------------------------
    entries: list[str] = []

    for path in sorted(changed):
        status = changed[path]
        full_path = worktree / path
        if status == "D" or not full_path.exists():
            entries.append(f"{status} {path} DELETED")
        else:
            content_hash = _sha256_file(full_path)
            entries.append(f"{status} {path} {content_hash}")

    for path in sorted(untracked):
        full_path = worktree / path
        content_hash = _sha256_file(full_path)
        entries.append(f"? {path} {content_hash}")

    combined = "\n".join(entries)
    return hashlib.sha256(combined.encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 hexdigest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
