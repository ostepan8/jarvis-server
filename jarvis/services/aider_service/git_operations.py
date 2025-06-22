"""
Git operations for the Aider CLI Service.

This module provides comprehensive git operations including
status, commits, branches, merging, and repository management.
"""

from typing import List, Optional

from .types import AiderResult, GitOperationError
from .executor import BaseExecutor


class GitOperations(BaseExecutor):
    """Git operations handler"""

    def __init__(self, **kwargs):
        """Initialize Git operations."""
        super().__init__(**kwargs)

        # Verify git is available
        if not self.verify_command_available("git"):
            raise GitOperationError("Git is not installed or not available in PATH")

    def status(self, repo_path: str, porcelain: bool = True) -> AiderResult:
        """Get git status of the repository."""
        cmd = ["git", "status"]
        if porcelain:
            cmd.append("--porcelain")

        return self.run_command(cmd, cwd=repo_path)

    def diff(
        self,
        repo_path: str,
        file_path: Optional[str] = None,
        staged: bool = False,
        name_only: bool = False,
    ) -> AiderResult:
        """Get git diff for changes."""
        cmd = ["git", "diff"]

        if staged:
            cmd.append("--staged")

        if name_only:
            cmd.append("--name-only")

        if file_path:
            cmd.append(file_path)

        return self.run_command(cmd, cwd=repo_path)

    def add(self, repo_path: str, file_paths: List[str]) -> AiderResult:
        """Stage files for commit."""
        cmd = ["git", "add"] + file_paths
        return self.run_command(cmd, cwd=repo_path)

    def add_all(self, repo_path: str) -> AiderResult:
        """Stage all changes."""
        cmd = ["git", "add", "."]
        return self.run_command(cmd, cwd=repo_path)

    def commit(self, repo_path: str, message: str, amend: bool = False) -> AiderResult:
        """Create a git commit."""
        cmd = ["git", "commit", "-m", message]

        if amend:
            cmd.append("--amend")

        return self.run_command(cmd, cwd=repo_path)

    def push(
        self,
        repo_path: str,
        remote: str = "origin",
        branch: Optional[str] = None,
        force: bool = False,
        set_upstream: bool = False,
    ) -> AiderResult:
        """Push commits to remote repository."""
        cmd = ["git", "push"]

        if force:
            cmd.append("--force")

        if set_upstream:
            cmd.append("--set-upstream")

        cmd.append(remote)

        if branch:
            cmd.append(branch)

        return self.run_command(cmd, cwd=repo_path)

    def pull(
        self,
        repo_path: str,
        remote: str = "origin",
        branch: Optional[str] = None,
        rebase: bool = False,
    ) -> AiderResult:
        """Pull latest changes from remote."""
        cmd = ["git", "pull"]

        if rebase:
            cmd.append("--rebase")

        cmd.append(remote)

        if branch:
            cmd.append(branch)

        return self.run_command(cmd, cwd=repo_path)

    def fetch(
        self, repo_path: str, remote: str = "origin", all_remotes: bool = False
    ) -> AiderResult:
        """Fetch from remote repository."""
        cmd = ["git", "fetch"]

        if all_remotes:
            cmd.append("--all")
        else:
            cmd.append(remote)

        return self.run_command(cmd, cwd=repo_path)

    def checkout(
        self, repo_path: str, branch: str, create: bool = False, force: bool = False
    ) -> AiderResult:
        """Checkout a git branch."""
        cmd = ["git", "checkout"]

        if create:
            cmd.append("-b")

        if force:
            cmd.append("--force")

        cmd.append(branch)

        return self.run_command(cmd, cwd=repo_path)

    def merge(
        self, repo_path: str, branch: str, no_ff: bool = False, squash: bool = False
    ) -> AiderResult:
        """Merge a branch into current branch."""
        cmd = ["git", "merge"]

        if no_ff:
            cmd.append("--no-ff")

        if squash:
            cmd.append("--squash")

        cmd.append(branch)

        return self.run_command(cmd, cwd=repo_path)

    def rebase(
        self, repo_path: str, branch: str, interactive: bool = False
    ) -> AiderResult:
        """Rebase current branch onto another branch."""
        cmd = ["git", "rebase"]

        if interactive:
            cmd.append("-i")

        cmd.append(branch)

        return self.run_command(cmd, cwd=repo_path)

    def log(
        self,
        repo_path: str,
        max_count: int = 10,
        oneline: bool = True,
        graph: bool = False,
    ) -> AiderResult:
        """Get git commit history."""
        cmd = ["git", "log", f"--max-count={max_count}"]

        if oneline:
            cmd.append("--oneline")

        if graph:
            cmd.append("--graph")

        return self.run_command(cmd, cwd=repo_path)

    def branch_list(
        self, repo_path: str, all_branches: bool = False, remote: bool = False
    ) -> AiderResult:
        """List git branches."""
        cmd = ["git", "branch"]

        if all_branches:
            cmd.append("-a")
        elif remote:
            cmd.append("-r")

        return self.run_command(cmd, cwd=repo_path)

    def branch_create(
        self, repo_path: str, branch_name: str, start_point: Optional[str] = None
    ) -> AiderResult:
        """Create a new branch."""
        cmd = ["git", "branch", branch_name]

        if start_point:
            cmd.append(start_point)

        return self.run_command(cmd, cwd=repo_path)

    def branch_delete(
        self, repo_path: str, branch_name: str, force: bool = False
    ) -> AiderResult:
        """Delete a branch."""
        cmd = ["git", "branch"]

        if force:
            cmd.append("-D")
        else:
            cmd.append("-d")

        cmd.append(branch_name)

        return self.run_command(cmd, cwd=repo_path)

    def current_branch(self, repo_path: str) -> AiderResult:
        """Get the current branch name."""
        cmd = ["git", "branch", "--show-current"]
        return self.run_command(cmd, cwd=repo_path)

    def stash(
        self,
        repo_path: str,
        message: Optional[str] = None,
        include_untracked: bool = False,
    ) -> AiderResult:
        """Stash current changes."""
        cmd = ["git", "stash", "push"]

        if include_untracked:
            cmd.append("-u")

        if message:
            cmd.extend(["-m", message])

        return self.run_command(cmd, cwd=repo_path)

    def stash_pop(self, repo_path: str, stash_index: int = 0) -> AiderResult:
        """Pop a stash."""
        cmd = ["git", "stash", "pop"]

        if stash_index > 0:
            cmd.append(f"stash@{{{stash_index}}}")

        return self.run_command(cmd, cwd=repo_path)

    def stash_list(self, repo_path: str) -> AiderResult:
        """List all stashes."""
        cmd = ["git", "stash", "list"]
        return self.run_command(cmd, cwd=repo_path)

    def stash_drop(self, repo_path: str, stash_index: int = 0) -> AiderResult:
        """Drop a stash."""
        cmd = ["git", "stash", "drop", f"stash@{{{stash_index}}}"]
        return self.run_command(cmd, cwd=repo_path)

    def reset(
        self,
        repo_path: str,
        mode: str = "mixed",  # soft, mixed, hard
        commit: Optional[str] = None,
    ) -> AiderResult:
        """Reset repository state."""
        cmd = ["git", "reset", f"--{mode}"]

        if commit:
            cmd.append(commit)

        return self.run_command(cmd, cwd=repo_path)

    def clean(
        self,
        repo_path: str,
        directories: bool = False,
        force: bool = False,
        dry_run: bool = False,
    ) -> AiderResult:
        """Clean untracked files."""
        cmd = ["git", "clean"]

        if dry_run:
            cmd.append("-n")
        elif force:
            cmd.append("-f")

        if directories:
            cmd.append("-d")

        return self.run_command(cmd, cwd=repo_path)

    def tag_create(
        self,
        repo_path: str,
        tag_name: str,
        message: Optional[str] = None,
        commit: Optional[str] = None,
    ) -> AiderResult:
        """Create a git tag."""
        cmd = ["git", "tag"]

        if message:
            cmd.extend(["-a", tag_name, "-m", message])
        else:
            cmd.append(tag_name)

        if commit:
            cmd.append(commit)

        return self.run_command(cmd, cwd=repo_path)

    def tag_list(self, repo_path: str, pattern: Optional[str] = None) -> AiderResult:
        """List git tags."""
        cmd = ["git", "tag"]

        if pattern:
            cmd.extend(["-l", pattern])

        return self.run_command(cmd, cwd=repo_path)

    def tag_delete(self, repo_path: str, tag_name: str) -> AiderResult:
        """Delete a git tag."""
        cmd = ["git", "tag", "-d", tag_name]
        return self.run_command(cmd, cwd=repo_path)

    def remote_list(self, repo_path: str, verbose: bool = False) -> AiderResult:
        """List git remotes."""
        cmd = ["git", "remote"]

        if verbose:
            cmd.append("-v")

        return self.run_command(cmd, cwd=repo_path)

    def remote_add(self, repo_path: str, name: str, url: str) -> AiderResult:
        """Add a git remote."""
        cmd = ["git", "remote", "add", name, url]
        return self.run_command(cmd, cwd=repo_path)

    def remote_remove(self, repo_path: str, name: str) -> AiderResult:
        """Remove a git remote."""
        cmd = ["git", "remote", "remove", name]
        return self.run_command(cmd, cwd=repo_path)

    def blame(
        self, repo_path: str, file_path: str, line_range: Optional[tuple] = None
    ) -> AiderResult:
        """Show git blame for a file."""
        cmd = ["git", "blame"]

        if line_range:
            cmd.extend(["-L", f"{line_range[0]},{line_range[1]}"])

        cmd.append(file_path)

        return self.run_command(cmd, cwd=repo_path)

    def show(
        self, repo_path: str, commit: str, file_path: Optional[str] = None
    ) -> AiderResult:
        """Show commit details."""
        cmd = ["git", "show", commit]

        if file_path:
            cmd.extend(["--", file_path])

        return self.run_command(cmd, cwd=repo_path)
