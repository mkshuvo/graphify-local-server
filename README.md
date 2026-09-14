# graphify-local-server

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Docker](https://img.shields.io/badge/Docker-Enabled-blue.svg)](https://www.docker.com/)
[![MCP](https://img.shields.io/badge/Model%20Context%20Protocol-Compatible-purple.svg)](https://modelcontextprotocol.io/)
[![Python](https://img.shields.io/badge/Python-3.12-yellow.svg)](https://www.python.org/)

A self-hosted, 100% local, zero-external-API **Graphify Knowledge Graph Server** and **Web Management Dashboard** integrated as a Model Context Protocol (MCP) tool provider for **Google Antigravity**, **Claude Code / Claude Desktop**, **Cursor**, **Windsurf**, **Codex**, and other AI coding assistants.

Turn any codebase into a queryable knowledge graph using deterministic tree-sitter AST parsing across 36+ programming languages—no vector store, no external LLM costs for code AST, fully local and private.

---

## 🌟 Key Features

- 🕸️ **Deterministic Code Graphs**: AST-based parsing of classes, functions, calls, imports, and inheritance across 36+ languages.
- 🐳 **Dockerized & Isolated**: Runs in a lightweight container on custom unique port **`28848`** (prevents local port collisions).
- 🌐 **Modern Web Dashboard**: Clean Dark/Light UI at `http://localhost:28848` for querying, tracing shortest paths, and indexing codebases.
- 🤖 **Universal Multi-Agent MCP**: Zero-dependency Python standard library MCP stdio bridge (`mcp/graphify_mcp.py`) compatible with any MCP client.
- 📂 **Multi-Project Support**: Pass `project_path` to query or index different repositories on demand.
- 💾 **Persistent & Private**: Graph artifacts (`graph.json`, `graph.html`, `GRAPH_REPORT.md`) are stored safely in `./data` and host workspaces.

---

## 🚀 Quick Start

### 1. Launch the Docker Container

```bash
cd /Users/mohsin/.local-mcp/graphify-local-server

# Build and start container in the background
docker compose up -d --build
```

Access the Web Management Dashboard at [**http://localhost:28848**](http://localhost:28848).

### 2. Configure Your AI Assistants

#### A. Google Antigravity (`~/.gemini/config/mcp_config.json`)

```json
{
  "mcpServers": {
    "graphify": {
      "command": "/opt/homebrew/bin/python3",
      "args": [
        "/Users/mohsin/.local-mcp/graphify-local-server/mcp/graphify_mcp.py"
      ],
      "env": {
        "GRAPHIFY_SERVER_URL": "http://localhost:28848"
      }
    }
  }
}
```

#### B. Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "graphify": {
      "command": "python3",
      "args": [
        "/Users/mohsin/.local-mcp/graphify-local-server/mcp/graphify_mcp.py"
      ],
      "env": {
        "GRAPHIFY_SERVER_URL": "http://localhost:28848"
      }
    }
  }
}
```

#### C. Cursor (`.cursor/mcp.json` or Settings > Features > MCP)

```json
{
  "mcpServers": {
    "graphify": {
      "command": "python3",
      "args": [
        "/Users/mohsin/.local-mcp/graphify-local-server/mcp/graphify_mcp.py"
      ],
      "env": {
        "GRAPHIFY_SERVER_URL": "http://localhost:28848"
      }
    }
  }
}
```

#### D. Windsurf (`~/.codeium/windsurf/mcp_config.json`)

```json
{
  "mcpServers": {
    "graphify": {
      "command": "python3",
      "args": [
        "/Users/mohsin/.local-mcp/graphify-local-server/mcp/graphify_mcp.py"
      ],
      "env": {
        "GRAPHIFY_SERVER_URL": "http://localhost:28848"
      }
    }
  }
}
```

#### E. Claude Code CLI

```bash
claude mcp add graphify python3 /Users/mohsin/.local-mcp/graphify-local-server/mcp/graphify_mcp.py
```

---

## 🛠️ MCP Tools Reference

| Tool | Description |
| :--- | :--- |
| `graphify_query` | Natural language or keyword BFS/DFS search over knowledge graphs. |
| `graphify_node` | Retrieve full details of a symbol (file location, definition line, community, degree). |
| `graphify_neighbors` | Direct inbound and outbound relations for a concept (calls, imports, inherits, uses). |
| `graphify_community` | List all member classes/files of an architectural community or subsystem. |
| `graphify_core_hubs` | Identify the highest-degree architectural hubs that code flows through. |
| `graphify_shortest_path` | Trace the shortest dependency path between any two concepts or classes. |
| `graphify_stats` | Return summary statistics (node count, edge count, confidence breakdown). |
| `graphify_build` | Index or update a codebase directory using deterministic tree-sitter AST parsing. |

---

## 📁 Repository Structure

```
graphify-local-server/
├── Dockerfile                  # Container definition with Python 3.12 and tree-sitter
├── docker-compose.yml          # Compose file (Port 28848 + persistent ./data volume)
├── requirements.txt            # graphifyy[mcp], fastapi, uvicorn, networkx
├── server/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application and health checks
│   ├── routes.py               # REST API endpoints
│   └── graphify_service.py     # Graphify core engine and NetworkX cache
├── static/
│   └── index.html              # Modern Web Management Dashboard
├── mcp/
│   └── graphify_mcp.py         # Zero-dependency Python stdlib MCP stdio bridge
└── data/                       # Persistent knowledge graph storage
```

---

## 📄 License

This project is open-source and licensed under the [MIT License](LICENSE).
