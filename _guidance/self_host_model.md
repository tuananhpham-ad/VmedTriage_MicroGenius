# Self-host `Qwen/Qwen3.5-4B` cho VMedTriage

> **Phương án đã chốt:** Render chỉ chạy web app; model chạy trên máy Linux/GPU riêng tại
> `112.137.129.161` và được quản trị qua SSH bằng tài khoản `anhnd_03`.
>
> Render free chỉ có 512 MB RAM nên không thể tải model 4B. Riêng trọng số model đã lớn hơn nhiều
> giới hạn này, chưa kể runtime, KV cache và bộ nhớ của FastAPI. Không cài `torch`, `transformers`
> hoặc vLLM vào Render.

## 1. Kiến trúc

```text
Browser
   │
   ▼
Render (FastAPI, 512 MB)
   │  HTTPS + Bearer token
   ▼
Reverse proxy :443 trên máy model
   │  localhost
   ▼
vLLM :8001 ──> Qwen/Qwen3.5-4B
```

- SSH chỉ dùng để cài đặt, vận hành và tạo tunnel kiểm thử.
- Render không gọi model qua phiên SSH cá nhân. Production cần một endpoint HTTPS ổn định.
- vLLM chỉ bind vào `127.0.0.1`; không mở trực tiếp cổng inference ra Internet.
- Model không được tự quyết định `triage_level`. `rule_engine`, emergency short-circuit, state machine,
  output guard và HITL vẫn là các lớp kiểm soát tất định.

## 2. Kết nối máy self-host

Từ máy cá nhân:

```bash
ssh anhnd_03@112.137.129.161
```

SSH sẽ tự hỏi password trong terminal. Không đưa password vào tài liệu, `.env`, lệnh shell, commit,
chat hoặc log. Sau khi đăng nhập được, nên chuyển sang SSH key:

```bash
ssh-keygen -t ed25519 -C "vmedtriage-admin"
ssh-copy-id anhnd_03@112.137.129.161
```

Nếu máy Windows không có `ssh-copy-id`, chép **public key** từ file `.pub` vào
`~/.ssh/authorized_keys` trên server. Không bao giờ chép private key lên server hay vào repo.

## 3. Kiểm tra server trước khi tải model

Chạy trên máy `112.137.129.161`:

```bash
uname -a
nvidia-smi
docker --version
docker info
df -h
free -h
```

Điều kiện tối thiểu:

- Linux nhìn thấy NVIDIA GPU và driver hoạt động;
- Docker nhìn thấy GPU qua NVIDIA Container Toolkit;
- còn đủ dung lượng cho image và Hugging Face cache;
- GPU có đủ VRAM cho trọng số, KV cache và context dự kiến.

`Qwen/Qwen3.5-4B` ở BF16 cần nhiều hơn dung lượng trọng số thô khi chạy. Không chốt cấu hình chỉ dựa
trên số “4B”: phải smoke test rồi theo dõi VRAM thực tế. Nếu OOM, giảm context/concurrency trước.
Chỉ chuyển sang một checkpoint quantized sau khi đã ghi đúng model ID và chạy lại eval; checkpoint
quantized là artifact khác với `Qwen/Qwen3.5-4B`.

Kiểm tra Docker sử dụng được GPU:

```bash
docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi
```

Nếu tag CUDA này không tương thích driver, chọn image CUDA phù hợp với driver trên máy. Không tải
model tiếp khi lệnh kiểm tra GPU chưa chạy được.

## 4. Chạy Qwen3.5-4B bằng vLLM

### 4.1. Chuẩn bị secret

Tạo API key trên server, lưu bằng secret manager hoặc file chỉ owner đọc được:

```bash
umask 077
mkdir -p "$HOME/.config/vmedtriage"
openssl rand -hex 32 > "$HOME/.config/vmedtriage/vllm_api_key"
```

Không in key ra log và không commit file này. Để dùng key trong phiên hiện tại:

```bash
export VLLM_API_KEY="$(cat "$HOME/.config/vmedtriage/vllm_api_key")"
```

### 4.2. Khởi động container

Lần smoke test đầu có thể dùng image vLLM đã chọn để xác nhận nó hỗ trợ đúng kiến trúc Qwen3.5.
Trước production, thay `VERSION_TESTED` bằng tag hoặc digest đã chạy qua eval; không dùng `latest`:

```bash
docker run --rm \
  --name vmedtriage-qwen \
  --gpus all \
  --ipc=host \
  -p 127.0.0.1:8001:8000 \
  -v vmedtriage-hf-cache:/root/.cache/huggingface \
  vllm/vllm-openai:VERSION_TESTED \
  --model Qwen/Qwen3.5-4B \
  --served-model-name vmedtriage-qwen3.5-4b \
  --api-key "$VLLM_API_KEY" \
  --dtype auto \
  --max-model-len 4096 \
  --max-num-seqs 4 \
  --gpu-memory-utilization 0.85 \
  --disable-log-requests
```

Các giá trị `4096` và `4` là cấu hình khởi đầu bảo thủ, không phải benchmark production. Nếu image
báo không nhận kiến trúc/model, nâng vLLM lên bản có hỗ trợ Qwen3.5 rồi pin chính bản đó. Không thêm
`--trust-remote-code` một cách mặc định; chỉ dùng sau khi đã review model revision.

Khi OOM, giảm theo thứ tự:

1. `--max-num-seqs`;
2. `--max-model-len`;
3. concurrency của app;
4. dùng checkpoint quantized đã eval;
5. nâng GPU.

Production nên chạy container bằng systemd hoặc Compose với restart policy, không giữ lệnh
`--rm` chạy trong một terminal SSH. Đồng thời pin image digest, model revision và tokenizer revision.

### 4.3. Health check trên server

```bash
curl http://127.0.0.1:8001/v1/models \
  -H "Authorization: Bearer $VLLM_API_KEY"

curl http://127.0.0.1:8001/v1/chat/completions \
  -H "Authorization: Bearer $VLLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "vmedtriage-qwen3.5-4b",
    "temperature": 0,
    "messages": [
      {"role": "system", "content": "Chỉ trả JSON hợp lệ."},
      {"role": "user", "content": "Trích xuất đúng lời người dùng: Tôi không khó thở."}
    ]
  }'
```

Pass tối thiểu: HTTP 200, có `choices[0].message.content`, output qua được parser/validator và không
tự thêm triệu chứng không xuất hiện trong câu nguồn.

## 5. Kiểm thử qua SSH tunnel

Giữ vLLM bind ở localhost trên server. Từ máy cá nhân, mở một terminal khác:

```bash
ssh -N -L 8001:127.0.0.1:8001 anhnd_03@112.137.129.161
```

Sau đó gọi `http://127.0.0.1:8001/v1` trên máy cá nhân. Tunnel này phù hợp để smoke test, nhưng
Render không thể dùng `127.0.0.1` này và không nên phụ thuộc vào một phiên SSH thủ công.

## 6. Endpoint dành cho Render

Đặt Caddy, Nginx hoặc gateway tương đương trên máy model:

```text
https://llm.<domain-cua-ban>/v1/*  ->  http://127.0.0.1:8001/v1/*
```

Yêu cầu bắt buộc:

- domain và chứng chỉ TLS hợp lệ; không dùng HTTP trần tới IP công khai;
- giữ xác thực Bearer token của vLLM hoặc xác thực tương đương tại gateway;
- firewall chỉ mở SSH và HTTPS; cổng `8001` không public;
- nếu hạ tầng cho phép, allowlist outbound IP của Render;
- tắt request-body logging để prompt/response chứa dữ liệu y tế không lọt vào access log;
- đặt timeout của proxy lớn hơn timeout inference nhưng nhỏ hơn request budget tổng của app.

Không nhúng API key vào URL. Trên Render, lưu key bằng Secret Environment Variable:

```dotenv
LOCAL_SLM_API_KEY=<secret giống key của vLLM/gateway>
LOCAL_SLM_BASE_URL=https://llm.<domain-cua-ban>/v1
LOCAL_SLM_MODEL_NAME=vmedtriage-qwen3.5-4b
```

Không commit ba giá trị production vào `.env`, `.env.example` hoặc `render.yaml`; các file mẫu chỉ
chứa placeholder.

## 7. Tích hợp vào repo

Repo hiện **đã có** `RoleProfile` và các biến `ROLE_ORDER_*`, nhưng **chưa có** provider
`local_slm`. Dựng model server xong chưa làm ứng dụng tự gọi endpoint này. Cần triển khai các thay
đổi sau trong một PR riêng có test.

### 7.1. `src/config.py`

```python
llm_provider: Literal[
    "auto", "local_slm", "openai", "deepseek", "gemini", "anthropic", "openrouter"
] = "auto"

local_slm_api_key: str = ""
local_slm_base_url: str = "http://127.0.0.1:8001/v1"
local_slm_model_name: str = "vmedtriage-qwen3.5-4b"
```

`SUPPORTED_MODEL_NAME` không thay thế ba biến trên: nó đang là metadata của pipeline khác, không
phải cấu hình endpoint của provider router.

### 7.2. `src/services/infra/provider_router.py`

Thêm `ProviderSpec` cho `local_slm`, rồi trong `_build_provider()` truyền
`settings.local_slm_base_url` khi `spec.name == "local_slm"`. Không cho client gửi tùy ý `base_url`;
điều đó tạo rủi ro SSRF vào mạng nội bộ.

### 7.3. `src/providers/__init__.py`

Map `local_slm` sang `OpenAIProvider` với `api_key`, `base_url` và `default_model` truyền tường minh.
Không cần adapter mới nếu vLLM giữ đúng Chat Completions contract mà repo đang sử dụng.

### 7.4. Định tuyến theo vai trò

Không đặt `LLM_PROVIDER=local_slm` ngay trong production vì như vậy mọi tác vụ model đều bị ghim vào
Qwen3.5-4B và mất fallback. Cấu hình mục tiêu sau khi eval:

```text
synthesis:             local_slm -> hosted fallback -> script_hint
symptom_group_router:  local_slm -> deterministic registry
fact_extractor:        hosted validated model -> provider fallback
```

Chỉ đưa `local_slm` vào `fact_extractor` khi field-level eval, negation/correction accuracy,
hallucination rate và red-flag recall đều đạt gate đã chốt.

## 8. Kiểm tra sau tích hợp

```powershell
$env:PYTHONIOENCODING = "utf-8"
python -c "from src.services.infra import provider_router; print(provider_router.available_providers()); print(provider_router.describe_selection())"
python -m pytest tests/test_agents tests/test_services -q
python scripts/manual_llm_check.py --delay 0 c1 c2 m1 emergency
```

Sau smoke test, chạy toàn bộ eval với cùng model revision, vLLM image, context và concurrency sẽ dùng
ở production. Chỉ dùng dữ liệu giả lập/de-identified; script kiểm thử có thể ghi prompt và response
vào `logs/`.

## 9. Monitoring và rollback

Theo dõi tối thiểu:

- `/v1/models` và một synthetic chat không chứa dữ liệu bệnh nhân;
- p50/p95/p99 latency, time-to-first-token, queue depth và timeout;
- GPU utilization, VRAM, OOM và restart count;
- parse failure và fallback rate theo từng vai trò;
- model revision, tokenizer revision, vLLM image digest và prompt hash.

Rollback không được cần sửa code:

1. bỏ `local_slm` khỏi `ROLE_ORDER_*`;
2. synthesis rơi về hosted provider hoặc `script_hint`;
3. router rơi về deterministic registry;
4. chỉ dừng model container sau khi traffic về 0.

Model server chết không được làm dừng red-flag rule engine, state machine hoặc HITL handoff.

## 10. Checklist

- [ ] SSH vào được `anhnd_03@112.137.129.161` mà không lưu password trong repo.
- [ ] `nvidia-smi` và Docker GPU test pass.
- [ ] `Qwen/Qwen3.5-4B` load được bằng vLLM và chat smoke test pass.
- [ ] vLLM chỉ bind `127.0.0.1:8001`.
- [ ] Render gọi endpoint HTTPS có authentication; cổng inference không public.
- [ ] Image, model và tokenizer revision đã pin.
- [ ] Provider `local_slm` đã được implement và có test.
- [ ] Role routing, eval an toàn, monitoring và rollback đều pass trước production.
