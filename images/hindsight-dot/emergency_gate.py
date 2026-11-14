"""Isolated ASGI safety gate, not an OAuth issuer or deployed ingress policy.

Wrap ALL dedicated dot routes including /token. A trusted external status reader
must use an authoritative store (not a process-local cached flag). No public setter.
Each deployment pins an epoch; incrementing authoritative epoch invalidates all
old replicas. Starting again requires a new epoch deployment AND fresh OAuth
storage/signing identity; do not reenable a stale store.
"""
import asyncio
from dataclasses import dataclass
from starlette.responses import JSONResponse

@dataclass(frozen=True)
class GateStatus:
    enabled: bool
    epoch: int

class EmergencyGate:
    def __init__(self, app, read_status, epoch, status_timeout=0.5):
        if type(epoch) is not int or epoch < 1: raise ValueError('epoch')
        if not 0 < status_timeout <= 2: raise ValueError("status_timeout")
        self.app,self.read_status,self.epoch=app,read_status,epoch
        self.status_timeout=status_timeout
    async def __call__(self,scope,receive,send):
        if scope['type']=='lifespan':
            return await self.app(scope,receive,send)
        try:
            status=await asyncio.wait_for(self.read_status(), timeout=self.status_timeout)
            allowed=(type(status) is GateStatus and status.enabled is True and
                     type(status.epoch) is int and status.epoch==self.epoch)
        except Exception:
            allowed=False
        if not allowed:
            if scope['type']=='websocket':
                return await send({'type':'websocket.close','code':1008})
            return await JSONResponse({'error':'connection disabled'},503,
                headers={'Cache-Control':'no-store'})(scope,receive,send)
        return await self.app(scope,receive,send)
