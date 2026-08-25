#!/usr/bin/env bash
# Go environment Container Apps hien tai de giai phong cho mot environment o VUNG KHAC.
#
#   ./scripts/azure_teardown_env.sh            # chi LIET KE thu se xoa, khong xoa gi
#   ./scripts/azure_teardown_env.sh --yes      # xoa that
#
# VI SAO CAN SCRIPT NAY: goi Azure for Students cho dung MOT Container App Environment tren ca
# subscription (loi MaxNumberOfGlobalEnvironmentsInSubExceeded). Environment lai KHONG doi vung
# duoc sau khi tao. Nen doi vung = phai go cai cu truoc, va giua luc do app KHONG truy cap duoc.
#
# THU TU BAT BUOC, khong dao duoc:
#   1. containerapp   - environment con chua app thi khong xoa duoc
#   2. builders       - tan du cua `az containerapp up --source .` (Buildpack). Con builder thi
#                       environment tra ve ManagedEnvironmentHasBuilders. `az containerapp` khong
#                       co lenh rieng cho builder, phai xoa qua `az resource delete`.
#   3. environment
#
# KHONG dung toi registry: image da push nam trong do, va app o vung moi keo image tu registry vung
# cu hoan toan binh thuong. Xoa registry = phai build + push lai vai GB.
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-vmedtriage-rg}"
ENVIRONMENT="${ENVIRONMENT:-vmedtriage-env}"

export PYTHONIOENCODING=utf-8
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

DRY_RUN=1
[[ "${1:-}" == "--yes" ]] && DRY_RUN=0

command -v az >/dev/null 2>&1 || { echo "Chua cai Azure CLI." >&2; exit 2; }
az account show >/dev/null 2>&1 || { echo "Chua dang nhap: az login" >&2; exit 2; }

LOCATION_OF_ENV="$(az containerapp env show -n "$ENVIRONMENT" -g "$RESOURCE_GROUP" \
  --query location -o tsv 2>/dev/null || true)"
if [[ -z "$LOCATION_OF_ENV" ]]; then
  echo "Environment '$ENVIRONMENT' khong ton tai trong '$RESOURCE_GROUP' - khong con gi de go."
  echo "Chay thang: ENVIRONMENT=vmedtriage-japaneast-env APP_NAME=vmedtriage-japaneast ./scripts/deploy_azure.sh"
  exit 0
fi
echo "Environment '$ENVIRONMENT' dang o '$LOCATION_OF_ENV'."

APPS="$(az containerapp list -g "$RESOURCE_GROUP" \
  --query "[?properties.environmentId!=null] | [?contains(properties.environmentId,'$ENVIRONMENT')].name" \
  -o tsv 2>/dev/null || true)"
BUILDERS="$(az resource list -g "$RESOURCE_GROUP" \
  --query "[?type=='Microsoft.App/builders'].name" -o tsv 2>/dev/null || true)"

echo
echo "Se xoa, theo thu tu:"
echo "$APPS"     | sed '/^$/d; s/^/  1. containerapp  /' || true
echo "$BUILDERS" | sed '/^$/d; s/^/  2. builder       /' || true
echo "  3. environment   $ENVIRONMENT"
echo
echo "KHONG dung toi: registry (image da push), Log Analytics workspace."

if (( DRY_RUN )); then
  echo
  echo "Day moi la ban LIET KE. Xoa that thi chay lai voi --yes."
  exit 0
fi

echo
for app in $APPS; do
  echo "[1/3] xoa containerapp $app"
  az containerapp delete -n "$app" -g "$RESOURCE_GROUP" --yes --output none
done
for builder in $BUILDERS; do
  echo "[2/3] xoa builder $builder"
  az resource delete -g "$RESOURCE_GROUP" -n "$builder" \
    --resource-type "Microsoft.App/builders" --output none
done
echo "[3/3] xoa environment $ENVIRONMENT"
az containerapp env delete -n "$ENVIRONMENT" -g "$RESOURCE_GROUP" --yes --output none

echo
echo "Xong. Gio deploy sang vung moi:"
echo "  ENVIRONMENT=vmedtriage-japaneast-env APP_NAME=vmedtriage-japaneast ./scripts/deploy_azure.sh"
