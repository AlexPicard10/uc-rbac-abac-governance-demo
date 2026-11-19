# Presenter script — Unity Catalog governance + ontology (~6 min)

**Audience:** Data & governance stakeholders.
**One-liner takeaway:** *RBAC selects the active access context; ABAC protects the rows and columns within it — and the Genie ontology lets anyone ask for a governed KPI in plain language. One grant model, enforced everywhere (SQL, Genie, dashboards).*

**Before you start:** SQL editor open on the serverless warehouse; know the top-bar **role switcher** (workspace name → *Assume role*); have **Genie One / "Ask Genie"**, **Discover → Browse by domain**, and the published dashboard **"Energy KPIs (Governed)"** ready in tabs. All data is synthetic.

> **Two scenarios, Tell → Show → Tell** — they fill the two `DEMO` slots in the "Governance on Databricks" deck: **Scenario 1 · Governance** (deck slide 20) and **Scenario 2 · Discover Pages + Genie One** (deck slide 55). Keep the roadmap/NDA slides out of the live portion — everything below is GA.

### 0 · Frame it (20s)
"Two data domains — renewable **generation** and district-**heating**. Three groups of users. I'll prove, live, that access is enforced by the platform, not the app — and that the same governance carries into Discover and Genie."

---

## Scenario 1 — Governance: RBAC + ABAC  *(deck slide 20)*

**① Tell — what I'll show (15s):** "Access is decided by your *active role*. Same person — I switch identity in the top bar and the view changes: domain isolation from **RBAC**, plus **FR + BE** rows and masked site names from **ABAC** — enforced by Unity Catalog, never the app."

**② Show — live on Databricks (~2 min):** run `sql/10_persona_queries.sql`, one section per assumed role.

1. **As admin (no role)** — the "before":
   ```sql
   SELECT country_code, count(*) FROM governance_demo.generation.generation_daily GROUP BY country_code ORDER BY 1;
   ```
   → all four: FR, BE, NL, DE.
2. **Assume role → `role_generation`** (persona 1): `generation_daily` returns all four countries; `heating_consumption` → **PERMISSION_DENIED**. "Assuming a role *replaces* my permissions with the role's — I lost my admin reach."
3. **Assume role → `role_cross_domain`** (persona 3): **both** domains return — but **FR + BE only**: gen **28** / heat **18** rows. `SELECT session_user();` → `role_cross_domain`.
4. Still that role: `SELECT DISTINCT site_name …` → **`REDACTED`** (ABAC column mask), while the generation role sees real site names.

**③ Tell — the result (15s):** "Three identities, three views. RBAC picked the context; ABAC filtered the rows *and* columns within it. *Which* countries comes from an **entitlement table keyed on `session_user()`** (cross-domain → `FR`,`BE`) — to widen or narrow access I add/remove one table row, **no DDL, no new policy**. The filter evaluates the active role, not my login, so even an admin acting as the role is held to exactly what it can see."

> Entitlement note: `role_cross_domain` has **Consumer access** (Genie/dashboards, not the SQL editor). Run its SQL in the editor only if you temporarily grant it `databricks-sql-access`; otherwise land its FR+BE proof in **Genie One** (Scenario 2). An un-assumed admin bypasses the filter — always assume the role.

---

## Scenario 2 — Discover Pages + Genie One  *(deck slide 55)*

**① Tell — what I'll show (15s):** "A business user finds governed data by **business area** and just asks. I browse the Discover domain, open the business-rule **Page**, then ask **Genie One** a KPI question — the **certified metric view** answers precisely, still governed to my active role."

**② Show — live on Databricks (~3 min):**
1. **(steward) Discover → Browse by domain → Energy Operations** → two subdomains + the shared `country_reference`, with the **Certified** metric views `generation_metrics` / `heating_metrics`. Open the **three governed Pages** — business-rule wikis the ontology reads:
   - **Geo access rule — cross-domain sees FR + BE only** *(parent)* — the FR/BE restriction, in plain language.
   - **Renewable generation metrics** *(generation)* — metric definitions **+ the rule: availability < ~85% → flagged for maintenance review.**
   - **District-heating consumption metrics** *(heating)* — segments anonymized, reported monthly.

   "Discover shows each person only what they can access; **Pages carry the business rules**; certification tells Genie what to trust."
2. **Genie — who asks what.** Assume each role in the top-bar role switcher; Genie writes & runs the SQL **as that role**, so every ontology answer is governed to it. (Genie is a consumer surface, so it works even for a Consumer-access role.)

   **a) `role_generation` → open the "Renewable Generation Operations" Genie space** (domain analyst — sees all countries):
   - > "Compare the capacity factor of wind versus solar for each country."

     Certified `generation_metrics`: the `Capacity Factor` measure joins `asset_reference` for nameplate capacity, split by asset type × country (`country_reference` join). All four countries; wind ≈ 55% vs solar ≈ 19%.
   - > "What's the utilization by technology, and which sites fall under the 85% availability maintenance rule?"

     **Synonyms** (utilization → Capacity Factor, technology → asset_type) **+ the rule from the "Renewable generation metrics" Page**.

   **b) `role_heating` → open the "District Heating" Genie space** (domain analyst):
   - > "Rank customer segments by total heating consumption and show each segment's share of the total."

     Certified `heating_metrics` by `Customer Segment`, with share-of-total.

   **c) `role_cross_domain` → Genie One ("Ask Genie")** (cross-domain consumer — the governance punchline):
   - > "Compare the capacity factor of wind versus solar for each country."  *(the same question as (a))*

     Same certified metric — but now **FR + BE only**. Governance rides on top of the ontology.
   - > "For France, compare renewable generation with district-heating consumption by month."

     Spans **both** certified metric views — only the cross-domain role can.
   - > "Show heating consumption for Germany."

     **No rows** — Genie can't exceed the role's ABAC scope.

   The point: domain analysts get the full ontology-powered picture; the cross-domain consumer gets the **same** answers, governed to FR + BE.
3. Open the dashboard **"Energy KPIs (Governed)"** (published with **individual data permission**) → as the cross-domain role it shows the **same FR + BE** numbers. "Same certified measure, same answer — in the dashboard *and* in the agent."

**③ Tell — the result (15s):** "The ontology gave Genie the business meaning — domains, **three governed Pages**, synonyms, and **certified metric views** — so it answered complex questions precisely instead of guessing SQL. Governance held end-to-end: FR + BE only, in Genie *and* the dashboard. The deck's benchmark — 1.6× accuracy on a fictional energy-suppliers workspace — is exactly this, on your data shape."

---

### Appendix · How it works (evidence, optional, 45s)
Drop the role (or a new tab as admin). Highlights of `sql/11_how_it_works.sql`:
- `SHOW EFFECTIVE POLICIES ON TABLE …` on **both** tables → the same single row-filter + column-mask policy.
- `information_schema.column_tags` → the governed tag on `country_code`.
- `SHOW GRANTS` → data is granted to **role** groups only; member groups just hold ASSUME.
- Audit: `run_by` (the person) vs `run_as` (the role).

"Classify → tag → one policy protects every matching asset. Grant once, enforced everywhere, provable in SQL."

---

### If asked / honest caveats
- *"Did the UI toggle change who you are?"* — Yes, genuinely: assuming a role **replaces** the session's permissions (one active role at a time). It is not a cosmetic switch.
- Row filters/masks don't **grant** access — the role must already hold SELECT; the filter only restricts. (ABAC **GRANT** policies apply to AI securables — models / MCP / agents — not tables; table `SELECT` stays a direct grant.)
- *"Is the dashboard itself access-controlled per row?"* — **Yes.** It's published with **individual data permission** (run-as-viewer), so each viewer's own UC permissions run the queries: the cross-domain consumer sees **FR + BE**, not the full fleet. A single-domain role sees only its own domain (the other domain's tiles are empty — no grant on that metric view); the cross-domain role is the intended full-dashboard audience.
- PK/FK relationships are **informational** (`RELY`): the ontology + optimizer use them; Unity Catalog does not enforce them.
- This is a synthetic demo on serverless; it demonstrates the controls, it is not a formal security certification or a production configuration.
