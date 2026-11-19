#!/usr/bin/env bash
# One-time CLI profile setup for the Unity Catalog RBAC + ABAC demo.
# Creates a workspace profile and an account profile (both OAuth / browser login).
#
# Usage:
#   WS_HOST=https://dbc-00000000-0000.cloud.databricks.com/ \
#   ACCOUNT_ID=00000000-0000-0000-0000-000000000000 \
#   bash scripts/setup_profiles.sh
set -euo pipefail

WS_HOST="${WS_HOST:?set WS_HOST to your workspace URL}"
ACCOUNT_ID="${ACCOUNT_ID:?set ACCOUNT_ID (from the account console)}"
WS_PROFILE="${DEMO_WS_PROFILE:-uc-gov}"
ACCT_PROFILE="${DEMO_ACCT_PROFILE:-uc-gov-acct}"

echo "1/2 Workspace profile '$WS_PROFILE' (browser login)…"
databricks auth login --host "$WS_HOST" --profile "$WS_PROFILE"

echo "2/2 Account profile '$ACCT_PROFILE' (browser login)…"
databricks auth login --account-id "$ACCOUNT_ID" --host https://accounts.cloud.databricks.com --profile "$ACCT_PROFILE"

echo "Done. Verify:  databricks current-user me --profile $WS_PROFILE"
