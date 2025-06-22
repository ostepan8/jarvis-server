"""
Core Aider CLI operations and AI-powered code tasks.

This module handles direct interactions with the aider CLI tool
for AI-powered code generation, modification, and analysis.
"""

import os
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from .types import AiderMode, AiderResult, AiderNotFoundError
from .executor import BaseExecutor


class AiderCore(BaseExecutor):
    """Core Aider CLI operations"""

    def __init__(
        self,
        aider_executable: str = "aider",
        default_model: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize Aider core operations.

        Args:
            aider_executable: Path to aider executable
            default_model: Default AI model to use
            **kwargs: Additional arguments for BaseExecutor
        """
        super().__init__(**kwargs)
        self.aider_executable = aider_executable
        self.default_model = default_model

        # Verify aider is available
        self._verify_aider_installation()

    def _verify_aider_installation(self) -> None:
        """Verify that aider is installed and accessible"""
        if not self.verify_command_available(self.aider_executable):
            raise AiderNotFoundError(
                f"Aider not found at '{self.aider_executable}'. "
                "Please ensure aider is installed and in PATH."
            )

    def _build_aider_command(
        self,
        mode: AiderMode,
        message: Optional[str] = None,
        files: Optional[List[str]] = None,
        extra_args: Optional[List[str]] = None,
        yes: bool = False,
        no_git: bool = False,
        model: Optional[str] = None,
    ) -> List[str]:
        """Build aider command with appropriate arguments."""
        cmd = [self.aider_executable]

        if model or self.default_model:
            cmd.extend(["--model", model or self.default_model])

        if mode == AiderMode.MESSAGE and message:
            cmd.extend(["--message", message])
        elif mode == AiderMode.COMMIT:
            cmd.append("--commit")
        elif mode == AiderMode.TEST:
            cmd.append("--test")
        elif mode == AiderMode.LINT:
            cmd.append("--lint")

        if yes or mode == AiderMode.YES:
            cmd.append("--yes")

        if no_git:
            cmd.append("--no-git")

        if self.verbose:
            cmd.append("--verbose")

        if extra_args:
            cmd.extend(extra_args)

        if files:
            cmd.extend(files)

        return cmd

    def send_message(
        self,
        repo_path: str,
        message: str,
        files: Optional[List[str]] = None,
        auto_commit: bool = True,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> AiderResult:
        """
        Send a generic message to aider for any custom operation.

        Args:
            repo_path: Path to the repository
            message: Message to send to aider
            files: List of files to include in context
            auto_commit: Whether to auto-commit changes
            model: AI model to use
            timeout: Operation timeout
            **kwargs: Additional arguments for command building

        Returns:
            AiderResult with operation details
        """
        extra_args = []
        if not auto_commit:
            extra_args.append("--no-auto-commits")

        cmd = self._build_aider_command(
            mode=AiderMode.MESSAGE,
            message=message,
            files=files,
            yes=True,
            extra_args=extra_args,
            model=model,
            **kwargs,
        )

        return self.run_command(cmd, cwd=repo_path, timeout=timeout)

    def generate_function_in_file(
        self,
        repo_path: str,
        file_path: str,
        function_name: str,
        function_description: str,
        parameters: Optional[List[Dict[str, str]]] = None,
        return_type: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        timeout: Optional[float] = None,
    ) -> AiderResult:
        """Generate a new function in a specific file using aider."""
        prompt_parts = [
            f"Generate a new function named '{function_name}' in the file.",
            f"Function description: {function_description}",
        ]

        if parameters:
            param_str = ", ".join(
                f"{p['name']}: {p.get('type', 'Any')}" for p in parameters
            )
            prompt_parts.append(f"Parameters: {param_str}")

        if return_type:
            prompt_parts.append(f"Return type: {return_type}")

        if dependencies:
            prompt_parts.append(f"Required imports: {', '.join(dependencies)}")

        prompt = "\n".join(prompt_parts)

        return self.send_message(
            repo_path=repo_path, message=prompt, files=[file_path], timeout=timeout
        )

    def explain_code(
        self,
        repo_path: str,
        file_path: str,
        function_or_class_name: Optional[str] = None,
        line_range: Optional[Tuple[int, int]] = None,
        timeout: Optional[float] = None,
    ) -> AiderResult:
        """Explain code in a file or specific function/class."""
        prompt_parts = ["Please explain the following code:"]

        if function_or_class_name:
            prompt_parts.append(
                f"Focus on the '{function_or_class_name}' function/class"
            )
        elif line_range:
            prompt_parts.append(f"Focus on lines {line_range[0]} to {line_range[1]}")
        else:
            prompt_parts.append("Provide an overview of the entire file")

        prompt_parts.append(
            "Include information about purpose, logic flow, and key concepts."
        )

        prompt = "\n".join(prompt_parts)

        return self.send_message(
            repo_path=repo_path,
            message=prompt,
            files=[file_path],
            auto_commit=False,
            timeout=timeout,
        )

    def refactor_code(
        self,
        repo_path: str,
        file_path: str,
        refactor_description: str,
        preserve_functionality: bool = True,
        timeout: Optional[float] = None,
    ) -> AiderResult:
        """Refactor code based on description."""
        prompt_parts = [f"Refactor the code according to: {refactor_description}"]

        if preserve_functionality:
            prompt_parts.append("IMPORTANT: Preserve all existing functionality.")
            prompt_parts.append("Ensure the refactored code passes all existing tests.")

        prompt = "\n".join(prompt_parts)

        return self.send_message(
            repo_path=repo_path, message=prompt, files=[file_path], timeout=timeout
        )

    def write_tests(
        self,
        repo_path: str,
        source_file: str,
        test_file: Optional[str] = None,
        test_framework: str = "pytest",
        coverage_target: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> AiderResult:
        """Write tests for a source file."""
        if not test_file:
            source_path = Path(source_file)
            test_file = str(source_path.parent / f"test_{source_path.name}")

        prompt_parts = [
            f"Write comprehensive tests for the code in {source_file}.",
            f"Use the {test_framework} testing framework.",
            "Include unit tests, edge cases, and integration tests.",
        ]

        if coverage_target:
            prompt_parts.append(f"Aim for at least {coverage_target}% code coverage.")

        prompt = "\n".join(prompt_parts)

        files = [source_file]
        if os.path.exists(os.path.join(repo_path, test_file)):
            files.append(test_file)

        return self.send_message(
            repo_path=repo_path, message=prompt, files=files, timeout=timeout
        )

    def document_code(
        self,
        repo_path: str,
        file_path: str,
        doc_style: str = "google",
        include_examples: bool = True,
        timeout: Optional[float] = None,
    ) -> AiderResult:
        """Add or improve documentation for code."""
        prompt_parts = [
            f"Add comprehensive documentation to the code using {doc_style} style.",
            "Include module, class, and function docstrings with type hints.",
        ]

        if include_examples:
            prompt_parts.append("Include usage examples where helpful.")

        prompt = "\n".join(prompt_parts)

        return self.send_message(
            repo_path=repo_path, message=prompt, files=[file_path], timeout=timeout
        )

    def debug_code(
        self,
        repo_path: str,
        file_path: str,
        error_description: str,
        error_message: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> AiderResult:
        """Debug code issues using aider."""
        prompt_parts = [f"Debug and fix the following issue: {error_description}"]

        if error_message:
            prompt_parts.append(f"Error message: {error_message}")

        prompt_parts.append("Fix the bug while maintaining existing functionality.")

        prompt = "\n".join(prompt_parts)

        return self.send_message(
            repo_path=repo_path, message=prompt, files=[file_path], timeout=timeout
        )

    def optimize_code(
        self,
        repo_path: str,
        file_path: str,
        optimization_goals: str,
        timeout: Optional[float] = None,
    ) -> AiderResult:
        """Optimize code for performance or other metrics."""
        prompt = f"""
        Optimize the code for: {optimization_goals}
        
        Consider:
        - Time complexity improvements
        - Space complexity improvements
        - Code readability
        - Best practices
        
        Ensure optimized code maintains correctness.
        """

        return self.send_message(
            repo_path=repo_path, message=prompt, files=[file_path], timeout=timeout
        )

    def commit_changes(
        self,
        repo_path: str,
        commit_message: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> AiderResult:
        """Create a git commit using aider's commit functionality."""
        if commit_message:
            # Use manual commit message
            return self.send_message(
                repo_path=repo_path,
                message=f"Commit the current changes with message: {commit_message}",
                timeout=timeout,
            )
        else:
            # Use aider's auto-commit
            cmd = self._build_aider_command(mode=AiderMode.COMMIT, yes=True)
            return self.run_command(cmd, cwd=repo_path, timeout=timeout)
