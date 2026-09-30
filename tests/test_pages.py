"""Smoke tests for the server-rendered HTML pages (/, /login, /admin)."""

import pytest


@pytest.mark.parametrize("path", ["/", "/login", "/admin"])
def test_html_page_renders(client, path):
    res = client.get(path)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert "<html" in res.text


def test_root_injects_csp_nonce(client):
    res = client.get("/")
    csp = res.headers.get("content-security-policy", "")
    assert "nonce-" in csp
    nonce = csp.split("nonce-", 1)[1].split("'", 1)[0]
    assert f'nonce="{nonce}"' in res.text
