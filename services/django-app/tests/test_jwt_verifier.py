import pytest

from core.jwt import JwtVerificationError, JwtVerifier


def test_invalid_token_raises():
    v = JwtVerifier(
        issuer="http://kc/realms/aztdp",
        audience="aztdp-api",
        jwks_url="http://kc/realms/aztdp/protocol/openid-connect/certs",
        timeout=0.1,
    )
    with pytest.raises(JwtVerificationError):
        v.verify("not.a.jwt")
