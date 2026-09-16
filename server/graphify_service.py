import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set
import networkx as nx

logger = logging.getLogger("graphify_service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

try:
    import kuzu
    HAS_KUZU = True
except ImportError:
    kuzu = None
    HAS_KUZU = False


def _run_graphify_cmd(args: List[str], env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    """Invokes graphify CLI using the active environment across Windows, Linux, and macOS."""
    py_dir = Path(sys.executable).parent
    binary_name = "graphify.exe" if sys.platform == "win32" else "graphify"
    candidate = py_dir / binary_name
    if candidate.exists():
        cmd = [str(candidate)] + args
    else:
        cmd = [sys.executable, "-m", "graphify.cli"] + args

    run_env = {**os.environ}
    if env:
        run_env.update(env)
    return subprocess.run(cmd, capture_output=True, text=True, env=run_env)


class GraphifyService:
    def __init__(self, data_dir: Optional[str] = None):
        base_dir = Path(__file__).resolve().parent.parent
        default_data = "/app/data" if (os.path.exists("/.dockerenv") or os.getenv("IS_DOCKER") == "1") else str(base_dir / "data")
        self.data_dir = Path(data_dir or os.getenv("GRAPHIFY_DATA_DIR", default_data))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.graphs: Dict[str, Tuple[nx.Graph, Dict[int, List[str]]]] = {}
        self.kuzu_connections: Dict[str, Any] = {}
        self.default_graph_key: Optional[str] = None
        self.has_kuzu = HAS_KUZU
        self._bootstrap_existing_graphs()

    def _map_path(self, path_str: Optional[str]) -> Optional[Path]:
        """Universal cross-platform path resolver for Windows, macOS, Linux, and Docker mounts."""
        if not path_str:
            return None
        p_str = path_str.strip().strip('"').strip("'")
        if not p_str:
            return None

        # Container workspace mount mapping
        if os.path.exists("/.dockerenv") or os.getenv("IS_DOCKER") == "1":
            workspaces = Path("/app/workspaces")
            p = Path(p_str)
            if not p.exists():
                candidate = workspaces / p.name
                if candidate.exists():
                    return candidate

        try:
            expanded = Path(p_str).expanduser()
            if expanded.exists():
                return expanded.resolve()
            if not expanded.is_absolute():
                cwd_rel = (Path.cwd() / expanded).resolve()
                if cwd_rel.exists():
                    return cwd_rel
            return expanded.resolve()
        except Exception:
            return Path(p_str)

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

        # If an explicit project name was passed (e.g. "my-project")
        if project_or_graph_path and not str(project_or_graph_path).startswith(("/", "\\")):
            clean_name = Path(project_or_graph_path).name
            candidate = self.data_dir / clean_name / "graphify-out" / "graph.json"
            if candidate.is_file():
                return candidate
            candidate2 = self.data_dir / clean_name / "graph.json"
            if candidate2.is_file():
                return candidate2

        # Check default loaded graph
        if self.default_graph_key and self.default_graph_key in self.graphs:
            return Path(self.default_graph_key)

        # Look in self.data_dir for any existing graph.json
        for f in self.data_dir.glob("**/graph.json"):
            if f.is_file():
                return f

        # Check local working directory graphify-out
        local_out = Path.cwd() / "graphify-out" / "graph.json"
        if local_out.is_file():
            return local_out

        return None

    def _bootstrap_existing_graphs(self):
        """Scans data dir and local directory for graphs and preloads them."""
        candidates = list(self.data_dir.glob("**/graph.json"))
        local_candidate = Path.cwd() / "graphify-out" / "graph.json"
        if local_candidate.exists() and local_candidate not in candidates:
            candidates.append(local_candidate)

        for f in candidates:
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
                f"Build a graph first with POST /api/build or 'graphify extract <directory>'."
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
                    try:
                        communities.setdefault(int(cid), []).append(node_id)
                    except (ValueError, TypeError):
                        pass

        self.graphs[key] = (G, communities)
        if not self.default_graph_key:
            self.default_graph_key = key
        logger.info(f"Loaded graph from {key}: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

        if HAS_KUZU:
            try:
                self._sync_to_kuzu(resolved, G)
            except Exception as e:
                logger.warning(f"KùzuDB sync notice for {resolved}: {e}")

        return G, communities, key

    # ==================== KÙZUDB INTEGRATION ====================
    def _sync_to_kuzu(self, graph_file: Path, G: nx.Graph):
        """Ingests graph nodes and relationships into an embedded KùzuDB on disk."""
        if not HAS_KUZU:
            return None

        db_dir = graph_file.parent / "kuzu_db"
        key = str(graph_file.resolve())
        if key in self.kuzu_connections:
            return self.kuzu_connections[key]

        try:
            db = kuzu.Database(str(db_dir))
            conn = kuzu.Connection(db)
        except Exception as e:
            if "lock" in str(e).lower() and (db_dir.exists() or Path(str(db_dir) + ".lock").exists()):
                try:
                    db = kuzu.Database(str(db_dir), read_only=True)
                    conn = kuzu.Connection(db)
                    self.kuzu_connections[key] = conn
                    return conn
                except Exception:
                    pass
            raise e

        try:
            conn.execute(
                "CREATE NODE TABLE IF NOT EXISTS CodeNode("
                "id STRING, label STRING, source_file STRING, file_type STRING, "
                "community INT64, degree INT64, PRIMARY KEY (id))"
            )
            conn.execute(
                "CREATE REL TABLE IF NOT EXISTS Relates("
                "FROM CodeNode TO CodeNode, relation STRING, confidence STRING, location STRING)"
            )
        except Exception as e:
            logger.debug(f"Kùzu schema check: {e}")

        count_res = conn.execute("MATCH (c:CodeNode) RETURN count(c) AS cnt").get_next()
        existing_count = count_res[0] if count_res else 0

        if existing_count < G.number_of_nodes():
            logger.info(f"Populating KùzuDB at {db_dir} with {G.number_of_nodes()} nodes...")
            for nid, d in G.nodes(data=True):
                lbl = str(d.get("label", nid)).replace("'", "''")
                sf = str(d.get("source_file", "")).replace("'", "''")
                ft = str(d.get("file_type", "")).replace("'", "''")
                comm = int(d.get("community", -1)) if isinstance(d.get("community"), (int, float)) else -1
                deg = int(G.degree(nid))
                safe_nid = str(nid).replace("'", "''")
                try:
                    conn.execute(
                        f"MERGE (c:CodeNode {{id: '{safe_nid}'}}) "
                        f"ON CREATE SET c.label = '{lbl}', c.source_file = '{sf}', c.file_type = '{ft}', c.community = {comm}, c.degree = {deg}"
                    )
                except Exception:
                    pass

            for u, v, d in G.edges(data=True):
                safe_u = str(u).replace("'", "''")
                safe_v = str(v).replace("'", "''")
                rel = str(d.get("relation", "CALLS")).replace("'", "''")
                conf = str(d.get("confidence", "EXTRACTED")).replace("'", "''")
                loc = str(d.get("source_location", "")).replace("'", "''")
                try:
                    conn.execute(
                        f"MATCH (a:CodeNode {{id: '{safe_u}'}}), (b:CodeNode {{id: '{safe_v}'}}) "
                        f"CREATE (a)-[:Relates {{relation: '{rel}', confidence: '{conf}', location: '{loc}'}}]->(b)"
                    )
                except Exception:
                    pass

        self.kuzu_connections[key] = conn
        logger.info(f"KùzuDB ready for {key}")
        return conn

    def execute_cypher(self, query: str, project_path: Optional[str] = None) -> Dict[str, Any]:
        """Runs a declarative Cypher query against the embedded KùzuDB instance."""
        if not HAS_KUZU:
            return {"error": "KùzuDB is not installed in the environment. Install with: pip install kuzu"}

        G, communities, key = self.get_graph(project_path)
        conn = self.kuzu_connections.get(key)
        if not conn:
            conn = self._sync_to_kuzu(Path(key), G)

        try:
            res = conn.execute(query)
            cols = res.get_column_names()
            rows = []
            while res.has_next():
                row = res.get_next()
                rows.append(dict(zip(cols, row)))
            return {
                "status": "success",
                "query": query,
                "columns": cols,
                "row_count": len(rows),
                "rows": rows[:100],
                "graph_path": key,
            }
        except Exception as e:
            return {"error": f"Cypher execution failed: {e}", "query": query, "graph_path": key}

    # ==================== ADVANCED AGENTIC TOOLS ====================
    def blast_radius(
        self,
        symbol: str,
        max_depth: int = 3,
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculates all transitive downstream dependents, files, and tests affected if a symbol changes."""
        G, communities, key = self.get_graph(project_path)
        sym_lower = symbol.strip().lower()

        matched_nids = []
        for nid, d in G.nodes(data=True):
            lbl = str(d.get("label", nid)).lower()
            if sym_lower == lbl or sym_lower in lbl or sym_lower == str(nid).lower():
                matched_nids.append(nid)

        if not matched_nids:
            return {"error": f"Symbol '{symbol}' not found in knowledge graph.", "graph_path": key}

        target_nid = matched_nids[0]
        target_data = G.nodes[target_nid]

        affected_by_depth: Dict[int, List[Dict[str, Any]]] = {d: [] for d in range(1, max_depth + 1)}
        visited: Set[str] = {target_nid}
        queue: List[Tuple[str, int]] = [(target_nid, 0)]
        affected_files: Set[str] = set()
        affected_tests: Set[str] = set()

        while queue:
            curr, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            for pred in G.predecessors(curr):
                if pred not in visited:
                    visited.add(pred)
                    pred_d = G.nodes[pred]
                    src_file = str(pred_d.get("source_file", ""))
                    item = {
                        "id": pred,
                        "label": pred_d.get("label", pred),
                        "file": src_file,
                        "type": pred_d.get("file_type", ""),
                        "depth": depth + 1,
                    }
                    affected_by_depth[depth + 1].append(item)
                    if src_file:
                        affected_files.add(src_file)
                        if "test" in src_file.lower():
                            affected_tests.add(src_file)
                    queue.append((pred, depth + 1))

        total_affected = len(visited) - 1
        return {
            "target": {
                "id": target_nid,
                "label": target_data.get("label", target_nid),
                "file": target_data.get("source_file", ""),
                "type": target_data.get("file_type", ""),
            },
            "total_dependents_affected": total_affected,
            "affected_files_count": len(affected_files),
            "affected_files": sorted(list(affected_files)),
            "affected_tests": sorted(list(affected_tests)),
            "impact_by_depth": {
                f"hop_{d}": items for d, items in affected_by_depth.items() if items
            },
            "risk_level": "HIGH" if total_affected > 15 else "MEDIUM" if total_affected > 4 else "LOW",
            "graph_path": key,
        }

    def call_flow(
        self,
        symbol: str,
        max_depth: int = 3,
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Traces execution call chains from an entrypoint and returns a Mermaid sequence/flowchart."""
        G, communities, key = self.get_graph(project_path)
        sym_lower = symbol.strip().lower()

        matched_nids = [nid for nid, d in G.nodes(data=True) if sym_lower in str(d.get("label", nid)).lower()]
        if not matched_nids:
            return {"error": f"Symbol '{symbol}' not found in knowledge graph.", "graph_path": key}

        start_nid = matched_nids[0]
        start_label = G.nodes[start_nid].get("label", start_nid)

        mermaid_lines = ["graph TD"]
        visited_edges: Set[Tuple[str, str]] = set()
        queue: List[Tuple[str, int]] = [(start_nid, 0)]
        visited_nodes: Set[str] = {start_nid}

        while queue:
            curr, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            curr_lbl = str(G.nodes[curr].get("label", curr)).replace('"', "")
            for succ in G.successors(curr):
                edge_key = (curr, succ)
                if edge_key not in visited_edges:
                    visited_edges.add(edge_key)
                    succ_lbl = str(G.nodes[succ].get("label", succ)).replace('"', "")
                    edge_d = G.get_edge_data(curr, succ) or {}
                    rel = edge_d.get("relation", "CALLS")
                    
                    safe_u = f"n_{abs(hash(curr)) % 100000}"
                    safe_v = f"n_{abs(hash(succ)) % 100000}"
                    mermaid_lines.append(f'    {safe_u}["{curr_lbl}"] -->|{rel}| {safe_v}["{succ_lbl}"]')

                    if succ not in visited_nodes:
                        visited_nodes.add(succ)
                        queue.append((succ, depth + 1))

        mermaid_code = "\n".join(mermaid_lines)
        return {
            "root": start_label,
            "total_nodes_traced": len(visited_nodes),
            "total_calls_traced": len(visited_edges),
            "mermaid": mermaid_code,
            "graph_path": key,
        }

    def dead_code(self, project_path: Optional[str] = None) -> Dict[str, Any]:
        """Identifies orphan functions, unreferenced classes, and potential dead code."""
        G, communities, key = self.get_graph(project_path)
        orphans = []
        ignored_names = {"main", "__init__", "app", "router", "setup", "test", "index"}

        for nid, d in G.nodes(data=True):
            in_deg = G.in_degree(nid)
            out_deg = G.out_degree(nid)
            lbl = str(d.get("label", nid)).lower()

            if any(ign in lbl for ign in ignored_names) or lbl.startswith("__"):
                continue
            src = str(d.get("source_file", "")).lower()
            if "test" in src or "migration" in src:
                continue

            if in_deg == 0:
                orphans.append({
                    "id": nid,
                    "label": d.get("label", nid),
                    "file": d.get("source_file", ""),
                    "file_type": d.get("file_type", ""),
                    "out_degree": out_deg,
                    "reason": "In-degree is 0 (unreferenced by other code in this project)",
                })

        return {
            "total_orphans_found": len(orphans),
            "orphans": orphans[:50],
            "graph_path": key,
        }

    def context_bundle(
        self,
        symbols: List[str],
        token_budget: int = 4000,
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extracts a token-capped sub-graph context package tailored for LLM prompt injection."""
        G, communities, key = self.get_graph(project_path)
        selected_nodes: Set[str] = set()

        for sym in symbols:
            s_lower = sym.strip().lower()
            for nid, d in G.nodes(data=True):
                if s_lower in str(d.get("label", nid)).lower():
                    selected_nodes.add(nid)
                    for nb in G.neighbors(nid):
                        selected_nodes.add(nb)

        lines = [f"# Codebase Context Bundle (Budget: {token_budget} tokens)"]
        for nid in list(selected_nodes)[:40]:
            d = G.nodes[nid]
            lines.append(f"### Symbol: {d.get('label', nid)}")
            lines.append(f"- File: `{d.get('source_file', '')}` (Type: {d.get('file_type', '')})")
            
            callers = [G.nodes[p].get("label", p) for p in G.predecessors(nid)][:5]
            callees = [G.nodes[s].get("label", s) for s in G.successors(nid)][:5]
            if callers:
                lines.append(f"- Called by: {', '.join(callers)}")
            if callees:
                lines.append(f"- Calls: {', '.join(callees)}")
            lines.append("")

        content = "\n".join(lines)
        approx_tokens = len(content) // 4

        return {
            "symbols_requested": symbols,
            "nodes_packaged": len(selected_nodes),
            "estimated_tokens": approx_tokens,
            "bundle": content,
            "graph_path": key,
        }

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
                "has_tree": (Path(key).parent / "GRAPH_TREE.html").exists(),
                "has_callflow": (Path(key).parent / "GRAPH_CALLFLOW.html").exists(),
            })

        for f in self.data_dir.glob("**/graph.json"):
            p_str = str(f.resolve())
            if p_str not in self.graphs:
                proj_name = f.parent.parent.name if "graphify-out" in str(f) else f.parent.name
                results.append({
                    "name": proj_name,
                    "path": p_str,
                    "status": "on_disk",
                    "has_visualizer": (f.parent / "graph.html").exists(),
                    "has_tree": (f.parent / "GRAPH_TREE.html").exists(),
                })
        return results

    def get_visualizer_html_path(self, project_or_graph_path: Optional[str] = None) -> Optional[Path]:
        """Finds or exports graph.html for visualization."""
        graph_file = self._resolve_graph_file(project_or_graph_path)
        if not graph_file or not graph_file.exists():
            return None

        html_candidate = graph_file.parent / "graph.html"
        if not html_candidate.exists():
            try:
                _run_graphify_cmd(["export", "html", "--graph", str(graph_file), "--node-limit", "50000"])
            except Exception as e:
                logger.error(f"Error exporting graph.html: {e}")

        return html_candidate if html_candidate.exists() else None

    def get_tree_html_path(self, project_or_graph_path: Optional[str] = None) -> Optional[Path]:
        """Finds or generates GRAPH_TREE.html (D3 collapsible architecture tree)."""
        graph_file = self._resolve_graph_file(project_or_graph_path)
        if not graph_file or not graph_file.exists():
            return None

        tree_candidate = graph_file.parent / "GRAPH_TREE.html"
        if not tree_candidate.exists():
            try:
                _run_graphify_cmd(["tree", "--graph", str(graph_file), "--output", str(tree_candidate)])
            except Exception as e:
                logger.error(f"Error generating GRAPH_TREE.html: {e}")

        return tree_candidate if tree_candidate.exists() else None

    def get_callflow_html_path(self, project_or_graph_path: Optional[str] = None) -> Optional[Path]:
        """Finds or exports Mermaid call-flow HTML."""
        graph_file = self._resolve_graph_file(project_or_graph_path)
        if not graph_file or not graph_file.exists():
            return None

        callflow_candidate = graph_file.parent / "GRAPH_CALLFLOW.html"
        if not callflow_candidate.exists():
            try:
                _run_graphify_cmd(["export", "callflow-html", str(graph_file.parent), "--output", str(callflow_candidate)])
            except Exception as e:
                logger.error(f"Error generating callflow HTML: {e}")

        return callflow_candidate if callflow_candidate.exists() else None

    def build_graph(self, target_path: str, force: bool = False) -> Dict[str, Any]:
        """Runs graphify extraction and exports interactive HTML visualizers."""
        mapped = self._map_path(target_path)
        if not mapped or not mapped.exists():
            raise FileNotFoundError(f"Target path not found: '{target_path}'")

        proj_name = self._get_project_name(mapped)
        out_base = self.data_dir / proj_name
        out_base.mkdir(parents=True, exist_ok=True)

        args = [
            "extract",
            str(mapped),
            "--code-only",
            "--output",
            str(out_base),
        ]
        if force:
            args.append("--force")

        logger.info(f"Indexing repository at: {mapped}")
        proc = _run_graphify_cmd(args)

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
            try:
                _run_graphify_cmd(["export", "html", "--graph", str(graph_file), "--node-limit", "50000"])
            except Exception as e:
                logger.warning(f"Could not auto-generate graph.html: {e}")

            try:
                _run_graphify_cmd(["tree", "--graph", str(graph_file), "--output", str(out_base / "GRAPH_TREE.html")])
            except Exception as e:
                logger.warning(f"Could not auto-generate tree HTML: {e}")

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
                "tree_url": f"/tree?project={proj_name}",
                "stdout": proc.stdout,
            }

        return {
            "status": "warning",
            "message": "Process completed but graph.json not found.",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
