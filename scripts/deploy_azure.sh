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
#
# TRONG 5 VUNG DO, KHONG DUOC CHON eastasia. Hong Kong nam ngoai danh sach phuc vu cua CA OpenAI lan
# Google Gemini: OpenAI tra 403, Gemini tra 400 FAILED_PRECONDITION ("User location is not supported
# for the API use"). Cung key do, cung code do, chay o may tai Viet Nam thi ca hai deu 200. DeepSeek
# (Trung Quoc) van song, nen app KHONG chet han - no chi mat dung nhanh GPT-direct cua C6, va vi
# service.py:288-290 tra None khi nhanh do hong, MOI CA KHONG PHAI CAP CUU BIEN MAT KHOI HANG DOI
# DIEU DUONG. Trieu chung nhin thay: "nurse chi nhan duoc ca red-flag". Da xay ra that tren
# revision 0000005 (2026-08-24). Bon vung con lai (japaneast, koreacentral, malaysiawest,
# indiasouthcentral) deu duoc ca hai nha cung cap phuc vu.
LOCATION="${LOCATION:-japaneast}"
# Ten CO HAU TO VUNG, va mac dinh phai khop dung tai nguyen DANG chay. Bo mac dinh cu
# (vmedtriage-env / vmedtriage) tro toi environment da bi xoa luc chuyen vung 2026-08-24: chay
# `./scripts/deploy_azure.sh` tran khi do lam script tuong chua co environment nao va di TAO MOI,
# roi chet voi MaxNumberOfRegionalEnvironmentsInSubExceeded - Azure for Students chi cho 1
# environment moi vung. Trieu chung do khong noi gi ve nguyen nhan that (ten mac dinh da cu), nen
# de mac dinh khop tai nguyen that la cach re nhat de no khong tai dien.
ENVIRONMENT="${ENVIRONMENT:-vmedtriage-japaneast-env}"
APP_NAME="${APP_NAME:-vmedtriage-japaneast}"
IMAGE_TAG="${IMAGE_TAG:-v1}"

# Azure CLI in ky tu ✓ ra stdout; console cp1252 tren Windows tieng Viet lam no crash
# UnicodeEncodeError giua chung. Ep utf-8 cho moi lenh az ben duoi.
export PYTHONIOENCODING=utf-8

# MSYS/Git Bash tu dich MOI tham so trong giong duong dan POSIX sang duong dan Windows truoc khi
# giao cho az.exe. Khong tat thi "GRAPH_TRIAGE_ARTIFACT_ROOT=/app/runs" den Azure duoi dang
# "C:/Program Files/Git/app/runs" - container Linux khong co duong dan do, Fusion khong nap duoc,
# va MAT AI DE XUAT ma khong he bao loi o buoc deploy. Da xay ra that tren revision 0000004
# (2026-08-24). Hai bien duoi tat viec dich do cho ca hai the he MSYS.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

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
# Chi register khi CHUA Registered. `az provider register` la thao tac cap SUBSCRIPTION: nguoi chi
# co Contributor pham vi resource group (cach chia se dung cho dong doi - xem docs/DEPLOYMENT.md)
# se an AuthorizationFailed va `set -e` giet ca script ngay tai day, du ba provider deu da dang ky
# tu lan deploy dau cua chu subscription. Doc trang thai truoc, chi goi khi that su can.
for ns in Microsoft.App Microsoft.OperationalInsights Microsoft.ContainerRegistry; do
  state="$(az provider show --namespace "$ns" --query registrationState -o tsv 2>/dev/null || true)"
  if [[ "$state" == "Registered" ]]; then
    echo "      $ns: da Registered"
  else
    az provider register --namespace "$ns" --wait \
      || { echo "  !! Khong register duoc $ns (can quyen cap subscription)." >&2
           echo "     Nho chu subscription chay: az provider register --namespace $ns --wait" >&2
           exit 2; }
  fi
done
# Chi tao resource group khi CHUA co. `az group create` tren mot group da ton tai o vung khac tra
# ve InvalidResourceGroupLocation va giet ca script - trong khi vung cua group hoan toan khong quan
# trong: no chi la nhan metadata, tai nguyen ben trong (environment, app, registry) moi thuc su nam
# o vung rieng cua chung. Nho vay deploy sang japaneast van dung lai duoc group tao tu thoi eastasia.
az group show --name "$RESOURCE_GROUP" --output none 2>/dev/null \
  || az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
# Environment KHONG doi vung duoc sau khi tao. Neu cai dang co nam o vung khac $LOCATION thi viec
# dung lai no am tham vo hieu hoa moi thay doi LOCATION - app van chay o vung cu, va neu vung cu la
# eastasia thi van mat AI de xuat. Dung lai va bao ro thay vi deploy nham.
EXISTING_LOCATION="$(az containerapp env show --name "$ENVIRONMENT" --resource-group "$RESOURCE_GROUP" \
  --query location -o tsv 2>/dev/null || true)"
if [[ -z "$EXISTING_LOCATION" ]]; then
  az containerapp env create --name "$ENVIRONMENT" --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" --output none
  echo "      da tao environment $ENVIRONMENT tai $LOCATION"
elif [[ "$(echo "$EXISTING_LOCATION" | tr -d ' ' | tr '[:upper:]' '[:lower:]')" != "$LOCATION" ]]; then
  echo "  !! Environment '$ENVIRONMENT' dang o '$EXISTING_LOCATION', khong phai '$LOCATION'." >&2
  echo "     Environment khong doi vung duoc. Deploy sang vung moi bang mot environment + app moi:" >&2
  echo "       ENVIRONMENT=vmedtriage-$LOCATION-env APP_NAME=vmedtriage-$LOCATION ./scripts/deploy_azure.sh" >&2
  echo "     (giu nguyen RESOURCE_GROUP de dung lai registry, khoi push lai vai GB)" >&2
  exit 3
else
  echo "      dung environment san co: $ENVIRONMENT tai $EXISTING_LOCATION"
fi

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

# KIEM TRA SAU DEPLOY. Loi MSYS dich duong dan (xem comment o dau file) khong lam buoc nao ben tren
# that bai - no deploy "thanh cong" voi mot bien SAI, roi Fusion im lang khong nap duoc artifact va
# MAT AI DE XUAT ma khong co dong log loi nao o buoc deploy. Da xay ra that tren revision 0000004
# (2026-08-24) va chi lo ra khi chay scripts/check_nurse_flow.py. Doc lai env DA LEN SERVER va bat
# loi do ngay tai day, thay vi de no song im lim toi luc co nguoi thu luong that.
echo
echo "[kiem tra 1/2] doc lai bien moi truong tren server"
# Loc bang regex o phia bash chu khong bang JMESPath: `contains(value, ':/')` bat nham ca https://
# cua PASSWORD_RESET_BASE_URL / CORS_ORIGINS / DATABASE_URL. Dau hieu THAT cua duong dan bi MSYS
# dich la gia tri BAT DAU bang mot ky tu o dia rieng le: "C:/..." hoac "C:\...".
BAD="$(az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --query "properties.template.containers[0].env[?value!=null].[name,value]" -o tsv 2>/dev/null \
  | awk -F'\t' '$2 ~ /^[A-Za-z]:[\/\\]/ {print $1}' || true)"
if [[ -n "$BAD" ]]; then
  echo "      !! CANH BAO: bien duoi day mang duong dan kieu Windows - MSYS da dich sai:" >&2
  echo "$BAD" | sed 's/^/         /' >&2
  echo "         Container Linux khong co duong dan do. Go bang:" >&2
  echo "         az containerapp update -n $APP_NAME -g $RESOURCE_GROUP --remove-env-vars <TEN_BIEN>" >&2
else
  echo "      OK - khong bien nao bi dich thanh duong dan Windows"
fi

echo "[kiem tra 2/2] /health (min-replicas=0 nen lan goi dau phai cho cold start, co the vai phut)"
# Doc ket qua vao BIEN roi moi in, thay vi de curl tu in bang `-w` ra console: tren Git Bash/MSYS
# curl hay chet voi "(23) client returned ERROR on write" khi ghi chuoi -w ra terminal, du request
# da thanh cong. Bam vao exit code cua curl trong tinh huong do cho ra BAO DONG GIA - da xay ra
# that 2026-08-25: script in "HTTP 200 sau 50.44s" roi ngay dong sau bao "/health khong tra loi".
# Xet MA HTTP moi la thu dung: no noi ve server, con exit code con lan ca loi phia client.
HEALTH="$(curl -fsS -m 300 -o /dev/null -w '%{http_code} %{time_total}' "$URL/health" 2>/dev/null || true)"
HEALTH_CODE="${HEALTH%% *}"
if [[ "$HEALTH_CODE" == "200" ]]; then
  echo "      OK - HTTP 200 sau ${HEALTH##* }s"
else
  echo "      !! /health tra ve '${HEALTH_CODE:-khong co phan hoi}'." >&2
  echo "         Xem log: az containerapp logs show -n $APP_NAME -g $RESOURCE_GROUP --follow" >&2
fi

echo
echo "Xong: $URL"
echo "Neu PASSWORD_RESET_BASE_URL / CORS_ORIGINS trong $ENV_FILE chua phai URL nay thi sua roi chay lai."
echo
echo "Kiem tra luong that (benh nhan chat -> dieu duong -> AI de xuat):"
echo "  python -m scripts.check_nurse_flow --base-url $URL"
