-- ============================================================================
-- Unity Catalog RBAC + ABAC demo — 11 · "How it works" evidence view
-- ----------------------------------------------------------------------------
-- Run as the admin/steward (no role assumed) to show the governance wiring:
-- grants, the governed tag, the single ABAC policy on both tables, and audit.
-- ============================================================================
USE CATALOG governance_demo;

-- 1) The governed tag marks country_code in BOTH domains. tag_value is empty —
--    the tag is a pure marker; the policy binds by NAME via has_tag(). -----------
SELECT schema_name, table_name, column_name, tag_name, tag_value
FROM information_schema.column_tags
WHERE tag_name = 'country'
ORDER BY schema_name;

-- 2) ONE ABAC policy, its type, scope and target principals -------------------
SELECT policy_name, policy_type, on_securable_type, to_principals, match_columns
FROM information_schema.abac_policy_definitions
WHERE policy_name = 'country_row_filter';

-- 3) The SAME policy is effective on BOTH tables (tag-driven, one definition) --
SHOW EFFECTIVE POLICIES ON TABLE generation.generation_daily;
SHOW EFFECTIVE POLICIES ON TABLE heating.heating_consumption;

-- 4) The row-filter logic (keys on the ACTIVE identity, not group membership) -
DESCRIBE FUNCTION EXTENDED gov.country_entitlement_filter;

-- 5) Least-privilege grants — data access is on the ROLE groups only ----------
SHOW GRANTS ON TABLE generation.generation_daily;
SHOW GRANTS ON TABLE heating.heating_consumption;

-- 6) Audit evidence: RBAC separates "who ran it" (run_by) from "which role was
--    used for authorization" (run_as). Audit can lag minutes; widen the window
--    if empty. Column paths may vary slightly by workspace/schema version.
SELECT event_time,
       identity_metadata.run_by  AS run_by,
       identity_metadata.run_as  AS run_as,
       action_name
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 1 DAY
  AND identity_metadata.run_as IS NOT NULL
  AND identity_metadata.run_as <> identity_metadata.run_by
ORDER BY event_time DESC
LIMIT 50;
