"""C1 regression: list[UnifyingIssueDraft] must round-trip through Temporal's
default data converter as real dataclass instances, not dicts.

Context: worker/consolidation_activities.py:write_consolidation_pr previously
annotated its `drafts` parameter as a bare `list`. Under Temporal's default
data converter, a bare `list` type hint decodes payloads as `list[dict]`
rather than `list[UnifyingIssueDraft]`, so `d.cluster_id` inside the activity
raised AttributeError at runtime (dicts don't support attribute access).
Annotating the parameter as `list[UnifyingIssueDraft]` fixes decoding.
This test proves the annotated form round-trips correctly.
"""
from temporalio.converter import default as _default_converter

from shared.workflow_types import UnifyingIssueDraft


def test_unifying_draft_list_roundtrips_as_objects():
    conv = _default_converter().payload_converter
    drafts = [UnifyingIssueDraft(cluster_id="cluster-1-2", title="T",
                                 body_markdown="# b", source_issue_numbers=[1, 2])]
    payloads = conv.to_payloads([drafts])
    # Decoding with the ANNOTATED type must yield real dataclass instances:
    decoded = conv.from_payloads(payloads, [list[UnifyingIssueDraft]])[0]
    assert isinstance(decoded[0], UnifyingIssueDraft)
    assert decoded[0].cluster_id == "cluster-1-2"       # attribute access, not dict
    assert decoded[0].source_issue_numbers == [1, 2]


def test_bare_list_hint_decodes_as_dicts_not_objects():
    """Sanity check documenting the bug this guards against: without a
    concrete element type hint, the default converter yields plain dicts,
    which is exactly what caused the AttributeError in production."""
    conv = _default_converter().payload_converter
    drafts = [UnifyingIssueDraft(cluster_id="cluster-1-2", title="T",
                                 body_markdown="# b", source_issue_numbers=[1, 2])]
    payloads = conv.to_payloads([drafts])
    decoded = conv.from_payloads(payloads, [list])[0]
    assert isinstance(decoded[0], dict)
    assert not isinstance(decoded[0], UnifyingIssueDraft)
