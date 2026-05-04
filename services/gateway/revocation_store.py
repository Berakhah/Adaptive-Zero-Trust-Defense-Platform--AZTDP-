import logging
import time
from typing import Dict, Optional

import redis

from . import config

logger = logging.getLogger("aztdp.gateway.revocation")


class InMemoryRevocationStore:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._data: Dict[str, float] = {}

    def revoke(self, token_hash: str) -> None:
        self._data[token_hash] = time.time() + self.ttl_seconds

    def is_revoked(self, token_hash: str) -> bool:
        expires_at = self._data.get(token_hash)
        if not expires_at:
            return False
        if expires_at < time.time():
            self._data.pop(token_hash, None)
            return False
        return True


class RevocationStore:
    def __init__(self) -> None:
        if config.REDIS_URL:
            self._redis = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
        else:
            self._redis = None
            self._memory = InMemoryRevocationStore(config.REVOCATION_TTL_SECONDS)

    def cold_start_recovery(self) -> None:
        """Re-seed Redis from the token_revocations table on startup.

        This ensures that revoked tokens survive a simultaneous Redis + gateway
        restart. Rows without expires_at get the default TTL. Rows that have
        already expired are skipped.
        """
        db_url = config.DB_URL
        if not db_url or not self._redis:
            return
        try:
            import psycopg
            with psycopg.connect(db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT token_jti_hash, expires_at FROM token_revocations "
                        "WHERE expires_at IS NULL OR expires_at > now()"
                    )
                    loaded = 0
                    for row in cur:
                        token_hash, expires_at = row
                        if expires_at:
                            remaining = int((expires_at.timestamp()) - time.time())
                            if remaining <= 0:
                                continue
                        else:
                            remaining = config.REVOCATION_TTL_SECONDS
                        key = self._key(token_hash)
                        # Only set if not already present (another gateway may
                        # have revoked it with a longer TTL).
                        if not self._redis.exists(key):
                            self._redis.setex(key, remaining, "1")
                            loaded += 1
                    logger.info("cold-start recovery: loaded %d active revocations from DB", loaded)
        except Exception as exc:
            logger.warning("cold-start recovery failed (non-fatal): %s", exc)

    def revoke(self, token_hash: str) -> None:
        if not token_hash:
            return
        if self._redis:
            self._redis.setex(self._key(token_hash), config.REVOCATION_TTL_SECONDS, "1")
            return
        self._memory.revoke(token_hash)

    def is_revoked(self, token_hash: str) -> bool:
        if not token_hash:
            return False
        if self._redis:
            return self._redis.exists(self._key(token_hash)) == 1
        return self._memory.is_revoked(token_hash)

    @staticmethod
    def _key(token_hash: str) -> str:
        return f"revoked:token:{token_hash}"

