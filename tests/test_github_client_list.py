import json
import github_client


def test_list_open_issues_parses_labels(monkeypatch):
    class R:
        returncode = 0
        stdout = json.dumps([{"number": 5, "title": "t", "body": "b",
                              "labels": [{"name": "advisor:consultation"}]}])
    monkeypatch.setattr(github_client.subprocess, "run", lambda *a, **k: R())
    monkeypatch.setattr(github_client, "_auth_headers",
                        lambda: {"Authorization": "Bearer x"})
    out = github_client.list_open_issues("o/r", 50)
    assert out[0]["number"] == 5
    assert out[0]["labels"] == ["advisor:consultation"]
