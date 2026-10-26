"""Prepare checksum-pinned public E5 files without credentials or remote code.

The manifest is a JSON object mapping exact repository-relative paths to SHA256
hex digests. A completed directory is immutable: verify and reuse it, or fail
closed. Recovery from a failed, incomplete download is an explicit Job rerun.
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

PINNED_REPO = "intfloat/multilingual-e5-small"
PINNED_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
COMPLETE_FILE = ".hindsight-model-complete.json"
REQUIRED_FILES = {"onnx/model.onnx", "tokenizer.json"}


def download_file(**kwargs):
    # Import only on a first/incomplete run, after disabling ambient HF auth.
    from huggingface_hub import hf_hub_download

    return hf_hub_download(**kwargs)


def validate_manifest(files_sha256):
    if not isinstance(files_sha256, dict) or not files_sha256:
        raise ValueError("filesSha256 must be a nonempty relative-path/SHA256 map")
    for name, expected in files_sha256.items():
        if not isinstance(name, str):
            raise TypeError("manifest paths must be strings")
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or str(path) != name
            or not path.parts
            or any(part in (".", "..") or part.startswith(".") for part in path.parts)
            or "\\" in name
            or any(ord(char) < 32 for char in name)
            or path.suffix.lower() in (".py", ".pyc", ".pyo")
        ):
            raise ValueError(f"unsafe public model path: {name!r}")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"invalid SHA256 for {name!r}")
    if not REQUIRED_FILES.issubset(files_sha256):
        raise ValueError("manifest must include onnx/model.onnx and tokenizer.json")
    return dict(sorted(files_sha256.items()))


def regular_file(target, name):
    current = target
    for component in PurePosixPath(name).parts:
        current = current / component
        if current.is_symlink():
            raise ValueError(f"refusing symlink in model path: {name!r}")
    if not current.is_file():
        raise ValueError(f"missing public model file: {name!r}")
    return current


def verify_files(target, files_sha256):
    for name, expected in files_sha256.items():
        path = regular_file(target, name)
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(f"public model SHA256 mismatch: {name!r}")


def prepare_model(repo, revision, files_sha256, model_dir):
    if repo != PINNED_REPO or revision != PINNED_REVISION:
        raise ValueError(
            "only the approved public E5 repository and exact revision are allowed"
        )
    manifest = validate_manifest(files_sha256)
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
    target = Path(model_dir).absolute()
    # Do not follow a preexisting symlink even at an ancestor of the target.
    for path in (target, *target.parents):
        if path.is_symlink():
            raise ValueError("refusing symlink in model directory")
    target.mkdir(parents=True, exist_ok=True)
    lock_path = target / ".hindsight-bootstrap.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(
                "another model bootstrap holds the lock; no retry attempted"
            ) from error
        marker = target / COMPLETE_FILE
        expected_marker = {"repo": repo, "revision": revision, "filesSha256": manifest}
        if marker.is_symlink():
            raise ValueError("refusing symlink completion marker")
        if marker.exists():
            if json.loads(marker.read_text(encoding="utf-8")) != expected_marker:
                raise ValueError(
                    "completed model revision or manifest differs; refusing replacement"
                )
            verify_files(target, manifest)
            return "verified-existing"
        for name, expected in manifest.items():
            destination = target / name
            for path in (destination, *destination.parents):
                if path == target.parent:
                    break
                if path.is_symlink():
                    raise ValueError(
                        f"refusing symlink in download destination: {name!r}"
                    )
            # An interrupted first run can reuse only independently verified bytes.
            if destination.is_file():
                try:
                    verify_files(target, {name: expected})
                    continue
                except ValueError:
                    pass
            download_file(
                repo_id=repo,
                revision=revision,
                filename=name,
                local_dir=str(target),
                token=False,
            )
            verify_files(target, {name: expected})
        verify_files(target, manifest)
        # Publish completion atomically, only after every manifest digest passes.
        temporary = target / f"{COMPLETE_FILE}.tmp"
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(expected_marker, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(marker)
        directory_descriptor = os.open(target, os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        return "downloaded"


def load_manifest(path):
    def unique_keys(pairs):
        values = {}
        for key, value in pairs:
            if key in values:
                raise ValueError(f"duplicate manifest path: {key!r}")
            values[key] = value
        return values

    return json.loads(
        Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_keys
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--model-dir", default="/models/e5-small")
    args = parser.parse_args()
    try:
        result = prepare_model(
            args.repo, args.revision, load_manifest(args.manifest), args.model_dir
        )
    except Exception as error:  # noqa: BLE001 - redact third-party network diagnostics
        # Model paths and error type are public. Avoid dumping network exception
        # text, headers, environment, or any implicit library diagnostic payload.
        print(
            f"public E5 bootstrap failed ({type(error).__name__}); no completion claimed",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps({"model": args.repo, "revision": args.revision, "status": result}),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
