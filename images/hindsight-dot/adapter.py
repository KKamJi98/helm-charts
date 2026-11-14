"""Isolated recall-only candidate. No deployment, hooks, or background ingestion."""

import json
import os
import re
import stat
import subprocess
from pathlib import Path
from urllib.request import HTTPRedirectHandler, Request, build_opener

URL = "https://hindsight.kkamji.net/v1/default/banks/personal_shared/memories/recall"
CREDENTIALS = Path.home() / ".local/share/hindsight-dot-readonly/credentials.json"
MAX_BYTES = 65536
BLOCK = re.compile(
    r"bunjang|번개장터|번장|code-work|vault-company|"
    r"(?:password|secret|token|api[_ -]?key|비밀번호|인증번호|복구코드)\s*[:=]|"
    r"authorization\s*:|cookie\s*:|-----BEGIN|"
    r"CONTEXT COMPACTION|ASYNC DELEGATION|INTERNAL NOTIFICATION",
    re.IGNORECASE,
)


def safe_text(text, scanner):
    if not isinstance(text, str) or not text.strip() or "\x00" in text:
        return False
    try:
        raw = text.encode("utf-8", errors="strict")
    except UnicodeError:
        return False
    if len(raw) > MAX_BYTES or BLOCK.search(text):
        return False
    if not Path(scanner).is_absolute():
        return False
    try:
        result = subprocess.run(
            [
                scanner,
                "stdin",
                "--config",
                str(Path(__file__).with_name("gitleaks.toml")),
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
