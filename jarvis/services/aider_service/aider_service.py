"""
Main Aider CLI Service - Comprehensive integration layer.

This module provides the main service class that combines all
individual operation modules into a unified interface.
"""

import os
from typing import Optional, Dict, Any

from .types import (
    AiderResult,
    AiderNotFoundError,
    GitOperationError,
    GitHubOperationError,
)
from .core import AiderCore
from .file_system import FileOperations
from .git_operations import GitOperations
from .github_operations import GitHubOperations
from .testing_operations import TestingOperations
from .project_analysis import ProjectAnalysis


class AiderService:
    """
    Comprehensive Aider CLI Service combining all operations.

    This service provides a unified interface to all Aider CLI operations
    including AI-powered code operations, file system operations, git operations,
    GitHub operations, testing, and project analysis.
    """

    def __init__(
        self,
        aider_executable: str = "aider",
        default_model: Optional[str] = None,
        default_timeout: float = 300.0,
        verbose: bool = False,
        github_token: Optional[str] = None,
    ):
        """
        Initialize the comprehensive Aider service.

        Args:
            aider_executable: Path to aider executable
            default_model: Default AI model to use with aider
            default_timeout: Default timeout for operations in seconds
            verbose: Whether to enable verbose output
            github_token: GitHub personal access token for GitHub operations
        """
        self.aider_executable = aider_executable
        self.default_model = default_model
        self.default_timeout = default_timeout
        self.verbose = verbose
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN")

        # Initialize all operation modules
        base_kwargs = {"default_timeout": default_timeout, "verbose": verbose}

        # AI-powered operations
        self.aider = AiderCore(
            aider_executable=aider_executable,
            default_model=default_model,
            **base_kwargs,
        )

        # File system operations
        self.files = FileOperations(**base_kwargs)

        # Git operations
        self.git = GitOperations(**base_kwargs)

        # GitHub operations (only if token is available)
        self.github = None
        if self.github_token:
            try:
                self.github = GitHubOperations(
                    github_token=self.github_token, **base_kwargs
                )
            except GitHubOperationError as e:
                if verbose:
                    print(f"GitHub operations not available: {e}")

        # Testing and quality operations
        self.testing = TestingOperations(**base_kwargs)

        # Project analysis operations
        self.analysis = ProjectAnalysis(**base_kwargs)

    @property
    def is_github_available(self) -> bool:
        """Check if GitHub operations are available."""
        return self.github is not None

    def get_service_status(self) -> Dict[str, Any]:
        """Get the status of all available services."""
        status = {
            "aider": {
                "available": True,
                "executable": self.aider_executable,
                "model": self.default_model,
            },
            "files": {"available": True},
            "git": {"available": True},
            "github": {
                "available": self.is_github_available,
                "token_configured": bool(self.github_token),
            },
            "testing": {"available": True},
            "analysis": {"available": True},
        }

        return status

    # Convenience methods that delegate to appropriate modules

    def send_message(self, repo_path: str, message: str, **kwargs) -> AiderResult:
        """Send a message to aider (convenience method)."""
        return self.aider.send_message(repo_path, message, **kwargs)

    def read_file(self, repo_path: str, file_path: str, **kwargs) -> AiderResult:
        """Read a file (convenience method)."""
        return self.files.read_file(repo_path, file_path, **kwargs)

    def write_file(
        self, repo_path: str, file_path: str, content: str, **kwargs
    ) -> AiderResult:
        """Write a file (convenience method)."""
        return self.files.write_file(repo_path, file_path, content, **kwargs)

    def git_status(self, repo_path: str, **kwargs) -> AiderResult:
        """Get git status (convenience method)."""
        return self.git.status(repo_path, **kwargs)

    def git_commit(self, repo_path: str, message: str, **kwargs) -> AiderResult:
        """Create git commit (convenience method)."""
        return self.git.commit(repo_path, message, **kwargs)

    def run_tests(self, repo_path: str, **kwargs) -> AiderResult:
        """Run tests (convenience method)."""
        return self.testing.run_tests(repo_path, **kwargs)

    def create_pr(self, repo_path: str, title: str, body: str, **kwargs) -> AiderResult:
        """Create GitHub PR (convenience method)."""
        if not self.is_github_available:
            return AiderResult.error_result(
                error_message="GitHub operations not available. Check token and gh CLI installation.",
                command="create_pr",
            )
        return self.github.create_pr(repo_path, title, body, **kwargs)

    # Workflow methods that combine multiple operations

    def complete_feature_workflow(
        self,
        repo_path: str,
        feature_description: str,
        target_files: list,
        branch_name: Optional[str] = None,
        create_tests: bool = True,
        create_pr: bool = False,
        pr_title: Optional[str] = None,
        pr_body: Optional[str] = None,
    ) -> Dict[str, AiderResult]:
        """
        Complete workflow for developing a new feature.

        This method combines multiple operations:
        1. Create feature branch (optional)
        2. Generate/modify code using aider
        3. Write tests (optional)
        4. Run tests and fix issues
        5. Commit changes
        6. Create PR (optional)

        Returns a dictionary with results from each step.
        """
        results = {}

        # Step 1: Create feature branch
        if branch_name:
            results["create_branch"] = self.git.checkout(
                repo_path, branch_name, create=True
            )
            if not results["create_branch"].success:
                return results

        # Step 2: Generate/modify code
        results["code_generation"] = self.aider.send_message(
            repo_path=repo_path, message=feature_description, files=target_files
        )

        # Step 3: Write tests
        if create_tests:
            for file_path in target_files:
                test_result = self.aider.write_tests(repo_path, file_path)
                results[f"tests_{file_path}"] = test_result

        # Step 4: Run tests
        results["run_tests"] = self.testing.run_tests(repo_path)

        # Step 5: Commit changes
        commit_message = f"Implement feature: {feature_description[:50]}..."
        results["commit"] = self.git.commit(repo_path, commit_message)

        # Step 6: Create PR
        if create_pr and self.is_github_available:
            pr_title = pr_title or f"Feature: {feature_description[:50]}..."
            pr_body = pr_body or f"This PR implements: {feature_description}"
            results["create_pr"] = self.github.create_pr(
                repo_path, pr_title, pr_body, head_branch=branch_name
            )

        return results

    def code_review_workflow(
        self, repo_path: str, target_files: Optional[list] = None
    ) -> Dict[str, AiderResult]:
        """
        Complete code review workflow.

        This method performs:
        1. Run linting
        2. Run tests with coverage
        3. Security scan
        4. Generate review summary

        Returns a dictionary with results from each step.
        """
        results = {}

        # Step 1: Linting
        results["lint"] = self.testing.run_linter(repo_path)

        # Step 2: Tests with coverage
        results["test_coverage"] = self.testing.run_coverage(repo_path)

        # Step 3: Security scan
        results["security"] = self.testing.run_security_scan(repo_path)

        # Step 4: Code quality validation
        results["quality_check"] = self.testing.validate_code_quality(repo_path)

        # Step 5: Generate analysis summary
        if target_files:
            # Analyze specific files
            analysis_messages = []
            for file_path in target_files:
                explain_result = self.aider.explain_code(repo_path, file_path)
                if explain_result.success:
                    analysis_messages.append(
                        f"Analysis of {file_path}:\n{explain_result.stdout}"
                    )

            results["code_analysis"] = AiderResult.success_result(
                stdout="\n\n".join(analysis_messages), command="code_review_workflow"
            )

        return results

    def project_setup_workflow(
        self,
        repo_path: str,
        project_type: str = "python",
        include_tests: bool = True,
        include_ci: bool = True,
        include_docs: bool = True,
    ) -> Dict[str, AiderResult]:
        """
        Complete project setup workflow.

        This method sets up:
        1. Project structure
        2. Configuration files
        3. Test framework
        4. CI/CD pipeline
        5. Documentation

        Returns a dictionary with results from each step.
        """
        results = {}

        # Step 1: Create basic project structure
        structure_prompt = f"""
        Set up a basic {project_type} project structure with:
        - Proper directory organization
        - Configuration files (setup.py, pyproject.toml, etc.)
        - README.md with project description
        - .gitignore file
        {'- Test directory structure' if include_tests else ''}
        {'- CI/CD workflow files' if include_ci else ''}
        {'- Documentation structure' if include_docs else ''}
        """

        results["project_structure"] = self.aider.send_message(
            repo_path=repo_path, message=structure_prompt
        )

        # Step 2: Initialize git if not already initialized
        git_init_result = self.git.status(repo_path)
        if not git_init_result.success:
            # Repository not initialized
            init_result = self.run_command(["git", "init"], cwd=repo_path)
            results["git_init"] = init_result

        # Step 3: Generate project summary
        results["project_summary"] = self.analysis.generate_project_summary(repo_path)

        return results

    def maintenance_workflow(self, repo_path: str) -> Dict[str, AiderResult]:
        """
        Complete maintenance workflow.

        This method performs:
        1. Dependency analysis
        2. Find and categorize TODOs
        3. Code metrics analysis
        4. Large files check
        5. Git history analysis

        Returns a dictionary with results from each step.
        """
        results = {}

        # Step 1: Dependency analysis
        results["dependencies"] = self.analysis.analyze_dependencies(repo_path)

        # Step 2: Find TODOs
        results["todos"] = self.analysis.find_todos(repo_path)

        # Step 3: Code metrics
        results["metrics"] = self.analysis.analyze_code_metrics(repo_path)

        # Step 4: Large files
        results["large_files"] = self.analysis.find_large_files(repo_path)

        # Step 5: Git history analysis
        results["git_history"] = self.analysis.analyze_git_history(repo_path)

        # Step 6: Generate maintenance report
        results["maintenance_report"] = self.analysis.generate_project_summary(
            repo_path,
            output_file="MAINTENANCE_REPORT.md",
            include_metrics=True,
            include_dependencies=True,
            include_todos=True,
        )

        return results


# Convenience factory function
def create_aider_service(
    aider_executable: str = "aider",
    model: Optional[str] = None,
    github_token: Optional[str] = None,
    verbose: bool = False,
    timeout: float = 300.0,
) -> AiderService:
    """
    Factory function to create an AiderService instance.

    Args:
        aider_executable: Path to aider executable
        model: Default AI model to use
        github_token: GitHub token for GitHub operations
        verbose: Enable verbose output
        timeout: Default timeout for operations

    Returns:
        Configured AiderService instance
    """
    return AiderService(
        aider_executable=aider_executable,
        default_model=model,
        github_token=github_token,
        verbose=verbose,
        default_timeout=timeout,
    )
