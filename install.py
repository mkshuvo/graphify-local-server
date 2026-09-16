#!/usr/bin/env python3
"""
Universal Cross-Platform Installer Engine for Graphify Local Server 2.0
Supports Windows, macOS, and Linux.

1. Automatically configures/updates virtual environment (.venv).
2. Installs requirements (KùzuDB, Graphify, FastAPI, NetworkX, Uvicorn).
3. Auto-discovers and configures AI assistants (Google Antigravity, Claude Desktop, Cursor, Windsurf).
4. Generates native launcher scripts (start.bat, start.ps1, start.sh).
5. Pre-indexes starter knowledge graph so the Web Studio is immediately interactive.
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
from typing import Optional, Tuple
from pathlib import Path

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def log(msg: str):
    print(f"[*] {msg}")


def log_ok(msg: str):
    print(f"[OK] {msg}")


def log_warn(msg: str):
    print(f"[!] {msg}")


def get_python_and_scripts() -> tuple[Path, Path]:
    """Returns (python_bin, scripts_dir) for the project venv."""
    venv_dir = ROOT / ".venv"
    if IS_WIN:
        scripts = venv_dir / "Scripts"
        python_bin = scripts / "python.exe"
    else:
        scripts = venv_dir / "bin"
        python_bin = scripts / "python"
    return python_bin, scripts


def ensure_environment():
    """Sets up virtual environment and installs dependencies."""
    venv_dir = ROOT / ".venv"
    python_bin, _ = get_python_and_scripts()

    has_uv = shutil.which("uv") is not None

    if not python_bin.exists():
        log(f"Creating virtual environment in {venv_dir}...")
        if has_uv:
            subprocess.run(["uv", "venv", str(venv_dir)], check=True, cwd=str(ROOT))
        else:
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, cwd=str(ROOT))
        log_ok("Virtual environment created.")

    log("Installing and verifying dependencies (requirements.txt)...")
    req_file = ROOT / "requirements.txt"
    if has_uv:
        subprocess.run(["uv", "pip", "install", "-r", str(req_file)], check=True, cwd=str(ROOT))
    else:
        subprocess.run([str(python_bin), "-m", "pip", "install", "--upgrade", "pip"], check=True)
        subprocess.run([str(python_bin), "-m", "pip", "install", "-r", str(req_file)], check=True, cwd=str(ROOT))

    log_ok("All core dependencies installed successfully.")


def generate_launchers():
    """Generates 1-click startup scripts for Windows, macOS, and Linux."""
    # 1. Windows Batch (start.bat)
    bat_content = (
        "@echo off\r\n"
        "title Graphify Local Server 2.0\r\n"
        "cd /d \"%~dp0\"\r\n"
        "if exist \".venv\\Scripts\\python.exe\" (\r\n"
        "    \".venv\\Scripts\\python.exe\" run_server.py %*\r\n"
        ") else (\r\n"
        "    python run_server.py %*\r\n"
        ")\r\n"
        "pause\r\n"
    )
    (ROOT / "start.bat").write_text(bat_content, encoding="utf-8")

    # 2. Windows PowerShell (start.ps1)
    ps1_content = (
        "$PSScriptRoot = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition\r\n"
        "Set-Location $PSScriptRoot\r\n"
        "$py = Join-Path $PSScriptRoot '.venv\\Scripts\\python.exe'\r\n"
        "if (Test-Path $py) {\r\n"
        "    & $py run_server.py @args\r\n"
        "} else {\r\n"
        "    python run_server.py @args\r\n"
        "}\r\n"
    )
    (ROOT / "start.ps1").write_text(ps1_content, encoding="utf-8")

    # 3. macOS / Linux Bash (start.sh)
    sh_content = (
        "#!/usr/bin/env bash\n"
        "DIR=\"$( cd \"$( dirname \"${BASH_SOURCE[0]}\" )\" >/dev/null 2>&1 && pwd )\"\n"
        "cd \"$DIR\"\n"
        "if [ -f \".venv/bin/python\" ]; then\n"
        "    exec .venv/bin/python run_server.py \"$@\"\n"
        "else\n"
        "    exec python3 run_server.py \"$@\"\n"
        "fi\n"
    )
    sh_file = ROOT / "start.sh"
    sh_file.write_text(sh_content, encoding="utf-8")
    try:
        sh_file.chmod(0o755)
    except Exception:
        pass

    log_ok("Generated native launcher scripts: start.bat, start.ps1, start.sh")


def update_json_config(path: Path, server_config: dict) -> bool:
    """Safely merges 'graphify' into an MCP JSON configuration file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}
        if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
            data["mcpServers"] = {}

        data["mcpServers"]["graphify"] = server_config
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        log_warn(f"Could not write to {path}: {e}")
        return False


def configure_assistants():
    """Detects and registers graphify MCP in Antigravity, Claude, Cursor, and Windsurf."""
    python_bin, _ = get_python_and_scripts()
    mcp_script = ROOT / "mcp" / "graphify_mcp.py"

    py_exec = str(python_bin) if python_bin.exists() else sys.executable

    server_entry = {
        "command": py_exec,
        "args": [str(mcp_script)],
        "env": {
            "GRAPHIFY_SERVER_URL": "http://localhost:28848"
        }
    }

    configured = []

    # 1. Google Antigravity (~/.gemini/config/mcp_config.json)
    agy_config = Path.home() / ".gemini" / "config" / "mcp_config.json"
    if update_json_config(agy_config, server_entry):
        configured.append(f"Google Antigravity ({agy_config})")

    # 2. Claude Desktop
    if IS_WIN:
        appdata = os.getenv("APPDATA", "")
        claude_config = Path(appdata) / "Claude" / "claude_desktop_config.json" if appdata else None
    elif IS_MAC:
        claude_config = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        claude_config = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"

    if claude_config:
        try:
            if claude_config.parent.exists():
                if update_json_config(claude_config, server_entry):
                    configured.append(f"Claude Desktop ({claude_config})")
        except Exception:
            pass

    # 3. Cursor (~/.cursor/mcp.json)
    cursor_config = Path.home() / ".cursor" / "mcp.json"
    try:
        if cursor_config.parent.exists():
            if update_json_config(cursor_config, server_entry):
                configured.append(f"Cursor ({cursor_config})")
    except Exception:
        pass

    # 4. Windsurf (~/.codeium/windsurf/mcp_config.json)
    windsurf_config = Path.home() / ".codeium" / "windsurf" / "mcp_config.json"
    try:
        if windsurf_config.parent.exists():
            if update_json_config(windsurf_config, server_entry):
                configured.append(f"Windsurf ({windsurf_config})")
    except Exception:
        pass

    if configured:
        log_ok("Auto-configured MCP in detected AI assistants:")
        for c in configured:
            print(f"    * {c}")
    else:
        log_ok("Assistant configs written to default locations.")


def ensure_starter_graph(target_path: Optional[str] = None):
    """Builds a starter or custom knowledge graph so the server has immediate data."""
    python_bin, scripts_dir = get_python_and_scripts()
    py_exec = str(python_bin) if python_bin.exists() else sys.executable

    graph_target = target_path or str(ROOT / "server")
    out_dir = ROOT / "data" / "default"
    out_dir.mkdir(parents=True, exist_ok=True)

    target_graph = out_dir / "graphify-out" / "graph.json"
    if target_graph.exists() and not target_path:
        log_ok(f"Starter knowledge graph already available at {target_graph}")
        return

    log(f"Extracting knowledge graph for: {graph_target}...")
    try:
        # 1. AST extraction
        res = subprocess.run(
            [py_exec, "-m", "graphify.cli", "extract", graph_target, "--code-only", "--output", str(out_dir)],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        if res.returncode == 0 and target_graph.exists():
            log_ok(f"Knowledge graph extracted ({target_graph})")
            # 2. HTML visualizer
            subprocess.run(
                [py_exec, "-m", "graphify.cli", "export", "html", "--graph", str(target_graph)],
                capture_output=True,
                cwd=str(ROOT),
            )
            # 3. Tree HTML
            tree_html = out_dir / "graphify-out" / "GRAPH_TREE.html"
            subprocess.run(
                [py_exec, "-m", "graphify.cli", "tree", "--graph", str(target_graph), "--output", str(tree_html)],
                capture_output=True,
                cwd=str(ROOT),
            )
            # 4. Callflow HTML
            callflow_html = out_dir / "graphify-out" / "GRAPH_CALLFLOW.html"
            subprocess.run(
                [py_exec, "-m", "graphify.cli", "export", "callflow-html", str(out_dir / "graphify-out"), "--output", str(callflow_html)],
                capture_output=True,
                cwd=str(ROOT),
            )
            log_ok("Generated visualizers: 2D Force Graph, D3 Tree, and Mermaid Call-Flow.")
        else:
            log_warn(f"Starter extraction completed with notice: {res.stderr[:200] if res.stderr else 'OK'}")
    except Exception as e:
        log_warn(f"Could not build starter graph: {e}")


def main():
    parser = argparse.ArgumentParser(description="Graphify Local Server 2.0 Installer")
    parser.add_argument("--codebase", "-c", type=str, help="Codebase directory path to index on install")
    parser.add_argument("--skip-graph", action="store_true", help="Skip starter graph indexing")
    parser.add_argument("--start", "-s", action="store_true", help="Start the server immediately after installation")
    parser.add_argument("--port", "-p", type=int, default=28848, help="Server port (default: 28848)")
    args = parser.parse_args()

    print("=" * 68)
    print("       Graphify 2.0 — Automatic Cross-Platform Setup")
    print("=" * 68)
    platform_name = "Windows" if IS_WIN else ("macOS" if IS_MAC else "Linux")
    print(f"  Platform:    {platform_name} ({sys.platform})")
    print(f"  Repository:  {ROOT}")
    print(f"  Python Base: {sys.executable}\n")

    ensure_environment()
    generate_launchers()
    configure_assistants()

    if not args.skip_graph:
        ensure_starter_graph(args.codebase)

    print("\n" + "=" * 68)
    print("  [OK] GRAPHIFY 2.0 SETUP COMPLETE — ZERO CONFIGURATION NEEDED!")
    print("=" * 68)
    print("  To launch the server at any time:")
    if IS_WIN:
        print("    Powershell:  .\\start.ps1")
        print("    CMD/Batch:   .\\start.bat")
    else:
        print("    Terminal:    ./start.sh")
    print(f"  Web Studio:    http://localhost:{args.port}")
    print(f"  MCP Server:    {ROOT / 'mcp' / 'graphify_mcp.py'}")
    print("=" * 68 + "\n")

    if args.start:
        python_bin, _ = get_python_and_scripts()
        py_exec = str(python_bin) if python_bin.exists() else sys.executable
        log(f"Starting server on port {args.port}...")
        os.environ["PORT"] = str(args.port)
        subprocess.run([py_exec, "run_server.py"], cwd=str(ROOT))


if __name__ == "__main__":
    main()
