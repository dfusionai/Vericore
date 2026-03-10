"""
Tests for JWT auth middleware on the validator API.
Set JWT env vars before importing the app so the middleware uses test keys.
Requires full project deps (bittensor, fastapi, etc.) to be installed.
"""
import os
import time
import jwt
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

# Set test JWT config before any validator/api_server import (env is read at import time).
os.environ["VALIDATOR_JWT_PUBLIC_KEY"] = "test_secret_for_hmac"
os.environ["VALIDATOR_JWT_ALGORITHM"] = "HS256"

try:
    from fastapi.testclient import TestClient
    from validator.api_server import app
    from shared.veridex_protocol import VericoreQueryResponse
    _APP_AVAILABLE = True
except ModuleNotFoundError:
    _APP_AVAILABLE = False
    app = None
    TestClient = None
    VericoreQueryResponse = None

pytestmark = pytest.mark.skipif(not _APP_AVAILABLE, reason="Full project deps (bittensor, fastapi) required")

# JWT config the middleware must use so HS256 tokens validate (import order can leave default RS512).
_TEST_JWT_PUBLIC_KEY = "test_secret_for_hmac"
_TEST_JWT_ALGORITHM = "HS256"


def _make_valid_token():
    """Token with sub=validator_proxy and future exp, signed with test secret."""
    payload = {
        "sub": "validator_proxy",
        "exp": time.time() + 300,
    }
    return jwt.encode(
        payload,
        _TEST_JWT_PUBLIC_KEY,
        algorithm=_TEST_JWT_ALGORITHM,
    )


@pytest.fixture
def client():
    """TestClient with mocked startup so no real APIQueryHandler is created."""
    async def mock_startup():
        from validator import api_server as api_server_mod
        api_server_mod.app.state.handler = MagicMock()
        minimal_response = VericoreQueryResponse(
            validator_hotkey="",
            validator_uid=0,
            status="ok",
            request_id="req-1",
            statement="test",
            sources=[],
        )
        api_server_mod.app.state.handler.handle_query = AsyncMock(
            return_value=minimal_response
        )

    # Force middleware to use HS256 and test key (avoids RS512 default when env is read after other imports).
    with patch("validator.api_server.VALIDATOR_JWT_PUBLIC_KEY", _TEST_JWT_PUBLIC_KEY), patch(
        "validator.api_server.VALIDATOR_JWT_ALGORITHM", _TEST_JWT_ALGORITHM
    ), patch("validator.api_server.startup_event", mock_startup):
        with TestClient(app) as c:
            yield c


def test_version_without_auth_returns_200(client):
    """GET /version does not require Authorization."""
    response = client.get("/version")
    assert response.status_code == 200


def test_veridex_query_without_auth_returns_401(client):
    """POST /veridex_query without Authorization returns 401."""
    response = client.post(
        "/veridex_query",
        json={"statement": "test", "sources": []},
    )
    assert response.status_code == 401
    assert "detail" in response.json()


def test_veridex_query_with_invalid_token_returns_401(client):
    """POST /veridex_query with invalid Bearer token returns 401."""
    response = client.post(
        "/veridex_query",
        json={"statement": "test", "sources": []},
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401
    assert "detail" in response.json()


def test_veridex_query_with_expired_token_returns_401(client):
    """POST /veridex_query with expired JWT returns 401."""
    payload = {"sub": "validator_proxy", "exp": time.time() - 60}
    token = jwt.encode(
        payload,
        _TEST_JWT_PUBLIC_KEY,
        algorithm=_TEST_JWT_ALGORITHM,
    )
    response = client.post(
        "/veridex_query",
        json={"statement": "test", "sources": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert "detail" in response.json()


def test_veridex_query_with_valid_token_allowed(client):
    """POST /veridex_query with valid Bearer JWT is allowed (not 401)."""
    token = _make_valid_token()
    response = client.post(
        "/veridex_query",
        json={"statement": "test", "sources": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code != 401
    # Handler returns 200 with our mocked response
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"
    assert data.get("request_id") == "req-1"
