# Validation checklist — Unity Catalog RBAC + ABAC

Two layers: **(A)** automated metadata/evidence proofs (run as admin), and **(B)** interactive access-outcome proofs under genuinely assumed roles. A demo is "green" only when both pass.

> **Maps to the two demo scenarios** (presenter-script.md): section **B** (per-role SQL outcomes) is **Scenario 1 · Governance**; sections **C / D / E** (Genie, Discover, metric views + dashboard) are **Scenario 2 · Discover Pages + Genie One**. Section **A** proves the wiring behind both.

## A. Automated metadata proofs — `python driver/40_validate.py`
- [ ] All 6 account groups exist (3 member, 3 role).
- [ ] ASSUME wired: each member group holds `group.assumer` on its role group.
- [ ] Governed tag `country` attached to `country_code` in **both** tables.
- [ ] The ABAC row-filter policy `country_row_filter` (keyed on the assumed role via `gov.role_country_entitlements`) is **effective on both** tables.
- [ ] Entitlement table `gov.role_country_entitlements` has the expected rows: generation→`ALL`, heating→`ALL`, cross-domain→`FR`,`BE`.
- [ ] The ABAC column-mask policy `mask_confidential` is effective on generation_daily; `confidential` tags `site_name`.
- [ ] Data `SELECT` is granted to the **role** groups only; member groups have **no** direct SELECT.
- [ ] Two domain Genie spaces exist with correct **CAN_RUN** (generation+cross; heating+cross).
- [ ] Discover: parent domain + 2 subdomains exist; both tables assigned to their subdomain.
- [ ] Shared `country_reference`: SELECT for all 3 roles; tagged into BOTH subdomains.
- [ ] Discover Pages: 3 business-rule pages PUBLISHED on their domains; no duplicates.
- [ ] Entitlements (least privilege): generation/heating = **Databricks SQL access**; cross-domain = **Consumer access** (`workspace-consume`).
- [ ] Ontology: sites dimension `asset_reference` has 8 rows; informational **PK/FK (RELY)** present (2 PKs, 3 FKs).
- [ ] Ontology: `generation_daily` columns carry **comments** (self-documenting).
- [ ] Ontology: two **certified** metric views (`generation_metrics`, `heating_metrics`) are queryable via `MEASURE()`, tagged `system.certification_status=certified`, with `SELECT` granted to the right roles.
- [ ] AI/BI dashboard **"Energy KPIs (Governed)"** exists (published).

## B. Interactive access outcomes — `sql/10_persona_queries.sql` (assume each role in the UI)

| # | Acting as | Query | Expected |
|---|-----------|-------|----------|
| 1 | `role_generation` | `session_user()` | `role_generation` |
| 2 | `role_generation` | count generation by country | ✅ BE, DE, FR, NL |
| 3 | `role_generation` | count heating | ❌ **PERMISSION_DENIED** |
| 4 | `role_heating` | `session_user()` | `role_heating` |
| 5 | `role_heating` | count heating by country | ✅ BE, DE, FR, NL |
| 6 | `role_heating` | count generation | ❌ **PERMISSION_DENIED** |
| 7 | `role_cross_domain` | `session_user()` | `role_cross_domain` ✅ confirmed |
| 8 | `role_cross_domain` | count generation by country | ✅ **FR + BE (28 rows)** |
| 9 | `role_cross_domain` | count heating by country | ✅ **FR + BE (18 rows)** |
| 10 | `role_cross_domain` | `SELECT DISTINCT site_name` (generation) | ✅ **REDACTED** (column mask) |
| 11 | `role_generation` | `SELECT DISTINCT site_name` (generation) | ✅ real site names (unmasked) |

> Rows 7–10 (`role_cross_domain`) assume **SQL-editor access**, which this role no longer has (it's **Consumer access**). Verify the cross-domain **FR+BE** + REDACTED results via **Genie One** instead (section C), or temporarily grant the role `databricks-sql-access` to run them in the editor.

## C. Genie (interactive) — two domain spaces + Genie One for cross-domain
Genie runs generated SQL as the active role, so UC grants + the ABAC filter apply.
- [ ] As `role_generation`: open **Renewable Generation Operations** → "Summarize generation output by country." → answers (all countries; domain role is not FR-restricted).
- [ ] As `role_heating`: open **District Heating** → "Summarize heating consumption by country." → answers.
- [ ] As `role_cross_domain`: use **Genie One** ("Ask Genie") → "Compare generation and heating consumption by country for the latest month." → **FR + BE only**.
- [ ] As `role_cross_domain` (Genie One): "Show heating consumption for Germany." → **no DE rows** (ABAC enforced).

## D. Discover (interactive) — Browse by domain
- [ ] As admin/steward: **Discover → Browse by domain** shows **Energy Operations** with 2 subdomains (Renewable Generation, District Heating), each listing its schema + table.
- [ ] As a domain role: Browse by domain surfaces only the assets that role can access (UC enforcement carries into Discover).
- [ ] Open a domain **Page** (e.g. "Geo access rule…") — readable by anyone who can access the domain.
- [ ] Shared `country_reference` appears in BOTH subdomains and is readable by all three roles.

## E. Ontology / metric views (interactive)
Governed KPIs defined once, reused by the dashboard **and** Genie One.
- [ ] Admin: open the dashboard **"Energy KPIs (Governed)"** → tiles render (capacity factor, availability, generation/consumption; bars by country/segment).
- [ ] Published with **individual data permission** (run-as-viewer): as `role_cross_domain`, the dashboard tiles show **FR + BE only** (the viewer's own governed slice) — governance carries into AI/BI. A single-domain role sees only its domain; the other domain's tiles are empty (no grant on that metric view).
- [ ] Admin or role (SQL/Genie): `SELECT \`Asset Type\`, MEASURE(\`Capacity Factor Pct\`) FROM governance_demo.generation.generation_metrics GROUP BY \`Asset Type\`` → **wind ~55%, solar ~19%**.
- [ ] As `role_cross_domain` in **Genie One**: "capacity factor by asset type" / "total generation by country" → answered from the **certified metric view**, **FR + BE only** (the metric view inherits the geo row filter).
- [ ] Catalog Explorer: both metric views show a **Certified** badge (`system.certification_status=certified`).

## Negative-path note
The denials in rows 3 and 6 are the proof that assuming a role **replaces** base permissions —
a workspace/metastore admin running these as an assumed role still gets denied the other domain.
If an admin runs them **without** assuming a role, they bypass the filter (expected) — which is why
persona tests must always be run under an assumed role.
