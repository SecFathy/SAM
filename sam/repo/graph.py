"""File dependency graph with PageRank ranking."""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from sam.repo.tags import FileSymbols


@dataclass
class RankedFile:
    """A file with its PageRank importance score."""

    path: str
    score: float
    definitions: list[str]


def build_dependency_graph(
    file_symbols: list[FileSymbols],
) -> nx.DiGraph:
    """Build a directed graph of file dependencies based on symbol references.

    An edge from A -> B means file A references symbols defined in file B.
    """
    graph = nx.DiGraph()

    # Build index: symbol name -> list of files defining it
    symbol_to_files: dict[str, list[str]] = {}
    for fs in file_symbols:
        graph.add_node(fs.path)
        for defn in fs.definitions:
            symbol_to_files.setdefault(defn.name, []).append(fs.path)

    # Add edges from references to definitions
    for fs in file_symbols:
        for ref in fs.references:
            if ref in symbol_to_files:
                for def_file in symbol_to_files[ref]:
                    if def_file != fs.path:
                        # fs.path references a symbol in def_file
                        if graph.has_edge(fs.path, def_file):
                            graph[fs.path][def_file]["weight"] += 1
                        else:
                            graph.add_edge(fs.path, def_file, weight=1)

    return graph


def rank_files(
    graph: nx.DiGraph,
    personalized_files: list[str] | None = None,
    top_n: int = 30,
) -> list[RankedFile]:
    """Rank files by importance using personalized PageRank.

    If personalized_files is provided, those files get boosted importance
    (simulating the user's working set).
    """
    if len(graph) == 0:
        return []

    # Build personalization vector
    personalization = None
    if personalized_files:
        personalization = {}
        nodes = set(graph.nodes())
        for node in nodes:
            personalization[node] = 1.0
        for pf in personalized_files:
            if pf in nodes:
                personalization[pf] = 10.0  # Boost working files

    try:
        scores = nx.pagerank(
            graph,
            alpha=0.85,
            personalization=personalization,
            max_iter=100,
        )
    except nx.PowerIterationFailedConvergence:
        # Fallback to uniform scores
        scores = {node: 1.0 / len(graph) for node in graph.nodes()}

    # Sort by score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    return [
        RankedFile(path=path, score=score, definitions=[])
        for path, score in ranked[:top_n]
    ]
