"""90 · Cleanup — removes ONLY demo-created objects, in dependency order.
Leaves the catalog itself (it pre-existed) unless DEMO_DROP_CATALOG=1.

Run: python driver/90_cleanup.py --yes
"""
from __future__ import annotations
import os, sys
import _common as C


def main() -> int:
    if "--yes" not in sys.argv:
        print("Refusing to delete without --yes. Re-run: python driver/90_cleanup.py --yes")
        return 2
    w = C.ws(); a = C.acct(); wid = C.warehouse_id(w)

    # 0) AI/BI dashboard -> trash (a workspace object; NOT removed by DROP SCHEMA CASCADE,
    #    unlike the metric views + asset_reference which live in the demo schemas).
    try:
        for d in w.lakeview.list():
            if d.display_name == C.DASHBOARD_NAME and (d.lifecycle_state is None or getattr(d.lifecycle_state, "value", "") != "TRASHED"):
                w.lakeview.trash(d.dashboard_id); print(f"trashed dashboard: {C.DASHBOARD_NAME} ({d.dashboard_id})")
    except Exception as e:
        print("dashboard cleanup:", repr(e)[:120])

    # 1) Genie spaces -> trash (both domain spaces + any legacy combined space)
    demo_titles = {s["title"] for s in C.GENIE_SPACES} | set(C.LEGACY_GENIE_TITLES)
    try:
        for s in (getattr(w.genie.list_spaces(), "spaces", None) or []):
            if (s.title or "") in demo_titles:
                w.genie.trash_space(space_id=s.space_id); print(f"trashed Genie space: {s.title} ({s.space_id})")
    except Exception as e:
        print("genie cleanup:", repr(e)[:120])

    # 2) Discover Pages -> delete (they live in our domains; remove before the domains)
    try:
        my_res = {f"domains/{d.domain_id}" for d in w.domains.list_domains() if d.tag_key in C.DOMAIN_TAGS}
        for p in C.knowledge_pages(w, my_res):
            w.api_client.do("DELETE", f"/api/2.0/knowledge/{p.get('name')}")
            print(f"deleted page: {p.get('display_name')}")
    except Exception as e:
        print("page cleanup:", repr(e)[:120])

    # 3) Discover domains -> delete (children before parent, before dropping their tags)
    try:
        by_tag = {d.tag_key: d for d in w.domains.list_domains()}
        for key in [C.DOMAIN_GEN_TAG, C.DOMAIN_HEAT_TAG, C.DOMAIN_PARENT_TAG]:
            d = by_tag.get(key)
            if d:
                w.domains.delete_domain(name=d.name); print(f"deleted domain: {key}")
    except Exception as e:
        print("domain cleanup:", repr(e)[:120])

    # 3) ABAC policies -> schemas (CASCADE drops tables/UDF + every column/asset tag
    #    assignment) -> governed tags LAST, once nothing references them.
    #    NOTE: DROP POLICY / DROP GOVERNED TAG do NOT accept IF EXISTS; on an already
    #    clean workspace the "not found" is harmless — the loop prints ERR and continues.
    steps = [
        f"DROP POLICY {C.POLICY_NAME} ON CATALOG {C.CATALOG}",
        f"DROP POLICY {C.MASK_POLICY_NAME} ON CATALOG {C.CATALOG}",
        f"DROP SCHEMA IF EXISTS {C.CATALOG}.generation CASCADE",
        f"DROP SCHEMA IF EXISTS {C.CATALOG}.heating CASCADE",
        f"DROP SCHEMA IF EXISTS {C.CATALOG}.shared CASCADE",
        f"DROP SCHEMA IF EXISTS {C.CATALOG}.gov CASCADE",
        f"DROP GOVERNED TAG {C.GOVERNED_TAG}",
        f"DROP GOVERNED TAG {C.CONFIDENTIAL_TAG}",
    ] + [f"DROP GOVERNED TAG `{t}`" for t in C.DOMAIN_TAGS]
    if os.environ.get("DEMO_DROP_CATALOG") == "1":
        steps.append(f"DROP CATALOG IF EXISTS {C.CATALOG} CASCADE")
    for s in steps:
        ok, res = C.run_sql(w, s, wid, catalog=None)
        print(f"  {'OK' if ok else 'ERR'}  {s}" + ("" if ok else f" -> {res}"))

    # 5) Delete the 6 account groups (removes assumer rules, membership, ACLs, assignments)
    for name in C.MEMBER_GROUPS + C.ROLE_GROUPS:
        gid = C.group_id(a, name)
        if gid:
            try:
                a.groups.delete(id=gid); print(f"deleted group {name}")
            except Exception as e:
                print(f"group delete {name}: {repr(e)[:120]}")
        else:
            print(f"group absent {name}")

    print("\nCLEANUP: done. (Warehouse, workspace, and the catalog itself were left intact.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
