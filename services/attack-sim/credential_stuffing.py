from utils import load_credentials, print_result, request_token, sleep_between, env


def main() -> None:
    creds_file = env("AZTDP_CREDENTIAL_FILE", "")
    credentials = load_credentials(creds_file)
    if not credentials:
        attack_user = env("AZTDP_ATTACK_USERNAME", env("AZTDP_USERNAME", "user"))
        attack_pass = env("AZTDP_ATTACK_PASSWORD", env("AZTDP_PASSWORD", "wrongpass"))
        credentials = [
            ("user1", "wrongpass"),
            ("user2", "wrongpass"),
            (attack_user, attack_pass),
        ]

    successes = 0
    failures = 0
    for username, password in credentials:
        response = request_token(username, password)
        if response.status_code == 200:
            successes += 1
        else:
            failures += 1
        print_result(f"attempt:{username}", response)
        sleep_between()

    print(f"summary successes={successes} failures={failures}")


if __name__ == "__main__":
    main()
