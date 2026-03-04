#!/usr/bin/env python3
"""Prepare review_data.json for the Wikidata QID review interface.

Joins person_search_all.json (high+medium matches) with knowledge_graph_final.json
to build a single file with IOL career details + Wikidata match info.
"""

import json
import os
import sys

KG_FILE = "knowledge_graph_final.json"
SEARCH_FILE = "wikidata_batches/person_search_all.json"
OUTPUT_DIR = "review"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "review_data.json")


def build_person_context(person_id, nodes_by_id, rels_by_source):
    """Extract career details from KG relationships for a person."""
    rels = rels_by_source.get(person_id, [])

    education = []
    roles = []
    places = []
    honours = []
    qualifications = []
    service = None
    cohort = None
    organizations = []

    for r in rels:
        target = nodes_by_id.get(r["target_id"])
        if not target:
            continue
        rtype = r["type"]
        tname = target.get("name", "")

        if rtype == "EDUCATED_AT":
            education.append(tname)
        elif rtype == "APPOINTED":
            roles.append(tname)
        elif rtype == "SERVED_IN":
            places.append(tname)
        elif rtype == "AWARDED":
            honours.append(tname)
        elif rtype == "HOLDS":
            qualifications.append(tname)
        elif rtype == "MEMBER_OF":
            service = tname
        elif rtype == "IN_COHORT":
            cohort = tname
        elif rtype == "WORKED_FOR":
            organizations.append(tname)

    return {
        "education": education,
        "roles": roles,
        "places": sorted(set(places)),
        "honours": honours,
        "qualifications": qualifications,
        "service": service,
        "cohort": cohort,
        "organizations": sorted(set(organizations)),
    }


def main():
    print("Loading knowledge graph...")
    with open(KG_FILE) as f:
        kg = json.load(f)

    nodes_by_id = {n["id"]: n for n in kg["nodes"]}

    rels_by_source = {}
    for r in kg["relationships"]:
        sid = r["source_id"]
        if sid not in rels_by_source:
            rels_by_source[sid] = []
        rels_by_source[sid].append(r)

    print(f"  {len(kg['nodes']):,} nodes, {len(kg['relationships']):,} relationships")

    print("Loading person search results...")
    with open(SEARCH_FILE) as f:
        searches = json.load(f)

    # Filter to high + medium confidence only
    matches = [s for s in searches if s["confidence"] in ("high", "medium")]
    matches.sort(key=lambda x: (-x["match"]["score"], x["person_name"]))
    print(f"  {len(matches)} high+medium matches")

    print("Building review data...")
    review_data = []
    for entry in matches:
        pid = entry["person_id"]
        person_node = nodes_by_id.get(pid, {})
        context = build_person_context(pid, nodes_by_id, rels_by_source)
        match = entry["match"]

        review_data.append({
            "person_id": pid,
            "name": entry["person_name"],
            "birth_date": entry.get("birth_date"),
            "service_entry": person_node.get("service_entry_date"),
            "current_appointment": person_node.get("current_appointment"),
            "service": context["service"],
            "cohort": context["cohort"],
            "education": context["education"],
            "roles": context["roles"],
            "places": context["places"],
            "honours": context["honours"],
            "qualifications": context["qualifications"],
            "organizations": context["organizations"],
            "wikidata": {
                "qid": match["qid"],
                "label": match["label"],
                "description": match.get("description", ""),
                "birth_date": match.get("birth_date_wd"),
                "death_date": match.get("death_date_wd"),
                "url": f"https://www.wikidata.org/wiki/{match['qid']}",
            },
            "confidence": entry["confidence"],
            "score": match["score"],
            "reasons": match.get("reasons", []),
        })

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(review_data, f, indent=2)

    print(f"Wrote {len(review_data)} entries to {OUTPUT_FILE}")
    high = sum(1 for r in review_data if r["confidence"] == "high")
    med = sum(1 for r in review_data if r["confidence"] == "medium")
    print(f"  High: {high}, Medium: {med}")


if __name__ == "__main__":
    main()
