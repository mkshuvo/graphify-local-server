from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from .graphify_service import GraphifyService

router = APIRouter(prefix="/api", tags=["Graphify"])


class QueryRequest(BaseModel):
    question: str = Field(..., description="Natural language question or search query")
    mode: str = Field("bfs", description="Traversal mode: 'bfs' or 'dfs'")
    depth: int = Field(3, ge=1, le=6, description="Traversal depth (1-6)")
    token_budget: int = Field(2000, ge=100, le=10000, description="Max token budget")
    context_filter: Optional[List[str]] = Field(None, description="Filter edge context (e.g. ['call', 'import'])")
    project_path: Optional[str] = Field(None, description="Target project or graph path")


class ShortestPathRequest(BaseModel):
    source: str = Field(..., description="Source concept name or label")
    target: str = Field(..., description="Target concept name or label")
    max_hops: int = Field(8, ge=1, le=20, description="Maximum hops to consider")
    undirected: bool = Field(False, description="Ignore direction")
    project_path: Optional[str] = Field(None, description="Target project or graph path")


class BuildRequest(BaseModel):
    path: str = Field(..., description="Codebase or project directory path to index")
    force: bool = Field(False, description="Force re-indexing even if graph exists")


class CypherRequest(BaseModel):
    query: str = Field(..., description="OpenCypher query to execute")
    project_path: Optional[str] = Field(None, description="Target project or graph path")


class ContextBundleRequest(BaseModel):
    symbols: List[str] = Field(..., description="List of symbols or concepts to package")
    token_budget: int = Field(4000, ge=500, le=32000, description="Max token budget")
    project_path: Optional[str] = Field(None, description="Target project or graph path")


def setup_routes(service: GraphifyService) -> APIRouter:
    @router.get("/graphs")
    def list_graphs():
        return {"graphs": service.list_graphs()}

    @router.post("/query")
    def query_graph(req: QueryRequest):
        try:
            return service.query(
                question=req.question,
                mode=req.mode,
                depth=req.depth,
                token_budget=req.token_budget,
                context_filter=req.context_filter,
                project_path=req.project_path,
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/node")
    def get_node(label: str = Query(..., description="Node label or ID"), project_path: Optional[str] = None):
        try:
            res = service.get_node(label, project_path)
            if "error" in res:
                raise HTTPException(status_code=404, detail=res["error"])
            return res
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/neighbors")
    def get_neighbors(
        label: str = Query(..., description="Node label"),
        relation_filter: Optional[str] = Query(None, description="Filter relations"),
        token_budget: int = Query(2000, description="Token budget"),
        project_path: Optional[str] = None,
    ):
        try:
            res = service.get_neighbors(label, relation_filter, token_budget, project_path)
            if "error" in res:
                raise HTTPException(status_code=404, detail=res["error"])
            return res
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/community")
    def get_community(community_id: int = Query(..., description="Community ID"), project_path: Optional[str] = None):
        try:
            res = service.get_community(community_id, project_path)
            if "error" in res:
                raise HTTPException(status_code=404, detail=res["error"])
            return res
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/core-hubs")
    def get_core_hubs(
        top_n: int = Query(10, ge=1, le=100),
        exclude_hubs_percentile: Optional[float] = Query(None),
        project_path: Optional[str] = None,
    ):
        try:
            return service.core_hubs(top_n, exclude_hubs_percentile, project_path)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/shortest-path")
    def shortest_path(req: ShortestPathRequest):
        try:
            res = service.shortest_path(
                source=req.source,
                target=req.target,
                max_hops=req.max_hops,
                undirected=req.undirected,
                project_path=req.project_path,
            )
            if "error" in res:
                raise HTTPException(status_code=404, detail=res["error"])
            return res
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/blast-radius")
    def blast_radius(
        symbol: str = Query(..., description="Target symbol/function name"),
        max_depth: int = Query(3, ge=1, le=6, description="Downstream traversal depth"),
        project_path: Optional[str] = None,
    ):
        try:
            res = service.blast_radius(symbol=symbol, max_depth=max_depth, project_path=project_path)
            if "error" in res:
                raise HTTPException(status_code=404, detail=res["error"])
            return res
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/callflow")
    def call_flow(
        symbol: str = Query(..., description="Entrypoint symbol/function name"),
        max_depth: int = Query(3, ge=1, le=6, description="Call chain depth"),
        project_path: Optional[str] = None,
    ):
        try:
            res = service.call_flow(symbol=symbol, max_depth=max_depth, project_path=project_path)
            if "error" in res:
                raise HTTPException(status_code=404, detail=res["error"])
            return res
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/dead-code")
    def dead_code(project_path: Optional[str] = None):
        try:
            return service.dead_code(project_path=project_path)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/context-bundle")
    def context_bundle(req: ContextBundleRequest):
        try:
            return service.context_bundle(
                symbols=req.symbols,
                token_budget=req.token_budget,
                project_path=req.project_path,
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/cypher")
    def execute_cypher(req: CypherRequest):
        try:
            res = service.execute_cypher(query=req.query, project_path=req.project_path)
            if "error" in res and "not found" in res["error"].lower():
                raise HTTPException(status_code=404, detail=res["error"])
            return res
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/stats")
    def get_stats(project_path: Optional[str] = None):
        try:
            return service.stats(project_path)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/build")
    def build_graph(req: BuildRequest):
        try:
            res = service.build_graph(req.path, req.force)
            return res
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router
