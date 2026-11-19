"""50 · AI/BI (Lakeview) dashboard on the CERTIFIED METRIC VIEWS.

Builds one governed KPI dashboard spanning both domains, sourced entirely from
the metric views generation.generation_metrics + heating.heating_metrics (queried
with MEASURE()). This is the "ontology" payoff: the SAME certified measures power
the dashboard AND Genie One, and publishing feeds the dashboard's queries into the
Genie ontology as learned knowledge.

GOVERNANCE NOTE: the dashboard is published with INDIVIDUAL data permission
(embed_credentials=False / run-as-viewer), so each viewer runs the queries with
their OWN Unity Catalog permissions. The metric views inherit the base-table ABAC
row filter, so the cross-domain consumer sees FR+BE KPIs in the dashboard itself —
governance carries into AI/BI, not just Genie/SQL. (A single-domain role sees its
own domain; the other domain's tiles are empty — no grant on that metric view —
the expected least-privilege outcome. The cross-domain role, with SELECT on both
metric views, is the intended full-dashboard audience.)

Run: python driver/50_dashboard.py     (after driver/20 has created the metric views)
"""
from __future__ import annotations
import json, sys
import _common as C

# Brand palette (light/dark pairs where the theme expects them).
VIZ = ["#00BDFF", "#003D7C", "#E5005B", "#FF7A59", "#00C389", "#001E62", "#6B7B8C"]
PCT = {"type": "number-plain", "decimalPlaces": {"type": "max", "places": 1}}
MWH = {"type": "number-plain", "decimalPlaces": {"type": "max", "places": 0}}


def _counter(name, title, dataset, field, fmt=None, template=None):
    value = {"fieldName": field, "displayName": title}
    if fmt:
        value["format"] = fmt
    if template:
        value["formatTemplate"] = template
    return {
        "name": name,
        "queries": [{"name": "main_query", "query": {
            "datasetName": dataset,
            "fields": [{"name": field, "expression": f"`{field}`"}],
            "disaggregated": True}}],
        "spec": {"version": 2, "widgetType": "counter",
                 "encodings": {"value": value},
                 "frame": {"showTitle": True, "title": title}},
    }


def _bar(name, title, dataset, dim, dim_label, measure, measure_label, mfmt=None):
    y = {"fieldName": measure, "scale": {"type": "quantitative"}, "displayName": measure_label}
    if mfmt:
        y["format"] = mfmt
    return {
        "name": name,
        "queries": [{"name": "main_query", "query": {
            "datasetName": dataset,
            "fields": [{"name": dim, "expression": f"`{dim}`"},
                       {"name": measure, "expression": f"`{measure}`"}],
            "disaggregated": True}}],
        "spec": {"version": 3, "widgetType": "bar",
                 "encodings": {"x": {"fieldName": dim, "scale": {"type": "categorical"}, "displayName": dim_label},
                               "y": y},
                 "frame": {"showTitle": True, "title": title}},
    }


def _pie(name, title, dataset, dim, dim_label, measure, measure_label):
    return {
        "name": name,
        "queries": [{"name": "main_query", "query": {
            "datasetName": dataset,
            "fields": [{"name": dim, "expression": f"`{dim}`"},
                       {"name": measure, "expression": f"`{measure}`"}],
            "disaggregated": True}}],
        "spec": {"version": 3, "widgetType": "pie",
                 "encodings": {"angle": {"fieldName": measure, "scale": {"type": "quantitative"}, "displayName": measure_label},
                               "color": {"fieldName": dim, "scale": {"type": "categorical"}, "displayName": dim_label},
                               "label": {"show": True}},
                 "frame": {"showTitle": True, "title": title}},
    }


def _lay(widget, x, y, w, h):
    return {"widget": widget, "position": {"x": x, "y": y, "width": w, "height": h}}


def build_dashboard_json() -> str:
    """Serialized dashboard (fully-qualified metric-view names via _common.CATALOG)."""
    gmv, hmv = C.GEN_METRIC_VIEW, C.HEAT_METRIC_VIEW
    datasets = [
        {"name": "ds_gen_kpi", "displayName": "Generation KPIs", "queryLines": [
            "SELECT MEASURE(`Total Generation MWh`) AS total_generation, ",
            "MEASURE(`Capacity Factor Pct`) AS capacity_factor, ",
            "MEASURE(`Avg Availability Pct`) AS avg_availability ",
            f"FROM {gmv}"]},
        {"name": "ds_gen_by_country", "displayName": "Generation by country", "queryLines": [
            "SELECT `Country Name` AS country, MEASURE(`Total Generation MWh`) AS gen_mwh ",
            f"FROM {gmv} GROUP BY `Country Name` ORDER BY gen_mwh DESC"]},
        {"name": "ds_gen_by_type", "displayName": "Capacity factor by asset type", "queryLines": [
            "SELECT `Asset Type` AS asset_type, MEASURE(`Capacity Factor Pct`) AS capacity_factor ",
            f"FROM {gmv} GROUP BY `Asset Type` ORDER BY asset_type"]},
        {"name": "ds_heat_kpi", "displayName": "Heating KPIs", "queryLines": [
            "SELECT MEASURE(`Total Consumption MWh`) AS total_consumption ",
            f"FROM {hmv}"]},
        {"name": "ds_heat_by_country", "displayName": "Consumption by country", "queryLines": [
            "SELECT `Country Name` AS country, MEASURE(`Total Consumption MWh`) AS cons_mwh ",
            f"FROM {hmv} GROUP BY `Country Name` ORDER BY cons_mwh DESC"]},
        {"name": "ds_heat_by_segment", "displayName": "Consumption by segment", "queryLines": [
            "SELECT `Customer Segment` AS segment, MEASURE(`Total Consumption MWh`) AS cons_mwh ",
            f"FROM {hmv} GROUP BY `Customer Segment` ORDER BY cons_mwh DESC"]},
    ]

    header = {"name": "header", "multilineTextboxSpec": {"lines": [
        "## Energy KPIs — Governed by Unity Catalog\n",
        "\n",
        "Synthetic demo. Every number here comes from the **certified metric views** "
        "`generation.generation_metrics` and `heating.heating_metrics` — the same governed KPIs "
        "**Genie One** answers from. ABAC row/column security lives on the base tables, so asking "
        "these measures as a domain role in Genie returns only that role's entitled countries "
        "(the cross-domain role sees FR + BE)."]}}

    layout = [
        _lay(header, 0, 0, 12, 3),
        _lay(_counter("kpi-total-gen", "Total Generation", "ds_gen_kpi", "total_generation", MWH, "{{ @formatted }} MWh"), 0, 3, 3, 3),
        _lay(_counter("kpi-capacity-factor", "Capacity Factor", "ds_gen_kpi", "capacity_factor", PCT, "{{ @formatted }}%"), 3, 3, 3, 3),
        _lay(_counter("kpi-availability", "Avg Availability", "ds_gen_kpi", "avg_availability", PCT, "{{ @formatted }}%"), 6, 3, 3, 3),
        _lay(_counter("kpi-total-consumption", "Total Heating Consumption", "ds_heat_kpi", "total_consumption", MWH, "{{ @formatted }} MWh"), 9, 3, 3, 3),
        _lay(_bar("gen-by-country", "Generation by country (MWh)", "ds_gen_by_country", "country", "Country", "gen_mwh", "Generation (MWh)", MWH), 0, 6, 6, 6),
        _lay(_bar("cf-by-type", "Capacity factor by asset type (%)", "ds_gen_by_type", "asset_type", "Asset type", "capacity_factor", "Capacity Factor (%)", PCT), 6, 6, 6, 6),
        _lay(_bar("cons-by-country", "Heating consumption by country (MWh)", "ds_heat_by_country", "country", "Country", "cons_mwh", "Consumption (MWh)", MWH), 0, 12, 6, 6),
        _lay(_pie("cons-by-segment", "Heating consumption by segment", "ds_heat_by_segment", "segment", "Customer segment", "cons_mwh", "Consumption (MWh)"), 6, 12, 6, 6),
    ]

    theme = {
        "canvasBackgroundColor": {"light": "#FCFCFC", "dark": "#0B1C2C"},
        "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#0F2238"},
        "widgetBorderColor": {"light": "#FFFFFF", "dark": "#0F2238"},
        "fontColor": {"light": "#001E62", "dark": "#E8ECF0"},
        "selectionColor": {"light": "#00BDFF", "dark": "#00BDFF"},
        "visualizationColors": VIZ,
        "widgetHeaderAlignment": "LEFT",
    }

    dash = {
        "datasets": datasets,
        "pages": [{"name": "kpis", "displayName": "KPIs", "pageType": "PAGE_TYPE_CANVAS",
                   "layoutVersion": "GRID_V1", "layout": layout}],
        "uiSettings": {"theme": theme},
    }
    return json.dumps(dash)


def main() -> int:
    from databricks.sdk.service.dashboards import Dashboard
    w = C.ws(); wid = C.warehouse_id(w)
    me = w.current_user.me().user_name
    parent = f"/Workspace/Users/{me}/uc-governance-demo"
    try:
        w.workspace.mkdirs(parent)
    except Exception:
        pass
    js = build_dashboard_json()

    existing = None
    for d in w.lakeview.list():
        if d.display_name == C.DASHBOARD_NAME and (d.lifecycle_state is None or d.lifecycle_state.value != "TRASHED"):
            existing = d
            break

    if existing:
        did = existing.dashboard_id
        w.lakeview.update(did, dashboard=Dashboard(display_name=C.DASHBOARD_NAME, warehouse_id=wid, serialized_dashboard=js),
                          dataset_catalog=C.CATALOG, dataset_schema="generation")
        print(f"updated dashboard: {C.DASHBOARD_NAME} ({did})")
    else:
        d = w.lakeview.create(dashboard=Dashboard(display_name=C.DASHBOARD_NAME, warehouse_id=wid,
                                                  serialized_dashboard=js, parent_path=parent),
                              dataset_catalog=C.CATALOG, dataset_schema="generation")
        did = d.dashboard_id
        print(f"created dashboard: {C.DASHBOARD_NAME} ({did})")

    # Publish with INDIVIDUAL data permission (run-as-viewer, embed_credentials=False):
    # each viewer's own UC permissions run the queries, so the ABAC filter applies in the
    # dashboard too (cross-domain consumer sees FR+BE; a domain role sees only its domain).
    w.lakeview.publish(did, embed_credentials=False, warehouse_id=wid)
    print("published (individual data permission — queries run as each viewer)")

    # Best-effort: let the demo roles VIEW the dashboard (consumer surface).
    try:
        acl = [{"group_name": r, "permission_level": "CAN_READ"} for r in C.ROLE_GROUPS]
        w.api_client.do("PATCH", f"/api/2.0/permissions/dashboards/{did}",
                        body={"access_control_list": acl})
        print(f"   CAN_READ -> {C.ROLE_GROUPS}")
    except Exception as e:
        print("   (permissions skipped:", repr(e)[:100], ")")

    print(f"\n   draft:     {w.config.host}/sql/dashboardsv3/{did}")
    print(f"   published: {w.config.host}/sql/dashboardsv3/{did}/published")
    print("\nDASHBOARD: done. Same certified metric views also power Genie One (ask a KPI as a role).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
