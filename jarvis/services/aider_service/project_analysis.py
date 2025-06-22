"""
Project analysis operations for the Aider CLI Service.

This module provides comprehensive project analysis including
dependency analysis, TODO finding, project summarization, and metrics.
"""

import os
import json
from typing import List, Optional, Dict, Any
from pathlib import Path

from .types import AiderResult
from .executor import BaseExecutor


class ProjectAnalysis(BaseExecutor):
    """Project analysis operations handler"""

    def analyze_dependencies(self, repo_path: str) -> AiderResult:
        """Analyze project dependencies for vulnerabilities."""
        # Try different dependency analysis tools based on project type

        # Python projects
        if os.path.exists(os.path.join(repo_path, "requirements.txt")):
            return self._analyze_python_dependencies(repo_path)
        elif os.path.exists(os.path.join(repo_path, "Pipfile")):
            return self._analyze_pipenv_dependencies(repo_path)
        elif os.path.exists(os.path.join(repo_path, "pyproject.toml")):
            return self._analyze_poetry_dependencies(repo_path)

        # Node.js projects
        elif os.path.exists(os.path.join(repo_path, "package.json")):
            return self._analyze_npm_dependencies(repo_path)

        # Ruby projects
        elif os.path.exists(os.path.join(repo_path, "Gemfile")):
            return self._analyze_gem_dependencies(repo_path)

        # Go projects
        elif os.path.exists(os.path.join(repo_path, "go.mod")):
            return self._analyze_go_dependencies(repo_path)

        # Rust projects
        elif os.path.exists(os.path.join(repo_path, "Cargo.toml")):
            return self._analyze_cargo_dependencies(repo_path)

        else:
            return AiderResult.error_result(
                error_message="No recognized dependency file found",
                command="analyze_dependencies",
            )

    def _analyze_python_dependencies(self, repo_path: str) -> AiderResult:
        """Analyze Python dependencies using pip-audit or safety."""
        # Try pip-audit first
        result = self.run_command(["pip-audit"], cwd=repo_path)
        if result.success:
            return result

        # Fall back to safety
        return self.run_command(["safety", "check"], cwd=repo_path)

    def _analyze_pipenv_dependencies(self, repo_path: str) -> AiderResult:
        """Analyze Pipenv dependencies."""
        return self.run_command(["pipenv", "check"], cwd=repo_path)

    def _analyze_poetry_dependencies(self, repo_path: str) -> AiderResult:
        """Analyze Poetry dependencies."""
        return self.run_command(["poetry", "audit"], cwd=repo_path)

    def _analyze_npm_dependencies(self, repo_path: str) -> AiderResult:
        """Analyze npm dependencies."""
        return self.run_command(["npm", "audit"], cwd=repo_path)

    def _analyze_gem_dependencies(self, repo_path: str) -> AiderResult:
        """Analyze Ruby gem dependencies."""
        return self.run_command(["bundle", "audit"], cwd=repo_path)

    def _analyze_go_dependencies(self, repo_path: str) -> AiderResult:
        """Analyze Go module dependencies."""
        return self.run_command(["go", "list", "-m", "-u", "all"], cwd=repo_path)

    def _analyze_cargo_dependencies(self, repo_path: str) -> AiderResult:
        """Analyze Rust Cargo dependencies."""
        return self.run_command(["cargo", "audit"], cwd=repo_path)

    def find_todos(
        self,
        repo_path: str,
        patterns: List[str] = None,
        file_extensions: List[str] = None,
    ) -> AiderResult:
        """Find TODO comments and similar markers in code."""
        if patterns is None:
            patterns = ["TODO", "FIXME", "HACK", "XXX", "NOTE", "BUG"]

        if file_extensions is None:
            file_extensions = [
                "*.py",
                "*.js",
                "*.java",
                "*.go",
                "*.rs",
                "*.cpp",
                "*.c",
                "*.h",
            ]

        pattern_regex = "|".join(patterns)
        cmd = ["grep", "-r", "-n", "-E", f"({pattern_regex})"]

        # Add include patterns for file extensions
        for ext in file_extensions:
            cmd.extend(["--include", ext])

        cmd.append(".")

        return self.run_command(cmd, cwd=repo_path)

    def analyze_code_metrics(self, repo_path: str) -> AiderResult:
        """Analyze various code metrics using multiple tools."""
        metrics = {}

        # Lines of code
        loc_result = self.run_command(
            ["find", ".", "-name", "*.py", "-exec", "wc", "-l", "{}", "+"],
            cwd=repo_path,
        )
        if loc_result.success:
            metrics["lines_of_code"] = self._parse_wc_output(loc_result.stdout)

        # Cyclomatic complexity
        complexity_result = self.run_command(["radon", "cc", "-s", "."], cwd=repo_path)
        if complexity_result.success:
            metrics["complexity"] = complexity_result.stdout

        # Maintainability index
        mi_result = self.run_command(["radon", "mi", "."], cwd=repo_path)
        if mi_result.success:
            metrics["maintainability"] = mi_result.stdout

        # Raw metrics (SLOC, comments, etc.)
        raw_result = self.run_command(["radon", "raw", "."], cwd=repo_path)
        if raw_result.success:
            metrics["raw_metrics"] = raw_result.stdout

        output = json.dumps(metrics, indent=2)

        return AiderResult.success_result(stdout=output, command="analyze_code_metrics")

    def _parse_wc_output(self, output: str) -> Dict[str, int]:
        """Parse wc command output to extract line counts."""
        lines = output.strip().split("\n")
        total_lines = 0
        file_count = 0

        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[0].isdigit():
                total_lines += int(parts[0])
                file_count += 1

        return {
            "total_lines": total_lines,
            "file_count": file_count,
            "average_lines_per_file": (
                total_lines // file_count if file_count > 0 else 0
            ),
        }

    def generate_project_summary(
        self,
        repo_path: str,
        output_file: str = "PROJECT_SUMMARY.md",
        include_metrics: bool = True,
        include_dependencies: bool = True,
        include_todos: bool = True,
    ) -> AiderResult:
        """Generate a comprehensive project summary."""
        summary_sections = []

        # Basic project info
        project_name = os.path.basename(repo_path)
        summary_sections.append(f"# {project_name} - Project Summary\n")

        # Project structure
        structure = self._analyze_project_structure(repo_path)
        summary_sections.append("## Project Structure\n")
        summary_sections.append(f"```\n{structure}\n```\n")

        # Key files analysis
        key_files = self._identify_key_files(repo_path)
        if key_files:
            summary_sections.append("## Key Files\n")
            for file_info in key_files:
                summary_sections.append(
                    f"- **{file_info['path']}**: {file_info['description']}\n"
                )

        # Dependencies analysis
        if include_dependencies:
            dep_result = self.analyze_dependencies(repo_path)
            if dep_result.success:
                summary_sections.append("## Dependencies\n")
                summary_sections.append(f"```\n{dep_result.stdout}\n```\n")

        # Code metrics
        if include_metrics:
            metrics_result = self.analyze_code_metrics(repo_path)
            if metrics_result.success:
                summary_sections.append("## Code Metrics\n")
                summary_sections.append(f"```json\n{metrics_result.stdout}\n```\n")

        # TODO items
        if include_todos:
            todos_result = self.find_todos(repo_path)
            if todos_result.success and todos_result.stdout.strip():
                summary_sections.append("## TODO Items\n")
                summary_sections.append(f"```\n{todos_result.stdout}\n```\n")

        # Technology stack
        tech_stack = self._detect_technology_stack(repo_path)
        if tech_stack:
            summary_sections.append("## Technology Stack\n")
            for tech in tech_stack:
                summary_sections.append(f"- {tech}\n")

        # Combine all sections
        summary_content = "\n".join(summary_sections)

        # Write to file
        try:
            full_path = os.path.join(repo_path, output_file)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(summary_content)

            return AiderResult.success_result(
                stdout=f"Project summary generated: {output_file}",
                command=f"generate_project_summary {output_file}",
            )
        except Exception as e:
            return AiderResult.error_result(
                error_message=str(e), command=f"generate_project_summary {output_file}"
            )

    def _analyze_project_structure(self, repo_path: str) -> str:
        """Analyze and return project directory structure."""
        result = self.run_command(
            ["tree", "-L", "3", "-I", "__pycache__|*.pyc|.git"], cwd=repo_path
        )
        if result.success:
            return result.stdout

        # Fallback to find if tree is not available
        result = self.run_command(
            [
                "find",
                ".",
                "-type",
                "d",
                "-not",
                "-path",
                "./.git*",
                "-not",
                "-path",
                "./__pycache__*",
            ],
            cwd=repo_path,
        )
        return result.stdout if result.success else "Could not analyze structure"

    def _identify_key_files(self, repo_path: str) -> List[Dict[str, str]]:
        """Identify and describe key files in the project."""
        key_files = []

        common_files = {
            "README.md": "Project documentation and overview",
            "README.rst": "Project documentation and overview",
            "setup.py": "Python package setup and installation",
            "pyproject.toml": "Python project configuration",
            "requirements.txt": "Python dependencies",
            "Pipfile": "Pipenv dependencies",
            "package.json": "Node.js dependencies and scripts",
            "Dockerfile": "Docker container configuration",
            "docker-compose.yml": "Docker Compose configuration",
            "Makefile": "Build automation scripts",
            ".github/workflows": "GitHub Actions CI/CD workflows",
            "tests/": "Test files directory",
            "src/": "Source code directory",
            "docs/": "Documentation directory",
        }

        for file_path, description in common_files.items():
            full_path = os.path.join(repo_path, file_path)
            if os.path.exists(full_path):
                key_files.append({"path": file_path, "description": description})

        return key_files

    def _detect_technology_stack(self, repo_path: str) -> List[str]:
        """Detect the technology stack used in the project."""
        technologies = []

        # Check for various technology indicators
        if (
            os.path.exists(os.path.join(repo_path, "setup.py"))
            or os.path.exists(os.path.join(repo_path, "pyproject.toml"))
            or any(f.endswith(".py") for f in os.listdir(repo_path))
        ):
            technologies.append("Python")

        if os.path.exists(os.path.join(repo_path, "package.json")):
            technologies.append("Node.js/JavaScript")

        if os.path.exists(os.path.join(repo_path, "go.mod")):
            technologies.append("Go")

        if os.path.exists(os.path.join(repo_path, "Cargo.toml")):
            technologies.append("Rust")

        if os.path.exists(os.path.join(repo_path, "pom.xml")):
            technologies.append("Java (Maven)")

        if os.path.exists(os.path.join(repo_path, "build.gradle")):
            technologies.append("Java/Kotlin (Gradle)")

        if os.path.exists(os.path.join(repo_path, "Gemfile")):
            technologies.append("Ruby")

        if os.path.exists(os.path.join(repo_path, "composer.json")):
            technologies.append("PHP")

        if os.path.exists(os.path.join(repo_path, "Dockerfile")):
            technologies.append("Docker")

        if os.path.exists(os.path.join(repo_path, "docker-compose.yml")):
            technologies.append("Docker Compose")

        return technologies

    def find_large_files(
        self,
        repo_path: str,
        size_threshold: str = "10M",
        exclude_patterns: List[str] = None,
    ) -> AiderResult:
        """Find large files in the repository."""
        if exclude_patterns is None:
            exclude_patterns = [".git", "__pycache__", "node_modules", "*.pyc"]

        cmd = ["find", ".", "-type", "f", "-size", f"+{size_threshold}"]

        # Add exclusions
        for pattern in exclude_patterns:
            cmd.extend(["-not", "-path", f"*/{pattern}/*"])

        return self.run_command(cmd, cwd=repo_path)

    def analyze_git_history(self, repo_path: str, limit: int = 100) -> AiderResult:
        """Analyze git commit history for patterns and statistics."""
        # Get commit statistics
        cmd = [
            "git",
            "log",
            f"--max-count={limit}",
            "--pretty=format:%h|%an|%ad|%s",
            "--date=short",
        ]

        result = self.run_command(cmd, cwd=repo_path)

        if result.success:
            # Parse and analyze the commit data
            commits = []
            for line in result.stdout.strip().split("\n"):
                if "|" in line:
                    parts = line.split("|", 3)
                    if len(parts) == 4:
                        commits.append(
                            {
                                "hash": parts[0],
                                "author": parts[1],
                                "date": parts[2],
                                "message": parts[3],
                            }
                        )

            # Generate statistics
            analysis = self._analyze_commit_data(commits)
            result.stdout = json.dumps(analysis, indent=2)

        return result

    def _analyze_commit_data(self, commits: List[Dict[str, str]]) -> Dict[str, Any]:
        """Analyze commit data and generate statistics."""
        if not commits:
            return {"error": "No commits found"}

        # Author statistics
        authors = {}
        for commit in commits:
            author = commit["author"]
            if author not in authors:
                authors[author] = 0
            authors[author] += 1

        # Most active authors
        top_authors = sorted(authors.items(), key=lambda x: x[1], reverse=True)[:5]

        # Date range
        dates = [commit["date"] for commit in commits]
        date_range = {"earliest": min(dates), "latest": max(dates)}

        return {
            "total_commits": len(commits),
            "unique_authors": len(authors),
            "top_authors": [
                {"author": author, "commits": count} for author, count in top_authors
            ],
            "date_range": date_range,
            "recent_activity": commits[:10],  # Last 10 commits
        }
