#!/usr/bin/env bash
# Deploy VMedTriage len Azure Container Apps.
#
#   ./scripts/deploy_azure.sh
#
# Yeu cau: Azure CLI da `az login`, Docker Desktop dang chay.
# Bien moi truong doc tu deploy/azure/env (copy tu env.example, da nam trong .gitignore).
#
# VI SAO BUILD TAI MAY CHU KHONG PHAI TREN CLOUD: subscription Azure for Students chan ca hai
# duong build tren cloud - `az acr build` tra ve TasksOperationsNotAllowed, con `az containerapp up
# --source .` thi dung Buildpack (bo qua Dockerfile cua du an) va Buildpack do chet voi
# "/lifecycle/analyzer: Permission denied". Build tai may roi push la duong duy nhat con lai.
# Doi lai, layer artifact ~1GB chi push MOT lan; nhung lan deploy sau chi day layer code vai MB.
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-vmedtriage-rg}"
# eastasia (Hong Kong) chu KHONG phai southeastasia (Singapore): subscription Azure for Students bi
# chinh sach "Allowed resource deployment regions" gioi han dung 5 vung - koreacentral,
# malaysiawest, eastasia, indiasouthcentral, japaneast. Vung ngoai danh sach hong voi loi
# RequestDisallowedByAzure ngay o buoc tao Log Analytics workspace.
LOCATION="${LOCATION:-eastasia}"
ENVIRONMENT="${ENVIRONMENT:-vmedtriage-env}"
APP_NAME="${APP_NAME:-vmedtriage}"
IMAGE_TAG="${IMAGE_TAG:-v1}"

# Azure CLI in ky tu ✓ ra stdout; console cp1252 tren Windows tieng Viet lam no crash
# UnicodeEncodeError giua chung. Ep utf-8 cho moi lenh az ben duoi.
export PYTHONIOENCODING=utf-8

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="deploy/azure/env"

command -v az >/dev/null 2>&1 || { echo "Chua cai Azure CLI: winget install -e --id Microsoft.AzureCLI" >&2; exit 2; }
az account show >/dev/null 2>&1 || { echo "Chua dang nhap: az login" >&2; exit 2; }
docker info >/dev/null 2>&1 || { echo "Docker Desktop chua chay - mo len roi chay lai." >&2; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "Thieu $ENV_FILE. Chay: cp deploy/azure/env.example $ENV_FILE" >&2; exit 2; }

# Doc env file thanh mang "KEY=value" cho --env-vars/--replace-env-vars. Bo dong trong va comment.
ENV_ARGS=()
while IFS= read -r line; do
  [[ -z "${line// }" || "${line#\#}" != "$line" ]] && continue
  [[ "$line" != *=* ]] && continue
  ENV_ARGS+=("$line")
done < "$ENV_FILE"
echo "[1/6] doc $ENV_FILE: ${#ENV_ARGS[@]} bien"

echo "[2/6] resource provider + resource group + environment"
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait
az provider register --namespace Microsoft.ContainerRegistry --wait
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
az containerapp env show --name "$ENVIRONMENT" --resource-group "$RESOURCE_GROUP" --output none 2>/dev/null \
  || az containerapp env create --name "$ENVIRONMENT" --resource-group "$RESOURCE_GROUP" \
       --location "$LOCATION" --output none

echo "[3/6] container registry"
# Ten ACR phai duy nhat toan cau va chi gom chu+so. Lay ten dang co trong resource group truoc,
# chi tao moi khi chua co - de chay lai script khong de ra registry moi moi lan.
ACR="$(az acr list -g "$RESOURCE_GROUP" --query '[0].name' -o tsv 2>/dev/null || true)"
if [[ -z "$ACR" ]]; then
  ACR="vmedtriage$(date +%s | tail -c 6)"
  az acr create -n "$ACR" -g "$RESOURCE_GROUP" --sku Basic --location "$LOCATION" \
    --admin-enabled true --output none
  echo "      da tao registry $ACR"
else
  echo "      dung registry san co: $ACR"
fi
SERVER="$(az acr show -n "$ACR" --query loginServer -o tsv)"
IMAGE="$SERVER/vmedtriage:$IMAGE_TAG"

echo "[4/6] build image tai may (lan dau ~20 phut)"
az acr login --name "$ACR"
# --platform linux/amd64: Container Apps chay amd64. Bat buoc khai ro neu may build la ARM (Mac M-series).
docker build --platform linux/amd64 -t "$IMAGE" .

echo "[5/6] push len registry (lan dau ~2-3 GB, cac lan sau chi vai MB)"
docker push "$IMAGE"

echo "[6/6] tao/cap nhat container app"
ACR_USER="$(az acr credential show -n "$ACR" --query username -o tsv)"
ACR_PASS="$(az acr credential show -n "$ACR" --query 'passwords[0].value' -o tsv)"
if az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" --output none 2>/dev/null; then
  az containerapp registry set --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --server "$SERVER" --username "$ACR_USER" --password "$ACR_PASS" --output none
  az containerapp update --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --image "$IMAGE" --replace-env-vars "${ENV_ARGS[@]}" \
    --cpu 2 --memory 4Gi --min-replicas 0 --max-replicas 3 --output none
else
  # --cpu 2 --memory 4Gi: PhoBERT (~500MB) + fusion (~500MB) + torch + app ~ 2GB luc chay. Goi
  #   Consumption bat buoc ty le memory = cpu * 2 GiB, nen 2 vCPU di kem dung 4Gi.
  # --min-replicas 0: khong co request thi khong ton credit.
  # --target-port 8080: khop EXPOSE trong Dockerfile.
  az containerapp create --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT" --image "$IMAGE" \
    --registry-server "$SERVER" --registry-username "$ACR_USER" --registry-password "$ACR_PASS" \
    --ingress external --target-port 8080 \
    --cpu 2 --memory 4Gi --min-replicas 0 --max-replicas 3 \
    --env-vars "${ENV_ARGS[@]}" --output none
fi

URL="https://$(az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --query 'properties.configuration.ingress.fqdn' -o tsv)"
echo
echo "Xong: $URL"
echo "Neu PASSWORD_RESET_BASE_URL / CORS_ORIGINS trong $ENV_FILE chua phai URL nay thi sua roi chay lai."
