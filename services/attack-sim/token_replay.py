from utils import base_url, default_headers, get_access_token, print_result, request_json, sleep_between


def main() -> None:
    token = get_access_token()
    target_path = "/v1/payments/123"
    url = f"{base_url().rstrip('/')}{target_path}"

    headers_a = default_headers(token, "203.0.113.10", "aztdp-sim-a", "US-CA")
    headers_b = default_headers(token, "198.51.100.22", "aztdp-sim-b", "US-NY")

    response_a = request_json("GET", url, headers_a)
    print_result("first_use", response_a)
    sleep_between()

    response_b = request_json("GET", url, headers_b)
    print_result("replay", response_b)


if __name__ == "__main__":
    main()
