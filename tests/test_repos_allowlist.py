"""Допуск репозитория, включая пути глубже двух сегментов."""

from shared.repos import is_allowed, parse_repo_specs


def test_exact_two_segment_match():
    assert is_allowed("po-helper-org/poh-demo-checkout",
                      ["po-helper-org/poh-demo-checkout"])


def test_exact_match_is_case_insensitive():
    assert is_allowed("PO-Helper-Org/Poh-Demo", ["po-helper-org/poh-demo"])


def test_owner_mask_matches_direct_child():
    assert is_allowed("po-helper-org/anything", ["po-helper-org/*"])


def test_bare_owner_is_the_same_as_mask():
    assert is_allowed("po-helper-org/anything", ["po-helper-org"])


def test_star_allows_everything():
    assert is_allowed("whoever/whatever", ["*"])


def test_empty_specs_allow_everything():
    assert is_allowed("whoever/whatever", [])
    assert is_allowed("whoever/whatever", [""])


def test_foreign_repo_is_rejected():
    assert not is_allowed("someone-else/repo", ["po-helper-org/*"])


# --- то, что ломалось до правки ---

def test_exact_three_segment_match():
    """Проект GitLab в подгруппе, записанный точно."""
    assert is_allowed("group/sub/project", ["group/sub/project"])


def test_subgroup_mask_matches_project_inside_it():
    assert is_allowed("group/sub/project", ["group/sub/*"])


def test_owner_mask_reaches_into_subgroups():
    """`group/*` покрывает и вложенные подгруппы — это осознанно."""
    assert is_allowed("group/sub/project", ["group/*"])


def test_subgroup_mask_does_not_match_sibling_subgroup():
    assert not is_allowed("group/other/project", ["group/sub/*"])


def test_mask_matches_on_segment_boundary_only():
    """`group/sub` не должна цеплять `group/subterfuge`."""
    assert not is_allowed("group/subterfuge/project", ["group/sub/*"])


def test_parse_splits_multi_segment_masks():
    concrete, masks = parse_repo_specs(["group/sub/*", "group/sub/project", "owner"])
    assert concrete == ["group/sub/project"]
    assert masks == ["group/sub", "owner"]
