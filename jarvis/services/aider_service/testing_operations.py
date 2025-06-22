"""
Testing and quality operations for the Aider CLI Service.

This module provides comprehensive testing, linting, and code quality
operations including test execution, coverage analysis, and static analysis.
"""

import os
import shlex
import re
from typing import List, Optional, Dict, Any

from .types import AiderResult
from .executor import BaseExecutor


class TestingOperations(BaseExecutor):
    """Testing and quality operations handler"""

    def run_tests(
        self,
        repo_path: str,
        test_command: Optional[str] = None,
        test_path: Optional[str] = None,
        verbose: bool = False,
        timeout: Optional[float] = None,
    ) -> AiderResult:
        """Run tests using various test frameworks."""
        if test_command:
            cmd = shlex.split(test_command)
        else:
            # Auto-detect test framework
            cmd = self._detect_test_command(repo_path)

        if test_path:
            cmd.append(test_path)

        if verbose:
            if "pytest" in cmd[0]:
                cmd.append("-v")
            elif "unittest" in cmd:
                cmd.append("-v")

        return self.run_command(cmd, cwd=repo_path, timeout=timeout)

    def _detect_test_command(self, repo_path: str) -> List[str]:
        """Auto-detect the appropriate test command for the project."""
        # Check for pytest
        if os.path.exists(os.path.join(repo_path, "pytest.ini")) or os.path.exists(
            os.path.join(repo_path, "pyproject.toml")
        ):
            return ["pytest"]

        # Check for unittest in setup.py or test files
        if os.path.exists(os.path.join(repo_path, "setup.py")):
            return ["python", "-m", "pytest"]

        # Check for Node.js projects
        if os.path.exists(os.path.join(repo_path, "package.json")):
            return ["npm", "test"]

        # Check for Go projects
        if any(f.endswith(".go") for f in os.listdir(repo_path)):
            return ["go", "test", "./..."]

        # Check for Rust projects
        if os.path.exists(os.path.join(repo_path, "Cargo.toml")):
            return ["cargo", "test"]

        # Default to Python unittest
        return ["python", "-m", "unittest", "discover"]

    def run_coverage(
        self,
        repo_path: str,
        coverage_command: Optional[str] = None,
        min_coverage: Optional[float] = None,
        report_format: str = "term",  # term, html, xml
        output_file: Optional[str] = None,
    ) -> AiderResult:
        """Run test coverage analysis."""
        if coverage_command:
            cmd = shlex.split(coverage_command)
        else:
            # Default coverage command
            cmd = ["pytest", "--cov=.", f"--cov-report={report_format}"]

            if output_file and report_format in ["html", "xml"]:
                cmd.append(f"--cov-report={report_format}:{output_file}")

        result = self.run_command(cmd, cwd=repo_path)

        # Check if coverage meets minimum requirement
        if result.success and min_coverage:
            coverage_percent = self._parse_coverage_percentage(result.stdout)
            if coverage_percent is not None and coverage_percent < min_coverage:
                result.success = False
                result.error_message = (
                    f"Coverage {coverage_percent}% is below minimum {min_coverage}%"
                )

        return result

    def _parse_coverage_percentage(self, output: str) -> Optional[float]:
        """Parse coverage percentage from test output."""
        # Look for pytest-cov format
        match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
        if match:
            return float(match.group(1))

        # Look for coverage.py format
        match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)%", output)
        if match:
            return float(match.group(1))

        return None

    def run_linter(
        self,
        repo_path: str,
        linter: str = "flake8",
        file_paths: Optional[List[str]] = None,
        fix: bool = False,
        config_file: Optional[str] = None,
    ) -> AiderResult:
        """Run code linter."""
        if linter == "flake8":
            cmd = ["flake8"]
            if config_file:
                cmd.extend(["--config", config_file])
        elif linter == "pylint":
            cmd = ["pylint"]
            if config_file:
                cmd.extend(["--rcfile", config_file])
        elif linter == "black":
            cmd = ["black"]
            if not fix:
                cmd.append("--check")
            if config_file:
                cmd.extend(["--config", config_file])
        elif linter == "isort":
            cmd = ["isort"]
            if not fix:
                cmd.append("--check-only")
            if config_file:
                cmd.extend(["--settings-file", config_file])
        elif linter == "ruff":
            cmd = ["ruff", "check"]
            if fix:
                cmd.append("--fix")
            if config_file:
                cmd.extend(["--config", config_file])
        elif linter == "mypy":
            cmd = ["mypy"]
            if config_file:
                cmd.extend(["--config-file", config_file])
        else:
            return AiderResult.error_result(
                error_message=f"Unknown linter: {linter}",
                command=f"run_linter {linter}",
            )

        if file_paths:
            cmd.extend(file_paths)
        else:
            cmd.append(".")

        return self.run_command(cmd, cwd=repo_path)

    def run_formatter(
        self,
        repo_path: str,
        formatter: str = "black",
        file_paths: Optional[List[str]] = None,
        check_only: bool = False,
        config_file: Optional[str] = None,
    ) -> AiderResult:
        """Run code formatter."""
        if formatter == "black":
            cmd = ["black"]
            if check_only:
                cmd.append("--check")
            if config_file:
                cmd.extend(["--config", config_file])
        elif formatter == "autopep8":
            cmd = ["autopep8"]
            if not check_only:
                cmd.append("--in-place")
            if config_file:
                cmd.extend(["--global-config", config_file])
        elif formatter == "yapf":
            cmd = ["yapf"]
            if not check_only:
                cmd.append("--in-place")
            if config_file:
                cmd.extend(["--style", config_file])
        elif formatter == "isort":
            cmd = ["isort"]
            if check_only:
                cmd.append("--check-only")
        else:
            return AiderResult.error_result(
                error_message=f"Unknown formatter: {formatter}",
                command=f"run_formatter {formatter}",
            )

        if file_paths:
            cmd.extend(file_paths)
        else:
            cmd.append(".")

        return self.run_command(cmd, cwd=repo_path)

    def run_type_check(
        self,
        repo_path: str,
        type_checker: str = "mypy",
        file_paths: Optional[List[str]] = None,
        config_file: Optional[str] = None,
        strict: bool = False,
    ) -> AiderResult:
        """Run static type checking."""
        if type_checker == "mypy":
            cmd = ["mypy"]
            if strict:
                cmd.append("--strict")
            if config_file:
                cmd.extend(["--config-file", config_file])
        elif type_checker == "pyright":
            cmd = ["pyright"]
        elif type_checker == "pyre":
            cmd = ["pyre", "check"]
        else:
            return AiderResult.error_result(
                error_message=f"Unknown type checker: {type_checker}",
                command=f"run_type_check {type_checker}",
            )

        if file_paths:
            cmd.extend(file_paths)
        else:
            cmd.append(".")

        return self.run_command(cmd, cwd=repo_path)

    def run_security_scan(
        self,
        repo_path: str,
        scanner: str = "bandit",
        file_paths: Optional[List[str]] = None,
        config_file: Optional[str] = None,
    ) -> AiderResult:
        """Run security vulnerability scanning."""
        if scanner == "bandit":
            cmd = ["bandit", "-r"]
            if config_file:
                cmd.extend(["-c", config_file])
        elif scanner == "safety":
            cmd = ["safety", "check"]
        elif scanner == "semgrep":
            cmd = ["semgrep", "--config=auto"]
        else:
            return AiderResult.error_result(
                error_message=f"Unknown security scanner: {scanner}",
                command=f"run_security_scan {scanner}",
            )

        if file_paths and scanner == "bandit":
            cmd.extend(file_paths)
        elif not file_paths and scanner == "bandit":
            cmd.append(".")

        return self.run_command(cmd, cwd=repo_path)

    def run_complexity_analysis(
        self,
        repo_path: str,
        analyzer: str = "radon",
        file_paths: Optional[List[str]] = None,
        threshold: Optional[int] = None,
    ) -> AiderResult:
        """Run code complexity analysis."""
        if analyzer == "radon":
            cmd = ["radon", "cc"]
            if threshold:
                cmd.extend(["-n", str(threshold)])
        elif analyzer == "xenon":
            cmd = ["xenon"]
            if threshold:
                cmd.extend(["--max-average", str(threshold)])
        else:
            return AiderResult.error_result(
                error_message=f"Unknown complexity analyzer: {analyzer}",
                command=f"run_complexity_analysis {analyzer}",
            )

        if file_paths:
            cmd.extend(file_paths)
        else:
            cmd.append(".")

        return self.run_command(cmd, cwd=repo_path)

    def run_performance_test(
        self,
        repo_path: str,
        test_command: Optional[str] = None,
        benchmark_file: Optional[str] = None,
        iterations: int = 10,
    ) -> AiderResult:
        """Run performance/benchmark tests."""
        if test_command:
            cmd = shlex.split(test_command)
        elif benchmark_file:
            cmd = ["python", benchmark_file]
        else:
            # Look for pytest-benchmark
            cmd = ["pytest", "--benchmark-only", f"--benchmark-rounds={iterations}"]

        return self.run_command(cmd, cwd=repo_path)

    def generate_test_report(
        self,
        repo_path: str,
        output_file: str = "test_report.html",
        include_coverage: bool = True,
        include_lint: bool = True,
        include_security: bool = True,
    ) -> AiderResult:
        """Generate a comprehensive test report."""
        report_sections = []

        # Run tests
        test_result = self.run_tests(repo_path, verbose=True)
        report_sections.append(f"## Test Results\n```\n{test_result.stdout}\n```\n")

        if include_coverage:
            coverage_result = self.run_coverage(repo_path, report_format="term")
            if coverage_result.success:
                report_sections.append(
                    f"## Coverage Report\n```\n{coverage_result.stdout}\n```\n"
                )

        if include_lint:
            lint_result = self.run_linter(repo_path)
            report_sections.append(
                f"## Lint Results\n```\n{lint_result.stdout or 'No issues found'}\n```\n"
            )

        if include_security:
            security_result = self.run_security_scan(repo_path)
            report_sections.append(
                f"## Security Scan\n```\n{security_result.stdout or 'No issues found'}\n```\n"
            )

        # Combine report sections
        report_content = f"""# Test Report
Generated for repository: {os.path.basename(repo_path)}

{''.join(report_sections)}
"""

        # Write report to file
        try:
            full_path = os.path.join(repo_path, output_file)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(report_content)

            return AiderResult.success_result(
                stdout=f"Test report generated: {output_file}",
                command=f"generate_test_report {output_file}",
            )
        except Exception as e:
            return AiderResult.error_result(
                error_message=str(e), command=f"generate_test_report {output_file}"
            )

    def validate_code_quality(
        self,
        repo_path: str,
        min_coverage: Optional[float] = None,
        max_complexity: Optional[int] = None,
        allow_lint_warnings: bool = True,
    ) -> AiderResult:
        """Validate overall code quality against criteria."""
        issues = []

        # Check test coverage
        if min_coverage:
            coverage_result = self.run_coverage(repo_path)
            if coverage_result.success:
                coverage_percent = self._parse_coverage_percentage(
                    coverage_result.stdout
                )
                if coverage_percent is not None and coverage_percent < min_coverage:
                    issues.append(
                        f"Coverage {coverage_percent}% is below minimum {min_coverage}%"
                    )

        # Check code complexity
        if max_complexity:
            complexity_result = self.run_complexity_analysis(
                repo_path, threshold=max_complexity
            )
            if not complexity_result.success:
                issues.append(
                    f"Code complexity exceeds maximum threshold of {max_complexity}"
                )

        # Check linting
        lint_result = self.run_linter(repo_path)
        if not lint_result.success and not allow_lint_warnings:
            issues.append("Linting issues found and warnings not allowed")

        # Check security
        security_result = self.run_security_scan(repo_path)
        if not security_result.success:
            issues.append("Security vulnerabilities detected")

        if issues:
            return AiderResult.error_result(
                error_message="; ".join(issues), command="validate_code_quality"
            )
        else:
            return AiderResult.success_result(
                stdout="All code quality checks passed", command="validate_code_quality"
            )

        return self.run_command(cmd, cwd=repo_path, timeout=timeout)

    def _detect_test_command(self, repo_path: str) -> List[str]:
        """Auto-detect the appropriate test command for the project."""
        # Check for pytest
        if os.path.exists(os.path.join(repo_path, "pytest.ini")) or os.path.exists(
            os.path.join(repo_path, "pyproject.toml")
        ):
            return ["pytest"]

        # Check for unittest in setup.py or test files
        if os.path.exists(os.path.join(repo_path, "setup.py")):
            return ["python", "-m", "pytest"]

        # Check for Node.js projects
        if os.path.exists(os.path.join(repo_path, "package.json")):
            return ["npm", "test"]

        # Check for Go projects
        if any(f.endswith(".go") for f in os.listdir(repo_path)):
            return ["go", "test", "./..."]

        # Check for Rust projects
        if os.path.exists(os.path.join(repo_path, "Cargo.toml")):
            return ["cargo", "test"]

        # Default to Python unittest
        return ["python", "-m", "unittest", "discover"]

    def run_coverage(
        self,
        repo_path: str,
        coverage_command: Optional[str] = None,
        min_coverage: Optional[float] = None,
        report_format: str = "term",  # term, html, xml
        output_file: Optional[str] = None,
    ) -> AiderResult:
        """Run test coverage analysis."""
        if coverage_command:
            cmd = shlex.split(coverage_command)
        else:
            # Default coverage command
            cmd = ["pytest", "--cov=.", f"--cov-report={report_format}"]

            if output_file and report_format in ["html", "xml"]:
                cmd.append(f"--cov-report={report_format}:{output_file}")

        result = self.run_command(cmd, cwd=repo_path)

        # Check if coverage meets minimum requirement
        if result.success and min_coverage:
            coverage_percent = self._parse_coverage_percentage(result.stdout)
            if coverage_percent is not None and coverage_percent < min_coverage:
                result.success = False
                result.error_message = (
                    f"Coverage {coverage_percent}% is below minimum {min_coverage}%"
                )

        return result

    def _parse_coverage_percentage(self, output: str) -> Optional[float]:
        """Parse coverage percentage from test output."""
        # Look for pytest-cov format
        match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
        if match:
            return float(match.group(1))

        # Look for coverage.py format
        match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)%", output)
        if match:
            return float(match.group(1))

        return None

    def run_linter(
        self,
        repo_path: str,
        linter: str = "flake8",
        file_paths: Optional[List[str]] = None,
        fix: bool = False,
        config_file: Optional[str] = None,
    ) -> AiderResult:
        """Run code linter."""
        if linter == "flake8":
            cmd = ["flake8"]
            if config_file:
                cmd.extend(["--config", config_file])
        elif linter == "pylint":
            cmd = ["pylint"]
            if config_file:
                cmd.extend(["--rcfile", config_file])
        elif linter == "black":
            cmd = ["black"]
            if not fix:
                cmd.append("--check")
            if config_file:
                cmd.extend(["--config", config_file])
        elif linter == "isort":
            cmd = ["isort"]
            if not fix:
                cmd.append("--check-only")
            if config_file:
                cmd.extend(["--settings-file", config_file])
        elif linter == "ruff":
            cmd = ["ruff", "check"]
            if fix:
                cmd.append("--fix")
            if config_file:
                cmd.extend(["--config", config_file])
        elif linter == "mypy":
            cmd = ["mypy"]
            if config_file:
                cmd.extend(["--config-file", config_file])
        else:
            return AiderResult.error_result(
                error_message=f"Unknown linter: {linter}",
                command=f"run_linter {linter}",
            )

        if file_paths:
            cmd.extend(file_paths)
        else:
            cmd.append(".")

        return self.run_command(cmd, cwd=repo_path)

    def run_formatter(
        self,
        repo_path: str,
        formatter: str = "black",
        file_paths: Optional[List[str]] = None,
        check_only: bool = False,
        config_file: Optional[str] = None,
    ) -> AiderResult:
        """Run code formatter."""
        if formatter == "black":
            cmd = ["black"]
            if check_only:
                cmd.append("--check")
            if config_file:
                cmd.extend(["--config", config_file])
        elif formatter == "autopep8":
            cmd = ["autopep8"]
            if not check_only:
                cmd.append("--in-place")
            if config_file:
                cmd.extend(["--global-config", config_file])
        elif formatter == "yapf":
            cmd = ["yapf"]
            if not check_only:
                cmd.append("--in-place")
            if config_file:
                cmd.extend(["--style", config_file])
        elif formatter == "isort":
            cmd = ["isort"]
            if check_only:
                cmd.append("--check-only")
        else:
            return AiderResult.error_result(
                error_message=f"Unknown formatter: {formatter}",
                command=f"run_formatter {formatter}",
            )

        if file_paths:
            cmd.extend(file_paths)
        else:
            cmd.append(".")

        return self.run_command(cmd, cwd=repo_path)

    def run_type_check(
        self,
        repo_path: str,
        type_checker: str = "mypy",
        file_paths: Optional[List[str]] = None,
        config_file: Optional[str] = None,
        strict: bool = False,
    ) -> AiderResult:
        """Run static type checking."""
        if type_checker == "mypy":
            cmd = ["mypy"]
            if strict:
                cmd.append("--strict")
            if config_file:
                cmd.extend(["--config-file", config_file])
        elif type_checker == "pyright":
            cmd = ["pyright"]
        elif type_checker == "pyre":
            cmd = ["pyre", "check"]
        else:
            return AiderResult.error_result(
                error_message=f"Unknown type checker: {type_checker}",
                command=f"run_type_check {type_checker}",
            )

        if file_paths:
            cmd.extend(file_paths)
        else:
            cmd.append(".")

        return self.run_command(cmd, cwd=repo_path)

    def run_security_scan(
        self,
        repo_path: str,
        scanner: str = "bandit",
        file_paths: Optional[List[str]] = None,
        config_file: Optional[str] = None,
    ) -> AiderResult:
        """Run security vulnerability scanning."""
        if scanner == "bandit":
            cmd = ["bandit", "-r"]
            if config_file:
                cmd.extend(["-c", config_file])
        elif scanner == "safety":
            cmd = ["safety", "check"]
        elif scanner == "semgrep":
            cmd = ["semgrep", "--config=auto"]
        else:
            return AiderResult.error_result(
                error_message=f"Unknown security scanner: {scanner}",
                command=f"run_security_scan {scanner}",
            )

        if file_paths and scanner == "bandit":
            cmd.extend(file_paths)
        elif not file_paths and scanner == "bandit":
            cmd.append(".")

        return self.run_command(cmd, cwd=repo_path)

    def run_complexity_analysis(
        self,
        repo_path: str,
        analyzer: str = "radon",
        file_paths: Optional[List[str]] = None,
        threshold: Optional[int] = None,
    ) -> AiderResult:
        """Run code complexity analysis."""
        if analyzer == "radon":
            cmd = ["radon", "cc"]
            if threshold:
                cmd.extend(["-n", str(threshold)])
        elif analyzer == "xenon":
            cmd = ["xenon"]
            if threshold:
                cmd.extend(["--max-average", str(threshold)])
        else:
            return AiderResult.error_result(
                error_message=f"Unknown complexity analyzer: {analyzer}",
                command=f"run_complexity_analysis {analyzer}",
            )

        if file_paths:
            cmd.extend(file_paths)
        else:
            cmd.append(".")

        return self.run_command(cmd, cwd=repo_path)

    def run_performance_test(
        self,
        repo_path: str,
        test_command: Optional[str] = None,
        benchmark_file: Optional[str] = None,
        iterations: int = 10,
    ) -> AiderResult:
        """Run performance/benchmark tests."""
        if test_command:
            cmd = shlex.split(test_command)
        elif benchmark_file:
            cmd = ["python", benchmark_file]
        else:
            # Look for pytest-benchmark
            cmd = ["pytest", "--benchmark-only", f"--benchmark-rounds={iterations}"]

        return self.run_command(cmd, cwd=repo_path)

    def generate_test_report(
        self,
        repo_path: str,
        output_file: str = "test_report.html",
        include_coverage: bool = True,
        include_lint: bool = True,
        include_security: bool = True,
    ) -> AiderResult:
        """Generate a comprehensive test report."""
        report_sections = []

        # Run tests
        test_result = self.run_tests(repo_path, verbose=True)
        report_sections.append(f"## Test Results\n```\n{test_result.stdout}\n```\n")

        if include_coverage:
            coverage_result = self.run_coverage(repo_path, report_format="term")
            if coverage_result.success:
                report_sections.append(
                    f"## Coverage Report\n```\n{coverage_result.stdout}\n```\n"
                )

        if include_lint:
            lint_result = self.run_linter(repo_path)
            report_sections.append(
                f"## Lint Results\n```\n{lint_result.stdout or 'No issues found'}\n```\n"
            )

        if include_security:
            security_result = self.run_security_scan(repo_path)
            report_sections.append(
                f"## Security Scan\n```\n{security_result.stdout or 'No issues found'}\n```\n"
            )

        # Combine report sections
        report_content = f"""# Test Report
Generated for repository: {os.path.basename(repo_path)}

{''.join(report_sections)}
"""

        # Write report to file
        try:
            full_path = os.path.join(repo_path, output_file)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(report_content)

            return AiderResult.success_result(
                stdout=f"Test report generated: {output_file}",
                command=f"generate_test_report {output_file}",
            )
        except Exception as e:
            return AiderResult.error_result(
                error_message=str(e), command=f"generate_test_report {output_file}"
            )

    def validate_code_quality(
        self,
        repo_path: str,
        min_coverage: Optional[float] = None,
        max_complexity: Optional[int] = None,
        allow_lint_warnings: bool = True,
    ) -> AiderResult:
        """Validate overall code quality against criteria."""
        issues = []

        # Check test coverage
        if min_coverage:
            coverage_result = self.run_coverage(repo_path)
            if coverage_result.success:
                coverage_percent = self._parse_coverage_percentage(
                    coverage_result.stdout
                )
                if coverage_percent is not None and coverage_percent < min_coverage:
                    issues.append(
                        f"Coverage {coverage_percent}% is below minimum {min_coverage}%"
                    )

        # Check code complexity
        if max_complexity:
            complexity_result = self.run_complexity_analysis(
                repo_path, threshold=max_complexity
            )
            if not complexity_result.success:
                issues.append(
                    f"Code complexity exceeds maximum threshold of {max_complexity}"
                )

        # Check linting
        lint_result = self.run_linter(repo_path)
        if not lint_result.success and not allow_lint_warnings:
            issues.append("Linting issues found and warnings not allowed")

        # Check security
        security_result = self.run_security_scan(repo_path)
        if not security_result.success:
            issues.append("Security vulnerabilities detected")

        if issues:
            return AiderResult.error_result(
                error_message="; ".join(issues), command="validate_code_quality"
            )
        else:
            return AiderResult.success_result(
                stdout="All code quality checks passed", command="validate_code_quality"
            )
