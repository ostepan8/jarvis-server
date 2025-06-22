"""
Aider CLI Integration Layer for Software Engineering Agent

This module provides a subprocess-based integration with the aider CLI tool,
allowing the Software Engineering Agent to interact with aider exclusively
through command-line invocations.
"""

import subprocess
import json
import os
import tempfile
import shlex
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from pathlib import Path
import time
from enum import Enum


class AiderMode(Enum):
    """Aider interaction modes"""

    MESSAGE = "message"
    YES = "yes"
    COMMIT = "commit"
    TEST = "test"
    LINT = "lint"


@dataclass
class AiderResult:
    """Structured result from aider CLI invocation"""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    command: str
    duration: float
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary"""
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "command": self.command,
            "duration": self.duration,
            "error_message": self.error_message,
        }


class AiderCLIIntegration:
    """
    Integration layer for aider CLI tool via subprocess.

    This class provides a Python interface to aider's command-line tool,
    mapping agent capabilities to appropriate aider CLI commands.
    """

    def __init__(
        self,
        aider_executable: str = "aider",
        default_timeout: float = 300.0,
        default_model: Optional[str] = None,
        verbose: bool = False,
    ):
        """
        Initialize the aider CLI integration.

        Args:
            aider_executable: Path to aider executable (default: "aider")
            default_timeout: Default timeout for subprocess calls in seconds
            default_model: Default AI model to use with aider
            verbose: Whether to enable verbose output
        """
        self.aider_executable = aider_executable
        self.default_timeout = default_timeout
        self.default_model = default_model
        self.verbose = verbose

        # Verify aider is available
        self._verify_aider_installation()

    def _verify_aider_installation(self) -> None:
        """Verify that aider is installed and accessible"""
        try:
            result = subprocess.run(
                [self.aider_executable, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Aider verification failed: {result.stderr}")
        except FileNotFoundError:
            raise RuntimeError(
                f"Aider not found at '{self.aider_executable}'. "
                "Please ensure aider is installed and in PATH."
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Aider verification timed out")

    def _build_command(
        self,
        mode: AiderMode,
        message: Optional[str] = None,
        files: Optional[List[str]] = None,
        extra_args: Optional[List[str]] = None,
        yes: bool = False,
        no_git: bool = False,
        model: Optional[str] = None,
    ) -> List[str]:
        """
        Build aider command with appropriate arguments.

        Args:
            mode: The aider mode to use
            message: The message/prompt for aider
            files: List of file paths to include
            extra_args: Additional command-line arguments
            yes: Auto-confirm prompts
            no_git: Disable git integration
            model: AI model to use

        Returns:
            List of command arguments
        """
        cmd = [self.aider_executable]

        # Add model if specified
        if model or self.default_model:
            cmd.extend(["--model", model or self.default_model])

        # Add mode-specific arguments
        if mode == AiderMode.MESSAGE and message:
            cmd.extend(["--message", message])
        elif mode == AiderMode.COMMIT:
            cmd.append("--commit")
        elif mode == AiderMode.TEST:
            cmd.append("--test")
        elif mode == AiderMode.LINT:
            cmd.append("--lint")

        # Add common flags
        if yes or mode == AiderMode.YES:
            cmd.append("--yes")

        if no_git:
            cmd.append("--no-git")

        if self.verbose:
            cmd.append("--verbose")

        # Add any extra arguments
        if extra_args:
            cmd.extend(extra_args)

        # Add files at the end
        if files:
            cmd.extend(files)

        return cmd

    def _run_aider(
        self,
        command: List[str],
        cwd: Optional[str] = None,
        timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> AiderResult:
        """
        Execute aider command and capture results.

        Args:
            command: Command arguments list
            cwd: Working directory for the command
            timeout: Command timeout in seconds
            env: Environment variables

        Returns:
            AiderResult with execution details
        """
        timeout = timeout or self.default_timeout
        start_time = time.time()

        # Prepare environment
        cmd_env = os.environ.copy()
        if env:
            cmd_env.update(env)

        # Convert command to string for logging
        cmd_str = " ".join(shlex.quote(arg) for arg in command)

        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout,
                env=cmd_env,
            )

            duration = time.time() - start_time
            success = process.returncode == 0

            return AiderResult(
                success=success,
                stdout=process.stdout,
                stderr=process.stderr,
                exit_code=process.returncode,
                command=cmd_str,
                duration=duration,
                error_message=None if success else f"Exit code: {process.returncode}",
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return AiderResult(
                success=False,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
                exit_code=-1,
                command=cmd_str,
                duration=duration,
                error_message=f"Timeout after {timeout} seconds",
            )

        except Exception as e:
            duration = time.time() - start_time
            return AiderResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                command=cmd_str,
                duration=duration,
                error_message=f"Execution error: {str(e)}",
            )

    # Tool wrapper methods

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
        """
        Generate a new function in a specific file.

        Args:
            repo_path: Path to the repository root
            file_path: Relative path to the file within the repo
            function_name: Name of the function to generate
            function_description: Description of what the function should do
            parameters: List of parameter dicts with 'name' and 'type'
            return_type: Expected return type
            dependencies: List of required imports
            timeout: Operation timeout

        Returns:
            AiderResult with operation details
        """
        # Build the prompt
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

        # Build and execute command
        cmd = self._build_command(
            mode=AiderMode.MESSAGE, message=prompt, files=[file_path], yes=True
        )

        return self._run_aider(cmd, cwd=repo_path, timeout=timeout)

    def explain_code(
        self,
        repo_path: str,
        file_path: str,
        function_or_class_name: Optional[str] = None,
        line_range: Optional[Tuple[int, int]] = None,
        timeout: Optional[float] = None,
    ) -> AiderResult:
        """
        Explain code in a file or specific function/class.

        Args:
            repo_path: Path to the repository root
            file_path: Relative path to the file within the repo
            function_or_class_name: Specific function/class to explain
            line_range: Tuple of (start_line, end_line) to explain
            timeout: Operation timeout

        Returns:
            AiderResult with code explanation
        """
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

        cmd = self._build_command(
            mode=AiderMode.MESSAGE,
            message=prompt,
            files=[file_path],
            yes=True,
            extra_args=["--no-auto-commits"],
        )

        return self._run_aider(cmd, cwd=repo_path, timeout=timeout)

    def refactor_code(
        self,
        repo_path: str,
        file_path: str,
        refactor_description: str,
        preserve_functionality: bool = True,
        timeout: Optional[float] = None,
    ) -> AiderResult:
        """
        Refactor code based on description.

        Args:
            repo_path: Path to the repository root
            file_path: Relative path to the file within the repo
            refactor_description: Description of the refactoring to perform
            preserve_functionality: Whether to ensure functionality is preserved
            timeout: Operation timeout

        Returns:
            AiderResult with refactoring details
        """
        prompt_parts = [f"Refactor the code according to: {refactor_description}"]

        if preserve_functionality:
            prompt_parts.append("IMPORTANT: Preserve all existing functionality.")
            prompt_parts.append("Ensure the refactored code passes all existing tests.")

        prompt_parts.append("Apply best practices and improve code quality.")

        prompt = "\n".join(prompt_parts)

        cmd = self._build_command(
            mode=AiderMode.MESSAGE, message=prompt, files=[file_path], yes=True
        )

        return self._run_aider(cmd, cwd=repo_path, timeout=timeout)

    def write_tests(
        self,
        repo_path: str,
        source_file: str,
        test_file: Optional[str] = None,
        test_framework: str = "pytest",
        coverage_target: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> AiderResult:
        """
        Write tests for a source file.

        Args:
            repo_path: Path to the repository root
            source_file: Path to the source file to test
            test_file: Path to the test file (will be created/updated)
            test_framework: Testing framework to use
            coverage_target: Target test coverage percentage
            timeout: Operation timeout

        Returns:
            AiderResult with test generation details
        """
        # Determine test file path if not provided
        if not test_file:
            source_path = Path(source_file)
            test_file = str(source_path.parent / f"test_{source_path.name}")

        prompt_parts = [
            f"Write comprehensive tests for the code in {source_file}.",
            f"Use the {test_framework} testing framework.",
            "Include:",
            "- Unit tests for all functions and methods",
            "- Edge cases and error conditions",
            "- Integration tests where appropriate",
            "- Clear test names and documentation",
        ]

        if coverage_target:
            prompt_parts.append(f"Aim for at least {coverage_target}% code coverage.")

        prompt = "\n".join(prompt_parts)

        files = [source_file]
        if os.path.exists(os.path.join(repo_path, test_file)):
            files.append(test_file)

        cmd = self._build_command(
            mode=AiderMode.MESSAGE, message=prompt, files=files, yes=True
        )

        return self._run_aider(cmd, cwd=repo_path, timeout=timeout)

    def document_code(
        self,
        repo_path: str,
        file_path: str,
        doc_style: str = "google",
        include_examples: bool = True,
        timeout: Optional[float] = None,
    ) -> AiderResult:
        """
        Add or improve documentation for code.

        Args:
            repo_path: Path to the repository root
            file_path: Relative path to the file within the repo
            doc_style: Documentation style (google, numpy, sphinx)
            include_examples: Whether to include usage examples
            timeout: Operation timeout

        Returns:
            AiderResult with documentation details
        """
        prompt_parts = [
            f"Add comprehensive documentation to the code using {doc_style} style.",
            "Include:",
            "- Module-level docstring",
            "- Class docstrings with attributes",
            "- Function/method docstrings with parameters, returns, and raises",
            "- Type hints where missing",
        ]

        if include_examples:
            prompt_parts.append("- Usage examples in docstrings where helpful")

        prompt = "\n".join(prompt_parts)

        cmd = self._build_command(
            mode=AiderMode.MESSAGE, message=prompt, files=[file_path], yes=True
        )

        return self._run_aider(cmd, cwd=repo_path, timeout=timeout)

    def git_commit(
        self,
        repo_path: str,
        commit_message: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> AiderResult:
        """
        Create a git commit with changes.

        Args:
            repo_path: Path to the repository root
            commit_message: Custom commit message (aider will generate if None)
            timeout: Operation timeout

        Returns:
            AiderResult with commit details
        """
        if commit_message:
            cmd = self._build_command(
                mode=AiderMode.MESSAGE,
                message=f"Commit the changes with message: {commit_message}",
                yes=True,
                extra_args=["--commit"],
            )
        else:
            cmd = self._build_command(mode=AiderMode.COMMIT, yes=True)

        return self._run_aider(cmd, cwd=repo_path, timeout=timeout)

    def run_tests(
        self,
        repo_path: str,
        test_command: Optional[str] = None,
        fix_failures: bool = True,
        timeout: Optional[float] = None,
    ) -> AiderResult:
        """
        Run tests and optionally fix failures.

        Args:
            repo_path: Path to the repository root
            test_command: Custom test command (uses aider's default if None)
            fix_failures: Whether to attempt fixing test failures
            timeout: Operation timeout

        Returns:
            AiderResult with test execution details
        """
        extra_args = []

        if test_command:
            extra_args.extend(["--test-cmd", test_command])

        if fix_failures:
            message = "Run the tests and fix any failures"
            cmd = self._build_command(
                mode=AiderMode.MESSAGE,
                message=message,
                yes=True,
                extra_args=extra_args + ["--auto-test"],
            )
        else:
            cmd = self._build_command(
                mode=AiderMode.TEST, yes=True, extra_args=extra_args
            )

        return self._run_aider(cmd, cwd=repo_path, timeout=timeout)

    def generic_message(
        self,
        repo_path: str,
        message: str,
        files: Optional[List[str]] = None,
        auto_commit: bool = True,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> AiderResult:
        """
        Send a generic message to aider for any custom operation.

        Args:
            repo_path: Path to the repository root
            message: The message/prompt for aider
            files: List of files to include in context
            auto_commit: Whether to auto-commit changes
            timeout: Operation timeout
            **kwargs: Additional arguments passed to build_command

        Returns:
            AiderResult with operation details
        """
        extra_args = []
        if not auto_commit:
            extra_args.append("--no-auto-commits")

        cmd = self._build_command(
            mode=AiderMode.MESSAGE,
            message=message,
            files=files,
            yes=True,
            extra_args=extra_args,
            **kwargs,
        )

        return self._run_aider(cmd, cwd=repo_path, timeout=timeout)


# Example usage functions


def example_explain_code():
    """Example: Explain code in a file"""
    aider = AiderCLIIntegration(verbose=True)

    result = aider.explain_code(
        repo_path="/path/to/repo",
        file_path="src/main.py",
        function_or_class_name="process_data",
    )

    if result.success:
        print("Code explanation:")
        print(result.stdout)
    else:
        print(f"Error: {result.error_message}")
        print(f"Stderr: {result.stderr}")

    return result


def example_write_tests():
    """Example: Write tests for a module"""
    aider = AiderCLIIntegration(default_model="gpt-4")

    result = aider.write_tests(
        repo_path="/path/to/repo",
        source_file="src/calculator.py",
        test_file="tests/test_calculator.py",
        test_framework="pytest",
        coverage_target=90.0,
    )

    if result.success:
        print("Tests written successfully!")
        print(f"Output: {result.stdout}")
    else:
        print(f"Failed to write tests: {result.error_message}")

    return result


def example_git_commit():
    """Example: Commit changes with aider"""
    aider = AiderCLIIntegration()

    # Let aider generate the commit message
    result = aider.git_commit(repo_path="/path/to/repo")

    if result.success:
        print("Changes committed successfully!")
        print(f"Commit details: {result.stdout}")
    else:
        print(f"Commit failed: {result.error_message}")

    return result


"""
# Integration Guide

## Overview

The AiderCLIIntegration class provides a subprocess-based interface to the aider CLI tool,
enabling the Software Engineering Agent to interact with aider without direct Python imports.

## Architecture

1. **AiderResult**: Structured dataclass containing all execution details
2. **AiderCLIIntegration**: Main integration class with tool-specific methods
3. **Tool Wrappers**: Each agent capability maps to a specific method

## Extending the Integration

### Adding New Tool Wrappers

To add support for new aider features:

1. Create a new method in AiderCLIIntegration:
```python
def new_feature(self, repo_path: str, **kwargs) -> AiderResult:
    '''Docstring explaining the feature'''
    # Build appropriate prompt/command
    # Use self._build_command() and self._run_aider()
    # Return AiderResult
```

2. Map the appropriate aider CLI arguments
3. Handle tool-specific error cases
4. Document expected inputs and outputs

### Custom Aider Commands

For operations not covered by existing methods, use `generic_message()`:

```python
result = aider.generic_message(
    repo_path="/path/to/repo",
    message="Custom aider instruction",
    files=["file1.py", "file2.py"],
    extra_args=["--some-flag"]
)
```

## Usage in Agent

The agent can use these wrappers by:

1. Instantiating AiderCLIIntegration
2. Calling appropriate methods with repo context
3. Processing AiderResult for success/failure
4. Handling errors gracefully

## Error Handling

The integration handles several error scenarios:

1. **Aider not installed**: Caught during initialization
2. **Timeout**: Configurable per operation
3. **Non-zero exit codes**: Captured in AiderResult
4. **Subprocess errors**: Wrapped in structured response

## Configuration

Key configuration options:

- `aider_executable`: Path to aider binary
- `default_timeout`: Global timeout setting
- `default_model`: AI model preference
- `verbose`: Enable detailed output

## Best Practices

1. Always specify repo_path for consistent execution context
2. Use appropriate timeouts for long operations
3. Check result.success before processing output
4. Log commands for debugging (available in result.command)
5. Handle both stdout and stderr appropriately

## Limitations

- Requires aider CLI to be installed and accessible
- Interactive prompts are auto-confirmed with --yes flag
- Some agent tools may require multiple aider invocations
- File operations depend on aider's file handling capabilities

## Troubleshooting

Common issues and solutions:

1. **"Aider not found"**: Ensure aider is installed: `pip install aider-chat`
2. **Timeouts**: Increase timeout for complex operations
3. **Git errors**: Ensure repo has proper git configuration
4. **Model errors**: Verify API keys are configured for aider

"""
