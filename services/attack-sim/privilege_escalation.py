from utils import base_url, default_headers, get_access_token, print_result, request_json


def main() -> None:
    token = get_access_token()
    target_path = "/v1/admin/flags"
    url = f"{base_url().rstrip('/')}{target_path}"

    headers = default_headers(token, "203.0.113.10", "aztdp-sim-user", "US-CA")
    response = request_json("GET", url, headers)
    print_result("priv_escalation", response)


if __name__ == "__main__":
    main()
