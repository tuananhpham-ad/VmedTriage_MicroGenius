# Kế hoạch nâng cấp agent hỏi đáp và trích xuất triệu chứng

> Bản này đã được đối chiếu với code thật (2026-08-17). Mọi khẳng định về hiện trạng đều kèm
> `file:line` để kiểm chứng lại; nếu sửa code mà không sửa mục §2 tương ứng thì tài liệu này lại
> thành sai như bản trước.
>
> **Cập nhật 2026-08-19 — đã nhập YÊU CẦU CHỦ DỰ ÁN và kết quả vòng review
> `medical_conversation_agent_plan_v2*.md`.** Hai thứ khác nhau, và cách xử lý cũng khác nhau:
>
> - **Yêu cầu chủ dự án (16 điểm)** — là quyết định sản phẩm, không phải đề xuất để thẩm định. Toàn
>   bộ nằm ở **§15**, mỗi điểm kèm điều kiện an toàn tối thiểu và chỗ nó nằm trong kế hoạch. Ba điểm
>   tôi có phản biện kỹ thuật (§15.3 lọc field, §15.8 suy `False`, §15.9 thứ tự memory) được ghi đúng
>   một lần rồi chuyển sang phương án thực thi.
> - **Ba tài liệu V2** (bản gốc + hai bản đánh giá) — là tài liệu diễn giải, không thay thế kế hoạch
>   này. Phần còn giá trị đã rút vào: §9 P0.6 (lỗi an toàn), §9 P3.9, §9 PC+, §17 (phiếu bàn giao).
>   Tóm tắt ở §2.7.
>
> Bản này **thay thế** mục "phạm vi bị loại trừ" của bản 2026-08-19 sáng: bốn mục từng bị đánh dấu
> LOẠI ở đó đều đã được chủ dự án khẳng định lại, nên chuyển thành *có làm, kèm điều kiện*.
>
> Quyết định kiến trúc đã chốt: **deterministic controller + model workers + protocol-grounded
> tools + HITL**. Controller là code/state machine, không phải SLM/LLM. Model được phân tầng theo
> tác vụ (trích xuất, router phụ trợ, diễn đạt), còn rule engine giữ nguyên toàn quyền quyết định
> mức triage và stage machine giữ toàn quyền chọn cụm câu hỏi tiếp theo.

## 1. Kết luận ngắn

Không dùng một prompt/một output LLM để vừa trò chuyện, vừa tự quyết định triệu chứng, vừa chọn câu
hỏi tiếp theo. Cũng không biến mỗi bước pipeline thành một "agent" có quyền tự quyết. Mỗi tác vụ có
thể dùng một model tier khác nhau, nhưng quyền điều phối và quyết định an toàn vẫn nằm ở code.

Mỗi lượt hội thoại đi qua sáu tầng:

```text
Tin nhắn người dùng
  L0  text_safety_signals   [KHÔNG model]  -> ứng viên red flag trên text thô, không tự kết luận
  L1  controller            [KHÔNG model]  -> điều phối theo session/state/policy cố định
  L2  symptom_group_router  [SLM tùy chọn] -> gợi ý protocol khi rule chưa quyết được
  L2  fact_extractor        [SLM/LLM]      -> field_events JSON kèm bằng chứng
  L3  reducer + rule_engine [KHÔNG model]  -> snapshot, cụm kế tiếp, mức triage
  L4  synthesis/renderer    [SLM/LLM]      -> câu tiếng Việt theo ResponsePlan đóng
  L5  output_guard          [KHÔNG model]  -> chặn chẩn đoán/câu hỏi ngoài plan
```

Không mặc định hai tầng L2 chạy song song. Schema extraction phụ thuộc protocol/cụm hiện tại; chỉ
lượt mở dùng schema harvest chung mới có thể trích xuất trước rồi route sau. Router model chỉ được
gọi khi router deterministic chưa đủ bằng chứng, tránh thêm latency vào mọi lượt.

Nguyên tắc bất biến của **kiến trúc mục tiêu**, quan trọng hơn mọi chi tiết còn lại trong tài liệu
này (hiện trạng chưa đạt mục 3 cho tới khi hoàn tất P0):

1. **Mọi tầng ghi "KHÔNG model" là tầng an toàn — không bao giờ được thay bằng một lời gọi model, kể cả khi model tốt lên.** Đó là những tầng khiến hệ thống test được bằng fake LLM và audit được sau sự cố.
2. **Controller là code, không phải model.** Nó chọn worker theo policy cố định, không chọn câu hỏi
   lâm sàng và tuyệt đối không chọn mức ưu tiên.
3. Không có đường nào để một lỗi model làm mất red flag.
4. Model không kết luận chẩn đoán bệnh. Không có bước nào tên `diagnose_disease` trong hệ thống này.
5. **Trải nghiệm hội thoại là yêu cầu sản phẩm, không phải phần thưởng thêm.** Một agent hỏi đúng
   nhưng khiến người bệnh bỏ giữa chừng thì không thu được triệu chứng nào — độ phủ bằng 0.

Hai mục tiêu "hỏi linh hoạt tự nhiên" và "khai phá đủ triệu chứng" nghe như đánh đổi nhưng không
phải, vì trong code **yêu cầu độ phủ và thứ tự hỏi đã là hai thứ tách rời**: độ phủ do tier field
M0/M1 quyết (`mandatory_fields_covered`, `stage_machine.py:64`), còn thứ tự chỉ là first-fit theo
thứ tự khai báo (`next_cluster`, `stage_machine.py:106`). Nới thứ tự không đụng tới bảo đảm độ phủ.
Cách nới: thay first-fit bằng **hàm xếp hạng tất định** — không trao quyền chọn câu hỏi cho model.
Chi tiết ở §8.

## 2. Hiện trạng trong repo

### 2.1. Khoảng trống defense-in-depth: text safety signals ~~chưa chạy~~ ĐÃ chạy trong luồng chuẩn

> **Cập nhật 2026-08-17 — P0.1 ĐÃ XONG.** Tầng L0 nằm ở
> `src/services/symptom_protocol/common_safety/text_safety_signals.py`, được gọi trong
> `session.submit_message` **trước** nhánh lượt mở và trước mọi lời gọi model. Test:
> `tests/test_services/test_text_safety_signals.py` (25 ca). Phần mô tả hiện trạng bên dưới giữ
> nguyên vì nó là lý do tầng này tồn tại, nhưng câu "chỉ có hai caller" nay đã cũ.
>
> Thiết kế đã chốt khi implement:
> - `scan_text_safety_signals()` trả `TextSafetySignal` có `status` ∈ {`confirmed_positive`,
>   `needs_confirmation`, `suppressed`} + `guard` ghi rõ guard nào đã đổi trạng thái (audit).
> - Ba guard: polarity (cửa sổ 60 ký tự, cắt tại dấu câu và liên từ đối lập), temporality (mốc quá
>   khứ hạ xuống `needs_confirmation`, cue "đang/bây giờ" ghi đè), subject (người khác/giả định/đuôi
>   nghi vấn "... không?").
> - `SHORT_CIRCUIT_CODES` — 32/100 mã được phép short-circuit. **Vẫn chờ clinical governance ký
>   duyệt.** Mã ngoài danh sách dù dương tính rõ vẫn đi đường xác nhận (`guard=not_reviewed`).
> - Khi model trả về không dữ kiện xác định nào mà lượt đó có tín hiệu mơ hồ:
>   `session._safety_confirmation` phát câu xác nhận **tĩnh**, giữ nguyên cụm, mỗi mã hỏi đúng 1 lần.
> - **Phát sinh ngoài kế hoạch:** `intake_agent.scan_opportunistic_fields` cũng khớp substring trên
>   text thô và ghi `seizure_occurred="true"` cho câu "tôi không co giật". Đã dùng chung guard
>   polarity (`text_safety_signals.all_mentions_negated`) — một bản luật phủ định, một chỗ định nghĩa.
>
> **Còn nợ:** đẩy cụm xác nhận red flag lên đầu hàng đợi (policy 2 ở dưới) mới chỉ có đường dự phòng
> tĩnh, chưa có ưu tiên cụm thật — việc đó thuộc ranking ở §8.3/P3.

Đây là phát hiện quan trọng nhất và là lý do P0 ở §9 không phụ thuộc vào bất kỳ việc kiến trúc nào.

`detect_text_red_flags` (`src/services/engines/red_flag_text_rules.py:158`) chỉ có hai caller:

- `src/services/agents/intake_agent.py:107` — agent intake **cũ**, không nằm trên luồng UI;
- `src/services/engines/red_flag.py:28` — và **không module nào trong `src/services/symptom_protocol/` hay `src/services/sessions/` import `engines.red_flag`**.

Luồng thật là `POST /chat` (`src/api/routes.py`) → `symptom_session` → `symptom_protocol.session.submit_message`, và ở đó escalation chỉ đến từ `common_safety/rules.py` chạy trên **field đã được LLM trích xuất** (`session.py:300`, `session.py:358`).

Hệ quả: LLM trả JSON hỏng, timeout, hoặc provider chết → không còn lớp deterministic nào quan sát
text thô để ưu tiên xử lý một tín hiệu nguy hiểm. Đây là khoảng trống defense-in-depth so với nguyên
tắc red-flag escalate ngay trong `CLAUDE.md`.

Tuy nhiên, **không được nối thẳng matcher hiện tại vào `EMERGENCY`**. Hàm
`detect_text_red_flags()` chỉ kiểm tra substring, chưa xử lý polarity, temporality hay subject. Kiểm
thử trực tiếp cho thấy cả ba câu phủ định sau vẫn match red flag:

```text
"Toi khong co giat"                -> seizure
"Be khong kho tho nang"            -> severe_breathing
"Khong co moi tim hay co giat"     -> cyanosis + seizure
```

Vì vậy tầng mới phải tên là **L0 `text_safety_signals`** và output ban đầu chỉ là tín hiệu ứng viên,
không phải `reason_codes` chính thức. Policy xử lý:

1. Mẫu dương tính rõ, đang diễn ra, đã được clinical review (ví dụ "bé đang co giật") có thể
   short-circuit bằng thông điệp tĩnh.
2. Match còn mơ hồ phải đẩy cụm xác nhận red flag lên đầu, không tự kết luận và không được im lặng
   bỏ qua khi model lỗi.
3. Phủ định, tiền sử cũ hoặc nói về người khác phải được loại bằng guard deterministic/validated
   extraction trước khi tạo disposition.

L0 phải tồn tại trước mọi lời gọi model, nhưng P0 là **thiết kế lại + nối có guard**, không phải chỉ
thêm một lời gọi hàm vào `submit_message`.

### 2.2. Luồng chuẩn và các đường legacy/tooling đang cùng tồn tại

| Đường | Trạng thái |
| --- | --- |
| `src/services/symptom_protocol/` + `sessions/symptom_session.py` | **Luồng chuẩn**, phục vụ `POST /chat` và `/chat/stream` |
| `src/api/routers/fever_intake.py` | **Vẫn được mount** (`src/main.py:57`), cùng `sessions/fever_session.py` |
| `src/api/routers/result.py` | Vẫn được mount (`src/main.py:56`), nhưng đây là đường đọc kết quả/disclaimer, **không phải intake pipeline cạnh tranh** |
| `src/services/agents/intake_agent.py` | Agent cũ; extraction bỏ qua field đã có (`skip_existing`, `intake_agent.py:252`) |
| `src/tool/catalog/` (82 tool + `ToolOrchestrator`) + `src/services/triage_pipeline.py` | **Đã có orchestrator nhưng nằm chết** — caller duy nhất là `tests/test_tools/test_catalog.py:10` |

Hai lưu ý khi dọn dẹp:

- ~~`symptom_protocol/intake_agent.py:24` vẫn `from src.services.agents.intake_agent import _parse_json_object`.~~
  **ĐÃ VÁ 2026-08-17** — hàm nay ở `src/services/infra/json_output.py`. Luồng chuẩn không còn phụ
  thuộc ngược vào agent cũ, nên xoá agent cũ giờ chỉ còn là xoá file.
- **Trước khi mở rộng controller deterministic của luồng chuẩn, phải quyết số phận
  `src/tool/catalog/orchestrator.py`.** Nó đã có `ToolOrchestrator`, `CatalogToolRegistry`,
  `ToolExecutionContext`, policy enforcement và audit trace — nhưng plan là danh sách 6 bước tĩnh
  (`orchestrator.py:36`) của pipeline legacy/tooling. Xây thêm một orchestration abstraction mà không
  quyết cái cũ sẽ tạo thêm đường song song khó audit.

### 2.3. Nhiều cơ chế trong kế hoạch cũ ĐÃ được implement

Đừng viết lại. Những thứ sau đang chạy:

- `_merge_answers` (`symptom_protocol/intake_agent.py:662`): giá trị xác định mới nhất ghi đè giá trị cũ; `unknown` không làm mất dữ kiện đã biết.
- `retraction.apply_retraction`: field cha bị phủ định → field con về `unknown` (`retraction.py:30`).
- `retraction.find_contradictions`: mở lại cụm cần làm rõ khi hai dữ kiện xung đột.
- `registry.select_protocol` + `_fever_ruled_out` (`registry.py:41`): đổi từ protocol sốt sang tổng quát khi người dùng rút lại lời khai. **Đây là sàn deterministic của `symptom_group_router`.**
- `_generate_question` (`intake_agent.py:802`): model chỉ diễn đạt câu hỏi mà rule engine đã chọn, temperature riêng cho bước này.
- **Validation bằng chứng đã có**: `_evidence_in_message` (`intake_agent.py:508`), `EvidencePolicy` (`asked`/`unasked`), `_repair_bareword_unknown`.
- `escalation_lock` (`session.py:94`): escalation đã khoá không bị hạ.
- `answer_quality`: đã nhận diện `correction`, `asks_question`, `non_answer` — **đây là tiền thân của
  `dialogue_act` mà extractor sẽ trả cùng field events**, nhưng hiện chưa được dùng để tạo phản hồi
  phù hợp cho từng loại.

Vì thế một phần “Definition of Done” ở §13 **có thể đã pass sẵn**. Phải đo trước khi sửa (§9 P0).

### 2.4. Hạ tầng evaluation đã có sẵn — nhưng có ba lỗ hổng, hai đã vá

- `eval/scripts/run_eval.py` — có sẵn cờ `--fail-under-triage-accuracy`, `--fail-under-red-flag-recall`.
- `data/golden_cases_v1.jsonl` — 120 ca, kèm `expected_red_flags`, `expected_triage`, `expected_handoff`.

> **Cập nhật 2026-08-17 sau khi chạy thật.** Ba điều bản trước nói không đúng:
>
> 1. **"120 ca multi-turn" — thực tế mỗi ca đúng 2 lượt bệnh nhân**, trong khi protocol cần ~10-20
>    lượt để kết luận. Hệ quả: chỉ đo được nhánh ĐỎ (escalate sớm); `EARLY_VISIT`/`SELF_CARE` không
>    bao giờ đạt tới, mọi ca không escalate đều đọng ở kết luận tạm `Urgent`. Muốn đo hai mức kia
>    cần **bệnh nhân mô phỏng** trả lời tiếp, hoặc golden case dài lượt hơn.
> 2. **`--mode api` đã hỏng từ khi thêm auth** — `/api/v1/chat` đòi Bearer token, mọi ca trả HTTP
>    401. ĐÃ VÁ: thêm `--bearer-token`.
> 3. **Chấm điểm trên response bệnh nhân luôn ra 0%** — `_patient_chat_response` CỐ Ý che
>    `triage_proposal`/`red_flags` (đúng ràng buộc HITL). ĐÃ VÁ: thêm `--nurse-token`, harness đọc
>    lại case qua `GET /cases/{id}`.
>
> **Chưa vá:** mã red flag của hệ thống (`RF-07`, `RF-12`, `TEXT_SIGNAL_*`) và của golden case
> (`RF-TRAUMA-POISONING-001`, ...) là hai hệ từ vựng khác nhau, không có bảng quy đổi ⇒ red-flag
> recall đo ra 0% dù hệ thống có phát hiện. **Bảng quy đổi là quyết định lâm sàng, không phải việc
> engineering.**

Không tạo bộ 50 ca mới từ đầu. Việc đúng là gán nhãn **field-level** cho tập đã có và bổ sung nhánh correction/retraction còn thiếu.

### 2.5. Hệ thống KHÔNG chỉ dùng một provider

`src/services/infra/provider_router.py` xoay vòng 5 provider với fallback hai cấp; `src/config.py:42` đặt thứ tự mặc định `gemini,deepseek,openai,anthropic,openrouter`, còn `render.yaml` ghi đè thành `openrouter,deepseek,gemini,openai,anthropic`. Model đang cấu hình: `gemini-3.1-flash-lite` (production), `deepseek-chat`, `gpt-4o-mini`, `claude-haiku-4-5`.

Điểm cần biết cho §7: **`credential` không tái dụng được để pin model theo vai trò.** Tham số này cố ý **tắt fallback** vì nó mang key của người dùng (`provider_router.py:336`) — dùng nó cho việc định tuyến vai trò sẽ vô tình làm mọi vai trò mất khả năng fallback.

### 2.6. Hạ tầng hiện tại KHÔNG chạy được SLM 4–7B

- `render.yaml` đang `plan: free` — CPU-only, RAM rất hạn chế. Không load nổi model 4B, chưa nói 7–8B.
- `requirements.txt` đã **cố ý** tách `torch`/`transformers` sang `requirements-graph.txt` vì torch một mình đã ~2.5 GB, và `src/graph_triage/service.py` import lazy để app vẫn boot khi thiếu.
- `SUPPORTED_MODEL_NAME=Qwen/Qwen3-8B` đã có trong `src/config.py:75` và `render.yaml`, nhưng chỉ được đọc **một chỗ duy nhất** làm chuỗi metadata (`src/pipeline/full_pipeline.py:54`) — chưa load model nào.

Kết luận: SLM phải là **service riêng**, không nhét vào app hiện tại. Chi tiết ở §7.2.

### 2.7. Vòng review kế hoạch V2 (2026-08-19) — cái gì được nhập vào đây

`_guidance/medical_conversation_agent_plan_v2.md` mô tả một agent hội thoại thu thập triệu chứng tổng
quát. Đối chiếu từng mục với code: **16/19 mục đã tồn tại trong `src/services/symptom_protocol/`**, và
ở những chỗ V2 khác code hiện tại thì nó khác theo chiều **kém an toàn hơn** (Stop Agent bằng LLM thay
`should_stop` tất định, LLM router thay router rule, RAG sinh câu hỏi lâm sàng thay checklist đã duyệt,
memory xuyên phiên chứa PHI). Chi tiết đối chiếu ở `medical_conversation_agent_plan_v2_claude_high.md`
§3; các mục bị loại khỏi phạm vi ghi ở §15 dưới đây.

Bốn thứ **thật sự mới** đã được nhập vào kế hoạch này:

| Phát hiện | Loại | Nhập vào |
| --- | --- | --- |
| `should_stop` xét `user_can_continue` **trước** `provisional_emergency_signal`, ngược với chính docstring của nó | **Lỗi an toàn trong code hiện tại** | §9 P0.6 |
| Không có đường nào để ý định người dùng ("tóm tắt đi", "tôi không trả lời nữa") tác động vào `should_stop` | Gap thật | §9 P3.9 |
| Một phiên chỉ gắn được **một** protocol; ca "đau bụng + sốt 39" phải chọn một | Gap thật, nhưng vô nghĩa trước khi có 4 protocol kia | §9 PC+ |
| ISBAR có template thật của team, nhưng ADR-006 vẫn trống và `HandoffSummary` thiếu 5 trường | Hợp đồng dữ liệu | §17 |

Cái V2 làm tốt và đáng giữ: nó là bản diễn giải dễ đọc, có ví dụ hội thoại tiếng Việt cụ thể — dùng để
onboard người mới hoặc giải thích cho PM/PO. Đó không phải giá trị của một implementation plan, nên nó
được đánh dấu *superseded by tài liệu này* chứ không bị xoá.

> **Lưu ý khi đọc §2.7 cùng §15.** Bảng trên là kết quả đối chiếu V2 với code. §15 là yêu cầu chủ dự
> án, và ở bốn chỗ nó **đi xa hơn** kết luận của bảng này: red flag hai nhánh có đối chiếu (§15.1),
> điều dưỡng sửa được red flag (§15.4), RAG grounding có phạm vi (§15.6), memory ba tầng (§15.9).
> Khi hai mục mâu thuẫn, **§15 thắng** — nó là quyết định sản phẩm, còn §2.7 chỉ là ghi nhận hiện trạng.

## 3. `symptom_group_router` — không phải "disease detector"

“Sốt”, “đau bụng”, “khó thở” là triệu chứng/than phiền chính, không phải kết luận bệnh. Model không được suy diễn “sốt xuất huyết”, “cúm”, “viêm phổi”… từ hội thoại.

Vì vậy agent này tên là **`symptom_group_router`**, không phải `disease_detector`. Nhiệm vụ của nó là chọn **một trong 5 nhóm triệu chứng của MVP** (hoặc `general`) để nạp đúng protocol, hết. Nó không sinh danh sách chẩn đoán phân biệt, không xếp mức ưu tiên.

Tên nội bộ dùng thống nhất: `extract_clinical_facts`, `select_symptom_protocol`, `evaluate_triage_rules`.

Router có **sàn deterministic**: `registry.select_protocol` (`registry.py:41`) đã hoạt động bằng luật thuần. Model chỉ được dùng để *cải thiện* độ nhạy khi luật không quyết được, và khi model chết thì rơi thẳng về luật — chi tiết ở §7.3.

### 3.1. Khi nào được gọi router model — danh sách đóng

“Chỉ gọi khi rule chưa đủ dữ liệu” là mô tả mục đích, không phải điều kiện implement được: mỗi người
sẽ hiểu một kiểu và cuối cùng router chạy mọi lượt. Điều kiện là **đúng bốn trigger** sau, không có
trường hợp thứ năm:

1. **Lượt mở** — phiên chưa gắn protocol nào.
2. `dialogue_act == new_symptom` — người bệnh tự nêu thêm một triệu chứng mới.
3. Lượt vừa rồi có `field_event` chạm field chief complaint.
4. `_fever_ruled_out` vừa bật (`registry.py:41`) — protocol hiện tại vừa mất căn cứ.

Ngoài bốn trường hợp đó: **không gọi**, dùng thẳng protocol đang gắn. Đây là điều kiện thuần code,
tính được từ `field_events` + session state, nên test được và đếm được: log tỉ lệ lượt có gọi router
để phát hiện sớm nếu nó lặng lẽ chạy mọi lượt.

Không cần đổi tên gì trong repo hiện tại: `grep -r "detect_disease\|disease_agent\|disease_detection" src tests docs` trả về 0 kết quả (chỉ còn `.pyc` cũ trong `__pycache__`). Đây là quy ước cho code viết mới.

## 4. Hợp đồng output cho `fact_extractor`

### 4.1. Không trả một snapshot mơ hồ

Extractor trả **các thay đổi của đúng lượt hiện tại**, kèm bằng chứng, thay vì viết lại toàn bộ hồ sơ:

```json
{
  "dialogue_act": "correction",
  "field_events": [
    {
      "field": "fever_reported",
      "operation": "set",
      "value": "false",
      "certainty": "explicit",
      "evidence_span": "mình không sốt"
    }
  ],
  "mentioned_but_unclear": [],
  "user_question": null
}
```

Các `dialogue_act` tối thiểu — extractor trả nhãn này trong cùng lời gọi trích xuất để
`DialoguePolicy` deterministic xử lý UX; controller không cần một model phân loại riêng:

- `answer`: trả lời câu vừa hỏi;
- `partial_answer`: chỉ trả lời một phần;
- `correction`: sửa/rút lại thông tin cũ;
- `new_symptom`: tự nêu thêm triệu chứng;
- `asks_clarification`: hỏi “bạn đang hỏi gì?”, “ý bạn là sao?”;
- `cannot_answer`: quên, không biết, không đo được;
- `off_topic`: nội dung không liên quan;
- `greeting`.

Các `operation` tối thiểu:

- `set`: xác nhận giá trị mới, kể cả `false`;
- `unset`: người dùng nói rõ thông tin cũ không còn đúng nhưng chưa cung cấp giá trị thay thế;
- `no_change`: không có bằng chứng để cập nhật field.

### 4.2. Phân biệt `false` / `unknown` — và `unset` là OPERATION, không phải giá trị

**Ở tầng event (output của model)** có ba `operation`: `set`, `unset`, `no_change`.

**Ở tầng snapshot (state của phiên)** chỉ có ba **giá trị**, đúng như `TriState` hiện tại (`intake_agent.py:34`):

- `"true"`: người dùng khẳng định rõ;
- `"false"`: người dùng phủ định rõ — “tôi không sốt”;
- `"unknown"`: chưa được nói tới, mơ hồ, hoặc người dùng không biết — “tôi quên nhiệt độ”.

Reducer quy `operation=unset` về giá trị `"unknown"` trong snapshot (đúng như `retraction._RETRACTED` đang làm), và ghi sự kiện `unset` vào audit log để phân biệt “chưa bao giờ hỏi” với “đã khai rồi rút lại”.

Lý do không thêm trạng thái thứ tư vào snapshot: `rule_engine.evaluate` và `common_safety/predicates.py` đang giả định đúng ba giá trị. Thêm giá trị thứ tư là thay đổi lan ra toàn bộ tầng luật an toàn — không đáng, vì thông tin “đã bị rút lại” chỉ cần cho audit và cho controller, không cần cho việc đánh giá luật.

Không dùng `null` cho cả ba ý nghĩa vì sẽ không biết người dùng phủ định, không biết, hay model không trích được.

### 4.3. Field bị đính chính vẫn phải xuất hiện trong output

```text
Lượt 1: “Tôi bị sốt”
=> event: fever_reported = true

Lượt 2: “Mình quên mất, mình không sốt”
=> event: fever_reported = false
=> snapshot cuối: fever_reported = false
=> temp_c/temp_site/fever_duration... được reducer xoá về unknown nếu trước đó có
=> history vẫn giữ cả hai sự kiện để audit
```

Không được trả `{}` ở lượt 2 chỉ vì `fever_reported` đã có giá trị. Không được xoá hẳn field `fever_reported`; giá trị `false` là dữ kiện quan trọng để `symptom_group_router` chọn lại protocol.

### 4.4. Bằng chứng và validation — mở rộng cái đang có, không viết mới

Cơ chế nền đã chạy: `_evidence_in_message` so khớp substring sau khi chuẩn hoá khoảng trắng + casefold, và `EvidencePolicy` phân biệt mức khắt khe cho field trong cụm và ngoài cụm.

Phần cần **bổ sung** khi chuyển sang schema event:

- kiểm `operation` hợp lệ và `field` nằm trong schema được phép của lượt này;
- `set` với giá trị `false` phải có `evidence_span` nhắc tới **chính triệu chứng đó**, không chấp nhận hạt phủ định trần (“Không”) — lỗi này đã được ghi nhận trong comment tại `intake_agent.py:498`;
- `unset` cũng phải có bằng chứng;
- field không hợp lệ bị loại riêng, không làm hỏng toàn bộ kết quả (hiện đã đúng, cần giữ);
- model không thêm field chẩn đoán hoặc hướng điều trị.

Với dấu hiệu đỏ, ưu tiên độ nhạy: tầng L0 chạy **độc lập** với mọi model, không phụ thuộc việc JSON có parse được hay không.

## 5. State reducer: nguồn sự thật của hồ sơ

Không để model tự merge trạng thái. Reducer thuần code nhận:

```text
previous_snapshot + current_field_events -> next_snapshot + audit_events + reopened_clusters
```

Quy tắc merge:

1. Dữ kiện xác định mới nhất có bằng chứng thắng dữ kiện cũ.
2. `unknown/no_change` không ghi đè dữ kiện xác định đã có.
3. `set false` phải ghi đè `true` khi đó là đính chính rõ.
4. Khi field cha bị phủ định, xoá dây chuyền field phụ thuộc. Ví dụ `fever_reported=false` làm `temp_c`, `temp_site`, `fever_onset_at`, `fever_duration_days`, thông tin thuốc hạ sốt… về `unknown`.
5. Với đính chính có rủi ro hiểu nhầm, không xoá ngay mà đặt `pending_confirmation`. Ví dụ “không sốt xuất huyết” không đồng nghĩa “không sốt”.
6. Mâu thuẫn không giải được bằng độ mới/bằng chứng thì giữ cờ contradiction và hỏi một câu xác nhận ngắn.
7. Lưu lịch sử sự kiện để debug và audit; downstream triage chỉ đọc snapshot hiện tại đã validate.
8. Một đính chính KHÔNG được tự hạ `escalation_lock` đã bật.

Quy tắc 1–4 và 8 phần lớn đã có trong `_merge_answers` + `retraction.py` + `session.escalation_lock`. **Mở rộng hai module đó**, không tạo cơ chế thứ hai song song.

## 6. Làm hội thoại tự nhiên hơn

### 6.1. Controller điều phối, `DialoguePolicy` tạo `ResponsePlan`, renderer chỉ viết câu

Ba trách nhiệm khác nhau, đừng gộp:

**Execution plan** — controller thuần code suy ra từ phase, protocol, current cluster và trạng thái
provider. Đây là cấu trúc nội bộ, không phải output model:

```json
{
  "invoke": ["fact_extractor"],
  "allow_optional_group_router": false,
  "current_cluster_id": "GENERIC_CHIEF_COMPLAINT"
}
```

**`ResponsePlan`** — `DialoguePolicy` deterministic tạo sau khi extraction, reducer, rule engine và
stage machine đã chạy. Rule engine chỉ cung cấp disposition/reason codes; nó không chịu trách nhiệm
viết acknowledgement hay trả lời meta-question:

```json
{
  "acknowledge": "Bạn vừa nói rằng hiện tại bạn không sốt.",
  "answer_user_question": "Mình đang muốn biết vấn đề chính bạn cần hỗ trợ.",
  "next_cluster_id": "GENERIC_CHIEF_COMPLAINT",
  "missing_fields": ["chief_complaint"],
  "max_questions": 1
}
```

**Renderer** chỉ chuyển `ResponsePlan` thành tiếng Việt tự nhiên; không tự chọn field, không thêm câu
hỏi y khoa. Với cụm safety-critical và thông điệp cấp cứu, bỏ renderer và dùng template tĩnh.

Với ví dụ hiện tại, phản hồi phù hợp là:

> Hiểu rồi, vậy hiện tại bạn không sốt. Bạn đang gặp triệu chứng hay khó chịu gì khiến bạn muốn được hỗ trợ?

Không mặc định người dùng chắc chắn “khó chịu ở một vùng” rồi hỏi vị trí, thời điểm, mức độ và xu hướng trong cùng một lượt.

**`DialoguePolicy` phải là bảng tra cứu, không phải chuỗi `if`.** Sau khi bỏ mọi tính thích ứng đến từ
model, toàn bộ sự tự nhiên của hệ thống dồn vào ranking (§8.3) và số nhánh của `DialoguePolicy`. Số
nhánh đó phình theo tích `dialogue_act × trạng thái cụm × trạng thái protocol` — 8 nhãn nhân với vài
trạng thái là đã vài chục tổ hợp. Khai báo dạng bảng (key → template/hành động) ngay từ đầu, vì:

- thiếu tổ hợp nào nhìn ra ngay, thay vì lẩn trong nhánh `else`;
- test được bằng cách duyệt toàn bảng, không phải nghĩ ra từng ca;
- thêm một `dialogue_act` mới là thêm một hàng, không phải sửa một hàm dài.

Refactor một chuỗi `if` 500 dòng thành bảng sau khi nó đã có test bám vào là việc đắt — làm đúng từ
đầu rẻ hơn nhiều.

### 6.2. Xử lý câu hỏi ngược/meta-question

Khi extractor trả `dialogue_act=asks_clarification`, `DialoguePolicy` phải **trả lời câu hỏi của người
dùng trước**, sau đó chỉ hỏi lại một ý bằng từ ngữ đơn giản hơn:

> Mình đang muốn biết vấn đề chính bạn cần hỗ trợ là gì, vì bạn vừa xác nhận không sốt. Hiện tại bạn đang thấy triệu chứng gì?

Không chỉ xin lỗi rồi lặp nguyên câu cũ. `asks_clarification` cũng không được tính là đã trả lời xong cụm.

### 6.3. Chính sách diễn đạt

- Mỗi lượt ưu tiên một mục tiêu lâm sàng; chỉ gộp tối đa 2 ý có liên quan chặt chẽ.
- Không hỏi lại thông tin đã biết, trừ khi đang xác nhận mâu thuẫn.
- Công nhận ngắn dữ kiện vừa nhận được, không nhắc lại toàn bộ hồ sơ.
- Xưng hô nhất quán nhưng tránh “dạ/ạ/anh ơi” ở mọi câu gây cảm giác kịch bản.
- Không ép người lớn nam 20 tuổi trả lời theo cách dành cho trẻ/người chăm sóc.
- Nếu người dùng nói “quên/không biết/không có dụng cụ”, chuyển sang phương án hỏi khác thay vì lặp yêu cầu đo.
- Nếu chuyển protocol, nói một câu chuyển hướng dễ hiểu; không để người dùng thấy hệ thống đột ngột hỏi một checklist mới.
- Red flag dùng thông điệp tĩnh đã duyệt, không qua renderer.

### 6.4. Trình bày: markdown, xuống dòng, dễ đọc

Đây là phần `synthesis` chịu trách nhiệm và là thứ người dùng cảm nhận rõ nhất:

- câu hỏi nhiều ý thì tách gạch đầu dòng, không nhồi một đoạn văn dài;
- tách đoạn giữa phần "công nhận thông tin" và phần "câu hỏi";
- in đậm đúng chỗ cần chú ý, không in đậm tràn lan;
- không dùng bảng, không dùng heading trong tin nhắn chat;
- output đi qua `/chat/stream` nên markdown phải hợp lệ **theo từng mẩu**, không được phụ thuộc ký tự đóng ở cuối.

### 6.5. Guard sau khi render (L5)

Trước khi gửi câu do model viết:

- kiểm tra có đúng 1–2 dấu hỏi theo plan;
- không chứa tên bệnh/chẩn đoán/hướng điều trị bị cấm;
- không hỏi field đã biết ngoài danh sách `missing_fields`;
- không chứa câu hỏi ngoài `next_cluster`;
- markdown parse được;
- nếu fail, dùng `script_hint` deterministic.

## 7. Phân tầng model theo vai trò

### 7.1. Vai trò nào dùng tầng model nào

| Vai trò | Tầng | Vì sao |
| --- | --- | --- |
| `text_safety_signals` (L0) | **Không model** | Quan sát text thô khi model chết; chỉ short-circuit với mẫu dương tính rõ đã duyệt, còn lại yêu cầu xác nhận (§2.1). |
| `controller` (L1) | **Không model** | Điều phối theo state/policy phải tái lập, test và audit được; không có lý do lâm sàng để thêm một lời gọi model. |
| `symptom_group_router` (L2) | **Rule trước, SLM tùy chọn** | Chỉ gọi SLM khi `registry.select_protocol` chưa quyết được. Output là đề xuất 5 nhóm + `general`, không phải chẩn đoán. |
| `fact_extractor` (L2) | **Model tốt nhất đã qua eval; hiện giữ LLM API** | Chỗ khó nhất: phủ định tiếng Việt, đính chính, số đo, khẩu ngữ/không dấu/typo. Sai ở đây là sai hồ sơ lâm sàng. **Không hạ xuống SLM khi chưa có số eval chứng minh.** |
| `reducer` + `rule_engine` (L3) | **Không model** | Tất định để test được bằng fake LLM và audit được sau sự cố. |
| `synthesis/renderer` (L4) | **SLM hoặc LLM đã qua eval**, temperature 0.4–0.7 | Nhiệm vụ bị giới hạn bởi `ResponsePlan`; fallback về template. Đây là ứng viên tốt để thử SLM trước extractor. |
| `output_guard` (L5) | **Không model** | Cùng lý do L0. |

Cấu hình `fact_extractor` giữ như hiện tại: temperature `0`, schema nhỏ theo cụm hiện tại + danh sách hẹp safety/switch fields, không đưa toàn bộ registry vào mỗi lượt, timeout ngắn, retry tối đa 1 lần, log model/version/latency/parse status — không log API key, có chính sách bảo vệ PHI.

### 7.2. Hạ tầng SLM tự host — PHỤ LỤC CÓ ĐIỀU KIỆN, không nằm trong kế hoạch gần

> Mục này chỉ được kích hoạt khi đã qua điều kiện tiên quyết bên dưới. Trước đó nó là tài liệu tham
> khảo, **không phải hạng mục công việc**.

§7.1 đã hạ SLM xuống thành worker tuỳ chọn, quyết định bằng eval. Hai điều đó không đi cùng với việc
dựng một service GPU ngay: nếu SLM là một tối ưu hoá **chưa chứng minh được là cần**, thì xây hạ tầng
cho nó trước khi có số liệu là làm ngược thứ tự.

> **Cập nhật 2026-08-17 — điều kiện 1 ĐÃ CÓ SỐ, và nó nghiêng về "chưa đáng".**
> Đo trên `deepseek-chat`: một lượt tốn ~4s, trong đó `synthesis` chỉ **1.2s** còn `fact_extractor`
> **3.8s**. Hạ `synthesis` xuống SLM tự host tiết kiệm tối đa ~1.2s/lượt, mà `fact_extractor` -
> phần chiếm thời gian - thì §7.1 đã chốt không hạ khi chưa có số eval chứng minh. Điều kiện 2 và 3
> vẫn chưa được trả lời. Chi tiết: `eval/baselines/2026-08-17-p0-summary.md`.

**Điều kiện tiên quyết — phải đủ cả ba mới bắt đầu:**

1. Đã có số latency/chi phí thật của `gemini-3.1-flash-lite` (và provider fallback) ở vai trò
   renderer, đo trên tập golden case — không phải ước lượng.
2. Con số đó cho thấy chi phí hoặc p95 latency **thật sự là vấn đề** ở quy mô đang nhắm tới.
3. Có người và có máy để vận hành một service GPU dài hạn — kể cả sau khi sprint kết thúc.

Thiếu bất kỳ điều nào: tiếp tục dùng provider API, và mục này nằm yên. Ghi rõ như vậy để không ai
đọc §7.1 rồi hiểu thành “sprint này dựng GPU box”.

**Nếu đã qua điều kiện**, thiết kế như sau — SLM chạy trên **service riêng**, không nằm trong app
FastAPI hiện tại (§2.6):

- Serving: vLLM hoặc Ollama, cả hai đều expose endpoint **OpenAI-compatible**.
- App gọi qua HTTP như một provider bình thường. **Không** thêm `torch`/`transformers` vào `requirements.txt`.
- Điểm sửa trong code:
  - thêm `ProviderSpec("local_slm", "local_slm_api_key", "LOCAL_SLM_API_KEY", "local_slm_model_name")` vào `PROVIDER_SPECS` (`provider_router.py:77`);
  - thêm `local_slm_base_url` / `local_slm_model_name` vào `Settings` (`src/config.py`);
  - mở rộng nhánh base_url trong `_build_provider` (`provider_router.py:234`) — hiện chỉ OpenRouter được truyền base_url;
  - map `local_slm` → `OpenAIProvider` trong `make_provider` (`src/providers/__init__.py:27`). `OpenAIProvider` đã nhận `base_url` sẵn (`openai_provider.py:20`) nên không cần adapter mới.
- `SUPPORTED_MODEL_NAME=Qwen/Qwen3-8B` đang có sẵn nhưng chỉ là metadata (§2.6) — hoặc dùng lại nó cho đúng mục đích, hoặc đặt biến mới, đừng để hai biến cùng nghĩa.

**Điều kiện để việc tự host là đáng:** SLM phải nhanh hơn LLM API cho cùng nhiệm vụ. Một model 7B chạy trên máy yếu, thêm một chặng mạng, có thể chậm hơn `gemini-3.1-flash-lite`. Đo trước khi cam kết (§9 P1).

### 7.3. `RoleProfile` — định tuyến model theo tác vụ, và fallback

Khái niệm mới: mỗi vai trò có **danh sách provider theo thứ tự riêng**, thay vì dùng chung `llm_provider_order` toàn cục.

`credential` giữ nguyên ngữ nghĩa hiện tại (key người dùng, không fallback — §2.5) và **không** bị tái dụng cho việc này.

Chính sách fallback bắt buộc — đây là phần dễ làm sai nhất:

| Vai trò | Khi model chết thì rơi về |
| --- | --- |
| `controller` | Không có model và không có fallback; execution plan được tạo bằng code. |
| `symptom_group_router` | `registry.select_protocol` thuần rule |
| `fact_extractor` | Fallback nhiều provider như hiện nay |
| `synthesis` | `script_hint` deterministic (đã có ở §6.5) |
| `text_safety_signals`, `reducer`, `rule_engine`, `output_guard` | Không có fallback vì không có model |

Hệ quả cần test: **tắt hoàn toàn SLM, hệ thống phải vẫn chạy đúng** bằng router deterministic +
extractor provider hiện tại + renderer fallback; có thể kém tự nhiên hoặc route nhiều ca hơn về
`general`. Nếu tắt SLM làm hỏng safety/triage flow thì kiến trúc đã sai.

### 7.4. Ngân sách mỗi lượt

Hiện một lượt tốn tối đa **2 lời gọi chính** (extract + render). Controller deterministic không thêm
lời gọi. Router model là lời gọi thứ ba **chỉ ở đúng bốn trigger đóng liệt kê ở §3.1**, không chạy mọi
lượt.

`_AttemptBudget` đã có (`llm_max_total_attempts=6`, `llm_total_budget_seconds=45` — `src/config.py:71-72`) nhưng là ngân sách **cho một lời gọi `complete()`**, không phải cho cả lượt. Cần thêm ngân sách cấp-lượt, và cần đo p50/p95 trước/sau (§9 P0 và P4).

Cách giảm số lời gọi:

- `dialogue_act` đi cùng output của `fact_extractor`, không có classifier/controller call riêng;
- lượt mở dùng broad harvest rồi `registry.select_protocol`; router SLM chỉ chạy theo §3.1;
- `greeting` thuần có thể được guard deterministic xử lý mà không gọi extractor; `off_topic` không
  nên bỏ extractor chỉ dựa trên nhãn model chưa validate;
- cụm safety-critical dùng template tĩnh nên không tốn render call.

### 7.5. Structured output

`Provider` protocol (`src/providers/base.py:20`) và `provider_router.complete()` chưa có đường truyền `response_schema`, và mỗi nhà cung cấp làm một kiểu. Với kiến trúc nhiều tầng model, phân nhánh theo từng hãng còn tệ hơn.

- **Phương án A (khuyến nghị cho MVP):** giữ parser text hiện tại làm hợp đồng chung cho **mọi** provider kể cả `local_slm`, đầu tư vào validator backend. Rẻ, không phân nhánh hành vi, và validator dù sao vẫn phải viết.
- **Phương án B:** bật structured output riêng cho từng provider hỗ trợ, chấp nhận hai đường xử lý output song song.

Trong cả hai phương án, validator backend là bắt buộc; structured output chỉ giảm tỉ lệ lỗi, không thay thế được kiểm tra.

## 8. Linh hoạt mà vẫn khai phá đủ triệu chứng

Mục tiêu: hội thoại tự nhiên như nói chuyện với một điều dưỡng giỏi — theo mạch người bệnh đang kể,
không đọc checklist — **nhưng khi phiên đóng vẫn phải đủ dữ kiện để rule engine kết luận an toàn**.

### 8.1. Ba loại cứng, và loại nào được nới

Cảm giác “agent hỏi máy móc” đến từ ba nguồn khác nhau. Gộp chung sẽ dẫn tới nới lỏng nhầm chỗ.

**Loại 1 — cứng cố ý, KHÔNG nới.** `common_safety/rules.py`, `rule_engine.evaluate`, `escalation_lock`,
HITL, và ngưỡng độ phủ M0/M1. Đây là thứ khiến hệ thống audit được và là ràng buộc cứng trong
`CLAUDE.md`.

**Loại 2 — cứng ở cách diễn đạt. NỚI.** `_generate_question` chỉ đọc lại một câu do rule chọn: không
acknowledge thông tin vừa nhận, không markdown, không trả lời câu hỏi ngược, không có câu chuyển
hướng khi đổi protocol. Xử lý bằng `DialoguePolicy` + synthesis (§6), không đụng tầng an toàn.

**Loại 3 — cứng ở thứ tự hỏi. NỚI, nhưng bằng ranking tất định chứ không bằng model.**
`next_cluster` hiện là first-fit thuần vị trí (`stage_machine.py:106`): duyệt `clusters_for_stage`
theo thứ tự khai báo, trả về cụm đầu tiên còn thiếu. Người bệnh vừa kể về khó thở mà cụm khó thở
đứng thứ 7 trong danh sách thì vẫn phải trả lời 6 cụm khác trước — đây mới là nguồn chính của cảm
giác "nó không nghe mình nói".

Quyết định (đổi so với bản trước): **nới loại 3, bằng cách thay first-fit bằng một hàm xếp hạng
thuần code.** Cùng input cho ra cùng output, nên vẫn test được bằng fake LLM và transcript vẫn lặp
lại được. Điều **không** đổi: model vẫn không được chọn cụm hỏi.

### 8.2. Ba bất biến không được đánh đổi lấy sự tự nhiên

1. **Độ phủ:** phiên chỉ được đóng khi `mandatory_fields_covered` đúng, hoặc dừng vì `RED_FLAG` /
   `USER_CANNOT_CONTINUE` (`should_stop`, `stage_machine.py:229`). Linh hoạt chỉ được đổi *thứ tự* và
   *cách hỏi*, không bao giờ được bỏ bớt field M0/M1.
2. **Cụm an toàn không được hoãn.** Cụm chứa field safety-critical luôn đứng đầu bảng xếp hạng, bất kể
   người bệnh đang nói về chuyện gì.
3. **Không có gì bị hoãn mà biến mất.** Mọi cụm bị đẩy lùi phải vào hàng đợi nợ và được hỏi lại (§8.5).

### 8.3. Từ first-fit sang ranking tất định

Thay vòng lặp "trả về cụm đầu tiên còn thiếu" bằng: chấm điểm mọi cụm khả dụng, chọn cụm điểm cao
nhất, hoà điểm thì **giữ nguyên thứ tự khai báo** (để hành vi cũ là trường hợp đặc biệt của hành vi
mới, và diff của test cũ nhỏ nhất có thể).

Bốn thành phần điểm, tất cả đều tính được từ `answers` + `asked_ids` + `field_events` của lượt vừa
rồi — không có gì đến từ model:

| Thành phần | Ý nghĩa | Nguồn dữ liệu |
| --- | --- | --- |
| `safety` | Cụm chứa field safety-critical → điểm áp đảo | tier field + `common_safety` |
| `relevance` | Người bệnh **vừa nhắc tới** field của cụm này ở lượt trước | `field_events` của lượt vừa rồi |
| `yield` | Cụm này lấp được bao nhiêu field M0/M1 còn thiếu | `mandatory_fields_covered` |
| `debt` | Cụm đã bị hoãn bao nhiêu lượt → điểm tăng dần theo thời gian chờ | ledger §8.5 |

Trọng số là hằng số trong code, không phải tham số model. Đổi trọng số phải chạy lại eval.

Điều kiện lọc hiện có giữ nguyên và chạy **trước** khi chấm điểm: `cluster_is_skipped`,
`cluster_needs_answer`, ranh giới stage. Ranking chỉ sắp lại thứ tự trong tập cụm **vốn đã hợp lệ**,
không mở thêm cụm nào.

### 8.4. Follow-the-user: nguồn cảm giác "được lắng nghe"

Đây là phần `relevance` ở trên, và là thay đổi tạo khác biệt lớn nhất về trải nghiệm với chi phí kỹ
thuật thấp nhất.

Cơ chế thu hoạch cơ hội đã tồn tại — extractor vẫn nhặt field ngoài cụm đang hỏi (`opportunistic`,
`intake_agent.py:936` và `:1174`). Cái thiếu là **thứ tự hỏi chưa phản ứng lại theo nó**: hệ thống
nhặt được thông tin về khó thở nhưng câu tiếp theo vẫn quay về cụm thứ tự kế tiếp.

Quy tắc:

- Người bệnh tự nêu thông tin thuộc cụm X → **đóng nốt X trước**, rồi mới đi tiếp.
- Người bệnh nêu triệu chứng thuộc protocol khác → cân nhắc chuyển protocol (§3), kèm một câu chuyển
  hướng dễ hiểu, không đổi checklist im lặng.
- Người bệnh trả lời vượt trước nhiều cụm → những cụm đó biến mất khỏi hàng đợi, và **phải công nhận
  ngắn** là đã ghi nhận, nếu không họ sẽ tưởng mình nói vào khoảng không.

### 8.5. Coverage ledger + hàng đợi nợ

Linh hoạt không có sổ sách sẽ biến thành quên hỏi. Mỗi phiên giữ một ledger thuần code:

```text
coverage_ledger = {
  "mandatory_remaining": ["chief_complaint", "onset_at", ...],   # field M0/M1 chưa có căn cứ
  "deferred": {"CLUSTER_X": 3, "CLUSTER_Y": 1},                  # cụm -> số lượt đã bị hoãn
  "asked_but_unanswered": ["CLUSTER_Z"],                         # đã hỏi, người bệnh né/không biết
}
```

Ba quy tắc vận hành:

1. `deferred[cluster]` vượt ngưỡng (đề xuất 3) → cụm đó được cộng đủ điểm `debt` để chắc chắn thắng ở
   lượt kế tiếp. Đây là cơ chế chống bỏ sót, không phải chống hoãn.
2. Trước khi phiên đóng, nếu `mandatory_remaining` không rỗng thì **không được đóng** — kể cả khi đã
   hết ngân sách lượt. Ngân sách chỉ được cắt cụm tier O/H, đúng như `_cluster_is_optional_tier`
   (`stage_machine.py:85`) đang làm.
3. `asked_but_unanswered` khác `mandatory_remaining`: đã hỏi mà người bệnh không biết là một **kết
   quả hợp lệ** (`unknown`), không phải nợ. Hỏi lại lần thứ ba câu người ta vừa nói "không biết" là
   lỗi trải nghiệm nặng hơn là thiếu một field tier O.

Ledger phải log được ra để debug — "vì sao agent hỏi câu này" phải trả lời được bằng bảng điểm, không
phải bằng suy đoán.

### 8.6. Phễu khai phá: mở → sàng lọc gộp → khoan sâu → quét sót

Khai phá triệu chứng tốt không phải là hỏi nhiều câu, mà là hỏi đúng độ rộng ở đúng thời điểm:

1. **Mở** — chief complaint tự do, không presupposition. Không hỏi "đau ở vùng nào" khi chưa biết
   người ta có đau hay không. Một câu mở tốt thu được nhiều field hơn ba câu đóng.
2. **Sàng lọc gộp** — `ScreeningGroup` đã có sẵn (`models.py:37`) và đúng là công cụ cho việc này:
   một câu liệt kê nhiều dấu hiệu, phủ định gộp thì đóng cả nhóm. Đây là thứ kéo ca lành tính từ 36
   lượt xuống còn ít lượt. Giữ nguyên ràng buộc: câu sàng lọc ghép **tĩnh** từ `probe_hint`, không
   qua renderer — một nhóm chỉ được đóng khi người bệnh thật sự nhìn thấy đủ danh sách dấu hiệu.
3. **Khoan sâu** — chỉ nhóm dương tính/chưa rõ mới đi vào từng cụm chi tiết.
4. **Quét sót** — trước khi chốt, một câu mở cuối: "Còn triệu chứng hay điều gì khác khiến bạn lo
   không?". Đây là chỗ bắt được triệu chứng mà checklist không hỏi tới, và là câu rẻ nhất trong toàn
   bộ phiên xét theo giá trị lâm sàng thu được. Câu này **không** được bỏ khi hết ngân sách.

### 8.7. Ngân sách lượt: cắt theo tier, không cắt theo số đếm

Ngân sách hiện tại cắt theo `asked_count`. Với hội thoại linh hoạt, số lượt không còn tỉ lệ với lượng
thông tin thu được — người kể nhiều trong một lượt đáng được ít câu hỏi hơn.

Đổi tiêu chí dừng sang: dừng khi `mandatory_fields_covered` **và** đã chạy bước quét sót (§8.6 mục 4),
thay vì khi đủ N câu. Ngân sách số đếm giữ lại làm **trần an toàn** chống vòng lặp vô hạn, không phải
làm tiêu chí chính.

### 8.8. Cái gì KHÔNG được linh hoạt

Để tránh hiểu nhầm khi implement:

- Model vẫn **không** chọn cụm hỏi. Ranking là code.
- Câu sàng lọc gộp vẫn ghép tĩnh, không qua renderer (§8.6 mục 2).
- Thông điệp cấp cứu vẫn là template tĩnh đã duyệt.
- Không được "linh hoạt" bằng cách bỏ field M0/M1 vì thấy hội thoại đã dài.
- Không đổi trọng số ranking theo phiên/theo người dùng. Một hệ thống xếp hạng tự điều chỉnh là một
  hệ thống không reproduce được lỗi.

## 9. Thứ tự triển khai

### 9.0. Hai track, và quy tắc track nào chèn track nào

Kế hoạch này gồm **hai track có chủ trì khác nhau**, không phải một chuỗi tuyến tính. Bản trước đánh
số P0→P5 liên tục nên đọc như một chuỗi, trong khi phần phạm vi MVP lại ngụ ý thứ tự có thể đảo hoàn
toàn — người đọc không biết mình đang ở lộ trình nào. Mục này là chỗ duy nhất chốt việc đó.

| Track | Nội dung | Chủ trì |
| --- | --- | --- |
| **P** (P0–P5) | Kiến trúc, controller, extraction, trải nghiệm hội thoại, eval | Agent Lead |
| **PC** | Xây 4 protocol lâm sàng còn thiếu | Data Lead, cùng tài liệu CS |

**Quy tắc chèn:** `P0` luôn chạy trước mọi thứ ở cả hai track — nó là an toàn và baseline, không đánh
đổi được. Sau `P0`:

- Nếu **Demo V1 cuối Sprint 2 cần đủ 5 nhóm** → `PC` **chèn trước** `P1`–`P3`; phần kiến trúc lùi
  sang Sprint 3. Lý do ở §10: router và ranking chưa tạo thêm giá trị khi 4/5 đích đến chưa tồn tại.
- Nếu mục tiêu là **một nhóm chạy thật tốt** → chạy `P1`→`P5` như liệt kê, `PC` lùi lại, và ghi rõ
  trong demo rằng 4 nhóm còn lại đi qua `GENERIC_PROTOCOL`.

Đây là quyết định của PM, cần chốt trong buổi planning. **Không chốt thì mặc định trôi theo hướng thứ
hai** — không phải vì ai chọn nó, mà vì `P1` là thứ dễ bắt đầu hơn.

### P0 — Vá lỗ hổng an toàn và đo baseline (không phụ thuộc kiến trúc mới)

1. ✅ **[XONG 2026-08-17]** **Thiết kế lại rồi nối L0 `text_safety_signals` vào luồng chuẩn** — chạy trên text thô trước model,
   nhưng không biến substring match thành `EMERGENCY` trực tiếp (§2.1). Bổ sung polarity/subject/time
   guard, phân biệt `confirmed_positive` với `needs_confirmation`, và clinical review tập mẫu được
   phép short-circuit. Test hiện có chỉ kiểm positive/neutral, chưa đủ; bắt buộc thêm negation,
   historical và other-subject cases.
2. ✅ **[XONG 2026-08-17]** **Chạy `eval/scripts/run_eval.py` trên `data/golden_cases_v1.jsonl` (120 ca) để lấy baseline** — kết quả ở `eval/baselines/2026-08-17-p0-summary.md`. Chạy trên `deepseek-chat`, `--mode api` (server thật).
3. ✅ **[XONG 2026-08-17]** **Đo latency p50/p95 và số lời gọi mỗi lượt ở kiến trúc hiện tại.** Lượt: p50 3.98s / p95 5.72s; ca 2 lượt: p50 9.98s / p95 11.40s; 1.23–1.72 lời gọi/lượt. Theo vai trò: `fact_extractor` p50 3827ms, `synthesis` p50 1234ms.
4. ✅ **[XONG 2026-08-17]** Thêm regression transcript cho ví dụ "có sốt → không sốt → hỏi agent đang hỏi gì" — `tests/test_services/test_dod_transcript.py` (8 ca, LLM giả, phủ đủ §13 mục 1-6). Bản chạy với model thật ở `eval/baselines/2026-08-17-p3-synthesis-transcripts.md`.
5. ✅ **[XONG 2026-08-17]** Ghi lại provider/model thực tế phục vụ luồng UI, config và prompt hash — `eval/scripts/record_baseline.py`, kết quả `eval/baselines/2026-08-17-p0.json`.
6. ⛔ **[MỚI 2026-08-19 — chưa làm]** **Sửa thứ tự ưu tiên trong `should_stop`: `RED_FLAG` phải
   thắng `USER_CANNOT_CONTINUE`.** Docstring của hàm ghi *"Áp theo thứ tự: chốt đỏ > đủ căn cứ > hết
   ngân sách > người dùng không tiếp tục được"* nhưng code kiểm `user_can_continue` **đầu tiên**
   (`stage_machine.py:298-303`). Hệ quả: người bệnh vừa khai một dấu hiệu cấp cứu rồi nói "thôi khỏi"
   trong cùng lượt thì phiên đóng với `USER_CANNOT_CONTINUE` thay vì `RED_FLAG` — tức là **không
   escalate**, ngược `CLAUDE.md` nguyên tắc 4 và ngược bất biến §1 mục 3 ("không có đường nào để một
   lỗi làm mất red flag").

   Đây là P0 vì nó là lỗi an toàn trong code **đang chạy**, không phải một tính năng mới. Việc sửa
   nhỏ (đảo hai khối `if`) nhưng **bắt buộc kèm test** (§11 nhóm "Ý định người dùng"), vì đúng lượt
   đó là lượt hiếm nên không ca golden nào hiện chạm tới. Cũng phải sửa `advance` nếu nó tự suy
   `user_can_continue` ở chỗ khác.

   Lưu ý khi sửa: `USER_CANNOT_CONTINUE` vẫn phải thắng `SUFFICIENT_EVIDENCE` và `BUDGET_EXHAUSTED` —
   thứ tự đúng chính là thứ tự docstring đã ghi, chỉ là code chưa theo.

### PC — Protocol lâm sàng: 4 nhóm còn thiếu (track song song, chủ trì Data Lead)

Hạng mục **lớn nhất** trong toàn bộ tài liệu, và trước đây chỉ nằm ở §10 như một ghi chú. Nâng thành
phase thật vì quy mô của nó quyết định được cả roadmap (§9.0).

**Quy mô thực tế, đo trên protocol đã hoàn thiện:** `fever_protocol.py` là **696 dòng** và không phải
bảng dữ liệu — 7 stage, ~10 hàm skip-rule, `determine_route`, `conservatism_tier`,
`_is_dengue_context`, `budget_key`, `derive_duration`. Bốn protocol nữa là bốn lần chừng đó **logic
lâm sàng viết tay**.

**Phần được thừa hưởng, không phải viết lại:** `common_safety/rules.py` (443 dòng), `clusters.py`,
`fields.py`, `screening_groups.py` dùng chung cho mọi protocol — 4 nhóm mới có sẵn tầng an toàn.
`stage_machine`, `screening`, `batching`, `retraction` cũng đã trung lập với symptom group.

**Phần phải viết riêng từng nhóm:** field + tier (M0/M1/C/O/H), cụm câu hỏi, `ScreeningGroup`,
skip-rule, `determine_route`, ngưỡng budget, và luật triage riêng của nhóm.

Các bước:

1. Chốt nguồn lâm sàng cho từng nhóm trước khi code: `data/triage_daubung.csv`,
   `triage_daunguc.csv`, `triage_khotho.csv`, `triage_daudau.csv` là **nguyên liệu thô**, không phải
   protocol — phải qua tài liệu CS và review lâm sàng.
2. Làm **một** nhóm trọn vẹn trước (đề xuất Khó thở hoặc Đau ngực vì tỉ trọng red flag cao), rút kinh
   nghiệm, rồi mới làm ba nhóm còn lại song song.
3. Mỗi nhóm phải có đủ test như fever hiện có: extraction, red-flag engine, stage machine, skip-rule.
4. Bổ sung golden case cho nhóm mới vào `data/golden_cases_v1.jsonl` trước khi merge.

Đây **không phải việc engineering thuần**: phần lớn công là đọc tài liệu lâm sàng và quyết ngưỡng.
Lên kế hoạch sprint theo đúng bản chất đó, đừng ước lượng như một task code.

### P1 — Hạ tầng định tuyến theo vai trò

> **Cập nhật 2026-08-17 — P1 ĐÃ XONG (mục 1-3).** `provider_router.RoleProfile` + ba vai trò
> `fact_extractor` / `synthesis` / `symptom_group_router`; cấu hình qua `ROLE_ORDER_*` trong `.env`,
> để trống = kế thừa `llm_provider_order` ⇒ **mặc định không đổi hành vi gì**. `complete()` và
> `complete_stream()` nhận `role=`; `intake_agent` đã gắn `ROLE_FACT_EXTRACTOR` cho bước trích xuất
> và `ROLE_SYNTHESIS` cho bước diễn đạt câu hỏi. `LLMCredential` KHÔNG bị tái dụng cho việc này.
>
> `role_usage_snapshot()` gom p50/p95 + số lời gọi + provider theo từng vai trò, và `run_eval.py` đã
> in ra bảng "Per-Role LLM Usage" (chỉ có số ở `--mode direct`; xem cảnh báo ở P0.2). Test:
> `tests/test_services/test_role_profiles.py` (8 ca).
>
> **Còn nợ mục 4** (đo thật trên golden case) - cần API key và chi phí model thật, không chạy được ở
> đây. Hạ tầng đã sẵn: chạy eval là ra bảng.

1. `RoleProfile` trong `provider_router`: mỗi vai trò một danh sách provider riêng (§7.3). **Đây là
   toàn bộ nội dung bắt buộc của P1** — thuần code, không cần máy GPU, không cần model mới.
2. Mọi profile trỏ về provider API đang dùng. `RoleProfile` có giá trị ngay cả khi không bao giờ có
   SLM: nó tách được cấu hình model của extractor khỏi renderer.
3. **Không** thêm provider `local_slm` ở phase này — việc đó nằm sau điều kiện tiên quyết ở §7.2.
4. Đo latency/chi phí theo từng vai trò trên tập golden case. Đây chính là dữ liệu để trả lời điều
   kiện §7.2, và cũng là thứ P4 cần. Nếu số liệu cho thấy provider API đã đủ rẻ và đủ nhanh thì hướng
   tự host đóng lại tại đây — đó là một kết quả hợp lệ, không phải thất bại.

### P2 — Deterministic controller + `symptom_group_router` phụ trợ

> **Cảnh báo churn.** `session.submit_message` + `stage_machine.advance` + `screening.next_probe` +
> `batching.next_batch` **hiện đã là** một controller tất định. Nếu P2 chỉ gói chúng lại dưới một cái
> tên mới thì đó là một sprint đổi tên, không phải một thay đổi hành vi.

`ExecutionPlan` chỉ đáng làm nếu nó giao được **đúng ba thứ mà code hiện tại chưa có**. Đây là tiêu
chí nghiệm thu của P2 — không đạt cả ba thì cắt phase này:

1. **Một chỗ tường minh để quyết “lượt này có gọi extractor không”.** Hiện quyết định đó nằm rải rác
   và implicit; đó là lý do không tối ưu được chi phí theo `dialogue_act` (§7.4).
2. **Một chỗ để gắn `coverage_ledger`** (§8.5) — nếu không có, ledger sẽ bị nhét vào `session` và trộn
   lẫn với trạng thái phiên.
3. **Fail closed khi session state không hợp lệ** — rơi về đường extraction + handoff, không bao giờ
   gọi model để “đoán plan”.

> **Cập nhật 2026-08-17 — P2 mục 1-3 ĐÃ XONG, mục 4-5 CHƯA.** Đối chiếu ba tiêu chí nghiệm thu ở trên:
>
> | Tiêu chí | Kết quả |
> | --- | --- |
> | 1. chỗ tường minh quyết "có gọi extractor không" | ✅ `controller.build_execution_plan` |
> | 2. chỗ gắn `coverage_ledger` | ⚠️ **đã giải quyết TRƯỚC ở P3.1 theo cách khác** - ledger là `session.ledger`, một `CoverageLedger` riêng chứ không phải vài trường rời rạc. Dời vào `ExecutionPlan` lúc này là churn thuần. |
> | 3. fail closed khi state không hợp lệ | ✅ `_hand_off` |
>
> `controller.py` cố ý HẸP, đúng theo cảnh báo churn ở trên: nó KHÔNG gói `stage_machine`/`screening`/
> `batching` lại dưới một tên mới, chỉ nhận hai việc code cũ chưa có chỗ nào làm.
>
> - **Bỏ extractor cho lời chào thuần** (§7.4). Danh sách lời chào là danh sách ĐÓNG - tiêu chí là
>   "không thể chứa dữ kiện lâm sàng", không phải "trông giống lời chào"; và lời chào có kèm tín hiệu
>   L0 thì vẫn gọi extractor. Đo trên model thật: lượt chào từ **~7s + 2 lời gọi → 16ms + 0 lời gọi**.
> - **Fail closed**: trước đây `submit_message` lặng lẽ `return session` khi không còn cụm - người
>   bệnh gõ tin nhắn và KHÔNG nhận được gì. Giờ chuyển sang đường bàn giao với thông điệp tĩnh,
>   `stop_reason=INVALID_STATE:*`, và test khẳng định **0 lời gọi model** trên nhánh đó.
> - **Cổng router** `should_consult_group_router`: đúng bốn trigger đóng của §3.1, có bộ đếm
>   `router_gate_stats()`. Chưa có model phía sau - `registry.select_protocol` thuần luật vẫn quyết.
>   Đo trên transcript 4 lượt thật: `{turns: 3, consulted: 1}`, lượt trả lời bình thường = 0.
>
> Test: `tests/test_services/test_controller.py` (25 ca, gồm §11 an toàn mục 5 và mục 7).
>
> **Cập nhật 2026-08-17 — P2 mục 4-5 ĐÃ XONG.** `symptom_protocol/reducer.py`: `FieldEvent`
> (`operation`/`certainty`/`evidence_span`/`source`), `AuditEvent`, và `reduce()` là chỗ DUY NHẤT gộp
> trạng thái - `run_turn` lẫn `run_open_turn` đều đi qua nó, không còn hai đường merge khác nhau.
>
> - **`operation: "unset"`** (§4.1) là năng lực mới: "con số 39 đó là nhiệt độ phòng" KHÔNG phủ định
>   `fever_reported` nên trước đây không có field cha nào để xoá dây chuyền, và `temp_c=39` đi thẳng
>   vào phiếu bàn giao. `unset` cũng bắt buộc có bằng chứng như `set false`.
> - **Snapshot vẫn đúng 3 giá trị `TriState`** (§4.2): reducer quy `unset` về `"unknown"` và ghi
>   `AuditEvent` để phân biệt "chưa bao giờ hỏi" với "đã khai rồi rút lại".
> - **`certainty` do CODE chấm** (`reducer.certainty_of`), không lấy nhãn model tự gán: nhãn đó không
>   tốn gì của model nhưng lại là thứ quyết định hệ thống có được xoá hồ sơ hay không.
> - **`confirm_before_retract` thôi là lời hứa suông** (§5 quy tắc 5). Docstring `protocol.py:123` ghi
>   "phải XIN XÁC NHẬN trước khi xoá dây chuyền" nhưng `apply_retraction` chưa bao giờ đọc tập đó.
>   Giờ đính chính đáng ngờ bị GIỮ LẠI (hồ sơ đứng yên, `session` hỏi một câu tĩnh, hỏi đúng 1 lần/field).
>   "Đáng ngờ" = đoạn trích nhắc TÊN BỆNH (dùng chung `output_guard.DISEASE_NAMES` — bug C2), hoặc lật
>   ngược một lời khai `"true"` mà không trích được câu nào.
> - **`skip_existing` không có trong luồng chuẩn** — nó chỉ tồn tại ở agent cũ (`agents/intake_agent.py:252`).
>
> Cổng xác nhận ban đầu bắt QUÁ RỘNG (chỉ kiểm `certainty`) và làm ca lành tính H1 dài thêm một lượt:
> model trả JSON phẳng thì MỌI câu "không" đều là `inferred`, kể cả lần trả lời ĐẦU TIÊN — mà trả lời
> lần đầu thì không có gì để rút lại. Đây là lý do có điều kiện `before == "true"`.
>
> Test: `tests/test_services/test_reducer.py` (31 ca) + `test_retraction_events.py` (7 ca, chạy qua
> `session.submit_message`).

Các bước:

1. Pydantic models: `DialogueAct`, `FieldEvent`, `ExtractionResult`, `ExecutionPlan`, `ResponsePlan`.
2. Controller code tạo `ExecutionPlan` từ phase/protocol/current cluster; không nhận plan từ model.
   Giữ `stage_machine`/`screening`/`batching` nguyên vẹn bên dưới — controller **gọi** chúng, không
   thay thế chúng.
3. Thêm router SLM theo đúng bốn trigger đóng ở §3.1, fallback về `general`/protocol hiện tại theo
   policy tất định (§7.3), kèm test “tắt SLM, hệ thống vẫn chạy đúng” và log tỉ lệ lượt có gọi router.
4. ✅ **[XONG 2026-08-17]** Chuyển extractor sang event/delta có `operation`, `certainty`, `evidence_span`; bỏ tư duy `skip_existing` khỏi luồng chính.
5. ✅ **[XONG 2026-08-17]** Mở rộng reducer/retraction cho `unset`, dependency cleanup, pending confirmation — **giữ snapshot ở đúng 3 giá trị TriState** (§4.2).

### P3 — Trải nghiệm hội thoại: linh hoạt + khai phá đủ

> **Cập nhật 2026-08-17 — P3 mục 1-4 ĐÃ XONG.**
>
> - `coverage.CoverageLedger` (`src/services/symptom_protocol/coverage.py`): chỉ giữ ĐÚNG bộ đếm
>   hoãn; `mandatory_remaining` tính lại từ `answers`, `asked_but_unanswered` lấy từ
>   `session.unresolved_cluster_ids` - không tạo nguồn sự thật thứ hai. Ghi ra log qua sự kiện
>   `route_decided` mỗi lượt.
> - `ranking.py`: 5 thành phần điểm (`safety` > `overdue` > `relevance` > `yield` > `debt`), trọng số
>   là hằng số, hoà điểm giữ thứ tự khai báo ⇒ **first-fit cũ là trường hợp đặc biệt**.
>   `stage_machine.next_cluster` giữ nguyên chữ ký, thêm `context=`; `select_cluster` trả kèm
>   `deferred_ids`.
>   - `yield` là NHỊ PHÂN (có/không lấp field M0/M1), không đếm số field: đếm thì cả bảng câu hỏi bị
>     xáo lại để đổi lấy một lợi ích không đo được.
>   - `safety` suy ra từ field của stage quét đỏ, KHÔNG dùng `protocol.safety_signal_fields` (tập đó
>     trộn cả field "hay được nói sớm" như nhiệt độ).
> - Follow-the-user: `run_turn` và `run_open_turn` dựng `RankingContext.recent_fields` từ chính kết
>   quả trích xuất của lượt đó.
> - Quét sót (§8.6 mục 4): `session.CATCH_ALL_QUESTION` - câu tĩnh trước khi chốt, không bị cắt bởi
>   ngân sách, không hỏi lần hai, bỏ qua khi dừng vì `RED_FLAG`. Câu trả lời được đọc bằng một cụm
>   tổng hợp dựng tại chỗ (`_catch_all_cluster`), KHÔNG khai vào `protocol.clusters`.
> - `should_stop`: hết ngân sách không được đóng phiên khi từ stage hiện tại trở đi còn cụm CHƯA HỎI
>   mang field M0/M1. Điều kiện tính trên CỤM CHƯA HỎI chứ không trên `mandatory_fields_covered` -
>   một field bắt buộc có thể vĩnh viễn `unknown` vì người bệnh không trả lời được, và "chưa đủ độ
>   phủ" không được biến thành "phiên không bao giờ đóng".
>
> Đo được: ca lành tính H1 đi từ 20 lên **21 lượt**, và +1 đó là bước quét sót. Luật dừng theo độ phủ
> KHÔNG tốn thêm lượt nào ở ca này. Test: `tests/test_services/test_coverage_and_ranking.py` (45 ca,
> gồm property test 25 seed cho bất biến §8.2).
>
> **Cập nhật 2026-08-17 — P3 mục 5-7 ĐÃ XONG, mục 8 bị chặn bởi §7.2.**
>
> - `dialogue.py`: `DialogueAct` (8 nhãn của §4.1) + `DIALOGUE_POLICY` dạng **BẢNG**, phủ đủ 8/8
>   hàng, có test duyệt toàn bảng. `dialogue_act` suy ra từ `answer_quality` extractor ĐÃ trả về ⇒
>   **không tốn thêm lời gọi model nào**. `ResponsePlan` là hợp đồng đóng giữa policy và renderer.
> - `output_guard.py`: 5 kiểm tra của §6.5 + đếm vi phạm theo loại cho metric §12. Fail ⇒ rơi về
>   `script_hint`. Ghi rõ GIỚI HẠN đã biết thay vì giấu: không có cách tất định nào khẳng định "câu
>   này không hỏi gì ngoài `next_cluster`" chỉ bằng văn bản.
> - Markdown (§6.4): hai đoạn tách nhau, gạch đầu dòng khi nhiều ý, **cấm in đậm/nghiêng/bảng/tiêu
>   đề** - vì `/chat/stream` cần markdown hợp lệ theo TỪNG MẨU. Renderer streaming giờ **gom trọn rồi
>   mới phát**: guard phải chạy trước khi người bệnh đọc được chữ nào, và cái giá đã đo được là p50
>   1.2s của bước diễn đạt.
>
> **Ba lỗi chỉ lộ ra khi chạy model thật** (`deepseek-chat`), đã vá và có test:
> 1. tiền tố hướng dẫn ngôi thứ ba bị model chép nguyên văn ra tin nhắn ⇒ tách `acknowledge`
>    (dữ liệu) khỏi `acknowledge_instruction` (hướng dẫn);
> 2. trần dấu hỏi đếm theo CỤM thay vì theo FIELD ⇒ guard chặn nhầm chính câu hỏi chuẩn của cụm gộp;
> 3. đính chính làm đổi protocol bị gán nhãn `new_symptom` ⇒ `correction` nay thắng `new_symptom`,
>    và `label_protocol` cho phép công nhận dữ kiện mà protocol MỚI không khai (`fever_reported`
>    không tồn tại trong `general`).
>
> **Tỉ lệ bị `output_guard` chặn: 31% → 7.7% → 0%** (13 lượt diễn đạt, model thật). Transcript cho
> reviewer chấm: `eval/baselines/2026-08-17-p3-synthesis-transcripts.md`.
>
> **Mục 8 (hạ synthesis xuống SLM) KHÔNG làm** - §7.2 chưa đủ điều kiện tiên quyết, và số đo P0.3
> cho thấy lãi tối đa ~1.2s/lượt. `RoleProfile` đã sẵn nên khi có SLM chỉ cần đổi `ROLE_ORDER_SYNTHESIS`.

Đây là phần trả lời trực tiếp yêu cầu sản phẩm ở §1 mục 5. Làm theo thứ tự này vì mục 1–2 là thứ
người dùng cảm nhận ngay, còn mục 3 là thứ giữ cho sự linh hoạt không biến thành bỏ sót.

1. **`coverage_ledger` + hàng đợi nợ** (§8.5) — làm **trước** ranking. Có sổ sách rồi mới được phép
   hoãn câu hỏi; làm ngược lại là mở đường cho bỏ sót âm thầm.
2. **Ranking tất định thay first-fit** trong `next_cluster` (§8.3). Hoà điểm giữ nguyên thứ tự khai
   báo để test hiện có không vỡ hàng loạt.
3. **Follow-the-user** (§8.4): nối `field_events` của lượt vừa rồi vào thành phần `relevance`. Cơ chế
   thu hoạch cơ hội đã có sẵn, chỉ thiếu phần thứ tự phản ứng theo nó.
4. **Bước quét sót trước khi chốt** (§8.6 mục 4) và đổi tiêu chí dừng sang độ phủ thay vì số đếm
   (§8.7).
5. Tách `DialoguePolicy` tạo `ResponsePlan` khỏi `_generate_question`; policy cho
   `asks_clarification`, `cannot_answer`, `correction`, `partial_answer`, protocol switch.
6. Markdown/xuống dòng/gạch đầu dòng theo §6.4, an toàn với streaming.
7. `output_guard` + fallback deterministic (§6.5).
8. Thử hạ synthesis xuống SLM và đo bằng reviewer score — chỉ giữ nếu không tụt chất lượng.
9. ⛔ **[MỚI 2026-08-19]** **Ý định người dùng làm đầu vào của stop policy.** `user_can_continue` đã
   có sẵn trong chữ ký `should_stop` (`stage_machine.py:293`) nhưng **chưa ai suy nó ra từ tin nhắn**
   — nghĩa là "tóm tắt cho tôi đi" hoặc "tôi không muốn trả lời nữa" hiện không có đường nào tác động
   vào việc dừng phiên. Đây là gap thật duy nhất mà toàn bộ §23–36 của kế hoạch V2 tìm ra.

   Làm theo bốn ràng buộc, không nhiều hơn:

   - **Classifier tất định trước, model sau.** Danh sách từ khoá/mẫu câu tiếng Việt là sàn; chỉ khi
     sàn không quyết được mới hỏi model. Đây là cùng mô hình với `registry.select_protocol` +
     `symptom_group_router` (§3), không phải một cơ chế mới.
   - **Intent chỉ được set `user_can_continue=False`.** Nó không được chọn cụm, không được đổi
     protocol, không được hạ escalation. Một hướng, một tác dụng.
   - **Không bao giờ được vượt qua nhánh red flag** — phụ thuộc P0.6 ở trên. Làm P3.9 trước khi sửa
     P0.6 là mở rộng đúng cái lỗ đang có.
   - **Dừng vì intent phải đánh dấu phiếu là chưa đầy đủ**: `missing_information` phải liệt kê các
     field M0/M1 còn `unset`, để downstream không đọc một phiên bỏ dở thành một ca lành tính. Đây là
     lý do §16 quan tâm tới trường đó.

   **KHÔNG làm:** một "Stop Agent" bằng LLM nhận JSON và trả `CONTINUE`/`SUMMARIZE` như V2 §35 đề
   xuất. Xem §15 mục 1.

### PC+ — Multi-protocol đồng thời (chỉ có nghĩa sau khi PC xong)

`registry.select_protocol` trả **một** tên protocol cho một phiên. Ca thật "đau bụng kèm sốt 39" phải
chọn một trong hai. Kế hoạch V2 §6 nêu đúng vấn đề (`primary` + `secondary[]`), nhưng chưa trả lời
được các câu khó — và chúng phải được trả lời **trước khi viết dòng code nào**:

1. Field trùng tên khác nghĩa giữa hai protocol merge thế nào?
2. Tier / budget / luật triage của protocol nào thắng khi mâu thuẫn?
3. Đổi `primary` giữa phiên thì các cụm đã hỏi map sang protocol mới ra sao?
4. **`CoverageLedger.reset()` hiện xoá sạch nợ hoãn khi đổi protocol** vì mã cụm dùng chung giữa các
   protocol (`coverage.py:80-86`). Multi-protocol đồng thời phá giả định này — hoặc phải namespace mã
   cụm theo protocol, hoặc phải bỏ `reset()`. Đây là điều kiện kỹ thuật mà cả V2 lẫn hai bản đánh giá
   đều không nêu, và nó là thứ tốn công nhất trong bốn câu.

**Xếp sau `PC` chứ không song song:** merge hai protocol chỉ có nghĩa khi có hơn một protocol thật để
merge. Hiện `GENERIC_PROTOCOL` là cái duy nhất mà `FEVER_PROTOCOL` có thể ghép cùng, và đó cũng chính
là fallback — không có gì để giải quyết.

### P4 — Eval theo từng vai trò

> **Cập nhật 2026-08-17 — mục 1, 2, 5 ĐÃ XONG; mục 3, 4 CÒN NỢ.**
>
> - Mục 1-2: `test_reducer.py` (31 ca) + `test_retraction_events.py` (7 ca) + `test_flags.py` (11 ca),
>   cộng bộ có sẵn `test_controller.py`, `test_coverage_and_ranking.py`, `test_dialogue_and_output_guard.py`,
>   `test_dod_transcript.py`. Toàn bộ chạy bằng LLM giả. Tổng: **590 test xanh**.
> - Mục 5: `src/services/symptom_protocol/flags.py` + 4 biến `AGENT_*_ENABLED` trong `.env.example`.
>   **BỐN công tắc riêng, không phải một cờ "flow cũ"** — một cờ tổng thì tắt cả những cơ chế đang
>   chạy đúng nên không ai dám bật, và một đường quay lui không ai dám dùng thì không phải đường quay
>   lui. Mỗi công tắc rơi về một nhánh ĐÃ CÓ SẴN (ranking→first-fit, synthesis→`script_hint`,
>   xác nhận đính chính→áp ngay, `unset`→bỏ qua), không mở nhánh code thứ hai.
>   **KHÔNG có công tắc nào cho tầng an toàn** (§8.1 loại 1) — `test_no_switch_can_turn_off_a_safety_layer`
>   là hợp đồng: thêm một công tắc cho tầng an toàn sẽ làm bài đó đỏ.
> - **Còn nợ mục 3-4:** metric §12 về TRẢI NGHIỆM (`user_led_ratio`, `repeat_question_rate`,
>   `deferral_depth`, `catch_all_yield`, `mandatory_coverage_at_close`) chưa có chỗ nào tính ra số.
>   Dữ liệu thô đã có trong `stage_log` + `CoverageLedger.snapshot`; việc còn lại là một script đọc log
>   và một lần chạy model thật để có mẫu số.

1. ✅ **[XONG]** Unit test reducer, evidence validator, dependency cleanup, contradiction resolution.
2. ✅ **[XONG]** Transcript test end-to-end với fake LLM cho toàn bộ tầng deterministic.
3. Metric **tách theo trách nhiệm**, không gộp một con số: controller (branch/transition coverage),
   router (group accuracy), extractor (field F1), synthesis (reviewer score).
4. Dashboard/log: parse failure, invalid field, correction, protocol switch, red-flag short-circuit, fallback theo từng vai trò, latency/cost mỗi lượt.
5. ✅ **[XONG 2026-08-17]** Feature flag để quay lại flow cũ.

### P5 — Dọn kiến trúc

1. **Quyết số phận `src/tool/catalog/` + `triage_pipeline.py`** (§2.2): tái sử dụng phần registry/
   policy/audit trong controller chuẩn, hoặc deprecate pipeline legacy. Không để hai runtime path cùng
   có vẻ authoritative. Không xoá trước khi kiểm tra toàn bộ caller và migration endpoint.
2. ✅ **[XONG 2026-08-17]** Dời `_parse_json_object` ra khỏi `src/services/agents/intake_agent.py` — nay là
   `src/services/infra/json_output.parse_json_object`. Luồng chuẩn không còn import ngược vào agent cũ,
   nên bước 3-4 dưới đây chỉ còn là xoá file chứ không phải gỡ một sợi dây. Agent cũ giữ một bí danh
   `_parse_json_object = parse_json_object` để không phải sửa module sắp bị khai tử.
3. Quyết số phận `routers/fever_intake.py` + `sessions/fever_session.py` (đang mount tại `src/main.py:57`).
4. Chuyển mọi endpoint/UI còn lại sang `symptom_protocol.session.SessionStore`.

## 10. Phạm vi MVP: vì sao 4 protocol còn thiếu quyết định cả roadmap

Nội dung công việc nằm ở **track PC** (§9); mục này chỉ giải thích vì sao nó được ưu tiên như vậy.

`CLAUDE.md` chốt 5 nhóm (Sốt, Đau bụng, Đau ngực, Khó thở, Đau đầu/Chấn thương đầu nhẹ). Repo hiện
chỉ có `FEVER_PROTOCOL` + `GENERIC_PROTOCOL` (`registry.py:22`).

Ba hệ quả, xếp theo mức độ nghiêm trọng:

1. **`symptom_group_router` gần như vô nghĩa.** Router chọn giữa 5 nhóm nhưng 4 đích đến chưa tồn tại
   — mọi ca không phải sốt đều rơi về `GENERIC_PROTOCOL` dù router có chính xác đến đâu. Đây là lý do
   trực tiếp khiến PC cấp thiết hơn việc thêm router model.
2. **Ranking và follow-the-user (§8) mất phần lớn tác dụng.** Cả hai sắp xếp *trong* tập cụm của
   protocol đang gắn. `GENERIC_PROTOCOL` (210 dòng, so với fever 696 dòng) có ít cụm hơn hẳn, nên
   không gian để "hỏi theo mạch người bệnh" cũng hẹp hơn hẳn.
3. **Độ phủ triệu chứng của MVP chỉ đạt 1/5** — điều mà một demo khó che được nếu người xem thử một
   ca đau ngực.

Quyết định roadmap tương ứng nằm ở §9.0 và là việc của PM, không phải của kỹ thuật.

## 11. Bộ test bắt buộc

### Đính chính/rút lời

1. “Tôi bị sốt” → “À nhầm, tôi không sốt”.
2. “Tôi sốt 39 độ” → “39 là nhiệt độ phòng, tôi không sốt”.
3. “Không sốt xuất huyết” không được map thành `fever_reported=false`.
4. “Tôi không sốt” → “À có, vừa đo 39.2 độ ở nách”.
5. “Có khó thở” → “Ý tôi là hơi mệt chứ thở bình thường”.
6. Một câu sửa nhiều field: “Không phải bé gái 2 tuổi, là bé trai 20 tháng”.

### Phủ định và mơ hồ

1. “Không” trả lời câu gộp phải chỉ phủ định đúng phạm vi cụm.
2. “Không biết”, “quên rồi”, “chắc không”, “có lẽ có” không bị ép thành false/true chắc chắn.
3. “Không ho nhưng khó thở” phải tách đúng hai field.
4. “Không còn sốt” phải phân biệt đã từng sốt với hiện tại không sốt nếu schema có thời gian.
5. Double negation và cách nói khẩu ngữ/không dấu/typo tiếng Việt.

### Hội thoại

1. “Bạn đang hỏi gì vậy?” → giải thích mục đích rồi hỏi lại một ý.
2. Người dùng trả lời vượt trước nhiều field → không hỏi lại.
3. Người dùng đổi chủ thể từ “tôi” sang “con tôi” → yêu cầu xác nhận chủ thể, không merge hai hồ sơ.
4. Người dùng chỉ chào → guard deterministic có thể bỏ `fact_extractor`. Người dùng hỏi meta → có
   thể vẫn gọi extractor để nhận `asks_clarification`, nhưng không được đánh dấu cụm lâm sàng hoàn
   tất hay merge fact không có bằng chứng.
5. Sau khi phủ định sốt, câu tiếp theo hỏi chief complaint mở, không mặc định vị trí đau/khó chịu.

### Linh hoạt và độ phủ (§8)

1. **Property test — bất biến quan trọng nhất của §8:** với mọi hoán vị thứ tự trả lời sinh ngẫu
   nhiên, khi phiên đóng bình thường thì `mandatory_fields_covered` phải `True`. Linh hoạt tới đâu
   cũng không được làm mất field M0/M1.
2. Ranking tất định: cùng `answers` + `asked_ids` + `field_events` phải luôn cho ra cùng một cụm.
   Chạy hai lần, so bằng nhau.
3. Hoà điểm phải rơi về đúng thứ tự khai báo — tức là hành vi first-fit cũ là trường hợp đặc biệt.
4. Người bệnh tự nêu triệu chứng thuộc cụm X → câu hỏi kế tiếp thuộc X, không phải cụm vị trí kế tiếp.
5. Cụm bị hoãn quá ngưỡng phải được hỏi lại, không biến mất khỏi hàng đợi.
6. Cụm chứa field safety-critical không bao giờ bị hoãn, kể cả khi người bệnh đang nói chuyện khác.
7. Hết ngân sách lượt mà `mandatory_remaining` chưa rỗng → **không được đóng phiên**; chỉ cụm tier
   O/H được cắt.
8. Người bệnh trả lời "không biết" cho một cụm → không bị hỏi lại cụm đó lần thứ ba.
9. Bước quét sót trước khi chốt luôn chạy, kể cả khi ngân sách đã cạn.

### Ý định người dùng và dừng phiên (§9 P0.6, P3.9)

1. **Ca chặn của P0.6:** cùng một lượt vừa khai dấu hiệu cấp cứu vừa nói "thôi tôi không trả lời nữa"
   → `should_stop` phải trả `RED_FLAG`, **không** `USER_CANNOT_CONTINUE`. Đây là bài test giữ cho lỗi
   đã sửa không quay lại.
2. Thứ tự còn lại vẫn đúng như docstring: `USER_CANNOT_CONTINUE` thắng `SUFFICIENT_EVIDENCE` và
   `BUDGET_EXHAUSTED` khi không có tín hiệu đỏ.
3. "Tóm tắt cho tôi đi" / "thôi vậy đủ rồi" → dừng, và phiếu bàn giao có `missing_information` liệt kê
   field M0/M1 còn `unset`.
4. "Không còn triệu chứng nào khác" **không** phải lệnh dừng tuyệt đối: nếu còn cụm CHƯA HỎI mang
   field M0/M1 thì vẫn phải hỏi tiếp (đây là §8.2 mục 1, không phải ngoại lệ mới).
5. Câu chửi tục hoặc lạc đề đơn lẻ không được suy thành `user_can_continue=False`.
6. Intent dừng không được hạ một escalation đã khoá (`escalation_lock`, `session.py:94`).

### Red flag hai nhánh và quyền của điều dưỡng (§15.1, §15.4)

1. Model bắt được một red flag mà rule bỏ sót → vẫn escalate, và mục đó xuất hiện trong
   `red_flag_agreement.model_only`.
2. **Model KHÔNG tắt được red flag mà rule đã bật** — kể cả khi model khẳng định ngược lại.
3. Nhánh model timeout/JSON hỏng → hai nhánh cũ vẫn chạy đủ, `model_branch_status="failed"` vào log,
   không mất phát hiện nào.
4. `red_flag_agreement` không có đường nào tác động vào `proposed_priority` — kiểm bằng cách đổi nội
   dung nó và khẳng định mức ưu tiên không đổi.
5. Điều dưỡng hạ một red flag → `generated_value` vẫn giữ giá trị gốc, audit ghi đủ `edited_by`,
   `edited_at`, `reason`.
6. Điều dưỡng **không** hạ được `escalation_lock` trong phiên đang chạy bằng đường API của bước duyệt
   — hai cơ chế phải tách rời (§15.4).
7. Ca đã hiển thị `EMERGENCY_MESSAGE` cho bệnh nhân → điều dưỡng hạ cờ vẫn không xoá được sự kiện đã
   hiển thị; log giữ nguyên.

### Batch câu hỏi và field bị bỏ qua (§15.8)

1. Người bệnh trả lời 3/6 ý trong một batch → **field M0/M1 bị bỏ qua thành `unknown`**, không phải
   `false`; chỉ field tier O/H mới được suy `false`.
2. Field M0/M1 bị bỏ qua được hỏi lại **đúng một lần**, không lặp vòng.
3. Phủ định gộp: một chữ "không" chỉ đóng đúng các field trong danh sách vừa đọc lên, không lan sang
   nhóm khác (`pending_probe` turn-scoping).
4. Batch không vượt trần ý mỗi lượt.

### Dừng vì bất hợp tác (§15.7)

1. Một lượt lạc đề đơn lẻ (kể cả có chửi tục) **không** dừng phiên.
2. 2–3 lượt liên tiếp lạc đề + không thu được field mới → agent hỏi một lần, chưa dừng.
3. Vẫn không hợp tác sau câu hỏi đó → `USER_UNCOOPERATIVE`, phiếu đánh dấu incomplete.
4. Ba lý do dừng (`USER_CANNOT_CONTINUE`, `USER_UNCOOPERATIVE`, `SUFFICIENT_EVIDENCE`) tạo ra ba phiếu
   **phân biệt được với nhau** — không thu về cùng một hình dạng.

### Memory (§15.9)

1. `conversation_id` trùng nhau khi hai phiên mở cùng một giây → không đụng khoá (không dùng timestamp).
2. Restart giữa phiên → phiên đang dở khôi phục được từ event log.
3. Nén context dài **không** ghi đè snapshot; snapshot và bản tóm tắt bất đồng thì snapshot thắng.
4. **`previous fever = true` của phiên trước không nạp thành `current fever = true`** — snapshot phiên
   mới bắt đầu từ `NULL`. Đây là bất biến số một của M3.
5. Không có đường nào đọc được hồ sơ của `user_id` khác.

### An toàn và kiến trúc model workers

1. Red flag đã được xác nhận dương tính trong lượt mở hoặc giữa hội thoại phải short-circuit ngay.
2. **JSON lỗi/timeout của model không được làm mất tín hiệu red flag trên text thô**; tín hiệu rõ đã
   duyệt phải short-circuit, tín hiệu mơ hồ phải đi vào đường xác nhận an toàn.
3. Câu phủ định như “không co giật/không khó thở nặng/không tím môi” không được short-circuit chỉ vì
   keyword matcher khớp substring.
4. **Tắt hoàn toàn SLM: hệ thống vẫn chạy đúng**, chỉ kém tự nhiên hoặc route thêm ca về `general`
   (§7.3).
5. Controller luôn tạo plan hợp lệ bằng code; state lạ/thiếu phải fail closed về đường extraction +
   handoff, không gọi model để “đoán plan”.
6. `symptom_group_router` chọn sai nhóm không được làm mất common-safety red flag.
7. **Router model KHÔNG được gọi ngoài bốn trigger ở §3.1.** Test bằng cách đếm số lời gọi trên một
   transcript nhiều lượt: lượt trả lời bình thường trong cùng protocol phải là 0 lời gọi router. Đây
   là chốt chặn chống việc "chỉ gọi khi cần" âm thầm trôi thành "gọi mọi lượt".
8. Renderer không được nêu chẩn đoán hay tự thêm hướng điều trị.
9. Một đính chính không được tự hạ escalation đã khoá nếu chưa qua policy xác nhận an toàn/HITL.

## 12. Metric và acceptance gate

Đo tách theo vai trò, không gộp một con số:

- **controller**: branch/transition coverage, invalid-state handling và execution-plan determinism
  (unit/property test, không phải model accuracy);
- **symptom_group_router**: group accuracy, tỉ lệ bất đồng với `registry.select_protocol`;
- **fact_extractor**: field-level precision/recall/F1, negation accuracy, correction/retraction accuracy, hallucinated-field rate;
- **reducer/rule engine**: contradiction resolution accuracy, tỉ lệ hỏi lại field đã biết;
- **synthesis**: reviewer score, tỉ lệ bị `output_guard` chặn;
- **trải nghiệm + độ phủ (§8)** — hai nhóm này phải đọc **cùng nhau**, vì cải thiện một cái bằng cách
  hy sinh cái kia là hỏng:
  - `mandatory_coverage_at_close`: tỉ lệ phiên đóng với đủ field M0/M1 — ~~**phải là 100%**~~.

    > **SỬA 2026-08-17 — gate 100% ở đây đặt lên NHẦM chỉ số, và nó không bao giờ qua được.**
    > Phát hiện khi chạy thật: 10/10 phiên đóng với `mandatory_coverage_at_close = False`. Đó KHÔNG
    > phải lỗi độ phủ — nó là hệ quả trực tiếp của §8.5 quy tắc 3, thứ chính tài liệu này đã chốt:
    > người bệnh trả lời "không biết" là một **kết quả hợp lệ**, nhưng field vẫn `unknown`. Hệ thống
    > không ép được người bệnh biết điều họ không biết, nên nó **cố ý không bảo đảm** chỉ số này.
    > Quyết định ở P3 nói đúng điều đó: `should_stop` tính trên **cụm CHƯA HỎI**, không tính trên
    > `mandatory_fields_covered`.
    >
    > Bất biến hệ thống thật sự giữ — và là thứ đáng đặt gate — là **`mandatory_unasked` phải rỗng**:
    > không cụm nào mang field M0/M1 bị bỏ qua *im lặng*. Linh hoạt được đổi **thứ tự** hỏi, không
    > được **bỏ** hỏi (§8.2 mục 1). `metrics.py` trả cả hai chỉ số; gate cứng đi với chỉ số thứ hai,
    > còn chỉ số thứ nhất đọc như một mô tả (bao nhiêu phần trăm ca thu đủ được căn cứ), không phải
    > như một ngưỡng.
  - số lượt trung vị để hoàn thành, tách riêng ca lành tính và ca cần khoan sâu;
  - `user_led_ratio`: tỉ lệ câu hỏi thuộc cụm mà người bệnh vừa tự nhắc tới — đo trực tiếp hiệu quả
    của follow-the-user (§8.4);
  - `repeat_question_rate`: tỉ lệ hỏi lại thông tin đã biết hoặc đã được trả lời "không biết";
  - `deferral_depth`: số lượt trung bình một cụm bị hoãn trước khi được hỏi;
  - `abandonment_rate`: tỉ lệ phiên người bệnh bỏ giữa chừng — chỉ số trải nghiệm thật nhất, và là lý
    do §1 mục 5 tồn tại;
  - `catch_all_yield`: tỉ lệ phiên mà bước quét sót (§8.6 mục 4) thu được thêm triệu chứng — nếu gần 0
    thì hoặc checklist đã đủ, hoặc câu quét sót đang được hỏi sai cách.
- **red flag hai nhánh (§15.1)** — nhóm chỉ số mới, và là thứ trả lời được câu hỏi mà baseline
  `emergency recall 48.9%` đang bỏ ngỏ:
  - `agreement_rate` giữa nhánh rule và nhánh model;
  - `model_only` — model bắt, rule bỏ sót. **Đây là danh sách ứng viên để mở rộng rule**, và là output
    có giá trị nhất của cả cơ chế;
  - `rule_only` — rule bắt, model bỏ sót; đọc như chất lượng của nhánh model;
  - `model_branch_failure_rate` — tỉ lệ nhánh model lỗi/timeout. Không phải chỉ số chất lượng, nhưng
    nếu nó cao thì mọi con số trên đều mất mẫu số.
- **trải nghiệm bổ sung**: `median_turns` (hiện 21 lượt ở ca lành tính — xem §16.3 về ba đòn bẩy giảm),
  `uncooperative_stop_rate`.
- **toàn hệ thống**: exact match cho field red flag và demographics, latency p50/p95 và chi phí mỗi phiên — **so với baseline P0.3**.

### Gate tách làm hai, vì không phải metric nào cũng chạy được trong CI

**Gate cứng, chạy trong CI (deterministic, không gọi model thật):**

- 100% test an toàn ở §11 với fake LLM, gồm ca JSON hỏng/timeout, negation text signal, ca tắt SLM và
  invalid session state;
- **100% nhóm test "Linh hoạt và độ phủ" ở §11**, đặc biệt property test hoán vị thứ tự trả lời —
  đây là thứ duy nhất chặn được việc nới thứ tự hỏi làm mất field bắt buộc;
- không regression các test hiện có;
- unit test reducer/validator pass.

**Gate mềm, chạy tay theo release (model thật, trên 120 golden case):**

- red-flag recall: 100% — **kèm ghi rõ cỡ mẫu**, vì 100% trên 20 ca không chứng minh được gì;
- correction/retraction accuracy ≥ 98% trên tập edge case (tối thiểu 50 ca có nhãn);
- hallucinated negative rate: 0% trên tập safety;
- `symptom_group_router` accuracy ≥ 98%;
- latency p95 **không tệ hơn baseline P0.3** dù thêm 1–2 lời gọi;
- `mandatory_unasked` rỗng ở **100%** phiên — không có ngoại lệ, đây là loại 1 ở §8.1. (Thay cho
  `mandatory_coverage_at_close = 100%` của bản trước — xem ghi chú "SỬA 2026-08-17" ở trên: gate cũ
  đặt lên nhầm chỉ số và không bao giờ qua được.);
- số lượt trung vị **không tăng** so với baseline P0.3 (mục tiêu là giảm);
- `repeat_question_rate` giảm so với baseline;
- reviewer chấm “rõ, đúng ngữ cảnh, không lặp máy móc” ở ít nhất 90% transcript;
- reviewer chấm “agent có phản ứng theo điều tôi vừa nói” ở ít nhất 90% transcript — chỉ tiêu này đo
  đúng thứ §8.4 nhắm tới, và không thay thế được bằng chỉ số tự động nào.

Mọi ngưỡng phần trăm phải đi kèm mẫu số. Không có mẫu số thì không phải gate.

## 13. Definition of Done cho chính ví dụ này

Với transcript:

```text
User: Tôi bị sốt.
User: Mình là người lớn, nam, 20 tuổi.
User: Mình quên mất, mình không sốt.
```

Hệ thống phải đạt đồng thời:

1. Hồ sơ cuối có `age=20`, `sex=male`, `fever_reported=false`.
2. Các chi tiết phụ thuộc sốt được xoá về `unknown`; lịch sử vẫn ghi nhận lời khai cũ và đính chính mới.
3. Nếu phiên không bị ghim vào endpoint sốt, `symptom_group_router` chuyển từ `fever` sang `general`.
4. Câu tiếp theo là câu hỏi mở về vấn đề chính, không mặc định có đau hay khó chịu tại một vùng.
5. Nếu user hỏi “Bây giờ bạn đang hỏi tôi cái gì?”, extractor gán `asks_clarification`,
   `DialoguePolicy` giải thích ngắn mục đích rồi hỏi lại đúng một ý.
6. Không có chẩn đoán bệnh hoặc hướng điều trị tự động. `EARLY_VISIT`/`SELF_CARE` chờ HITL;
   `EMERGENCY` hiển thị cảnh báo tĩnh ngay và đồng thời escalate cho điều dưỡng, không chờ duyệt.
7. Lặp lại toàn bộ transcript với SLM bị tắt: kết quả 1–4 và 6 **không đổi**, chỉ mục 5 kém tự nhiên hơn.
8. Nếu người bệnh nói tiếp "mình bị đau bụng hai hôm nay", câu kế tiếp phải thuộc cụm đau bụng
   (follow-the-user, §8.4), không quay về cụm đứng kế tiếp trong danh sách khai báo. Đồng thời
   `coverage_ledger.mandatory_remaining` phải ghi lại những cụm bị đẩy lùi, và chúng phải được hỏi
   trước khi phiên đóng.

> **Cập nhật 2026-08-17 — cả 8 mục ĐÃ ĐẠT**, kiểm bằng `tests/test_services/test_dod_transcript.py`
> (cơ chế, LLM giả) và một lần chạy `deepseek-chat` thật
> (`eval/baselines/2026-08-17-p3-synthesis-transcripts.md`). Mục 5 là mục DUY NHẤT trước đây không
> chạy được: `answer_quality=asks_question` đã tồn tại nhưng không nhánh nào dùng nó - nay đi qua
> `DialoguePolicy`. Mục 7 (tắt SLM) đúng theo nghĩa hiện tại: không vai trò nào dùng SLM.

Lưu ý: mục 2 và 3 có thể **đã pass** nhờ `retraction.apply_retraction` và `registry._fever_ruled_out` (§2.3). Chạy P0.2 để biết chắc, đừng implement lại.

## 14. Việc nên làm ngay trong sprint kế tiếp

Bốn việc, theo đúng thứ tự:

1. ✅ **[XONG 2026-08-17]** **Thiết kế lại và nối `text_safety_signals` vào luồng chuẩn** (§9 P0.1). Khoảng trống
   defense-in-depth là có thật, nhưng matcher hiện tại chưa đủ để tạo disposition. Phải thêm
   negation/subject/time guard và test trước, rồi mới cho tập mẫu dương tính đã duyệt short-circuit.
2. ✅ **[XONG 2026-08-17]** **Chạy eval lấy baseline + đo latency hiện tại** (§9 P0.2–P0.3) —
   `eval/baselines/2026-08-17-p0-summary.md`. Emergency recall **48.9% (22/45)**; triage accuracy
   33.3% nhưng KHÔNG đọc được như chỉ số chất lượng (§2.4 lỗ hổng 1); red-flag recall 0% do lệch từ
   vựng mã (§2.4). ⚠️ Phải dùng `--mode api`: `--mode direct` chạy `TriagePipeline` LEGACY (§2.2). Không có baseline thì không chứng minh được kiến trúc mới đáng giá.
3. ✅ **[XONG 2026-08-17]** **`coverage_ledger` + ranking tất định** (§9 P3.1–P3.3). Đây là lát cắt tạo khác biệt lớn nhất về
   trải nghiệm: thuần code, không cần model mới, không cần máy GPU, và đo được ngay bằng
   `user_led_ratio` + số lượt trung vị. Làm ledger trước ranking — có sổ sách rồi mới được phép hoãn
   câu hỏi.
4. ✅ **[XONG 2026-08-17]** **`RoleProfile` với mọi profile trỏ về provider API** (§9 P1). Thuần code, có giá trị ngay cả khi
   không bao giờ có SLM, và là chỗ sinh ra số liệu để trả lời điều kiện §7.2.

Ba việc đầu **không phụ thuộc** vào quyết định roadmap ở §9.0, nên bắt đầu được ngay kể cả khi PM
chưa chốt.

> **Cập nhật 2026-08-17 — bốn việc trên đã xong, cộng thêm P2.4-P2.5 (reducer + `field_events`),
> P4.1-P4.2 (test), P4.5 (công tắc ngắt) và P5.2 (dời `_parse_json_object`). 590 test xanh.**
>
> Việc CÒN LẠI, xếp theo thứ tự nên làm — và điều quan trọng nhất là **chỉ một trong bốn cái này là
> việc engineering thuần**:
>
> 1. **PC — 4 protocol lâm sàng còn thiếu** (§9 track PC, §10). Vẫn là hạng mục lớn nhất trong toàn
>    tài liệu và vẫn chưa có người chủ trì. Phần lớn công là đọc tài liệu lâm sàng và quyết ngưỡng,
>    không phải viết code. Chừng nào 4/5 đích đến chưa tồn tại thì router và ranking còn bị giới hạn
>    tác dụng.
> 2. **Bảng quy đổi mã red flag** (§2.4). `RF-07`/`TEXT_SIGNAL_*` của hệ thống và
>    `RF-TRAUMA-POISONING-001` của golden case là hai hệ từ vựng, nên red-flag recall đo ra 0% dù hệ
>    thống có phát hiện. **Quyết định lâm sàng, không phải engineering** — nhưng nó chặn một gate ở §12.
> 3. **Clinical governance ký duyệt `SHORT_CIRCUIT_CODES`** (§2.1). 32/100 mã đang được phép
>    short-circuit; mã ngoài danh sách vẫn đi đường xác nhận nên hệ thống an toàn, chỉ là kém nhạy.
> 4. **P4.3-P4.4 — metric trải nghiệm** (§12). `user_led_ratio`, `repeat_question_rate`,
>    `deferral_depth`, `catch_all_yield`, `mandatory_coverage_at_close` chưa có chỗ nào tính ra số.
>    Dữ liệu thô đã có trong `stage_log` + `CoverageLedger.snapshot`; cần một script đọc log, và một
>    lần chạy model thật để có mẫu số.
>
> **Bổ sung 2026-08-19 sau vòng review V2 (§2.7) — chèn vào danh sách trên như sau:**
>
> 0. **P0.6 — sửa thứ tự `RED_FLAG` vs `USER_CANNOT_CONTINUE` trong `should_stop`.** Đứng **trước cả
>    bốn việc trên**: đây là lỗi an toàn trong code đang chạy, sửa nhỏ, và mọi việc liên quan tới ý
>    định người dùng đều bị chặn bởi nó.
> 5. **P3.9 — ý định người dùng → `user_can_continue`.** Engineering thuần, làm sau P0.6.
> 6. **ADR-006 — chốt hợp đồng phiếu bàn giao** (§17). Quyết định của PM + điều dưỡng, **không chặn**
>    bất kỳ việc nào ở trên, nhưng chặn việc versioning schema và chặn cả track UI W-07.
>
> `PC+` (multi-protocol) **không** nằm trong danh sách này: nó chỉ có nghĩa sau khi PC xong.
>
> **Bổ sung 2026-08-19 chiều — yêu cầu chủ dự án (§15).** Xếp xen vào danh sách trên theo tỉ lệ
> giá-trị/công-sức, không phải theo thứ tự chủ dự án liệt kê:
>
> | Việc | §  | Công sức | Vì sao ở đây |
> | --- | --- | --- | --- |
> | Mở quyền sửa red flag cho điều dưỡng + audit overlay | §15.4 | Nhỏ | Gap thật, đã kiểm chứng bằng code; đúng mô hình HITL của dự án |
> | Sửa quy tắc suy `False` theo tier + tăng batch | §15.8 | Nhỏ | Vừa giảm số lượt vừa **vá một nguồn dữ liệu sai**; hai lợi ích một lần sửa |
> | `USER_UNCOOPERATIVE` + đếm lạc đề | §15.7 | Nhỏ | Cùng chỗ code với P3.9, làm chung một lượt |
> | Hai output summary (NLP + field-based) | §15.3 | Vừa | Là output contract của agent; (b) render tất định nên rẻ, và nó là bản đối chứng của (a) |
> | Nhánh model red-flag + `red_flag_agreement` | §15.1 | Vừa | Đây là **cách duy nhất đang có** để biết rule bỏ sót cái gì |
> | 5 trường ISBAR còn thiếu + `priority_source` | §17, §15.2 | Vừa | Đi cùng ADR-006 |
> | Memory M1 (composite key + persist) | §15.9 | Vừa | Điều kiện tiên quyết của M2/M3 |
> | Protocol phi lâm sàng (chitchat/lifestyle) | §15.10 | Vừa | Tách khỏi track PC — engineering, không phải lâm sàng |
> | Memory M2 → M3 | §15.9 | Lớn | M3 cần consent/retention từ PM trước khi lên production |
> | RAG vào luồng chuẩn | §15.6 | Lớn | Phải quyết số phận `pipeline/weaviate_cloud.py` (§2.2) trước |
>
> Ba việc đầu cộng lại nhỏ hơn một protocol lâm sàng, và cả ba đều sửa một khiếm khuyết thật chứ không
> thêm bề mặt mới — nên chúng đi trước, kể cả khi track PC đã bắt đầu.
>
> P1.4 và P3.8 vẫn nợ vì cùng một lý do: cần API key và chi phí model thật. Hạ tầng đã sẵn — chạy eval
> là ra bảng.

Song song, đưa hai câu hỏi sau ra buổi planning — cả hai là quyết định phạm vi, không phải kỹ thuật:

- **Chọn lộ trình: `PC` chèn trước hay `P1`–`P3` chạy trước** (§9.0). Đây là câu hỏi quan trọng nhất
  trong tài liệu này, vì nó quyết định cả sprint. Bối cảnh ở §10: router và ranking chưa tạo thêm giá
  trị khi 4/5 đích đến chưa tồn tại, và `PC` là bốn lần khối lượng của một file 696 dòng logic lâm
  sàng.
- **Ai chủ trì `PC`** (§9 track PC). Phần lớn công là đọc tài liệu lâm sàng và quyết ngưỡng, không
  phải viết code — nếu giao nhầm cho track engineering thì ước lượng sẽ sai từ đầu.

Câu hỏi “có dựng máy chạy SLM không” **đã bị gỡ khỏi danh sách planning**: §7.2 giờ là phụ lục có
điều kiện, và điều kiện đó chỉ trả lời được sau khi P1.4 có số liệu. Trước đó không có gì để quyết.

Thứ tự này ưu tiên an toàn trước, correctness sau, rồi mới tới trải nghiệm — vì độ tự nhiên chỉ có ý
nghĩa khi đặt trên một state đúng, còn prompt văn phong thì che được lỗi giao diện chứ không che được
lỗi nhớ trạng thái.

Nhưng "cuối" ở đây là **thứ tự làm, không phải mức độ quan trọng**. Trải nghiệm có gate riêng ở §12
và có bất biến riêng ở §8.2; nó không phải phần được cắt đầu tiên khi sprint chật. Một agent hỏi đúng
mọi thứ nhưng khiến người bệnh bỏ giữa chừng thì không thu được triệu chứng nào — và đó cũng là một
lỗi an toàn, chỉ là lỗi khó nhìn thấy trong log hơn.


---

---

## 15. Yêu cầu chủ dự án 2026-08-19 — quyết định phạm vi và cách thực thi

Mục này ghi lại **yêu cầu sản phẩm do chủ dự án đưa ra**, không phải một đề xuất kỹ thuật để thẩm
định. Vì thế cách viết ở đây khác §9: mỗi mục là *quyết định đã chốt* + *điều kiện an toàn tối thiểu
để thực thi được nó* + *chỗ nó nằm trong kế hoạch*. Ở ba mục tôi có phản biện kỹ thuật, phản biện
được ghi đúng một lần rồi chuyển sang phương án thực thi — không mở lại.

Bản này **thay thế** phần "phạm vi bị loại trừ" của bản 2026-08-19 sáng: bốn mục từng bị đánh dấu
LOẠI ở đó (RAG grounding, memory xuyên phiên, ranh giới triage, stop policy mềm) đều đã được chủ dự
án khẳng định lại, nên chúng chuyển thành **có làm, kèm điều kiện**.

### 15.0. Bảng quyết định — 16 điểm

| # | Yêu cầu | Quyết định | Nằm ở |
| --- | --- | --- | --- |
| 1 | Không rule cứng; red flag do **rule + model** cùng chạy, so sánh khớp/không khớp ở cuối | Có làm | §15.1 |
| 2 | 3 mức triage vẫn cập nhật liên tục nhưng **không quyết định**; chạy triage sau summary để đối chiếu | Có làm, kèm 1 ngoại lệ an toàn | §15.2 |
| 3 | Phiếu summary I/S/B/A/R, trường rỗng không xuất, đưa hết câu trả lời của user | Có làm | §15.3, §16 |
| 4 | Hai dạng natural summary: (a) NLP gọn, (b) theo field đã detect | Có làm cả hai | §15.3 |
| 5 | **Điều dưỡng sửa được MỌI trường, kể cả red flag** (hiện đang khoá) | Có làm — gap thật, đã kiểm chứng | §15.4 |
| 6 | Rule ở dạng guardrails, không phải `if/else` theo bệnh | Đã có sẵn phần lớn | §15.5 |
| 7 | RAG grounding cho cả hai nhánh | Có làm, phạm vi hẹp | §15.6 |
| 8 | Dừng khi hết triệu chứng / user chửi tục / bất hợp tác | Có làm | §15.7 |
| 9 | Detect đúng và đủ triệu chứng (positive/negative/unknown) | Đã chạy | §2.3, §4 |
| 10 | LLM sinh câu hỏi phủ hết trường **và phủ hết nhóm bệnh** | Đã có cơ chế; thiếu 4 protocol | track PC |
| 11 | Hỏi nhanh hơn: batch lớn, **field bị bỏ qua coi là False** | Có làm batch — **quy tắc suy False phải sửa** | §15.8 |
| 12 | Memory: composite key, short hybrid, long-term 3 phiên gần nhất | Có làm theo 3 giai đoạn | §15.9 |
| 13 | Mở rộng protocol: bụng/đầu/lưng/da/tình dục + chitchat + lifestyle + summarize + search\_db | Có làm, tách hai loại protocol | §15.10 |
| 14 | Router bằng model nhỏ (Qwen3.5-4B) | Hạ tầng đã sẵn; điều kiện ở §7.2 | §15.10 |
| 15 | UX: streaming, loading, xuống dòng, câu hỏi dễ hiểu | Phần lớn đã chạy | §17 |
| 16 | Đang dài dòng — cần cơ chế giảm, chấp nhận đánh đổi | Có làm | §17.3 |

---

### 15.1. Red flag hai nhánh: rule và model cùng chạy, đối chiếu ở cuối

**Yêu cầu:** không dựa vào rule cứng một chiều. Cho agent/model phát hiện red flag song song với rule,
rồi **đưa xuống cuối để hai bên so sánh** — khớp hay không khớp.

Đây là một **thay đổi thật** và là hướng đúng: nó biến red flag từ một quyết định đơn nguồn thành một
quyết định có kiểm chứng chéo, và số liệu đối chiếu chính là thứ đo được chất lượng của cả hai bên.
Hiện repo đã có **hai nhánh nhưng chưa đối chiếu**:

| Nhánh | Nơi | Tính chất |
| --- | --- | --- |
| L0 — tín hiệu trên text thô | `common_safety/text_safety_signals.py` (383 dòng) | KHÔNG model, chạy trước mọi lời gọi LLM |
| Rule engine trên state | `common_safety/rules.py` (443 dòng) + `rule_engine.py` | KHÔNG model, chạy trên snapshot đã trích xuất |

Cái còn thiếu là **nhánh thứ ba (model) và bước đối chiếu**. Thiết kế:

```text
mỗi lượt:
  L0 text signals   ──┐
  rule engine       ──┼──> escalate NGAY nếu bất kỳ nhánh nào dương tính đã duyệt
  model red-flag    ──┘    (OR, không phải AND — xem bất biến bên dưới)

cuối phiên:
  red_flag_agreement = {
    "rule_only":  [...],   # rule bắt, model bỏ sót
    "model_only": [...],   # model bắt, rule bỏ sót  <- nguồn để mở rộng rule
    "both":       [...],
    "agreement_rate": 0.xx
  }
  -> ghi vào phiếu bàn giao + log, KHÔNG dùng để tự sửa quyết định
```

**Bốn ràng buộc bắt buộc:**

1. **Hợp nhất bằng OR, không phải AND, và không phải "chờ đối chiếu".** Bất kỳ nhánh nào cho tín hiệu
   dương tính đã duyệt thì escalate **ngay trong lượt** (`CLAUDE.md` nguyên tắc 4). Việc "đưa xuống
   cuối để so sánh" là **để đo và để điều dưỡng đọc**, không phải để hoãn cảnh báo. Nếu hai bên bất
   đồng thì lấy bên **an toàn hơn** — không lấy bên nào "đúng hơn", vì lúc đó chưa ai biết bên nào đúng.
2. **Model không được phép tắt một red flag mà rule đã bật.** Một nhánh mới chỉ được **thêm** phát
   hiện, không được **trừ**. Đây là hệ quả trực tiếp của bất biến §1 mục 3.
3. **Lỗi model không được làm mất nhánh nào.** Timeout/JSON hỏng ở nhánh model ⇒ phiên chạy tiếp với
   hai nhánh cũ, ghi `model_branch_status: "failed"` vào log. Đây là ca test bắt buộc.
4. **`red_flag_agreement` là dữ liệu, không phải quyết định.** Nó đi vào phiếu và vào metric; không có
   dòng code nào đọc nó để đổi mức ưu tiên.

**Giá trị đo được ngay:** `model_only` chính là danh sách ứng viên để bổ sung vào rule, và
`agreement_rate` là chỉ số trả lời được câu "rule của chúng ta có bỏ sót gì không" — thứ mà baseline
hiện tại (`emergency recall 48.9%`) đang đặt ra mà chưa có cách trả lời.

---

### 15.2. Mức triage: vẫn cập nhật liên tục, nhưng không còn là quyết định cuối

**Yêu cầu:** 3 mức triage vẫn được cập nhật trong lúc hội thoại, nhưng **không quyết định**; sau khi
có summary mới chạy triage để đối chiếu với một bên khác.

Vòng đánh giá trước tôi đã phản đối cách diễn đạt này vì sợ nó đẩy rule engine tất định ra khỏi agent.
Chủ dự án đã khẳng định lại, và khi đọc kỹ thì **hai thứ không mâu thuẫn** — chúng chỉ là hai vai trò
khác nhau của cùng một con số:

```text
TRONG hội thoại:
  rule_engine.evaluate(protocol, answers)  ->  provisional_priority
     dùng để:  (a) kích hoạt EMERGENCY banner tĩnh ngay trong lượt   [BẮT BUỘC GIỮ]
               (b) chọn nhánh câu hỏi / ngân sách (budget_key)        [đã chạy]
               (c) hiển thị cho điều dưỡng như "đề xuất tạm thời"
     KHÔNG dùng để: gửi bất cứ hướng xử trí nào cho bệnh nhân

SAU summary (ngoài ranh giới agent):
  snapshot + summary  ->  triage module  ->  final_priority
                       -> đối chiếu với provisional_priority
                       -> điều dưỡng duyệt (HITL) -> mới có hiệu lực
```

**Một ngoại lệ không đánh đổi được:** ca `EMERGENCY` vẫn phải hiện `EMERGENCY_MESSAGE` tĩnh **ngay
trong lượt**, không chờ summary, không chờ duyệt (`CLAUDE.md` nguyên tắc 4, `ARCHITECTURE.md:15-19`
ràng buộc 3). "Không quyết định" áp cho `EARLY_VISIT`/`SELF_CARE` — hai mức có thể chờ. Cấp cứu thì
không, vì cái giá của việc chờ là bất đối xứng.

**Hệ quả lên schema:** `HandoffSummary.proposed_priority` giữ nguyên tên và ý nghĩa (*đề xuất*, không
phải *kết luận*) — đúng `docs/prd.md:65` FR-05. Thêm hai trường:

```python
provisional_priority: TriagePriority | None   # rule engine trong hội thoại
priority_source: str                          # "rule_engine" | "downstream" | "nurse_edited"
```

Trường thứ hai là thứ khiến việc "so sánh với một bên khác" đọc được về sau — không có nó thì ba
nguồn cùng ghi vào một ô và không ai truy được ô đó đến từ đâu.

---

### 15.3. Hai output summary

**Đây là output contract của agent.** Cả hai đọc **cùng một snapshot đã validate** — đó là điều kiện
duy nhất khiến chúng không mâu thuẫn nhau (V2 §45 FR8 nói đúng điểm này).

**Output 1 — Natural summary, hai chế độ, cả hai đều làm:**

*Chế độ (a) — NLP gọn.* LLM viết lại toàn bộ câu trả lời của người bệnh thành văn xuôi: bỏ trùng lặp,
bỏ chitchat, **giải quyết đính chính bằng giá trị mới nhất**. Không được bịa thêm chi tiết y khoa
không có trong hội thoại (`CLAUDE.md` nguyên tắc 3), và phải đi qua `output_guard` như mọi văn bản
model sinh khác.

> Người dùng báo đau bụng bên phải từ sáng, cơn đau tăng dần, kèm buồn nôn. Phủ nhận nôn và tiêu
> chảy. Chưa xác định được có sốt hay không vì chưa đo nhiệt độ.

*Chế độ (b) — theo field đã detect.* Render tất định từ snapshot, **không qua model**:

```text
Triệu chứng ghi nhận:      <- các field = true
- Đau bụng bên phải
- Buồn nôn

Người bệnh phủ nhận:        <- các field = false
- Nôn, tiêu chảy

Chưa xác định được:         <- các field = unknown
- Sốt (chưa đo nhiệt độ)
```

Chế độ (b) là **bản đối chứng của chế độ (a)**: nếu (a) nói một điều mà (b) không có field nào đỡ,
thì (a) đang bịa. Đó là một kiểm tra rẻ và nên chạy tự động.

> **Một chỗ phải làm khác yêu cầu, và lý do:** yêu cầu ghi *"trường nào có thông tin thì đưa, còn lại
> False/Unknown thì thôi"*. Ở tầng **hiển thị** thì đúng — UI không cần liệt kê 30 dòng "không".
> Nhưng ở tầng **dữ liệu thì không được xoá**: "bệnh nhân phủ nhận đau lan xuống tay" là một dữ kiện
> lâm sàng có giá trị, và `unknown` là dữ kiện nói "chỗ này chưa ai biết" — xoá nó đi thì phiếu đọc
> ra giống hệt như đã hỏi và người bệnh nói không. Quy tắc: **snapshot giữ đủ ba giá trị, renderer
> mới lọc.** Riêng field an toàn thì `false` và `unknown` **luôn** được render, vì đó chính là chỗ
> điều dưỡng cần nhìn.

**Output 2 — Nurse structured summary:** JSON theo I/S/B/A/R → HTML, trường rỗng không xuất. Chi tiết
hợp đồng và 5 câu hỏi cần chốt ở §17.

**Kèm theo cả hai:** toàn văn hội thoại (`raw_conversation`) — yêu cầu "đưa hết tất cả câu trả lời của
user". UI điều dưỡng đã render khối này (`nurse.js`, mục "Hội thoại"), nên phần còn lại chỉ là đưa nó
vào bản JSON xuất ra.

---

### 15.4. Điều dưỡng sửa được mọi trường, kể cả red flag

**Đây là gap thật, đã kiểm chứng bằng code**, và là mục cụ thể nhất trong toàn bộ 16 điểm:

- `nurse.js:73` render red flag dưới dạng banner đọc-chỉ (`red-flag-alert`), cùng với
  `chief_complaint`, `onset`, `severity`, `associated_symptoms` — tất cả đều **không sửa được**.
- Form duyệt chỉ có ba ô: `edited_priority`, `approved_response`, `nurse_notes`.

**Phải tách hai khái niệm đang bị gộp làm một:**

| Khái niệm | Nơi | Có được nới không |
| --- | --- | --- |
| `escalation_lock` (`session.py:107`) | **trong phiên** — chặn agent tự hạ escalation đã bật | **KHÔNG.** Đây là loại 1 §8.1, và `flags.py:13` đã ghi nó không có công tắc tắt |
| Quyền sửa của điều dưỡng | **sau phiên**, ở bước duyệt | **CÓ** — đây chính là HITL, không phải ngoại lệ của HITL |

Nói cách khác: khoá hiện tại chặn **model** hạ cờ, và điều đó phải giữ. Nó không nên chặn **con
người** — điều dưỡng là người có thẩm quyền lâm sàng cao nhất trong luồng này, khoá họ lại là làm
ngược chính mô hình HITL mà dự án đặt ra.

**Thực thi:**

1. Mở quyền sửa cho toàn bộ trường của phiếu: identify, situation, background, assessment, symptoms,
   **red flags**, recommendation, triage.
2. **Bản ghi do hệ thống sinh là bất biến.** Sửa của điều dưỡng ghi vào một lớp overlay, không ghi đè:

   ```json
   {
     "field": "red_flags.RF-07",
     "generated_value": true,
     "current_value": false,
     "edited_by": "nurse_123",
     "edited_at": "...",
     "reason": "..."
   }
   ```

   Lý do: nếu có sự cố, câu hỏi đầu tiên sẽ là "hệ thống có bắt được không, và ai đã bỏ nó đi" — mất
   `generated_value` là mất luôn khả năng trả lời.
3. **Hạ một red flag phải kèm lý do**, không phải một cú click. Đây là ma sát cố ý, và là loại ma sát
   duy nhất tôi đề nghị giữ trong toàn mục này.
4. **Một việc không rút lại được:** nếu ca đã `EMERGENCY` và banner tĩnh **đã hiển thị cho bệnh nhân**,
   thì điều dưỡng hạ cờ về sau chỉ đổi phiếu và luồng xử trí — **không xoá được cái người bệnh đã
   đọc**. UI phải nói rõ điều đó tại chỗ, thay vì để điều dưỡng tưởng mình vừa thu hồi một cảnh báo.

---

### 15.5. Rule ở dạng guardrails

Đã đúng hướng sẵn, không phải viết mới. Hệ thống hiện **không** có `if fever: ... if chest_pain: ...`;
cái nó có là năm guardrail đúng như yêu cầu mô tả:

| Guardrail trong yêu cầu | Hiện thực |
| --- | --- |
| Safety guardrail | `common_safety/` (L0 + rules), không tắt được (`flags.py:13`) |
| Critical information guardrail | tier M0/M1 + `mandatory_unasked` (§8.2, §12) |
| Unsupported recommendation guardrail | `output_guard.check()` chặn chẩn đoán và câu hỏi ngoài plan |
| Conversation stop guardrail | `should_stop` 4 reason code |
| Output validation guardrail | `EvidencePolicy` + `_evidence_in_message` |

Việc còn lại là **giữ cho nó không trôi ngược thành rule cứng** khi track PC viết 4 protocol mới —
mỗi protocol mới là một cơ hội để `if` theo bệnh lẻn vào. Đề nghị: review PC bám đúng bảng trên.

---

### 15.6. RAG grounding cho cả hai nhánh

**Có làm, nhưng phạm vi hẹp hơn V2 §13 mô tả.** Ranh giới quyết định bởi một câu hỏi duy nhất: *nếu
RAG trả về rác, hậu quả là câu chữ xấu hay là câu hỏi lâm sàng sai?*

| Tầng | RAG được ground | Vì sao |
| --- | --- | --- |
| Protocol router | ✅ | Chọn sai ⇒ rơi về `GENERIC_PROTOCOL`, không mất red flag (§11 test 6) |
| Model red-flag branch (§15.1) | ✅ | Chỉ được **thêm** phát hiện; nhánh rule vẫn chạy độc lập |
| Summarizer (NLP) | ✅ | Ground để diễn đạt đúng thuật ngữ, không để thêm dữ kiện |
| Diễn đạt câu hỏi | ✅ | Chỉ đổi **cách nói**, không đổi **hỏi cái gì** |
| **Chọn hỏi field nào** | ❌ | Đây là checklist lâm sàng — ADR-003, `output_guard.py:145-163` |

Nói ngắn: **RAG ground cách nói và cách nhận diện, không ground việc chọn câu hỏi lâm sàng.** Muốn
thêm câu hỏi mới thì thêm vào protocol (track PC) và qua review lâm sàng — đó là con đường đã có, và
nó chậm hơn RAG đúng ở chỗ nó nên chậm.

Hạ tầng: `pipeline/weaviate_cloud.py` đã có nhưng đang là nhánh tooling ngoài luồng chuẩn (§2.2).
Việc đầu tiên là quyết định nó có vào luồng hay không, trước khi bàn ground cho tầng nào.

---

### 15.7. Khi nào dừng — bổ sung hai điều kiện còn thiếu

`should_stop` hiện có 4 reason code (§9 P3.9 đang bổ sung nhánh ý định người dùng). Yêu cầu thêm hai
tình huống, cả hai đều **không** được là dừng tức thì:

**(a) "Không còn triệu chứng gì khác."** Là tín hiệu mạnh, **không phải lệnh dừng tuyệt đối**:

```text
"không còn gì nữa"
      ↓
còn cụm CHƯA HỎI mang field M0/M1?
   ├─ CÓ  -> vẫn hỏi nốt, nhưng nói rõ vì sao:
   │         "Mình hỏi thêm 2 ý an toàn nữa rồi chốt nhé."
   └─ KHÔNG -> STOP
```

Lý do giữ nhánh trên: người bệnh nói "hết rồi" khi chưa ai hỏi họ về đau lan xuống tay hay ngất — họ
không biết những thứ đó là triệu chứng cần khai. Đây đúng là §8.2 mục 1, không phải ngoại lệ mới.

**(b) Bất hợp tác / lạc đề / chửi tục.** Không dừng ngay ở lượt đầu. Đếm ba tín hiệu:

```text
off_topic_streak        (số lượt liên tiếp không trả lời câu đang hỏi)
clinical_information_gain  (lượt vừa rồi có field nào mới không)
explicit_refusal
```

Ngưỡng đề xuất: **2–3 lượt liên tiếp** vừa lạc đề vừa không thu được field mới ⇒ agent **hỏi một lần**:

> Nếu bạn không muốn bổ sung thêm, mình có thể tổng hợp những gì đã có. Bạn muốn dừng ở đây không?

Tiếp tục không hợp tác ⇒ `STOP` với reason code mới `USER_UNCOOPERATIVE`, và **phiếu phải đánh dấu
incomplete** kèm `missing_information` — hệt như nhánh ý định người dùng ở P3.9. Ba lý do dừng khác
nhau không được thu về cùng một phiếu trông giống nhau: điều dưỡng cần biết ca này thiếu thông tin vì
người bệnh bỏ dở, chứ không phải vì không có triệu chứng.

**Chửi tục đơn lẻ không phải tín hiệu dừng.** Người đang đau và sợ thì nói năng không dễ chịu — đó là
bối cảnh y tế bình thường. Chỉ đếm khi nó **đi kèm** việc không trả lời.

---

### 15.8. Hỏi nhanh hơn: batch lớn — và quy tắc suy `False` phải sửa

**Phần đồng ý, làm ngay:** batch nhiều field trong một lượt là cách chính để rút ngắn hội thoại, và
`batching.py` (206 dòng) + `ScreeningGroup` đã làm đúng thế. Có thể **tăng kích thước batch**, đặc
biệt cho nhóm câu hỏi Có/Không cùng chủ đề. Trần trên vẫn cần: 20 câu một lượt thì người bệnh bỏ sót,
trả lời không theo thứ tự, và một chữ "không" không biết đang phủ định câu nào (V2 §17 nói đúng).
Đề xuất **4–7 ý mỗi lượt**, gom theo nhóm, và tune bằng `abandonment_rate`.

**Phần phải làm khác yêu cầu — nêu một lần rồi chuyển sang phương án:**

> Yêu cầu: *"hỏi một đống câu, người dùng bỏ qua cái nào thì cho cái đấy là False luôn"*.
>
> Im lặng không phải phủ định. Người bệnh bỏ qua một ý vì không đọc kỹ, vì không hiểu, hoặc vì không
> biết — và khi field đó là `chest_pain_radiation` hay `loss_of_consciousness` thì "suy ra False" tạo
> ra một phiếu ghi *"người bệnh phủ nhận ngất"* trong khi **chưa ai hỏi họ về ngất**. Điều dưỡng đọc
> phiếu đó không có cách nào biết sự khác nhau. Đây đúng là loại lỗi im lặng mà `CLAUDE.md` nguyên
> tắc 3 nhắm tới, và nó cũng xoá mất chính distinction `NULL ≠ UNKNOWN` mà kế hoạch V2 §9 nhấn mạnh.

**Phương án đạt được cùng mục tiêu (hỏi ít lượt hơn) mà không tạo dữ liệu sai — theo tier field:**

| Tier | Bỏ qua trong batch ⇒ | Lý do |
| --- | --- | --- |
| M0/M1, field an toàn | `unknown` + **hỏi lại đúng một lần**, ngắn gọn | Không được suy diễn ở chỗ đắt nhất |
| C (protocol-specific) | `unknown`, không hỏi lại | Ghi vào `missing_information` là đủ |
| O/H (tuỳ chọn) | `false` — **đúng như yêu cầu** | Chi phí sai thấp, lợi ích tốc độ thật |

Cộng thêm một mẹo rẻ hơn mọi suy diễn: **cho người bệnh phủ định gộp một câu**. `ScreeningGroup` đã
làm sẵn cơ chế này — hỏi "còn 4 dấu hiệu sau, bạn có cái nào không?" và một chữ "không" đóng cả bốn
field một cách **tường minh**, vì người bệnh đã nghe đọc đủ danh sách (`models.py:36-64`,
`session.py:94-96` ghi rõ guard turn-scoping). Đó là cách hợp lệ để một lượt lấp nhiều field: **người
bệnh phủ định, chứ không phải hệ thống suy ra.**

---

### 15.9. Memory — ba giai đoạn, không làm ngược thứ tự

**Yêu cầu (đủ ba tầng):** composite key `user_id + conversation_id`; short memory hybrid; long memory
vào DB, mở hội thoại mới thì lấy 3 phiên gần nhất để hỏi thăm.

Hướng thiết kế đúng, nhưng **thứ tự thực thi phải đảo lại** vì một dữ kiện: `ARCHITECTURE.md:364-369`
ghi `session_store` còn **mất khi restart** — phiên đang dở còn chưa sống nổi qua một lần deploy, mà
đã bàn tới ký ức xuyên phiên. Ba giai đoạn:

**M1 — Composite key + persist phiên đang dở.** *Điều kiện tiên quyết của hai giai đoạn sau.*

- Key: `user_id + conversation_id`, mỗi hội thoại là một collection độc lập.
- ⚠️ **`conversation_id` không nên là timestamp** như V2 §3.2 đề xuất: hai phiên mở cùng giây sẽ đụng
  nhau, và timestamp trong khoá là một mẩu metadata rò ra ngoài. Dùng UUID/ULID, để `created_at` ở một
  cột riêng.
- Persist event log + snapshot sau mỗi lượt được nhận. Đây chính là thứ khiến "hỏi vu vơ rồi quay lại
  hỏi cái cũ" chạy được qua một lần restart.

**M2 — Short memory hybrid.** Đúng như yêu cầu mô tả (cách 3), và **phần lớn đã chạy**:

```text
Structured snapshot   [ĐÃ CÓ - reducer, là nguồn sự thật]
+ Tóm tắt lượt cũ      [CHƯA CÓ - cần khi context dài]
+ N lượt raw gần nhất  [ĐÃ CÓ - session.conversation]
```

Chỉ thiếu bước nén khi context vượt ngưỡng. Bất biến: **summarizer nén phần hội thoại, không bao giờ
ghi đè snapshot.** Nếu tóm tắt và snapshot bất đồng thì snapshot thắng — nó là thứ có bằng chứng
`evidence_span`, còn bản tóm tắt thì không.

**M3 — Long memory + hỏi thăm phiên trước.** Lưu `nurse_summary_json` thành một cột như yêu cầu; mở
hội thoại mới thì lấy 3 `conversation_id` gần nhất, tóm tắt lại để agent hỏi thăm. Ba điều kiện tối
thiểu, vì đây là PHI (`CLAUDE.md` nguyên tắc 5):

1. **Bất biến tuyệt đối — dữ kiện lịch sử không tự trở thành dữ kiện hiện tại.** `previous fever =
   true` **không** được nạp thành `current fever = true`. Nó vào một namespace riêng (`history.*`),
   chỉ dùng để agent hỏi lại, và snapshot phiên mới bắt đầu từ `NULL` như mọi phiên khác. Đây là bất
   biến số một của cả M3, và cũng là điều chính V2 §22 đã nhấn mạnh.
2. **Truy cập theo đúng `user_id` đang đăng nhập**, không có đường nào đọc chéo hồ sơ người khác. Cần
   một test cho riêng việc này.
3. **Consent + retention** — bệnh nhân biết hệ thống nhớ gì và trong bao lâu. Đây là câu hỏi cho PM,
   không phải cho kỹ thuật, nhưng nó phải có câu trả lời **trước khi** M3 lên production.

Trải nghiệm mà M3 mở ra (*"Lần trước bạn đau bụng, hiện đã đỡ hơn chưa? Có làm theo lộ trình bác sĩ
đưa không?"*) là thứ đáng làm — nó biến sản phẩm từ một form hỏi bệnh thành một chỗ có người theo dõi.
Chỉ cần nó đứng sau M1.

---

### 15.10. Mở rộng protocol: hai loại, đừng trộn vào nhau

**Yêu cầu:** hết tập trung vào fever; thêm bụng/đầu/lưng/da/tình dục; xử lý được cả long-tail (ngứa
chân, ê mông, nghi giang mai) và cả chitchat/lifestyle (uống bia, chạy bộ); dùng model nhỏ để route.

Điểm quan trọng nhất của mục này: **những thứ đang được gọi chung là "protocol" thực ra là hai loại
khác hẳn nhau**, và trộn chúng vào một registry sẽ hỏng cả hai.

| | **Protocol lâm sàng** | **Protocol phi lâm sàng** |
| --- | --- | --- |
| Ví dụ | fever, bụng, ngực, khó thở, đầu | chitchat, lifestyle, summarize, search\_db |
| Nội dung | field + tier + cụm + skip-rule + luật triage | intent handler, không có checklist |
| Ai viết | Data Lead + review lâm sàng | Engineering |
| Quy mô | ~700 dòng logic lâm sàng mỗi nhóm | vài chục dòng |
| Sinh red flag | Có | **Không** — nhưng L0 vẫn chạy trên mọi lượt |
| Nằm ở | track PC | track P |

**Ba nhóm ca cần xử lý, ba đường khác nhau:**

1. **Trong 5 nhóm MVP** → protocol lâm sàng riêng. Đây là track PC, hạng mục lớn nhất còn lại.
2. **Long-tail ngoài 5 nhóm** (ngứa chân, ê mông, nghi giang mai) → `GENERIC_PROTOCOL` + L0 safety.
   Agent vẫn hỏi được, vẫn bắt được red flag, và `registry.py:27-30` đã ghi nguyên tắc đúng: **generic
   không bao giờ kết luận an toàn** — nó thu thập rồi bàn giao, không tự trấn an. Cách xử lý long-tail
   là *bàn giao sớm cho người*, không phải *cố tỏ ra biết*.
3. **Phi lâm sàng** (uống bia, chạy bộ) → protocol phi lâm sàng.

> **Về ví dụ "uống bia khi đang dùng kháng sinh":** cách xử lý đúng là hỏi **đang dùng thuốc gì, điều
> trị bệnh gì**, rồi bàn giao — không hard-code "kháng sinh + bia ⇒ tê liệt thần kinh". Tương tác với
> rượu phụ thuộc thuốc cụ thể, liều, bệnh nền; một luật rộng như vậy vừa sai về y khoa vừa là dạng
> "kết luận" mà `CLAUDE.md` nguyên tắc 2 cấm. Chính kế hoạch V2 §46 NFR4 cũng đã kết luận đúng như
> thế. Với MVP, đường an toàn nhất cho nhóm này là: thu thập thuốc/bệnh nền → không đưa lời khuyên →
> bàn giao.

**Router bằng model nhỏ (Qwen3.5-4B):** hạ tầng đã sẵn — `RoleProfile` có sẵn vai trò
`symptom_group_router` (§7.3), chỉ cần đổi `ROLE_ORDER_SYMPTOM_GROUP_ROUTER`. Bốn ràng buộc đã chốt ở
§3 vẫn nguyên: router **chỉ được gọi trong 4 trigger** ở §3.1 (không phải mọi lượt), sàn deterministic
`registry.select_protocol` chạy trước, route sai **không được** làm mất common-safety red flag (§11
test 6), và điều kiện tự host SLM nằm ở §7.2 — chưa trả lời được cho tới khi P1.4 có số đo.

**Multi-protocol đồng thời** (`primary` + `secondary[]` như V2 §6): xem §9 track `PC+`. Xếp sau PC vì
merge hai protocol chỉ có nghĩa khi có hơn một protocol thật để merge.

---

## 16. Non-functional: UX, ngôn ngữ, và độ dài hội thoại

### 16.1. Trình bày phản hồi

| Yêu cầu | Trạng thái |
| --- | --- |
| Streaming | ✅ `/chat/stream` |
| Xuống dòng, không đoạn quá dài, bullet cho câu Có/Không | ✅ §6.4 — hai đoạn tách nhau, gạch đầu dòng khi nhiều ý |
| Cấm in đậm/nghiêng/bảng/tiêu đề | ✅ có lý do: markdown phải hợp lệ theo **từng mẩu** stream |
| **Loading indicator** | ⛔ chưa xác nhận ở UI |

Một chi tiết đã đo và cần biết khi động vào phần này: renderer streaming hiện **gom trọn rồi mới phát**
— `output_guard` phải chạy xong trước khi người bệnh đọc được chữ nào. Cái giá là **p50 ~1.2s** im
lặng trước khi chữ đầu tiên hiện ra. Đây chính là chỗ loading indicator có giá trị nhất, và cũng là lý
do không nên "sửa" độ trễ đó bằng cách phát sớm: guard chạy sau khi người bệnh đã đọc thì không còn là
guard.

### 16.2. Ngôn ngữ cho người không có chuyên môn y tế

Không dùng thuật ngữ (*dyspnea*, *orthopnea*); hỏi Có/Không, mức độ, thời gian, vị trí, con số cụ thể
nếu người bệnh biết. Cơ chế đã có: `synthesis` diễn đạt lại câu hỏi mà rule engine đã chọn, và
`output_guard` chặn phần vượt phạm vi.

Một ngoại lệ đã chốt và **không nên "cải thiện"**: câu sàng lọc gộp được ghép **tĩnh** từ
`ScreeningGroup.probe_hint`, không cho LLM diễn đạt lại — vì "LLM diễn đạt lại thì có thể lược mất
vài ý trong danh sách" (`models.py:52-56`). Với một danh sách dấu hiệu nguy hiểm, lược một ý là mất
một cơ hội phát hiện. Đây là chỗ chấp nhận văn phong cứng hơn để đổi lấy tính đầy đủ.

### 16.3. Giảm dài dòng — bảy cơ chế, và cái nào chưa dùng hết

Yêu cầu nêu đúng bản chất: y tế cần chính xác nên **phải đánh đổi**, nhưng đánh đổi phải có cơ chế
chứ không phải "cứ còn `NULL` thì cứ hỏi".

| Cơ chế | Trạng thái | Còn dư địa |
| --- | --- | --- |
| Protocol routing | ✅ | Nhiều — 4/5 nhóm chưa có (track PC) |
| Active field selection theo protocol | ✅ | |
| Priority scoring (tier M0/M1/C/O/H) | ✅ `ranking.py` | |
| Question batching | ✅ `batching.py` | **Có — tăng batch lên 4–7 ý (§15.8)** |
| State reuse (không hỏi lại field đã biết) | ✅ | |
| Soft turn budget | ✅ `protocol.budget` | |
| Information gain / dừng theo đủ căn cứ | ✅ `_has_sufficient_evidence` | |
| Phủ định gộp theo nhóm | ✅ `ScreeningGroup` | **Có — dùng nhiều hơn (§15.8)** |

Số đo hiện tại: ca lành tính đi hết **21 lượt**. Ba đòn bẩy rẻ nhất để kéo xuống, theo thứ tự:

1. **Tăng kích thước batch** và dùng phủ định gộp nhiều hơn (§15.8) — thuần cấu hình + nội dung.
2. **Bỏ cụm tier O/H sớm hơn** khi đã đủ căn cứ.
3. **Nhánh ý định người dùng** (§9 P3.9) — người bệnh chủ động chốt sớm.

Và một chỉ số phải đọc **cùng lúc** với số lượt, nếu không sẽ tối ưu sai: `mandatory_unasked` phải
rỗng ở 100% phiên (§12). Rút ngắn hội thoại bằng cách bỏ hỏi field bắt buộc là làm hỏng đúng thứ sản
phẩm này tồn tại để làm.

---

## 17. Hợp đồng phiếu bàn giao: ADR-006 và template ISBAR

ADR-006 ("format phiếu tóm tắt phải chốt trước khi viết schema JSON") vẫn để trống, trong khi
`HandoffSummary` (`src/models/schemas.py:138-149`) đã chạy và UI W-07 đã dựng theo nó. Đây là món nợ
duy nhất trong tài liệu này thuộc về **hợp đồng dữ liệu** chứ không phải hành vi agent.

Team có một template ISBAR (*"Cấu trúc ISBAR chuẩn cho AI sinh ra phiếu tóm tắt [WHO]"*). Đối chiếu
với schema đang chạy:

| Template ISBAR | `HandoffSummary` hiện có | Việc phải làm |
| --- | --- | --- |
| **[I]** Patient: tuổi, giới tính | ❌ | Thêm `age`, `sex` |
| **[I]** Triage Category | ✅ `proposed_priority` | Thêm `provisional_priority` + `priority_source` (§15.2) |
| **[S]** Lý do vào viện, 1 câu | ✅ `chief_complaint` | — |
| **[B]** Dị ứng: Có/Không/Unknown | ❌ | Thêm `allergies`, dùng đúng 3 giá trị của reducer |
| **[B]** Bệnh nền | ❌ | Thêm `comorbidities` — **liệt kê tất cả**, xem mục 4 dưới |
| **[B]** Thuốc đang dùng | ❌ | Thêm `current_medications` |
| **[A]** Onset | ✅ `onset` | — |
| **[A]** Severity | ✅ `severity` | — |
| **[A]** Red Flags Detected | ✅ `red_flags` | Thêm `red_flag_agreement` (§15.1) |
| **[A]** Missing Information | ✅ `missing_information` | — |
| **[R]** AI Action / Pending Action | ⚠️ | Đổi tên, xem mục 3 dưới |
| — | ✅ `protocol_reason`, `detect_source`, `grounding_source` | **Giữ** — dấu vết truy nguyên |
| — | ✅ `associated_symptoms` | — |

**7/13 trường đã có; 4 trường thiếu là dữ liệu hành chính/tiền sử đơn giản; 2 trường cần quyết định.**
Tức là **bổ sung field, không phải migrate kiến trúc**.

Năm câu hỏi cần chốt trong ADR-006, kèm khuyến nghị:

1. **Giữ `HandoffSummary` phẳng và map ISBAR ở tầng render, hay đổi schema thành lồng I/S/B/A/R?**
   → *Khuyến nghị: giữ phẳng, map khi render.* Rẻ hơn, không đụng `NurseQueueItem`, và giữ được bất
   biến "natural summary và phiếu bàn giao đọc **cùng một** snapshot đã validate" (§15.3).
2. **Bổ sung 5 trường còn thiếu** như bảng trên. Dị ứng dùng đúng semantics 3 giá trị
   (`true`/`false`/`unknown`) của reducer, **không thêm kiểu mới**.
3. **Khối `[R]` viết như hành động đã thực hiện** (`AI Action: Khuyên bệnh nhân đến bệnh viện ngay`).
   Đọc theo mặt chữ thì AI đã khuyên bệnh nhân trước khi điều dưỡng duyệt — ngược `CLAUDE.md` nguyên
   tắc 1. → *Khuyến nghị: đổi thành `proposed_action` + `approval_status`.* Ngoại lệ duy nhất đã chốt:
   ca `EMERGENCY` hiện `EMERGENCY_MESSAGE` tĩnh ngay, không chờ duyệt và không do model sinh
   (`CLAUDE.md` nguyên tắc 4, §15.2).
4. **`Bệnh nền: chỉ hiển thị bệnh có liên quan nếu AI có khả năng lọc`** giao một phán đoán lâm sàng
   cho LLM. Lọc sai thì điều dưỡng không có cách nào biết cái gì đã bị giấu — lỗi im lặng, và ngược
   `CLAUDE.md` nguyên tắc 3. → *Khuyến nghị MVP: liệt kê tất cả.* Sắp xếp lại thì được (bằng danh sách
   tĩnh do lâm sàng ký duyệt, giống `SHORT_CIRCUIT_CODES`); giấu đi thì không.
5. **Nhãn RED/YELLOW/GREEN hay *Cấp cứu / Khám sớm / Tự theo dõi*?** `CLAUDE.md` và UI đang dùng tiếng
   Việt. → Nếu phiếu cho điều dưỡng dùng màu theo WHO thì đó là **nhãn hiển thị**; giá trị lưu trong
   `TriagePriority` giữ nguyên.

**Quy tắc render, áp cho cả JSON và HTML** (§15.3):

- Trường không có giá trị ⇒ **không xuất** trong JSON gửi renderer, và renderer chỉ render trường tồn
  tại. Không xuất `"allergies": null`.
- **Nhưng snapshot giữ đủ ba giá trị.** Việc lọc xảy ra ở renderer, không ở nguồn dữ liệu.
- **Ngoại lệ — field an toàn luôn được render** kể cả khi `false` hoặc `unknown`. "Người bệnh phủ nhận
  đau lan xuống tay" và "chưa ai hỏi về đau lan xuống tay" là hai thứ điều dưỡng bắt buộc phải phân
  biệt được, và đó chính là chỗ họ nhìn đầu tiên.
- Kèm `raw_conversation` — toàn văn câu trả lời của người bệnh.

**Điều dưỡng sửa được mọi trường của phiếu này, gồm cả red flag** — xem §15.4 về lớp overlay giữ
`generated_value` và về việc `escalation_lock` (khoá trong phiên, chặn model) không phải là khoá
quyền của điều dưỡng.

Một điểm template làm **đúng**: nó giữ `Triage Category` ngay trong khối `[I]`. Trường này **do code
tất định điền, không do LLM** — cần ghi rõ điều đó trong chính template, vì đó là chỗ dễ bị hiểu nhầm
nhất khi người mới đọc phiếu.
