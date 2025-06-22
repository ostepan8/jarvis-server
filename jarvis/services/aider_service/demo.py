from .aider_service import create_aider_service


def run_demo() -> None:
    # Set up the AiderService (adjust parameters as needed)
    aider = create_aider_service(verbose=True)

    repo_path = "."  # Current directory, or set to your repo root

    print("==== 1. Add file ====")
    file_path = "jarvis/tools/hello.py"
    code = "def say_hello(name):\n    return f'Hello, {name}!'\n"
    result = aider.write_file(repo_path, file_path, code)
    print(result.stdout if hasattr(result, "stdout") else result)

    print("==== 2. Generate tests ====")
    test_path = "tests/tools/test_hello.py"
    test_code = (
        "from jarvis.tools.hello import say_hello\n\n"
        "def test_say_hello():\n    assert say_hello('World') == 'Hello, World!'\n"
    )
    result = aider.write_file(repo_path, test_path, test_code)
    print(result.stdout if hasattr(result, "stdout") else result)

    print("==== 3. Run tests ====")
    result = aider.run_tests(repo_path)
    print(result.stdout if hasattr(result, "stdout") else result)

    print("==== 4. Git commit ====")
    result = aider.git_commit(repo_path, "Add hello tool with tests")
    print(result.stdout if hasattr(result, "stdout") else result)

    if aider.is_github_available:
        print("==== 5. GitHub PR ====")
        result = aider.create_pr(
            repo_path,
            "Add hello tool demo",
            "This PR adds a simple hello tool and demonstrates the Aider workflow.",
        )
        print(result.stdout if hasattr(result, "stdout") else result)
    else:
        print("==== 5. GitHub PR ====")
        print("GitHub operations not available (no token or setup missing).")


if __name__ == "__main__":
    run_demo()
