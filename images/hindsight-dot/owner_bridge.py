"""Synthetic integration only. No listener/native secret or real upstream.
No semantic approval classifier; bounded summary text is NOT proven approved.
"""
import logging
import re
from fastmcp.server.auth.providers.google import GoogleProvider
from mcp.server.auth.provider import RegistrationError, AuthorizeError

BOOTSTRAP_SUBJECT="bootstrap-unverified-deny-all"

class OwnerGoogleProvider(GoogleProvider):
    def __init__(self, *, owner_sub, owner_email, bootstrap_identity_diagnostic=False, **kwargs):
        if bootstrap_identity_diagnostic and owner_sub!=BOOTSTRAP_SUBJECT:raise ValueError("bootstrap subject must deny all")
        self._upstream_client_id=kwargs["client_id"]
        self.exact_redirects=frozenset(kwargs.get("allowed_client_redirect_uris") or ())
        if not self.exact_redirects:raise ValueError("exact redirects required")
        self.bootstrap_identity_diagnostic=bootstrap_identity_diagnostic
        self._bootstrap_logged=False
        self._registration_events=0
        self.owner_sub,self.owner_email=owner_sub,owner_email
        super().__init__(**kwargs)
    def _registration_event(self, outcome):
        # Bounded, fixed vocabulary only. Never log client metadata, URIs,
        # exception text, authorization headers, codes or credentials.
        if self._registration_events < 16:
            logging.getLogger('uvicorn.error').info('DCR outcome=%s',outcome)
            self._registration_events += 1

    async def register_client(self, client_info):
        redirects=client_info.redirect_uris
        if not redirects or any(str(uri) not in self.exact_redirects for uri in redirects):
            self._registration_event('redirect_denied')
            raise RegistrationError("invalid_redirect_uri", "Exact registered callback required")
        try:
            await super().register_client(client_info)
        except Exception:
            self._registration_event('storage_or_provider_error')
            # Do not hand raw provider/storage exceptions to ASGI loggers.
            raise RegistrationError("invalid_client_metadata", "Registration unavailable") from None
        self._registration_event('accepted')

    async def authorize(self, client, params):
        redirect=str(params.redirect_uri)
        registered={str(uri) for uri in (client.redirect_uris or ())}
        if redirect not in self.exact_redirects or redirect not in registered:
            raise AuthorizeError("invalid_request", "Exact registered callback required")
        return await super().authorize(client, params)

    async def load_access_token(self, token):
        verified=await super().load_access_token(token)
        if not verified:return None
        c=verified.claims or {}
        if c.get('sub')!=verified.subject or c.get('aud')!=self._upstream_client_id:return None
        if c.get('email')!=self.owner_email or c.get('email_verified') not in (True,'true'):return None
        if self.bootstrap_identity_diagnostic:
            subject=verified.subject
            if not self._bootstrap_logged and isinstance(subject,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',subject):
                logging.getLogger('uvicorn.error').info('Bootstrap verified owner identity: sub=%s email=%s; MCP access denied',subject,self.owner_email)
                self._bootstrap_logged=True
            return None
        if verified.subject!=self.owner_sub:return None
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
