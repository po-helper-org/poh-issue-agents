import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.repos import allowed_specs, is_allowed, parse_repo_specs


def test_parse_splits_concrete_and_masks():
    concrete, masks = parse_repo_specs(["o/a", "o/*", "org", "*", "  ", "x/y"])
    assert concrete == ["o/a", "x/y"]
    assert masks == ["o", "org", "*"]


def test_empty_list_allows_all():
    assert is_allowed("any/repo", [])
    assert is_allowed("any/repo", [""])  # ISSUE_AGENT_REPOS не задан → [""]


def test_star_allows_all():
    assert is_allowed("any/repo", ["*"])


def test_exact_match_case_insensitive():
    specs = ["po-helper-org/poh-helper"]
    assert is_allowed("po-helper-org/poh-helper", specs)
    assert is_allowed("PO-Helper-Org/POH-Helper", specs)
    assert not is_allowed("po-helper-org/other", specs)


def test_owner_mask():
    for spec in ("po-helper-org/*", "po-helper-org"):
        assert is_allowed("po-helper-org/anything", [spec])
        assert not is_allowed("someone-else/repo", [spec])


def test_mixed_specs():
    specs = ["a/one", "b/*"]
    assert is_allowed("a/one", specs)
    assert is_allowed("b/anything", specs)
    assert not is_allowed("a/two", specs)
    assert not is_allowed("c/x", specs)


def test_allowed_specs_from_env(monkeypatch):
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "a/b, c/* ,d")
    assert is_allowed("a/b", allowed_specs())
    assert is_allowed("c/anything", allowed_specs())
    assert is_allowed("d/x", allowed_specs())
    assert not is_allowed("e/y", allowed_specs())


def test_allowed_specs_unset_allows_all(monkeypatch):
    monkeypatch.delenv("ISSUE_AGENT_REPOS", raising=False)
    assert is_allowed("whatever/repo", allowed_specs())
