"""
GitHub operations for the Aider CLI Service.

This module provides GitHub-specific operations using the GitHub CLI (gh)
for pull requests, issues, and repository management.
"""

import os
from typing import List, Optional, Dict, Any

from .types import AiderResult, GitHubOperationError
from .executor import BaseExecutor


class GitHubOperations(BaseExecutor):
    """GitHub operations handler using GitHub CLI"""

    def __init__(self, github_token: Optional[str] = None, **kwargs):
        """
        Initialize GitHub operations.

        Args:
            github_token: GitHub personal access token
            **kwargs: Additional arguments for BaseExecutor
        """
        super().__init__(**kwargs)
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN")

        # Verify gh CLI is available
        if not self.verify_command_available("gh"):
            raise GitHubOperationError(
                "GitHub CLI (gh) is not installed or not available in PATH. "
                "Please install it from https://cli.github.com/"
            )

    def _get_env(self) -> Dict[str, str]:
        """Get environment variables with GitHub token if available."""
        env = {}
        if self.github_token:
            env["GH_TOKEN"] = self.github_token
        return env

    def auth_status(self, repo_path: str) -> AiderResult:
        """Check GitHub authentication status."""
        cmd = ["gh", "auth", "status"]
        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def create_pr(
        self,
        repo_path: str,
        title: str,
        body: str,
        base_branch: str = "main",
        head_branch: Optional[str] = None,
        draft: bool = False,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
        reviewers: Optional[List[str]] = None,
    ) -> AiderResult:
        """Create a GitHub pull request."""
        cmd = [
            "gh",
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--base",
            base_branch,
        ]

        if head_branch:
            cmd.extend(["--head", head_branch])

        if draft:
            cmd.append("--draft")

        if labels:
            cmd.extend(["--label", ",".join(labels)])

        if assignees:
            cmd.extend(["--assignee", ",".join(assignees)])

        if reviewers:
            cmd.extend(["--reviewer", ",".join(reviewers)])

        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def merge_pr(
        self,
        repo_path: str,
        pr_number: int,
        merge_method: str = "merge",  # merge, squash, rebase
        delete_branch: bool = True,
    ) -> AiderResult:
        """Merge a GitHub pull request."""
        cmd = ["gh", "pr", "merge", str(pr_number), f"--{merge_method}"]

        if delete_branch:
            cmd.append("--delete-branch")

        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def close_pr(self, repo_path: str, pr_number: int) -> AiderResult:
        """Close a pull request."""
        cmd = ["gh", "pr", "close", str(pr_number)]
        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def reopen_pr(self, repo_path: str, pr_number: int) -> AiderResult:
        """Reopen a pull request."""
        cmd = ["gh", "pr", "reopen", str(pr_number)]
        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def list_prs(
        self,
        repo_path: str,
        state: str = "open",  # open, closed, merged, all
        limit: int = 30,
        author: Optional[str] = None,
        assignee: Optional[str] = None,
        label: Optional[str] = None,
    ) -> AiderResult:
        """List GitHub pull requests."""
        cmd = ["gh", "pr", "list", "--state", state, "--limit", str(limit)]

        if author:
            cmd.extend(["--author", author])

        if assignee:
            cmd.extend(["--assignee", assignee])

        if label:
            cmd.extend(["--label", label])

        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def pr_view(self, repo_path: str, pr_number: int, web: bool = False) -> AiderResult:
        """View pull request details."""
        cmd = ["gh", "pr", "view", str(pr_number)]

        if web:
            cmd.append("--web")

        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def pr_diff(self, repo_path: str, pr_number: int) -> AiderResult:
        """Get diff for a pull request."""
        cmd = ["gh", "pr", "diff", str(pr_number)]
        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def pr_checkout(self, repo_path: str, pr_number: int) -> AiderResult:
        """Checkout a pull request locally."""
        cmd = ["gh", "pr", "checkout", str(pr_number)]
        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def pr_review(
        self,
        repo_path: str,
        pr_number: int,
        action: str = "approve",  # approve, request-changes, comment
        body: Optional[str] = None,
    ) -> AiderResult:
        """Review a pull request."""
        cmd = ["gh", "pr", "review", str(pr_number), f"--{action}"]

        if body:
            cmd.extend(["--body", body])

        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def pr_comment(self, repo_path: str, pr_number: int, body: str) -> AiderResult:
        """Add a comment to a pull request."""
        cmd = ["gh", "pr", "comment", str(pr_number), "--body", body]
        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def create_issue(
        self,
        repo_path: str,
        title: str,
        body: str,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
        milestone: Optional[str] = None,
    ) -> AiderResult:
        """Create a GitHub issue."""
        cmd = ["gh", "issue", "create", "--title", title, "--body", body]

        if labels:
            cmd.extend(["--label", ",".join(labels)])

        if assignees:
            cmd.extend(["--assignee", ",".join(assignees)])

        if milestone:
            cmd.extend(["--milestone", milestone])

        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def close_issue(self, repo_path: str, issue_number: int) -> AiderResult:
        """Close an issue."""
        cmd = ["gh", "issue", "close", str(issue_number)]
        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def reopen_issue(self, repo_path: str, issue_number: int) -> AiderResult:
        """Reopen an issue."""
        cmd = ["gh", "issue", "reopen", str(issue_number)]
        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def list_issues(
        self,
        repo_path: str,
        state: str = "open",  # open, closed, all
        limit: int = 30,
        author: Optional[str] = None,
        assignee: Optional[str] = None,
        label: Optional[str] = None,
    ) -> AiderResult:
        """List GitHub issues."""
        cmd = ["gh", "issue", "list", "--state", state, "--limit", str(limit)]

        if author:
            cmd.extend(["--author", author])

        if assignee:
            cmd.extend(["--assignee", assignee])

        if label:
            cmd.extend(["--label", label])

        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def issue_view(
        self, repo_path: str, issue_number: int, web: bool = False
    ) -> AiderResult:
        """View issue details."""
        cmd = ["gh", "issue", "view", str(issue_number)]

        if web:
            cmd.append("--web")

        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def issue_comment(
        self, repo_path: str, issue_number: int, body: str
    ) -> AiderResult:
        """Add a comment to an issue."""
        cmd = ["gh", "issue", "comment", str(issue_number), "--body", body]
        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def create_release(
        self,
        repo_path: str,
        tag: str,
        title: Optional[str] = None,
        notes: Optional[str] = None,
        draft: bool = False,
        prerelease: bool = False,
        generate_notes: bool = True,
    ) -> AiderResult:
        """Create a GitHub release."""
        cmd = ["gh", "release", "create", tag]

        if title:
            cmd.extend(["--title", title])

        if notes:
            cmd.extend(["--notes", notes])
        elif generate_notes:
            cmd.append("--generate-notes")

        if draft:
            cmd.append("--draft")

        if prerelease:
            cmd.append("--prerelease")

        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def list_releases(self, repo_path: str, limit: int = 30) -> AiderResult:
        """List GitHub releases."""
        cmd = ["gh", "release", "list", "--limit", str(limit)]
        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def delete_release(
        self, repo_path: str, tag: str, cleanup_tag: bool = True
    ) -> AiderResult:
        """Delete a GitHub release."""
        cmd = ["gh", "release", "delete", tag]

        if cleanup_tag:
            cmd.append("--cleanup-tag")

        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def repo_view(self, repo_path: str, web: bool = False) -> AiderResult:
        """View repository information."""
        cmd = ["gh", "repo", "view"]

        if web:
            cmd.append("--web")

        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def repo_clone(
        self,
        repo_url: str,
        directory: Optional[str] = None,
        depth: Optional[int] = None,
    ) -> AiderResult:
        """Clone a GitHub repository."""
        cmd = ["gh", "repo", "clone", repo_url]

        if directory:
            cmd.append(directory)

        if depth:
            cmd.extend(["--", "--depth", str(depth)])

        return self.run_command(cmd, env=self._get_env())

    def repo_fork(
        self, repo_path: str, clone: bool = True, remote: bool = True
    ) -> AiderResult:
        """Fork a GitHub repository."""
        cmd = ["gh", "repo", "fork"]

        if clone:
            cmd.append("--clone")

        if remote:
            cmd.append("--remote")

        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def workflow_list(self, repo_path: str) -> AiderResult:
        """List GitHub Actions workflows."""
        cmd = ["gh", "workflow", "list"]
        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def workflow_run(
        self, repo_path: str, workflow_id: str, ref: Optional[str] = None
    ) -> AiderResult:
        """Trigger a GitHub Actions workflow."""
        cmd = ["gh", "workflow", "run", workflow_id]

        if ref:
            cmd.extend(["--ref", ref])

        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def run_list(
        self, repo_path: str, workflow: Optional[str] = None, limit: int = 20
    ) -> AiderResult:
        """List GitHub Actions workflow runs."""
        cmd = ["gh", "run", "list", "--limit", str(limit)]

        if workflow:
            cmd.extend(["--workflow", workflow])

        return self.run_command(cmd, cwd=repo_path, env=self._get_env())

    def run_view(self, repo_path: str, run_id: str, log: bool = False) -> AiderResult:
        """View GitHub Actions workflow run details."""
        cmd = ["gh", "run", "view", run_id]

        if log:
            cmd.append("--log")

        return self.run_command(cmd, cwd=repo_path, env=self._get_env())
