#!/usr/bin/env python3
"""Build docs/data.json for the IOL Knowledge Graph GitHub Pages visualization.

Includes all persons with at least one SERVED_IN/EDUCATED_AT/IN_COHORT edge,
plus all Place, EducationInstitution, and ExamCohort nodes.

Sources:
  - knowledge_graph_final.json          (full KG with Place/Edu QIDs)
  - iol_wikidata_review.json            (718 accepted Person QIDs)
  - wikidata_batches/person_search_all.json  (Person Wikidata metadata)
"""

import json
import os
from collections import Counter, defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

KG_PATH = os.path.join(BASE_DIR, "knowledge_graph_final.json")
PERSON_REVIEW_PATH = "/mnt/c/Users/jic823/Dropbox/2026/iol_wikidata_review.json"
PERSON_SEARCH_PATH = os.path.join(BASE_DIR, "wikidata_batches", "person_search_all.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "docs", "data.json")

CONNECTING_EDGE_TYPES = {"SERVED_IN", "EDUCATED_AT", "IN_COHORT"}
ALL_EDGE_TYPES = {"SERVED_IN", "EDUCATED_AT", "IN_COHORT", "MILITARY_SERVICE"}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_person_qid_map(review_data, search_data):
    """Build person_id -> {qid, description, death_date, label} from review + search."""
    search_by_id = {}
    for rec in search_data:
        if rec.get("match"):
            search_by_id[rec["person_id"]] = rec["match"]

    person_qids = {}
    for rec in review_data:
        if rec.get("decision") != "accepted" or not rec.get("qid"):
            continue
        pid = rec["person_id"]
        meta = search_by_id.get(pid, {})
        person_qids[pid] = {
            "qid": rec["qid"],
            "confidence": rec.get("confidence", "medium"),
            "description": meta.get("description", ""),
            "death_date": meta.get("death_date_wd"),
            "wikidata_label": meta.get("label", ""),
        }
    return person_qids


def main():
    print("Loading knowledge graph...")
    kg = load_json(KG_PATH)
    nodes_raw = kg["nodes"]
    rels_raw = kg["relationships"]

    print("Loading person review data...")
    review_data = load_json(PERSON_REVIEW_PATH)

    print("Loading person search metadata...")
    search_data = load_json(PERSON_SEARCH_PATH)

    person_qids = build_person_qid_map(review_data, search_data)
    print(f"  Accepted person QIDs: {len(person_qids)}")

    # Index nodes by id and label
    node_by_id = {n["id"]: n for n in nodes_raw}
    person_ids = {n["id"] for n in nodes_raw if n["label"] == "Person"}

    # Find connected persons: those with at least one SERVED_IN/EDUCATED_AT/IN_COHORT edge
    connected_persons = set()
    for rel in rels_raw:
        if rel["type"] in CONNECTING_EDGE_TYPES and rel["source_id"] in person_ids:
            connected_persons.add(rel["source_id"])
    print(f"  Connected persons: {len(connected_persons)}")

    # Build output nodes
    out_nodes = {}

    for n in nodes_raw:
        nid = n["id"]
        label = n["label"]

        if label == "Person" and nid in connected_persons:
            entry = {
                "id": nid,
                "label": "Person",
                "name": n.get("name", ""),
                "birth_date": n.get("birth_date"),
                "current_appointment": n.get("current_appointment"),
                "has_qid": nid in person_qids,
            }
            if nid in person_qids:
                pq = person_qids[nid]
                entry["wikidata_qid"] = pq["qid"]
                entry["wikidata_confidence"] = pq["confidence"]
                entry["wikidata_label"] = pq["wikidata_label"]
                entry["wikidata_description"] = pq["description"]
                entry["death_date"] = pq.get("death_date")
            out_nodes[nid] = entry

        elif label == "Place":
            has_qid = bool(n.get("wikidata_qid"))
            entry = {
                "id": nid,
                "label": "Place",
                "name": n.get("name", ""),
                "has_qid": has_qid,
            }
            if has_qid:
                entry["wikidata_qid"] = n["wikidata_qid"]
                entry["wikidata_confidence"] = n.get("wikidata_confidence")
                entry["wikidata_label"] = n.get("wikidata_label")
                entry["alt_names"] = n.get("alt_names", [])
            out_nodes[nid] = entry

        elif label == "EducationInstitution":
            has_qid = bool(n.get("wikidata_qid"))
            entry = {
                "id": nid,
                "label": "EducationInstitution",
                "name": n.get("name", ""),
                "has_qid": has_qid,
                "institution_type": n.get("institution_type"),
            }
            if has_qid:
                entry["wikidata_qid"] = n["wikidata_qid"]
                entry["wikidata_confidence"] = n.get("wikidata_confidence")
                entry["wikidata_label"] = n.get("wikidata_label")
                entry["alt_names"] = n.get("alt_names", [])
            out_nodes[nid] = entry

        elif label == "ExamCohort":
            out_nodes[nid] = {
                "id": nid,
                "label": "ExamCohort",
                "name": n.get("name", ""),
                "year": int(n["year"]) if n.get("year") else None,
                "service": n.get("service", ""),
                "has_qid": False,
            }

    type_counts = Counter(n["label"] for n in out_nodes.values())
    print(f"  Total nodes: {len(out_nodes)}")
    for t, c in sorted(type_counts.items()):
        print(f"    {t}: {c}")

    # Collect edges between included nodes
    included_ids = set(out_nodes.keys())
    edges = []
    edge_type_counts = Counter()
    for rel in rels_raw:
        if rel["type"] not in ALL_EDGE_TYPES:
            continue
        src, tgt = rel["source_id"], rel["target_id"]
        if src in included_ids and tgt in included_ids:
            edges.append({"source": src, "target": tgt, "type": rel["type"]})
            edge_type_counts[rel["type"]] += 1

    print(f"  Total edges: {len(edges)}")
    for t, c in sorted(edge_type_counts.items()):
        print(f"    {t}: {c}")

    # Compute degree
    degree = Counter()
    for e in edges:
        degree[e["source"]] += 1
        degree[e["target"]] += 1
    for nid in out_nodes:
        out_nodes[nid]["degree"] = degree.get(nid, 0)

    # Top places by person count
    place_person_count = defaultdict(int)
    for e in edges:
        if e["type"] == "SERVED_IN":
            tgt = out_nodes.get(e["target"])
            if tgt and tgt["label"] == "Place":
                place_person_count[e["target"]] += 1
    top_places = sorted(place_person_count.items(), key=lambda x: -x[1])[:20]
    top_places = [{"id": pid, "name": out_nodes[pid]["name"], "count": c} for pid, c in top_places]

    # Top institutions by person count
    edu_person_count = defaultdict(int)
    for e in edges:
        if e["type"] == "EDUCATED_AT":
            tgt = out_nodes.get(e["target"])
            if tgt and tgt["label"] == "EducationInstitution":
                edu_person_count[e["target"]] += 1
    top_institutions = sorted(edu_person_count.items(), key=lambda x: -x[1])[:20]
    top_institutions = [{"id": eid, "name": out_nodes[eid]["name"], "count": c} for eid, c in top_institutions]

    # Timeline: birth decade distribution of ALL included persons
    decade_counts = Counter()
    for n in out_nodes.values():
        if n["label"] == "Person" and n.get("birth_date"):
            try:
                year = int(n["birth_date"][:4])
                decade = (year // 10) * 10
                decade_counts[decade] += 1
            except (ValueError, TypeError):
                pass
    timeline = [{"decade": d, "count": c} for d, c in sorted(decade_counts.items())]

    # QID counts for stats
    qid_persons = sum(1 for n in out_nodes.values() if n["label"] == "Person" and n.get("has_qid"))
    qid_places = sum(1 for n in out_nodes.values() if n["label"] == "Place" and n.get("has_qid"))
    qid_edu = sum(1 for n in out_nodes.values() if n["label"] == "EducationInstitution" and n.get("has_qid"))

    output = {
        "stats": {
            "total_kg_nodes": len(nodes_raw),
            "total_kg_edges": len(rels_raw),
            "viz_nodes": len(out_nodes),
            "viz_edges": len(edges),
            "nodes_by_type": dict(type_counts),
            "edges_by_type": dict(edge_type_counts),
            "qid_counts": {
                "Person": qid_persons,
                "Place": qid_places,
                "EducationInstitution": qid_edu,
            },
        },
        "nodes": list(out_nodes.values()),
        "edges": edges,
        "top_places": top_places,
        "top_institutions": top_institutions,
        "timeline": timeline,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)

    print(f"\nWrote {OUTPUT_PATH}")
    print(f"  {len(output['nodes'])} nodes, {len(output['edges'])} edges")
    print(f"  QID: {qid_persons} persons, {qid_places} places, {qid_edu} edu")
    print(f"  File size: {os.path.getsize(OUTPUT_PATH) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
