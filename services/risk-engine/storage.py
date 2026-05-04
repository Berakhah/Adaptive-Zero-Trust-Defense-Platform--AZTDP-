import json
import time
from typing import Any, Dict, Optional

import redis

from . import config


class InMemoryStore:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._data: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        entry = self._data.get(key)
        if not entry:
            return None
        if entry["expires_at"] < time.time():
            self._data.pop(key, None)
            return None
        return entry["value"]

    def set(self, key: str, value: Dict[str, Any]) -> None:
        self._data[key] = {"value": value, "expires_at": time.time() + self.ttl_seconds}


class ReplayStore:
    def __init__(self) -> None:
        if config.REDIS_URL:
            self._redis = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
        else:
            self._redis = None
            self._memory = InMemoryStore(config.TOKEN_TTL_SECONDS)

    def get_last_seen(self, token_hash: str) -> Optional[Dict[str, Any]]:
        if not token_hash:
            return None
        if self._redis:
            value = self._redis.get(self._key(token_hash))
            return json.loads(value) if value else None
        return self._memory.get(token_hash)

    def set_last_seen(self, token_hash: str, value: Dict[str, Any]) -> None:
        if not token_hash:
            return
        if self._redis:
            self._redis.setex(self._key(token_hash), config.TOKEN_TTL_SECONDS, json.dumps(value))
            return
        self._memory.set(token_hash, value)

    @staticmethod
    def _key(token_hash: str) -> str:
        return f"token:last_seen:{token_hash}"
