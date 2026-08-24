# Image cho Azure Container Apps (giữ ENABLE_GRAPH_TRIAGE_AGENT=true).
#
# HAI RÀNG BUỘC QUYẾT ĐỊNH FILE NÀY:
#
# 1. Ổ đĩa của container là ephemeral: restart là mất sạch. Artifact graph triage (~1.6 GB) và
#    corpus y văn vì thế được tải ngay trong lúc BUILD, nằm sẵn trong image, thay vì tải lại mỗi
#    lần khởi động như trên Render. Cold start nhờ đó không phải chờ tải 1.6 GB.
#
# 2. Container phải lắng nghe cổng $PORT (mặc định 8080), khớp --target-port của Container Apps.
#
# VÌ SAO MULTI-STAGE: bản một stage ra image 9.5 GB, mà `az acr build` bị khoá trên subscription
# Azure for Students nên image phải push từ máy cá nhân - mỗi GB thừa là vài phút upload. Hai thứ
# bị cắt: (a) build-essential 373 MB chỉ cần lúc biên dịch wheel, (b) layer 1.64 GB do
# `chown -R /app` sinh ra - lệnh đó ghi lại quyền cho MỌI file nên Docker nhân đôi nguyên khối
# artifact thành một layer mới. Stage cuối dùng `COPY --chown` để gán quyền ngay lúc copy.
#
# Build/chạy thử tại máy:
#   docker build -t vmedtriage .
#   docker run --rm -p 8000:8080 -e PORT=8080 --env-file deploy/azure/env vmedtriage

# ---------- Stage 1: build ----------
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-graph.txt ./

# torch bản CPU cài riêng TRƯỚC. requirements-graph.txt trỏ index cu126: để nguyên thì pip kéo về
# bánh xe CUDA ~2.5 GB kèm cả chục gói nvidia-* - vô dụng trên Container Apps (không có GPU) và làm
# image phình gấp ba. Hai dòng `grep -v` bên dưới lọc bỏ dòng index CUDA và dòng `torch` của cả hai
# file. `|| pip install ... torch` là lưới an toàn khi index CPU chưa có đúng phiên bản được pin.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.10.0 \
    || pip install --index-url https://download.pytorch.org/whl/cpu torch

RUN grep -vE '^[[:space:]]*(--extra-index-url|torch[=<>])' requirements.txt > /tmp/req-base.txt \
    && pip install -r /tmp/req-base.txt
RUN grep -vE '^[[:space:]]*(--extra-index-url|torch[=<>])' requirements-graph.txt > /tmp/req-graph.txt \
    && pip install -r /tmp/req-graph.txt

COPY . /app

# Repo id của 3 artifact - model công khai trên HF Hub, không phải bí mật. Đặt ở đây (chứ không chỉ
# ở biến môi trường lúc chạy) vì bước tải bên dưới chạy trong lúc build.
ENV GRAPH_TRIAGE_ARTIFACT_ROOT=/app/runs \
    LOGREG_FULL_MODEL=danhnahh/logreg_full \
    BERT_FULL_MODEL=danhnahh/bert_full \
    FUSION_FULL_MODEL=danhnahh/fusion_full

# Gọi dạng `-m` chứ không phải `python scripts/xxx.py`: chạy trực tiếp file thì Python đặt
# sys.path[0] = thư mục scripts/, nên `import src.config` chết với ModuleNotFoundError.
#
# Artifact KHÔNG dùng "|| true" - thiếu nó là graph triage vô dụng, phải biết ngay lúc build.
# Corpus thì có: một URL guideline chết chỉ làm corpus thiếu vài tài liệu.
#
# CHỈ TẢI FUSION. Image này chạy GRAPH_TRIAGE_MODE=c6, và c6 chỉ đọc fusion_full/ (qua
# `_fusion_label_for`). logreg_full/ + bert_full/ chỉ được nạp bởi `service.py::_get_agent`, hàm mà
# duy nhất nhánh `ensemble` gọi tới. Tải cả 3 = thêm ~500 MB vào image và ~3 phút vào mỗi lần build
# cho hai thư mục không ai mở.
#
# Build cho ensemble: `docker build --build-arg GRAPH_ARTIFACTS= ...` (để trống = tải cả 3).
ARG GRAPH_ARTIFACTS=fusion_full
RUN python -m scripts.download_graph_artifacts ${GRAPH_ARTIFACTS:+--only "$GRAPH_ARTIFACTS"}
RUN python -m scripts.build_source_corpus || echo "[build] build_source_corpus: FAILED (bo qua)"

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    GRAPH_TRIAGE_ARTIFACT_ROOT=/app/runs

# libgomp1: torch cần libgomp.so.1 lúc import. Ở bản một stage nó đi kèm build-essential; bỏ
# build-essential ra rồi thì phải cài riêng, nếu không app chết ngay khi import torch.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 appuser

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder --chown=appuser:appuser /app /app

USER appuser
EXPOSE 8080

# `exec` để uvicorn thành PID 1 và nhận được SIGTERM khi nền tảng thu hồi replica - không có nó,
# shell nuốt tín hiệu và container bị giết cứng sau 10 giây.
# seed_demo_users chạy mỗi lần khởi động (idempotent, chỉ đụng user0/nurse0) và không được phép
# chặn app: một lần DB hiccup lúc seed chỉ làm thiếu tài khoản demo.
CMD ["sh", "-c", "python -m scripts.seed_demo_users || echo '[startup] seed_demo_users: FAILED (bo qua)'; exec uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
