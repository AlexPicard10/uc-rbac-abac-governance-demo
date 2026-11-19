-- ============================================================================
-- Unity Catalog RBAC + ABAC demo — 10 · Persona queries (the live walkthrough)
-- ----------------------------------------------------------------------------
-- HOW TO RUN (honest identity switching — not a UI mock):
--   1. In the Databricks workspace top bar, click the workspace name ->
--      "Assume role" -> pick the role named in each section below.
--   2. Open a SQL editor on the serverless/pro SQL warehouse.
--   3. Run that section's statements.
-- Assuming a role REPLACES your base permissions with ONLY the role's, so
-- these outcomes are enforced by Unity Catalog, not by the UI.
--
-- (Presenters who are workspace/metastore admins: you MUST assume a role for
--  these tests. As the bare admin you would bypass the row filter.)
-- ============================================================================

-- ######################  PERSONA 1 — GENERATION  ############################
-- Assume role:  role_generation
SELECT session_user() AS acting_as;                 -- expect: role_generation

-- ✅ Domain 1 is allowed (all countries — domain roles are NOT FR-restricted):
SELECT country_code, count(*) AS rows, round(sum(generation_mwh),1) AS total_mwh
FROM governance_demo.generation.generation_daily
GROUP BY country_code ORDER BY country_code;        -- expect: BE, DE, FR, NL

-- The domain owner sees real site names (the column mask does not redact this role):
SELECT DISTINCT site_name FROM governance_demo.generation.generation_daily ORDER BY 1;  -- expect: real names

-- ❌ Domain 2 is denied (run separately — expect PERMISSION_DENIED):
SELECT count(*) FROM governance_demo.heating.heating_consumption;


-- ######################  PERSONA 2 — HEATING  ###############################
-- Assume role:  role_heating
SELECT session_user() AS acting_as;                 -- expect: role_heating

-- ✅ Domain 2 is allowed (all countries):
SELECT country_code, count(*) AS rows, round(sum(consumption_mwh),1) AS total_mwh
FROM governance_demo.heating.heating_consumption
GROUP BY country_code ORDER BY country_code;        -- expect: BE, DE, FR, NL

-- ❌ Domain 1 is denied (run separately — expect PERMISSION_DENIED):
SELECT count(*) FROM governance_demo.generation.generation_daily;


-- ##################  PERSONA 3 — CROSS-DOMAIN (ABAC)  #######################
-- Assume role:  role_cross_domain
-- NOTE: this role has CONSUMER access (Genie/dashboards), NOT the SQL editor — so
--       verify its result in GENIE ONE ("Ask Genie"). The SQL below is for reference;
--       it runs only if the role is temporarily granted databricks-sql-access.
-- Its countries come from the entitlement table gov.role_country_entitlements
-- (role_cross_domain -> FR, BE). Add/remove a row there to change access — no DDL.
SELECT session_user() AS acting_as;                 -- expect: role_cross_domain

-- ✅ BOTH domains are allowed, but the ABAC row filter returns only its entitled countries (FR, BE):
SELECT country_code, count(*) AS rows
FROM governance_demo.generation.generation_daily
GROUP BY country_code ORDER BY country_code;        -- expect: FR + BE (28 rows total)

SELECT country_code, count(*) AS rows
FROM governance_demo.heating.heating_consumption
GROUP BY country_code ORDER BY country_code;        -- expect: FR + BE (18 rows total)

-- ABAC column mask: this role sees REDACTED site identities (site_name is tagged confidential):
SELECT DISTINCT site_name
FROM governance_demo.generation.generation_daily;   -- expect: single value 'REDACTED'

-- The "before/after": the same two queries as a metastore admin (no role
-- assumed) return all four countries. One assumed role + one ABAC policy is
-- the entire difference.
