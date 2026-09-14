import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from .graphify_service import GraphifyService
from .routes import setup_routes

DATA_DIR = os.getenv("GRAPHIFY_DATA_DIR", "/app/data")
STATIC_DIR = os.getenv("GRAPHIFY_STATIC_DIR", "/app/static")
PORT = int(os.getenv("PORT", "28848"))

app = FastAPI(
    title="Graphify Local Server & MCP Engine",
    version="1.0.0",
    description="100% Local Self-Hosted Knowledge Graph Server for AI Coding Assistants"
)

# Enable CORS for local cross-origin access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "port": PORT,
        "graphs_count": len(graphs),
        "default_graph": service.default_graph_key,
        "data_dir": DATA_DIR,
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
