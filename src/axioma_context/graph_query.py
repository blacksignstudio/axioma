"""Bounded, read-only queries over a manifest-verified local graph."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .cli import InvalidProject, safe


def _read_json(path, label):
    try:
        raw = path.read_bytes()
        return json.loads(raw.decode("utf-8")), raw
    except (OSError, UnicodeError, ValueError) as error:
        raise InvalidProject(f"Cannot read {label}: {error}") from error


def _bounded(items, available):
    return {"items": items, "available": available, "returned": len(items),
            "truncated": len(items) < available}


def query(root, *, search=None, identifier=None, limit=8, relation=None,
          include_text=False, max_bytes=65536):
    """Return matches or incident edges with explicit source verification levels.

    Limit applies to matches or incident edges. Neighbours are the unique other
    endpoints of returned edges, so no returned edge has an undisclosed peer.
    Integrity is relative to the local manifest, not an external signature.
    The self-manifest node is exposed as an explicitly unverified trust root.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise InvalidProject("Graph limit must be an integer from 1 to 100")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1024 <= max_bytes <= 1048576:
        raise InvalidProject("Graph max-bytes must be an integer from 1024 to 1048576")
    if not isinstance(include_text, bool):
        raise InvalidProject("Graph text option must be boolean")
    if (search is None) == (identifier is None):
        raise InvalidProject("Choose exactly one graph --search or --id")
    value = search if search is not None else identifier
    if not isinstance(value, str) or not value.strip():
        raise InvalidProject("Graph search or ID must be nonempty")
    if relation is not None and search is not None:
        raise InvalidProject("Graph --relation requires --id")
    if include_text and search is not None:
        raise InvalidProject("Graph --text requires --id")
    if relation is not None and (not isinstance(relation, str) or not relation):
        raise InvalidProject("Graph relation must be a nonempty type or semantic relation")
    root = Path(root).resolve()
    manifest, _ = _read_json(safe(root, "manifest.json", exists=True), "release manifest")
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, list):
        raise InvalidProject("Release manifest requires a file list")
    manifest_files = {}
    for row in files:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise InvalidProject("Invalid release manifest file record")
        if row["path"] in manifest_files:
            raise InvalidProject("Duplicate path in release manifest")
        manifest_files[row["path"]] = row
    graph_record = manifest_files.get("graph.json")
    if graph_record is None:
        raise InvalidProject("Graph is absent from release manifest; regenerate the local release")
    graph, raw = _read_json(safe(root, "graph.json", exists=True), "local graph")
    graph_sha = hashlib.sha256(raw).hexdigest()
    if graph_sha != graph_record.get("sha256"):
        raise InvalidProject("Graph digest differs from release manifest; regenerate the local release")
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
        raise InvalidProject("Graph requires node and edge lists")
    nodes = {}
    for node in graph["nodes"]:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or node["id"] in nodes:
            raise InvalidProject("Invalid or duplicate graph node ID")
        nodes[node["id"]] = node
    edges = graph["edges"]
    if any(not isinstance(e, dict) or not isinstance(e.get("source"), str) or
           not isinstance(e.get("target"), str) or e.get("source") not in nodes or
           e.get("target") not in nodes or not isinstance(e.get("type"), str) for e in edges):
        raise InvalidProject("Graph contains an invalid or dangling edge")
    types = {e["type"] for e in edges} | {
        e["relation"] for e in edges if isinstance(e.get("relation"), str)}
    if relation is not None and relation not in types:
        raise InvalidProject("Unknown graph relation: " + str(relation))
    checked = {}
    verification = {}
    source_bytes = {}

    def verify(node):
        document = node
        if node.get("kind") == "block":
            document = nodes.get(node.get("document_id"))
            if document is None or document.get("kind") == "block" or document.get("path") != node.get("path"):
                raise InvalidProject("Graph block has no matching source document: " + node["id"])
        path = document.get("path")
        if not isinstance(path, str):
            raise InvalidProject("Graph node has no source path: " + node["id"])
        if (node is document and document["id"] == "file:manifest.json" and
                document.get("kind") == "file" and path == "manifest.json" and
                document.get("derived") is True):
            if document.get("sha256") is not None:
                raise InvalidProject("Self-manifest graph node must not declare a source digest")
            verification[path] = {
                "status": "unverified-self",
                "detail": "not self-hashable; manifest is the local trust root"}
            return
        expected = document.get("sha256") or manifest_files.get(path, {}).get("sha256")
        if node.get("kind") == "block" and not isinstance(document.get("sha256"), str):
            raise InvalidProject("Graph block source has no graph-bound digest: " + node["id"])
        if not isinstance(expected, str):
            raise InvalidProject("Graph node has no verifiable source digest: " + node["id"])
        if checked.get(path) == expected:
            return
        actual_bytes = safe(root, path, exists=True).read_bytes()
        actual = hashlib.sha256(actual_bytes).hexdigest()
        if actual != expected:
            raise InvalidProject("Changed graph source: " + path + "; regenerate the local release")
        checked[path] = expected
        source_bytes[path] = actual_bytes
        verification[path] = {"status": "sha256-verified", "sha256": expected}

    files_by_path = {n.get("path"): n for n in nodes.values() if n.get("kind") != "block"}

    def verify_edge(edge):
        paths = [edge["source_path"]] if edge.get("source_path") else []
        evidence = edge.get("evidence", [])
        if isinstance(evidence, list):
            paths.extend(e["path"] for e in evidence if isinstance(e, dict) and e.get("path"))
        for path in paths:
            if path not in files_by_path:
                raise InvalidProject("Graph evidence has no source document: " + str(path))
            verify(files_by_path[path])
        if isinstance(evidence, list):
            for witness in evidence:
                if not isinstance(witness, dict) or not witness.get("path"):
                    continue
                raw_source = source_bytes.get(witness["path"])
                if raw_source is None:
                    raise InvalidProject("Graph evidence cannot use the self-manifest as a witness")
                if witness.get("source_sha256") not in (None, checked[witness["path"]]):
                    raise InvalidProject("Graph evidence digest differs from its source")
                excerpt = witness.get("excerpt")
                if not isinstance(excerpt, str) or excerpt not in raw_source.decode("utf-8"):
                    raise InvalidProject("Stale graph evidence excerpt: " + witness["path"])

    result = {"graph_sha256": graph_sha, "limit": limit,
              "graph_verification": "sha256-verified-against-local-manifest",
              "max_bytes": max_bytes,
              "verification_scope": "Returned source files and returned edge evidence; self-manifest is explicitly unverified",
              "source_verification": verification}
    if search is not None:
        needle = search.strip().casefold()
        fields = ("id", "title", "path", "module", "concept")
        matches = sorted((n for n in nodes.values() if any(
            needle in str(n.get(field, "")).casefold() for field in fields)), key=lambda n: n["id"])
        selected = matches[:limit]
        for node in selected:
            verify(node)
        result.update({"mode": "search", "search": search, "search_fields": list(fields),
                       "matches": _bounded(selected, len(matches))})
    else:
        if identifier not in nodes:
            raise InvalidProject("Unknown graph ID: " + identifier)
        focus = nodes[identifier]
        incident = [e for e in edges if identifier in (e["source"], e["target"]) and
                    (relation is None or relation in (e["type"], e.get("relation")))]
        incident.sort(key=lambda e: (e["type"], e["source"], e["target"],
                                     json.dumps(e, sort_keys=True, ensure_ascii=False)))
        selected = incident[:limit]
        peers = lambda es: {endpoint for e in es for endpoint in (e["source"], e["target"])
                            if endpoint != identifier}
        neighbours = [nodes[i] for i in sorted(peers(selected))]
        for node in [focus, *neighbours]:
            verify(node)
        for edge in selected:
            verify_edge(edge)
        result.update({"mode": "neighbors", "focus": focus, "relation": relation,
                       "limit_applies_to": "Incident edges; neighbors are their unique other endpoints",
                       "neighbors": _bounded(neighbours, len(peers(incident))),
                       "edges": _bounded(selected, len(incident))})
        if include_text or focus.get("block_type") == "component":
            verify(focus)
            if focus["path"] not in source_bytes:
                raise InvalidProject("The self-manifest has no graph-bound source text")
            try:
                text = source_bytes[focus["path"]].decode("utf-8")
            except UnicodeError as error:
                raise InvalidProject("Graph --text requires a UTF-8 source file") from error
            if focus.get("kind") == "block":
                lines = text.splitlines(keepends=True)
                start, end = focus.get("line_start"), focus.get("line_end")
                if (isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or
                        not isinstance(end, int) or not 1 <= start <= end <= len(lines)):
                    raise InvalidProject("Graph text block has an invalid source range")
                text = "".join(lines[start - 1:end])
                if hashlib.sha256(text.encode("utf-8")).hexdigest() != focus.get("content_sha256"):
                    raise InvalidProject("Graph text span digest differs from its source")
            result["text"] = {"scope": "whole_component" if focus.get("block_type") == "component" else
                              "section_subtree" if focus.get("kind") == "block" else "whole_file",
                              "complete": True, "utf8_bytes": len(text.encode("utf-8")), "content": text}
    # Match the CLI's actual UTF-8 JSON format including its trailing newline.
    # A whole source span is either returned in full or refused, never clipped.
    result["budget_policy"] = "Complete JSON response; refuse rather than silently clip text or evidence"
    if len((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")) > max_bytes:
        raise InvalidProject("Graph response exceeds max-bytes; lower --limit or increase --max-bytes (text is never clipped)")
    return result
