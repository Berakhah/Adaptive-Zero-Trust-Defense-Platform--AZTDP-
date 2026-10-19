import logging
import threading
import time
from typing import Dict, List, Optional, Protocol, Tuple

import redis as redis_lib

from . import config

logger = logging.getLogger("aztdp.gateway.revocation")


class RevocationPersistError(Exception):
    """A revocation could not be written to the durable store (Postgres).

    Callers must treat this as a failed revocation (fail closed): the gateway
    answers 503 revocation_not_persisted and the calling service still denies.
    """


class RevocationDB(Protocol):
    def insert_revocation(
        self, token_hash: str, expires_at: Optional[int], *, reason: str = ..., source: str = ...
    ) -> None: ...

    def active(self) -> List[Tuple[str, Optional[int]]]: ...


class PostgresRevocationDB:
    """token_revocations access for the gateway (role aztdp_gateway: SELECT+INSERT).

    Uses a short-lived connection per call: revocations are rare and the resync
    runs once per period, so a pool would mostly sit idle. connect_timeout keeps
    a dead database from hanging the revoke request.
    """

    def __init__(self, dsn: str, connect_timeout: int = 3, default_ttl_seconds: int = 3600) -> None:
        self._dsn = dsn
        self._connect_timeout = connect_timeout
        self._default_ttl = default_ttl_seconds

    def _connect(self):
        import psycopg

        return psycopg.connect(self._dsn, connect_timeout=self._connect_timeout)

    def insert_revocation(
        self,
        token_hash: str,
        expires_at: Optional[int],
        *,
        reason: str = "policy",
        source: str = "policy",
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO token_revocations (token_jti_hash, reason, source, expires_at) "
                    "VALUES (%s, %s, %s, to_timestamp(%s::double precision)) "
                    "ON CONFLICT (token_jti_hash) DO NOTHING",
                    (token_hash, reason, source, expires_at),
                )

    def active(self) -> List[Tuple[str, Optional[int]]]:
        """Revocations still in force, with their effective expiry (epoch seconds).

        Rows without expires_at are in force for the default TTL after
        revoked_at, matching the Redis TTL they were written with; this keeps
        the resync from re-seeding them forever.
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT token_jti_hash, "
                    "       extract(epoch FROM COALESCE(expires_at, "
                    "           revoked_at + make_interval(secs => %s)))::bigint "
                    "FROM token_revocations "
                    "WHERE COALESCE(expires_at, revoked_at + make_interval(secs => %s)) > now()",
                    (self._default_ttl, self._default_ttl),
                )
                return [(row[0], row[1]) for row in cur.fetchall()]


class InMemoryRevocationStore:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._data: Dict[str, float] = {}
        self._lock = threading.Lock()

    def revoke(self, token_hash: str, ttl_seconds: Optional[int] = None) -> None:
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        with self._lock:
            self._data[token_hash] = time.time() + ttl

    def is_revoked(self, token_hash: str) -> bool:
        with self._lock:
            expires_at = self._data.get(token_hash)
            if not expires_at:
                return False
            if expires_at < time.time():
                self._data.pop(token_hash, None)
                return False
            return True


class RevocationStore:
    """Revocation state: Postgres is the durable record, Redis the fast path.

    revoke() writes Postgres first, synchronously, then Redis. A failed DB write
    raises RevocationPersistError and nothing is cached, so a revocation is
    never reported as done unless it would survive a Redis loss. resync()
    re-seeds Redis from Postgres and runs at startup and periodically.
    """

    def __init__(self, redis=None, db: Optional[RevocationDB] = None) -> None:
        self._memory: Optional[InMemoryRevocationStore] = None
        if redis is not None:
            self._redis = redis
        elif config.REDIS_URL:
            self._redis = redis_lib.Redis.from_url(config.REDIS_URL, decode_responses=True)
        else:
            self._redis = None
            self._memory = InMemoryRevocationStore(config.REVOCATION_TTL_SECONDS)

        if db is not None:
            self._db = db
        elif config.DB_URL:
            self._db = PostgresRevocationDB(
                config.DB_URL,
                connect_timeout=config.DB_CONNECT_TIMEOUT,
                default_ttl_seconds=config.REVOCATION_TTL_SECONDS,
            )
        else:
            self._db = None
            logger.warning(
                "AZTDP_DB_URL is not set: revocations are NOT durable "
                "(cache only); do not run this way in production"
            )

        self._resync_stop = threading.Event()
        self._resync_thread: Optional[threading.Thread] = None
        self._resync_lock = threading.Lock()

    # -- writes ---------------------------------------------------------------

    def revoke(
        self,
        token_hash: str,
        expires_at: Optional[int] = None,
        *,
        reason: str = "policy",
        source: str = "policy",
    ) -> None:
        if not token_hash:
            return
        if self._db is not None:
            try:
                self._db.insert_revocation(token_hash, expires_at, reason=reason, source=source)
            except Exception as exc:
                logger.error("revocation not persisted for %s...: %s", token_hash[:12], exc)
                raise RevocationPersistError("revocation_not_persisted") from exc
        # Persisted (or no DB configured): now the fast path. A cache failure
        # here is healed by the next resync because the DB row exists.
        try:
            self._cache_set(token_hash, self._ttl_for(expires_at))
        except Exception as exc:
            logger.error(
                "revocation persisted but cache write failed for %s...: %s "
                "(next resync restores it)",
                token_hash[:12],
                exc,
            )
            if self._db is None:
                raise RevocationPersistError("revocation_not_persisted") from exc

    # -- reads ----------------------------------------------------------------

    def is_revoked(self, token_hash: str) -> bool:
        if not token_hash:
            return False
        if self._redis is not None:
            return self._redis.exists(self._key(token_hash)) == 1
        return self._memory.is_revoked(token_hash)

    # -- resync ---------------------------------------------------------------

    def resync(self) -> int:
        """Re-seed missing cache entries from the DB. Non-fatal on error.

        Returns the number of entries restored.
        """
        if self._db is None:
            return 0
        try:
            rows = self._db.active()
        except Exception as exc:
            logger.warning("revocation resync failed (non-fatal): %s", exc)
            return 0
        now = time.time()
        loaded = 0
        try:
            for token_hash, expires_at in rows:
                if expires_at is not None:
                    remaining = int(expires_at - now)
                    if remaining <= 0:
                        continue
                else:
                    remaining = config.REVOCATION_TTL_SECONDS
                # Only set if missing: never shorten a TTL another writer set.
                if not self.is_revoked(token_hash):
                    self._cache_set(token_hash, remaining)
                    loaded += 1
        except Exception as exc:
            logger.warning("revocation resync cache write failed (non-fatal): %s", exc)
        if loaded:
            logger.info("revocation resync: restored %d active revocations from DB", loaded)
        return loaded

    def cold_start_recovery(self) -> None:
        """Re-seed the cache from token_revocations on startup."""
        self.resync()

    def periodic_resync(self, interval_seconds: float) -> None:
        """Loop body of the resync thread: resync every interval until stopped.

        Covers a Redis restart (or flush) without a gateway restart.
        """
        while not self._resync_stop.wait(interval_seconds):
            self.resync()

    def start_periodic_resync(self, interval_seconds: float) -> threading.Thread:
        with self._resync_lock:
            if self._resync_thread is not None and self._resync_thread.is_alive():
                return self._resync_thread
            self._resync_stop.clear()
            self._resync_thread = threading.Thread(
                target=self.periodic_resync,
                args=(interval_seconds,),
                name="revocation-resync",
                daemon=True,
            )
            self._resync_thread.start()
            return self._resync_thread

    def stop_periodic_resync(self, timeout: float = 5.0) -> None:
        with self._resync_lock:
            self._resync_stop.set()
            thread = self._resync_thread
        if thread is not None:
            thread.join(timeout)

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _ttl_for(expires_at: Optional[int]) -> int:
        if expires_at is None:
            return config.REVOCATION_TTL_SECONDS
        return max(1, int(expires_at - time.time()))

    def _cache_set(self, token_hash: str, ttl_seconds: int) -> None:
        if self._redis is not None:
            self._redis.setex(self._key(token_hash), ttl_seconds, "1")
        else:
            self._memory.revoke(token_hash, ttl_seconds)

    @staticmethod
    def _key(token_hash: str) -> str:
        return f"revoked:token:{token_hash}"
