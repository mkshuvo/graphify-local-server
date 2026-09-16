#!/usr/bin/env python3
"""
Graphify MCP Server (Pure Python Standard Library)
Zero external host dependencies required.
Communicates with any MCP client (Antigravity, Claude Code, Cursor, Windsurf, Codex, etc.)
via JSON-RPC 2.0 over stdio and forwards tool calls to the local Graphify server at http://localhost:28848.
"""

import sys
import json
import os
import urllib.request
import urllib.parse
import urllib.error

# Ensure UTF-8 stdio encoding across all platforms (especially Windows)
if hasattr(sys.stdin, "reconfigure"):
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

GRAPHIFY_SERVER_URL = os.getenv("GRAPHIFY_SERVER_URL", "http://localhost:28848").rstrip("/")
GRAPHIFY_API_KEY = os.getenv("GRAPHIFY_API_KEY", "").strip()

TOOLS = [
    {
        "name": "graphify_query",
        "description": "Search the codebase knowledge graph using BFS or DFS traversal. Returns relevant nodes, connections, and architectural context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Natural language question or search query about the codebase"
                },
                "mode": {
                    "type": "string",
                    "enum": ["bfs", "dfs"],
                    "default": "bfs",
                    "description": "bfs=broad architectural context, dfs=trace a specific execution path"
                },
                "depth": {
                    "type": "integer",
                    "default": 3,
                    "description": "Traversal depth from matched nodes (1-6)"
                },
                "token_budget": {
                    "type": "integer",
                    "default": 2000,
                    "description": "Maximum token budget for output response"
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional: Absolute path to the project directory containing graphify-out/graph.json"
                }
            },
            "required": ["question"]
        }
    },
    {
        "name": "graphify_node",
        "description": "Retrieve full details for a specific node/concept in the knowledge graph (file source, definition location, type, community, and degree).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Class name, function, symbol, or node label to look up"
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional: Absolute path to the project directory"
                }
            },
            "required": ["label"]
        }
    },
    {
        "name": "graphify_neighbors",
        "description": "Get all direct inbound and outbound relations for a concept (calls, imports, inherits, uses).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Node label to inspect neighbors for"
                },
                "relation_filter": {
                    "type": "string",
                    "description": "Optional: filter by relation type (e.g. 'call', 'import', 'inherit')"
                },
                "token_budget": {
                    "type": "integer",
                    "default": 2000,
                    "description": "Max output tokens"
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional: Project directory path"
                }
            },
            "required": ["label"]
        }
    },
    {
        "name": "graphify_community",
        "description": "List all members of a detected architectural community/subsystem by community ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "community_id": {
                    "type": "integer",
                    "description": "Community ID number (0-indexed)"
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional: Project directory path"
                }
            },
            "required": ["community_id"]
        }
    },
    {
        "name": "graphify_core_hubs",
        "description": "Return the most connected nodes in the knowledge graph—the core hubs, central abstractions, and key architectural elements everything flows through.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "top_n": {
                    "type": "integer",
                    "default": 10,
                    "description": "Number of top connected nodes to return"
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional: Project directory path"
                }
            }
        }
    },
    {
        "name": "graphify_shortest_path",
        "description": "Trace the shortest path of dependencies or relationships between two concepts in the knowledge graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Source concept label or keyword"
                },
                "target": {
                    "type": "string",
                    "description": "Target concept label or keyword"
                },
                "max_hops": {
                    "type": "integer",
                    "default": 8,
                    "description": "Maximum path length to consider"
                },
                "undirected": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to ignore edge direction"
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional: Project directory path"
                }
            },
            "required": ["source", "target"]
        }
    },
    {
        "name": "graphify_stats",
        "description": "Return summary statistics for the knowledge graph (total nodes, edges, detected communities, confidence breakdown).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_path": {
                    "type": "string",
                    "description": "Optional: Project directory path"
                }
            }
        }
    },
    {
        "name": "graphify_build",
        "description": "Index or update the knowledge graph for a given codebase directory using deterministic tree-sitter AST parsing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Target codebase directory path to index"
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "Force full re-index from scratch"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "graphify_blast_radius",
        "description": "Calculate all transitive downstream dependents, files, and tests that could break if a symbol is modified.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Target function, class, or symbol name"
                },
                "max_depth": {
                    "type": "integer",
                    "default": 3,
                    "description": "Downstream traversal depth (1-6)"
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional: Project directory path"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "graphify_call_flow",
        "description": "Trace execution call chains from an entrypoint and output a Mermaid sequence/flowchart.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Entrypoint function or class name"
                },
                "max_depth": {
                    "type": "integer",
                    "default": 3,
                    "description": "Call chain depth (1-6)"
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional: Project directory path"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "graphify_dead_code",
        "description": "Find orphan functions, unreferenced classes, and potential dead code with in-degree 0 in the project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_path": {
                    "type": "string",
                    "description": "Optional: Project directory path"
                }
            }
        }
    },
    {
        "name": "graphify_context_bundle",
        "description": "Extract a token-capped sub-graph context package tailored for LLM prompt injection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of core symbol names to include"
                },
                "token_budget": {
                    "type": "integer",
                    "default": 4000,
                    "description": "Maximum token budget for output bundle"
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional: Project directory path"
                }
            },
            "required": ["symbols"]
        }
    },
    {
        "name": "graphify_cypher",
        "description": "Execute an openCypher query directly against the embedded KùzuDB graph for advanced multi-hop queries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Cypher query string (e.g. 'MATCH (c:CodeNode) RETURN c.label LIMIT 10')"
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional: Project directory path"
                }
            },
            "required": ["query"]
        }
    }
]


def http_request(path, method="GET", body=None, timeout=30):
    url = f"{GRAPHIFY_SERVER_URL}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if GRAPHIFY_API_KEY:
        headers["Authorization"] = f"Bearer {GRAPHIFY_API_KEY}"
        headers["X-API-Key"] = GRAPHIFY_API_KEY
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_body)
            msg = err_json.get("detail", err_json.get("error", err_body))
        except Exception:
            msg = err_body or str(e)
        raise RuntimeError(f"HTTP {e.code}: {msg}")
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Cannot connect to Graphify server at {GRAPHIFY_SERVER_URL} ({e.reason}). "
            f"Ensure the Docker container is running ('docker compose up -d')."
        )


def handle_tool_call(tool_name, arguments):
    try:
        if tool_name == "graphify_query":
            res = http_request(
                "/api/query",
                method="POST",
                body={
                    "question": arguments.get("question"),
                    "mode": arguments.get("mode", "bfs"),
                    "depth": arguments.get("depth", 3),
                    "token_budget": arguments.get("token_budget", 2000),
                    "project_path": arguments.get("project_path"),
                },
                timeout=60,
            )
            return res.get("result", json.dumps(res, indent=2))

        elif tool_name == "graphify_node":
            params = {"label": arguments.get("label")}
            if arguments.get("project_path"):
                params["project_path"] = arguments.get("project_path")
            qs = urllib.parse.urlencode(params)
            res = http_request(f"/api/node?{qs}", method="GET")
            return (
                f"Node: {res.get('label')}\n"
                f"  ID: {res.get('id')}\n"
                f"  Source: {res.get('source_file')} {res.get('source_location')}\n"
                f"  Defined in: {res.get('definition_file', 'Same file')} {res.get('definition_location', '')}\n"
                f"  Type: {res.get('file_type')}\n"
                f"  Community: {res.get('community')}\n"
                f"  Degree: {res.get('degree')}"
            )

        elif tool_name == "graphify_neighbors":
            params = {"label": arguments.get("label")}
            if arguments.get("relation_filter"):
                params["relation_filter"] = arguments.get("relation_filter")
            if arguments.get("token_budget"):
                params["token_budget"] = arguments.get("token_budget")
            if arguments.get("project_path"):
                params["project_path"] = arguments.get("project_path")
            qs = urllib.parse.urlencode(params)
            res = http_request(f"/api/neighbors?{qs}", method="GET")

            lines = [f"Neighbors of {res.get('node')} ({res.get('node_id')}):"]
            for edge in res.get("outgoing", []):
                lines.append(f"  --> {edge['target']} [{edge['relation']}] ({edge.get('confidence', '')})")
            for edge in res.get("incoming", []):
                lines.append(f"  <-- {edge['source']} [{edge['relation']}] ({edge.get('confidence', '')})")
            return "\n".join(lines)

        elif tool_name == "graphify_community":
            params = {"community_id": arguments.get("community_id")}
            if arguments.get("project_path"):
                params["project_path"] = arguments.get("project_path")
            qs = urllib.parse.urlencode(params)
            res = http_request(f"/api/community?{qs}", method="GET")
            lines = [f"Community {res.get('community_id')} '{res.get('community_name', '')}' ({res.get('size', 0)} members):"]
            for m in res.get("members", [])[:100]:
                lines.append(f"  - {m['label']} [{m.get('source_file', '')}] ({m.get('type', '')})")
            return "\n".join(lines)

        elif tool_name == "graphify_core_hubs":
            params = {"top_n": arguments.get("top_n", 10)}
            if arguments.get("project_path"):
                params["project_path"] = arguments.get("project_path")
            qs = urllib.parse.urlencode(params)
            res = http_request(f"/api/core-hubs?{qs}", method="GET")
            lines = ["Core Hubs (Highest Degree Architectural Abstractions):"]
            for i, n in enumerate(res.get("core_hubs", []), 1):
                lines.append(f"  {i}. {n.get('label')} ({n.get('id', '')}) - {n.get('degree', 0)} edges")
            return "\n".join(lines)

        elif tool_name == "graphify_shortest_path":
            res = http_request(
                "/api/shortest-path",
                method="POST",
                body={
                    "source": arguments.get("source"),
                    "target": arguments.get("target"),
                    "max_hops": arguments.get("max_hops", 8),
                    "undirected": arguments.get("undirected", False),
                    "project_path": arguments.get("project_path"),
                }
            )
            return res.get("result", json.dumps(res, indent=2))

        elif tool_name == "graphify_stats":
            params = {}
            if arguments.get("project_path"):
                params["project_path"] = arguments.get("project_path")
            qs = urllib.parse.urlencode(params)
            endpoint = f"/api/stats?{qs}" if qs else "/api/stats"
            res = http_request(endpoint, method="GET")
            conf = res.get("confidence", {})
            return (
                f"Knowledge Graph Statistics:\n"
                f"  Graph Path: {res.get('graph_path')}\n"
                f"  Nodes: {res.get('nodes')}\n"
                f"  Edges: {res.get('edges')}\n"
                f"  Communities: {res.get('communities')}\n"
                f"  EXTRACTED: {conf.get('extracted_pct', 0)}%\n"
                f"  INFERRED: {conf.get('inferred_pct', 0)}%\n"
                f"  AMBIGUOUS: {conf.get('ambiguous_pct', 0)}%"
            )

        elif tool_name == "graphify_build":
            res = http_request(
                "/api/build",
                method="POST",
                body={
                    "path": arguments.get("path"),
                    "force": arguments.get("force", False),
                },
                timeout=300
            )
            return json.dumps(res, indent=2)

        elif tool_name == "graphify_blast_radius":
            params = {
                "symbol": arguments.get("symbol"),
                "max_depth": arguments.get("max_depth", 3),
            }
            if arguments.get("project_path"):
                params["project_path"] = arguments.get("project_path")
            qs = urllib.parse.urlencode(params)
            res = http_request(f"/api/blast-radius?{qs}", method="GET")
            lines = [
                f"Blast Radius Impact Analysis for '{res.get('target', {}).get('label')}':",
                f"  Risk Level: {res.get('risk_level')}",
                f"  Total Dependents Affected: {res.get('total_dependents_affected')}",
                f"  Affected Files: {res.get('affected_files_count')}",
            ]
            if res.get("affected_tests"):
                lines.append(f"  Affected Tests: {', '.join(res.get('affected_tests'))}")
            for hop, items in res.get("impact_by_depth", {}).items():
                lines.append(f"  {hop}: {len(items)} callers/dependents")
                for it in items[:5]:
                    lines.append(f"    - {it.get('label')} ({it.get('file')})")
            return "\n".join(lines)

        elif tool_name == "graphify_call_flow":
            params = {
                "symbol": arguments.get("symbol"),
                "max_depth": arguments.get("max_depth", 3),
            }
            if arguments.get("project_path"):
                params["project_path"] = arguments.get("project_path")
            qs = urllib.parse.urlencode(params)
            res = http_request(f"/api/callflow?{qs}", method="GET")
            return res.get("mermaid", json.dumps(res, indent=2))

        elif tool_name == "graphify_dead_code":
            params = {}
            if arguments.get("project_path"):
                params["project_path"] = arguments.get("project_path")
            qs = urllib.parse.urlencode(params)
            endpoint = f"/api/dead-code?{qs}" if qs else "/api/dead-code"
            res = http_request(endpoint, method="GET")
            orphans = res.get("orphans", [])
            lines = [f"Found {res.get('total_orphans_found', len(orphans))} unreferenced orphan symbols:"]
            for o in orphans[:25]:
                lines.append(f"  - {o.get('label')} ({o.get('file')})")
            return "\n".join(lines)

        elif tool_name == "graphify_context_bundle":
            res = http_request(
                "/api/context-bundle",
                method="POST",
                body={
                    "symbols": arguments.get("symbols", []),
                    "token_budget": arguments.get("token_budget", 4000),
                    "project_path": arguments.get("project_path"),
                }
            )
            return res.get("bundle", json.dumps(res, indent=2))

        elif tool_name == "graphify_cypher":
            res = http_request(
                "/api/cypher",
                method="POST",
                body={
                    "query": arguments.get("query"),
                    "project_path": arguments.get("project_path"),
                }
            )
            rows = res.get("rows", [])
            if not rows:
                return f"Cypher query executed successfully. (0 rows returned)"
            return json.dumps(rows, indent=2)

        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    except Exception as e:
        return f"Error executing {tool_name}: {e}"


def send_response(response):
    payload = json.dumps(response)
    sys.stdout.write(payload + "\n")
    sys.stdout.flush()


def run_stdio_server():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "graphify-local-mcp",
                        "version": "1.0.0"
                    }
                }
            })
        elif method == "notifications/initialized":
            pass
        elif method == "ping":
            send_response({"jsonrpc": "2.0", "id": req_id, "result": {}})
        elif method == "tools/list":
            send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS}
            })
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            text_result = handle_tool_call(tool_name, arguments)
            send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": str(text_result)}]
                }
            })
        else:
            if req_id is not None:
                send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                })


if __name__ == "__main__":
    run_stdio_server()
