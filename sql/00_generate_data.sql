-- ============================================================================
-- Unity Catalog RBAC + ABAC demo — 00 · Synthetic data (Domain 1 + Domain 2)
-- ----------------------------------------------------------------------------
-- Creates the demo catalog/schemas and two small, DETERMINISTIC synthetic
-- tables. All data is synthetic and bears no relation to any real
-- company's operations, customers, or employees.
--
-- Run on the serverless / pro SQL warehouse (ABAC needs serverless or DBR 16.4+).
-- Idempotent: safe to re-run (CREATE ... IF NOT EXISTS / CREATE OR REPLACE).
-- The only value to change for another workspace is the catalog name below.
-- ============================================================================

CREATE CATALOG IF NOT EXISTS governance_demo
  COMMENT 'Unity Catalog RBAC + ABAC demo (synthetic data only)';
USE CATALOG governance_demo;

CREATE SCHEMA IF NOT EXISTS generation COMMENT 'Domain 1 — renewable generation operations (synthetic)';
CREATE SCHEMA IF NOT EXISTS heating    COMMENT 'Domain 2 — district-heating energy consumption (synthetic)';
CREATE SCHEMA IF NOT EXISTS shared     COMMENT 'Shared cross-domain reference data (synthetic)';
CREATE SCHEMA IF NOT EXISTS gov        COMMENT 'Governance objects: row-filter UDF(s) for ABAC policies';

-- On a RE-RUN, drop the metric views (sql/02) first so the base tables below can be
-- replaced cleanly without a dependent-object conflict. sql/02 recreates them.
DROP VIEW IF EXISTS generation.generation_metrics;
DROP VIEW IF EXISTS heating.heating_metrics;

-- ---------------------------------------------------------------------------
-- Domain 1: renewable generation operations
--   site/asset, country, date, generation (MWh), availability (%)
-- 8 sites across FR/BE/NL/DE x 7 days = 56 rows (FR = 14, a clean 25% subset).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE generation.generation_daily
COMMENT 'SYNTHETIC renewable generation (MWh) & availability by site/country/date. Not real data.'
AS
WITH sites AS (
  SELECT * FROM VALUES
    ('FR-WND-01','Dunkerque Wind','FR','wind'),
    ('FR-SOL-02','Fos-sur-Mer Solar','FR','solar'),
    ('BE-WND-01','Zeebrugge Wind','BE','wind'),
    ('BE-SOL-02','Antwerp Solar','BE','solar'),
    ('NL-WND-01','Eemshaven Wind','NL','wind'),
    ('NL-SOL-02','Rotterdam Solar','NL','solar'),
    ('DE-WND-01','Bremerhaven Wind','DE','wind'),
    ('DE-SOL-02','Munich Solar','DE','solar')
  AS t(site_id, site_name, country_code, asset_type)
),
days AS (SELECT date_add(DATE'2025-01-01', x) AS d FROM (SELECT explode(sequence(0,6)) AS x))
SELECT
  s.site_id, s.site_name, s.country_code, s.asset_type,
  d.d AS activity_date,
  round((CASE WHEN s.asset_type='wind' THEN 100 ELSE 70 END) + pmod(hash(concat(s.site_id, d.d)), 40), 2) AS generation_mwh,
  round(85 + pmod(hash(concat('av', s.site_id, d.d)), 15), 1) AS availability_pct
FROM sites s CROSS JOIN days d;

-- ---------------------------------------------------------------------------
-- Domain 1 dimension: renewable asset/site registry (the "sites" dimension).
--   One row per site_id in generation_daily. Carries nameplate capacity (MW),
--   technology and commissioning year — the authoritative "what is this asset"
--   reference that turns generation_daily.site_id into a governed star-schema
--   fact. capacity_mw is the denominator of the capacity-factor KPI (metric view).
--   capacity_mw is sized so wind runs ~55-62% and solar ~17-21% capacity factor.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE generation.asset_reference
COMMENT 'SYNTHETIC renewable asset/site registry (nameplate capacity MW, technology, commissioning year) — dimension for generation.generation_daily. Not real data.'
AS SELECT * FROM VALUES
  ('FR-WND-01','wind',   8, 2017),
  ('FR-SOL-02','solar', 18, 2019),
  ('BE-WND-01','wind',   9, 2016),
  ('BE-SOL-02','solar', 20, 2020),
  ('NL-WND-01','wind',   8, 2018),
  ('NL-SOL-02','solar', 22, 2021),
  ('DE-WND-01','wind',  10, 2015),
  ('DE-SOL-02','solar', 18, 2022)
AS t(site_id, asset_type, capacity_mw, commissioned_year);

-- ---------------------------------------------------------------------------
-- Domain 2: district-heating energy consumption
--   anonymized customer segment, country, month, consumption (MWh)
-- 3 segments x FR/BE/NL/DE x 3 months = 36 rows (FR = 9, a clean 25% subset).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE heating.heating_consumption
COMMENT 'SYNTHETIC district-heating consumption (MWh) by anonymized customer segment/country/month. Not real data.'
AS
WITH segs AS (SELECT * FROM VALUES ('Residential'),('Commercial'),('Industrial') AS t(customer_segment)),
countries AS (SELECT * FROM VALUES ('FR'),('BE'),('NL'),('DE') AS t(country_code)),
months AS (SELECT add_months(DATE'2025-01-01', x) AS m FROM (SELECT explode(sequence(0,2)) AS x))
SELECT
  concat(substr(upper(s.customer_segment),1,3),'-',c.country_code) AS segment_id,
  s.customer_segment, c.country_code,
  m.m AS activity_date,
  round((CASE s.customer_segment WHEN 'Residential' THEN 500 WHEN 'Commercial' THEN 1200 ELSE 3000 END)
        * (0.8 + pmod(hash(concat(s.customer_segment, c.country_code, m.m)), 40)/100.0), 2) AS consumption_mwh
FROM segs s CROSS JOIN countries c CROSS JOIN months m;

-- ---------------------------------------------------------------------------
-- Shared cross-domain reference: a country dimension used by BOTH domains.
-- Reference data is broadly readable (granted to all three roles) and is NOT
-- row-filtered — joins/labels need every country. Demonstrates a shared asset.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE shared.country_reference
COMMENT 'SYNTHETIC shared country dimension used by BOTH domains (generation + heating). Not real data.'
AS SELECT * FROM VALUES
  ('FR','France','Western Europe','EUR'),
  ('BE','Belgium','Western Europe','EUR'),
  ('NL','Netherlands','Western Europe','EUR'),
  ('DE','Germany','Western Europe','EUR')
AS t(country_code, country_name, region, currency);

-- Quick admin-view sanity check (as a metastore admin you see ALL countries here):
--   SELECT country_code, count(*) FROM generation.generation_daily GROUP BY country_code;  -- BE/DE/FR/NL = 14 each
--   SELECT country_code, count(*) FROM heating.heating_consumption GROUP BY country_code;   -- BE/DE/FR/NL = 9 each

-- ===========================================================================
-- COLUMN COMMENTS (business meaning + usage) — part of the Unity Catalog
-- "ontology": rich descriptions make tables self-documenting and feed Genie's
-- natural-language understanding. Re-applied after each CREATE OR REPLACE.
-- ===========================================================================
ALTER TABLE generation.generation_daily ALTER COLUMN site_id         COMMENT 'Unique asset/site identifier (e.g. FR-WND-01). Foreign key to generation.asset_reference. Pattern: <country>-<WND|SOL>-<nn>.';
ALTER TABLE generation.generation_daily ALTER COLUMN site_name       COMMENT 'Human-readable site name. CONFIDENTIAL: masked to REDACTED for the cross-domain role by the ABAC column mask.';
ALTER TABLE generation.generation_daily ALTER COLUMN country_code    COMMENT 'ISO-3166 alpha-2 country of the site (FR/BE/NL/DE). Foreign key to shared.country_reference; governed by the ABAC geo row filter.';
ALTER TABLE generation.generation_daily ALTER COLUMN asset_type      COMMENT 'Generation technology: wind or solar.';
ALTER TABLE generation.generation_daily ALTER COLUMN activity_date   COMMENT 'Operating day of the reading (daily grain).';
ALTER TABLE generation.generation_daily ALTER COLUMN generation_mwh  COMMENT 'Energy generated that day, in megawatt-hours (MWh). Additive across sites and days.';
ALTER TABLE generation.generation_daily ALTER COLUMN availability_pct COMMENT 'Technical availability that day, in percent (0-100). Averaged, not summed.';

ALTER TABLE heating.heating_consumption ALTER COLUMN segment_id       COMMENT 'Synthetic key for a customer-segment x country cell (e.g. RES-FR).';
ALTER TABLE heating.heating_consumption ALTER COLUMN customer_segment COMMENT 'Anonymized customer segment: Residential, Commercial or Industrial.';
ALTER TABLE heating.heating_consumption ALTER COLUMN country_code     COMMENT 'ISO-3166 alpha-2 country (FR/BE/NL/DE). Foreign key to shared.country_reference; governed by the ABAC geo row filter.';
ALTER TABLE heating.heating_consumption ALTER COLUMN activity_date    COMMENT 'First day of the consumption month (monthly grain).';
ALTER TABLE heating.heating_consumption ALTER COLUMN consumption_mwh  COMMENT 'District-heating energy consumed that month, in MWh. Additive.';

ALTER TABLE shared.country_reference ALTER COLUMN country_code COMMENT 'ISO-3166 alpha-2 country code. Primary key; referenced by both domain fact tables.';
ALTER TABLE shared.country_reference ALTER COLUMN country_name COMMENT 'Full country name, for display and Genie labelling.';
ALTER TABLE shared.country_reference ALTER COLUMN region       COMMENT 'Geographic grouping (e.g. Western Europe).';
ALTER TABLE shared.country_reference ALTER COLUMN currency     COMMENT 'ISO-4217 currency code used in the country.';

ALTER TABLE generation.asset_reference ALTER COLUMN site_id           COMMENT 'Unique asset/site identifier (e.g. FR-WND-01). Primary key; referenced by generation.generation_daily.';
ALTER TABLE generation.asset_reference ALTER COLUMN asset_type        COMMENT 'Generation technology: wind or solar.';
ALTER TABLE generation.asset_reference ALTER COLUMN capacity_mw       COMMENT 'Nameplate (installed) capacity in megawatts (MW). Denominator of the capacity-factor KPI.';
ALTER TABLE generation.asset_reference ALTER COLUMN commissioned_year COMMENT 'Year the asset entered commercial operation.';
