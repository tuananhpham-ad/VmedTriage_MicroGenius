# VMedTriage - Solution Design Review

## 1. Đánh giá nhanh

Hướng thiết kế mới dùng **Gemma 3 4B làm Semantic Mapper** thay cho rule-based mapping là hợp lý với đề bài. Đề bài yêu cầu agent hỏi đáp có cấu trúc, xử lý mô tả triệu chứng tự nhiên, phát hiện thiếu/mâu thuẫn thông tin, lập phiếu bàn giao và chuyển cho điều dưỡng duyệt. Rule-based mapping hoặc keyword matching khó xử lý được cách bệnh nhân mô tả đa dạng, từ đồng nghĩa, lỗi chính tả và câu nói thiếu cấu trúc.

Tuy nhiên, bản Solution Design cần nhấn mạnh thêm 5 điểm để khớp hoàn toàn với đề bài:

1. **Grounded trên protocol triage chuẩn**: Triage Decision Engine phải tra bảng phân độ/protocol, không tự suy luận tự do.
2. **Red-flag escalation**: Các triệu chứng như đau ngực, khó thở, dấu hiệu đột quỵ, chảy máu nặng, co giật phải được ưu tiên phát hiện và escalate cấp cứu ngay.
3. **HITL bắt buộc**: AI chỉ tạo đề xuất; điều dưỡng/bác sĩ phê duyệt trước khi bệnh nhân nhận hướng xử trí.
4. **Chống bịa và giới hạn AI**: Gemma chỉ mapping/information extraction, không chẩn đoán, không kê đơn, không tự trả lời hướng xử trí.
5. **PII/PHI, audit log và giải thích guideline**: Cần có logging, bảo mật dữ liệu y tế, và khả năng giải thích lý do phân độ dựa trên guideline.

Kết luận: Thiết kế hiện tại đi đúng hướng, nhưng nên mô tả rõ hơn vai trò của protocol engine, red-flag safety layer, human approval gate, audit trail và security để đạt yêu cầu MVP và phần nâng cao.

---

## 2. Gợi ý kiến trúc phù hợp hơn với đề bài

Nên xem VMedTriage là hệ thống **Single-Agent Hybrid + Protocol-Grounded Tools + Human-in-the-Loop**.

Trong đó:

- **Single-Agent**: một agent chính điều phối hội thoại, trạng thái phiên, câu hỏi tiếp theo và luồng triage.
- **Hybrid**: kết hợp LLM semantic mapping với logic kiểm chứng, protocol triage, rule safety và HITL.
- **Protocol-Grounded Tools**: các quyết định ưu tiên phải dựa trên bảng phân độ/guideline đã lưu trong hệ thống.
- **HITL**: mọi kết quả gửi cho bệnh nhân phải qua điều dưỡng/bác sĩ duyệt.

Gemma 3 4B nên được đặt ở vai trò **Semantic Mapper**, không nên đặt ở vai trò "medical reasoner" cuối cùng. Quyết định triage nên được sinh bởi engine có kiểm soát, dựa trên JSON đã chuẩn hóa và protocol.

---

## 3. Solution Design

> **Cập nhật 2026-08-07.** Mục này đã được viết lại để khớp với code thực tế. Hai sai lệch lớn của
> bản cũ đã được sửa: (a) bản cũ mô tả **Gemma 3 4B** là thành phần AI chính, nhưng kiểm tra code cho
> thấy Gemma **chưa từng được nối** - chỉ tồn tại trong docstring của `RuleBackedSemanticMapper`;
> (b) bản cũ chỉ có một luồng, trong khi hệ thống hiện có **hai luồng song song**. Lịch sử thay đổi
> nằm ở mục 9.

### 3.1. Kiến trúc tổng thể

VMedTriage được thiết kế theo kiến trúc **Single-Agent Hybrid** với cơ chế **Human-in-the-Loop (HITL)**
bắt buộc nhằm đảm bảo an toàn trong môi trường y tế.

Hệ thống hiện có **hai luồng song song**, phục vụ hai mục đích khác nhau:

| | **Luồng A — Triage pipeline** | **Luồng B — Intake conversation (demo)** |
|---|---|---|
| Code | `src/services/triage_pipeline.py` | `src/services/intake_session.py` |
| Mapping | `RuleBackedSemanticMapper` — **100% rule-based**, không gọi LLM | `IntakeAgent` — **gọi LLM thật** để trích xuất + sinh câu hỏi |
| Checklist | Theo nhóm bệnh (`REQUIRED_FIELDS_BY_SYMPTOM_GROUP`) | Bộ trường chung, mock (`INTAKE_CHECKLIST`) |
| Đầu ra | Đề xuất mức ưu tiên + phiếu bàn giao → hàng đợi điều dưỡng | Phiếu tóm tắt → **bệnh nhân tự xác nhận** (chưa nối sang điều dưỡng) |
| Trạng thái | Đường quyết định chính | Demo phần hỏi-đáp, chưa có auth |

**Về thành phần AI:** có **hai cơ chế chọn provider song song** trong code, không dùng chung:

- `src/services/llm.py` — dựa trên LangChain, chỉ hỗ trợ 3 provider (openai/deepseek/gemini), đọc key
  qua `Settings` (pydantic-settings). Hiện **không thấy nơi nào gọi** module này trong luồng sống
  (kiểm tra lại thấy mô tả cũ ở đây là sai).
- `src/services/provider_router.py` — **đây là cơ chế đang thực sự chạy**, dùng cho `IntakeAgent`
  (Luồng B). Đọc thứ tự ưu tiên từ `Settings.llm_provider_order` (mặc định
  `"gemini,deepseek,openai,anthropic,openrouter"`; đặt `Settings.llm_provider` khác `"auto"` để ép
  dùng đúng 1 provider), duyệt qua 5 provider theo thứ tự đó, provider nào có API key hợp lệ (không
  rỗng, không phải giá trị placeholder như `sk-your-key-here`) thì dùng, gọi vào đúng adapter tương ứng
  trong `src/providers/` (`anthropic_provider.py`, `deepseek_provider.py`, `gemini_provider.py`,
  `openai_provider.py`, `openrouter_provider.py`) qua `make_provider(name)`. Nếu provider đầu lỗi (hết
  quota, lỗi mạng, model sai tên) tự rơi xuống provider tiếp theo còn key (`max_attempts=3`), không phải
  hỏng cả tính năng. Module này còn vá một lỗ hổng: `src/providers/*` đọc key bằng `os.getenv(...)`
  nhưng project nạp `.env` qua pydantic-settings (không ghi vào `os.environ`) — `provider_router` đồng
  bộ `Settings.<key>` sang `os.environ[<ENV_VAR>]` ngay trước khi build provider để adapter đọc được.
  Nếu không có provider nào có key, raise `NoProviderConfiguredError` và nơi gọi (`intake_agent`) tự
  rơi về nhánh deterministic — không im lặng dùng key rác.

⚠️ Lưu ý vận hành: `.env` hiện tại có `LLM_PROVIDER=DEEPSEEK_MODEL_NAME` — đây là giá trị **không hợp
lệ** so với `Literal["auto","openai","deepseek","gemini","anthropic","openrouter"]` khai ở
`src/config.py:24`, cần sửa thành `auto` (để dùng thứ tự ưu tiên) hoặc `deepseek` (ép cứng 1 provider)
trước khi chạy, nếu không `get_settings()` sẽ raise lỗi validation lúc khởi động.

Kiến trúc **không phụ thuộc một model cụ thể** - việc bản cũ gọi tên "Gemma 3 4B" là mô tả một dự
định chưa triển khai, không phải hiện trạng. Nếu sau này nối Gemma, nó thay vào đúng vị trí adapter
này mà không đổi kiến trúc.

Trong toàn bộ quy trình, AI chỉ đóng vai trò **Clinical Decision Support**. Hệ thống không chẩn đoán
bệnh, không kê đơn, không thay thế bác sĩ/điều dưỡng và không tự động đưa ra hướng xử trí cuối cùng.

### 3.2. Workflow

**Luồng A — Triage pipeline (đường quyết định chính):**

```text
Patient
    |
    v
Conversation Agent
    |
    v
Tool Orchestration Preflight
(Normalize / Language / Safety / Risk Extraction)
    |
    v
Semantic Mapper
(Natural Language -> Structured Data)
[hiện tại: rule-backed; điểm nối LLM adapter trong tương lai]
    |
    v
Checklist Validator
(Schema / Missing Fields / Contradiction Check)
    |
    v
Red-Flag Safety Layer            <-- chạy MỖI LƯỢT, không đợi checklist đủ
(Emergency Escalation Detection)
    |
    v
Protocol-Grounded Triage Decision Engine
(Priority Proposal + Guideline Evidence)
    |
    v
Summary Generator
    |
    v
Quality Guard  --(low_quality VÀ không có red-flag)--> không đẩy vào hàng đợi
    |
    v
Nurse Dashboard
(Approve / Override / Escalate / Reject / Ask more)
    |
    v
Approved Response
    |
    v
Patient
```

**Luồng B — Intake conversation (demo hỏi-đáp):**

```text
Patient message
    |
    v
Red-Flag Scan (rule thuần, KHÔNG LLM)   <-- bước ĐẦU TIÊN mỗi lượt
    |                                        cảnh báo hiện ngay, không chờ duyệt
    v
LLM Extraction -> điền checklist
(chỉ trích xuất, không suy diễn, không ghi đè giá trị cũ)
    |
    v
Red-Flag Scan lần 2 trên field vừa trích xuất
(LLM có thể chuẩn hoá "li bi" -> "li bì", quét lại để không bỏ sót)
    |
    v
Completeness Check
    |
    +--(< 85% trường bắt buộc)--> LLM sinh câu hỏi tiếp theo tự nhiên --> quay lại
    |
    +--(>= 85%, tức 6/7 trường)--> Phiếu tóm tắt
                                        |
                                        v
                            Bệnh nhân xác nhận
                            "Đúng rồi" -> chốt phiên
                            "Chưa đúng" + đính chính -> quay lại thu thập
```

### 3.3. Thành phần hệ thống

#### 1. Conversation Agent

Conversation Agent điều khiển luồng hội thoại với bệnh nhân.

Chức năng chính:

- Thu thập triệu chứng theo checklist.
- Theo dõi trạng thái hội thoại theo từng phiên.
- Xác định trường thông tin còn thiếu.
- Đặt câu hỏi tiếp theo dựa trên checklist và protocol.
- Không cho phép bỏ qua các trường bắt buộc.
- Chuyển ca sang điều dưỡng nếu bệnh nhân có dấu hiệu nguy hiểm, thông tin mâu thuẫn hoặc vượt ngưỡng an toàn.

Conversation Agent không tự kết luận chẩn đoán và không tự gửi hướng xử trí cuối cùng cho bệnh nhân.

#### 2. Semantic Mapper / Intake Extraction

Thành phần chuyển ngôn ngữ tự nhiên thành dữ liệu có cấu trúc. Hiện có **hai bản triển khai** ứng
với hai luồng ở mục 3.1:

**2a. `RuleBackedSemanticMapper`** (`src/services/semantic_mapper.py`) — dùng trong Luồng A.

- Rule-based thuần bằng so khớp từ khoá, **không gọi LLM**.
- Ưu điểm: deterministic, test được, chạy offline, không tốn chi phí API.
- Hạn chế đã biết: không hiểu từ đồng nghĩa/lỗi chính tả ngoài danh sách từ khoá cứng.
- Đây là chỗ để nối LLM adapter sau này (interface `SemanticMapper` trong `src/models/protocols.py`
  đã tách sẵn, `TriagePipeline.__init__` nhận `mapper` qua tham số nên thay được mà không sửa pipeline).

Ví dụ output (`StructuredSymptomData`):

```json
{
  "symptom_group": "chest_pain",
  "fields": {
    "chest_pain": true,
    "shortness_of_breath": true,
    "onset": "this_morning"
  },
  "missing_fields": ["pain_severity", "pain_radiation"],
  "confidence": 0.86
}
```

**2b. `IntakeAgent`** (`src/services/intake_agent.py`) — dùng trong Luồng B, **có gọi LLM thật**.

Ba tác vụ, mỗi tác vụ một prompt riêng:

| Tác vụ | Ràng buộc trong prompt |
|---|---|
| `extract()` | Chỉ trích xuất thông tin đã có trong tin nhắn; không suy diễn; không ghi đè trường đã có |
| `extract_correction()` | Chỉ trả về trường bệnh nhân đang chủ động sửa; **cấm** diễn đạt lại trường không được nhắc tới |
| `next_question()` | Sinh 1 câu hỏi tự nhiên cho tối đa 2 trường thiếu; cấm chẩn đoán/nhận định nguy hiểm |

Tách `extract_correction()` khỏi `extract()` là bắt buộc: nếu dùng chung, LLM sẽ trích lại cả trường
không được sửa và có thể **làm nghèo dữ liệu đã có** (đã quan sát thật: `"đau bụng"` bị ghi đè thành
`"đau"` khi bệnh nhân chỉ đang sửa tuổi).

Khi LLM lỗi hoặc chưa cấu hình, cả hai luồng đều rơi về fallback deterministic. Việc này **không im
lặng**: API trả cờ `llm_used`/`llm_available` và UI hiển thị rõ đang chạy chế độ nào.

LLM ở cả hai vị trí đều không đưa ra chẩn đoán, không kết luận bệnh và không tự quyết mức ưu tiên.

#### 3. Checklist Validator

Checklist Validator kiểm tra dữ liệu sau khi Gemma mapping.

Bao gồm:

- Kiểm tra JSON schema.
- Kiểm tra kiểu dữ liệu.
- Kiểm tra trường bắt buộc.
- Phát hiện dữ liệu mâu thuẫn.
- Kiểm tra độ tin cậy của mapping.
- Yêu cầu hỏi bổ sung nếu còn thiếu thông tin.

Nếu dữ liệu không hợp lệ, hệ thống không chuyển sang triage decision mà quay lại Conversation Agent để hỏi rõ thêm hoặc chuyển điều dưỡng nếu rủi ro cao.

#### 4. Red-Flag Safety Layer

Red-Flag Safety Layer là lớp an toàn bắt buộc để phát hiện các dấu hiệu nguy hiểm.

Ví dụ red-flag:

- Đau ngực kèm khó thở, vã mồ hôi, ngất hoặc đau lan tay/hàm.
- Khó thở nặng.
- Dấu hiệu đột quỵ: méo miệng, yếu liệt tay chân, nói khó, lú lẫn đột ngột.
- Chảy máu nặng.
- Co giật.
- Mất ý thức.
- Đau đầu dữ dội đột ngột.
- Sốt cao ở nhóm nguy cơ cao nếu protocol quy định.

Khi phát hiện red-flag, hệ thống phải:

- Đề xuất mức **Emergency**.
- Chuyển ca ngay sang hàng đợi điều dưỡng ưu tiên cao.
- Hiển thị cảnh báo rõ ràng trong Nurse Dashboard.
- Không tự động gửi kết luận cuối cùng cho bệnh nhân khi chưa có phê duyệt.

#### 5. Protocol-Grounded Triage Decision Engine

Triage Decision Engine sử dụng dữ liệu đã chuẩn hóa và bảng protocol triage để đề xuất mức độ ưu tiên.

Chức năng:

- Tra bảng phân độ/guideline đã cấu hình.
- Đề xuất mức độ ưu tiên.
- Xác định ca cần escalate.
- Sinh trạng thái triage.
- Ghi lại lý do phân độ và guideline/protocol được dùng.

Output gồm:

- **Emergency**: cần xử trí/cấp cứu ngay.
- **Urgent**: cần khám sớm.
- **Routine**: có thể đặt lịch khám thông thường.
- **Self-care**: tự chăm sóc tại nhà nếu protocol cho phép.

Đây chỉ là đề xuất, không phải quyết định cuối cùng. Điều dưỡng/bác sĩ có quyền chỉnh sửa, hạ/nâng mức ưu tiên hoặc từ chối đề xuất.

#### 6. Summary Generator

Summary Generator tự động tạo phiếu tóm tắt dành cho nhân viên y tế.

Nội dung phiếu gồm:

- Triệu chứng chính.
- Thời điểm khởi phát.
- Mức độ nghiêm trọng.
- Triệu chứng đi kèm.
- Yếu tố nguy cơ nếu có.
- Checklist đã hoàn thành.
- Thông tin còn thiếu.
- Red-flag được phát hiện.
- Mức ưu tiên AI đề xuất.
- Lý do phân độ và protocol liên quan.

Phiếu tóm tắt dùng để bàn giao cho điều dưỡng, không phải văn bản chẩn đoán cho bệnh nhân.

#### 7. Nurse Dashboard (Human-in-the-Loop)

Nurse Dashboard là cổng phê duyệt bắt buộc trước khi gửi kết quả cho bệnh nhân.

Nhân viên y tế có thể:

- Xem toàn bộ hội thoại.
- Xem dữ liệu đã mapping.
- Xem checklist đã hoàn thành và thông tin còn thiếu.
- Xem cảnh báo red-flag.
- Xem mức ưu tiên AI đề xuất.
- Xem lý do phân độ có trích protocol/guideline.
- Chỉnh sửa thông tin.
- Thay đổi mức ưu tiên.
- Phê duyệt hoặc từ chối đề xuất.
- Gửi hướng xử trí đã duyệt cho bệnh nhân.

Hệ thống chỉ gửi kết quả cho bệnh nhân sau khi đã được xác nhận bởi nhân viên y tế.

#### 8. Audit Log & Analytics

Hệ thống cần ghi log phục vụ kiểm toán và đánh giá chất lượng.

Log nên bao gồm:

- Tin nhắn bệnh nhân.
- Kết quả semantic mapping.
- Các trường bị thiếu hoặc mâu thuẫn.
- Red-flag được phát hiện.
- Mức ưu tiên AI đề xuất.
- Điều chỉnh của điều dưỡng/bác sĩ.
- Thời gian xử lý.
- Kết quả cuối cùng đã được phê duyệt.

Dữ liệu log cần được bảo vệ như PHI/PII và chỉ dùng cho mục đích kiểm toán, cải thiện hệ thống hoặc thống kê độ chính xác so với điều dưỡng.

### 3.4. Vai trò của AI

Trong VMedTriage, AI được sử dụng cho các tác vụ:

- Hiểu ngôn ngữ tự nhiên.
- Semantic Mapping.
- Information Extraction.
- Chuẩn hóa dữ liệu.
- Phát hiện thông tin thiếu/mâu thuẫn ở mức dữ liệu.
- Sinh phiếu tóm tắt.

AI không được:

- Chẩn đoán bệnh.
- Kê đơn.
- Thay thế bác sĩ hoặc điều dưỡng.
- Tự động gửi hướng xử trí cho bệnh nhân.
- Bịa guideline hoặc protocol không tồn tại.
- Tạo quyết định triage cuối cùng khi chưa có phê duyệt.

### 3.5. Luồng dữ liệu

```text
Patient Message
        |
        v
Tool Orchestrator Preflight
(Normalize / Language / Crisis Safety / Risk Factors)
        |
        v
Gemma 3 4B Semantic Mapper
        |
        v
Structured JSON
        |
        v
Checklist Validator
        |
        v
Checklist / Session Database
        |
        v
Red-Flag Safety Layer
        |
        v
Protocol-Grounded Triage Decision Engine
        |
        v
Summary + Explanation
        |
        v
Nurse Approval
        |
        v
Approved Patient Response
```

### 3.6. Điểm mới của giải pháp

Trong thiết kế mục tiêu, VMedTriage sử dụng **Gemma 3 4B** để thực hiện Semantic Mapping thay cho rule-based mapping thuần túy. Điều này giúp hệ thống hiểu nhiều cách diễn đạt khác nhau của bệnh nhân, bao gồm câu nói tự nhiên, từ đồng nghĩa, lỗi chính tả phổ biến và mô tả không đầy đủ, rồi chuyển đổi về cùng một cấu trúc dữ liệu chuẩn theo checklist. Bản MVP vẫn giữ rule-backed mapper để chạy offline, kiểm thử deterministic và fallback khi LLM chưa được cấu hình.

Điểm mới này làm tăng độ linh hoạt ở bước thu thập triệu chứng, nhưng vẫn giữ an toàn bằng cách đặt Gemma trong phạm vi mapping và extraction. Các bước ra quyết định được kiểm soát bởi validator, red-flag safety layer, protocol-grounded triage engine và cổng phê duyệt của điều dưỡng/bác sĩ.

---

## 4. Đánh giá theo yêu cầu đề bài

| Yêu cầu đề bài | Mức đáp ứng | Ghi chú |
|---|---:|---|
| App deploy | Đạt ở mức public demo | Đã có FastAPI UI, Docker và Render Blueprint; in-memory state chưa phù hợp production. |
| 2 role: bệnh nhân, điều dưỡng | Đạt | Cần mô tả rõ quyền của từng role trong UI/API. |
| Agent hỏi đáp triage có cấu trúc | Đạt | Conversation Agent + Checklist Validator đáp ứng. |
| Phân 3-4 mức ưu tiên | Đạt | Emergency, Urgent, Routine, Self-care. |
| Hướng xử trí đề xuất | Đạt có điều kiện | Chỉ được gửi sau khi điều dưỡng/bác sĩ duyệt. |
| Red-flag escalation | Đạt ở mức MVP | Có rule safety và bổ sung self-harm high-risk từ orchestration preflight. |
| Disclaimer rõ | Cần bổ sung ở UI/response layer | Nên có disclaimer trong màn hình bệnh nhân. |
| HITL bắt buộc | Đạt | Nurse Dashboard là approval gate. |
| Không chẩn đoán thay bác sĩ | Đạt | Cần duy trì trong prompt, schema và UI text. |
| Grounded trên protocol triage | Đạt ở mức local MVP | Protocol engine dùng cấu hình local; cần guideline store được quản trị và version hóa trước production. |
| Chống bịa | Cần kiểm soát bằng schema + protocol lookup | Không cho LLM tự tạo guideline. |
| Bảo mật PII/PHI | Đạt ở mức framework MVP | Đã có PHI redactor, access-control checker, consent/policy tool và audit contract; encryption, authentication và persistent audit store vẫn cần trước production. |
| Queue realtime cho điều dưỡng | Đạt ở mức demo | Có queue/dashboard in-memory; chưa có durable queue hoặc realtime broker. |
| Memory phiên & phiếu bàn giao | Đạt | Session state + Summary Generator. |
| Giải thích lý do có trích guideline | Đạt một phần | Proposal có protocol id và reason; cần citation/version đầy đủ từ guideline store thật. |
| Xử lý thiếu/mâu thuẫn | Đạt | Validator + follow-up questions. |
| Audit log & thống kê accuracy | Đạt ở mức local MVP | Registry tự ghi audit cho tool call; đã có metrics, quality, grounding, safety-event và drift tool. Cần persistent store và dashboard trước production. |

---

## 5. Khuyến nghị triển khai MVP

MVP nên ưu tiên 6 luồng sau:

1. Bệnh nhân nhập mô tả triệu chứng.
2. Gemma 3 4B mapping sang JSON schema cố định.
3. Validator phát hiện trường thiếu và agent hỏi bổ sung.
4. Red-flag layer phát hiện dấu hiệu nguy hiểm.
5. Protocol engine đề xuất Emergency/Urgent/Routine/Self-care kèm lý do.
6. Điều dưỡng duyệt/chỉnh sửa trước khi bệnh nhân nhận phản hồi.

Không nên để Gemma trực tiếp quyết định mức triage hoặc sinh hướng xử trí cuối cùng. Cách an toàn hơn là để Gemma làm semantic mapping, còn triage proposal dựa trên protocol và được HITL phê duyệt.

---

## 6. Framework Update - Demo UI

Ngay 2026-08-02, framework bo sung Demo UI co ban de trinh dien luong hoi dap VMedTriage.

Code UI nam trong:

```text
src/ui/
    static_files.py
    static/index.html
    static/styles.css
    static/app.js
```

FastAPI mount static UI tai `/`, trong khi API van nam tai `/api/v1`.

Demo UI gom 3 vung chinh:

1. Patient chat: gui mo ta trieu chung va nhan cau hoi bo sung hoac thong bao cho duyet.
2. Case details: hien thi status, triage proposal, structured mapping, validation, red flags va queue item.
3. Nurse review: approve, escalate hoac ask more de the hien cong HITL bat buoc.

Nguyen tac an toan khong doi:

- UI khong hien thi ket luan xu tri cuoi cung neu chua co nurse/doctor approval.
- Red flag chi day case vao hang doi uu tien va canh bao nurse dashboard.
- Structured mapping va proposal chi phuc vu review noi bo.

---

## 7. Framework Update - Render Public Deploy

Ngay 2026-08-02, framework bo sung cau hinh Render Blueprint de deploy public demo.

File moi:

```text
render.yaml
_guidance/deploy_render.md
```

Render chay mot Python Web Service:

```text
branch: tuananhpham
buildCommand: pip install -r requirements.txt
startCommand: uvicorn src.main:app --host 0.0.0.0 --port $PORT
healthCheckPath: /health
```

UI public nam tai `/`, API nam tai `/api/v1`.

Luu y framework:

- Deploy public hien dung in-memory case store, chi phu hop demo.
- Khong nhap PHI that tren public demo.
- Database, auth, audit store va persistent HITL queue can duoc bo sung truoc production y te.

---

## 8. Framework Update - Executable Tool Catalog and Orchestrator

Ngày 2026-08-03, framework được mở rộng từ 6 MCP descriptor thành catalog thực thi gồm **82 tool**, chia
thành 12 nhóm A-L trong `src/tool/catalog/`:

1. Intake & Conversation.
2. Semantic Mapping.
3. Validation & Follow-up.
4. Safety / Red Flag.
5. Clinical Knowledge / RAG.
6. Triage Decision Support.
7. EHR / FHIR.
8. Nurse Workflow / HITL.
9. Audit / Compliance / Governance.
10. Notification.
11. Analytics / Evaluation.
12. Orchestrator Internal.

### 8.1. Kiến trúc tool framework

```text
User Query / Agent State
          |
          v
ToolOrchestrator
(build deterministic plan)
          |
          v
CatalogToolRegistry
(discovery + policy + output validation + audit)
          |
          v
Local Catalog Adapter
(development/demo)
          |
          v
CatalogToolResult

Agent / MCP API
          |
          v
MCPToolRegistry -> StreamableHTTPMCPClient -> Configured MCP Server
          |
          v
MCPToolCallResult
```

Local catalog registry và external MCP registry là hai execution path riêng. Việc tách này ngăn một MCP
server chưa cấu hình bị thay bằng kết quả local nhưng vẫn báo như external call thành công.

Các module framework chính:

| File | Trách nhiệm |
|---|---|
| `src/tool/catalog/framework.py` | Khai báo `ToolExecutionContext`, metadata và output contract chuẩn. |
| `src/tool/catalog/registry.py` | Discover 82 tool, áp policy, validate output và ghi audit. |
| `src/tool/catalog/implementations.py` | Implementation local cho toàn bộ nhóm A-L. |
| `src/tool/catalog/state.py` | In-memory state cho conversation, FHIR demo, queue, audit, outbox và metrics. |
| `src/tool/catalog/orchestrator.py` | Lập kế hoạch và điều hướng patient query tới chuỗi tool. |

Mỗi file `tool_<id>_<name>.py` giữ metadata `TOOL_SPEC` và entry point thống nhất:

```python
result = await execute(arguments, context)
```

Output chuẩn:

```json
{
  "tool_id": 1,
  "tool_name": "patient_message_normalizer",
  "ok": true,
  "data": {},
  "error": null,
  "metadata": {
    "source": "local",
    "confidence": 1.0,
    "requires_human_review": false,
    "patient_visible": false,
    "latency_ms": 0.1,
    "trace_id": null
  }
}
```

### 8.2. Policy và side effect

- Tool read-only có thể chạy trong orchestration preflight.
- Tool Clinical Decision Support luôn tạo kết quả nội bộ và có cờ yêu cầu human review.
- Tool side-effect như ghi FHIR, assign case, gửi thông báo hoặc đặt lịch cần
  `ToolExecutionContext(approved=True)`.
- Mọi tool call qua registry được ghi audit với tool id, argument keys, actor, case, latency và trạng thái.
- Output cho bệnh nhân vẫn phải qua safety filter và cổng HITL; tool result không tự động trở thành patient response.

### 8.3. Pipeline sau cập nhật

Pipeline production ch?y preflight g?m:

```text
patient_message_normalizer
    -> language_detector
    -> symptom_extraction_tool
    -> self_harm_risk_detector
    -> abuse_or_violence_detector
    -> risk_factor_extraction_tool
```

Sau preflight, pipeline tiếp tục theo thứ tự validator, red-flag safety, protocol engine, summary, nurse
queue, persistence và patient-safe response. Ngôn ngữ có nguy cơ tự hại mức cao được chuyển thành red flag
để bắt buộc escalation và human review.

### 8.4. Giới hạn hiện tại

- Local implementation là deterministic MVP, không phải hệ thống clinical terminology đã chứng nhận.
- FHIR, SMS, email, push và paging dùng in-memory state/outbox; `sent=false` hoặc `delivered=false` nghĩa là
  provider ngoài chưa xác nhận gửi.
- Dữ liệu mất khi process restart.
- MCP endpoint cũ vẫn yêu cầu URL server được cấu hình; không âm thầm giả lập external call thành công.
- Trước production y tế cần authentication, RBAC gắn với identity thật, encryption, persistent database,
  secret management, terminology license, provider credentials và clinical validation.

---

## 9. Framework Update - Chốt workflow: Structured Multi-Step Reasoning trong Single-Agent (không phải Multi-Agent)

Ngày 2026-08-07. Mục này chốt lại workflow sau khi thảo luận một hướng mở rộng (SLM checklist →
conversation graph → GNN triage classifier → nurse feedback scoring). Kết luận: **giữ nguyên khung
Single-Agent Hybrid + Protocol-Grounded Tools + HITL đã chốt ở mục 2** — không tách thành nhiều agent
độc lập ra quyết định song song. Mọi ý tưởng mới được đưa vào làm **tool/service bổ sung trong
Conversation Agent + tool catalog hiện có** (`src/tool/catalog/`, nhóm A-L ở mục 8), không phải agent
riêng. Chi tiết implementation nằm ở `ARCHITECTURE.md` (mục "Framework Update 2026-08-07"); mục này
chỉ ghi lại **lý do thiết kế**.

### 9.1. Vì sao bẻ lại từ "multi-agent" sang "single-agent + tool catalog"

Đề xuất ban đầu mô tả pipeline dưới dạng nhiều "agent" độc lập (Red-Flag Guard, Quality Guard,
Checklist Extraction Agent, Graph Builder, Decision Arbiter, Feedback/Calibration Agent...). Về mặt kỹ
thuật, các bước này đúng và cần thiết, nhưng khung "multi-agent" mâu thuẫn với nguyên tắc đã chốt ở
mục 2 của tài liệu này: một agent chính điều phối, quyết định do engine có kiểm soát sinh ra. Đã đổi
tên khung tư duy: **các "agent" đó thực chất là tool/bước xử lý deterministic**, chạy tuần tự dưới
`TriagePipeline`/`ToolOrchestrator` hiện có — không có tranh chấp quyền quyết định giữa nhiều tác nhân.

### 9.2. Red-flag mỗi turn — đã đúng từ trước, không cần sửa

Một lo ngại nêu ra là "red-flag phải chạy mỗi turn, không đợi checklist đủ mới check". Sau khi đọc lại
`src/services/triage_pipeline.py`: `RedFlagSafetyLayer.detect()` **đã** chạy vô điều kiện mỗi turn
trên `structured_data` gộp luỹ kế (không phụ thuộc `validation.is_valid`), và `_derive_case_status`
trả `NEEDS_NURSE_REVIEW` ngay khi có `red_flags` bất kể checklist đã đủ hay chưa. Tức là yêu cầu
"phát hiện red-flag ngay từ lượt đầu" (đặc tả #1) đã được đáp ứng đúng trong code hiện tại — **không
có thay đổi nào cần làm ở đây**, chỉ xác nhận lại bằng cách đọc code thay vì giả định.

### 9.3. Checklist theo từng bệnh + dataset có nhãn

5 bộ dataset `data/triage_*.csv` (đau bụng, đau đầu, đau ngực, khó thở, sốt — 609 dòng) là **nhãn tự
sinh (silver-label)**, không phải bác sĩ gán, và lệch nhãn nặng theo từng slug triệu chứng (ví dụ
`shortness_of_breath` xuất hiện ở cả 3 mức nhãn). Vì vậy dataset này **không** được dùng để huấn luyện
trực tiếp một classifier tự quyết định mức triage — chỉ dùng để: (a) mở rộng eval set sau khi
dedupe/quy đổi nhãn, (b) audit coverage của `RED_FLAG_RULES` hiện tại, (c) làm corpus case tương tự
cho phần GNN advisory (mục 9.5, vẫn ở dạng #TODO).

Đã phát hiện và vá một gap thật: `REQUIRED_FIELDS_BY_SYMPTOM_GROUP` (`src/config.py`) trước đó không
có nhóm nào khớp `triage_daudau.csv` (đau đầu) — đã bổ sung nhóm `headache` cùng red-flag rule
`thunderclap_headache` và protocol rule tương ứng.

### 9.4. Quality Guard và HITL mở rộng (reject/ask_more)

- Quality Guard chỉ được phép **gắn nhãn quan sát** (`quality_flag`), không có quyền tự đổi trạng
  thái case. Quyết định suppress case "vớ vẩn" khỏi hàng đợi nằm ở đúng một chỗ
  (`case_approval.list_queue`) và luôn kiểm tra `not red_flags` trước — an toàn luôn thắng.
- `reject`/`ask_more` được thêm vào `case_approval.py` (luồng Gen2 khớp đặc tả #2), không phải vào
  `hitl_review.py` (Gen1, legacy demo, đã bị deprecate — xem `ARCHITECTURE.md`). `reject` bắt buộc
  `reason_code` để tách tín hiệu: chỉ lý do "AI sai" mới được tính vào thống kê đồng thuận
  AI–điều dưỡng, lý do "đã xử lý offline" hoặc khác không được lẫn vào phép đo.

### 9.5. GNN Advisory Signal — tách riêng, đánh dấu #TODO cho người khác phụ trách

> **[SUPERSEDED 2026-08-07, cùng ngày]** — Quyết định "tách riêng, không nối" ở mục này đã bị **đảo
> ngược** ở mục 10. Giữ lại nguyên văn bên dưới làm lịch sử quyết định (lý do ban đầu vẫn đúng và vẫn
> là ràng buộc bắt buộc ở thiết kế mới — xem 10.2), không xoá.

Phần dual-embedding (text summary + conversation graph) → GNN → gợi ý mức ưu tiên **không được thay
thế** `ProtocolTriageEngine`/`RedFlagSafetyLayer` — lý do: GNN là black-box, không tra bảng phân độ,
vi phạm trực tiếp nguyên tắc "chống bịa" và "grounded trên protocol" ở mục 2-3.4. Toàn bộ phần này đã
được tách vào file riêng `src/services/graph_triage_advisor.py`, chưa có logic thật
(`NotImplementedError`), không được gọi ở bất kỳ pipeline nào hiện tại, kèm checklist việc cần làm chi
tiết trong docstring (schema graph, dual embedding, ingest dataset đã dedupe, explainability bắt buộc
trước khi hiển thị cho nurse, calibration offline loại trừ lý do reject không liên quan accuracy).
Người phụ trách phần này chỉ cần đọc docstring của file đó, không cần đọc lại toàn bộ ngữ cảnh hội
thoại thiết kế.

### 9.6. File/thư mục đã thay đổi trong đợt cập nhật này

| File | Thay đổi |
|---|---|
| `src/config.py` | Thêm nhóm checklist `headache` (fields, follow-up questions, red-flag rule, protocol rule) |
| `src/models/schemas.py` | Thêm `CaseStatus.NEEDS_MORE_INFO`/`WITHDRAWN`, `RejectReasonCode`, `ConversationQualityFlag`, `TriageCase.quality_flag` |
| `src/services/approval_store.py` | Thêm field `reason` vào `AuditLogEntry` |
| `src/services/case_approval.py` | Thêm `reject()`, `ask_more()`; `list_queue()` lọc thêm theo `quality_flag` |
| `src/services/case_flow.py` | Gọi `quality_guard.assess()` mỗi turn; xử lý status `NEEDS_MORE_INFO` khi bệnh nhân trả lời tiếp |
| `src/services/quality_guard.py` | **Mới** — heuristic rule-based, không LLM |
| `src/services/graph_triage_advisor.py` | **Mới** — #TODO, chưa implement, tách riêng khỏi luồng quyết định |
| `src/models/case_api.py` | Thêm `RejectRequest`, `AskMoreRequest`, `AuditActionResponse` |
| `src/api/routers/queue.py` | Thêm route `POST /cases/{id}/reject`, `POST /cases/{id}/ask_more` |
| `ARCHITECTURE.md` | Mục "Framework Update 2026-08-07": tài liệu hoá Gen2 REST API, flag trùng lặp Gen1/Gen2 |

Đã chạy `pytest` (30/30 pass) và `ruff check` (pass) trên toàn bộ file thay đổi, không phá vỡ hành vi
hiện có.
