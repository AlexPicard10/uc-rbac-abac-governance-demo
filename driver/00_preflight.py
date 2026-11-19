"""00 · Preflight — READ-ONLY probe. Aborts with a clear report if a prerequisite
is missing, before anything is built. Run: python driver/00_preflight.py"""
from __future__ import annotations
import sys
import _common as C


def main() -> int:
    ok = True
    w = C.ws()
    me = w.current_user.me()
    print(f"workspace user : {me.user_name}")
    is_ws_admin = any((g.display or "") == "admins" for g in (me.groups or []))
    print(f"workspace admin: {is_ws_admin}")

    try:
        a = C.acct()
        n = sum(1 for _ in a.groups.list(attributes="id"))
        print(f"account admin  : yes (can list {n} account groups)")
    except Exception as e:
        print(f"account admin  : NO / not reachable -> {repr(e)[:140]}")
        ok = False

    ms = w.metastores.summary()
    print(f"metastore      : {ms.name} ({ms.region}, {ms.cloud})")

    wid = C.warehouse_id(w)
    wh = w.warehouses.get(wid)
    print(f"warehouse      : {wh.name} [{wh.warehouse_type.value}] serverless={wh.enable_serverless_compute} id={wid}")
    if not (wh.enable_serverless_compute or (wh.warehouse_type and wh.warehouse_type.value == "PRO")):
        print("  WARNING: ABAC needs serverless or DBR 16.4+. A classic warehouse may fail closed.")

    # ABAC availability (system view present?)
    okq, res = C.run_sql(w, "SELECT count(*) FROM system.information_schema.abac_policy_definitions", wid, catalog=None)
    print(f"ABAC available : {okq}" + ("" if okq else f" -> {res}"))
    ok = ok and okq

    # RBAC: is group.assumer assignable on a group resource? (needs a role group to exist,
    # so this is best-effort; identity_setup confirms definitively.)
    try:
        a = C.acct()
        rid = C.group_id(a, C.ROLE_GROUPS[0])
        if rid:
            roles = a.access_control.get_assignable_roles_for_resource(
                resource=f"accounts/{a.config.account_id}/groups/{rid}")
            names = [r.name for r in (roles.roles or [])]
            print(f"RBAC assumer   : {'roles/group.assumer' in names} (assignable roles: {names})")
        else:
            print("RBAC assumer   : (role group not created yet — confirmed during identity_setup)")
    except Exception as e:
        print(f"RBAC check     : {repr(e)[:140]}")

    print("\nPREFLIGHT:", "OK" if ok else "ISSUES FOUND (see above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
