"""Synthetic integration only. No listener/native secret or real upstream.
No semantic approval classifier; bounded summary text is NOT proven approved.
"""
from fastmcp.server.auth.providers.google import GoogleProvider

class OwnerGoogleProvider(GoogleProvider):
    def __init__(self, *, owner_sub, owner_email, **kwargs):
        self.owner_sub,self.owner_email=owner_sub,owner_email
        super().__init__(**kwargs)
    async def load_access_token(self, token):
        verified=await super().load_access_token(token)
        if not verified:return None
        c=verified.claims or {}
        if verified.subject!=self.owner_sub or c.get('email')!=self.owner_email:return None
        if c.get('email_verified') not in (True,'true'):return None
        return verified

class CapabilityVerifier:
    """Owner identity plus authoritative kill state; readonly unless opted in."""
    def __init__(self, provider, *, read_status, epoch, capabilities=('hindsight:recall',)):
        allowed=frozenset(capabilities)
        if not allowed or not allowed <= {'hindsight:recall','hindsight:retain'}:
            raise ValueError('capabilities')
        self.provider,self.read_status,self.epoch=provider,read_status,epoch
        self.capabilities=allowed
    async def verify_token(self, token):
        import asyncio
        from emergency_gate import GateStatus
        async def enabled():
            try:
                s=await asyncio.wait_for(self.read_status(),timeout=0.5)
                return type(s) is GateStatus and s.enabled is True and type(s.epoch) is int and s.epoch==self.epoch
            except Exception:return False
        if not await enabled():return None
        owner=await self.provider.load_access_token(token)
        if owner is None or not await enabled():return None
        return owner.model_copy(update={'scopes':sorted(self.capabilities)})
