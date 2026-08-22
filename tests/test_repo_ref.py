"""Разбор ссылки на репозиторий, переживающий вложенные подгруппы."""

import pytest

from shared.repo_ref import RepoRef


def test_github_two_segments():
    ref = RepoRef.parse("po-helper-org/poh-demo-checkout")
    assert ref.provider == "github"
    assert ref.owner == "po-helper-org"
    assert ref.name == "poh-demo-checkout"
    assert str(ref) == "po-helper-org/poh-demo-checkout"


def test_github_api_segment_is_path_as_is():
    """У GitHub путь — валидный сегмент URL, кодировать нечего."""
    ref = RepoRef.parse("po-helper-org/poh-demo-checkout")
    assert ref.api_segment == "po-helper-org/poh-demo-checkout"


def test_gitlab_nested_subgroups_are_kept():
    ref = RepoRef.parse("group/sub1/sub2/project", provider="gitlab")
    assert ref.owner == "group"
    assert ref.name == "project"
    assert ref.segments == ("group", "sub1", "sub2", "project")


def test_gitlab_api_segment_is_url_encoded():
    """GitLab адресует проект либо числовым id, либо путём с %2F."""
    ref = RepoRef.parse("group/sub/project", provider="gitlab")
    assert ref.api_segment == "group%2Fsub%2Fproject"


def test_gitlab_numeric_id_wins_over_path():
    ref = RepoRef.parse("group/sub/project", provider="gitlab", project_id=85622870)
    assert ref.api_segment == "85622870"


def test_surrounding_slashes_and_spaces_are_stripped():
    assert RepoRef.parse("  /owner/repo/  ").path == "owner/repo"


def test_single_segment_is_rejected():
    with pytest.raises(ValueError, match="как минимум два сегмента"):
        RepoRef.parse("owner")


def test_empty_is_rejected():
    with pytest.raises(ValueError):
        RepoRef.parse("   ")


def test_is_hashable_and_comparable():
    """Ссылка ходит ключом словаря в кэше токенов."""
    a = RepoRef.parse("o/r")
    b = RepoRef.parse("o/r")
    assert a == b and hash(a) == hash(b)
    assert len({a, b}) == 1
