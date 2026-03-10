import os
import subprocess
import sys


def test_missing_jwt_secret():
    env = os.environ.copy()
    env.pop("JWT_SECRET", None)
    cmd = (
        "import importlib.util, pathlib;"
        "spec=importlib.util.spec_from_file_location('auth', pathlib.Path('server')/'auth.py');"
        "mod=importlib.util.module_from_spec(spec);"
        "spec.loader.exec_module(mod)"
    )
    result = subprocess.run(
        [sys.executable, "-c", cmd],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "JWT_SECRET" in result.stderr
