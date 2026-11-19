# Unity Catalog RBAC + ABAC demo

A small, presenter-friendly demo that makes **Unity Catalog RBAC (assumable roles)** and
**ABAC (governed-tag row filters)** easy to understand in a ~5-minute live walkthrough — and
shows **Genie** respecting the exact same controls.

> **Takeaway:** RBAC selects the *active access context*; ABAC applies *tag-driven row-level
> protection* within that context. Grant once, enforced everywhere, provable in SQL.

All data is **synthetic**. Nothing here is real operational, customer, or employee data —
it models a generic energy company with two domains (renewable **generation** and district
**heating**). Target cloud: **AWS** (`docs.databricks.com/aws/en`); built and verified on a
serverless Databricks workspace. It is a **portable template** — every workspace-specific
value (profiles, catalog, warehouse id) is an environment variable or a documented
placeholder, so you can deploy it into your own workspace end-to-end.

## What it shows

| Capability | Where |
|---|---|
| Two governed domains with a shared `country_code` | [sql/00_generate_data.sql](sql/00_generate_data.sql) |
| **Governed tag** on `country_code` (controlled vocabulary) | [sql/01_governed_tag_abac.sql](sql/01_governed_tag_abac.sql) |
| **One ABAC row-filter policy** keyed on the assumed role via an **entitlement table** — covering **both** tables | [sql/01_governed_tag_abac.sql](sql/01_governed_tag_abac.sql) |
| **ABAC column-mask policy** redacting a tagged column (`site_name`) for the cross-domain role | [sql/01_governed_tag_abac.sql](sql/01_governed_tag_abac.sql) |
| **RBAC**: 3 member groups → ASSUME → 3 role groups; least-privilege grants | [driver/10_identity_setup.py](driver/10_identity_setup.py) |
| Identity-correct filter (`session_user()`, not `is_account_group_member`) | [sql/01_governed_tag_abac.sql](sql/01_governed_tag_abac.sql) |
| **Two domain Genie spaces** + **Genie One** for cross-domain, each respecting the active role | [driver/30_genie_space.py](driver/30_genie_space.py) |
| **Discover domains** (Browse by domain): parent + 2 subdomains, permission-aware | [driver/35_discover_domains.py](driver/35_discover_domains.py) |
| **Shared reference table** across both domains (readable by all roles, not row-filtered) | [sql/00_generate_data.sql](sql/00_generate_data.sql) |
| **Discover Pages**: business-rule definitions on each domain, access inherited from the domain | [driver/35_discover_domains.py](driver/35_discover_domains.py) |
| **UC metric views** — two **certified** governed KPI layers (capacity factor, availability, consumption), queried with `MEASURE()` | [sql/02_ontology_metrics.sql](sql/02_ontology_metrics.sql) |
| **Sites/asset dimension** (`asset_reference`) + **PK/FK** relationships (`RELY`) — the ontology join graph | [sql/00_generate_data.sql](sql/00_generate_data.sql), [sql/02_ontology_metrics.sql](sql/02_ontology_metrics.sql) |
| **Rich table/column comments + synonyms** (self-documenting, Genie-readable) | [sql/00_generate_data.sql](sql/00_generate_data.sql), [sql/02_ontology_metrics.sql](sql/02_ontology_metrics.sql) |
| **AI/BI dashboard** on the metric views; the *same* certified KPIs power **Genie One** | [driver/50_dashboard.py](driver/50_dashboard.py) |
| Live persona walkthrough + "how it works" evidence | [sql/10_persona_queries.sql](sql/10_persona_queries.sql), [sql/11_how_it_works.sql](sql/11_how_it_works.sql) |

## Architecture

```
            generation_users ──ASSUME──▶ role_generation ──▶ SELECT generation only
 users ───▶ heating_users    ──ASSUME──▶ role_heating    ──▶ SELECT heating only
            cross_domain_users──ASSUME─▶ role_cross_domain─▶ SELECT both  ──┐
                                                                                        │
 governed tag  country  ── on country_code in BOTH tables                         │
       │                                                                                ▼
       └─▶ ONE ABAC row-filter policy (catalog-scoped, tag-matched) ─▶ cross-domain role = FR rows only
                                                                        domain roles   = unrestricted

 Genie: 2 domain spaces (1 table each) + Genie One (cross-domain)
        ─▶ runs SQL AS the asking user ─▶ UC grants + ABAC apply per active role
```

The **member groups hold no data grants** — they only grant the right to *assume* a role.
Assuming a role **replaces** the session's permissions with the role's (one active role at a time),
so the access you see is enforced by Unity Catalog, never by a UI toggle.

## Prerequisites

- **Account + metastore admin** (to create account groups, wire ASSUME, create governed tags, policies).
- **RBAC** enabled in the account/workspace, and **ABAC** available (GA). ABAC needs **serverless or
  DBR 16.4+** compute and **fails closed** on older runtimes.
- A **pro/serverless SQL warehouse**.
- Databricks **CLI ≥ 1.0** and local **Python 3.10+**.

## Setup

```bash
# 0. Profiles (browser OAuth): workspace + account
WS_HOST=https://dbc-00000000-0000.cloud.databricks.com/ \
ACCOUNT_ID=00000000-0000-0000-0000-000000000000 \
bash scripts/setup_profiles.sh

# 1. Python env for the driver
python3 -m venv .venv && . .venv/bin/activate && pip install -r driver/requirements.txt

# 2. Preflight (read-only) — aborts if a prerequisite is missing
python driver/00_preflight.py

# 3. Identity: account groups + ASSUME + membership + workspace/warehouse access  (account admin)
python driver/10_identity_setup.py

# 4. Governance: data + governed tag + grants + ABAC policy + ONTOLOGY
#    (sql/02: sites dimension, column comments, PK/FK, certified metric views)  (SQL warehouse)
python driver/20_governance.py
#    …or deploy the bundle and run the job (first run only; see note in resources/):
#    databricks bundle deploy -t dev --profile uc-gov
#    databricks bundle run governance_setup -t dev --profile uc-gov

# 5. Genie: two single-domain spaces (cross-domain scenario uses Genie One)
python driver/30_genie_space.py

# 5b. Discover: UC domains (parent + 2 subdomains), shared-table tagging, + business-rule Pages
python driver/35_discover_domains.py

# 5c. Dashboard: AI/BI dashboard on the certified metric views (create + publish)
python driver/50_dashboard.py

# 6. Validate (metadata proofs) + print the interactive runbook
python driver/40_validate.py
```

Run order matters: **identity (3) before governance (4)** — the ABAC policy and grants reference
the role groups.

### Configuration (override as needed)

Every workspace-specific value is an environment variable with a sensible default — no code edits:

| Variable | Default | What it is |
|---|---|---|
| `DEMO_WS_PROFILE` | `uc-gov` | Databricks CLI **workspace** (OAuth) profile |
| `DEMO_ACCT_PROFILE` | `uc-gov-acct` | **Account-level** (OAuth) profile for group + ASSUME setup |
| `DEMO_CATALOG` | `governance_demo` | Catalog the demo creates and uses |
| `DEMO_WAREHOUSE_ID` | auto-detect | Pro/serverless SQL warehouse (first serverless found if unset) |

The optional bundle path (`databricks.yml`) has its own `catalog` and `warehouse_id` variables —
set `warehouse_id` to your warehouse id if you deploy via `databricks bundle`.

## Live demo & validation

- Presenter script (~5 min): [docs/presenter-script.md](docs/presenter-script.md)
- Persona queries (assume each role in the UI): [sql/10_persona_queries.sql](sql/10_persona_queries.sql)
- "How it works" evidence: [sql/11_how_it_works.sql](sql/11_how_it_works.sql)
- Pass/fail checklist: [docs/validation-checklist.md](docs/validation-checklist.md)

**Persona switching is the native RBAC role switcher** (top bar → *Assume role*). It is a real
permission swap, not a UI mock. Headless role assumption for a *user* is not supported by the CLI;
the automated checks therefore cover the governance wiring + audit, and the per-role access outcomes
are validated interactively (or, if you choose, via a service-principal `assume_group` harness — not
included here by design).

## Cleanup

```bash
python driver/90_cleanup.py --yes     # removes ONLY demo objects; leaves the catalog itself
```

## How it fits together (concepts)

- **Group membership** → lets you *assume* a role (via the `group.assumer` rule). It is not data access.
- **ASSUME** → activates a role for the session; the role's grants **replace** your own.
- **Unity Catalog grants** → what the *active identity* (the role) may read.
- **ABAC policy** → a tag-matched row filter/column mask layered on top of grants; evaluated against
  the **active identity**. Our filter keys on `session_user()` (the role name). It deliberately does
  **not** use `is_account_group_member('role_cross_domain')` — a role is not a member of itself,
  so that would always be false. Two policies protect the tables: a **row filter** keyed on the
  assumed role via an **entitlement table** (`gov.role_country_entitlements`, one row per role; `ALL`
  = every country; domain roles → `ALL`, cross-domain → `FR`,`BE`) — add/remove a row to change
  access, no DDL — and a **column mask** (`site_name` → `REDACTED` for the cross-domain role). The
  governed tag `country` now only **marks** the country column (binds one policy across both
  tables). ABAC **GRANT** policies dynamically grant privileges, but only on AI securables (models,
  MCP, agents, skills) — **not** tables; table `SELECT` stays a direct grant.
- **Genie execution** → runs the generated SQL *as the asking user*, so the active role's grants and
  the ABAC filter apply. Genie does not bypass Unity Catalog. Two single-domain spaces keep each
  analyst's experience clean; the cross-domain scenario uses **Genie One** (workspace "Ask Genie"),
  which also runs as the active role (cross-domain role → FR + BE across both domains).
- **Discover (domains + Pages)** → assets are grouped into business-area domains, and business-rule
  **Pages** document metrics/rules. Both are **permission-aware**: a user sees only the assets they
  can access (BROWSE/VIEW/SELECT), and a published Page is readable by anyone who can access its
  domain — so per-role access is inherited from the UC grants, not a separate ACL. Domain/page
  *management* (MANAGE DOMAIN / MANAGE DISCOVER) is UI-only. The **shared** `country_reference` table
  belongs to both domains and is readable by all roles (reference data is not row-filtered).
- **Ontology (modeled + learned knowledge)** → the context layer Genie searches to turn a question
  into the right SQL. We model it with: two **certified metric views** (`generation.generation_metrics`,
  `heating.heating_metrics`) that define the KPIs once (capacity factor, availability, consumption) and
  are queried with `MEASURE()`; **rich table/column comments + synonyms**; **PK/FK relationships**
  (`RELY`) over a new **sites dimension** (`asset_reference`) so Genie can infer joins; and
  **certification** (`system.certification_status = certified`). The **AI/BI dashboard** and **Genie
  One** consume the *same* certified measures, and the published dashboard feeds its queries back as
  *learned* knowledge. Because the metric views sit on the governed base tables, every KPI is enforced
  per active role (the cross-domain role's KPIs cover FR + BE only).
- **Workspace entitlements (least privilege)** → domain roles get **Databricks SQL access**
  (`databricks-sql-access`: SQL editor + warehouse); the cross-domain role gets **Consumer access**
  (`workspace-consume`: AI/BI dashboards + Genie only, *no* SQL editor) — so it does its FR+BE work
  through **Genie One**, not the SQL editor. (Entitlements are workspace surface access; they're
  independent of the UC data grants that decide which rows/columns each role actually sees.)

## Limitations / honesty

- Row filters/masks don't grant access — the role must already hold `SELECT`.
- The row-filter function reads the entitlement table under its **owner's** (definer) rights, so the
  owner needs an **explicit `USE CATALOG`** on the catalog (owning the schema/table isn't enough, and
  admin bypass doesn't apply in that context) — else role queries hit `42501 … owner … failed an
  authorization check`. `driver/20_governance.py` grants this to the deploying user automatically.
  The entitlement table is therefore sensitive; in production, secure it (e.g. its own row filter so
  a role sees only its rows).
- ABAC fails closed on pre-16.4 non-serverless compute.
- A successful demo is **not** a formal security validation or a production-ready configuration.
- The demo presenter is an admin for setup only, and is deliberately not one of the personas; persona
  tests must be run **under an assumed role** (an un-assumed admin would bypass the row filter).
- **Metric views inherit the base-table ABAC.** The certified KPIs are views over the fact tables, so
  the geo row filter + column mask still apply per querying role (cross-domain KPIs = FR + BE). The
  views read the dimensions with the owner's rights, so roles get `SELECT` on the metric view only
  (not on `asset_reference`), which also stops the cross-domain role enumerating out-of-scope sites.
- **The dashboard uses _individual data permission_** (run-as-viewer, `embed_credentials=False`): each
  viewer runs the queries with their own UC permissions, so the ABAC filter applies in the dashboard
  too — the cross-domain consumer sees **FR + BE** KPIs, the same as in Genie. A single-domain role
  sees only its own domain (the other domain's tiles are empty — no grant on that metric view), so the
  **cross-domain role is the intended full-dashboard audience**.
- **PK/FK constraints are informational** (`NOT ENFORCED RELY`): the ontology + optimizer rely on them,
  but Unity Catalog does not enforce them — the synthetic data satisfies them by construction.

## Repo layout

```
databricks.yml                 DAB: deploys assets + governance job (var: catalog, warehouse_id)
resources/governance.job.yml   SQL-warehouse job (workspace-level governance SQL)
sql/00_generate_data.sql       catalog/schemas + 2 facts + sites dimension + column comments
sql/01_governed_tag_abac.sql   governed tag, column tags, grants, UDF, ABAC policy
sql/02_ontology_metrics.sql    PK/FK (RELY), 2 certified metric views, metric-view grants
sql/10_persona_queries.sql     per-role positive/negative demo queries
sql/11_how_it_works.sql        policies, tags, grants, audit evidence
driver/00_preflight.py         read-only prerequisite probe
driver/10_identity_setup.py    account groups + ASSUME + membership + entitlements
driver/20_governance.py        runs the governance SQL 00+01+02 (idempotent)
driver/30_genie_space.py       two domain Genie spaces (table + metric view) + CAN_RUN
driver/35_discover_domains.py  UC Discover domains (parent + 2 subdomains), shared-asset tagging, + Pages
driver/40_validate.py          automated metadata proofs + interactive runbook
driver/50_dashboard.py         AI/BI dashboard on the certified metric views (create + publish)
driver/90_cleanup.py           remove only demo objects
scripts/setup_profiles.sh      one-time OAuth profile setup
docs/                          presenter script, validation checklist, architecture
web-app/                       self-contained static explainer slide deck (open web-app/index.html)
```
