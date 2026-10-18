"""Task-specific abuse cases for deku/talent-roster-reel (G7 calibration fixture).

A worked example of what solution/golden_tests/abuse/ holds: the edges the
generic probe cannot know about -- races on the brief's unique keys, replays,
forged credentials. Every literal comes from instruction.md.
"""
import os
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

PRODUCER = ("producer@example.com", "deku-demo-pw-2026")


@pytest.fixture(scope="module")
def producer(base_url):
    r = httpx.post(f"{base_url}/api/auth/login", json={"email": PRODUCER[0], "password": PRODUCER[1]})
    assert r.status_code in (200, 201), f"login answered {r.status_code}: {r.text[:200]}"
    body = r.json()
    token = next(body[k] for k in ("token", "access_token", "bearer") if isinstance(body.get(k), str))
    with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=30) as c:
        yield c


def test_eight_simultaneous_creates_of_one_slug_land_once(producer):
    slug = f"abuse-race-{os.urandom(5).hex()}"
    body = {"kind": "work", "slug": slug, "title": "Abuse Race", "variant": "left"}
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = [f.result().status_code for f in [pool.submit(producer.post, "/api/studio/items", json=body)
                                                  for _ in range(8)]]
    assert not [c for c in codes if c >= 500], f"a create crashed: {codes}"
    assert sum(1 for c in codes if c in (200, 201)) == 1, f"exactly one create may win: {codes}"


def test_replayed_publish_never_errors(producer):
    slug = f"abuse-replay-{os.urandom(5).hex()}"
    created = producer.post("/api/studio/items", json={"kind": "work", "slug": slug,
                                                       "title": "Abuse Replay", "variant": "left"})
    assert created.status_code in (200, 201), created.text[:200]
    item_id = created.json()["id"]
    codes = [producer.post(f"/api/studio/items/{item_id}/publish", json={"published": False}).status_code
             for _ in range(3)]
    assert all(c < 500 for c in codes), f"a replayed publish crashed: {codes}"


@pytest.mark.parametrize("token", ["garbage", "Bearer", "x" * 4096, "eyJhbGciOiJub25lIn0.e30."])
def test_forged_bearer_is_refused_without_error(base_url, token):
    r = httpx.post(f"{base_url}/api/studio/items", headers={"Authorization": f"Bearer {token}"},
                   json={"kind": "work", "slug": "forged", "title": "Forged", "variant": "left"})
    assert 400 <= r.status_code < 500, f"a forged token answered {r.status_code}"
