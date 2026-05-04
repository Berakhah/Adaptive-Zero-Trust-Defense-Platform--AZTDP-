"""P5.3 — IP-spoofing regression test.

Verifies that X-Client-Ip and X-Geo headers sent by an *untrusted* client are
ignored; only REMOTE_ADDR drives IP/geo when no trusted-proxy CIDR is configured.
This closes the attack surface from the P1.1 audit finding.
"""
import pytest
from core.client_ip import parse_cidrs, resolve_client_ip, resolve_geo


# ── Untrusted source — header values must be silently discarded ──────────────

class TestXClientIpSpoof:
    """P5.3: X-Client-Ip spoofing from an untrusted source is ignored."""

    def test_x_client_ip_spoof_is_ignored(self):
        """Core regression: spoofed X-Client-Ip must NOT replace REMOTE_ADDR."""
        trusted = parse_cidrs("")  # no trusted proxies → strict mode
        attacker_remote = "203.0.113.5"
        spoofed_ip = "10.0.0.1"  # internal IP the attacker wants to impersonate

        ip, was_forwarded = resolve_client_ip(
            remote_addr=attacker_remote,
            forwarded_for=None,
            x_client_ip=spoofed_ip,
            trusted_proxies=trusted,
        )

        assert ip == attacker_remote, (
            f"Expected REMOTE_ADDR {attacker_remote!r} but got {ip!r}. "
            "X-Client-Ip header from untrusted source must be rejected."
        )
        assert was_forwarded is False

    def test_x_forwarded_for_spoof_is_ignored(self):
        """Spoofed X-Forwarded-For must NOT replace REMOTE_ADDR."""
        trusted = parse_cidrs("")
        attacker_remote = "203.0.113.5"
        spoofed_chain = "10.0.0.1, 172.16.0.1"

        ip, _ = resolve_client_ip(
            remote_addr=attacker_remote,
            forwarded_for=spoofed_chain,
            x_client_ip=None,
            trusted_proxies=trusted,
        )

        assert ip == attacker_remote

    def test_geo_spoof_is_ignored(self):
        """Spoofed X-Geo must be discarded when source is untrusted."""
        trusted = parse_cidrs("")
        geo = resolve_geo("US-CA", remote_addr="203.0.113.5", trusted_proxies=trusted)
        assert geo == "", f"Expected empty geo but got {geo!r}"

    def test_all_private_ip_headers_ignored_without_trusted_proxy(self):
        """Even RFC-1918 source cannot inject headers without explicit trust."""
        trusted = parse_cidrs("")  # empty = no trust even for private IPs
        ip, _ = resolve_client_ip(
            remote_addr="10.0.0.1",
            forwarded_for="1.2.3.4",
            x_client_ip="9.9.9.9",
            trusted_proxies=trusted,
        )
        assert ip == "10.0.0.1"


# ── Trusted proxy — headers ARE honored from known ingress CIDRs ─────────────

class TestTrustedProxyHeaderHonored:
    """Confirm that the legitimate ingress path still works after the fix."""

    NGINX_CIDR = "172.20.0.0/16"
    NGINX_IP = "172.20.0.2"

    def test_trusted_proxy_x_client_ip_accepted(self):
        trusted = parse_cidrs(self.NGINX_CIDR)
        real_client = "198.51.100.7"

        ip, forwarded = resolve_client_ip(
            remote_addr=self.NGINX_IP,
            forwarded_for=None,
            x_client_ip=real_client,
            trusted_proxies=trusted,
        )

        assert ip == real_client
        assert forwarded is True

    def test_trusted_proxy_xff_first_hop_accepted(self):
        trusted = parse_cidrs(self.NGINX_CIDR)
        ip, _ = resolve_client_ip(
            remote_addr=self.NGINX_IP,
            forwarded_for="198.51.100.7, 172.20.0.2",
            x_client_ip=None,
            trusted_proxies=trusted,
        )
        assert ip == "198.51.100.7"

    def test_trusted_proxy_geo_accepted(self):
        trusted = parse_cidrs(self.NGINX_CIDR)
        geo = resolve_geo("FR-75", remote_addr=self.NGINX_IP, trusted_proxies=trusted)
        assert geo == "FR-75"

    def test_x_client_ip_takes_precedence_over_xff(self):
        """When both headers are present, X-Client-Ip wins."""
        trusted = parse_cidrs(self.NGINX_CIDR)
        ip, _ = resolve_client_ip(
            remote_addr=self.NGINX_IP,
            forwarded_for="1.1.1.1",
            x_client_ip="2.2.2.2",
            trusted_proxies=trusted,
        )
        assert ip == "2.2.2.2"
