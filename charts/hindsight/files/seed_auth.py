"""Seed a new Hindsight-owned home once; never replace refreshed credentials."""

import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath

PLAN_SCOPE = "chatgpt.tokens.use.direct"
FILES = ("credentials.json", "host_id")


def validate_content(credential_bytes, host_bytes):
    record = json.loads(credential_bytes)
    host_id = host_bytes.decode().strip()
    if not isinstance(record, dict) or not host_id:
        raise ValueError("Invalid dedicated auth structure")
    if not all(
        isinstance(record.get(key), str) and record[key]
        for key in ("client_id", "refresh_token")
    ):
        raise ValueError("Dedicated auth session is incomplete")
    scopes = record.get("scopes")
    if not isinstance(scopes, list) or PLAN_SCOPE not in scopes:
        raise ValueError("Dedicated auth session has no plan-use grant")
    if record.get("ext_agent_host_id") and record["ext_agent_host_id"] != host_id:
        raise ValueError("Dedicated auth host identity mismatch")


def validate_home(home):
    info = home.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("Auth directory is not private")
    if info.st_uid != os.getuid():
        raise ValueError("Auth directory owner does not match the runtime")
    for name in FILES:
        info = (home / name).lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("Auth record is not a private regular file")
        if info.st_uid != os.getuid():
            raise ValueError("Auth record owner does not match the runtime")
    validate_content((home / FILES[0]).read_bytes(), (home / FILES[1]).read_bytes())


def require_model(model_dir, manifest_file):
    expected = json.loads(manifest_file.read_text())
    if not isinstance(expected, dict) or not expected:
        raise ValueError("Public model manifest is empty")
    root = model_dir.resolve(strict=True)
    for name, digest in expected.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid public model path")
        path = (root / name).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Public model file escapes the model directory")
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != digest:
            raise ValueError("Public model checksum mismatch")


def ensure_auth(home, seed):
    if home.exists() or home.is_symlink():
        validate_home(home)
        return False
    credential_bytes = (seed / FILES[0]).read_bytes()
    host_bytes = (seed / FILES[1]).read_bytes()
    validate_content(credential_bytes, host_bytes)
    home.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=".hindsight-seed-", dir=home.parent))
    try:
        for name, data in zip(FILES, (credential_bytes, host_bytes), strict=True):
            fd = os.open(staged / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        validate_home(staged)
        os.rename(staged, home)
        directory_fd = os.open(home.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    validate_home(home)
    return True


def main():
    os.umask(0o077)
    try:
        require_model(
            Path(os.environ.get("MODEL_DIR", "/models/e5-small")),
            Path(__file__).with_name("model-files.json"),
        )
        installed = ensure_auth(
            Path(os.environ.get("AUTH_HOME", "/auth/chatgpt")),
            Path(os.environ.get("SEED_DIR", "/seed")),
        )
    except (OSError, ValueError, TypeError, UnicodeError):
        print(
            "bootstrap_failed: auth or public-model validation refused", file=sys.stderr
        )
        raise SystemExit(1) from None
    print(
        json.dumps(
            {
                "bootstrap_ready": True,
                "seed_installed": installed,
                "secret_values_disclosed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
