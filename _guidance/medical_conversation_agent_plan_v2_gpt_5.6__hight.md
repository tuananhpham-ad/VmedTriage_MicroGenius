# Đánh giá kế hoạch V2 - Medical Conversation Agent

> Ngày đánh giá: 2026-08-19  
> Tài liệu được đánh giá: `_guidance/medical_conversation_agent_plan_v2.md`  
> Phạm vi: kiến trúc, an toàn y khoa, hợp đồng dữ liệu, khả năng tích hợp với code hiện tại, vận hành và kiểm thử.

## 1. Kết luận điều hành

**Quyết định: duyệt có điều kiện, chưa dùng làm implementation spec.**

Bản V2 đi đúng hướng ở cấp độ vision: tách conversation khỏi triage cuối, dùng active field set thay vì
điền toàn bộ schema, phân biệt phủ định với chưa biết, hỗ trợ đính chính, dùng state có cấu trúc và đặt
điều kiện dừng dựa trên nhiều tín hiệu. Tuy nhiên, tài liệu còn thiếu các bất biến an toàn, hợp đồng dữ
liệu và tiêu chí nghiệm thu đủ cụ thể để đội phát triển có thể triển khai mà không tự đưa ra những quyết
định lâm sàng/kiến trúc khác nhau.

Đặc biệt, V2 chưa giải quyết được bốn vấn đề chặn triển khai:

1. Luồng red flag trong V2 không bảo đảm short-circuit ngay trong lượt và đang mâu thuẫn với một số
   tài liệu nguồn thật của repo.
2. "Dynamic questions" chưa xác định LLM được chọn nội dung lâm sàng hay chỉ diễn đạt lại nội dung đã
   được protocol phê duyệt.
3. State `NULL/TRUE/FALSE/UNKNOWN` chưa đủ provenance để audit, sửa dữ kiện và phân biệt các loại thiếu
   thông tin.
4. Stop policy và information gain mới là ý tưởng, chưa phải thuật toán tất định có thể test.

Khuyến nghị là **mở rộng engine hiện tại**, không dựng một mạng nhiều LLM-agent độc lập. Repo đã có các
khối đáng giữ: `SymptomProtocol`, `common_safety`, `reducer`, `CoverageLedger`, `stage_machine`,
`rule_engine` và `escalation_lock`. Các tên như Router, Coverage Checker, Question Planner và Stop Agent
nên được hiểu là **trách nhiệm logic**; phần quyết định an toàn nên tiếp tục là code/rule tất định.

## 2. Chấm điểm

| Hạng mục | Điểm | Nhận xét |
|---|---:|---|
| Tầm nhìn sản phẩm | 8/10 | Phạm vi và ranh giới conversation/triage khá rõ |
| Mô hình hội thoại | 7/10 | Active fields, correction, batching và hybrid memory hợp lý |
| An toàn y khoa | 5/10 | Có nhận thức về red flag nhưng thiếu safety override hoàn chỉnh |
| Hợp đồng dữ liệu | 4/10 | Ví dụ JSON có ích nhưng chưa phải schema versioned/auditable |
| Tương thích repo | 6/10 | Có nhiều phần trùng với engine hiện tại, nhưng cũng xung đột ADR/PRD |
| Kiểm thử và đo lường | 3/10 | Chưa có dataset contract, metric, threshold và failure tests |
| Bảo mật/vận hành | 3/10 | Long-term memory có đề xuất nhưng thiếu consent, retention và recovery |

**Mức sẵn sàng triển khai: khoảng 4/10.** Đây là design note tốt, chưa phải đặc tả có thể giao thẳng cho
implementation.

## 3. Những điểm nên giữ

### 3.1 Active Field Set

Thiết kế `Global Schema -> Protocol Router -> Active Field Set` là đúng. Nó tránh mục tiêu sai là cố
điền hàng trăm field không liên quan, đồng thời cho phép coverage có mẫu số rõ ràng theo protocol đang
hoạt động.

Điều kiện cần bổ sung: field bị de-activate khi đổi protocol không được xóa; nó phải được giữ trong hồ
sơ với protocol/revision đã tạo ra nó.

### 3.2 Phân biệt khẳng định, phủ định và chưa biết

Việc khẳng định `NULL != UNKNOWN` là quan trọng. Phủ định rõ ràng là dữ kiện lâm sàng, không được bỏ khỏi
state chỉ vì UI không muốn hiển thị.

Điểm cần sửa là không nên dùng một enum duy nhất để vừa biểu diễn trạng thái thu thập, vừa biểu diễn giá
trị. Mô hình đề xuất nằm ở mục 6.

### 3.3 Correction và audit

Nguyên tắc "dữ kiện mới nhất thắng nhưng vẫn giữ lịch sử" phù hợp với reducer theo sự kiện trong code
hiện tại. Summary chỉ dùng giá trị hiệu lực hiện tại; audit vẫn phải giữ giá trị trước, bằng chứng, lượt
hội thoại và lý do thay đổi.

### 3.4 Coverage, batching và soft budget

Ưu tiên safety -> required -> protocol-specific -> optional, hỏi theo cụm nhỏ và dùng turn limit như
soft budget là hợp lý. Đây cũng là hướng engine hiện tại đã triển khai qua tier, batching và
`CoverageLedger`.

### 3.5 Một nguồn state cho hai summary

Natural summary và nurse JSON phải được dựng từ cùng snapshot là một bất biến tốt. Natural summary
không được là nguồn để sinh ngược nurse JSON, vì một lỗi diễn đạt sẽ trở thành lỗi dữ liệu.

### 3.6 Không tự merge lịch sử thành triệu chứng hiện tại

V2 xử lý đúng khi coi thông tin từ phiên cũ là history, không phải current truth. Đây phải là quy tắc
cứng, không chỉ là prompt.

## 4. Các vấn đề P0 phải sửa trước khi code

### P0.1 - Chưa có safety override hoàn chỉnh

V2 mô tả red flag là candidate/evidence và để triage downstream quyết định. Điều này đúng với nguyên
tắc "conversation agent không xếp loại triage", nhưng flow hiện tại của tài liệu vẫn cho red-flag đi
qua coverage/question planning/stop như một ca thường. Không có bất biến rằng một tín hiệu nguy hiểm đã
được xác nhận phải chặn mọi câu hỏi thường quy.

Repo hiện cũng có nguồn yêu cầu không thống nhất:

- `ARCHITECTURE.md:15-19`, `docs/prd.md:61-64` và ADR-004 yêu cầu phát hiện/escalate ngay.
- `docs/planning/Feature_Specification_VMedTriage.md:253-256` lại yêu cầu không gửi cảnh báo chi tiết
  cho bệnh nhân trước khi điều dưỡng duyệt.
- Code hiện tại dùng `escalation_lock`, `stop_reason="RED_FLAG"` và static `emergency_message`.

V2 không được âm thầm chọn một phía. Cần ADR mới xác định rõ **hai hành động độc lập**:

1. Khi nào case được khóa escalation và đẩy ưu tiên cho điều dưỡng.
2. Bệnh nhân được thấy thông điệp nào trước khi điều dưỡng duyệt.

Dù quyết định UI là gì, pipeline phải giữ các bất biến sau:

- Common-safety scan chạy sau mỗi user turn, độc lập với router và protocol chuyên biệt.
- Parse lỗi, timeout hoặc route sai không được làm mất text safety signal.
- Tín hiệu rõ và rule xác nhận red flag tạo `escalation_lock` đơn điệu: agent không tự hạ mức.
- Tín hiệu mơ hồ đẩy một câu xác nhận safety tĩnh lên đầu hàng đợi, không hỏi câu thường quy trước.
- Khi red flag được xác nhận: dừng interview thường, chụp snapshot chưa đầy đủ, tạo handoff và ưu tiên
  nurse queue ngay.
- Văn bản safety-facing phải là template đã duyệt, không do LLM ứng biến.

### P0.2 - Dynamic Question Generation xung đột với ADR-003

V2 nói Question Planner chọn field rồi LLM tạo câu hỏi. Nếu "tạo" bao gồm tự nghĩ thêm nội dung y khoa,
thiết kế này xung đột với `docs/context/decisions.md:23-29` và `docs/prd.md:61`, vốn giới hạn câu hỏi
trong checklist/protocol đã duyệt.

Cần chọn một trong hai và ghi ADR supersede:

- **Khuyến nghị:** planner tất định chỉ chọn `field_id/question_concept_id` từ protocol; LLM chỉ được
  diễn đạt câu hỏi non-safety trong phạm vi `script_hint`; output guard kiểm tra field và ý bắt buộc.
- Câu hỏi safety-critical luôn dùng template tĩnh.
- RAG có thể cung cấp tài liệu cho người thiết kế protocol, nhưng không được biến nội dung web vừa
  retrieve thành câu hỏi lâm sàng mới trong runtime.

Cách này vẫn cho hội thoại tự nhiên mà không làm mất khả năng audit câu hỏi nào đã được hỏi và tại sao.

### P0.3 - State chưa đủ để làm nguồn sự thật

`NULL/TRUE/FALSE/UNKNOWN` không biểu diễn được đầy đủ:

- chưa hỏi;
- đã hỏi nhưng không biết;
- từ chối trả lời;
- không áp dụng do nhánh cha;
- đã từng có nhưng bị rút lại;
- dữ kiện đến từ user hiện tại, history hay suy dẫn tất định;
- bằng chứng nào trong turn nào hỗ trợ giá trị.

Không nên coi `UNKNOWN` cho tất cả các trường hợp trên rồi cố suy ra bằng conversation log. Cần hợp đồng
field-level có status, value và evidence riêng, xem mục 6. State update phải đi qua một reducer duy nhất;
không module nào được merge dict trực tiếp.

### P0.4 - Stop Agent chưa phải policy có thể kiểm thử

`core_information_sufficient` và `expected information gain = LOW` chưa có định nghĩa tính toán. Nếu
giao cho LLM quyết định, cùng một state có thể dừng khác nhau giữa các lần chạy và khó chứng minh safety.

Stop policy nên là code/rule, theo thứ tự ưu tiên:

1. Luôn chạy safety scan của turn hiện tại.
2. Nếu red flag đã xác nhận: emergency handoff.
3. Nếu user yêu cầu dừng/tóm tắt/từ chối: tôn trọng quyền dừng, tạo **incomplete handoff** với data gaps;
   không ép trả lời thêm.
4. Nếu còn safety question chưa từng hỏi và user vẫn tiếp tục được: tiếp tục.
5. Nếu mandatory coverage đạt và next-field utility dưới ngưỡng cấu hình: offer summary hoặc summary.
6. Nếu chạm budget: không bỏ field mandatory chưa từng hỏi; nếu user không thể tiếp tục thì handoff
   thiếu dữ liệu, không suy diễn là ca an toàn.

"Information gain" ở MVP nên là score tất định, ví dụ:

```text
utility(field) = clinical_tier_weight
               + unresolved_safety_weight
               + protocol_dependency_weight
               - repeat_cost
               - user_burden_cost
```

Chỉ tune các trọng số trên dataset; không để model tự trả nhãn `LOW/HIGH` không được hiệu chỉnh.

### P0.5 - Router đa protocol chưa có semantics hợp nhất

Output `primary + secondary[]` chưa trả lời các câu hỏi quan trọng:

- Hai protocol có field cùng tên nhưng khác meaning/allowed values thì merge thế nào?
- Rule, tier, budget và question priority nào thắng?
- Khi đổi primary protocol, cluster đã hỏi được ánh xạ ra sao?
- Protocol revision nào đã tạo ra quyết định?
- Route sai có được fallback và chuyển lại mà không mất state không?

Cần stable field IDs, namespace hoặc canonical ontology, protocol version, transaction đổi protocol và
audit event `protocol_activated/deactivated/switched`. Common safety không được phụ thuộc route.

### P0.6 - Output contract chưa chốt

ADR-006 trong `docs/context/decisions.md` vẫn đang để trống, trong khi V2 đã đưa một ví dụ nurse JSON.
Ví dụ không phải schema. Cần chốt nghiệp vụ trước rồi định nghĩa JSON Schema/Pydantic versioned.

Các điểm phải quyết định:

- Gọi output là ISBAR hay chỉ `I/S/B/A` trước downstream. Không nên gọi ISBAR hoàn chỉnh nếu chưa có R.
- Unknown/refused quan trọng có nằm trong `data_gaps` hay bị bỏ hoàn toàn.
- Red-flag candidate khác confirmed red flag thế nào.
- Evidence/provenance có nằm trong payload nurse hay payload audit liên kết.
- `triage_category` và recommendation được append bằng schema version nào.
- Nurse edit tạo revision mới, không ghi đè generated snapshot.

Quy tắc "field không có giá trị thì không xuất" chỉ phù hợp với UI. Nurse handoff vẫn cần một danh sách
`data_gaps` cho field critical/mandatory; bỏ key hoàn toàn sẽ làm downstream không phân biệt "không hỏi"
với "schema không có field này".

### P0.7 - Long-term memory thiếu điều kiện bảo mật

Đề xuất tự lấy ba summary gần nhất chưa có consent, mục đích sử dụng, retention, xóa dữ liệu, phân quyền,
audit truy cập, mã hóa, data minimization hoặc quy tắc loại thông tin nhạy cảm. Đây là PHI/PII, không
phải memory tiện ích thông thường.

Khuyến nghị đưa cross-conversation memory ra khỏi MVP cho đến khi có:

- opt-in/opt-out rõ ràng;
- policy retention và deletion;
- tenant/user isolation và authorization test;
- relevance filter theo complaint, không mặc định nạp ba phiên;
- nhãn `historical`, timestamp và nguồn trên mọi dữ kiện được nạp;
- cấm history đi vào current state nếu chưa được user xác nhận lại.

## 5. Các vấn đề P1

### P1.1 - Flow trong chính V2 chưa nhất quán

Sơ đồ đầu tài liệu đặt `LLM Response -> Continue/Stop Decision`, trong khi Action Flow cuối đặt Stop
Decision trước nhánh Question Planner/Summarizer. Cần một thứ tự duy nhất. Đề xuất: update state -> safety
-> coverage -> stop policy -> planner -> verbalizer.

### P1.2 - `conversation_id` không nên là timestamp

Ví dụ dùng timestamp làm ID có nguy cơ collision và trộn identity với thời gian. Dùng UUID/ULID cho ID;
`created_at` là timestamp UTC riêng. Mọi update cần optimistic version/idempotency key để hai request
song song không ghi đè state.

### P1.3 - RAG quá rộng và chưa có governance

V2 đưa RAG vào Router, Planner, Red-flag Detector, Response và Summarizer nhưng chưa nêu corpus, nguồn,
version, ngày hiệu lực, quyền truy cập, prompt-injection defense hay fallback khi retrieval lỗi.

Protocol và safety rule nên đến từ corpus curated đã được chuyên môn duyệt, có `document_id/version`.
Summary không cần RAG để diễn giải dữ kiện user; đưa retrieval vào đó chỉ tăng bề mặt hallucination.

### P1.4 - Chọn model chưa dựa trên benchmark

Tên `Qwen/Qwen3.5-4B` chỉ nên là candidate. Cần benchmark trên tiếng Việt y khoa thực tế: route recall,
field exact match, negation, temporality, subject attribution, correction, JSON validity, latency, cost
và hành vi khi context dài. Model nhỏ chỉ được đưa vào khi đạt gate trên bộ dữ liệu của dự án.

### P1.5 - Phiên đang dở chưa bền vững

`ARCHITECTURE.md:364-369` ghi `session_store` mất khi restart. V2 nói long-term memory nhưng chưa giải
quyết crash recovery cho cuộc hội thoại đang thu thập. Cần persist event log/snapshot sau mỗi accepted
turn, hoặc ghi rõ đây là giới hạn MVP và UX phục hồi bắt buộc.

### P1.6 - Thiếu threat model và observability

Cần ít nhất các sự kiện/metric: model timeout, invalid JSON, rejected evidence, route/switch, correction,
retraction, contradiction, safety signal, red-flag short-circuit, stop reason, missing mandatory field,
latency/cost mỗi call, prompt/protocol/model version. Log không được chứa PHI nguyên văn ngoài nơi được
phép và phải có retention riêng.

## 6. Hợp đồng state đề xuất

Không cần ép toàn bộ code dùng đúng hình dạng dưới đây ngay, nhưng semantics phải tương đương:

```json
{
  "field_id": "abdominal.pain_location",
  "status": "answered",
  "value": "rlq",
  "polarity": "positive",
  "missing_reason": null,
  "evidence": [
    {
      "message_id": "msg_01",
      "span": "đau bên phải bụng",
      "source": "patient_current_turn"
    }
  ],
  "protocol_id": "abdominal",
  "protocol_version": "1.2.0",
  "updated_at": "2026-08-19T08:00:00Z",
  "revision": 3
}
```

`status` nên là một trong:

```text
unasked | answered | unknown | refused | not_applicable | retracted
```

Với field boolean, `value=true/false` chỉ xuất hiện khi `status=answered`. Không dùng `false` để biểu
diễn chưa biết. `not_applicable` phải do dependency rule tất định tạo ra. `retracted` phải có audit event;
snapshot hiệu lực có thể quy về unknown nhưng không được mất lịch sử.

Mỗi field update cần thỏa:

- evidence span thật nằm trong user message, hoặc source là deterministic derivation có input refs;
- không dùng confidence do LLM tự khai làm quyết định an toàn;
- correction mới thắng giá trị cũ nhưng red-flag escalation lock không tự hạ;
- history và current-turn là hai source khác nhau;
- summary chỉ đọc snapshot đã validate.

## 7. Kiến trúc đích đề xuất

```text
User turn
   |
   +--> L0 text safety scan (deterministic, route-independent)
   |
   +--> Extractor (LLM) --> schema/evidence validator
                            |
                            v
                    Event-based reducer
                            |
                    Canonical state snapshot
                            |
          +-----------------+------------------+
          |                                    |
   Common safety rules                 Protocol registry/router
          |                                    |
     confirmed red flag?                  Active field set
       /          \                            |
     yes          no                      Coverage ledger
      |            |                            |
 escalation lock   +--------------------> Stop policy (code)
 static action                                  |
 snapshot + queue                      continue / handoff
                                               |
                                      Question selector (code)
                                               |
                                template or constrained verbalizer
                                               |
                                         Output guard

Validated snapshot --> Natural summary renderer
                   --> Versioned nurse handoff JSON
                   --> downstream triage/recommendation
```

Không cần tách mỗi hộp thành service/process riêng. Trong MVP, chúng có thể là module thuần trong cùng
FastAPI process. Ranh giới quan trọng là ai có quyền thay đổi state và ai có quyền tạo quyết định safety.

## 8. Lộ trình triển khai thực tế

### Phase 0 - Chốt quyết định

1. Viết ADR supersede/clarify cho red-flag patient message và dynamic question scope.
2. Chốt format nurse handoff và schema version 1.
3. Chốt protocol ownership: ai duyệt field, tier, rule, template và version.

### Phase 1 - Củng cố nền hiện có

1. Giữ `common_safety`, `reducer`, coverage ledger và escalation lock.
2. Bổ sung field provenance/status semantics và persistence theo turn.
3. Bảo đảm L0 safety scan không phụ thuộc LLM/router.
4. Chuẩn hóa protocol version, stable IDs và switch audit.

### Phase 2 - Planner và stop policy

1. Planner chỉ xếp hạng field/concept trong active protocols.
2. Safety templates tĩnh; non-safety verbalizer bị output guard giới hạn.
3. Stop policy tất định, trả reason code và data gaps.
4. Không tạo một LLM Stop Agent riêng.

### Phase 3 - Output

1. Natural summary và nurse JSON đọc cùng validated snapshot.
2. Thêm contradiction check giữa hai output.
3. Nurse edit tạo immutable revision + audit.
4. Downstream enrich triage/recommendation, không ghi ngược làm biến dạng source snapshot.

### Phase 4 - Mở rộng protocol

Làm từng vertical slice hoàn chỉnh: protocol -> fields -> questions -> rules -> summary -> golden tests.
Không mở đồng thời Fever, Abdominal, Headache, Skin, Respiratory khi hợp đồng chung chưa ổn định.

### Phase 5 - Long-term memory

Chỉ triển khai sau security/privacy review và consent flow. Đây không phải dependency để hoàn thành
Medical Conversation Agent MVP.

## 9. Quality gates bắt buộc

### Safety

- 100% red-flag recall trên release gate đã khóa, luôn báo kèm `n` và khoảng tin cậy.
- 0 ca confirmed red flag bị hỏi câu thường quy sau khi rule đã trigger.
- 0 lỗi model/router làm tắt common-safety scan.
- Test riêng negation, temporality, subject khác bệnh nhân, hypothetical, correction và mixed intent.
- Model timeout/invalid JSON vẫn tạo được safety fallback và nurse handoff.

### Extraction/state

- Field exact match tách riêng positive, negative, unknown/refused và attributes.
- Evidence precision: span phải có thật trong message; không có span thì không nhận giá trị LLM.
- 0 dữ kiện hallucinated trong golden release set.
- Correction/retraction/contradiction giữ đúng audit và không làm mất escalation lock.

### Router/planner

- Đo route recall theo từng protocol, không chỉ accuracy tổng.
- Route sai không làm mất common-safety coverage.
- 0 câu hỏi ngoài concept/template đã được protocol cho phép.
- Repeat-question rate, số lượt median/p95 và mandatory-unasked count phải được báo theo nhóm ca.

### Stop/output

- Mọi stop có stable reason code.
- Normal completion không còn mandatory field chưa từng hỏi; refusal/end intent được đánh dấu incomplete.
- Natural summary và nurse JSON không mâu thuẫn trên positive/negative/current value.
- Unknown critical field xuất trong `data_gaps`, không biến mất do omit-null renderer.
- Schema validation và round-trip test cho mọi output version.

### Vận hành và HITL

- p50/p95 latency, LLM calls/turn, tokens/session và cost/session.
- Recovery test khi process restart giữa phiên.
- Authorization test ngăn đọc chéo case/memory.
- Audit đầy đủ ai/model/protocol/version đã tạo hoặc sửa dữ kiện/quyết định.
- Đánh giá thủ công bởi người có thẩm quyền y khoa trước mỗi protocol release.

## 10. Đối chiếu với hướng dẫn bên ngoài

WHO yêu cầu AI y tế đặt an toàn, quyền tự chủ, minh bạch, trách nhiệm giải trình, bao trùm và khả năng
đáp ứng/bền vững làm nguyên tắc quản trị; WHO cũng nhấn mạnh expert supervision và rigorous evaluation
đối với LLM trong y tế. Các yêu cầu về human oversight, provenance, audit, controlled protocol và
evaluation gates ở trên phù hợp với định hướng đó:

- [WHO - Ethics and governance of artificial intelligence for health](https://www.who.int/publications/i/item/9789240029200)
- [WHO - Ethics and governance of AI for health: guidance on large multi-modal models](https://www.who.int/publications/i/item/9789240084759)
- [WHO calls for safe and ethical AI for health](https://www.who.int/news/item/16-05-2023-who-calls-for-safe-and-ethical-ai-for-health)

Các nguồn này là khung quản trị, không thay thế việc người có thẩm quyền tại dự án phê duyệt protocol,
rule, ngưỡng lâm sàng và nội dung cảnh báo áp dụng trong bối cảnh Việt Nam.

## 11. Tiêu chí để nâng trạng thái lên "Approved for implementation"

V2 có thể được duyệt triển khai khi hoàn thành đủ các điều kiện sau:

1. ADR red-flag/HITL và ADR dynamic-question đã chốt, không còn hai nguồn thật xung đột.
2. Có schema versioned cho state event, state snapshot và nurse handoff.
3. Safety override, escalation lock và failure behavior được viết thành invariants/test cases.
4. Stop policy là thuật toán tất định với reason codes, không phải judgment tự do của LLM.
5. Protocol merge/switch/version semantics đã rõ.
6. Có golden dataset và quality gates cho safety, extraction, router, stop, summary và model failure.
7. Long-term memory được bỏ khỏi MVP hoặc có privacy/security specification riêng.

Sau các sửa đổi này, kế hoạch có thể trở thành kiến trúc V2 khả thi mà không phải phá bỏ nền tảng đã có.
