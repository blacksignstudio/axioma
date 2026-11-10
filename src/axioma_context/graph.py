"""Deterministic file, heading-section and editorial reading graphs.

Section ranges expose the source, not a duplicate of its full text. Lexical
mentions are candidates; neither a mention nor a drawing proves a causal,
canonical or biological relationship.
"""
from __future__ import annotations

from collections import Counter
import hashlib
from html import escape
import json
import math
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import quote, unquote, urlsplit

from .cli import InvalidProject, MD, anchor, digest, document, project_files, safe
from .graph_components import compositions
from .graph_readings import curated_relations, motif_candidates, section_records


OUTPUTS = ("graph.json", "assets/corpus-graph.svg")
SELF_DERIVED = {*OUTPUTS, "assets/graph-explorer.html", "manifest.json"}
MODULE_PATH = re.compile(r"^corpus/(\d{2}_[a-z_]+)/README\.md$")
RELATIONS = (
    ("AXIS", "WILL", "bearing and direction"),
    ("MEMORY", "ARCHIVE", "retained traces and preservation"),
    ("ARCHIVE", "TRACE", "a collection and its remainders"),
    ("TRACE", "RESIDUE", "marks and persistence"),
    ("ERROR", "CORRECTION", "a mismatch and its revision"),
    ("GLITCH", "ERROR", "interruption and observed failure"),
    ("WILL", "HAND", "direction and action"),
    ("SIGNAL", "NOISE", "meaning and interference"),
    ("EYE", "SURFACE", "viewpoint and appearance"),
    ("BRAIN", "PATTERN", "interpretation and recurrence"),
    ("SKIN", "FIELD", "boundary and encounter"),
    ("BONE", "FORM", "structure and arrangement"),
    ("HEART", "ECHO", "relation and returning response"),
    ("TENSION", "PULSE", "competing tendencies and rhythm"),
    ("PATTERN", "SYMMETRY", "recurrence and correspondence"),
    ("CORRECTION", "LOCK", "revision and a held version"),
    ("LOCK", "NULLFIELD", "a boundary and a pause"),
    ("NULLFIELD", "ECHO", "an interval and a return"),
    ("POWER", "WILL", "capability and direction"),
    ("POWER", "FIELD", "capability and shared conditions"),
    ("POWER", "HAND", "capability and its use"),
    ("FIELD", "SIGNAL", "conditions and reception"),
    ("PULSE", "SIGNAL", "rhythm and a received difference"),
    ("SHADOW", "SURFACE", "a blind side and appearance"),
    ("SHADOW", "POWER", "the limits of a strength"),
    ("SYMMETRY", "AXIS", "correspondence and a bearing"),
    ("FORM", "AXIS", "arrangement and recognizable form"),
    ("PATTERN", "MEMORY", "recurrence and retained evidence"),
    ("TENSION", "BONE", "pressure and supporting structure"),
    ("ECHO", "SIGNAL", "a return and its fidelity"),
)


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _navigation(title, lines):
    navigation_titles = {"connections", "contents", "table of contents", "navigation", "index",
                         "navigation of the working edition", "working edition navigation"}
    if " ".join(title.casefold().split()).rstrip(":") in navigation_titles:
        return True
    visible = [s.strip() for s in lines if s.strip() and s.strip() not in {"---", "\u2014"}]
    return bool(visible) and all(
        re.match(r"^(?:[-*+]\s+)?(?:\[[^]]+\]\([^)]+\)|\d{1,2}\s+[\u2014-]\s+)", s)
        for s in visible
    )


def _framing(title, lines):
    """Recognize narrow, inspectable framing; never classify by a title alone."""
    normalized = " ".join(title.casefold().split()).rstrip(":")
    text = "".join(lines)
    substantive = [t for t in MD.parse(text) if t.type != "hr"]
    if (normalized == "component metadata" and len(substantive) == 1
            and substantive[0].type == "fence"
            and substantive[0].info.strip().casefold() in {"yaml", "yml"}):
        return "metadata"
    if (normalized == "00. disclaimer"
            and "a work of speculative philosophy" in text.casefold()
            and "hypothetical and symbolic" in text.casefold()):
        return "editorial"
    return None


def _sections(record, text):
    """Map every heading section and any unheaded preamble to exact file lines."""
    _, body = document(text)
    file_lines = text.splitlines(keepends=True)
    body_lines = body.splitlines(keepends=True)
    offset = len(file_lines) - len(body_lines)
    tokens = MD.parse(body)
    headings, explicit, used = [], [], set()
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            title = "".join(c.content for c in tokens[i + 1].children or []
                            if c.type in {"text", "code_inline"})
            headings.append({"level": int(token.tag[1:]), "title": title,
                             "anchor": anchor(title, used),
                             "start": token.map[0], "heading_end": token.map[1]})
        if token.type == "inline" and token.map:
            match = re.fullmatch(r'<a\s+id=["\']([^"\']+)["\']\s*></a>', token.content.strip())
            if match:
                explicit.append((match[1], token.map[0], token.map[1]))
    blocks, hierarchy, stack = [], [], []
    for i, heading in enumerate(headings):
        end = next((h["start"] for h in headings[i + 1:]
                    if h["level"] <= heading["level"]), len(body_lines))
        own_end = headings[i + 1]["start"] if i + 1 < len(headings) else len(body_lines)
        own_lines = body_lines[heading["heading_end"]:own_end]
        meaningful = any(s.strip() and s.strip() not in {"---", "\u2014"} for s in own_lines)
        block_type = (_framing(heading["title"], own_lines) or
                      ("navigation" if _navigation(heading["title"], own_lines)
                       else "content" if meaningful else "outline"))
        identifier = record["id"] + "#" + heading["anchor"]
        node = {"id": identifier, "kind": "block", "block_type": block_type,
                "title": heading["title"], "document_id": record["id"],
                "path": record["path"], "anchor": heading["anchor"],
                "anchor_kind": "github_heading", "heading_level": heading["level"],
                "line_start": offset + heading["start"] + 1, "line_end": offset + end,
                "own_line_start": offset + heading["start"] + 1,
                "own_line_end": offset + own_end,
                "content_sha256": _sha("".join(body_lines[heading["start"]:end]))}
        while stack and stack[-1]["heading_level"] >= node["heading_level"]:
            stack.pop()
        hierarchy.append((stack[-1]["id"] if stack else record["id"], identifier))
        stack.append(node)
        blocks.append(node)
    preamble_end = headings[0]["start"] if headings else len(body_lines)
    if "".join(body_lines[:preamble_end]).strip():
        node = {"id": record["id"] + "#~preamble", "kind": "block",
                "block_type": "content", "title": "Unheaded body",
                "document_id": record["id"], "path": record["path"],
                "anchor": None, "anchor_kind": "line_range", "heading_level": 0,
                "line_start": offset + 1, "line_end": offset + preamble_end,
                "own_line_start": offset + 1, "own_line_end": offset + preamble_end,
                "content_sha256": _sha("".join(body_lines[:preamble_end]))}
        blocks.insert(0, node)
        hierarchy.append((record["id"], node["id"]))
    for name, start, end in explicit:
        containing = [h for h in blocks if h["line_start"] <= offset + start + 1 <= h["line_end"]]
        parent = min(containing, key=lambda h: h["line_end"] - h["line_start"]) if containing else None
        node = {"id": record["id"] + "#" + name, "kind": "block", "block_type": "anchor",
                "title": name, "document_id": record["id"], "path": record["path"],
                "anchor": name, "anchor_kind": "explicit", "heading_level": 0,
                "line_start": offset + start + 1, "line_end": offset + end,
                "own_line_start": offset + start + 1, "own_line_end": offset + end,
                "content_sha256": _sha("".join(body_lines[start:end]))}
        blocks.append(node)
        hierarchy.append((parent["id"] if parent else record["id"], node["id"]))
    blocks.sort(key=lambda n: (n["line_start"], n["id"]))
    return blocks, hierarchy, tokens, offset, file_lines


def _lexical(block, file_lines, concepts):
    start, end = block["own_line_start"], block["own_line_end"]
    for term, target in sorted(concepts.items()):
        pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.I)
        evidence = None
        for number in range(start, end + 1):
            line = file_lines[number - 1]
            for match in pattern.finditer(line):
                if term == "WILL" and match[0] != "WILL":
                    prefix = (file_lines[number - 2] if number > 1 else "") + line[:match.end()]
                    if not re.search(r"\b(?:the|my|your|our|their|its|free|human|of)\s+will$", prefix, re.I):
                        continue
                evidence = {"term": match[0], "line": number, "column": match.start() + 1}
                break
            if evidence:
                break
        if evidence:
            yield {"source": block["id"], "target": target, "type": "lexical_mention",
                   "basis": "lexical_candidate", "concept": term, "evidence": evidence,
                   "interpretation": "A term occurs here; no causal or canonical relationship is inferred."}


def _svg(nodes, edges, modules, chapters, summary):
    width, height, cx, cy = 1100, 1200, 550, 585
    ordered = sorted(modules.values(), key=lambda n: n["path"])
    axis = next((n for n in ordered if n["concept"] == "AXIS"), ordered[0] if ordered else None)
    ring = [n for n in ordered if n is not axis]
    positions = {}
    if axis:
        positions[axis["id"]] = (cx, cy)
    for i, node in enumerate(ring):
        angle = -math.pi / 2 + 2 * math.pi * i / max(1, len(ring))
        positions[node["id"]] = (cx + 370 * math.cos(angle), cy + 370 * math.sin(angle))
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">',
             '<title id="title">AXIOMA: an aggregate map of every reading chapter</title>',
             '<desc id="description">Chapter dots surround module hubs. Editorial chords are interpretations. The complete file and heading-section network is in graph.json. Positions are a composition, not measurements.</desc>',
             '<metadata>Copyright 2026 AXIOMA project. CC-BY-4.0. https://creativecommons.org/licenses/by/4.0/</metadata>',
             '<rect width="1100" height="1200" fill="#f6f2e8"/>',
             '<style>text{font-family:Georgia,serif;fill:#21493d}.small{font-family:Arial,sans-serif;font-size:12px}.module-label{font-family:Arial,sans-serif;font-size:11px;font-weight:bold;letter-spacing:1px}.chapter-dot{fill:#547c67;stroke:#f6f2e8;stroke-width:1}.module-hub{fill:#21493d;stroke:#f6f2e8;stroke-width:2}</style>',
             '<text x="550" y="55" text-anchor="middle" font-size="42" letter-spacing="8">AXIOMA</text>',
             '<text x="550" y="84" text-anchor="middle" font-size="17">The sphere as a connected reading form</text>',
             f'<text class="small" x="550" y="109" text-anchor="middle">{summary["reading_chapters"]} reading texts · {summary["modules"]} modules · {summary["blocks"]} addressable sections</text>',
             '<text class="small" x="550" y="130" text-anchor="middle">Aggregate view · complete block graph in graph.json · layout is not a measurement</text>',
             '<circle cx="550" cy="585" r="370" fill="none" stroke="#c9d4c6" stroke-width="1"/>']
    for edge in edges:
        if edge["type"] != "editorial_module_relation":
            continue
        x1, y1 = positions[edge["source"]]
        x2, y2 = positions[edge["target"]]
        parts.append(f'<path d="M{x1:.2f},{y1:.2f} Q{cx},{cy} {x2:.2f},{y2:.2f}" fill="none" stroke="#6e947b" stroke-opacity=".22" stroke-width="1.1"><title>{escape(edge["label"])}</title></path>')
    for module in ordered:
        x, y = positions[module["id"]]
        entries = chapters.get(module["id"], [])
        central = module is axis
        for i, entry in enumerate(entries):
            radius = 62 if central else 23 if i < 8 else 35 + 11 * ((i - 8) // 16)
            slot, slots = (i, len(entries)) if central else (i, min(8, len(entries))) if i < 8 else ((i - 8) % 16, min(16, len(entries) - 8))
            angle = -math.pi / 2 + 2 * math.pi * slot / max(1, slots)
            dx, dy = x + radius * math.cos(angle), y + radius * math.sin(angle)
            href = "../" + quote(entry["path"], safe="/")
            parts.append(f'<a href="{escape(href, quote=True)}"><circle class="chapter-dot" cx="{dx:.2f}" cy="{dy:.2f}" r="3.7"><title>{escape(entry["title"])} · {escape(entry["id"])}</title></circle></a>')
        parts.append(f'<a href="../{quote(module["path"], safe="/")}"><circle class="module-hub" cx="{x:.2f}" cy="{y:.2f}" r="{23 if central else 12}"><title>{escape(module["title"])}: {len(entries)} reading texts</title></circle></a>')
        if central:
            parts.append(f'<text x="{x}" y="{y + 4}" text-anchor="middle" fill="#f6f2e8" style="fill:#f6f2e8;font:10px Arial,sans-serif">AXIS</text>')
        else:
            angle = math.atan2(y - cy, x - cx)
            lx, ly = x + 56 * math.cos(angle), y + 56 * math.sin(angle)
            align = "middle" if abs(math.cos(angle)) < .15 else "start" if math.cos(angle) > 0 else "end"
            parts.append(f'<text class="module-label" x="{lx:.2f}" y="{ly:.2f}" text-anchor="{align}">{escape(module["concept"])}</text>')
    other = [n for n in nodes if n["kind"] not in {"block", "module", "literary", "interpretation"}]
    parts.extend(['<text class="small" x="550" y="1054" text-anchor="middle">Green dots: complete texts · dark hubs: modules · chords: editorial reading routes</text>',
                  f'<text class="small" x="550" y="1081" text-anchor="middle">Other release files: {len(other)} · each dot has a source link</text>'])
    for i, node in enumerate(other):
        col, row = i % 55, i // 55
        x, y = 226 + col * 12, 1102 + row * 13
        parts.append(f'<a href="../{quote(node["path"], safe="/")}"><circle class="support-dot" cx="{x}" cy="{y}" r="2.6" fill="#a4b3a1"><title>{escape(node["path"])}</title></circle></a>')
    parts.extend(['<text class="small" x="550" y="1160" text-anchor="middle">Files and sections are explicit. Meaning remains open to reading and review.</text>',
                  '<text x="550" y="1185" text-anchor="middle" font-size="14">Silentium Regit Omnia.</text>', '</svg>'])
    return "\n".join(parts) + "\n"


def _write(root, relative, text):
    target = safe(root, relative)
    if target.exists() and not target.is_file():
        raise InvalidProject("Graph output must be a regular file: " + relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=target.parent, prefix=".graph-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        safe(root, relative)
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def generate(root, catalog):
    """Write only graph.json and assets/corpus-graph.svg; return actual counts."""
    root = Path(root).resolve()
    records = catalog.get("documents") if isinstance(catalog, dict) else catalog
    if not isinstance(records, list):
        raise InvalidProject("Graph requires a catalog document list")
    paths = {p.relative_to(root).as_posix(): p for p in project_files(root)}
    for relative in SELF_DERIVED:
        target = safe(root, relative)
        if target.exists() and not target.is_file():
            raise InvalidProject("Graph output must be a file: " + relative)
        for parent in target.parents:
            if parent == root:
                break
            if parent.exists() and not parent.is_dir():
                raise InvalidProject("Graph output parent is not a directory: " + relative)
        paths[relative] = target
    by_path, documents, sections, parsed = {}, {}, [], {}
    for record in records:
        if not isinstance(record, dict) or not all(isinstance(record.get(k), str) for k in ("id", "path", "title", "kind", "sha256")):
            raise InvalidProject("Invalid graph catalog record")
        relative = record["path"]
        path = safe(root, relative, exists=True)
        if relative not in paths or path.suffix.casefold() != ".md":
            raise InvalidProject("Catalog path is outside the Markdown release set")
        if relative in by_path or record["id"] in documents:
            raise InvalidProject("Duplicate graph catalog path or ID")
        if digest(path) != record["sha256"]:
            raise InvalidProject("Changed graph source: " + relative)
        text = path.read_bytes().decode("utf-8")
        meta, _ = document(text)
        if any(meta.get(k) != record[k] for k in ("id", "title", "kind")):
            raise InvalidProject("Graph catalog metadata differs from its source")
        by_path[relative] = record
        documents[record["id"]] = record
        blocks, hierarchy, tokens, offset, lines = _sections(record, text)
        sections.extend(blocks)
        parsed[relative] = (blocks, hierarchy, tokens, offset, lines)
    if {p for p in paths if Path(p).suffix.casefold() == ".md"} != set(by_path):
        raise InvalidProject("Graph catalog does not cover every Markdown release file")
    if "README.md" not in by_path:
        raise InvalidProject("Graph requires the project README entry")
    nodes, edges = [], []
    for relative in sorted(paths):
        record = by_path.get(relative)
        node = ({k: record[k] for k in ("id", "title", "kind", "path", "sha256")}
                if record else {"id": "file:" + relative, "title": Path(relative).name,
                                "kind": "file", "path": relative})
        if relative not in SELF_DERIVED and not record:
            node["sha256"] = digest(paths[relative])
        if relative in SELF_DERIVED:
            node["derived"] = True
            node["digest_policy"] = "Excluded to avoid cyclic derived hashes"
        match = MODULE_PATH.fullmatch(relative)
        if match:
            node["module"] = match[1]
            node["concept"] = record["title"].upper()
        nodes.append(node)
    component_nodes, component_edges = [], []
    for relative, (blocks, _, _, _, lines) in parsed.items():
        spans, membership = compositions(by_path[relative], blocks, lines)
        component_nodes.extend(spans)
        component_edges.extend(membership)
    nodes.extend(sections)
    nodes.extend(component_nodes)
    edges.extend(component_edges)
    indexed = {n["id"]: n for n in nodes}
    if len(indexed) != len(nodes):
        raise InvalidProject("Graph node ID collision")
    file_ids = {n["path"]: n["id"] for n in nodes if n["kind"] != "block"}
    project = file_ids["README.md"]
    edges.extend({"source": project, "target": identifier, "type": "project_contains"}
                 for identifier in file_ids.values() if identifier != project)
    modules = {n["module"]: n for n in nodes if "module" in n}
    concepts = {n["concept"]: n["id"] for n in modules.values()}
    chapters = {n["id"]: [] for n in modules.values()}
    for record in records:
        if record["kind"] in {"literary", "interpretation"}:
            parent = Path(record["path"]).parent.name
            if parent not in modules:
                raise InvalidProject("Reading document has no declared module")
            hub = modules[parent]["id"]
            chapters[hub].append(record)
            edges.append({"source": hub, "target": record["id"], "type": "module_contains"})
    for entries in chapters.values():
        entries.sort(key=lambda r: r["path"])
        edges.extend({"source": a["id"], "target": b["id"], "type": "next_in_file_order",
                      "basis": "filename_order", "canonical_reading_order": False}
                     for a, b in zip(entries, entries[1:]))
    anchors = {(n["path"], n["anchor"]): n["id"] for n in sections if n["anchor"] is not None}
    for relative, (blocks, hierarchy, tokens, offset, lines) in parsed.items():
        edges.extend({"source": a, "target": b, "type": "contains_block"} for a, b in hierarchy)
        edges.extend({"source": a["id"], "target": b["id"], "type": "next_block_in_document",
                      "basis": "source_order", "canonical_reading_order": False}
                     for a, b in zip(blocks, blocks[1:]))
        for block in blocks:
            edges.extend(_lexical(block, lines, concepts))
        for token in tokens:
            if token.type != "inline" or not token.map:
                continue
            number = offset + token.map[0] + 1
            containing = [b for b in blocks if b["line_start"] <= number <= b["line_end"]]
            origin = min(containing, key=lambda b: b["line_end"] - b["line_start"])["id"] if containing else file_ids[relative]
            for child in token.children or []:
                target = child.attrGet("href") if child.type == "link_open" else child.attrGet("src") if child.type == "image" else None
                if not target:
                    continue
                url = urlsplit(target)
                if url.scheme in {"http", "https", "mailto"}:
                    continue
                if url.scheme or url.netloc:
                    raise InvalidProject("Unsupported graph link scheme")
                destination = safe(root, (Path(relative).parent / unquote(url.path)).as_posix() if url.path else relative)
                destination_path = destination.relative_to(root).as_posix()
                if destination_path not in file_ids:
                    raise InvalidProject("Graph link leaves the release set: " + target)
                identifier = file_ids[destination_path]
                if url.fragment and destination_path in by_path:
                    key = (destination_path, unquote(url.fragment))
                    if key not in anchors:
                        raise InvalidProject("Missing graph fragment: " + target)
                    identifier = anchors[key]
                edges.append({"source": origin, "target": identifier, "type": "local_markdown_link",
                              "href": target, "line": number})
    for left, right, label in RELATIONS:
        if left in concepts and right in concepts:
            if "docs/atlas.md" not in by_path:
                raise InvalidProject("Editorial module routes require docs/atlas.md")
            edges.append({"source": concepts[left], "target": concepts[right],
                          "type": "editorial_module_relation", "label": label,
                          "basis": "editorial_interpretation", "source_path": "docs/atlas.md"})
    lines_by_path = {p: parsed[p][4] for p in parsed}
    for relative in ("semantic-relations.json", "reading-relations.json"):
        if relative in paths:
            edges.extend(curated_relations(paths[relative], relative, indexed, anchors, lines_by_path,
                                           reviewed=relative == "reading-relations.json"))
    readings = section_records(sections, lines_by_path, documents)
    candidates = motif_candidates(readings)
    edges.extend(e for matches in candidates.values() for e in matches)
    curated_ids = {endpoint for e in edges if e["type"] in {
        "editorial_semantic_relation", "curated_section_reading"}
        for endpoint in (e["source"], e["target"]) if endpoint in readings}
    candidate_ids = {endpoint for matches in candidates.values() for e in matches
                     for endpoint in (e["source"], e["target"])}
    # Dedupe repeated source links, retaining distinct fragment/evidence records.
    edges = [json.loads(s) for s in sorted({json.dumps(e, sort_keys=True, ensure_ascii=False) for e in edges})]
    adjacency = {identifier: set() for identifier in indexed}
    for edge in edges:
        if edge["source"] not in indexed or edge["target"] not in indexed:
            raise InvalidProject("Dangling graph edge")
        adjacency[edge["source"]].add(edge["target"])
        adjacency[edge["target"]].add(edge["source"])
    visited, pending = set(), [project]
    while pending:
        current = pending.pop()
        if current not in visited:
            visited.add(current)
            pending.extend(adjacency[current] - visited)
    if visited != set(indexed) or any(not peers for peers in adjacency.values()):
        raise InvalidProject("Graph contains an orphan or disconnected component")
    edge_counts = dict(sorted(Counter(e["type"] for e in edges).items()))
    summary = {"files": len(file_ids), "markdown_documents": len(records), "modules": len(modules),
               "reading_chapters": sum(len(v) for v in chapters.values()),
               "literary_chapters": sum(r["kind"] == "literary" for r in records),
               "interpretation_chapters": sum(r["kind"] == "interpretation" for r in records),
               "reading_genres": dict(sorted(Counter(r["kind"] for r in records
                                                     if r["kind"] in {"literary", "interpretation"}).items())),
               "blocks": len(sections) + len(component_nodes), "whole_components": len(component_nodes),
               "nodes": len(nodes), "edges": len(edges), "connected_components": 1,
               "connectivity_mode": "Underlying undirected graph (weak connectivity)",
               "dangling_edges": 0, "orphan_nodes": 0,
               "lexical_mentions": edge_counts.get("lexical_mention", 0),
               "editorial_module_relations": edge_counts.get("editorial_module_relation", 0),
               "editorial_semantic_relations": edge_counts.get("editorial_semantic_relation", 0),
               "curated_section_readings": edge_counts.get("curated_section_reading", 0),
               "derived_section_candidates": edge_counts.get("section_reading_candidate", 0),
               "section_reading_coverage": {"eligible_sections": len(readings),
                    "with_curated_reading": len(curated_ids),
                    "with_derived_candidate": len(candidate_ids),
                    "without_curated_reading": len(set(readings) - curated_ids),
                    "without_curated_or_derived": len(set(readings) - curated_ids - candidate_ids),
                    "curator_acceptance": "Candidate coverage is not curator acceptance or complete semantics"}}
    graph = {"schema_version": "1.0.0", "project_id": project, "summary": summary,
             "edge_counts": edge_counts,
             "coverage": {"files": "All release files, including declared derived assets and the manifest",
                          "markdown_blocks": "Every heading section, explicit anchor and nonempty unheaded body",
                          "section_ranges": "Inclusive 1-based original file lines; nested sections overlap by design",
                          "lexical_evidence": "Own section lines only; WILL uses uppercase or a noun-phrase guard",
                          "meaning": "Lexical candidates and editorial interpretations, not proof of causality or canon",
                          "reading_routes": "Paired exact passages; curator readings and unreviewed derived motif candidates remain separate",
                          "whole_components": "Exact overlapping composition spans with all thirteen source parts; source links use real heading anchors",
                          "layout": "Aggregate composition, not a biological model or measurement"},
             "nodes": sorted(nodes, key=lambda n: n["id"]), "edges": edges}
    svg = _svg(nodes, edges, modules, chapters, summary)
    # All source, route and graph checks precede the first derived write.
    _write(root, OUTPUTS[0], json.dumps(graph, ensure_ascii=False, separators=(",", ":")) + "\n")
    _write(root, OUTPUTS[1], svg)
    return summary
