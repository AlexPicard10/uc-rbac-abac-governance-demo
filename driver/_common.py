"""Shared config + helpers for the Unity Catalog RBAC + ABAC demo driver.

Profiles (override via env):
  DEMO_WS_PROFILE    workspace OAuth profile   (default: uc-gov)
  DEMO_ACCT_PROFILE  account  OAuth profile    (default: uc-gov-acct)
  DEMO_CATALOG       demo catalog              (default: governance_demo)
  DEMO_WAREHOUSE_ID  pro/serverless warehouse  (default: auto-detect)

All objects created by the demo carry these names so cleanup can target ONLY them.
"""
from __future__ import annotations
import os
from databricks.sdk import WorkspaceClient, AccountClient
from databricks.sdk.service.sql import StatementState

WS_PROFILE   = os.environ.get("DEMO_WS_PROFILE", "uc-gov")
ACCT_PROFILE = os.environ.get("DEMO_ACCT_PROFILE", "uc-gov-acct")
CATALOG      = os.environ.get("DEMO_CATALOG", "governance_demo")

MEMBER_GROUPS = ["generation_users", "heating_users", "cross_domain_users"]
ROLE_GROUPS   = ["role_generation", "role_heating", "role_cross_domain"]
# member group -> role group it may ASSUME
PAIRS = list(zip(MEMBER_GROUPS, ROLE_GROUPS))
CROSS_ROLE = "role_cross_domain"

# Least-privilege WORKSPACE entitlements per role group (SCIM values).
# Domain roles are SQL users; the cross-domain role is a pure *consumer*
# (AI/BI dashboards + Genie), so it gets Consumer access = "workspace-consume"
# and uses Genie One (not the SQL editor).
ROLE_ENTITLEMENTS = {
    "role_generation":   ["databricks-sql-access"],
    "role_heating":      ["databricks-sql-access"],
    "role_cross_domain": ["workspace-consume"],
}

GEN_TABLE  = f"{CATALOG}.generation.generation_daily"
HEAT_TABLE = f"{CATALOG}.heating.heating_consumption"

# Ontology / UC-semantics layer (sql/02): sites dimension + certified metric views.
ASSET_TABLE      = f"{CATALOG}.generation.asset_reference"      # sites/asset dimension (PK site_id)
GEN_METRIC_VIEW  = f"{CATALOG}.generation.generation_metrics"   # certified KPI layer (domain 1)
HEAT_METRIC_VIEW = f"{CATALOG}.heating.heating_metrics"         # certified KPI layer (domain 2)
CERT_TAG         = "system.certification_status"               # value 'certified' = trusted asset
# metric view -> roles granted SELECT (the base-table ABAC geo filter still applies per role)
METRIC_VIEW_ROLES = {
    GEN_METRIC_VIEW:  ["role_generation", "role_cross_domain"],
    HEAT_METRIC_VIEW: ["role_heating", "role_cross_domain"],
}
# AI/BI dashboard built on the metric views (driver/50_dashboard.py)
DASHBOARD_NAME = "Energy KPIs (Governed)"

# Two single-domain Genie spaces (clean, no cross-table access warnings). The
# cross-domain scenario is run with Genie One (workspace "Ask Genie"), which also
# runs as the active role and enforces the ABAC FR filter.
GENIE_SPACES = [
    {"title": "Renewable Generation Operations (Domain 1)", "table": GEN_TABLE,
     "metric_view": GEN_METRIC_VIEW,
     "roles": ["role_generation", "role_cross_domain"]},
    {"title": "District Heating (Domain 2)", "table": HEAT_TABLE,
     "metric_view": HEAT_METRIC_VIEW,
     "roles": ["role_heating", "role_cross_domain"]},
]
# Older single combined space to remove if present (superseded by the two above).
LEGACY_GENIE_TITLES = ["Governance Demo - Generation & Heating"]

# Unity Catalog "Discover" domains (Beta). A domain is backed by a governed tag;
# assets join a domain by carrying that tag (empty value = membership). The title
# shown in Discover is the tag_key's leaf segment.
DOMAIN_PARENT_TAG = "Energy Operations"
DOMAIN_GEN_TAG    = f"{DOMAIN_PARENT_TAG}/Renewable Generation"
DOMAIN_HEAT_TAG   = f"{DOMAIN_PARENT_TAG}/District Heating"
DOMAIN_TAGS       = [DOMAIN_PARENT_TAG, DOMAIN_GEN_TAG, DOMAIN_HEAT_TAG]
# Which securables carry each subdomain tag: schema + fact table + sites dimension +
# the certified metric view. Metric views are VIEWs, so they use ALTER VIEW ... SET TAGS
# (ALTER TABLE would error on a view) — hence the explicit securable kind per asset.
DOMAIN_ASSETS = {
    DOMAIN_GEN_TAG:  [("SCHEMA", "generation"),
                      ("TABLE",  "generation.generation_daily"),
                      ("TABLE",  "generation.asset_reference"),
                      ("VIEW",   "generation.generation_metrics")],
    DOMAIN_HEAT_TAG: [("SCHEMA", "heating"),
                      ("TABLE",  "heating.heating_consumption"),
                      ("VIEW",   "heating.heating_metrics")],
}
# Shared reference table — tagged into BOTH subdomains (appears in each as a shared asset).
SHARED_TABLE = "shared.country_reference"

# UC Discover "Pages" (knowledge API /api/2.0/knowledge/pages): governed business-rule
# definitions attached to a domain, inheriting its access. Titles per domain for
# idempotency + cleanup; full markdown bodies live in 35_discover_domains.py.
PAGES_BY_DOMAIN = {
    DOMAIN_PARENT_TAG: ["Geo access rule — cross-domain sees FR + BE only"],
    DOMAIN_GEN_TAG:    ["Renewable generation metrics"],
    DOMAIN_HEAT_TAG:   ["District-heating consumption metrics"],
}
GOVERNED_TAG = "country"
POLICY_NAME  = "country_row_filter"
CONFIDENTIAL_TAG = "confidential"            # marks columns masked by ABAC
MASK_POLICY_NAME = "mask_confidential"       # tag-driven column-mask policy

# Row-filter entitlement (mapping) table, keyed on the assumed role (session_user()).
# 'ALL' = every country. Best practice: per-role row filters keyed on the assumed role.
ENTITLEMENT_TABLE = "gov.role_country_entitlements"
ROLE_COUNTRY_ENTITLEMENTS = {
    "role_generation":   ["ALL"],
    "role_heating":      ["ALL"],
    "role_cross_domain": ["FR", "BE"],
}


def ws() -> WorkspaceClient:
    return WorkspaceClient(profile=WS_PROFILE)


def acct() -> AccountClient:
    return AccountClient(profile=ACCT_PROFILE)


def warehouse_id(w: WorkspaceClient) -> str:
    """Return DEMO_WAREHOUSE_ID if set, else the first pro/serverless warehouse."""
    wid = os.environ.get("DEMO_WAREHOUSE_ID")
    if wid:
        return wid
    best = None
    for wh in w.warehouses.list():
        if wh.enable_serverless_compute:
            return wh.id
        best = best or wh.id
    if not best:
        raise SystemExit("No SQL warehouse found. Set DEMO_WAREHOUSE_ID.")
    return best


def run_sql(w: WorkspaceClient, sql: str, wid: str, catalog: str | None = CATALOG):
    """Execute one statement; return (ok: bool, rows_or_error)."""
    r = w.statement_execution.execute_statement(
        warehouse_id=wid, statement=sql, catalog=catalog, wait_timeout="50s")
    if r.status.state != StatementState.SUCCEEDED:
        return False, (r.status.error.message if r.status and r.status.error else str(r.status.state))
    rows = r.result.data_array if (r.result and r.result.data_array) else []
    return True, rows


def split_sql(path: str) -> list[str]:
    """Split a .sql file into individual statements. Drops full-line `--` comments,
    then splits on a `;` that ends a line (optionally followed by spaces and/or an
    inline `-- comment`) — so `... VALUES (...);  -- note` still terminates cleanly.
    `$$...$$` metric-view bodies stay intact as long as they contain no `;`."""
    import re
    text = open(path, "r", encoding="utf-8").read()
    # strip full-line comments
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
    body = "\n".join(lines)
    return [s.strip() for s in re.split(r";[ \t]*(?:--[^\n]*)?(?:\n|$)", body) if s.strip()]


def group_id(a: AccountClient, name: str) -> str | None:
    for g in a.groups.list(attributes="id,displayName"):
        if g.display_name == name:
            return g.id
    return None


def knowledge_pages(w: WorkspaceClient, domains: set[str] | None = None):
    """Yield UC Discover Pages. The server-side `domain` filter is ignored, so we
    paginate and filter client-side to the given 'domains/{id}' resource names."""
    token = None
    while True:
        q = {"page_size": "100"}
        if token:
            q["page_token"] = token
        r = w.api_client.do("GET", "/api/2.0/knowledge/pages", query=q)
        batch = r.get("pages") or []
        for p in batch:
            if domains is None or p.get("domain") in domains:
                yield p
        token = r.get("next_page_token")
        if not token or not batch:
            break
