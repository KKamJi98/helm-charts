"""Offline contract tests. FakeRedis models reservations, not Lua execution.
A real Redis/ACL integration test is required before deployment.
"""
import asyncio
import unittest

from rate_limit import (RedisDCRLimiter, RegistrationLimited, RegistrationUnavailable,
                        LUA_RESERVE)


class FakeRedis:
    def __init__(self):
        self.values = {'dot-dcr-e3:total': 0}
        self.expires = {}
        self.now = 0
        self.lock = asyncio.Lock()
        self.calls = []

    async def eval(self, script, numkeys, total, window, window_limit,
                   epoch_limit, window_seconds):
        async with self.lock:
            self.calls.append((script, numkeys, total, window))
            assert script == LUA_RESERVE and numkeys == 2
            if window in self.expires and self.expires[window] <= self.now:
                del self.values[window]
                del self.expires[window]
            if total in self.expires:
                return [-1, 0]
            t = self.values.get(total)
            w = self.values.get(window, 0)
            if type(t) is not int or not 0 <= t <= epoch_limit:
                return [-1, 0]
            if type(w) is not int or not 0 <= w <= window_limit:
                return [-1, 0]
            retry = window_seconds
            if window in self.values:
                retry = self.expires.get(window, self.now - 1) - self.now
                if not 1 <= retry <= window_seconds:
                    return [-1, 0]
            if t >= epoch_limit:
                return [2, 0]
            if w >= window_limit:
                return [0, retry]
            self.values[total] = t + 1
            self.values[window] = w + 1
            if w == 0:
                self.expires[window] = self.now + window_seconds
            return [1, 0]


class LimiterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = FakeRedis()
        self.limit = RedisDCRLimiter(self.redis, 3)

    async def test_five_then_429_and_window_expiry(self):
        for _ in range(5):
            await self.limit.acquire()
        self.redis.now = 60
        with self.assertRaises(RegistrationLimited) as e:
            await self.limit.acquire()
        self.assertEqual(e.exception.retry_after, 540)
        self.redis.now = 600
        await self.limit.acquire()
        self.assertEqual(self.redis.values[self.limit.total_key], 6)

    async def test_epoch_cap_survives_windows_and_process_restart(self):
        for index in range(32):
            self.redis.now = (index // 5) * 600
            await RedisDCRLimiter(self.redis, 3).acquire()
        self.redis.now += 600
        with self.assertRaises(RegistrationLimited) as e:
            await RedisDCRLimiter(self.redis, 3).acquire()
        self.assertIsNone(e.exception.retry_after)
        self.assertEqual(self.redis.values[self.limit.total_key], 32)

    async def test_concurrent_instances_share_one_cap(self):
        results = await asyncio.gather(
            *(RedisDCRLimiter(self.redis, 3).acquire() for _ in range(25)),
            return_exceptions=True,
        )
        self.assertEqual(sum(r is None for r in results), 5)
        self.assertEqual(sum(isinstance(r, RegistrationLimited) for r in results), 20)

    async def test_failed_callback_still_consumes_reserved_attempt(self):
        for _ in range(5):
            await self.limit.acquire()
            # Provider rejects callback after reservation; no refund API exists.
        with self.assertRaises(RegistrationLimited):
            await self.limit.acquire()

    async def test_missing_total_and_wrong_epoch_fail_closed(self):
        with self.assertRaises(RegistrationUnavailable):
            await RedisDCRLimiter(self.redis, 4).acquire()
        self.redis.values.clear()
        with self.assertRaises(RegistrationUnavailable):
            await self.limit.acquire()
        self.assertEqual(self.redis.values, {})

    async def test_corrupt_state_or_missing_window_ttl_fail_closed(self):
        for value in ('secret-invalid', -1, 33, True):
            self.redis.values[self.limit.total_key] = value
            with self.assertRaises(RegistrationUnavailable):
                await self.limit.acquire()
        self.redis.values[self.limit.total_key] = 0
        self.redis.values[self.limit.window_key] = 1
        with self.assertRaises(RegistrationUnavailable):
            await self.limit.acquire()
        self.assertEqual(self.redis.values[self.limit.total_key], 0)

    async def test_expiring_total_fails_closed(self):
        self.redis.expires[self.limit.total_key] = 600
        with self.assertRaises(RegistrationUnavailable):
            await self.limit.acquire()

    async def test_errors_are_fixed_and_never_retried(self):
        class Broken:
            calls = 0
            async def eval(self, *args):
                self.calls += 1
                raise RuntimeError('PRIVATE-CREDENTIAL')
        broken = Broken()
        with self.assertRaises(RegistrationUnavailable) as e:
            await RedisDCRLimiter(broken, 3).acquire()
        self.assertNotIn('PRIVATE-CREDENTIAL', str(e.exception))
        self.assertIsNone(e.exception.__cause__)
        self.assertTrue(e.exception.__suppress_context__)
        self.assertEqual(broken.calls, 1)

    async def test_timeout_fail_closed(self):
        class Slow:
            async def eval(self, *args):
                await asyncio.sleep(1)
        with self.assertRaises(RegistrationUnavailable):
            await RedisDCRLimiter(Slow(), 3, timeout_seconds=.01).acquire()

    async def test_unexpected_response_fails_closed(self):
        class Reply:
            def __init__(self, value): self.value = value
            async def eval(self, *args): return self.value
        for value in (None, [True, 0], [1], [0, 0], [0, 601], [2, 1], [-1, 0]):
            with self.assertRaises(RegistrationUnavailable):
                await RedisDCRLimiter(Reply(value), 3).acquire()

    async def test_only_exact_epoch_keys_are_passed(self):
        await self.limit.acquire()
        _, count, total, window = self.redis.calls[0]
        self.assertEqual((count, total, window),
                         (2, 'dot-dcr-e3:total', 'dot-dcr-e3:window'))

    def test_invalid_configuration(self):
        for epoch in (True, 0, -1, 1_000_001, '3'):
            with self.assertRaises(ValueError): RedisDCRLimiter(self.redis, epoch)
        for timeout in (True, 0, -1, 3, float('nan')):
            with self.assertRaises(ValueError):
                RedisDCRLimiter(self.redis, 3, timeout_seconds=timeout)


if __name__ == '__main__':
    unittest.main()
