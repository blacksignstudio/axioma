"""Source-grounded reading candidates, kept separate from curator readings.

Shared vocabulary is an inspectable search lead, never a validated philosophical
relation. The generator leaves unmatched sections unresolved rather than adding
generic module edges to manufacture coverage.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import math
import re
import json

from .cli import InvalidProject


WORD = re.compile(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)?")
STOP = set("""a an and are as at be been being but by can cannot could did do does
each for from had has have he her here hers him his how i if in into is it its
may me more most must my no nor not of on one only or other our out own same
she so than that the their them then there these they this those through to too
under until up us very was we were what when where which who why will with
without would you your itself themselves ourselves something nothing everything
axioma structure form field pattern signal memory archive echo presence silence
""".split())


def terms(text):
    return {m[0].casefold() for m in WORD.finditer(text)
            if len(m[0]) > 3 and m[0].casefold() not in STOP}


def section_records(blocks, lines_by_path, documents):
    """Own bodies of literary sections; parent ranges never duplicate children."""
    result = {}
    for node in blocks:
        parent = documents.get(node.get("document_id"), {})
        if (node.get("block_type") != "content" or parent.get("kind") not in {"literary", "interpretation"}
                or node.get("title", "").casefold() == "orientation"):
            continue
        lines = lines_by_path[node["path"]]
        start, end = node["own_line_start"], node["own_line_end"]
        first = start + 1 if lines[start - 1].lstrip().startswith("#") else start
        body = "".join(lines[first - 1:end])
        if not body.strip():
            continue
        parts = node["path"].split("/")
        paragraphs = []
        cursor = 0
        for raw in re.split(r"\n[ \t]*\n", body):
            text = raw.strip()
            pos = body.find(text, cursor) if text else cursor
            cursor = pos + len(text)
            if text and terms(text):
                paragraphs.append({"text": text, "offset": pos, "terms": terms(text)})
        result[node["id"]] = {
            "id": node["id"], "node": node, "path": node["path"],
            "anchor": node.get("anchor"), "title": node["title"],
            "module": parts[1] if len(parts) > 2 and parts[0] == "corpus" else None,
            "document_id": node["document_id"], "source_sha256": parent.get("sha256"),
            "body": body, "body_line_start": first, "body_line_end": end,
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "words": len(WORD.findall(body)), "terms": terms(body), "paragraphs": paragraphs}
    return result


def _witness(section, paragraph, shared, max_words=48):
    text = paragraph["text"]
    words = list(re.finditer(r"\S+", text))
    offset = 0
    if len(words) > max_words:
        choices = []
        for i in range(len(words) - max_words + 1):
            a, b = words[i].start(), words[i + max_words - 1].end()
            choices.append((len(terms(text[a:b]) & shared), -i, a, b))
        _, _, a, b = max(choices)
        offset, text = a, text[a:b]
    if len(terms(text) & shared) < 2:
        return None
    pos = paragraph["offset"] + offset
    first = section["body_line_start"] + section["body"].count("\n", 0, pos)
    return {"path": section["path"], "anchor": section["anchor"],
            "block_id": section["id"], "excerpt": text,
            "line_start": first, "line_end": first + text.count("\n"),
            "source_sha256": section["source_sha256"]}


def motif_candidates(records, identifiers=None, *, max_neighbors=2, cross_module=True):
    """Find distinctive paragraph motifs with exact witnesses at both ends.

    Scores describe rarity of shared words, not confidence in a meaning. At
    least two non-generic terms must occur together in both quoted paragraphs.
    No match is a valid result. Candidate selection is deterministic.
    """
    if isinstance(max_neighbors, bool) or not isinstance(max_neighbors, int) or not 1 <= max_neighbors <= 5:
        raise InvalidProject("Reading candidate limit must be from 1 to 5")
    ids = sorted(records if identifiers is None else identifiers)
    if any(i not in records for i in ids):
        raise InvalidProject("Unknown reading candidate source ID")
    postings = defaultdict(set)
    for identifier, record in records.items():
        for term in record["terms"]:
            postings[term].add(identifier)
    cap = max(12, int(len(records) * .18))
    weights = {t: math.log((len(records) + 1) / (len(v) + 1)) + 1
               for t, v in postings.items() if len(v) <= cap}
    result = {}
    for identifier in ids:
        source = records[identifier]
        scores = Counter()
        for term in sorted(source["terms"] & weights.keys()):
            for target_id in postings[term]:
                target = records[target_id]
                if (target["document_id"] == source["document_id"] or
                        cross_module and target["module"] == source["module"]):
                    continue
                scores[target_id] += weights[term] ** 2
        matches = []
        for target_id in sorted(scores, key=lambda i: (-scores[i], i))[:40]:
            target = records[target_id]
            shared = source["terms"] & target["terms"] & weights.keys()
            if len(shared) < 2:
                continue
            pairs = []
            for a in source["paragraphs"]:
                for b in target["paragraphs"]:
                    common = a["terms"] & b["terms"] & shared
                    if len(common) >= 2:
                        score = sum(weights[t] ** 2 for t in sorted(common))
                        pairs.append((score, a["offset"], b["offset"], a, b, common))
            if not pairs:
                continue
            pairs.sort(key=lambda p: (-p[0], p[1], p[2]))
            score, _, _, a, b, common = pairs[0]
            witnesses = [_witness(source, a, common), _witness(target, b, common)]
            if any(w is None for w in witnesses):
                continue
            matches.append({"source": identifier, "target": target_id,
                            "type": "section_reading_candidate",
                            "relation": "shared_motif_candidate",
                            "basis": "derived_distinctive_vocabulary_candidate",
                            "status": "unreviewed_candidate",
                            "confidence": "candidate_only_not_a_probability",
                            "score": round(score, 6), "shared_terms": sorted(common),
                            "rationale": "These exact passages share distinctive vocabulary; a curator must assess the proposed reading.",
                            "evidence": witnesses})
            if len(matches) == max_neighbors:
                break
        result[identifier] = matches
    return result


def curated_relations(path, relative, indexed, anchors, lines_by_path, *, reviewed=False):
    """Validate paired exact witnesses; acceptance remains an editorial reading.

    Source and target must be actual sections. An unrelated quotation elsewhere
    in the corpus cannot stand in for either endpoint. Curator files additionally
    declare an actual reader and explicit review status, never inferred by code.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise InvalidProject("Cannot read editorial readings: " + relative) from error
    if not isinstance(data, dict) or not isinstance(data.get("relations"), list):
        raise InvalidProject("Editorial readings require a relation list")
    allowed = {"supports", "contrasts_with", "constrains"}
    if reviewed:
        allowed |= {"shares_motif", "complements", "develops", "local_context"}
    edges = []
    for relation in data["relations"]:
        if not isinstance(relation, dict):
            raise InvalidProject("Editorial semantic relation must be an object")
        source, target = relation.get("source_id"), relation.get("target_id")
        if (source not in indexed or target not in indexed or
                any(indexed[i].get("kind") != "block" for i in (source, target)) or source == target):
            raise InvalidProject("Editorial semantic relation requires distinct known source and target sections")
        if relation.get("relation") not in allowed:
            raise InvalidProject("Unknown editorial semantic relation type")
        rationale = relation.get("rationale")
        evidence_items = relation.get("evidence")
        if not isinstance(rationale, str) or not rationale.strip():
            raise InvalidProject("Editorial semantic relation requires a nonempty rationale")
        if not isinstance(evidence_items, list) or not evidence_items:
            raise InvalidProject("Editorial semantic relation requires evidence")
        if reviewed and (relation.get("review_status") != "curator_reviewed" or
                         not isinstance(relation.get("reviewed_by"), str) or not relation["reviewed_by"].strip()):
            raise InvalidProject("Curator reading requires curator_reviewed and an actual reviewed_by")
        witnessed, evidence = set(), []
        for item in evidence_items:
            if not isinstance(item, dict):
                raise InvalidProject("Editorial semantic evidence must be an object")
            key = (item.get("path"), item.get("anchor"))
            if not all(isinstance(value, str) for value in key) or key not in anchors:
                raise InvalidProject("Editorial semantic evidence has an unknown anchor")
            excerpt = item.get("excerpt")
            if not isinstance(excerpt, str) or not excerpt.strip():
                raise InvalidProject("Editorial semantic evidence requires a nonempty excerpt")
            block_id = anchors[key]
            block = indexed[block_id]
            lines = lines_by_path[key[0]]
            actual = "".join(lines[block["line_start"] - 1:block["line_end"]])
            if excerpt not in actual:
                raise InvalidProject("Stale editorial semantic excerpt: " + key[0] + "#" + key[1])
            if block_id in (source, target):
                witnessed.add(block_id)
            first = block["line_start"] + actual.count("\n", 0, actual.index(excerpt))
            document = indexed[block["document_id"]]
            evidence.append({**item, "block_id": block_id, "line_start": first,
                             "line_end": first + excerpt.count("\n"), "source_sha256": document["sha256"]})
        if witnessed != {source, target}:
            raise InvalidProject("Editorial reading requires exact evidence at both endpoint sections")
        edge = {"source": source, "target": target,
                "type": "curated_section_reading" if reviewed else "editorial_semantic_relation",
                "relation": relation["relation"], "rationale": rationale, "evidence": evidence,
                "basis": "curator_interpretation" if reviewed else "editorial_interpretation",
                "status": "curator_reviewed" if reviewed else data.get("status", "proposed"),
                "confidence": "editorial_reading_not_empirical_causality", "source_path": relative}
        if reviewed:
            edge["reviewed_by"] = relation["reviewed_by"]
        edges.append(edge)
    return edges
