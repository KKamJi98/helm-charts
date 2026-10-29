"""Offline backport contracts. Needs Helm, PyYAML and full Git history, not a cluster."""

import difflib
import gzip
import hashlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts/envoy-gateway"
ARCHIVE = CHART / "charts/gateway-helm-1.8.1.tgz"
SCRIPT = ROOT / "scripts/patch_envoy_gateway_crd.py"
MEMBER = "gateway-helm/charts/crds/crds/generated/gateway.envoyproxy.io_backendtrafficpolicies.yaml"
FIXED_MEMBER_SHA256 = "3b285efcb7d8f9c292f386528d83a61bd719d992a67f9c48a848353f10655e66"
# Reuse the existing Git blob instead of committing a second vendor fixture.
ORIGINAL_BLOB = "a4c644ef9e52cfbccbaa6e357cb2f09ac738b2ab"
HELM = os.environ.get("HELM", "helm")


class CRDLoader(yaml.SafeLoader):
    pass


# Gateway CRDs contain a literal unquoted '=' enum. Keep the loader safe.
CRDLoader.add_constructor("tag:yaml.org,2002:value", lambda loader, node: node.value)


def run(*args):
    return subprocess.run(args, check=False, cwd=ROOT, capture_output=True, timeout=60)


def member_bytes(data):
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        stream = archive.extractfile(MEMBER)
        assert stream is not None
        return stream.read()


def render(chart):
    result = run(
        HELM,
        "template",
        "envoy-gateway",
        str(chart),
        "-n",
        "envoy-gateway-system",
        "--include-crds",
        "--skip-tests",
        "--kube-version",
        "1.36.1",
        "-f",
        str(chart / "kkamji_local_values.yaml"),
    )
    if result.returncode:
        raise AssertionError(result.stderr.decode())
    return result.stdout.decode()


class BackportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixed = ARCHIVE.read_bytes()
        result = run("git", "cat-file", "blob", ORIGINAL_BLOB)
        if result.returncode:
            raise AssertionError("pristine vendor blob missing; fetch full Git history")
        cls.original = result.stdout
        spec = importlib.util.spec_from_file_location("crd_backport", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.patch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.patch)

    def test_vendored_crd_matches_official_1_8_2(self):
        self.assertEqual(
            hashlib.sha256(member_bytes(self.fixed)).hexdigest(), FIXED_MEMBER_SHA256
        )

    def test_pristine_input_and_deterministic_idempotent_output(self):
        self.assertEqual(
            self.patch.sha256(self.original), self.patch.ORIGINAL_ARCHIVE_SHA256
        )
        self.assertEqual(self.patch.candidate(self.original), self.fixed)
        self.assertEqual(self.patch.candidate(self.fixed), self.fixed)

    def test_all_other_tar_bytes_headers_and_members_are_unchanged(self):
        before, after = gzip.decompress(self.original), gzip.decompress(self.fixed)
        with tarfile.open(fileobj=io.BytesIO(before)) as archive:
            member = archive.getmember(MEMBER)
        start, end = member.offset_data, member.offset_data + member.size
        self.assertEqual(before[:start], after[:start])
        self.assertEqual(before[end:], after[end:])
        self.assertEqual(
            before[start:end].replace(self.patch.OLD, self.patch.NEW), after[start:end]
        )
        self.assertEqual(before[start:end].count(self.patch.OLD), 2)

    def test_only_global_and_local_request_formats_change(self):
        before = yaml.load(member_bytes(self.original), Loader=CRDLoader)
        after = yaml.load(member_bytes(self.fixed), Loader=CRDLoader)
        self.assertEqual([v["name"] for v in after["spec"]["versions"]], ["v1alpha1"])
        rates = before["spec"]["versions"][0]["schema"]["openAPIV3Schema"][
            "properties"
        ]["spec"]["properties"]["rateLimit"]["properties"]
        for scope in ("global", "local"):
            requests = rates[scope]["properties"]["rules"]["items"]["properties"][
                "limit"
            ]["properties"]["requests"]
            self.assertEqual(requests["format"], "int32")
            self.assertEqual(requests["type"], "integer")
            self.assertEqual(
                (requests["minimum"], requests["maximum"]), (1, 4294967295)
            )
            requests["format"] = "int64"
        self.assertEqual(
            before, after, "CEL, bounds and every other schema field must stay intact"
        )

    def test_unknown_partial_or_oversized_inputs_are_rejected(self):
        raw = gzip.decompress(self.fixed)
        cases = [
            b"not gzip",
            self.fixed[:-8],
            b"x" * (self.patch.MAX_ARCHIVE_BYTES + 1),
            self.patch.pack(b"x" * (self.patch.MAX_TAR_BYTES + 1)),
            self.patch.pack(raw.replace(self.patch.NEW, self.patch.OLD, 1)),
            self.patch.pack(raw.replace(b"description:", b"descriptioN:", 1)),
        ]
        for data in cases:
            with (
                self.subTest(size=len(data)),
                self.assertRaises((ValueError, OSError, EOFError)),
            ):
                self.patch.candidate(data)

    def test_cli_check_is_read_only_and_apply_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vendor.tgz"
            path.write_bytes(self.original)
            result = run(sys.executable, str(SCRIPT), "--check", "--archive", str(path))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_bytes(), self.original)
            for _ in range(2):
                result = run(sys.executable, str(SCRIPT), "--archive", str(path))
                self.assertEqual(result.returncode, 0, result.stdout.decode())
                self.assertEqual(path.read_bytes(), self.fixed)
            result = run(sys.executable, str(SCRIPT), "--check", "--archive", str(path))
            self.assertEqual(result.returncode, 0, result.stdout.decode())
            path.write_bytes(b"unrecognized vendor")
            result = run(sys.executable, str(SCRIPT), "--archive", str(path))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_bytes(), b"unrecognized vendor")

    def test_wrapper_chart_and_lock_bytes_are_pinned(self):
        for name, expected in {
            "Chart.yaml": "ab083435d639563c34cc7787ec491ac796e1e7edd8b2ee6c469ad8ea6193f4cf",
            "Chart.lock": "aaa0e3f094c1c3d6314eb1ee44a23fe8de93008a8fd2b493f519299f38060dbe",
        }.items():
            self.assertEqual(self.patch.sha256((CHART / name).read_bytes()), expected)

    def test_full_render_diff_is_exactly_two_format_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / "envoy-gateway"
            shutil.copytree(CHART, baseline)
            (baseline / "charts" / ARCHIVE.name).write_bytes(self.original)
            before, after = render(baseline), render(CHART)
        delta = list(difflib.unified_diff(before.splitlines(), after.splitlines()))
        changed = [
            line.strip()
            for line in delta
            if line[:1] in ("+", "-") and not line.startswith(("+++", "---"))
        ]
        self.assertEqual(
            changed,
            [
                "-                                  format: int32",
                "+                                  format: int64",
            ]
            * 2,
        )
        before_docs = list(yaml.load_all(before, Loader=CRDLoader))
        after_docs = list(yaml.load_all(after, Loader=CRDLoader))
        self.assertEqual(
            [d for d in before_docs if d and d["kind"] != "CustomResourceDefinition"],
            [d for d in after_docs if d and d["kind"] != "CustomResourceDefinition"],
        )


if __name__ == "__main__":
    unittest.main()
