import os
import time
import uuid
from typing import Iterable, List, Tuple

import requests


def env(name: str, default: str | None = None) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        return default or ""
    return value


def token_endpoint() -> str:
    return env(
        "AZTDP_KEYCLOAK_TOKEN_URL",
        "http://keycloak:8080/realms/aztdp/protocol/openid-connect/token",
    )


def client_id() -> str:
    return env("AZTDP_CLIENT_ID", "aztdp-api")


def client_secret() -> str:
    return env("AZTDP_CLIENT_SECRET", "")


def base_url() -> str:
    return env("AZTDP_BASE_URL", "http://localhost:8000")


def request_delay_seconds() -> float:
    return float(env("AZTDP_REQUEST_DELAY_MS", "100")) / 1000.0


def get_access_token() -> str:
    token = env("AZTDP_ACCESS_TOKEN", "")
    if token:
        return token

    username = env("AZTDP_USERNAME", "")
    password = env("AZTDP_PASSWORD", "")
    if not username or not password:
        raise RuntimeError("missing_access_token_or_credentials")

    response = request_token(username, password)
    if response.status_code != 200:
        raise RuntimeError(f"token_request_failed:{response.status_code}")
    payload = response.json()
    return payload.get("access_token", "")


def request_token(username: str, password: str) -> requests.Response:
    data = {
        "grant_type": "password",
        "client_id": client_id(),
        "username": username,
        "password": password,
    }
    if client_secret():
        data["client_secret"] = client_secret()

    return requests.post(
        token_endpoint(),
        data=data,
        timeout=(0.6, 3.0),
    )


def load_credentials(path: str) -> List[Tuple[str, str]]:
    credentials: List[Tuple[str, str]] = []
    if not path:
        return credentials
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            username, password = line.split(":", 1)
            credentials.append((username.strip(), password.strip()))
    return credentials


def default_headers(token: str, ip: str, user_agent: str, geo: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "X-Request-Id": str(uuid.uuid4()),
        "X-Client-Ip": ip,
        "User-Agent": user_agent,
        "X-Geo": geo,
    }


def request_json(method: str, url: str, headers: dict) -> requests.Response:
    return requests.request(method, url, headers=headers, timeout=(0.6, 3.0))


def sleep_between() -> None:
    delay = request_delay_seconds()
    if delay > 0:
        time.sleep(delay)


def print_result(label: str, response: requests.Response) -> None:
    try:
        payload = response.json()
    except ValueError:
        payload = response.text
    print(f"{label} status={response.status_code} body={payload}")
