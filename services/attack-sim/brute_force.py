from utils import env, print_result, request_token, sleep_between


def main() -> None:
    username = env("AZTDP_ATTACK_USERNAME", env("AZTDP_USERNAME", "user"))
    password_list = env("AZTDP_PASSWORD_LIST", "wrong1,wrong2,wrong3").split(",")

    successes = 0
    failures = 0
    for password in password_list:
        response = request_token(username, password.strip())
        if response.status_code == 200:
            successes += 1
        else:
            failures += 1
        print_result(f"attempt:{username}", response)
        sleep_between()

    print(f"summary successes={successes} failures={failures}")


if __name__ == "__main__":
    main()
