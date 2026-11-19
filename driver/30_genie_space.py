"""30 · Genie — TWO single-domain spaces (clean, no cross-table warnings).
The cross-domain experience is run with Genie One (workspace "Ask Genie"),
which also runs as the asking user's active role and enforces the ABAC FR filter.

Each space is find-or-create by title; CAN_RUN is granted to the owning domain
role plus the cross-domain role. Any legacy combined space is trashed.
Genie runs generated SQL AS THE ASKING USER, so UC grants + the ABAC row filter
apply per active role. CAN_RUN on a space does NOT grant data access.

Run: python driver/30_genie_space.py
"""
from __future__ import annotations
import json, sys, uuid
import _common as C

# Per-domain curated content ------------------------------------------------
CONTENT = {
    C.GEN_TABLE: {
        "sample": [
            "Compare the capacity factor of wind versus solar for each country.",
            "Show monthly generation and average availability by region.",
            "Which sites fall under the 85% availability maintenance rule?",
            "What is the utilization by technology?",
            "Summarize generation output by country.",
        ],
        "examples": [
            ("Compare the capacity factor of wind versus solar for each country.",
             f"SELECT `Asset Type`, `Country Name`, MEASURE(`Capacity Factor Pct`) AS capacity_factor_pct, MEASURE(`Total Generation MWh`) AS total_generation_mwh FROM {C.GEN_METRIC_VIEW} GROUP BY `Asset Type`, `Country Name` ORDER BY `Asset Type`, `Country Name`"),
            ("Show monthly generation and average availability by region.",
             f"SELECT `Operating Month`, `Region`, MEASURE(`Total Generation MWh`) AS total_generation_mwh, MEASURE(`Avg Availability Pct`) AS avg_availability_pct FROM {C.GEN_METRIC_VIEW} GROUP BY `Operating Month`, `Region` ORDER BY `Operating Month`, `Region`"),
            ("What is the total generation and capacity factor by country?",
             f"SELECT `Country Name`, MEASURE(`Total Generation MWh`) AS total_generation_mwh, MEASURE(`Capacity Factor Pct`) AS capacity_factor_pct FROM {C.GEN_METRIC_VIEW} GROUP BY `Country Name` ORDER BY `Country Name`"),
            ("What is the utilization by technology?",
             f"SELECT `Asset Type`, MEASURE(`Capacity Factor Pct`) AS capacity_factor_pct, MEASURE(`Total Generation MWh`) AS total_generation_mwh FROM {C.GEN_METRIC_VIEW} GROUP BY `Asset Type` ORDER BY `Asset Type`"),
            ("Show generation availability by site in France.",
             f"SELECT site_name, ROUND(AVG(availability_pct),1) AS avg_availability_pct FROM {C.GEN_TABLE} WHERE country_code='FR' GROUP BY site_name ORDER BY site_name"),
        ],
        "instructions": [
            "Synthetic renewable generation operations. generation_daily = generation (MWh) and availability_pct by site/country/day; asset_type is wind or solar. asset_reference is the sites dimension (nameplate capacity_mw, commissioned_year).",
            "Prefer the CERTIFIED metric view generation.generation_metrics for KPIs: query measures with MEASURE(), e.g. MEASURE(`Total Generation MWh`), MEASURE(`Capacity Factor Pct`), MEASURE(`Avg Availability Pct`). Capacity factor = generation / (nameplate capacity x 24h).",
            "Business rule (from the Discover Page 'Renewable generation metrics'): a site with availability below ~85% is flagged for maintenance review. Synonyms: 'utilization'/'load factor' = Capacity Factor; 'technology' = asset_type; 'output'/'energy produced' = Total Generation.",
            "country_code is FR, BE, NL, DE. All data is synthetic; not real data.",
            "Governed by Unity Catalog RBAC + ABAC; results reflect your active role. The metric view inherits the same geo row filter, so the cross-domain role sees FR and BE only.",
        ],
    },
    C.HEAT_TABLE: {
        "sample": [
            "Rank customer segments by total consumption and show each segment's share of the total.",
            "Show monthly heating consumption by customer segment.",
            "Which customer segment consumes the most?",
            "Summarize heating consumption by country.",
        ],
        "examples": [
            ("Summarize total heating consumption by country using the governed metric.",
             f"SELECT `Country Name`, MEASURE(`Total Consumption MWh`) AS total_consumption_mwh FROM {C.HEAT_METRIC_VIEW} GROUP BY `Country Name` ORDER BY `Country Name`"),
            ("Which customer segment consumes the most?",
             f"SELECT `Customer Segment`, MEASURE(`Total Consumption MWh`) AS total_consumption_mwh FROM {C.HEAT_METRIC_VIEW} GROUP BY `Customer Segment` ORDER BY total_consumption_mwh DESC"),
            ("Show heating consumption by month.",
             f"SELECT activity_date, ROUND(SUM(consumption_mwh),1) AS total_mwh FROM {C.HEAT_TABLE} GROUP BY activity_date ORDER BY activity_date"),
            ("Show monthly heating consumption by customer segment.",
             f"SELECT `Month`, `Customer Segment`, MEASURE(`Total Consumption MWh`) AS total_consumption_mwh FROM {C.HEAT_METRIC_VIEW} GROUP BY `Month`, `Customer Segment` ORDER BY `Month`, `Customer Segment`"),
        ],
        "instructions": [
            "Synthetic district-heating consumption. heating_consumption = consumption (MWh) by anonymized customer_segment/country/month.",
            "Prefer the CERTIFIED metric view heating.heating_metrics for KPIs: query measures with MEASURE(), e.g. MEASURE(`Total Consumption MWh`), MEASURE(`Avg Monthly Consumption MWh`).",
            "country_code is FR, BE, NL, DE. All data is synthetic; not real data.",
            "Governed by Unity Catalog RBAC + ABAC; results reflect your active role. The metric view inherits the same geo row filter, so the cross-domain role sees FR and BE only.",
        ],
    },
}


def serialized(table: str, metric_view: str | None = None) -> str:
    nid = lambda: uuid.uuid4().hex
    c = CONTENT[table]
    # data_sources carries the base table AND (for the ontology demo) the certified
    # metric view, so Genie can answer KPI questions from the governed measures.
    data_sources = {"tables": [{"identifier": table}]}
    if metric_view:
        data_sources["metric_views"] = [{"identifier": metric_view}]
    space = {
        "version": 2,
        "config": {"sample_questions": sorted(
            [{"id": nid(), "question": [q]} for q in c["sample"]], key=lambda x: x["id"])},
        "data_sources": data_sources,
        "instructions": {
            "text_instructions": [{"id": nid(), "content": c["instructions"]}],
            "example_question_sqls": sorted(
                [{"id": nid(), "question": [q], "sql": [s]} for q, s in c["examples"]], key=lambda x: x["id"]),
        },
    }
    return json.dumps(space)


def all_spaces(w):
    return getattr(w.genie.list_spaces(), "spaces", None) or []


def main() -> int:
    w = C.ws(); wid = C.warehouse_id(w)

    # Remove any legacy combined space
    for s in all_spaces(w):
        if (s.title or "") in C.LEGACY_GENIE_TITLES:
            w.genie.trash_space(space_id=s.space_id)
            print(f"trashed legacy space: {s.title} ({s.space_id})")

    existing = {(s.title or ""): s.space_id for s in all_spaces(w)}
    for spec in C.GENIE_SPACES:
        title, table, roles = spec["title"], spec["table"], spec["roles"]
        ser = serialized(table, spec.get("metric_view"))
        if title in existing:
            sid = existing[title]
            w.genie.update_space(space_id=sid, serialized_space=ser, title=title)
            print(f"updated: {title} ({sid})")
        else:
            sid = w.genie.create_space(warehouse_id=wid, serialized_space=ser, title=title,
                description="Synthetic governance demo (single domain).").space_id
            print(f"created: {title} ({sid})")
        body = {"access_control_list": [{"group_name": r, "permission_level": "CAN_RUN"} for r in roles]}
        w.api_client.do("PATCH", f"/api/2.0/permissions/genie/{sid}", body=body)
        print(f"   CAN_RUN -> {roles}")
        print(f"   open: {w.config.host}/genie/rooms/{sid}")

    print("\nGENIE: done. Cross-domain uses Genie One (workspace 'Ask Genie') — no object to create;"
          "\n       it runs as the active role and enforces the same ABAC FR filter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
