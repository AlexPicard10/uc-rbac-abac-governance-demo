"""10 · Identity setup (account admin). Idempotent.

Creates the 6 account groups, wires ASSUME (member group -> group.assumer on its
role group), adds the presenter to the member groups (so roles are assumable),
and grants the role groups workspace access + warehouse CAN USE.

Run: python driver/10_identity_setup.py
Env: DEMO_PRESENTER=user@acme.com  (default: the workspace profile's current user)
"""
from __future__ import annotations
import sys
import _common as C
from databricks.sdk.service import iam
from databricks.sdk.service import sql as sqlsvc

ASSUMER = "roles/group.assumer"


def main() -> int:
    a = C.acct()
    w = C.ws()
    acc = a.config.account_id

    # 1) Create the 6 account groups (idempotent) ----------------------------
    existing = {g.display_name: g.id for g in a.groups.list(attributes="id,displayName")}
    ids = {}
    for name in C.MEMBER_GROUPS + C.ROLE_GROUPS:
        if name in existing:
            ids[name] = existing[name]; print(f"group exists : {name}")
        else:
            ids[name] = a.groups.create(display_name=name).id; print(f"group created: {name}")

    # Confirm RBAC is enabled: group.assumer must be assignable
    roles = a.access_control.get_assignable_roles_for_resource(
        resource=f"accounts/{acc}/groups/{ids[C.ROLE_GROUPS[0]]}")
    if ASSUMER not in [r.name for r in (roles.roles or [])]:
        print("ERROR: roles/group.assumer is not assignable — RBAC is not enabled in this account.")
        return 1

    # 2) Wire ASSUME: member group -> assumer on its role group (merge+etag) --
    for member, role in C.PAIRS:
        name = f"accounts/{acc}/groups/{ids[role]}/ruleSets/default"
        rs = a.access_control.get_rule_set(name=name, etag="")
        rules = list(rs.grant_rules or [])
        principal = f"groups/{member}"            # principals are referenced by NAME
        gr = next((x for x in rules if x.role == ASSUMER), None)
        if gr and principal in (gr.principals or []):
            print(f"assume wired : {member} -> {role}"); continue
        if gr:
            gr.principals = sorted(set((gr.principals or []) + [principal]))
        else:
            rules.append(iam.GrantRule(role=ASSUMER, principals=[principal]))
        a.access_control.update_rule_set(
            name=name, rule_set=iam.RuleSetUpdateRequest(name=name, grant_rules=rules, etag=rs.etag))
        print(f"assume set   : {member} -> {role}")

    # 3) Add the presenter to the member groups (so they can assume the roles)
    import os
    presenter = os.environ.get("DEMO_PRESENTER") or w.current_user.me().user_name
    users = list(a.users.list(filter=f"userName eq '{presenter}'", attributes="id,userName"))
    if not users:
        print(f"WARNING: presenter {presenter} not found at account level — add members manually.")
    else:
        uid = users[0].id
        for member in C.MEMBER_GROUPS:
            g = a.groups.get(ids[member])
            if uid in [m.value for m in (g.members or [])]:
                print(f"member ok    : {presenter} in {member}"); continue
            a.groups.patch(id=ids[member],
                schemas=[iam.PatchSchema.URN_IETF_PARAMS_SCIM_API_MESSAGES_2_0_PATCH_OP],
                operations=[iam.Patch(op=iam.PatchOp.ADD, path="members", value=[{"value": uid}])])
            print(f"member added : {presenter} -> {member}")

    # 4) Role groups need workspace access + SQL entitlement + warehouse CAN USE
    wsid = w.get_workspace_id()
    for role in C.ROLE_GROUPS:
        try:
            a.workspace_assignment.update(workspace_id=wsid, principal_id=int(ids[role]),
                permissions=[iam.WorkspacePermission.USER])
            print(f"workspace acc: {role}")
        except Exception as e:
            print(f"workspace acc ERR {role}: {repr(e)[:120]}")

    # workspace_assignment grants workspace membership but NOT the fine-grained
    # entitlement; set least-privilege entitlements per role via workspace SCIM
    # (federated group id == account group id). Domain roles = Databricks SQL access;
    # cross-domain role = Consumer access (workspace-consume) -> Genie/dashboards only.
    for role in C.ROLE_GROUPS:
        ents = C.ROLE_ENTITLEMENTS[role]
        body = {"schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [{"op": "replace", "path": "entitlements",
                                "value": [{"value": e} for e in ents]}]}
        try:
            w.api_client.do("PATCH", f"/api/2.0/preview/scim/v2/Groups/{ids[role]}", body=body)
            print(f"entitlements : {role} -> {ents}")
        except Exception as e:
            print(f"entitlements ERR {role}: {repr(e)[:120]}")

    wid = C.warehouse_id(w)
    acl = [sqlsvc.WarehouseAccessControlRequest(group_name=r,
            permission_level=sqlsvc.WarehousePermissionLevel.CAN_USE) for r in C.ROLE_GROUPS]
    w.warehouses.update_permissions(warehouse_id=wid, access_control_list=acl)
    print(f"warehouse CAN_USE granted to role groups on {wid}")

    print("\nIDENTITY SETUP: done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
