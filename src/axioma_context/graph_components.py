"""Whole source compositions spanning sibling Markdown sections."""
from __future__ import annotations

import hashlib
import re

from .cli import InvalidProject


ROMANS = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII")
NAME = re.compile(r"^TRANSMISSIO\s*(?:∞\s*)?(AXIOMA|HUMANA)$", re.I)
PART = re.compile(r"^([IVX]+)\s*(?:[—–.:\-]|$)")


def compositions(record, blocks, lines):
    """Add spans without changing heading IDs or duplicating lexical extraction.

    A component ends at the next component or next equal/higher ancestor after
    its introduction. Its thirteen Roman parts are source headings, not inferred
    concepts. The public URL always uses the existing introduction anchor.
    """
    headings = [b for b in blocks if b.get("anchor_kind") == "github_heading"]
    result, edges = [], []
    for index, intro in enumerate(headings):
        match = NAME.fullmatch(" ".join(intro["title"].split()))
        if not match:
            continue
        following = headings[index + 1:]
        boundary = next((b for b in following if NAME.fullmatch(" ".join(b["title"].split()))
                         or b["heading_level"] < intro["heading_level"]), None)
        end = boundary["line_start"] - 1 if boundary else len(lines)
        members = [b for b in headings[index:] if intro["line_start"] <= b["line_start"] <= end]
        parts = [(PART.match(b["title"]), b) for b in members[1:]]
        parts = [(m[1], b) for m, b in parts if m]
        # An outline can repeat the component title before the actual text.
        if not parts and boundary and NAME.fullmatch(" ".join(boundary["title"].split())):
            continue
        if tuple(roman for roman, _ in parts) != ROMANS:
            raise InvalidProject("Whole Transmissio component requires ordered parts I–XIII: " + intro["id"])
        key = "transmissio-" + match[1].casefold()
        identifier = record["id"] + "#~component-" + key
        node = {"id": identifier, "kind": "block", "block_type": "component",
                "title": intro["title"], "document_id": record["id"], "path": record["path"],
                "anchor": None, "anchor_kind": "line_range", "source_anchor": intro["anchor"],
                "heading_level": 0, "line_start": intro["line_start"], "line_end": end,
                "own_line_start": intro["line_start"], "own_line_end": end,
                "content_sha256": hashlib.sha256("".join(lines[intro["line_start"] - 1:end]).encode("utf-8")).hexdigest(),
                "component_key": key, "intro_id": intro["id"],
                "part_ids": [b["id"] for _, b in parts], "member_ids": [b["id"] for b in members]}
        intro["whole_component_id"] = identifier
        intro["span_role"] = "component_intro"
        result.append(node)
        edges.append({"source": record["id"], "target": identifier, "type": "contains_component",
                      "basis": "source_composition"})
        part_ids = set(node["part_ids"])
        for member in members:
            edges.append({"source": identifier, "target": member["id"], "type": "component_contains",
                          "basis": "source_composition", "role": "intro" if member is intro else
                          "part" if member["id"] in part_ids else "source_closing_or_subsection"})
    return result, edges
