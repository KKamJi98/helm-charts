"""Offline, disposable-container regressions. Never mount production data here."""

import asyncio
import base64
import hashlib
import hmac
import importlib
import json
import os
import secrets
import unittest


def b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=")


def forged_hmac(key, algorithm="HS256"):
    message = b".".join(
        (b64(json.dumps({"alg": algorithm}).encode()), b64(b'{"sub":"synthetic"}'))
    )
    digest = getattr(hashlib, "sha" + algorithm[2:])
    return message + b"." + b64(hmac.new(key, message, digest).digest())


class AdvisoryTests(unittest.TestCase):
    def test_empty_jws_signatures_rejected(self):
        # https://github.com/advisories/GHSA-6v38-4h7w-rj9h
        from authlib.jose import JsonWebSignature
        from authlib.jose.errors import JoseError

        jws = JsonWebSignature()
        for key in (None, secrets.token_bytes(32)):
            with self.subTest(key_is_none=key is None), self.assertRaises(JoseError):
                jws.deserialize_json(
                    {"payload": b64(b"synthetic").decode(), "signatures": []}, key
                )

    def test_empty_hmac_key_rejected(self):
        # https://github.com/advisories/GHSA-8m4g-j4wp-wgcg
        from authlib.jose import jwt

        for algorithm in ("HS256", "HS384", "HS512"):
            for key in (b"", ""):
                with (
                    self.subTest(algorithm=algorithm, key_type=type(key).__name__),
                    self.assertRaises(ValueError),
                ):
                    jwt.decode(forged_hmac(b"", algorithm), key)

    def test_prefixed_public_key_hmac_confusion_rejected(self):
        # https://github.com/advisories/GHSA-7vr2-2fgp-9w7p
        from authlib.jose import jwt
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        genuine = jwt.encode({"alg": "RS256"}, {"sub": "synthetic"}, private)
        for prefix in (
            b"",
            b"\n",
            b" ",
            b"    ",
            b"\xef\xbb\xbf",
            b"# synthetic public key\n",
        ):
            public = prefix + pem
            with self.subTest(prefix=prefix):
                self.assertEqual(jwt.decode(genuine, public)["sub"], "synthetic")
                with self.assertRaises(ValueError):
                    jwt.decode(forged_hmac(public), public)

    def test_genuine_jws_and_hmac_still_work(self):
        from authlib.jose import JsonWebSignature, jwt
        from authlib.jose.errors import BadSignatureError

        key = secrets.token_bytes(64)
        jws = JsonWebSignature()
        signed = jws.serialize_json({"protected": {"alg": "HS256"}}, b"synthetic", key)
        self.assertEqual(jws.deserialize_json(signed, key)["payload"], b"synthetic")
        for algorithm in ("HS256", "HS384", "HS512"):
            token = jwt.encode({"alg": algorithm}, {"sub": "synthetic"}, key)
            self.assertEqual(jwt.decode(token, key)["sub"], "synthetic")
            with self.assertRaises(BadSignatureError):
                jwt.decode(token, secrets.token_bytes(64))


class RuntimeTests(unittest.TestCase):
    def test_imports_and_cpu_onnx(self):
        for module in (
            "hindsight_api",
            "hindsight_api.api",
            "hindsight_api.pg0",
            "hindsight_api.engine.providers.chatgpt_llm",
            "hindsight_api.engine.providers.chatgpt_auth",
            "fastmcp",
            "pg0",
            "onnxruntime",
            "transformers",
            "tokenizers",
            "dns.resolver",
        ):
            with self.subTest(module=module):
                importlib.import_module(module)
        import onnxruntime

        self.assertIn("CPUExecutionProvider", onnxruntime.get_available_providers())
        self.assertEqual(os.getuid(), 1000)

    def test_disposable_pg0_query_and_restart(self):
        import asyncpg
        from hindsight_api.pg0 import EmbeddedPostgres

        async def check():
            db = EmbeddedPostgres(
                name="security-smoke", password=secrets.token_urlsafe(32)
            )
            try:
                uri = await db.start(max_retries=1)
                conn = await asyncpg.connect(uri)
                try:
                    await conn.execute("CREATE TABLE security_smoke (value integer)")
                    await conn.execute("INSERT INTO security_smoke VALUES (42)")
                finally:
                    await conn.close()
                await db.stop()
                uri = await db.start(max_retries=1)
                conn = await asyncpg.connect(uri)
                try:
                    self.assertEqual(
                        await conn.fetchval("SELECT value FROM security_smoke"), 42
                    )
                finally:
                    await conn.close()
            finally:
                await db.stop()

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main(verbosity=2)
