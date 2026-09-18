#!/usr/bin/env bash
# One-time Azure Cloud Shell setup for GitHub Actions OIDC deployment.
# Creates no client secret. The resulting identity can deploy only to this resource group.
set -euo pipefail

: "${GITHUB_REPOSITORY:=Sajibv1/gridwise-llm}"
: "${GITHUB_OWNER_ID:=215350998}"
: "${GITHUB_REPOSITORY_ID:=1375947266}"
: "${RESOURCE_GROUP:=gridwise-fest-rg}"
: "${ENTRA_APP_NAME:=gridwise-github-deployer}"

SUBSCRIPTION_ID="$(az account show --query id --output tsv)"
TENANT_ID="$(az account show --query tenantId --output tsv)"
SCOPE="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}"

APP_OBJECT_ID="$(az ad app list --display-name "$ENTRA_APP_NAME" --query '[0].id' --output tsv)"
if [[ -z "$APP_OBJECT_ID" ]]; then
  APP_OBJECT_ID="$(az ad app create --display-name "$ENTRA_APP_NAME" --query id --output tsv)"
fi
APP_CLIENT_ID="$(az ad app show --id "$APP_OBJECT_ID" --query appId --output tsv)"

if ! az ad sp show --id "$APP_CLIENT_ID" >/dev/null 2>&1; then
  az ad sp create --id "$APP_CLIENT_ID" >/dev/null
fi

ROLE_COUNT="$(az role assignment list --assignee "$APP_CLIENT_ID" --scope "$SCOPE" --query "length([?roleDefinitionName=='Contributor'])" --output tsv)"
if [[ "$ROLE_COUNT" == "0" ]]; then
  az role assignment create \
    --assignee "$APP_CLIENT_ID" \
    --role Contributor \
    --scope "$SCOPE" \
    --only-show-errors >/dev/null
fi

FEDERATED_CREDENTIAL_NAME="github-main-deploy"
FEDERATED_CREDENTIAL_COUNT="$(az ad app federated-credential list \
  --id "$APP_OBJECT_ID" \
  --query "length([?name=='${FEDERATED_CREDENTIAL_NAME}'])" \
  --output tsv)"
FEDERATED_SUBJECT="repo:${GITHUB_REPOSITORY%%/*}@${GITHUB_OWNER_ID}/${GITHUB_REPOSITORY#*/}@${GITHUB_REPOSITORY_ID}:ref:refs/heads/main"
FEDERATED_CREDENTIAL_JSON="$(printf \
  '{"issuer":"https://token.actions.githubusercontent.com","subject":"%s","description":"GitHub Actions deployment from main","audiences":["api://AzureADTokenExchange"]}' \
  "$FEDERATED_SUBJECT")"
if [[ "$FEDERATED_CREDENTIAL_COUNT" == "0" ]]; then
  FEDERATED_CREDENTIAL_JSON="$(printf \
    '{"name":"%s",%s' \
    "$FEDERATED_CREDENTIAL_NAME" "${FEDERATED_CREDENTIAL_JSON#\{}")"
  az ad app federated-credential create \
    --id "$APP_OBJECT_ID" \
    --parameters "$FEDERATED_CREDENTIAL_JSON" \
    --only-show-errors >/dev/null
else
  az ad app federated-credential update \
    --id "$APP_OBJECT_ID" \
    --federated-credential-id "$FEDERATED_CREDENTIAL_NAME" \
    --parameters "$FEDERATED_CREDENTIAL_JSON" \
    --only-show-errors >/dev/null
fi

printf 'AZURE_CLIENT_ID=%s\n' "$APP_CLIENT_ID"
printf 'AZURE_TENANT_ID=%s\n' "$TENANT_ID"
printf 'AZURE_SUBSCRIPTION_ID=%s\n' "$SUBSCRIPTION_ID"
