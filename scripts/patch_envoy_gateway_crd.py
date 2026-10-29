#!/usr/bin/env python3
"""Bounded, offline 1.8.1 -> 1.8.2 CRD-only backport; see gateway-api-routing.md."""

import argparse
import gzip
import hashlib
import io
import os
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "charts/envoy-gateway/charts/gateway-helm-1.8.1.tgz"
MEMBER = "gateway-helm/charts/crds/crds/generated/gateway.envoyproxy.io_backendtrafficpolicies.yaml"
ORIGINAL_ARCHIVE_SHA256 = (
    "251a38715d533bdce2ed11fa5d6c6663a80222a3b170adf1fe7a48d6fe0f0087"
)
ORIGINAL_TAR_SHA256 = "80eb07ec4df8d3b68bc85c7e868443b5d528b64025c6fec6df7bc87f8a3dd8b5"
FIXED_TAR_SHA256 = "4326f95f58de24bcf34dfe4d45186798c94cceb25aceade3b7f8f327f1368373"
ORIGINAL_MEMBER_SHA256 = (
    "dc4eabbf2c9393355e30e35f2976f4ed2c09f9b69e9c4419509c2ba5d0b8bbd1"
)
FIXED_MEMBER_SHA256 = "3b285efcb7d8f9c292f386528d83a61bd719d992a67f9c48a848353f10655e66"
MAX_ARCHIVE_BYTES = 1024 * 1024
MAX_TAR_BYTES = 4 * 1024 * 1024
# This exact block occurs only at rateLimit.{global,local}.rules[].limit.requests.
OLD = (
    b"format: int32\n"
    b"                                  maximum: 4294967295\n"
    b"                                  minimum: 1"
)
NEW = OLD.replace(b"int32", b"int64")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def pack(raw):
    """Keep tar bytes intact, normalize gzip filename, timestamp and compression."""
    output = io.BytesIO()
    with gzip.GzipFile(
        fileobj=output, mode="wb", filename="", mtime=0, compresslevel=9
    ) as stream:
        stream.write(raw)
    return output.getvalue()


def candidate(data):
    """Accept only the pinned pristine package or its exact two-line backport."""
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError("archive exceeds size limit")
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
        raw = stream.read(MAX_TAR_BYTES + 1)
    if len(raw) > MAX_TAR_BYTES:
        raise ValueError("tar exceeds size limit")
    digest = sha256(raw)
    if digest == FIXED_TAR_SHA256:
        return pack(raw)
    if sha256(data) != ORIGINAL_ARCHIVE_SHA256 or digest != ORIGINAL_TAR_SHA256:
        raise ValueError(
            "unknown vendor bytes; review upgrade instead of widening this patch"
        )
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        member = archive.getmember(MEMBER)
        stream = archive.extractfile(member)
        if not member.isfile() or stream is None:
            raise ValueError("target is not a regular file")
        content = stream.read()
    if sha256(content) != ORIGINAL_MEMBER_SHA256 or content.count(OLD) != 2:
        raise ValueError("unexpected CRD or request field count")
    fixed = content.replace(OLD, NEW)
    if sha256(fixed) != FIXED_MEMBER_SHA256:
        raise ValueError("backport differs from the official v1.8.2 CRD")
    # Equal-length substitution preserves every header, member and padding byte.
    raw = raw[: member.offset_data] + fixed + raw[member.offset_data + member.size :]
    if sha256(raw) != FIXED_TAR_SHA256:
        raise ValueError("unexpected tar change outside the two request formats")
    return pack(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="read-only canonical backport check"
    )
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    args = parser.parse_args()
    path = args.archive
    temporary = None
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("archive must be a regular non-symlink file")
        with path.open("rb") as stream:
            current = stream.read(MAX_ARCHIVE_BYTES + 1)
        fixed = candidate(current)
        if args.check and current != fixed:
            raise ValueError(
                "backport missing or noncanonical; run this script without --check"
            )
        if current != fixed:
            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=".crd-backport-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(fixed)
            temporary.chmod(path.stat().st_mode & 0o777)
            os.replace(temporary, path)
        print(
            f"OK: {'checked' if args.check else 'patched'} {path.name} sha256={sha256(fixed)}"
        )
        return 0
    except (OSError, EOFError, ValueError, tarfile.TarError) as error:
        print(f"ERROR: {error}")
        return 1
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
