-- ============================================================================
-- Unity Catalog RBAC + ABAC demo — 01 · Governed tag, grants & ABAC row filter
-- ----------------------------------------------------------------------------
-- Prereq: run AFTER the account groups/roles exist (driver/10_identity_setup.py),
-- because the ABAC policy and the GRANTs reference the role groups by name.
--
-- Demonstrates the ABAC "steward loop": classify -> tag -> ONE policy protects
-- every matching table. One governed tag on `country_code`, one catalog-scoped
-- row-filter policy that covers BOTH domain tables.
-- ============================================================================
USE CATALOG governance_demo;

-- 1) GOVERNED TAGS (account-level) — value-less COLUMN MARKERS. Both ABAC policies
--    bind by NAME via has_tag(); the tags carry no value. Declare BOTH up front so
--    each is registered well before the policy that references it (a freshly created
--    governed tag takes a few seconds to be usable in has_tag).
--      country       -> country_code  (geo row filter, step 5)
--      confidential  -> site_name     (column mask, step 6)
--    A row's country is the column's own value; which countries a role may see comes
--    from the entitlement table (step 3b), keyed on the assumed role — not the tag.
CREATE GOVERNED TAG country
  DESCRIPTION 'Marks the country_code column so the ABAC row-filter policy binds via has_tag(); access is decided by the entitlement table.';
CREATE GOVERNED TAG confidential
  DESCRIPTION 'Marks a confidential column so the ABAC column-mask policy binds via has_tag(); no value needed.';

-- 2) Put the markers on the columns (no value needed).
ALTER TABLE generation.generation_daily ALTER COLUMN country_code SET TAGS ('country' = '');
ALTER TABLE heating.heating_consumption  ALTER COLUMN country_code SET TAGS ('country' = '');
ALTER TABLE generation.generation_daily ALTER COLUMN site_name    SET TAGS ('confidential' = '');

-- 3) Least-privilege UC grants — to the ROLE groups only.
--    Member groups get NO direct data access; they only hold ASSUME on a role.
GRANT USE CATALOG ON CATALOG governance_demo TO `role_generation`;
GRANT USE CATALOG ON CATALOG governance_demo TO `role_heating`;
GRANT USE CATALOG ON CATALOG governance_demo TO `role_cross_domain`;

GRANT USE SCHEMA ON SCHEMA generation TO `role_generation`;
GRANT USE SCHEMA ON SCHEMA generation TO `role_cross_domain`;
GRANT USE SCHEMA ON SCHEMA heating    TO `role_heating`;
GRANT USE SCHEMA ON SCHEMA heating    TO `role_cross_domain`;

GRANT SELECT ON TABLE generation.generation_daily TO `role_generation`;
GRANT SELECT ON TABLE generation.generation_daily TO `role_cross_domain`;
GRANT SELECT ON TABLE heating.heating_consumption  TO `role_heating`;
GRANT SELECT ON TABLE heating.heating_consumption  TO `role_cross_domain`;

-- Shared reference table: readable by ALL three roles (reference data, not row-filtered).
GRANT USE SCHEMA ON SCHEMA shared TO `role_generation`;
GRANT USE SCHEMA ON SCHEMA shared TO `role_heating`;
GRANT USE SCHEMA ON SCHEMA shared TO `role_cross_domain`;
GRANT SELECT ON TABLE shared.country_reference TO `role_generation`;
GRANT SELECT ON TABLE shared.country_reference TO `role_heating`;
GRANT SELECT ON TABLE shared.country_reference TO `role_cross_domain`;

-- 3b) ENTITLEMENT (mapping) TABLE — best practice: per-role row filters keyed on
--     the assumed role (session_user()). One row per role; 'ALL' = every country.
--     Docs: security/auth/rbac/abac-interaction#per-project-row-filters-keyed-on-the-assumed-role
CREATE OR REPLACE TABLE gov.role_country_entitlements (
  role_name    STRING COMMENT 'Assumed-role name as returned by session_user()',
  country_code STRING COMMENT "ISO-2 country code, or 'ALL' for every country"
) COMMENT 'Row-filter entitlements keyed on the assumed role (session_user()); ALL = all countries';

INSERT INTO gov.role_country_entitlements VALUES
  ('role_generation',   'ALL'),   -- domain role: all countries (within its one domain)
  ('role_heating',      'ALL'),   -- domain role: all countries
  ('role_cross_domain', 'FR'),    -- cross-domain: France
  ('role_cross_domain', 'BE');    -- cross-domain: Belgium

-- IMPORTANT (definer-context access): the row-filter UDF below reads THIS table under
-- the function OWNER's rights. The owner needs an EXPLICIT `USE CATALOG` on this catalog
-- — owning the schema/table is NOT enough, and metastore-admin bypass does NOT apply in
-- the definer context. Without it, role queries fail with "the owner of one of the
-- underlying resources failed an authorization check" (SQLSTATE 42501). Grant it to
-- whoever deploys/owns these objects (driver/20_governance.py does this automatically):
--   GRANT USE CATALOG ON CATALOG governance_demo TO `<owner-user-or-group>`;

-- 4) Row-filter UDF — keyed on the ACTIVE identity (session_user() = the assumed
--    role) via an EXISTS against the entitlement table. 'ALL' means no restriction.
--    *** The crux of RBAC + ABAC ***  We use session_user() (NOT
--    is_account_group_member — a role is not a member of itself). EXISTS=false ->
--    row excluded (fail-closed); safe because the policy TO-targets only the 3 roles,
--    all of which have rows. The querying role does NOT need access to this table —
--    the engine applies the filter with the function's definer rights.
CREATE OR REPLACE FUNCTION gov.country_entitlement_filter(row_country STRING)
RETURNS BOOLEAN
COMMENT 'ABAC row filter keyed on the assumed role via gov.role_country_entitlements; ALL = all countries'
RETURN EXISTS (
  SELECT 1 FROM governance_demo.gov.role_country_entitlements e
  WHERE e.role_name = session_user()
    AND (e.country_code = 'ALL' OR e.country_code = row_country)
);

-- 5) ONE catalog-scoped ABAC row-filter policy, covers BOTH tables via the tag.
--    MATCH COLUMNS has_tag('country') binds the tagged country_code column (cc);
--    USING COLUMNS (cc) passes just that column to the UDF (which looks up the role).
CREATE OR REPLACE POLICY country_row_filter
ON CATALOG governance_demo
COMMENT 'ABAC row filter: shows each role only its entitled countries via gov.role_country_entitlements, keyed on session_user()'
ROW FILTER governance_demo.gov.country_entitlement_filter
TO `role_generation`, `role_heating`, `role_cross_domain`
FOR TABLES
MATCH COLUMNS has_tag('country') AS cc
USING COLUMNS (cc);

-- Verify the single policy lands on BOTH tables:
--   SHOW EFFECTIVE POLICIES ON TABLE generation.generation_daily;
--   SHOW EFFECTIVE POLICIES ON TABLE heating.heating_consumption;

-- 6) ABAC COLUMN MASK — the other half of tag-driven table protection. The
--    confidential marker tag + its column assignment are declared in step 1-2.
--    (Note: ABAC GRANT policies target AI securables — models/services/MCP/agents —
--     NOT tables; table SELECT stays a direct GRANT. Tag-driven *table* control = row
--     filters + column masks.) Here: redact a confidential column for the cross-domain role.
CREATE OR REPLACE FUNCTION gov.mask_site(site_name STRING)
RETURNS STRING
COMMENT 'Column mask: the cross-domain role sees a redacted site identity; the domain owner sees it in full'
RETURN CASE WHEN session_user() = 'role_cross_domain' THEN 'REDACTED' ELSE site_name END;

-- Single column-mask policy; ON COLUMN passes the tagged column to the mask UDF
-- (no USING COLUMNS needed for a one-argument mask).
CREATE OR REPLACE POLICY mask_confidential
ON CATALOG governance_demo
COMMENT 'ABAC column mask: redacts columns tagged confidential for the cross-domain role'
COLUMN MASK governance_demo.gov.mask_site
TO `role_generation`, `role_cross_domain`
FOR TABLES
MATCH COLUMNS has_tag('confidential') AS c
ON COLUMN c;
