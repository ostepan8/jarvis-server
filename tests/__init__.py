import os

# Default secret for tests; real deployments must provide JWT_SECRET
os.environ.setdefault("JWT_SECRET", "testing-secret")
