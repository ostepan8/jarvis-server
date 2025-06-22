"""
Aider CLI Service - Comprehensive integration layer for software engineering operations.

This package provides a complete toolkit for software engineering operations,
combining aider's AI capabilities with filesystem, git, and GitHub operations.

Main Classes:
    AiderService: Main service class combining all operations
    AiderCore: AI-powered code operations using aider
    FileOperations: File system operations
    GitOperations: Git version control operations
    GitHubOperations: GitHub-specific operations
    TestingOperations: Testing and quality operations
    ProjectAnalysis: Project analysis and metrics

Usage:
    from aider_service import AiderService, create_aider_service

    # Create service instance
    service = create_aider_service(
        model="gpt-4",
        github_token="your-token",
        verbose=True
    )

    # Use individual operations
    result = service.send_message(repo_path, "Add error handling to main.py")
    result = service.run_tests(repo_path)
    result = service.create_pr(repo_path, "Fix bug", "Description...")

    # Use complete workflows
    results = service.complete_feature_workflow(
        repo_path,
        "Add user authentication",
        ["auth.py", "models.py"]
    )
"""

from .aider_service import AiderService, create_aider_service
from .core import AiderCore
from .file_system import FileOperations
from .git_operations import GitOperations
from .github_operations import GitHubOperations
from .testing_operations import TestingOperations
from .project_analysis import ProjectAnalysis
from .executor import BaseExecutor
from .types import (
    AiderMode,
    AiderResult,
    ServiceError,
    AiderNotFoundError,
    GitOperationError,
    FileOperationError,
    GitHubOperationError,
)

__version__ = "1.0.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

__all__ = [
    "AiderService",
    "create_aider_service",
    "AiderCore",
    "FileOperations",
    "GitOperations",
    "GitHubOperations",
    "TestingOperations",
    "ProjectAnalysis",
    "BaseExecutor",
    "AiderMode",
    "AiderResult",
    "ServiceError",
    "AiderNotFoundError",
    "GitOperationError",
    "FileOperationError",
    "GitHubOperationError",
]
# Package metadata
PACKAGE_INFO = {
    "name": "aider-cli-service",
    "version": __version__,
    "description": "Comprehensive integration layer for Aider CLI operations",
    "author": __author__,
    "author_email": __email__,
    "url": "https://github.com/yourusername/aider-cli-service",
    "license": "MIT",
    "python_requires": ">=3.8",
    "dependencies": [
        "aider-chat>=0.30.0",
    ],
    "optional_dependencies": {
        "github": ["gh"],
        "testing": ["pytest", "pytest-cov", "flake8", "black", "mypy"],
        "analysis": ["radon", "bandit", "safety"],
        "all": [
            "gh",
            "pytest",
            "pytest-cov",
            "flake8",
            "black",
            "mypy",
            "radon",
            "bandit",
            "safety",
        ],
    },
}


def get_version() -> str:
    """Get package version."""
    return __version__


def get_package_info() -> dict:
    """Get package information."""
    return PACKAGE_INFO.copy()


def check_dependencies() -> dict:
    """Check if required dependencies are available."""
    import subprocess
    import shutil

    dependencies = {
        "aider": shutil.which("aider") is not None,
        "git": shutil.which("git") is not None,
        "gh": shutil.which("gh") is not None,
        "pytest": shutil.which("pytest") is not None,
        "flake8": shutil.which("flake8") is not None,
        "black": shutil.which("black") is not None,
        "mypy": shutil.which("mypy") is not None,
        "radon": shutil.which("radon") is not None,
        "bandit": shutil.which("bandit") is not None,
        "safety": shutil.which("safety") is not None,
    }

    return dependencies
