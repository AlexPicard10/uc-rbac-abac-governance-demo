"""40 · Validate. Automated metadata/evidence checks (run as admin — no role
tokens needed), then prints the interactive per-role outcome runbook.

Run: python driver/40_validate.py
"""
from __future__ import annotations
import sys
import _common as C

ASSUMER = "roles/group.assumer"
results = []


def check(name, cond, detail=""):
    results.append((bool(cond), name, detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def main() -> int:
    w = C.ws(); a = C.acct(); wid = C.warehouse_id(w); acc = a.config.account_id
    print("== Identity ==")
    names = {g.display_name for g in a.groups.list(attributes="id,displayName")}
    for g in C.MEMBER_GROUPS + C.ROLE_GROUPS:
        check(f"group exists: {g}", g in names)
    for member, role in C.PAIRS:
        rid = C.group_id(a, role)
        rs = a.access_control.get_rule_set(name=f"accounts/{acc}/groups/{rid}/ruleSets/default", etag="")
        wired = any(x.role == ASSUMER and f"groups/{member}" in (x.principals or []) for x in (rs.grant_rules or []))
        check(f"ASSUME wired: {member} -> {role}", wired)

    # least-privilege workspace entitlement per role (SQL access vs Consumer access)
    wscim = {g.get("displayName"): [e.get("value") for e in g.get("entitlements", [])]
             for g in w.api_client.do("GET", "/api/2.0/preview/scim/v2/Groups",
                                      query={"count": "500"}).get("Resources", [])}
    for role in C.ROLE_GROUPS:
        check(f"{role} entitlement = {C.ROLE_ENTITLEMENTS[role]}",
              set(wscim.get(role, [])) == set(C.ROLE_ENTITLEMENTS[role]))

    print("== Governance ==")
    ok, rows = C.run_sql(w, "SELECT schema_name, table_name FROM "
                            f"{C.CATALOG}.information_schema.column_tags WHERE tag_name='{C.GOVERNED_TAG}'", wid)
    tagged = {f"{r[0]}.{r[1]}" for r in rows} if ok else set()
    check("governed tag on generation.country_code", "generation.generation_daily" in tagged)
    check("governed tag on heating.country_code", "heating.heating_consumption" in tagged)
    for t in (C.GEN_TABLE, C.HEAT_TABLE):
        ok, rows = C.run_sql(w, f"SHOW EFFECTIVE POLICIES ON TABLE {t}", wid)
        has = ok and any(r[0] == C.POLICY_NAME for r in rows)
        check(f"ABAC row filter effective on {t.split('.')[-1]}", has)
    # entitlement (mapping) table keyed on the assumed role: exists + expected rows
    ok, rows = C.run_sql(w, f"SELECT role_name, country_code FROM {C.CATALOG}.{C.ENTITLEMENT_TABLE}", wid)
    got = {(r[0], r[1]) for r in rows} if ok else set()
    want = {(role, c) for role, cs in C.ROLE_COUNTRY_ENTITLEMENTS.items() for c in cs}
    check("entitlement table has expected per-role rows", got == want, "" if got == want else f"got={sorted(got)}")
    # the row-filter function owner needs EXPLICIT USE CATALOG (definer-context lookup of the table)
    me = w.current_user.me().user_name
    ok, rows = C.run_sql(w, f"SHOW GRANTS `{me}` ON CATALOG {C.CATALOG}", wid)
    check("row-filter owner has explicit USE CATALOG (definer lookup)",
          ok and any(r[0] == me and r[1] == "USE CATALOG" for r in rows))
    ok, rows = C.run_sql(w, f"SHOW EFFECTIVE POLICIES ON TABLE {C.GEN_TABLE}", wid)
    check("ABAC column mask effective on generation_daily", ok and any(r[0] == C.MASK_POLICY_NAME for r in rows))
    ok, rows = C.run_sql(w, f"SELECT column_name FROM {C.CATALOG}.information_schema.column_tags "
                            f"WHERE tag_name='{C.CONFIDENTIAL_TAG}'", wid)
    check("confidential tag on site_name", ok and any(r[0] == 'site_name' for r in rows))

    print("== Grants (least privilege) ==")
    def grantees(table):
        ok, rows = C.run_sql(w, f"SHOW GRANTS ON TABLE {table}", wid)
        return {(r[0], r[1]) for r in rows} if ok else set()  # (principal, action)
    g_gen, g_heat = grantees(C.GEN_TABLE), grantees(C.HEAT_TABLE)
    check("role_generation SELECT on generation", ("role_generation", "SELECT") in g_gen)
    check("role_heating SELECT on heating", ("role_heating", "SELECT") in g_heat)
    check("role_cross_domain SELECT on both",
          ("role_cross_domain", "SELECT") in g_gen and ("role_cross_domain", "SELECT") in g_heat)
    check("member groups have NO direct SELECT on generation",
          not any(p in C.MEMBER_GROUPS and act == "SELECT" for p, act in g_gen))

    print("== Genie (two single-domain spaces) ==")
    spaces = {(s.title or ""): s.space_id for s in (getattr(w.genie.list_spaces(), "spaces", None) or [])}
    for spec in C.GENIE_SPACES:
        sid = spaces.get(spec["title"])
        check(f"Genie space exists: {spec['title']}", sid is not None, sid or "")
        if sid:
            acl = w.api_client.do("GET", f"/api/2.0/permissions/genie/{sid}")
            runners = {x.get("group_name") for x in acl.get("access_control_list", [])
                       if any(p.get("permission_level") == "CAN_RUN" for p in x.get("all_permissions", []))}
            check(f"CAN_RUN = {spec['roles']} on '{spec['title']}'", set(spec["roles"]) == runners & set(C.ROLE_GROUPS))

    print("== Discover domains ==")
    dom_tags = {d.tag_key for d in w.domains.list_domains()}
    for t in C.DOMAIN_TAGS:
        check(f"domain exists: {t}", t in dom_tags)
    ok, rows = C.run_sql(w, "SELECT table_name, tag_name FROM "
        f"{C.CATALOG}.information_schema.table_tags WHERE tag_name LIKE 'Energy%'", wid)
    asset_tags = {(r[0], r[1]) for r in rows} if ok else set()
    # every TABLE/VIEW asset (fact tables, sites dimension, certified metric views)
    # carries its subdomain tag — so new assets can't silently miss the domain mapping
    for tag, assets in C.DOMAIN_ASSETS.items():
        for kind, name in assets:
            if kind == "SCHEMA":
                continue
            leaf = name.split(".")[-1]
            check(f"{leaf} assigned to its domain", (leaf, tag) in asset_tags)

    print("== Shared asset + Pages ==")
    g_shared = grantees(f"{C.CATALOG}.{C.SHARED_TABLE}")
    check("shared country_reference SELECT for all 3 roles",
          all((r, "SELECT") in g_shared for r in C.ROLE_GROUPS))
    ok, rows = C.run_sql(w, "SELECT DISTINCT tag_name FROM "
        f"{C.CATALOG}.information_schema.table_tags WHERE table_name='country_reference'", wid)
    stags = {r[0] for r in rows} if ok else set()
    check("shared table tagged into BOTH subdomains", {C.DOMAIN_GEN_TAG, C.DOMAIN_HEAT_TAG} <= stags)

    my_res = {f"domains/{d.domain_id}" for d in w.domains.list_domains() if d.tag_key in C.DOMAIN_TAGS}
    pages = list(C.knowledge_pages(w, my_res))
    pub = {p.get("display_name") for p in pages if p.get("state") == "PUBLISHED"}
    for titles in C.PAGES_BY_DOMAIN.values():
        for t in titles:
            check(f"page published: {t}", t in pub)
    check("no duplicate pages", len(pages) == sum(len(v) for v in C.PAGES_BY_DOMAIN.values()))

    print("== Ontology: sites dimension, PK/FK, comments ==")
    ok, rows = C.run_sql(w, f"SELECT count(*) FROM {C.ASSET_TABLE}", wid)
    check("asset_reference has 8 sites", ok and rows and int(rows[0][0]) == 8, str(rows[0][0]) if ok and rows else "")
    ok, rows = C.run_sql(w, f"SELECT constraint_type, count(*) FROM {C.CATALOG}.information_schema.table_constraints "
                            "WHERE constraint_type IN ('PRIMARY KEY','FOREIGN KEY') GROUP BY constraint_type", wid)
    ct = {r[0]: int(r[1]) for r in rows} if ok else {}
    check("2 RELY primary keys (country_reference, asset_reference)", ct.get("PRIMARY KEY", 0) >= 2, str(ct))
    check("3 RELY foreign keys (country x2, site_id)", ct.get("FOREIGN KEY", 0) >= 3, str(ct))
    ok, rows = C.run_sql(w, f"SELECT count(*) FROM {C.CATALOG}.information_schema.columns "
                            "WHERE table_schema='generation' AND table_name='generation_daily' "
                            "AND comment IS NOT NULL AND comment <> ''", wid)
    check("generation_daily columns are commented", ok and rows and int(rows[0][0]) >= 7, str(rows[0][0]) if ok and rows else "")

    print("== Ontology: certified metric views ==")
    for mv in (C.GEN_METRIC_VIEW, C.HEAT_METRIC_VIEW):
        schema, short = mv.split(".")[1], mv.split(".")[2]
        meas = "`Total Generation MWh`" if schema == "generation" else "`Total Consumption MWh`"
        ok, rows = C.run_sql(w, f"SELECT MEASURE({meas}) FROM {mv}", wid)
        check(f"metric view queryable via MEASURE(): {short}", ok and len(rows) > 0)
        ok, rows = C.run_sql(w, f"SELECT tag_value FROM {C.CATALOG}.information_schema.table_tags "
                                f"WHERE schema_name='{schema}' AND table_name='{short}' AND tag_name='{C.CERT_TAG}'", wid)
        check(f"metric view certified: {short}", ok and any(r[0] == 'certified' for r in rows))
        ok, rows = C.run_sql(w, f"SHOW GRANTS ON VIEW {mv}", wid)
        g = {(r[0], r[1]) for r in rows} if ok else set()
        check(f"SELECT granted to {C.METRIC_VIEW_ROLES[mv]} on {short}",
              all((r, "SELECT") in g for r in C.METRIC_VIEW_ROLES[mv]))

    print("== AI/BI dashboard (on the certified metric views) ==")
    try:
        names = {d.display_name for d in w.lakeview.list()
                 if d.lifecycle_state is None or getattr(d.lifecycle_state, "value", "") != "TRASHED"}
        check(f"dashboard exists: {C.DASHBOARD_NAME}", C.DASHBOARD_NAME in names)
    except Exception as e:
        check(f"dashboard exists: {C.DASHBOARD_NAME}", False, repr(e)[:80])

    npass = sum(1 for ok, *_ in results if ok)
    print(f"\nMETADATA CHECKS: {npass}/{len(results)} passed.")

    print("""
== Interactive access-outcome checks (run in the UI role switcher) ==
These prove the live outcomes and cannot be scripted headlessly on this CLI
(role assumption for a user is interactive). Run sql/10_persona_queries.sql
after assuming each role. Expected:
  role_generation  : generation OK (BE/DE/FR/NL); heating -> PERMISSION_DENIED
  role_heating     : heating OK (BE/DE/FR/NL); generation -> PERMISSION_DENIED
  role_cross_domain: both OK but FR+BE ONLY (gen 28 / heat 18); session_user() = 'role_cross_domain'

Genie (interactive): each domain role opens ITS space and gets an answer; the
cross-domain role uses Genie One ("Ask Genie") to query across both domains and
gets FR+BE only. Genie runs as the active role, so the ABAC filter applies.

Ontology (interactive): in a domain Genie space or Genie One, ask a KPI question
that uses the certified metric view, e.g. "capacity factor by asset type" or
"total generation by country". The answer is computed from the metric views
generation.generation_metrics / heating.heating_metrics via MEASURE(), and the
cross-domain role still sees FR+BE only (the metric view inherits the base-table
geo filter). Then open the published dashboard "Energy KPIs (Governed)":
it renders the SAME certified measures, published with INDIVIDUAL data permission
(run-as-viewer) so each viewer sees only their governed slice (cross-domain = FR+BE;
a single-domain role sees its own domain, the other domain's tiles are empty).
""")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
