# UI ↔ Backend hiện đang nối với nhau thế nào (và fever agent thì sao)

> Viết ra vì đã hỏi đi hỏi lại: `patient.js` gọi API nào, agent fever mới có chạy qua UI thật không.
> Câu trả lời ngắn: **KHÔNG** — UI bệnh nhân và engine fever mới (`symptom_protocol`) là **2 pipeline
> tách biệt hoàn toàn**, chạy song song, chưa được nối với nhau. File này giải thích rõ 2 luồng, cách
> chạy từng luồng, và việc cần quyết định nếu muốn gộp chúng lại.

## 1. Hai pipeline độc lập

| | Luồng UI thật (bệnh nhân đăng nhập, `patient.js`) | Luồng demo fever mới |
|---|---|---|
| Endpoint | `POST /api/v1/chat` | `POST /api/v1/fever/sessions`, `.../messages`, `.../confirm` |
| Định nghĩa route | `src/api/routes.py` (`@router.post("/chat")`) | `src/api/routers/fever_intake.py` |
| Engine phía sau | `src/agents/graph.py` (`agent`) — pipeline LangGraph cũ | `src/services/symptom_protocol/` + `src/services/engines/fever_protocol.py` (viết trong `fever-detect-agent-task.md`) |
| Cần đăng nhập? | CÓ — đọc `request.state.auth.sub` (JWT), nằm trong `ROUTE_POLICIES` của `src/middleware/auth.py` | KHÔNG — route demo, không yêu cầu auth (xem docstring đầu `fever_intake.py`) |
| Có tạo case/queue cho điều dưỡng? | CÓ — `case_store.save(triage_case)`, vào hàng chờ HITL | KHÔNG — chỉ trả kết quả trong response, không đẩy đi đâu |
| UI có màn hình riêng? | CÓ — `src/ui/new/features/patient.js` | KHÔNG — chưa có trang HTML nào gọi `/api/v1/fever/*`, phải test qua Swagger (`/docs`) hoặc `curl`/script |
| State lưu ở đâu? | DB thật (`case_store`, SQLAlchemy) | In-memory (`ProtocolSessionStore` trong `src/services/symptom_protocol/session.py`) — mất khi restart server |

**Kết luận quan trọng**: mọi phần đã sửa trong `fever-detect-agent-task.md`/`symptom_protocol.md`
(logging, budget, EMERGENCY short-circuit, extract nhiệt độ/ngày tháng, đa dạng câu hỏi, ...) **chỉ
chạy được khi gọi trực tiếp `/api/v1/fever/*`**, KHÔNG tự động xuất hiện khi bệnh nhân chat qua UI
thật (UI thật vẫn đi qua `graph.py` cũ, chưa biết gì về fever protocol).

## 2. Chạy server chung cho cả 2 luồng

```bash
# 1) Cài dependency (1 lần)
pip install -r requirements.txt

# 2) Copy .env.example -> .env, điền ít nhất 1 API key LLM
#    (DEEPSEEK_API_KEY / OPEN_ROUTER_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY - xem src/config.py
#    để biết tên provider hợp lệ: auto | openai | deepseek | gemini | anthropic | openrouter)
cp .env.example .env

# 3) Chạy server (reload để tiện sửa code)
uvicorn src.main:app --reload --port 8000
```

Cả 2 route (`/api/v1/chat` và `/api/v1/fever/*`) đều nằm trong CÙNG một `FastAPI app` (`src/main.py`),
nên chỉ cần chạy 1 server duy nhất cho cả 2 luồng.

## 3. Test luồng UI thật (`/api/v1/chat`)

Mở trình duyệt tới `http://localhost:8000/` (server tự phục vụ `src/ui/new/` qua
`build_demo_static_app()`). Đăng ký/đăng nhập tài khoản bệnh nhân, vào màn hình chat — UI tự gọi
`/api/v1/chat` với JWT trong header. Luồng này KHÔNG liên quan gì tới các sửa đổi fever gần đây.

## 4. Test luồng fever mới (`/api/v1/fever/*`)

Chưa có UI, nên test bằng 1 trong 2 cách:

### Cách A — Swagger UI (nhanh nhất, không cần code)

1. Mở `http://localhost:8000/docs`.
2. Tìm nhóm **"Demo - Fever intake (phát hiện triệu chứng sốt)"**.
3. `POST /api/v1/fever/sessions` — Execute với body rỗng `{}` (dùng key server đã cấu hình trong
   `.env`) hoặc truyền credential riêng:
   ```json
   {"provider": "deepseek", "api_key": "sk-...", "model": null}
   ```
   `provider` phải khớp ĐÚNG hãng của `api_key` (vd key OpenRouter luôn bắt đầu `sk-or-v1-` phải đi
   với `"provider": "openrouter"`, không phải `"openai"` — nhầm chỗ này ra lỗi 401 rất khó hiểu).
4. Copy `session_id` trong response.
5. `POST /api/v1/fever/sessions/{session_id}/messages` với body `{"message": "..."}`, lặp lại theo
   `next_question` trả về mỗi lần cho tới khi `state` chuyển sang trạng thái kết thúc
   (`triage_level` khác `null`, hoặc `stop_reason` được set).
6. Nếu cần, `POST /api/v1/fever/sessions/{session_id}/confirm` với `{"is_correct": true}` để xác nhận
   tóm tắt cuối phiên.

### Cách B — curl (kịch bản lặp nhiều lượt, tiện copy-paste)

```bash
BASE=http://localhost:8000/api/v1/fever

SID=$(curl -s -X POST "$BASE/sessions" -H "Content-Type: application/json" -d '{}' | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
echo "session_id=$SID"

curl -s -X POST "$BASE/sessions/$SID/messages" -H "Content-Type: application/json" \
  -d '{"message": "Con tôi 2 tuổi, sốt 38 độ C từ 2 ngày nay"}' | python -m json.tool
```

Xem field `next_question` trong response để biết câu hỏi kế tiếp, tiếp tục `POST .../messages` cho
tới khi có `triage_level`.

### Xem log chi tiết từng lượt (extract/tool call/LLM I/O)

Mỗi phiên ghi JSONL vào `logs/fever/<session_id>/` (namespace lấy từ `FEVER_PROTOCOL.name`, xem
`src/services/infra/fever_stage_log.py`). Đọc trực tiếp file hoặc dùng hàm `read_turn`/`read_session`
trong module đó để xem theo đúng thứ tự ghi (`seq`).

## 5. Chạy bộ test tự động

```bash
# Toàn bộ test (202 test tính tới thời điểm viết file này)
pytest tests/ -q

# Chỉ test liên quan fever/symptom_protocol
pytest tests/ -k "fever or symptom_protocol" -q

# Lint các file vừa sửa
ruff check src/services/symptom_protocol/ src/services/engines/fever_protocol.py
```

Chi tiết test theo từng checkpoint (0-6) đã có sẵn trong `_guidance/fever-detect-agent-task.md` §7-8,
không lặp lại ở đây.

## 6. Việc cần quyết định: có nối fever vào `/api/v1/chat` không?

Đây là thay đổi kiến trúc lớn (đổi endpoint UI đang gọi, hoặc thêm logic rẽ nhánh trong `/chat` để
chọn giữa `graph.py` cũ và `symptom_protocol` mới), **chưa làm** vì:

- Vượt phạm vi các sửa đổi đã yêu cầu (fix trích xuất, đa dạng câu hỏi).
- `/chat` đụng tới case/queue/HITL thật (`case_store`) — rủi ro cao hơn route demo `/fever/*` nhiều.
- Theo `_guidance/role_specific.md`, `src/agents/graph.py` và `src/ui/new/` không hoàn toàn thuộc
  phạm vi sở hữu của việc này — cần thống nhất trước khi đụng vào.

Nếu quyết định nối, hướng khả thi nhất: trong `/chat`, khi phát hiện phiên đang ở luồng "khai thác
triệu chứng sốt" (hoặc thêm 1 field `symptom_group` vào `ChatRequest`), rẽ sang gọi
`fever_session.start_session`/`submit_message` thay vì `agent.ainvoke(...)`, rồi map
`FeverSessionResponse` sang đúng shape `ChatResponse` UI đang mong đợi. Việc này nên bàn kỹ trước khi
code vì ảnh hưởng trực tiếp tới luồng bệnh nhân thật đang chạy.
