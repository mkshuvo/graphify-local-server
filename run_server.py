#!/usr/bin/env python3
"""
Universal Cross-Platform Server Runner for Graphify Local Server 2.0
Works natively on Windows, macOS, Linux, and WSL without Docker required.
"""

import os
import sys
import argparse
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main():
    from server.security import security_config

    is_container = os.path.exists("/.dockerenv") or os.getenv("IS_DOCKER") == "1"
    default_host = "0.0.0.0" if (is_container or security_config.is_cloud()) else "127.0.0.1"

    parser = argparse.ArgumentParser(description="Run Graphify Knowledge Graph Server")
    parser.add_argument("--host", default=default_host, help=f"Host interface (default: {default_host})")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "28848")), help="Port number (default: 28848)")
    parser.add_argument("--reload", action="store_true", help="Enable live code reload")
    parser.add_argument("--data-dir", default=None, help="Custom data directory")
    args = parser.parse_args()

    # Set environment variables
    os.environ["PORT"] = str(args.port)
    if args.data_dir:
        os.environ["GRAPHIFY_DATA_DIR"] = str(Path(args.data_dir).resolve())
    else:
        default_data = PROJECT_ROOT / "data"
        default_data.mkdir(parents=True, exist_ok=True)
        os.environ["GRAPHIFY_DATA_DIR"] = str(default_data)

    static_dir = PROJECT_ROOT / "static"
    os.environ["GRAPHIFY_STATIC_DIR"] = str(static_dir)

    mode_label = "LOCAL (Zero-friction, localhost-protected)" if security_config.is_local() else "CLOUD (Strict CORS, Bearer Auth Enforced)"

    print("=" * 65)
    print("  Graphify Local Server 2.0 — Knowledge Graph & MCP Engine")
    print("=" * 65)
    print(f"  * Status:         Starting runner...")
    print(f"  * Platform:       {sys.platform} ({'Windows' if sys.platform == 'win32' else 'macOS' if sys.platform == 'darwin' else 'Linux'})")
    print(f"  * Python:         {sys.version.split()[0]} ({sys.executable})")
    print(f"  * Security Mode:  {mode_label}")
    print(f"  * Host Binding:   {args.host}:{args.port}")
    print(f"  * Dashboard UI:   http://localhost:{args.port}")
    print(f"  * API Base:       http://localhost:{args.port}/api")
    print(f"  * MCP Stdio Path: {PROJECT_ROOT / 'mcp' / 'graphify_mcp.py'}")
    print(f"  * Data Dir:       {os.environ['GRAPHIFY_DATA_DIR']}")
    print("=" * 65)
    print("  Press Ctrl+C to stop the server.\n")

    try:
        import uvicorn
    except ImportError:
        print("[ERROR] uvicorn is not installed in the current environment.")
        print("Please run: pip install -r requirements.txt")
        sys.exit(1)

    uvicorn.run(
        "server.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
