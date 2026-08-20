#!/usr/bin/env python3
"""Validate that all required environment variables and paths are set for production."""

import os
import sys
import urllib.request
import urllib.error

REQUIRED_VARS = {
    "DFAT_JWT_SECRET": "JWT signing secret (generate with: openssl rand -hex 32)",
    "DFAT_DATABASE_URL": "Database connection URL",
    "DFAT_ENV": "Environment name (must be 'production')",
}

DEFAULT_SECRETS = {
    "change-me-in-production",
    "secret",
    "default",
    "changeme",
    "your-secret-here",
    "generate-with-openssl-rand-hex-32",
}


def check_env_vars() -> list[str]:
    errors: list[str] = []

    for var, description in REQUIRED_VARS.items():
        value = os.environ.get(var, "")
        if not value:
            errors.append(f"MISSING: {var} - {description}")

    env = os.environ.get("DFAT_ENV", "")
    if env and env != "production":
        errors.append(f"DFAT_ENV is '{env}', expected 'production'")

    secret = os.environ.get("DFAT_JWT_SECRET", "")
    if secret:
        if len(secret) < 32:
            errors.append(f"DFAT_JWT_SECRET is too short ({len(secret)} chars, need >=32)")
        if secret.lower() in DEFAULT_SECRETS:
            errors.append("DFAT_JWT_SECRET is set to a known default value - generate a real secret")

    return errors


def check_directory(env_var: str, label: str, writable: bool = False) -> list[str]:
    errors: list[str] = []
    path = os.environ.get(env_var, "")
    if not path:
        errors.append(f"MISSING: {env_var} - {label} directory not configured")
        return errors
    if not os.path.isdir(path):
        errors.append(f"{env_var}={path} - directory does not exist")
    elif not os.access(path, os.R_OK):
        errors.append(f"{env_var}={path} - directory is not readable")
    elif writable and not os.access(path, os.W_OK):
        errors.append(f"{env_var}={path} - directory is not writable")
    return errors


def check_audit_log_dir() -> list[str]:
    path = os.environ.get("DFAT_AUDIT_LOG_PATH", "")
    if not path:
        return ["MISSING: DFAT_AUDIT_LOG_PATH - audit log path not configured"]
    log_dir = os.path.dirname(path)
    if log_dir and not os.path.isdir(log_dir):
        return [f"DFAT_AUDIT_LOG_PATH directory '{log_dir}' does not exist"]
    if log_dir and not os.access(log_dir, os.W_OK):
        return [f"DFAT_AUDIT_LOG_PATH directory '{log_dir}' is not writable"]
    return []


def check_ollama() -> list[str]:
    warnings: list[str] = []
    url = os.environ.get("DFAT_LLM_API_URL", "http://ollama:11434")
    try:
        urllib.request.urlopen(url, timeout=5)
    except (urllib.error.URLError, OSError):
        warnings.append(f"WARNING: Ollama not reachable at {url} - AI features will degrade gracefully")
    return warnings


def main() -> int:
    print("=" * 60)
    print("DFAT Production Environment Validation")
    print("=" * 60)
    print()

    errors = check_env_vars()
    errors += check_directory("DFAT_EVIDENCE_DIR", "Evidence storage", writable=True)
    errors += check_directory("DFAT_OUTPUT_DIR", "Report output", writable=True)
    errors += check_audit_log_dir()
    warnings = check_ollama()

    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  [!] {w}")
        print()

    if errors:
        print("ERRORS (must fix before deploying):")
        for e in errors:
            print(f"  [X] {e}")
        print()
        print(f"RESULT: FAIL - {len(errors)} error(s) found")
        return 1

    print("All checks passed.")
    print("RESULT: PASS - environment is production-ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
