# Role-Specific Ownership - VMedTriage Backend Team

Mục đích: chia rõ phạm vi giữa 2 thành viên đang cùng làm backend để tránh conflict/đè code lên
nhau. Ai đổi phạm vi ngoài phần của mình phải báo trước cho người sở hữu phần đó.

## Thành viên & phạm vi

### Tuấn Anh (t)

**Việc chính:** Nối 5 API theo `docs/API_DOCUMENTATION.md` (mục 4 - Endpoint overview) + đảm bảo
đoạn đầu pipeline (intake agent) detect triệu chứng đúng và đủ trước khi đưa vào mapping/protocol.

**Sở hữu (được sửa tự do):**

- `src/api/routers/` - `cases.py`, `intake.py`, `queue.py`, `result.py` (route handler, request/response
  wiring theo `docs/API_DOCUMENTATION.md`)
- `src/models/*_api.py` (`intake_api.py`, `case_api.py`) - Pydantic schema cho request/response của các
  API trên
- `src/agents/` + `src/services/agents/` phần **detect/intake** (bước hỏi-đáp, trích xuất triệu chứng
  ban đầu) - không đụng vào phần semantic mapping -> probability nếu phần đó đã do Dũng Mai làm
- `src/tool/catalog/a_intake_conversation/` (tool contract cho bước intake)
- `src/services/infra/` (provider_router, llm) khi cần cho detect agent gọi LLM
- `src/providers/` khi cần thêm/sửa adapter provider

**Không tự ý sửa:** ERD/DB schema, `src/ui/new/` (frontend), model xác suất triệu chứng, script sinh
data.

### Dũng Mai

**Việc chính:** Sửa frontend, thiết kế lại ERD, các bảng trong backend, làm 3 model từ
triệu chứng => xác suất, sinh thêm data.

**Sở hữu (được sửa tự do):**

- `src/ui/new/` (toàn bộ frontend: `api.js`, `app.js`, `state.js`, `styles.css`, `features/`, ...)
- ERD + DB schema/bảng: `src/models/schemas.py`, `src/services/stores/` (`case_store.py`,
  `nurse_queue.py`, `approval_store.py`) và mọi migration/schema file mới sẽ tạo (vd `alembic/`,
  `src/db/`)
- 3 model xác suất triệu chứng -> priority: thư mục mới sẽ tạo (vd `src/ml/`, `models/`) + script
  sinh/augment data (vd trong `data/`, `scripts/`)
- `src/domain/` (dữ liệu tham chiếu triệu chứng/bệnh)

**Không tự ý sửa:** `src/api/routers/`, `src/agents/` phần detect, `docs/API_DOCUMENTATION.md`
(chỉ đọc để biết field cần trả về cho ERD/model).

## Vùng dùng chung - cần báo trước khi đổi field/contract

Các file này cả hai bên đều đọc/ghi qua lại (API trả field mà model/frontend cần đúng tên, đúng kiểu):

- `src/models/schemas.py`, `src/models/case_api.py`, `src/models/intake_api.py` - đổi field ở đây
  ảnh hưởng cả API lẫn frontend/model, phải thông báo trong nhóm trước khi merge.
- `src/config.py` (threshold, `REQUIRED_FIELDS_BY_SYMPTOM_GROUP`, `RED_FLAG_RULES`,
  `TRIAGE_PROTOCOL_RULES`) - Tuấn Anh dùng cho detect/validate, Dũng Mai dùng cho model xác suất và
  ERD tham chiếu. Sửa giá trị/rule ở đây cần đồng thuận cả hai.
- `docs/API_DOCUMENTATION.md`, `docs/openapi.yaml` - nguồn sự thật (source of truth) cho contract API;
  chỉ Tuấn Anh cập nhật khi đổi endpoint, Dũng Mai chỉ đọc để build frontend/ERD khớp.

## Quy tắc chung

1. Trước khi đổi field/kiểu dữ liệu trong vùng dùng chung, nhắn nhóm và chờ xác nhận.
2. Đặt tên bảng/field trong ERD khớp với field đã có trong `src/models/*_api.py` khi có thể, tránh
   phải map lại hai lần.
3. Không sửa file thuộc phạm vi người kia trừ khi được đồng ý; nếu cần sửa gấp (fix bug chặn cả hai),
   sửa tối thiểu và báo lại ngay.
4. Mỗi PR nêu rõ đụng tới file/thư mục nào để người còn lại dễ review phần giao nhau.
