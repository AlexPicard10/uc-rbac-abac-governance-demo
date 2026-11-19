-- ============================================================================
-- Unity Catalog RBAC + ABAC demo — 02 · Ontology / UC-semantics layer
-- ----------------------------------------------------------------------------
-- Prereq: run AFTER 00 (tables + asset_reference + comments) and 01 (grants/ABAC),
-- because the metric-view grants reference the role groups and the constraints
-- reference the dimension tables created in 00.
--
-- Adds the "modeled knowledge" that Databricks Genie's ontology searches:
--   1) PK/FK relationships (informational, RELY) — the join graph
--   2) Two certified METRIC VIEWS — governed, reusable KPIs (one per domain)
--   3) Grants on the metric views (least privilege, per role)
--   4) Certification tag (system.certification_status = certified)
--
-- GOVERNANCE NOTE: a metric view is a VIEW over the base fact table, and UC row
-- filters/column masks attach to the BASE TABLE and are enforced no matter how it
-- is queried. The geo row filter keys on session_user() (the assumed role), so the
-- metric views inherit it per role: the cross-domain role sees FR+BE KPIs only.
-- The views read the dimension tables with the OWNER's rights, so the roles need
-- SELECT only on the metric views, not on asset_reference.
-- ============================================================================
USE CATALOG governance_demo;

-- 1) PK / FK RELATIONSHIPS (informational: NOT ENFORCED RELY) --------------------
--    RELY lets the Genie ontology + the optimizer use the relationships for join
--    inference. Data satisfies them (synthetic + deterministic). Idempotent: drop
--    FKs then PKs first (CREATE OR REPLACE in 00 already clears them on a full run).
ALTER TABLE generation.generation_daily DROP CONSTRAINT IF EXISTS gen_country_fk;
ALTER TABLE generation.generation_daily DROP CONSTRAINT IF EXISTS gen_asset_fk;
ALTER TABLE heating.heating_consumption  DROP CONSTRAINT IF EXISTS heat_country_fk;
ALTER TABLE shared.country_reference     DROP CONSTRAINT IF EXISTS country_ref_pk;
ALTER TABLE generation.asset_reference   DROP CONSTRAINT IF EXISTS asset_ref_pk;

-- PK columns must be NOT NULL first.
ALTER TABLE shared.country_reference   ALTER COLUMN country_code SET NOT NULL;
ALTER TABLE generation.asset_reference ALTER COLUMN site_id      SET NOT NULL;

-- Primary keys on the two dimensions.
ALTER TABLE shared.country_reference   ADD CONSTRAINT country_ref_pk PRIMARY KEY (country_code) NOT ENFORCED RELY;
ALTER TABLE generation.asset_reference ADD CONSTRAINT asset_ref_pk  PRIMARY KEY (site_id)       NOT ENFORCED RELY;

-- Foreign keys from the facts to the dimensions (the join graph Genie can infer).
ALTER TABLE generation.generation_daily ADD CONSTRAINT gen_country_fk
  FOREIGN KEY (country_code) REFERENCES shared.country_reference (country_code) NOT ENFORCED RELY;
ALTER TABLE heating.heating_consumption ADD CONSTRAINT heat_country_fk
  FOREIGN KEY (country_code) REFERENCES shared.country_reference (country_code) NOT ENFORCED RELY;
ALTER TABLE generation.generation_daily ADD CONSTRAINT gen_asset_fk
  FOREIGN KEY (site_id) REFERENCES generation.asset_reference (site_id) NOT ENFORCED RELY;

-- 2) METRIC VIEWS (governed, reusable KPIs) ------------------------------------
--    version 1.1 YAML; every field/measure carries display_name/synonyms/comment/
--    format so both AI/BI dashboards and Genie understand the business meaning.
--    The YAML body must contain NO ';' (the driver splits statements on ';').
CREATE OR REPLACE VIEW generation.generation_metrics
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
source: governance_demo.generation.generation_daily
comment: "Governed renewable-generation KPIs (synthetic). A metric view over generation_daily, so the base-table ABAC geo row filter still applies - results reflect the querying role (cross-domain sees FR+BE)."
joins:
  - name: dim_asset
    source: governance_demo.generation.asset_reference
    "on": source.site_id = dim_asset.site_id
  - name: dim_country
    source: governance_demo.shared.country_reference
    "on": source.country_code = dim_country.country_code
dimensions:
  - name: Country
    expr: source.country_code
    synonyms: ["country", "country code", "geo"]
    comment: "ISO country code of the site (FR/BE/NL/DE). Governed by the ABAC geo row filter."
  - name: Country Name
    expr: dim_country.country_name
    synonyms: ["country name"]
  - name: Region
    expr: dim_country.region
  - name: Asset Type
    expr: source.asset_type
    synonyms: ["technology", "generation type", "wind or solar"]
    comment: "Generation technology: wind or solar."
  - name: Operating Month
    expr: "DATE_TRUNC('MONTH', source.activity_date)"
    synonyms: ["month", "activity month"]
measures:
  - name: Total Generation MWh
    expr: SUM(source.generation_mwh)
    display_name: Total Generation (MWh)
    synonyms: ["generation", "output", "energy produced", "total generation"]
    comment: "Sum of daily energy generated, in MWh. Additive across sites and days."
    format:
      type: number
      decimal_places:
        type: max
        places: 1
  - name: Avg Availability Pct
    expr: AVG(source.availability_pct)
    display_name: Avg Availability (%)
    synonyms: ["availability", "uptime", "technical availability"]
    comment: "Average technical availability of the fleet, in percent (0-100)."
    format:
      type: number
      decimal_places:
        type: max
        places: 1
  - name: Active Sites
    expr: COUNT(DISTINCT source.site_id)
    display_name: Active Sites
    synonyms: ["sites", "number of sites", "assets"]
    comment: "Distinct generation sites reporting output."
  - name: Capacity Factor Pct
    expr: 100 * SUM(source.generation_mwh) / SUM(dim_asset.capacity_mw * 24)
    display_name: Capacity Factor (%)
    synonyms: ["capacity factor", "utilization", "load factor"]
    comment: "Energy produced divided by (nameplate capacity x 24h), in percent. Wind ~55-62%, solar ~17-21%."
    format:
      type: number
      decimal_places:
        type: max
        places: 1
$$;

CREATE OR REPLACE VIEW heating.heating_metrics
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
source: governance_demo.heating.heating_consumption
comment: "Governed district-heating consumption KPIs (synthetic). A metric view over heating_consumption, so the base-table ABAC geo row filter still applies - results reflect the querying role (cross-domain sees FR+BE)."
joins:
  - name: dim_country
    source: governance_demo.shared.country_reference
    "on": source.country_code = dim_country.country_code
dimensions:
  - name: Country
    expr: source.country_code
    synonyms: ["country", "country code", "geo"]
    comment: "ISO country code (FR/BE/NL/DE). Governed by the ABAC geo row filter."
  - name: Country Name
    expr: dim_country.country_name
    synonyms: ["country name"]
  - name: Region
    expr: dim_country.region
  - name: Customer Segment
    expr: source.customer_segment
    synonyms: ["segment", "customer type", "customer segment"]
    comment: "Anonymized customer segment: Residential, Commercial or Industrial."
  - name: Month
    expr: "DATE_TRUNC('MONTH', source.activity_date)"
    synonyms: ["month", "consumption month"]
measures:
  - name: Total Consumption MWh
    expr: SUM(source.consumption_mwh)
    display_name: Total Consumption (MWh)
    synonyms: ["consumption", "energy consumed", "total consumption", "demand"]
    comment: "Sum of district-heating energy consumed, in MWh. Additive."
    format:
      type: number
      decimal_places:
        type: max
        places: 1
  - name: Avg Monthly Consumption MWh
    expr: AVG(source.consumption_mwh)
    display_name: Avg Monthly Consumption (MWh)
    synonyms: ["average consumption", "mean consumption"]
    comment: "Average consumption per segment-country-month cell, in MWh."
    format:
      type: number
      decimal_places:
        type: max
        places: 1
  - name: Served Segments
    expr: COUNT(DISTINCT source.customer_segment)
    display_name: Served Segments
    synonyms: ["segments", "number of segments"]
    comment: "Distinct customer segments served."
  - name: Served Countries
    expr: COUNT(DISTINCT source.country_code)
    display_name: Served Countries
    synonyms: ["countries", "number of countries"]
    comment: "Distinct countries served (reflects the active role entitlement)."
$$;

-- 3) GRANTS (least privilege) — SELECT on the metric views only ----------------
--    The views read the dimensions with the owner's rights, so roles need SELECT
--    on the metric view only. The base-table geo row filter still applies per role.
GRANT SELECT ON VIEW generation.generation_metrics TO `role_generation`;
GRANT SELECT ON VIEW generation.generation_metrics TO `role_cross_domain`;
GRANT SELECT ON VIEW heating.heating_metrics       TO `role_heating`;
GRANT SELECT ON VIEW heating.heating_metrics       TO `role_cross_domain`;

-- 4) CERTIFICATION — mark the KPIs as trusted ("modeled, certified knowledge").
--    Genie prioritizes certified assets; shows a Certified badge in Catalog/Discover.
ALTER VIEW generation.generation_metrics SET TAGS ('system.certification_status' = 'certified');
ALTER VIEW heating.heating_metrics       SET TAGS ('system.certification_status' = 'certified');
