"""20 · Governance (workspace). Executes the SQL that builds the data, the
governed tag, the grants and the ABAC policy on the SQL warehouse.

Prereq: driver/10_identity_setup.py (the ABAC policy + grants reference the roles).
Run: python driver/20_governance.py
"""
from __future__ import annotations
import os, sys
import _common as C

HERE = os.path.dirname(os.path.abspath(__file__))
SQL_DIR = os.path.join(HERE, "..", "sql")
FILES = ["00_generate_data.sql", "01_governed_tag_abac.sql", "02_ontology_metrics.sql"]

# Statements that are OK to "fail" because the object already exists (idempotency).
BENIGN = ("already exists", "already been assigned", "TAG_ALREADY_EXISTS")


def main() -> int:
    w = C.ws()
    wid = C.warehouse_id(w)
    print(f"running governance SQL on warehouse {wid}, catalog {C.CATALOG}\n")
    for fname in FILES:
        path = os.path.join(SQL_DIR, fname)
        print(f"== {fname} ==")
        for stmt in C.split_sql(path):
            ok, res = C.run_sql(w, stmt, wid)
            label = stmt.split("\n")[0][:70]
            if ok:
                print(f"  OK   {label}")
            elif any(b.lower() in str(res).lower() for b in BENIGN):
                print(f"  SKIP {label}  (already exists)")
            elif "tag policy key" in str(res).lower():
                # A just-created governed tag isn't registered for has_tag() in an ABAC
                # policy yet (governed-tag changes propagate in ~tens of seconds). Wait
                # and retry once — enough for a fresh deploy where tag + policy are close.
                import time
                print(f"  WAIT {label}  (governed-tag propagation; retry in 25s)")
                time.sleep(25)
                ok, res = C.run_sql(w, stmt, wid)
                if ok:
                    print(f"  OK   {label}  (after retry)")
                else:
                    print(f"  FAIL {label}\n       -> {res}")
                    return 1
            else:
                print(f"  FAIL {label}\n       -> {res}")
                return 1
    # The ABAC row filter reads gov.role_country_entitlements under the function
    # OWNER's rights (definer context). The owner needs an EXPLICIT USE CATALOG —
    # ownership of the schema/table is NOT enough, and metastore-admin bypass does
    # not apply in the definer context. Without this, the role's queries fail with
    # "the owner of one of the underlying resources failed an authorization check".
    me = w.current_user.me().user_name
    ok, res = C.run_sql(w, f"GRANT USE CATALOG ON CATALOG {C.CATALOG} TO `{me}`", wid)
    print(f"  {'OK  ' if ok else 'WARN'} grant USE CATALOG to row-filter owner {me}" + ("" if ok else f" -> {res}"))

    # quick proof the one policy is on both tables
    for t in (C.GEN_TABLE, C.HEAT_TABLE):
        ok, rows = C.run_sql(w, f"SHOW EFFECTIVE POLICIES ON TABLE {t}", wid)
        names = [r[0] for r in rows] if ok else []
        print(f"effective policies on {t}: {names}")
    print("\nGOVERNANCE: done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
