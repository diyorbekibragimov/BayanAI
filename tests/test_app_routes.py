"""The real FastAPI app (app.py, SPACE_ID unset): plan page and token-keyed file routes. Skipped if the app cannot be
built here (it needs gradio / fastrtc and the cached Silero VAD model)."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def client():
    try:
        import app as bayan_app
        from fastapi.testclient import TestClient
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"app not importable here: {e}")
    return TestClient(bayan_app.app)


def test_file_route_rejects_unknown_tokens_and_paths(client, tmp_path):
    from bayan import careplan

    for url in ("/files/" + "A" * 22 + "/care_plan.pdf", "/files/short/care_plan.pdf",
                "/files/..%2F..%2Fetc/passwd", "/plan/unknown"):
        r = client.get(url)
        assert r.status_code == 404, url
        if "%2F" not in url:      # a path that does not even match the route 404s in the Gradio mount
            assert r.headers.get("cache-control") == "no-store"
    (tmp_path / "care_plan.pdf").write_bytes(b"%PDF-1.4 test")
    (tmp_path / "note.md").write_text("private")
    tok = "T" * 22
    careplan.register_files(tok, tmp_path, ["care_plan.pdf"])
    r = client.get(f"/files/{tok}/care_plan.pdf")
    assert r.status_code == 200 and r.content == b"%PDF-1.4 test" and r.headers["content-type"] == "application/pdf"
    assert client.get(f"/files/{tok}/note.md").status_code == 404
    assert client.get(f"/files/{tok}/doctor_report.pdf").status_code == 404
    careplan.forget_files([tok])
    assert client.get(f"/files/{tok}/care_plan.pdf").status_code == 404


def test_plan_page_route_serves_an_approved_structured_plan(client):
    from bayan import careplan

    plan = {"lang": "en", "medicines": [{"name": "Paracetamol", "title_en": "Paracetamol 1 g",
                                         "note_en": "Take 1 g only when needed.", "prn": True}],
            "avoid": [{"en": "Penicillin medicines. You are allergic."}], "advice": [],
            "red_flags": [{"en": "Your chest pain comes back."}], "emergency": "999"}
    pid = careplan.create("en", plan)
    assert "almost ready" in client.get(f"/plan/{pid}").text
    careplan.approve(pid)
    r = client.get(f"/plan/{pid}")
    assert r.status_code == 200 and r.headers["x-robots-tag"] == "noindex"
    for needle in ("Your medicines", "Paracetamol 1 g", "Do not take", "Call 999 or come back now if"):
        assert needle in r.text
