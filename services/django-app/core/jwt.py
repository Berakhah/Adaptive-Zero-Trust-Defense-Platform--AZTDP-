import time
from dataclasses import dataclass
from typing import Any, Dict

import jwt
import requests


class JwtVerificationError(Exception):
    pass


@dataclass
class JwksCache:
    jwks: Dict[str, Any]
    expires_at: float


class JwtVerifier:
    def __init__(self, issuer: str, audience: str, jwks_url: str, timeout: float) -> None:
        self.issuer = issuer
        self.audience = audience
        self.jwks_url = jwks_url
        self.timeout = timeout
        self._cache: JwksCache | None = None

    def _fetch_jwks(self) -> Dict[str, Any]:
        response = requests.get(self.jwks_url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _get_jwks(self) -> Dict[str, Any]:
        now = time.time()
        if self._cache and self._cache.expires_at > now:
            return self._cache.jwks
        jwks = self._fetch_jwks()
        self._cache = JwksCache(jwks=jwks, expires_at=now + 300)
        return jwks

    def _get_signing_key(self, kid: str) -> Any:
        jwks = self._get_jwks()
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)
        raise JwtVerificationError("jwks_key_not_found")

    def verify(self, token: str) -> Dict[str, Any]:
        try:
            unverified_header = jwt.get_unverified_header(token)
            key = self._get_signing_key(unverified_header.get("kid", ""))
            return jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
            )
        except jwt.PyJWTError as exc:
            raise JwtVerificationError("invalid_token") from exc
        except requests.RequestException as exc:
            raise JwtVerificationError("jwks_unavailable") from exc
