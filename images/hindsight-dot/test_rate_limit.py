"""Offline CAS contract tests; real Redis restart suite is separate."""
import asyncio
import json
import unittest
from rate_limit import (RedisDCRLimiter, RegistrationLimited, RegistrationUnavailable,
                        INITIAL_STATE, MAX_CONFLICT_RETRIES)


class FakeRedis:
    def __init__(self):
        self.values = {'dot-dcr-e3:state': INITIAL_STATE}
        self.now = 1000
        self.lock = asyncio.Lock()
        self.calls = []
    async def get(self, key):
        value = self.values.get(key)
        await asyncio.sleep(0)
        return value
    async def time(self): return (self.now, 0)
    async def ttl(self, key): return -1
    async def execute_command(self, command, key, value, condition, old):
        async with self.lock:
            self.calls.append((command, key, condition))
            assert command == 'SET' and condition == 'IFEQ'
            if self.values.get(key) != old: return None
            self.values[key] = value
            return True


class LimiterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = FakeRedis()
        self.limit = RedisDCRLimiter(self.redis, 3)
    async def test_five_then_429_and_window_expiry(self):
        for _ in range(5): await self.limit.acquire()
        self.redis.now += 60
        with self.assertRaises(RegistrationLimited) as caught: await self.limit.acquire()
        self.assertEqual(caught.exception.retry_after, 540)
        self.redis.now += 540
        await self.limit.acquire()
        self.assertEqual(json.loads(self.redis.values[self.limit.state_key])['total'], 6)
    async def test_epoch_cap_survives_objects(self):
        for index in range(32):
            self.redis.now = 1000 + (index // 5) * 600
            await RedisDCRLimiter(self.redis, 3).acquire()
        self.redis.now += 600
        with self.assertRaises(RegistrationLimited) as caught: await self.limit.acquire()
        self.assertIsNone(caught.exception.retry_after)
    async def test_concurrent_instances_share_cap(self):
        outcomes = await asyncio.gather(*(RedisDCRLimiter(self.redis, 3).acquire()
                                        for _ in range(25)), return_exceptions=True)
        self.assertEqual(sum(x is None for x in outcomes), 5)
        self.assertEqual(sum(isinstance(x, RegistrationLimited) for x in outcomes), 20)
    async def test_rejected_provider_request_consumes_quota(self):
        for _ in range(5): await self.limit.acquire()  # Provider rejects after this.
        with self.assertRaises(RegistrationLimited): await self.limit.acquire()
    async def test_missing_and_corrupt_fail_closed(self):
        for value in (None, 'bad', '{}', '{"total":true,"window_count":0,"window_until":0}',
                      '{"total":0,"window_count":1,"window_until":0}',
                      '{"total":33,"window_count":0,"window_until":0}'):
            self.redis.values[self.limit.state_key] = value
            with self.assertRaises(RegistrationUnavailable): await self.limit.acquire()
            self.assertEqual(self.redis.values[self.limit.state_key], value)
    async def test_other_epoch_missing_fails_closed(self):
        with self.assertRaises(RegistrationUnavailable):
            await RedisDCRLimiter(self.redis, 4).acquire()
    async def test_future_window_or_bad_clock_fails_closed(self):
        self.redis.values[self.limit.state_key] = '{"total":1,"window_count":1,"window_until":9999}'
        with self.assertRaises(RegistrationUnavailable): await self.limit.acquire()
        self.redis.values[self.limit.state_key] = INITIAL_STATE
        self.redis.now = -1
        with self.assertRaises(RegistrationUnavailable): await self.limit.acquire()
    async def test_ambiguous_write_never_retried(self):
        class Ambiguous(FakeRedis):
            async def execute_command(self, *args):
                await super().execute_command(*args)
                raise RuntimeError('PRIVATE-CREDENTIAL')
        client = Ambiguous()
        with self.assertRaises(RegistrationUnavailable) as caught:
            await RedisDCRLimiter(client, 3).acquire()
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(json.loads(client.values[self.limit.state_key])['total'], 1)
        self.assertNotIn('PRIVATE-CREDENTIAL', str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)
    async def test_contention_is_bounded(self):
        class Contended(FakeRedis):
            async def execute_command(self, *args):
                self.calls.append(args)
                return None
        client = Contended()
        with self.assertRaises(RegistrationUnavailable): await RedisDCRLimiter(client, 3).acquire()
        self.assertEqual(len(client.calls), MAX_CONFLICT_RETRIES)
    async def test_timeout_fail_closed(self):
        class Slow(FakeRedis):
            async def get(self, key): await asyncio.sleep(1)
        with self.assertRaises(RegistrationUnavailable):
            await RedisDCRLimiter(Slow(), 3, timeout_seconds=.01).acquire()
    async def test_exact_key_only(self):
        await self.limit.acquire()
        self.assertEqual(self.redis.calls, [('SET', 'dot-dcr-e3:state', 'IFEQ')])
    def test_invalid_configuration(self):
        for epoch in (True, 0, -1, 1000001, '3'):
            with self.assertRaises(ValueError): RedisDCRLimiter(self.redis, epoch)
        for timeout in (True, 0, -1, 3, float('nan')):
            with self.assertRaises(ValueError): RedisDCRLimiter(self.redis, 3, timeout_seconds=timeout)

if __name__ == '__main__': unittest.main()
