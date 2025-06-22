"""
File system operations for the Aider CLI Service.

This module provides comprehensive file and directory operations
including reading, writing, searching, and manipulating files.
"""

import os
import shutil
import glob
from typing import List, Optional
from pathlib import Path

from .types import AiderResult, FileOperationError
from .executor import BaseExecutor


class FileOperations(BaseExecutor):
    """File system operations handler"""

    def read_file(
        self, repo_path: str, file_path: str, encoding: str = "utf-8"
    ) -> AiderResult:
        """Read contents of a file."""
        try:
            full_path = os.path.join(repo_path, file_path)

            if not os.path.exists(full_path):
                return AiderResult.error_result(
                    error_message=f"File not found: {file_path}",
                    command=f"read_file {file_path}",
                )

            with open(full_path, "r", encoding=encoding) as f:
                content = f.read()

            return AiderResult.success_result(
                stdout=content, command=f"read_file {file_path}"
            )

        except Exception as e:
            return AiderResult.error_result(
                error_message=str(e), command=f"read_file {file_path}"
            )

    def write_file(
        self,
        repo_path: str,
        file_path: str,
        content: str,
        encoding: str = "utf-8",
        create_dirs: bool = True,
    ) -> AiderResult:
        """Write content to a file."""
        try:
            full_path = os.path.join(repo_path, file_path)

            if create_dirs:
                os.makedirs(os.path.dirname(full_path), exist_ok=True)

            with open(full_path, "w", encoding=encoding) as f:
                f.write(content)

            return AiderResult.success_result(
                stdout=f"Successfully wrote to {file_path}",
                command=f"write_file {file_path}",
            )

        except Exception as e:
            return AiderResult.error_result(
                error_message=str(e), command=f"write_file {file_path}"
            )

    def create_file(
        self, repo_path: str, file_path: str, content: str = "", encoding: str = "utf-8"
    ) -> AiderResult:
        """Create a new file with optional content."""
        full_path = os.path.join(repo_path, file_path)

        if os.path.exists(full_path):
            return AiderResult.error_result(
                error_message=f"File already exists: {file_path}",
                command=f"create_file {file_path}",
            )

        return self.write_file(repo_path, file_path, content, encoding)

    def delete_file(self, repo_path: str, file_path: str) -> AiderResult:
        """Delete a file."""
        try:
            full_path = os.path.join(repo_path, file_path)

            if not os.path.exists(full_path):
                return AiderResult.error_result(
                    error_message=f"File not found: {file_path}",
                    command=f"delete_file {file_path}",
                )

            os.remove(full_path)

            return AiderResult.success_result(
                stdout=f"Successfully deleted {file_path}",
                command=f"delete_file {file_path}",
            )

        except Exception as e:
            return AiderResult.error_result(
                error_message=str(e), command=f"delete_file {file_path}"
            )

    def move_file(
        self, repo_path: str, source_path: str, dest_path: str
    ) -> AiderResult:
        """Move or rename a file."""
        try:
            full_source = os.path.join(repo_path, source_path)
            full_dest = os.path.join(repo_path, dest_path)

            if not os.path.exists(full_source):
                return AiderResult.error_result(
                    error_message=f"Source file not found: {source_path}",
                    command=f"move_file {source_path} {dest_path}",
                )

            os.makedirs(os.path.dirname(full_dest), exist_ok=True)
            shutil.move(full_source, full_dest)

            return AiderResult.success_result(
                stdout=f"Successfully moved {source_path} to {dest_path}",
                command=f"move_file {source_path} {dest_path}",
            )

        except Exception as e:
            return AiderResult.error_result(
                error_message=str(e), command=f"move_file {source_path} {dest_path}"
            )

    def copy_file(
        self, repo_path: str, source_path: str, dest_path: str
    ) -> AiderResult:
        """Copy a file."""
        try:
            full_source = os.path.join(repo_path, source_path)
            full_dest = os.path.join(repo_path, dest_path)

            if not os.path.exists(full_source):
                return AiderResult.error_result(
                    error_message=f"Source file not found: {source_path}",
                    command=f"copy_file {source_path} {dest_path}",
                )

            os.makedirs(os.path.dirname(full_dest), exist_ok=True)
            shutil.copy2(full_source, full_dest)

            return AiderResult.success_result(
                stdout=f"Successfully copied {source_path} to {dest_path}",
                command=f"copy_file {source_path} {dest_path}",
            )

        except Exception as e:
            return AiderResult.error_result(
                error_message=str(e), command=f"copy_file {source_path} {dest_path}"
            )

    def list_directory(
        self,
        repo_path: str,
        dir_path: str = ".",
        pattern: Optional[str] = None,
        recursive: bool = False,
    ) -> AiderResult:
        """List directory contents."""
        try:
            full_path = os.path.join(repo_path, dir_path)

            if not os.path.exists(full_path):
                return AiderResult.error_result(
                    error_message=f"Directory not found: {dir_path}",
                    command=f"list_directory {dir_path}",
                )

            if recursive and pattern:
                # Use glob for recursive pattern matching
                search_pattern = os.path.join(full_path, "**", pattern)
                files = glob.glob(search_pattern, recursive=True)
                # Make paths relative to repo
                files = [os.path.relpath(f, repo_path) for f in files]
            elif pattern:
                # Non-recursive pattern matching
                search_pattern = os.path.join(full_path, pattern)
                files = glob.glob(search_pattern)
                files = [os.path.relpath(f, repo_path) for f in files]
            else:
                # Simple directory listing
                files = []
                for item in os.listdir(full_path):
                    item_path = os.path.join(dir_path, item)
                    if os.path.isdir(os.path.join(repo_path, item_path)):
                        files.append(item_path + "/")
                    else:
                        files.append(item_path)

            output = "\n".join(sorted(files))

            return AiderResult.success_result(
                stdout=output, command=f"list_directory {dir_path}"
            )

        except Exception as e:
            return AiderResult.error_result(
                error_message=str(e), command=f"list_directory {dir_path}"
            )

    def create_directory(self, repo_path: str, dir_path: str) -> AiderResult:
        """Create a directory."""
        try:
            full_path = os.path.join(repo_path, dir_path)
            os.makedirs(full_path, exist_ok=True)

            return AiderResult.success_result(
                stdout=f"Successfully created directory {dir_path}",
                command=f"create_directory {dir_path}",
            )

        except Exception as e:
            return AiderResult.error_result(
                error_message=str(e), command=f"create_directory {dir_path}"
            )

    def search_files(
        self,
        repo_path: str,
        search_term: str,
        file_pattern: str = "*",
        case_sensitive: bool = False,
        max_results: int = 100,
    ) -> AiderResult:
        """Search for text within files using grep."""
        try:
            # Use grep for searching
            grep_args = ["grep", "-r", "-n"]

            if not case_sensitive:
                grep_args.append("-i")

            grep_args.extend(["--include", file_pattern])
            grep_args.append(search_term)
            grep_args.append(".")

            result = self.run_command(grep_args, cwd=repo_path, timeout=30)

            if result.success and result.stdout:
                lines = result.stdout.strip().split("\n")[:max_results]
                output = "\n".join(lines)
                if len(lines) == max_results:
                    output += f"\n\n(Showing first {max_results} results)"
                result.stdout = output

            return result

        except Exception as e:
            return AiderResult.error_result(
                error_message=str(e), command=f"search_files '{search_term}'"
            )

    def find_files(
        self, repo_path: str, name_pattern: str, recursive: bool = True
    ) -> AiderResult:
        """Find files by name pattern."""
        try:
            if recursive:
                search_pattern = os.path.join(repo_path, "**", name_pattern)
                files = glob.glob(search_pattern, recursive=True)
            else:
                search_pattern = os.path.join(repo_path, name_pattern)
                files = glob.glob(search_pattern)

            # Make paths relative to repo
            files = [os.path.relpath(f, repo_path) for f in files]
            output = "\n".join(sorted(files))

            return AiderResult.success_result(
                stdout=output, command=f"find_files '{name_pattern}'"
            )

        except Exception as e:
            return AiderResult.error_result(
                error_message=str(e), command=f"find_files '{name_pattern}'"
            )

    def get_file_info(self, repo_path: str, file_path: str) -> AiderResult:
        """Get file information (size, modification time, etc.)."""
        try:
            full_path = os.path.join(repo_path, file_path)

            if not os.path.exists(full_path):
                return AiderResult.error_result(
                    error_message=f"File not found: {file_path}",
                    command=f"get_file_info {file_path}",
                )

            stat = os.stat(full_path)
            info = {
                "path": file_path,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "is_file": os.path.isfile(full_path),
                "is_dir": os.path.isdir(full_path),
                "permissions": oct(stat.st_mode)[-3:],
            }

            output = "\n".join(f"{k}: {v}" for k, v in info.items())

            return AiderResult.success_result(
                stdout=output, command=f"get_file_info {file_path}"
            )

        except Exception as e:
            return AiderResult.error_result(
                error_message=str(e), command=f"get_file_info {file_path}"
            )
