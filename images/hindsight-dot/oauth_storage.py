"""Route only the pinned SDK DCR collection outside the revocable epoch store.

No migration or fallback to a previous epoch. Unknown collections are revocable.
This uses the public AsyncKeyValue interface, not provider private attributes.
"""
REGISTRATION_COLLECTION = 'mcp-oauth-proxy-clients'
REGISTRATION_PREFIX = 'dot-registration-v1:'

class OAuthStorage:
    def __init__(self, sessions, registrations):
        self.sessions, self.registrations = sessions, registrations

    def _store(self, collection):
        return self.registrations if collection == REGISTRATION_COLLECTION else self.sessions

    async def get(self, key, *, collection=None):
        return await self._store(collection).get(key=key, collection=collection)

    async def get_many(self, keys, *, collection=None):
        return await self._store(collection).get_many(keys=keys, collection=collection)

    async def ttl(self, key, *, collection=None):
        return await self._store(collection).ttl(key=key, collection=collection)

    async def ttl_many(self, keys, *, collection=None):
        return await self._store(collection).ttl_many(keys=keys, collection=collection)

    async def put(self, key, value, *, collection=None, ttl=None):
        return await self._store(collection).put(key=key, value=value, collection=collection, ttl=ttl)

    async def put_many(self, keys, values, *, collection=None, ttl=None):
        return await self._store(collection).put_many(keys=keys, values=values, collection=collection, ttl=ttl)

    async def delete(self, key, *, collection=None):
        return await self._store(collection).delete(key=key, collection=collection)

    async def delete_many(self, keys, *, collection=None):
        return await self._store(collection).delete_many(keys=keys, collection=collection)
