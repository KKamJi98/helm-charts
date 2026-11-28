"""Fail-closed privacy and secret scanner for cloud-agent Hindsight proxies."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

MAX_SUMMARY_CHARS = 4000
MIN_SUMMARY_CHARS = 6
MAX_SUMMARY_BYTES = 16384
DEFAULT_SCANNER_PATH = "/usr/local/bin/gitleaks"
DEFAULT_GITLEAKS_TOML = "[extend]\nuseDefault = true\n"

COMPANY_AND_SECRET_BLOCK = re.compile(
    r"\b(?:bunjang|bgzt|quicket)\b|"
    r"(?<![가-힣])번장|번개장터|"
    r"code-work|vault-company|bunjang\.co\.kr|ethan\.kim@|"
    r"\b(?:DAC|TECH|INFRA|DEVOPS|SECOPS|SRE)-\d{3,6}\b|"
    r"(?:password|secret|token|api[_ -]?key|비밀번호|인증번호|복구코드)\s*[:=]|"
    r"authorization\s*:|cookie\s*:|-----BEGIN|"
    r"\bgh[pousr]_[A-Za-z0-9]{20,}\b|"
    r"\bsk-[A-Za-z0-9_-]{20,}\b|"
    r"\bAKIA[0-9A-Z]{16}\b|"
    r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b|"
    r"CONTEXT COMPACTION|ASYNC DELEGATION|INTERNAL NOTIFICATION",
    re.IGNORECASE,
)


def passes_policy_regex(text: str) -> bool:
    if not isinstance(text, str) or "\x00" in text:
        return False
    clean = text.strip()
    if not MIN_SUMMARY_CHARS <= len(clean) <= MAX_SUMMARY_CHARS:
        return False
    try:
        raw = clean.encode("utf-8", errors="strict")
    except UnicodeError:
        return False
    if len(raw) > MAX_SUMMARY_BYTES:
        return False
    return COMPANY_AND_SECRET_BLOCK.search(clean) is None


def _ensure_gitleaks_config(config_path: str | None) -> str | None:
    if config_path is not None:
        p = Path(config_path)
        return str(p) if p.is_absolute() and p.is_file() else None
    tmp_cfg = Path("/tmp/hindsight-gitleaks.toml")
    try:
        if (
            not tmp_cfg.is_file()
            or tmp_cfg.read_text(encoding="utf-8") != DEFAULT_GITLEAKS_TOML
        ):
            tmp_cfg.write_text(DEFAULT_GITLEAKS_TOML, encoding="utf-8")
    except OSError:
        return None
    return str(tmp_cfg)


def safe_summary_text(
    text: str,
    *,
    scanner_path: str = DEFAULT_SCANNER_PATH,
    config_path: str | None = None,
) -> bool:
    """Fail-closed check: policy regex + Gitleaks stdin scan."""
    if not passes_policy_regex(text):
        return False
    if not isinstance(scanner_path, str) or not Path(scanner_path).is_absolute():
        return False
    cfg = _ensure_gitleaks_config(config_path)
    if cfg is None:
        return False
    raw = text.strip().encode("utf-8", errors="strict")
    try:
        result = subprocess.run(
            [
                scanner_path,
                "stdin",
                "--config",
                cfg,
                "--gitleaks-ignore-path",
                "/dev/null",
                "--ignore-gitleaks-allow",
                "--redact",
                "--no-banner",
                "--exit-code",
                "17",
            ],
            input=raw,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
            env={"PATH": os.defpath},
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0
