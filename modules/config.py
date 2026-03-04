"""
Environment configuration helpers.

All required variables must be present and non-empty.
Missing values raise RuntimeError at import/startup time.
"""
import os


def require_env(name):
    value = os.environ.get(name)
    if value is None or not str(value).strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
