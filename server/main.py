import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from .graphify_service import GraphifyService
from .routes import setup_routes
from .security import security_config, DynamicSecurityMiddleware

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
IS_CONTAINER = os.path.exists("/.dockerenv") or os.getenv("IS_DOCKER") == "1"

DEFAULT_DATA_DIR = "/app/data" if IS_CONTAINER else str(BASE_DIR / "data")
DEFAULT_STATIC_DIR = "/app/static" if IS_CONTAINER else str(BASE_DIR / "static")

DATA_DIR = os.getenv("GRAPHIFY_DATA_DIR", DEFAULT_DATA_DIR)
STATIC_DIR = os.getenv("GRAPHIFY_STATIC_DIR", DEFAULT_STATIC_DIR)
PORT = int(os.getenv("PORT", "28848"))

app = FastAPI(
    title="Graphify Local Server & MCP Engine",
    version="2.0.0",
    description="100% Local Self-Hosted Knowledge Graph Server for AI Coding Assistants"
)

# Configure CORS dynamically based on security mode (local vs cloud)
cors_kwargs = {
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if security_config.allow_origin_regex:
    cors_kwargs["allow_origin_regex"] = security_config.allow_origin_regex
else:
    cors_kwargs["allow_origins"] = security_config.allowed_origins

app.add_middleware(CORSMiddleware, **cors_kwargs)
app.add_middleware(DynamicSecurityMiddleware)

# Initialize Core Graphify Service
service = GraphifyService(data_dir=DATA_DIR)

# Mount API routes
api_router = setup_routes(service)
app.include_router(api_router)


@app.get("/health")
def health_check():
    graphs = service.list_graphs()
    return {
        "status": "ok",
        "service": "graphify-local-server",
        "version": "2.0.0",
        "security_mode": security_config.mode.value,
        "auth_enforced": bool(security_config.is_cloud() and security_config.api_key),
        "port": PORT,
        "graphs_count": len(graphs),
        "default_graph": service.default_graph_key,
        "data_dir": DATA_DIR if security_config.is_local() else "[REDACTED_IN_CLOUD]",
        "has_kuzu": service.has_kuzu,
    }


@app.get("/visualizer")
def serve_visualizer(project: Optional[str] = Query(None, description="Project name or graph path")):
    html_path = service.get_visualizer_html_path(project)
    if html_path and html_path.exists():
        return FileResponse(str(html_path), media_type="text/html")
    raise HTTPException(
        status_code=404,
        detail=f"Visualizer graph.html not found for '{project or 'default'}'. Build a graph first."
    )


@app.get("/tree")
def serve_tree(project: Optional[str] = Query(None, description="Project name or graph path")):
    html_path = service.get_tree_html_path(project)
    if html_path and html_path.exists():
        return FileResponse(str(html_path), media_type="text/html")
    raise HTTPException(
        status_code=404,
        detail=f"Architecture Tree HTML not found for '{project or 'default'}'. Build a graph first."
    )


@app.get("/callflow")
def serve_callflow(project: Optional[str] = Query(None, description="Project name or graph path")):
    html_path = service.get_callflow_html_path(project)
    if html_path and html_path.exists():
        return FileResponse(str(html_path), media_type="text/html")
    raise HTTPException(
        status_code=404,
        detail=f"Call-flow HTML not found for '{project or 'default'}'. Export callflow first."
    )


# Mount Web Dashboard static assets
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def serve_dashboard():
        index_file = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"message": "Graphify Server running. Static files not found."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host="0.0.0.0", port=PORT, reload=False)
