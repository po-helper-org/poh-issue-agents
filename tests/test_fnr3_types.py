from shared.workflow_types import DeliveryZone, Taxonomy, ZoneAssignment, Increment


def test_fnr3_types_construct():
    z = DeliveryZone(name="jira-engine", boundary="одна итерация JIRA", surface="JIRA-Connector")
    t = Taxonomy(zones=[z])
    a = ZoneAssignment(issue_number=57, primary_zone="jira-engine")
    inc = Increment(name="MVP", rationale="фундамент", issue_numbers=[57, 60])
    assert t.zones[0].name == "jira-engine"
    assert a.secondary_zones == []
    assert inc.issue_numbers == [57, 60]
