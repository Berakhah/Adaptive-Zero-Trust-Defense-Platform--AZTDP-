"""Burst attack: 100 requests in ~10 seconds to spike request_rate_1m."""
import time

from utils import base_url, default_headers, get_access_token, print_result, request_json


REQUEST_COUNT = 100
WINDOW_SECONDS = 10.0


def main() -> None:
    token = get_access_token()
    url = f"{base_url().rstrip('/')}/v1/payments/123"
    headers = default_headers(token, "203.0.113.10", "aztdp-flood", "US-CA")

    delay = WINDOW_SECONDS / REQUEST_COUNT
    blocked = 0
    allowed = 0
    started = time.time()
    for i in range(REQUEST_COUNT):
        response = request_json("GET", url, headers)
        if response.status_code in (401, 403):
            blocked += 1
        elif response.status_code == 200:
            allowed += 1
        if i in (0, REQUEST_COUNT // 2, REQUEST_COUNT - 1):
            print_result(f"flood_{i}", response)
        time.sleep(delay)

    elapsed = time.time() - started
    print(f"flood_summary count={REQUEST_COUNT} elapsed={elapsed:.2f}s allowed={allowed} blocked={blocked}")


if __name__ == "__main__":
    main()
