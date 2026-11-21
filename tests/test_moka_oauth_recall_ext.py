"""Hindsight recall-only extension logic, with Hindsight and FastAPI stubbed.

The deployed-image import and signature check is a separate acceptance step;
this keeps the auth, fixed-bank and input contracts in offline CI.
"""

import importlib
import sys
import types
import unittest
from dataclasses import dataclass
from enum import Enum
from types import SimpleNamespace

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

KEY = 'k' * 40


def install_stubs():
    class Budget(str, Enum):
        LOW = 'low'
        MID = 'mid'
        HIGH = 'high'

    @dataclass
    class RequestContext:
        api_key: str | None = None
        internal: bool = False
        authenticated_schema: str | None = None

    class HttpExtension:
        def __init__(self, config):
            self.config = config

    class APIRouter:
        """Minimal stand-in: records POST handlers, like FastAPI include_router would mount them."""

        def __init__(self):
            self.routes = []

        def post(self, path, include_in_schema=True):
            def register(handler):
                self.routes.append((path, handler))
                return handler
            return register

    fastapi = types.ModuleType('fastapi')
    fastapi.APIRouter = APIRouter
    fastapi.Request = object
    fastapi_responses = types.ModuleType('fastapi.responses')
    fastapi_responses.JSONResponse = JSONResponse

    modules = {
        'fastapi': fastapi,
        'fastapi.responses': fastapi_responses,
        'hindsight_api': types.ModuleType('hindsight_api'),
        'hindsight_api.config': types.ModuleType('hindsight_api.config'),
        'hindsight_api.engine': types.ModuleType('hindsight_api.engine'),
        'hindsight_api.engine.memory_engine': types.ModuleType('hindsight_api.engine.memory_engine'),
        'hindsight_api.extensions': types.ModuleType('hindsight_api.extensions'),
        'hindsight_api.models': types.ModuleType('hindsight_api.models'),
    }
    modules['hindsight_api.config'].get_config = lambda: SimpleNamespace(database_schema='public')
    modules['hindsight_api.engine.memory_engine'].Budget = Budget
    modules['hindsight_api.engine.memory_engine'].VALID_RECALL_FACT_TYPES = frozenset({'world', 'experience', 'observation'})
    modules['hindsight_api.extensions'].HttpExtension = HttpExtension
    modules['hindsight_api.models'].RequestContext = RequestContext
    sys.modules.update(modules)
    sys.modules.pop('hindsight_moka_recall_ext', None)
    return importlib.import_module('hindsight_moka_recall_ext')


class Memory:
    def __init__(self):
        self.calls = []

    async def recall_async(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(results=[SimpleNamespace(
            text='fixture fact', fact_type='world', mentioned_at='2026-11-01T00:00:00Z',
            occurred_start=None, occurred_end=None, document_id='hidden', metadata={'hidden': True})])


class RecallExtensionTest(unittest.TestCase):
    def setUp(self):
        self.ext_module = install_stubs()
        self.memory = Memory()
        ext = self.ext_module.MokaRecallHttpExtension({'moka_recall_key': KEY})
        router = ext.get_router(self.memory)
        app = Starlette(routes=[Route('/ext' + path, handler, methods=['POST']) for path, handler in router.routes])
        self.client = TestClient(app)
        self.url = '/ext/moka-recall/recall'
        self.ok = {'Authorization': 'Bearer ' + KEY}

    def test_rejects_missing_wrong_or_non_bearer_keys(self):
        for headers in ({}, {'Authorization': 'Bearer ' + 'x' * 40}, {'Authorization': 'Basic ' + KEY},
                        {'Authorization': 'Bearer ' + KEY + 'x'}, {'Authorization': KEY}):
            with self.subTest(headers=sorted(headers)):
                self.assertEqual(self.client.post(self.url, json={'query': 'q'}, headers=headers).status_code, 401)
        self.assertEqual(self.memory.calls, [])

    def test_body_can_only_carry_a_bounded_query(self):
        for body, status in (({'query': 'q', 'bank_id': 'other'}, 400), ({'bank_id': 'other'}, 400),
                             ({'query': ' '}, 400), ({'query': 'a' * 1001}, 400), ({'query': 1}, 400),
                             (['query'], 400)):
            with self.subTest(body=body):
                self.assertEqual(self.client.post(self.url, json=body, headers=self.ok).status_code, status)
        big = b'{"query":"' + b'a' * 5000 + b'"}'
        self.assertEqual(self.client.post(self.url, content=big, headers=self.ok).status_code, 413)
        self.assertEqual(self.client.post(self.url, content=b'{', headers=self.ok).status_code, 400)
        self.assertEqual(self.client.get(self.url, headers=self.ok).status_code, 405)
        self.assertEqual(self.client.post('/ext/moka-recall/retain', json={'query': 'q'}, headers=self.ok).status_code, 404)
        self.assertEqual(self.memory.calls, [])

    def test_recall_uses_fixed_bank_and_returns_only_public_fields(self):
        res = self.client.post(self.url, json={'query': ' homelab '}, headers=self.ok)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers['cache-control'], 'no-store')
        self.assertEqual(res.json(), {'bank': 'personal_shared', 'results': [{
            'text': 'fixture fact', 'type': 'world', 'mentioned_at': '2026-11-01T00:00:00Z',
            'occurred_start': None, 'occurred_end': None}]})
        call, = self.memory.calls
        self.assertEqual((call['bank_id'], call['query']), ('personal_shared', 'homelab'))
        self.assertEqual(call['request_context'].authenticated_schema, 'public')
        self.assertIsNone(call['request_context'].api_key)
        self.assertFalse(call['request_context'].internal)

    def test_refuses_weak_keys_at_startup(self):
        for key in ('', 'short', ' ' + KEY):
            with self.subTest(length=len(key)):
                with self.assertRaises(ValueError):
                    self.ext_module.MokaRecallHttpExtension({'moka_recall_key': key})


if __name__ == '__main__':
    unittest.main()
