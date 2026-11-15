"""Fail-closed DCR quotas using a single Redis 8.4 SET IFEQ state transition.

Reserve BEFORE parsing/validating POST /register; never refund failed requests.
One state key holds total/window count/deadline. Each successful reservation is
one standalone AOF SET, avoiding Redis 8.4's restricted-default-user MULTI/EXEC
AOF replay issue. Trusted bootstrap initializes INITIAL_STATE with SET NX once
per new epoch. Missing/corrupt state is never reinitialized by this module.

Dedicated ACL: ~dot-dcr-e<EPOCH>:state +get +set +time +ttl
No EVAL, MULTI, EXEC, control/OAuth-data or wildcard namespace access. Client
transport retry must be disabled. Only explicit compare conflicts are retried;
ambiguous timeout/network errors fail closed without retry or refund.

This is 5 attempts per anchored 600-second window, not a rolling-window limit,
and 32 attempts total per epoch. Rejected callbacks consume quota. Existing
clients/refresh requests must not call acquire(). Anonymous attackers can exhaust
new registration availability; total cap bounds registrations, not owner auth.
"""
import asyncio
import json

WINDOW_SECONDS = 600
WINDOW_LIMIT = 5
EPOCH_LIMIT = 32
MAX_CONFLICT_RETRIES = 8
INITIAL_STATE = '{"total":0,"window_count":0,"window_until":0}'


class RegistrationUnavailable(RuntimeError):
    def __init__(self):
        super().__init__('Registration temporarily unavailable')


class RegistrationLimited(RuntimeError):
    """429; retry_after=None means epoch cap, not a timed retry."""
    def __init__(self, *, retry_after=None):
        self.retry_after = retry_after
        super().__init__('Registration quota exceeded')


class RedisDCRLimiter:
    def __init__(self, client, epoch, *, timeout_seconds=0.5):
        if type(epoch) is not int or not 1 <= epoch <= 1_000_000:
            raise ValueError('positive bounded epoch required')
        if (type(timeout_seconds) not in (int, float)
                or not 0 < timeout_seconds <= 2):
            raise ValueError('bounded timeout required')
        self.client = client
        self.state_key = f'dot-dcr-e{epoch}:state'
        self.timeout_seconds = timeout_seconds

    async def acquire(self):
        try:
            await asyncio.wait_for(self._reserve(), timeout=self.timeout_seconds)
        except (RegistrationLimited, RegistrationUnavailable):
            raise
        except Exception:
            raise RegistrationUnavailable() from None

    async def _reserve(self):
        for _ in range(MAX_CONFLICT_RETRIES):
            raw = await self.client.get(self.state_key)
            if not isinstance(raw, (str, bytes)) or not 1 <= len(raw) <= 256:
                raise RegistrationUnavailable()
            try:
                state = json.loads(raw)
            except (ValueError, TypeError, UnicodeError):
                raise RegistrationUnavailable() from None
            if (not isinstance(state, dict)
                    or set(state) != {'total', 'window_count', 'window_until'}
                    or any(type(value) is not int for value in state.values())
                    or not 0 <= state['window_count'] <= WINDOW_LIMIT
                    or not state['window_count'] <= state['total'] <= EPOCH_LIMIT
                    or state['window_until'] < 0
                    or (state['window_until'] == 0 and state['window_count'] != 0)):
                raise RegistrationUnavailable()
            if await self.client.ttl(self.state_key) != -1:
                raise RegistrationUnavailable()
            server_time = await self.client.time()
            if (not isinstance(server_time, (list, tuple)) or len(server_time) != 2
                    or any(type(value) is not int for value in server_time)
                    or server_time[0] <= 0 or not 0 <= server_time[1] < 1_000_000):
                raise RegistrationUnavailable()
            now = server_time[0]
            if state['window_until'] > now + WINDOW_SECONDS:
                raise RegistrationUnavailable()
            if state['total'] >= EPOCH_LIMIT:
                raise RegistrationLimited()
            count, until = state['window_count'], state['window_until']
            if until <= now:
                count, until = 0, now + WINDOW_SECONDS
            if count >= WINDOW_LIMIT:
                raise RegistrationLimited(retry_after=until - now)
            new = json.dumps({'total': state['total'] + 1,
                              'window_count': count + 1,
                              'window_until': until}, separators=(',', ':'))
            result = await self.client.execute_command(
                'SET', self.state_key, new, 'IFEQ', raw)
            if result is True or result == 'OK' or result == b'OK':
                return
            if result is None:
                continue  # Explicit CAS mismatch only; state was not modified.
            raise RegistrationUnavailable()
        raise RegistrationUnavailable()
