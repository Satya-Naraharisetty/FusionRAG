import json
from pathlib import Path

import pytest

DASHBOARD_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "observability"
    / "grafana"
    / "dashboards"
)

EXPECTED_DASHBOARDS = [
    "rag-retrieval.json",
    "llm-provider.json",
    "queue-worker.json",
    "http-slo.json",
]


@pytest.mark.parametrize("filename", EXPECTED_DASHBOARDS)
def test_grafana_dashboard_json_syntax_and_structure(filename):
    file_path = DASHBOARD_DIR / filename
    assert file_path.exists(), f"Dashboard file {filename} not found in {DASHBOARD_DIR}"

    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    assert "title" in data
    assert "uid" in data
    assert "panels" in data
    assert isinstance(data["panels"], list)
    assert len(data["panels"]) > 0

    # Verify each panel's targets and query expressions
    for panel in data["panels"]:
        if panel.get("type") == "row":
            continue
        targets = panel.get("targets", [])
        for target in targets:
            expr = target.get("expr", "")
            assert expr != "", (
                f"Empty PromQL expression in {filename} panel {panel.get('title')}"
            )
            # Ensure no invalid syntax like multiple quantile values inside a single histogram_quantile
            assert "0.50|0.95" not in expr
            assert "P50|P95" not in expr


def test_queue_worker_dashboard_labels():
    file_path = DASHBOARD_DIR / "queue-worker.json"
    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    # Positive assertions: aligned with worker.py emitted labels
    assert 'status=\\"success\\"' in content or 'status="success"' in content
    assert 'status=\\"dead_letter\\"' in content or 'status="dead_letter"' in content

    # Negative assertions: ensure stale label names do not exist
    assert (
        'status=\\"completed\\"' not in content and 'status="completed"' not in content
    )
    assert (
        'status=\\"dead_lettered\\"' not in content
        and 'status="dead_lettered"' not in content
    )
