"""Opt-in integration test against an owned temporary official Redis container.

Run from this directory:
  DOT_RATE_LIVE=1 uv run --no-project --with redis python -m unittest test_rate_limit_live -v

No production credentials, cluster access or persistent host data. The image is
Redis 8.4.0-alpine pinned to the same approved chart digest. Only a random
127.0.0.1 port is published. Cleanup removes only this test's container and files.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import uuid

import redis
import redis.asyncio as aioredis
from redis.backoff import NoBackoff
from redis.retry import Retry

from rate_limit import RedisDCRLimiter, RegistrationLimited, RegistrationUnavailable

IMAGE = 'redis@sha256:4eec4565e45aa0b3966554c866bc73211e281b0b3d89fe9a33c982e6faca809d'


@unittest.skipUnless(os.environ.get('DOT_RATE_LIVE') == '1', 'explicit live-test opt-in required')
class LiveLimiterTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='dot-dcr-live-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.name = 'dot-dcr-test-' + uuid.uuid4().hex[:12]
        cls.password = 'synthetic-' + uuid.uuid4().hex
        hashed = hashlib.sha256(cls.password.encode()).hexdigest()
        acl = Path(cls.temp.name) / 'users.acl'
        acl.write_text('\n'.join([
            'user default off',
            f'user test-admin on #{hashed} ~* +@all',
            f'user rate on #{hashed} ~dot-dcr-e3:* +eval +get +incr +expire +ttl',
            '',
        ]))
        acl.chmod(0o644)  # Synthetic password only; read by unprivileged container UID.
        cls.addClassCleanup(lambda: subprocess.run(
            ['docker', 'rm', '-f', cls.name], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, check=False, timeout=15))
        subprocess.run([
            'docker', 'run', '--detach', '--name', cls.name, '--pull=never',
            '--user', '999:1000', '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--memory', '128m',
            '--cpus', '0.5', '--pids-limit', '64',
            '--tmpfs', '/data:rw,noexec,nosuid,size=16m,mode=1777',
            '--tmpfs', '/tmp:rw,noexec,nosuid,size=4m,mode=1777',
            '--publish', '127.0.0.1::6379',
            '--mount', f'type=bind,src={acl},dst=/run/test-users.acl,readonly',
            IMAGE, 'redis-server', '--bind', '0.0.0.0', '--protected-mode', 'yes',
            '--aclfile', '/run/test-users.acl', '--save', '', '--appendonly', 'no',
        ], check=True, capture_output=True, timeout=30)
        binding = json.loads(subprocess.check_output(
            ['docker', 'inspect', '--format', '{{json .NetworkSettings.Ports}}', cls.name],
            text=True, timeout=10))['6379/tcp']
        if len(binding) != 1 or binding[0]['HostIp'] != '127.0.0.1':
            raise RuntimeError('test listener must be loopback only')
        cls.port = int(binding[0]['HostPort'])
        check = redis.Redis(host='127.0.0.1', port=cls.port, username='test-admin',
                            password=cls.password, socket_connect_timeout=.2,
                            socket_timeout=.2, retry=Retry(NoBackoff(), 0))
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    if check.ping(): break
                except redis.RedisError:
                    if time.monotonic() >= deadline: raise
                    time.sleep(.1)
            if not check.info('server')['redis_version'].startswith('8.4.'):
                raise RuntimeError('unexpected Redis version')
        finally:
            check.close()

    async def asyncSetUp(self):
        settings = dict(host='127.0.0.1', port=self.port, password=self.password,
                        socket_connect_timeout=.5, socket_timeout=.5,
                        retry=Retry(NoBackoff(), 0), decode_responses=True)
        self.admin = aioredis.Redis(username='test-admin', **settings)
        self.rate = aioredis.Redis(username='rate', **settings)
        self.limit = RedisDCRLimiter(self.rate, 3, timeout_seconds=2)
        await self.admin.delete(self.limit.total_key, self.limit.window_key)
        await self.admin.set(self.limit.total_key, '0', nx=True)

    async def asyncTearDown(self):
        await self.rate.aclose()
        await self.admin.aclose()

    async def test_atomic_concurrency_allows_only_five(self):
        outcomes = await asyncio.gather(
            *(RedisDCRLimiter(self.rate, 3, timeout_seconds=2).acquire() for _ in range(25)),
            return_exceptions=True)
        self.assertEqual(sum(r is None for r in outcomes), 5)
        self.assertEqual(sum(isinstance(r, RegistrationLimited) for r in outcomes), 20)
        self.assertEqual(await self.admin.get(self.limit.total_key), '5')
        self.assertEqual(await self.admin.get(self.limit.window_key), '5')
        self.assertEqual(await self.admin.ttl(self.limit.total_key), -1)
        self.assertGreater(await self.admin.ttl(self.limit.window_key), 0)

    async def test_epoch_cap_32_with_prepared_count(self):
        await self.admin.set(self.limit.total_key, '31')
        await self.limit.acquire()
        with self.assertRaises(RegistrationLimited) as caught:
            await RedisDCRLimiter(self.rate, 3).acquire()
        self.assertIsNone(caught.exception.retry_after)
        self.assertEqual(await self.admin.get(self.limit.total_key), '32')

    async def test_counters_survive_new_limiter_and_client(self):
        for _ in range(5): await self.limit.acquire()
        other = aioredis.Redis(host='127.0.0.1', port=self.port, username='rate',
                              password=self.password, decode_responses=True,
                              retry=Retry(NoBackoff(), 0))
        try:
            with self.assertRaises(RegistrationLimited):
                await RedisDCRLimiter(other, 3).acquire()
        finally:
            await other.aclose()

    async def test_missing_total_fails_closed(self):
        await self.admin.delete(self.limit.total_key)
        with self.assertRaises(RegistrationUnavailable): await self.limit.acquire()
        self.assertIsNone(await self.admin.get(self.limit.total_key))

    async def test_expiring_or_corrupt_counter_fails_closed(self):
        await self.admin.expire(self.limit.total_key, 600)
        with self.assertRaises(RegistrationUnavailable): await self.limit.acquire()
        await self.admin.set(self.limit.total_key, 'not-an-integer')
        with self.assertRaises(RegistrationUnavailable): await self.limit.acquire()
        await self.admin.set(self.limit.total_key, '0')
        await self.admin.set(self.limit.window_key, '1')  # Missing TTL.
        with self.assertRaises(RegistrationUnavailable): await self.limit.acquire()
        self.assertEqual(await self.admin.get(self.limit.total_key), '0')

    async def test_window_expiry_does_not_reset_total(self):
        for _ in range(5): await self.limit.acquire()
        # Trusted fixture speeds expiry, not production limiter behavior.
        await self.admin.expire(self.limit.window_key, 1)
        await asyncio.sleep(1.1)
        await self.limit.acquire()
        self.assertEqual(await self.admin.get(self.limit.total_key), '6')

    async def test_acl_rejects_foreign_keys_and_set(self):
        for key in ('dot-control:state', 'dot-dcr-e1:total', 'dot-oauth-e3:probe'):
            with self.assertRaises(redis.ResponseError): await self.rate.get(key)
            with self.assertRaises(redis.ResponseError):
                await self.rate.eval("return redis.call('GET', KEYS[1])", 1, key)
        with self.assertRaises(redis.ResponseError):
            await self.rate.set(self.limit.total_key, '0')
        with self.assertRaises(redis.ResponseError):
            await self.rate.eval("return redis.call('SET', KEYS[1], '0')", 1,
                                 self.limit.total_key)
        self.assertEqual(await self.admin.get(self.limit.total_key), '0')


if __name__ == '__main__':
    unittest.main()
