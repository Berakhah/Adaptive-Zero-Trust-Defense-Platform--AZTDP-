from unittest.mock import patch, MagicMock

import pytest
import requests

from gateway import opa_client


def _ok_response(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_evaluate_returns_parsed_json():
    fake = _ok_response({"result": {"decision": "allow"}})
    with patch.object(opa_client.requests, "post", return_value=fake):
        out = opa_client.evaluate({"input": {"x": 1}})
    assert out == {"result": {"decision": "allow"}}


def test_evaluate_wraps_request_errors():
    with patch.object(opa_client.requests, "post", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(opa_client.OpaClientError):
            opa_client.evaluate({"input": {}})
