from core.client_ip import parse_cidrs, resolve_client_ip, resolve_geo


def test_untrusted_remote_addr_ignores_headers():
    trusted = parse_cidrs("10.0.0.0/8")
    ip, forwarded = resolve_client_ip(
        remote_addr="203.0.113.5",
        forwarded_for="1.2.3.4",
        x_client_ip="9.9.9.9",
        trusted_proxies=trusted,
    )
    assert ip == "203.0.113.5"
    assert forwarded is False


def test_trusted_proxy_honors_x_client_ip():
    trusted = parse_cidrs("10.0.0.0/8")
    ip, forwarded = resolve_client_ip(
        remote_addr="10.0.0.1",
        forwarded_for=None,
        x_client_ip="198.51.100.7",
        trusted_proxies=trusted,
    )
    assert ip == "198.51.100.7"
    assert forwarded is True


def test_trusted_proxy_falls_back_to_xff_first_hop():
    trusted = parse_cidrs("10.0.0.0/8")
    ip, _ = resolve_client_ip(
        remote_addr="10.0.0.1",
        forwarded_for="198.51.100.7, 10.0.0.1",
        x_client_ip=None,
        trusted_proxies=trusted,
    )
    assert ip == "198.51.100.7"


def test_resolve_geo_blocks_untrusted():
    trusted = parse_cidrs("10.0.0.0/8")
    assert resolve_geo("US-CA", "203.0.113.5", trusted) == ""
    assert resolve_geo("US-CA", "10.0.0.1", trusted) == "US-CA"


def test_empty_trusted_list_is_strict():
    ip, forwarded = resolve_client_ip(
        remote_addr="10.0.0.1",
        forwarded_for="1.2.3.4",
        x_client_ip="9.9.9.9",
        trusted_proxies=[],
    )
    assert ip == "10.0.0.1"
    assert forwarded is False


def test_cidr_parser_skips_garbage():
    nets = parse_cidrs("10.0.0.0/8, not-a-cidr, 192.168.0.0/16")
    assert len(nets) == 2
