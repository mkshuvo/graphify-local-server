import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import networkx as nx

logger = logging.getLogger("graphify_service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class GraphifyService:
    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.graphs: Dict[str, Tuple[nx.Graph, Dict[int, List[str]]]] = {}
        self.default_graph_key: Optional[str] = None
        self._bootstrap_existing_graphs()

    def _map_path(self, path_str: Optional[str]) -> Optional[Path]:
        """Maps a host path (/Users/mohsin/...) to container mount (/host_users/mohsin/...) if needed."""
        if not path_str:
            return None
        p_str = path_str.strip()
        p = Path(p_str)
        if p.is_absolute() and p_str.startswith("/Users/mohsin"):
            rel = p_str[len("/Users/mohsin"):].lstrip("/")
            container_path = Path("/host_users/mohsin") / rel
            if container_path.exists():
                return container_path
        return p

    def _get_project_name(self, mapped: Path) -> str:
        return mapped.name or "default"

    def _resolve_graph_file(self, project_or_graph_path: Optional[str] = None) -> Optional[Path]:
        """Finds graph.json from a project path, data storage, or graph file path."""
        mapped = self._map_path(project_or_graph_path)
        if mapped:
            if mapped.is_file() and mapped.suffix == ".json":
                return mapped
            # Check project directory graphify-out
            candidate = mapped / "graphify-out" / "graph.json"
            if candidate.is_file():
                return candidate
            candidate_here = mapped / "graph.json"
            if candidate_here.is_file():
                return candidate_here

            # Check persistent data directory under project name
            proj_name = self._get_project_name(mapped)
            candidate_data = self.data_dir / proj_name / "graphify-out" / "graph.json"
            if candidate_data.is_file():
                return candidate_data
            candidate_data_direct = self.data_dir / proj_name / "graph.json"
            if candidate_data_direct.is_file():
                return candidate_data_direct

        # If an explicit project name was passed (e.g. "Community")
        if project_or_graph_path and not project_or_graph_path.startswith("/"):
            candidate = self.data_dir / project_or_graph_path / "graphify-out" / "graph.json"
            if candidate.is_file():
                return candidate

        # Check default loaded graph
        if self.default_graph_key and self.default_graph_key in self.graphs:
            return Path(self.default_graph_key)

        # Look in self.data_dir for any existing graph.json
        for f in self.data_dir.glob("**/graph.json"):
            if f.is_file():
                return f

        return None

    def get_visualizer_html_path(self, project_or_graph_path: Optional[str] = None) -> Optional[Path]:
        """Finds or exports graph.html for visualization."""
        graph_file = self._resolve_graph_file(project_or_graph_path)
        if not graph_file or not graph_file.exists():
            return None

        html_candidate = graph_file.parent / "graph.html"
        if not html_candidate.exists():
            # Export html dynamically
            try:
                subprocess.run(
                    ["graphify", "export", "html", "--graph", str(graph_file)],
                    capture_output=True,
                    text=True,
                )
            except Exception as e:
                logger.error(f"Error exporting graph.html: {e}")

        return html_candidate if html_candidate.exists() else None

    def _bootstrap_existing_graphs(self):
        """Scans data dir for graphs and preloads them."""
        for f in self.data_dir.glob("**/graph.json"):
            try:
                self.get_graph(str(f))
                if not self.default_graph_key:
                    self.default_graph_key = str(f.resolve())
            except Exception as e:
                logger.warning(f"Could not load bootstrap graph at {f}: {e}")

    def get_graph(self, project_or_graph_path: Optional[str] = None) -> Tuple[nx.Graph, Dict[int, List[str]], str]:
        """Loads and caches NetworkX graph and communities dictionary."""
        resolved = self._resolve_graph_file(project_or_graph_path)
        if not resolved or not resolved.exists():
            raise FileNotFoundError(
                f"No knowledge graph found for path: '{project_or_graph_path or 'default'}'. "
                f"Build a graph first with POST /api/build or 'graphify <directory>'."
            )

        key = str(resolved.resolve())
        if key in self.graphs:
            G, communities = self.graphs[key]
            return G, communities, key

        try:
            from graphify.serve import _load_graph, _communities_from_graph
            G = _load_graph(str(resolved))
            communities = _communities_from_graph(G)
        except ImportError:
            with open(resolved, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "links" not in data and "edges" in data:
                data["links"] = data["edges"]
            from networkx.readwrite import json_graph
            try:
                G = json_graph.node_link_graph(data, edges="links")
            except TypeError:
                G = json_graph.node_link_graph(data)
            communities = {}
            for node_id, node_data in G.nodes(data=True):
                cid = node_data.get("community")
                if cid is not None:
                    communities.setdefault(int(cid), []).append(node_id)

        self.graphs[key] = (G, communities)
        if not self.default_graph_key:
            self.default_graph_key = key
        logger.info(f"Loaded graph from {key}: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        return G, communities, key

    def query(
        self,
        question: str,
        mode: str = "bfs",
        depth: int = 3,
        token_budget: int = 2000,
        context_filter: Optional[List[str]] = None,
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        G, communities, key = self.get_graph(project_path)
        try:
            from graphify.serve import _query_graph_text
            text_result = _query_graph_text(
                G,
                question,
                mode=mode,
                depth=min(depth, 6),
                token_budget=token_budget,
                context_filters=context_filter,
                graph_path=key,
            )
            return {"result": text_result, "graph_path": key, "nodes_total": G.number_of_nodes()}
        except ImportError:
            q_lower = question.lower()
            matched = []
            for nid, d in G.nodes(data=True):
                label = str(d.get("label", nid)).lower()
                if q_lower in label:
                    matched.append(f"Node: {d.get('label', nid)} ({nid}) - Type: {d.get('file_type', '')}")
            return {"result": "\n".join(matched[:20]) or "No matches found.", "graph_path": key}

    def get_node(self, label: str, project_path: Optional[str] = None) -> Dict[str, Any]:
        G, communities, key = self.get_graph(project_path)
        try:
            from graphify.serve import _resolve_single_node, sanitize_label
            nid, err = _resolve_single_node(G, label.lower())
            if err:
                return {"error": err, "graph_path": key}
            d = G.nodes[nid]
            return {
                "id": nid,
                "label": sanitize_label(d.get("label", nid)),
                "source_file": sanitize_label(str(d.get("source_file", ""))),
                "source_location": sanitize_label(str(d.get("source_location", ""))),
                "definition_file": sanitize_label(str(d.get("definition_file", ""))),
                "definition_location": sanitize_label(str(d.get("definition_location", ""))),
                "file_type": sanitize_label(str(d.get("file_type", ""))),
                "community": sanitize_label(str(d.get("community_name") or d.get("community", ""))),
                "degree": G.degree(nid),
                "graph_path": key,
            }
        except Exception as e:
            return {"error": str(e), "graph_path": key}

    def get_neighbors(
        self,
        label: str,
        relation_filter: Optional[str] = None,
        token_budget: int = 2000,
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        G, communities, key = self.get_graph(project_path)
        try:
            from graphify.serve import _resolve_single_node, sanitize_label, edge_data
            nid, err = _resolve_single_node(G, label.lower())
            if err:
                return {"error": err, "graph_path": key}

            out_edges = []
            for nb in G.successors(nid):
                d = edge_data(G, nid, nb)
                rel = d.get("relation", "")
                if relation_filter and relation_filter.lower() not in rel.lower():
                    continue
                out_edges.append({
                    "target": sanitize_label(G.nodes[nb].get("label", nb)),
                    "target_id": nb,
                    "relation": rel,
                    "confidence": d.get("confidence", "EXTRACTED"),
                    "location": d.get("source_location", ""),
                })

            in_edges = []
            for nb in G.predecessors(nid):
                d = edge_data(G, nb, nid)
                rel = d.get("relation", "")
                if relation_filter and relation_filter.lower() not in rel.lower():
                    continue
                in_edges.append({
                    "source": sanitize_label(G.nodes[nb].get("label", nb)),
                    "source_id": nb,
                    "relation": rel,
                    "confidence": d.get("confidence", "EXTRACTED"),
                    "location": d.get("source_location", ""),
                })

            return {
                "node": sanitize_label(G.nodes[nid].get("label", nid)),
                "node_id": nid,
                "outgoing": out_edges,
                "incoming": in_edges,
                "graph_path": key,
            }
        except Exception as e:
            return {"error": str(e), "graph_path": key}

    def get_community(self, community_id: int, project_path: Optional[str] = None) -> Dict[str, Any]:
        G, communities, key = self.get_graph(project_path)
        nodes = communities.get(community_id, [])
        if not nodes:
            return {"error": f"Community {community_id} not found", "graph_path": key}
        members = []
        for n in nodes:
            d = G.nodes[n]
            members.append({
                "id": n,
                "label": d.get("label", n),
                "source_file": d.get("source_file", ""),
                "type": d.get("file_type", ""),
            })
        return {
            "community_id": community_id,
            "community_name": G.nodes[nodes[0]].get("community_name") if nodes else "",
            "size": len(nodes),
            "members": members,
            "graph_path": key,
        }

    def core_hubs(
        self,
        top_n: int = 10,
        exclude_hubs_percentile: Optional[float] = None,
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        G, communities, key = self.get_graph(project_path)
        ranked = sorted(G.degree, key=lambda x: x[1], reverse=True)
        if exclude_hubs_percentile and 0.0 < exclude_hubs_percentile < 1.0:
            cutoff = int(len(ranked) * exclude_hubs_percentile)
            ranked = ranked[cutoff:]
        result = [
            {
                "id": nid,
                "label": G.nodes[nid].get("label", nid),
                "degree": deg,
                "file_type": G.nodes[nid].get("file_type", ""),
                "source_file": G.nodes[nid].get("source_file", ""),
                "community": G.nodes[nid].get("community", ""),
            }
            for nid, deg in ranked[:top_n]
        ]
        return {"core_hubs": result, "graph_path": key}

    def shortest_path(
        self,
        source: str,
        target: str,
        max_hops: int = 8,
        undirected: bool = False,
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        G, communities, key = self.get_graph(project_path)
        try:
            from graphify.serve import _shortest_path_text
            text = _shortest_path_text(
                G,
                {"source": source, "target": target, "max_hops": max_hops, "undirected": undirected}
            )
            return {"result": text, "graph_path": key}
        except Exception as e:
            return {"error": str(e), "graph_path": key}

    def stats(self, project_path: Optional[str] = None) -> Dict[str, Any]:
        G, communities, key = self.get_graph(project_path)
        confs = [d.get("confidence", "EXTRACTED") for _, _, d in G.edges(data=True)]
        total = len(confs) or 1
        return {
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "communities": len(communities),
            "confidence": {
                "extracted_pct": round(confs.count("EXTRACTED") / total * 100),
                "inferred_pct": round(confs.count("INFERRED") / total * 100),
                "ambiguous_pct": round(confs.count("AMBIGUOUS") / total * 100),
            },
            "graph_path": key,
        }

    def list_graphs(self) -> List[Dict[str, Any]]:
        results = []
        # Check active memory cache
        for key, (G, communities) in self.graphs.items():
            proj_name = Path(key).parent.parent.name if "graphify-out" in key else Path(key).parent.name
            results.append({
                "name": proj_name,
                "path": key,
                "nodes": G.number_of_nodes(),
                "edges": G.number_of_edges(),
                "communities": len(communities),
                "is_default": key == self.default_graph_key,
                "has_visualizer": (Path(key).parent / "graph.html").exists(),
            })
        # Check on-disk graphs not yet loaded
        for f in self.data_dir.glob("**/graph.json"):
            p_str = str(f.resolve())
            if p_str not in self.graphs:
                proj_name = f.parent.parent.name if "graphify-out" in str(f) else f.parent.name
                results.append({
                    "name": proj_name,
                    "path": p_str,
                    "status": "on_disk",
                    "has_visualizer": (f.parent / "graph.html").exists(),
                })
        return results

    def build_graph(self, target_path: str, force: bool = False) -> Dict[str, Any]:
        """Runs graphify extraction and exports interactive graph.html."""
        mapped = self._map_path(target_path)
        if not mapped or not mapped.exists():
            raise FileNotFoundError(f"Target path not found inside container: '{target_path}'")

        proj_name = self._get_project_name(mapped)
        out_base = self.data_dir / proj_name
        out_base.mkdir(parents=True, exist_ok=True)

        cmd = [
            "graphify",
            "extract",
            str(mapped),
            "--code-only",
            "--output",
            str(out_base),
        ]
        if force:
            cmd.append("--force")

        logger.info(f"Running indexing command: {' '.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True)

        if proc.returncode != 0:
            logger.error(f"Graphify build error: {proc.stderr}")
            return {
                "status": "error",
                "returncode": proc.returncode,
                "stderr": proc.stderr,
                "stdout": proc.stdout,
            }

        graph_file = out_base / "graphify-out" / "graph.json"
        if not graph_file.exists():
            graph_file = out_base / "graph.json"

        if graph_file.exists():
            # Automatically export interactive graph.html
            try:
                subprocess.run(
                    ["graphify", "export", "html", "--graph", str(graph_file)],
                    capture_output=True,
                    text=True,
                )
            except Exception as e:
                logger.warning(f"Could not auto-generate graph.html: {e}")

            self.graphs.pop(str(graph_file.resolve()), None)
            G, communities, key = self.get_graph(str(graph_file))
            return {
                "status": "success",
                "project_name": proj_name,
                "graph_path": key,
                "nodes": G.number_of_nodes(),
                "edges": G.number_of_edges(),
                "communities": len(communities),
                "visualizer_url": f"/visualizer?project={proj_name}",
                "stdout": proc.stdout,
            }

        return {
            "status": "warning",
            "message": "Process completed but graph.json not found.",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
