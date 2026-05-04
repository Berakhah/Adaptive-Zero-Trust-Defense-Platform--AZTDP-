"""Escalating geographic drift attack: same token, hops US -> GB -> DE -> CN."""
from utils import base_url, default_headers, get_access_token, print_result, request_json, sleep_between


GEO_HOPS = [
    ("203.0.113.10", "US-CA", "aztdp-sim-us"),
    ("198.51.100.22", "GB-LDN", "aztdp-sim-gb"),
    ("192.0.2.45", "DE-BER", "aztdp-sim-de"),
    ("203.0.113.99", "CN-SHA", "aztdp-sim-cn"),
]


def main() -> None:
    token = get_access_token()
    url = f"{base_url().rstrip('/')}/v1/payments/123"

    for label, (ip, geo, ua) in zip(("us", "gb", "de", "cn"), GEO_HOPS):
        headers = default_headers(token, ip, ua, geo)
        response = request_json("GET", url, headers)
        print_result(f"geo_drift_{label}", response)
        sleep_between()


if __name__ == "__main__":
    main()
