import http.client
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from project_management.server import make_server
from project_management.sources import transcripts
from project_management.sources.redact import is_secret_path, redact

SECRET = "sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
THOUGHT = "PRIVATE-REASONING-MARKER"


def _write_transcript(path: Path, repo: Path) -> None:
    lines = [
        {"type": "custom-title", "customTitle": "עובד בדיקה", "sessionId": "s1"},
        {"type": "agent-name", "agentName": "old name", "sessionId": "s1"},
        {"type": "assistant", "timestamp": "2026-09-26T12:00:00Z", "message": {
            "id": "m1",
            "usage": {"input_tokens": 1000, "cache_creation_input_tokens": 9000, "cache_read_input_tokens": 240000},
            "content": [
                {"type": "thinking", "thinking": THOUGHT},
                {"type": "redacted_thinking", "data": THOUGHT},
                {"type": "text", "text": f"Working on it. key={SECRET}"},
                {"type": "tool_use", "name": "Edit", "input": {"file_path": str(repo / "app" / "x.py"), "old_string": THOUGHT}},
                {"type": "tool_use", "name": "Write", "input": {"file_path": str(repo / ".env"), "content": SECRET}},
                {"type": "tool_use", "name": "Bash", "input": {"command": f"curl -H 'Authorization: {SECRET}' && pytest"}},
                {"type": "tool_use", "name": "Read", "input": {"file_path": "C:/Users/someone/secret.txt"}},
            ]}},
        {"type": "user", "timestamp": "2026-09-26T12:00:05Z", "message": {"content": [
            {"type": "tool_result", "content": f"lots of output {SECRET}\n===== 84 passed, 1 warning in 12.34s ====="}]}},
        {"type": "assistant", "isSidechain": True, "timestamp": "2026-09-26T12:01:00Z", "message": {
            "id": "m2", "usage": {"input_tokens": 999999}, "content": [{"type": "text", "text": "subagent text"}]}},
        "this line is not json",
    ]
    with path.open("w", encoding="utf-8") as fh:
        for ln in lines:
            fh.write((ln if isinstance(ln, str) else json.dumps(ln, ensure_ascii=False)) + "\n")
        fh.write('{"type": "assistant", "partial')   # half-written trailing line


def test_transcript_adapter_privacy_and_estimate(tmp_path):
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    tdir = tmp_path / "t"
    tdir.mkdir()
    _write_transcript(tdir / "abc.jsonl", repo)
    reader = transcripts.TranscriptReader(tdir, repo)
    s = reader.for_titles(["old name"])          # former titles still map
    assert s is not None and s["title"] == "עובד בדיקה"
    dumped = json.dumps(s, ensure_ascii=False)
    assert THOUGHT not in dumped                  # never thinking / tool inputs
    assert SECRET not in dumped                   # redaction
    assert "curl" not in dumped and "Authorization" not in dumped   # never command text
    assert "subagent text" not in dumped          # sidechain ignored
    assert "secret.txt" not in dumped             # Read is not reported
    texts = [a["text"] for a in s["activity"]]
    assert "ערך את app/x.py" in texts
    assert "כתב את [קובץ סודות]" in texts
    assert "הריץ בדיקות" in texts
    assert any("84 passed, 1 warning in 12.34s" in t for t in texts)
    est = s["context_estimate"]
    assert est["tokens"] == 250000 and est["percent"] == 25.0   # sidechain usage not counted
    assert s["turns_last_hour"] == 0 or isinstance(s["turns_last_hour"], int)
    now = datetime(2026, 9, 26, 12, 30, tzinfo=timezone.utc)
    st = reader.refresh()[0]
    assert transcripts.summarize(st, now)["turns_last_hour"] == 1


def test_transcript_incremental_and_missing(tmp_path):
    assert transcripts.TranscriptReader(None, tmp_path).for_titles(["x"]) is None
    tdir = tmp_path / "t"
    tdir.mkdir()
    p = tdir / "a.jsonl"
    p.write_text(json.dumps({"type": "custom-title", "customTitle": "A"}) + "\n", encoding="utf-8")
    r = transcripts.TranscriptReader(tdir, tmp_path)
    assert r.for_titles(["A"])["context_estimate"] is None     # no usage → no number
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "assistant", "timestamp": "2026-09-26T12:00:00Z",
                             "message": {"usage": {"input_tokens": 100000}, "content": []}}) + "\n")
    assert r.for_titles(["A"])["context_estimate"]["percent"] == 10.0
    assert r.for_titles(["nobody"]) is None


def test_project_dir_name():
    assert transcripts.project_dir_name(Path(r"C:\Users\x\שולחן")) == "C--Users-x------"


def test_redaction():
    assert SECRET not in redact(f"token: {SECRET}")
    assert "hunter2" not in redact("password=hunter2")
    assert "ghp_" not in redact("ghp_abcdefghijklmnopqrstuvwxyz0123")
    assert redact("ran 84 tests in app/ingest/pipeline.py") == "ran 84 tests in app/ingest/pipeline.py"
    assert is_secret_path(".env") and is_secret_path("x/.env.local") and not is_secret_path(".env.example")


# ------------------------------------------------------------------ HTTP security

@pytest.fixture()
def server(tmp_path):
    (tmp_path / "ROADMAP.md").write_text("## Milestone 1 — A\n- [ ] x\n", encoding="utf-8")
    pm_dir = tmp_path / "pm"
    pm_dir.mkdir()
    (pm_dir / "state.json").write_text(json.dumps({"workers": [{"id": "W1", "name": "עובד"}]}), encoding="utf-8")
    httpd = make_server(0, repo=tmp_path, pm_dir=pm_dir, transcripts_dir=None)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield httpd, pm_dir
    httpd.shutdown()
    httpd.server_close()


def _req(httpd, method, path, host=None, headers=None, body=None):
    port = httpd.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": host or f"127.0.0.1:{port}"}
    h.update(headers or {})
    conn.request(method, path, body=body, headers=h)
    r = conn.getresponse()
    data = r.read()
    conn.close()
    return r.status, data, r


def test_binds_loopback_only(server):
    httpd, _ = server
    assert httpd.server_address[0] == "127.0.0.1"


def test_host_header_checked(server):
    httpd, _ = server
    port = httpd.server_address[1]
    assert _req(httpd, "GET", "/api/dashboard")[0] == 200
    assert _req(httpd, "GET", "/api/dashboard", host=f"localhost:{port}")[0] == 200
    assert _req(httpd, "GET", "/api/dashboard", host="evil.example")[0] == 403
    assert _req(httpd, "GET", "/", host=f"attacker.com:{port}")[0] == 403


def test_static_is_fixed_and_traversal_safe(server):
    httpd, _ = server
    status, body, resp = _req(httpd, "GET", "/")
    assert status == 200 and "default-src 'self'" in resp.getheader("Content-Security-Policy")
    for bad in ("/../state.example.json", "/..%2f..%2fMEMORY.md", "/web/app.js", "/server.py",
                "/%2e%2e/%2e%2e/.env", "//etc/passwd", "/app.js/../../README.md"):
        assert _req(httpd, "GET", bad)[0] == 404, bad


def _post(httpd, payload, **headers):
    port = httpd.server_address[1]
    h = {"Content-Type": "application/json", "Sec-Fetch-Site": "same-origin", "Origin": f"http://127.0.0.1:{port}"}
    h.update(headers)
    h = {k: v for k, v in h.items() if v is not None}
    return _req(httpd, "POST", "/api/request", headers=h, body=json.dumps(payload).encode())


def test_post_requires_same_origin_and_json(server):
    httpd, pm_dir = server
    ok = {"type": "continue_worker", "worker": "W1"}
    assert _post(httpd, ok, **{"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert _post(httpd, ok, **{"Sec-Fetch-Site": None})[0] == 403
    assert _post(httpd, ok, Origin="http://evil.example")[0] == 403
    assert _post(httpd, ok, **{"Content-Type": "text/plain"})[0] == 415
    assert not (pm_dir / "inbox.jsonl").exists()
    status, body, _ = _post(httpd, ok)
    assert status == 201
    item = json.loads(body)
    assert item["id"] == 1 and item["copy_text"] == "[בקשה מהדשבורד #1] המשך את עובד."
    assert _post(httpd, {"type": "continue_worker", "worker": "W99"})[0] == 400
    assert _post(httpd, ok, **{"Sec-Fetch-Site": "none"})[0] == 201


def test_other_methods_rejected(server):
    httpd, _ = server
    assert _req(httpd, "DELETE", "/api/request")[0] == 405
    assert _req(httpd, "PUT", "/api/request")[0] == 405


def test_dashboard_payload_has_no_env(server, tmp_path):
    httpd, _ = server
    (tmp_path / ".env").write_text(f"ANTHROPIC_API_KEY={SECRET}\n", encoding="utf-8")
    status, body, resp = _req(httpd, "GET", "/api/dashboard")
    assert status == 200 and resp.getheader("Cache-Control") == "no-store"
    assert SECRET.encode() not in body
