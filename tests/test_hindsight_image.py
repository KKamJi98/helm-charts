"""Recipe checks; opt in to isolated Docker verification with HINDSIGHT_TEST_IMAGE."""

import hashlib
import json
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "images/hindsight-security"
BASE = "ghcr.io/vectorize-io/hindsight:1.1.0@sha256:50311d02b4d5d2b7c5242bd336edf8735df8374eaad496a92f49c83b37d2aa06"
UV = "ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0"
EXPECTED = {"authlib": "1.9.1", "dnspython": "2.9.0", "joserfc": "1.6.8"}
IMAGE = os.environ.get("HINDSIGHT_TEST_IMAGE")
EVIDENCE = os.environ.get("HINDSIGHT_TEST_EVIDENCE")
INVENTORY = r"""
import hashlib, importlib.metadata, json, os, pathlib, re, sys
packages = {re.sub(r"[-_.]+", "-", d.metadata["Name"]).lower(): d.version
            for d in importlib.metadata.distributions()}
files = {}
for root, dirs, names in os.walk("/app"):
    dirs[:] = sorted(d for d in dirs if d not in (".venv", "__pycache__"))
    for name in sorted(names):
        path = pathlib.Path(root) / name
        if path.is_symlink():
            files[str(path)] = "link:" + os.readlink(path)
        elif path.is_file():
            files[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
print(json.dumps({"packages": packages, "app_files": files,
                  "python": sys.version, "uid": os.getuid(),
                  "build_residue": [p for p in ("/uv", "/uvx", "/security-requirements.txt")
                                    if pathlib.Path(p).exists()]}, sort_keys=True))
"""


def command(args, payload=None, timeout=180):
    result = subprocess.run(
        args,
        check=False,
        input=payload,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise AssertionError(
            f"{args[:3]} failed ({result.returncode}):\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout, result.stderr


def isolated(image, payload):
    return command(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--pull",
            "never",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev",
            "--tmpfs",
            "/home/hindsight:rw,exec,nosuid,nodev,uid=1000,gid=1000",
            "--env",
            "HF_HUB_OFFLINE=1",
            "--env",
            "TRANSFORMERS_OFFLINE=1",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--entrypoint",
            "/app/api/.venv/bin/python",
            image,
            "-",
        ],
        payload,
    )


def record(name, content):
    if EVIDENCE:
        path = Path(EVIDENCE)
        path.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(content)


class RecipeTests(unittest.TestCase):
    def test_exact_base_tool_and_hashes(self):
        recipe = (SOURCE / "Dockerfile").read_text()
        self.assertEqual(re.findall(r"^FROM (\S+)", recipe, re.MULTILINE), [UV, BASE])
        pins = re.findall(
            r"^(\w+)==(\S+) --hash=sha256:([0-9a-f]{64})$",
            (SOURCE / "requirements.txt").read_text(),
            re.MULTILINE,
        )
        self.assertEqual({name: version for name, version, _ in pins}, EXPECTED)
        self.assertEqual(len(pins), 3)
        for flag in (
            "--require-hashes",
            "--no-deps",
            "--only-binary :all:",
            "--no-cache",
            "UV_PYTHON_DOWNLOADS=never",
        ):
            self.assertIn(flag, recipe)
        self.assertIn(
            "/uv --no-config --no-cache pip check --python /app/api/.venv/bin/python",
            recipe,
        )
        self.assertTrue(recipe.rstrip().endswith("USER hindsight"))
        self.assertNotRegex(recipe, r"(?m)^(COPY|ADD|ENV|CMD|ENTRYPOINT) ")
        self.assertEqual(
            (SOURCE / ".dockerignore").read_text(),
            "*\n!Dockerfile\n!requirements.txt\n",
        )


@unittest.skipUnless(IMAGE, "set HINDSIGHT_TEST_IMAGE to a locally built candidate")
class BuiltImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inspect = {}
        cls.inventory = {}
        for name, image in (("base", BASE), ("candidate", IMAGE)):
            info, _ = command(["docker", "image", "inspect", image])
            cls.inspect[name] = json.loads(info)[0]
            data, _ = isolated(image, INVENTORY)
            cls.inventory[name] = json.loads(data)
        evidence = {
            "inspect": cls.inspect,
            "inventory": cls.inventory,
            "source_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in SOURCE.iterdir()
                if p.is_file()
            },
        }
        record(
            "image-verification.json", json.dumps(evidence, indent=2, sort_keys=True)
        )

    def test_only_expected_package_delta(self):
        before = self.inventory["base"]["packages"]
        after = self.inventory["candidate"]["packages"]
        delta = {
            name: [before.get(name), after.get(name)]
            for name in before.keys() | after.keys()
            if before.get(name) != after.get(name)
        }
        self.assertEqual(
            delta,
            {
                "authlib": ["1.6.12", "1.9.1"],
                "dnspython": ["2.8.0", "2.9.0"],
                "joserfc": [None, "1.6.8"],
            },
        )
        self.assertEqual({name: after[name] for name in EXPECTED}, EXPECTED)
        self.assertEqual(after["fastmcp"], "3.2.0")
        self.assertEqual(after["pg0-embedded"], "0.15.2")
        self.assertEqual(after["onnxruntime"], "1.31.0")

    def test_original_runtime_source_and_config_preserved(self):
        before, after = self.inventory["base"], self.inventory["candidate"]
        self.assertEqual(after["app_files"], before["app_files"])
        self.assertEqual(after["python"], before["python"])
        self.assertEqual(after["uid"], 1000)
        self.assertEqual(after["build_residue"], [])
        base, candidate = self.inspect["base"], self.inspect["candidate"]
        self.assertEqual(candidate["Config"], base["Config"])
        self.assertEqual(candidate["Architecture"], "amd64")
        base_layers = base["RootFS"]["Layers"]
        self.assertEqual(candidate["RootFS"]["Layers"][:-1], base_layers)

    def test_advisories_imports_and_disposable_database(self):
        stdout, stderr = isolated(IMAGE, (SOURCE / "test_runtime.py").read_text())
        record("image-smoke-green.log", stdout + stderr)
        self.assertIn("Ran 6 tests", stderr)
        self.assertIn("\nOK", stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
