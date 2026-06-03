import pytest


@pytest.mark.asyncio
async def test_cors_preflight_allows_frontend_origin(client):
    # A browser preflight (OPTIONS) for a credentialed cross-origin request must
    # be answered with the matching Access-Control-* headers, or the frontend
    # cannot talk to the backend cross-origin.
    resp = await client.options(
        "/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert resp.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_cors_simple_request_echoes_origin(client):
    resp = await client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert resp.headers.get("access-control-allow-credentials") == "true"
