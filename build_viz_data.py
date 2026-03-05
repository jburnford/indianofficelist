#!/usr/bin/env python3
"""Build docs/data.json for the IOL Knowledge Graph GitHub Pages visualization.

Extracts the Wikidata-grounded subgraph: all nodes with QIDs and edges between them.

Sources:
  - knowledge_graph_final.json          (Place + EducationInstitution QIDs)
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


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_person_qid_map(review_data, search_data):
    """Build person_id -> {qid, description, death_date, label} from review + search."""
    # Index search results by person_id for metadata lookup
    search_by_id = {}
    for rec in search_data:
        if rec.get("match"):
            search_by_id[rec["person_id"]] = rec["match"]

    # Only accepted entries from review
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

    # Build person QID map
    person_qids = build_person_qid_map(review_data, search_data)
    print(f"  Accepted person QIDs: {len(person_qids)}")

    # Index all nodes by id
    node_by_id = {n["id"]: n for n in nodes_raw}

    # Collect all QID nodes
    qid_nodes = {}
    for n in nodes_raw:
        nid = n["id"]
        label = n["label"]

        if label == "Person" and nid in person_qids:
            pq = person_qids[nid]
            qid_nodes[nid] = {
                "id": nid,
                "label": label,
                "name": n.get("name", ""),
                "wikidata_qid": pq["qid"],
                "wikidata_confidence": pq["confidence"],
                "wikidata_label": pq["wikidata_label"],
                "wikidata_description": pq["description"],
                "birth_date": n.get("birth_date"),
                "death_date": pq.get("death_date"),
                "current_appointment": n.get("current_appointment"),
            }
        elif label in ("Place", "EducationInstitution") and n.get("wikidata_qid"):
            entry = {
                "id": nid,
                "label": label,
                "name": n.get("name", ""),
                "wikidata_qid": n["wikidata_qid"],
                "wikidata_confidence": n.get("wikidata_confidence"),
                "wikidata_label": n.get("wikidata_label"),
                "alt_names": n.get("alt_names", []),
            }
            if label == "EducationInstitution":
                entry["institution_type"] = n.get("institution_type")
            qid_nodes[nid] = entry

    print(f"  Total QID nodes: {len(qid_nodes)}")
    type_counts = Counter(n["label"] for n in qid_nodes.values())
    for t, c in sorted(type_counts.items()):
        print(f"    {t}: {c}")

    # Collect edges between QID nodes
    qid_ids = set(qid_nodes.keys())
    edges = []
    edge_type_counts = Counter()
    for rel in rels_raw:
        src = rel["source_id"]
        tgt = rel["target_id"]
        if src in qid_ids and tgt in qid_ids:
            edges.append({
                "source": src,
                "target": tgt,
                "type": rel["type"],
            })
            edge_type_counts[rel["type"]] += 1

    print(f"  Edges between QID nodes: {len(edges)}")
    for t, c in sorted(edge_type_counts.items()):
        print(f"    {t}: {c}")

    # Compute degree for each QID node
    degree = Counter()
    for e in edges:
        degree[e["source"]] += 1
        degree[e["target"]] += 1
    for nid in qid_nodes:
        qid_nodes[nid]["degree"] = degree.get(nid, 0)

    # Top places by connected QID person count
    place_person_count = defaultdict(int)
    for e in edges:
        if e["type"] == "SERVED_IN":
            tgt_node = qid_nodes.get(e["target"])
            if tgt_node and tgt_node["label"] == "Place":
                place_person_count[e["target"]] += 1
    top_places = sorted(place_person_count.items(), key=lambda x: -x[1])[:20]
    top_places = [{"id": pid, "name": qid_nodes[pid]["name"], "count": c} for pid, c in top_places]

    # Top institutions by connected QID person count
    edu_person_count = defaultdict(int)
    for e in edges:
        if e["type"] == "EDUCATED_AT":
            tgt_node = qid_nodes.get(e["target"])
            if tgt_node and tgt_node["label"] == "EducationInstitution":
                edu_person_count[e["target"]] += 1
    top_institutions = sorted(edu_person_count.items(), key=lambda x: -x[1])[:20]
    top_institutions = [{"id": eid, "name": qid_nodes[eid]["name"], "count": c} for eid, c in top_institutions]

    # Timeline: birth decade distribution of QID persons
    decade_counts = Counter()
    for n in qid_nodes.values():
        if n["label"] == "Person" and n.get("birth_date"):
            try:
                year = int(n["birth_date"][:4])
                decade = (year // 10) * 10
                decade_counts[decade] += 1
            except (ValueError, TypeError):
                pass
    timeline = [{"decade": d, "count": c} for d, c in sorted(decade_counts.items())]

    # Build output
    output = {
        "stats": {
            "total_kg_nodes": len(nodes_raw),
            "total_kg_edges": len(rels_raw),
            "qid_nodes": len(qid_nodes),
            "qid_edges": len(edges),
            "nodes_by_type": dict(type_counts),
            "edges_by_type": dict(edge_type_counts),
        },
        "nodes": list(qid_nodes.values()),
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
    print(f"  File size: {os.path.getsize(OUTPUT_PATH) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
