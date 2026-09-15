from frek_workforce_catalog import FREK_WORKFORCE
from frek_workforce_adl import build_catalog
from frek_workforce_contracts import capability_contract, static_catalog
from frek_workforce_seed import validate_adl


def test_exactly_38_unique_agents_and_capabilities():
    assert len(FREK_WORKFORCE) == 38
    assert len({r.id for r in FREK_WORKFORCE}) == 38
    assert len({r.capability for r in FREK_WORKFORCE}) == 38
    assert [r.id for r in FREK_WORKFORCE] == [f"AGT-{i:03d}" for i in range(301, 339)]


def test_entity_distribution():
    counts = {}
    for role in FREK_WORKFORCE:
        counts[role.entity] = counts.get(role.entity, 0) + 1
    assert counts == {"FREKCORE": 10, "FREKANSLA": 10, "FREKRAW": 9, "FREK Luciole": 9}


def test_all_adl_v2_documents_validate():
    catalog = build_catalog("2026-09-15T00:00:00+00:00")
    assert len(catalog) == 38
    for adl in catalog:
        assert validate_adl(adl) == [], adl["agent"]["id"]


def test_all_agents_start_prototype_dry_run_on_demand():
    for adl in build_catalog("2026-09-15T00:00:00+00:00"):
        assert adl["agent"]["status"] == "PROTOTYPE"
        assert adl["cvln_governance"]["runtime_mode"] == "dry_run"
        assert adl["cvln_governance"]["activation"] == "on_demand"
        assert adl["cvln_governance"]["self_permission_expansion"] is False
        assert adl["cvln_governance"]["orchestrator"] == "MetaCVLN"
        assert adl["cvln_governance"]["controller"] == "CVLN Agent Factory"


def test_no_agent_has_global_write_wildcard():
    for role in FREK_WORKFORCE:
        assert "*" not in role.write_scope
        assert "*:*" not in role.write_scope


def test_all_capabilities_project_to_metacvln_contract_v1():
    catalog = static_catalog()
    assert len(catalog) == 38
    ids = set()
    for item in catalog:
        contract = item["capability"]
        executor = item["executor"]
        assert contract["contract"] == "capability"
        assert contract["version"] == "1.0"
        assert contract["health"] == "amber"  # Prototype/dry-run is discoverable, not production-green.
        assert contract["id"] not in ids
        ids.add(contract["id"])
        assert executor["agent_id"].startswith("AGT-")
        assert executor["controller"] == "CVLN Agent Factory"
        assert executor["runtime_mode"] == "dry_run"
        assert executor["activation"] == "on_demand"


def test_human_gate_is_reflected_in_capability_contract():
    gated = [r for r in FREK_WORKFORCE if r.human_gate]
    ungated = [r for r in FREK_WORKFORCE if not r.human_gate]
    assert gated and ungated
    for role in gated:
        contract = capability_contract(role, status="Prototype", runtime_state="sommeil")
        assert contract["requires_approval_by"] == "human:admin"
        assert contract["escalation_to"] == "human:admin"
    for role in ungated:
        contract = capability_contract(role, status="Prototype", runtime_state="sommeil")
        assert contract["requires_approval_by"] is None
        assert contract["escalation_to"] == "AGT-000"
