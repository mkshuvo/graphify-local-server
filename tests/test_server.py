import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure a graph exists for test fixture
test_graph = PROJECT_ROOT / "graphify-out" / "graph.json"
if not test_graph.exists():
    from server.graphify_service import _run_graphify_cmd
    # Extract code from server directory
    code_target = PROJECT_ROOT / "server"
    _run_graphify_cmd(["extract", str(code_target), "--code-only", "--output", str(PROJECT_ROOT)])

from server.main import app
from server.graphify_service import HAS_KUZU

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "graphify-local-server"
    assert "port" in data


def test_stats():
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert data["nodes"] > 0


def test_node_query():
    response = client.get("/api/node?label=GraphifyService")
    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "GraphifyService"
    assert "graphify_service.py" in data.get("source_file", "")


def test_neighbors():
    response = client.get("/api/neighbors?label=GraphifyService")
    assert response.status_code == 200
    data = response.json()
    assert "incoming" in data
    assert "outgoing" in data


def test_blast_radius():
    response = client.get("/api/blast-radius?symbol=GraphifyService&max_depth=3")
    assert response.status_code == 200
    data = response.json()
    assert "total_dependents_affected" in data
    assert "affected_files" in data
    assert data["total_dependents_affected"] >= 1
    assert any("main.py" in f or "routes.py" in f or "graphify_service.py" in f for f in data["affected_files"])


def test_call_flow():
    response = client.get("/api/callflow?symbol=GraphifyService&max_depth=3")
    assert response.status_code == 200
    data = response.json()
    assert "mermaid" in data
    assert data["mermaid"].startswith("graph TD")


def test_dead_code():
    response = client.get("/api/dead-code")
    assert response.status_code == 200
    data = response.json()
    assert "total_orphans_found" in data
    assert isinstance(data["orphans"], list)


def test_context_bundle():
    response = client.post(
        "/api/context-bundle",
        json={"symbols": ["GraphifyService", "setup_routes"], "token_budget": 4000}
    )
    assert response.status_code == 200
    data = response.json()
    assert "bundle" in data
    assert "GraphifyService" in data["bundle"]


def test_cypher_query():
    if not HAS_KUZU:
        pytest.skip("KuzuDB not installed")
    response = client.post(
        "/api/cypher",
        json={"query": "MATCH (c:CodeNode) RETURN c.label LIMIT 5"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["rows"]) > 0


if __name__ == "__main__":
    pytest.main(["-v", __file__])
