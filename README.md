# graphify-local-server (Graphify 2.0)

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Docker](https://img.shields.io/badge/Docker-Tested%20%26%20Isolated-blue.svg)](https://www.docker.com/)
[![MCP](https://img.shields.io/badge/Model%20Context%20Protocol-Compatible-purple.svg)](https://modelcontextprotocol.io/)
[![KùzuDB](https://img.shields.io/badge/KùzuDB-Embedded%20Engine-cyan.svg)](https://kuzudb.com/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-yellow.svg)](https://www.python.org/)

A self-hosted, 100% local, zero-external-API **Graphify Knowledge Graph Server & Agentic Engine** with an interactive Web Studio and Model Context Protocol (MCP) tool provider for **Google Antigravity**, **Claude Code / Claude Desktop**, **Cursor**, **Windsurf**, **Codex**, and other autonomous AI coding agents.

Turn any codebase into a queryable knowledge graph using deterministic tree-sitter AST parsing across 36+ programming languages—no vector store, no external LLM costs for code AST, fully private, with low RAM footprint via embedded **KùzuDB**.

---

## ⚡ 1-Click Automatic Setup (Zero Manual Configuration)

Run the native automated installer for your operating system:

### 🪟 Windows (PowerShell)
```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```
> **Want to install and start the server immediately?**
> ```powershell
> .\install.ps1 -Start
> ```

### 🍎 macOS & 🐧 Linux (Bash)
```bash
bash install.sh
```
> **Want to install and start the server immediately?**
> ```bash
> ./install.sh --start
> ```

### 🐍 Or Universal Python CLI:
```bash
python install.py --start
```

### What the Automated Setup Does For You:
1. **Zero Prerequisites**: Automatically checks for Python 3.10+. If missing, offers silent installation via `winget` (Windows), `brew` (macOS), or `apt`/`dnf`/`pacman` (Linux).
2. **Virtual Environment**: Configures an isolated `.venv` using `uv` (if present) or `venv`.
3. **Installs Requirements**: Installs Graphify, KùzuDB, FastAPI, NetworkX, Uvicorn, and Starlette.
4. **Auto-Discovers AI Assistants**: Automatically registers the MCP server in:
   - **Google Antigravity**: `~/.gemini/config/mcp_config.json`
   - **Claude Desktop**: Auto-detects macOS, Windows `%APPDATA%`, and Linux config paths
   - **Cursor**: `~/.cursor/mcp.json`
   - **Windsurf**: `~/.codeium/windsurf/mcp_config.json`
5. **Populates Starter Graph**: Extracts and indexes the server itself (`90 nodes, 152 edges`), generating the interactive 2D Force Graph, Collapsible Architecture Tree, and Mermaid Call-Flow out-of-the-box.
6. **Emits Native Launchers**: Generates `start.bat`, `start.ps1`, and `start.sh`.

---

## 🚀 Starting the Server

### Option A: Native Zero-Docker Mode (Recommended)
* **Windows**: Double-click `start.bat` or run `.\start.ps1`
* **macOS / Linux**: Run `./start.sh`

### Option B: Isolated Docker Container

1. **Configure your workspace mount**:
   Copy `.env.example` to `.env` and set `HOST_WORKSPACE_DIR` to your projects directory so Docker can index external codebases:
   ```bash
   cp .env.example .env
   # Edit .env:
   # HOST_WORKSPACE_DIR=D:/projects      (Windows)
   # HOST_WORKSPACE_DIR=/path/to/projects (macOS / Linux)
   ```

2. **Start the Docker container**:
   ```bash
   docker compose up -d --build
   ```

3. **Auto-configure MCP Assistants for Docker**:
   Run the setup with the `--docker` flag to register the Docker-backed MCP provider in your AI coding tools:
   * **Windows**: `.\install.ps1 -Docker`
   * **macOS / Linux**: `./install.sh --docker`
   * **Universal**: `python install.py --docker`

   *(Or manually configure your assistant MCP json to use Docker directly without needing local Python:)*
   ```json
   {
     "mcpServers": {
       "graphify": {
         "command": "docker",
         "args": [
           "exec",
           "-i",
           "graphify-local-server",
           "python",
           "/app/mcp/graphify_mcp.py"
         ],
         "env": {
           "GRAPHIFY_SERVER_URL": "http://localhost:28848"
         }
       }
     }
   }
   ```

Access the Web Management Dashboard & Studio at [**http://localhost:28848**](http://localhost:28848).
* 🕸️ **2D Interactive Force Visualizer**: `http://localhost:28848/visualizer`
* 🌲 **D3 Collapsible Architecture Tree**: `http://localhost:28848/tree`
* 🔄 **Mermaid Call-Flow Sequences**: `http://localhost:28848/callflow`

---

## 🛡️ Dynamic Multi-Tier Security Architecture

Graphify 2.0 dynamically adapts its security model based on where it is deployed:

| Feature | Local Dev Mode (`127.0.0.1`) | Cloud / Hosted Mode (`0.0.0.0`) |
| :--- | :--- | :--- |
| **Activation** | Default when running locally | Set `GRAPHIFY_ENV=production` or `GRAPHIFY_API_KEY=...` |
| **Authentication** | Disabled (Zero friction for local dev & MCP) | **Enforced** (Bearer Token & `X-API-Key` required) |
| **CORS Policy** | Safe regex matching `localhost` and `127.0.0.1` | Strict configured allowlist (`ALLOWED_ORIGINS`) |
| **Path Exposure** | Full host filesystem paths shown | **Redacted** (`[REDACTED_IN_CLOUD]`) |
| **Security Headers** | Standard | HSTS, nosniff, frame protection, anti-MIME sniffing |

---

## 🛠️ MCP Tools Reference (For AI Coding Agents)

| Tool | Description |
| :--- | :--- |
| `graphify_blast_radius` | Calculate all transitive downstream callers, dependents, and tests that could break if a symbol is modified. |
| `graphify_call_flow` | Trace execution pipelines from an entrypoint and emit Mermaid sequence/flow diagrams. |
| `graphify_context_bundle`| Extract a token-capped subgraph + code context package ready for LLM prompt injection. |
| `graphify_dead_code` | Scan for orphan functions, unreferenced classes, and dead code with in-degree 0. |
| `graphify_cypher` | Execute openCypher queries directly over the embedded KùzuDB graph engine. |
| `graphify_query` | Natural language or keyword BFS/DFS search over knowledge graphs. |
| `graphify_node` | Retrieve full details of a symbol (file location, definition line, community, degree). |
| `graphify_neighbors` | Direct inbound and outbound relations for a concept (calls, imports, inherits, uses). |
| `graphify_community` | List all member classes/files of an architectural community or subsystem. |
| `graphify_core_hubs` | Identify the highest-degree architectural hubs that code flows through. |
| `graphify_shortest_path` | Trace the shortest dependency path between any two concepts or classes. |
| `graphify_stats` | Return summary statistics (node count, edge count, confidence breakdown). |
| `graphify_build` | Index or update a codebase directory using deterministic tree-sitter AST parsing. |

---

## 🧪 Testing

Run tests locally or in an isolated Docker container without affecting your host system:
```bash
# In Docker (isolated, zero host footprint):
docker run --rm graphify-local-server:test python -m pytest tests/test_server.py -v

# Locally:
pytest tests/test_server.py -v
```

---

## 📄 License

This project is open-source and licensed under the [MIT License](LICENSE).
