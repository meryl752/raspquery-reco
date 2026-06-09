from types import SimpleNamespace

from app.domain.catalog_filter import filter_catalog_agents


def test_filter_removes_inactive_even_without_blocklist():
    agents = [
        SimpleNamespace(id="1", name="Active Tool", catalog_status="active"),
        SimpleNamespace(id="2", name="Deprecated Tool", catalog_status="deprecated"),
    ]
    kept = filter_catalog_agents(agents)
    assert [a.name for a in kept] == ["Active Tool"]


def test_filter_defaults_missing_status_to_active():
    agents = [SimpleNamespace(id="1", name="No Status Tool")]
    kept = filter_catalog_agents(agents)
    assert len(kept) == 1
