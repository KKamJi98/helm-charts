"""Fail-closed, Redis-backed quota for anonymous DCR attempts.

Call ``await limiter.acquire()`` BEFORE callback/provider validation, so rejected
registrations also consume quota. Never refund quota after a failed registration.
One successful reservation permits at most one provider registration call.

The trusted bootstrap path must initialize ``total_key`` to "0" with SET NX once
per NEW epoch. This module cannot initialize/reset it. Preserve the non-expiring
total key with Redis persistence. Missing/corrupt state fails closed, not open.
The window key has a 600-second TTL beginning at its first reserved attempt.
This is a bounded fixed-window quota, not a rolling ten-minute guarantee.

Dedicated limiter ACL: ~dot-dcr-e<EPOCH>:* +eval +get +incr +expire +ttl
No control/OAuth-data access, SET, DEL, FLUSH or administrative commands. Bootstrap
uses separate trusted credentials with narrowly scoped SET NX permission.
Rate limits bound registration attempts/epoch (including rejected callbacks),
not just pending clients. Existing linked clients remain valid when the cap is
reached; do not run acquire() on token/refresh requests. An attacker can exhaust
anonymous registration availability; existing-client auth is unaffected.
"""
import asyncio

WINDOW_SECONDS = 600
WINDOW_LIMIT = 5
EPOCH_LIMIT = 32

# Integer codes avoid incorporating Redis/server error text into public errors.
# Redis executes the two counters as one atomic operation. All state is read and
# validated before either INCR, so malformed state cannot partially reserve.
LUA_RESERVE = r"""
local raw_total = redis.call('GET', KEYS[1])
if not raw_total or not string.match(raw_total, '^%d+$') then return {-1, 0} end
if redis.call('TTL', KEYS[1]) ~= -1 then return {-1, 0} end
local total = tonumber(raw_total)
if not total or total > tonumber(ARGV[2]) then return {-1, 0} end
local raw_window = redis.call('GET', KEYS[2])
local window = 0
local retry = tonumber(ARGV[3])
if raw_window then
    if not string.match(raw_window, '^%d+$') then return {-1, 0} end
    window = tonumber(raw_window)
    if not window or window > tonumber(ARGV[1]) then return {-1, 0} end
    retry = redis.call('TTL', KEYS[2])
    if retry < 1 or retry > tonumber(ARGV[3]) then return {-1, 0} end
end
if total >= tonumber(ARGV[2]) then return {2, 0} end
if window >= tonumber(ARGV[1]) then return {0, retry} end
redis.call('INCR', KEYS[1])
local current = redis.call('INCR', KEYS[2])
if current == 1 then redis.call('EXPIRE', KEYS[2], ARGV[3]) end
return {1, 0}
"""


class RegistrationUnavailable(RuntimeError):
    """Counter unavailable/invalid: caller must refuse registration (503)."""
    def __init__(self):
        super().__init__('Registration temporarily unavailable')


class RegistrationLimited(RuntimeError):
    """Caller must refuse registration (429), never retry inside this request.

    retry_after is seconds for window exhaustion; None means the epoch cap
    requires an operator-reviewed new registration policy, not a timed retry.
    """
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
        self.total_key = f'dot-dcr-e{epoch}:total'
        self.window_key = f'dot-dcr-e{epoch}:window'
        self.timeout_seconds = timeout_seconds

    async def acquire(self):
        try:
            result = await asyncio.wait_for(
                self.client.eval(LUA_RESERVE, 2, self.total_key, self.window_key,
                                 WINDOW_LIMIT, EPOCH_LIMIT, WINDOW_SECONDS),
                timeout=self.timeout_seconds,
            )
        except Exception:
            # An ambiguous timeout may have consumed quota. Never retry/refund.
            raise RegistrationUnavailable() from None
        if (not isinstance(result, (list, tuple)) or len(result) != 2
                or any(type(item) is not int for item in result)):
            raise RegistrationUnavailable()
        code, retry = result
        if code == 1 and retry == 0:
            return None
        if code == 0 and 1 <= retry <= WINDOW_SECONDS:
            raise RegistrationLimited(retry_after=retry)
        if code == 2 and retry == 0:
            raise RegistrationLimited()
        raise RegistrationUnavailable()
