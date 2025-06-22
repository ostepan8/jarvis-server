"""
Base command executor for running subprocess commands.

This module provides the core functionality for executing commands
and capturing their results in a structured format.
"""

import subprocess
import os
import shlex
import time
from typing import Dict, List, Optional, Any
from .types import AiderResult


class BaseExecutor:
    """Base class for executing subprocess commands"""

    def __init__(self, default_timeout: float = 300.0, verbose: bool = False):
        """
        Initialize the base executor.

        Args:
            default_timeout: Default timeout for subprocess calls in seconds
            verbose: Whether to enable verbose output
        """
        self.default_timeout = default_timeout
        self.verbose = verbose

    def run_command(
        self,
        command: List[str],
        cwd: Optional[str] = None,
        timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
        input_text: Optional[str] = None,
    ) -> AiderResult:
        """
        Execute a command and capture results.

        Args:
            command: Command arguments list
            cwd: Working directory for the command
            timeout: Command timeout in seconds
            env: Environment variables
            input_text: Text to send to stdin

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

        if self.verbose:
            print(f"Executing: {cmd_str}")
            if cwd:
                print(f"Working directory: {cwd}")

        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout,
                env=cmd_env,
                input=input_text,
            )

            duration = time.time() - start_time
            success = process.returncode == 0

            if self.verbose:
                print(
                    f"Command completed in {duration:.2f}s with exit code {process.returncode}"
                )

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
            error_msg = f"Command timed out after {timeout} seconds"

            if self.verbose:
                print(error_msg)

            return AiderResult(
                success=False,
                stdout="",
                stderr=error_msg,
                exit_code=-1,
                command=cmd_str,
                duration=duration,
                error_message=error_msg,
            )

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Execution error: {str(e)}"

            if self.verbose:
                print(error_msg)

            return AiderResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                command=cmd_str,
                duration=duration,
                error_message=error_msg,
            )

    def verify_command_available(
        self, command: str, version_arg: str = "--version"
    ) -> bool:
        """
        Verify that a command is available and executable.

        Args:
            command: Command to verify
            version_arg: Argument to check version (default: --version)

        Returns:
            True if command is available, False otherwise
        """
        try:
            result = subprocess.run(
                [command, version_arg], capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
