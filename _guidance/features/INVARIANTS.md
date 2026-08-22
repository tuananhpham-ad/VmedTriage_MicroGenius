# Bất biến — không đánh đổi lấy bất cứ thứ gì

> File nền. Mọi spec trong `_guidance/features/` trỏ về đây thay vì chép lại.
> Nguồn: `_guidance/archive/what_to_do_next_2026-08-22_full.md` §1–§2.

## 1. Sáu tầng của một lượt

Kiến trúc đã chốt: **deterministic controller + model workers + protocol-grounded tools + HITL**.
Controller là code, không phải LLM.

```text
Tin nhắn người dùng
  L0  text_safety_signals   [KHÔNG model]  -> ứng viên red flag trên text thô
  L1  controller            [SLM + code]   -> model đề xuất, code định đoạt trong tập hợp lệ
  L2  symptom_group_router  [SLM tùy chọn] -> chỉ gọi ở 4 trigger đóng
  L2  fact_extractor        [SLM/LLM]      -> field_events JSON kèm bằng chứng
  L3  reducer + rule_engine [KHÔNG model]  -> snapshot, cụm kế tiếp, mức đề xuất
  L4  synthesis/renderer    [SLM/LLM]      -> câu tiếng Việt theo ResponsePlan đóng
  L5  output_guard          [KHÔNG model]  -> chặn chẩn đoán/câu hỏi ngoài plan
```

## 2. Mười bất biến

Mọi thay đổi trong `_guidance/features/` phải giữ đủ cả mười:

1. **Mọi tầng ghi "KHÔNG model" không bao giờ được thay bằng một lời gọi model**, kể cả khi model tốt
   lên. Đó là những tầng khiến hệ thống test được bằng fake LLM và audit được sau sự cố.
2. **Controller chỉ được chọn trong tập hành động do code tính ra.** Model *đề xuất*; tập hành động
   hợp lệ do code sinh; model chết thì rơi về controller tất định. Nó không chọn câu hỏi lâm sàng và
   tuyệt đối không chọn mức ưu tiên.
3. **Không có đường nào để một lỗi model (timeout, JSON hỏng, route sai) làm mất red flag.**
4. Model không kết luận chẩn đoán bệnh. Không có bước nào tên `diagnose_disease` trong hệ thống này.
5. Mức ưu tiên do rule engine tất định quyết; LLM chỉ trích xuất và diễn đạt.
6. Văn bản safety-facing là template tĩnh đã duyệt, không đi qua LLM.
7. Mọi lần dừng có reason code ổn định; dừng vì ý định người dùng hoặc vì bất hợp tác **phải đánh dấu
   phiếu là chưa đầy đủ**.
8. Linh hoạt được đổi **thứ tự** hỏi, không được **bỏ** hỏi: `mandatory_unasked` phải rỗng khi phiên
   đóng bình thường.
9. Dữ kiện lịch sử không tự trở thành dữ kiện hiện tại.
10. **Trải nghiệm hội thoại là yêu cầu sản phẩm, không phải phần thưởng thêm.** Một agent hỏi đúng
    nhưng khiến người bệnh bỏ giữa chừng thì không thu được triệu chứng nào — độ phủ bằng 0.

Hai mục tiêu "hỏi linh hoạt" và "khai phá đủ" **không phải đánh đổi**, vì trong code độ phủ và thứ tự
hỏi đã tách rời: độ phủ do tier field M0/M1 quyết, thứ tự do hàm xếp hạng tất định quyết. Nới thứ tự
không đụng tới bảo đảm độ phủ. Đây là điều kiện khiến `F01` làm được.

## 3. Đã chạy — đừng viết lại

Code là đặc tả; cột cuối là nơi đọc. Package engine:
`src/services/symptom_protocol/` (cơ chế, trung lập với nhóm triệu chứng).
Nội dung theo bệnh nằm **ngoài** package: `src/services/checklists/`, `src/services/engines/`.

| Cơ chế | Nơi |
| --- | --- |
| L0 text safety (độc lập model, chạy trước mọi lời gọi LLM) | `common_safety/text_safety_signals.py` (383 dòng) |
| Rule engine red flag trên snapshot | `common_safety/rules.py` (443), `rule_engine.py` |
| Router tất định + `_fever_ruled_out` | `registry.select_protocol` (`registry.py:40-58`) |
| Extraction có bằng chứng, 3 `operation` / 3 giá trị snapshot | `intake_agent.py`, `reducer.py:22-70` |
| Đính chính, rút lời, xoá dây chuyền field phụ thuộc, audit | `retraction.py`, `reducer.py:72-100` |
| `escalation_lock` — model không tự hạ escalation trong phiên | `session.py:107` |
| Coverage ledger + hàng đợi nợ | `coverage.py:33-88` |
| Ranking tất định 5 thành phần | `ranking.py:40-44`, `:96-113` |
| Stage machine + `should_stop` 6 luật có thứ tự | `stage_machine.py:240-280`, `:327-401` |
| Batch câu hỏi + phủ định gộp theo nhóm | `batching.py`, `models.py:36-64` |
| `DialogueAct` 8 nhãn + `DIALOGUE_POLICY` dạng bảng | `dialogue.py:89-146` |
| `output_guard` 5 kiểm tra + fallback `script_hint` | `output_guard.py:91-126` |
| Bước quét sót trước khi chốt | `session.CATCH_ALL_QUESTION` (`session.py:190`) |
| `RoleProfile` — định tuyến model theo vai trò | `provider_router.py` |
| Ý định người bệnh (dừng / hết triệu chứng / chửi tục) — THUẦN code | `user_intent.py` |
| Bộ đếm bất hợp tác 3 nấc | `user_intent.UncooperativeTracker`, `session.py` |
| Suy `false` cho ý bị bỏ qua trong lượt gộp — CHỈ tier O/H | `batching.py:240-265` |
| Overlay sửa trường của điều dưỡng (kể cả red flag) + audit từng trường | `hitl_review.py`, `schemas.NurseFieldEdit` |
| ADR-008: 3 thông điệp tĩnh + đồng hồ SLA 5 phút | `common_safety/emergency_message.py`, `sessions/red_flag_sla.py` |
| Hai output summary: `summary_text` (LLM) + `summary_json` phẳng -> ISBAR | `sessions/narrative.py`, `sessions/summary_render.py` |
| Nhánh red-flag thứ ba (model) + `red_flag_agreement` (OR, không trừ được) | `red_flag_branches.py` |
| Memory M1: khoá composite `(conversation_id, user_id)`, sống qua restart | `services/stores/conversation_store.py`, `models/case_record.ConversationRow` |
| Lane phi lâm sàng (lifestyle / meta) | `non_clinical.py` |
| Controller shadow mode — model đề xuất, không tác động gì | `controller_shadow.py` |
| Script đọc log -> bảng metric | `eval/scripts/experience_report.py` |

## 4. Công tắc ngắt — SÁU, không phải bốn

`flags.py` (tài liệu cũ ghi nhầm là 4). **Không cờ nào cho tầng an toàn** (`flags.py:12-15`):

| Công tắc | Tắt ⇒ rơi về |
| --- | --- |
| `ranking_enabled` | first-fit theo thứ tự khai báo |
| `synthesis_enabled` | phát nguyên văn `script_hint` |
| `retraction_confirmation_enabled` | đính chính rủi ro áp NGAY |
| `unset_operation_enabled` | bỏ qua `operation: "unset"` |
| `llm_controller_shadow_enabled` | **mặc định TẮT** — shadow mode, không tác động hành vi |
| `model_red_flag_branch_enabled` | **mặc định TẮT** — mất một cái THƯỚC, không mất cái lưới |

`text_safety_signals` (L0), `common_safety/rules`, `rule_engine`, `escalation_lock`, `output_guard`
(L5) và bước quét sót **không được phép tắt**.

## 5. Bốn ràng buộc không đọc ra được từ code

- **Router model chỉ được gọi ở 4 trigger:** lượt mở; `dialogue_act == new_symptom`; lượt vừa rồi chạm
  field chief complaint; `_fever_ruled_out` vừa bật.
- **Không hạ `fact_extractor` xuống SLM khi chưa có số eval chứng minh.** Sai ở đây là sai hồ sơ lâm sàng.
- **Tắt hoàn toàn SLM thì hệ thống vẫn phải chạy đúng** — router rơi về rule, synthesis rơi về `script_hint`.
- **Ngân sách một lượt: 2 lời gọi chính** (extract + render), cộng router ở đúng 4 trigger trên.

## 6. Baseline đang có (2026-08-17, `deepseek-chat`, `--mode api`)

| | Số | Ghi chú |
| --- | --- | --- |
| Latency mỗi lượt | p50 3.98s / p95 5.72s | `fact_extractor` 3.83s, `synthesis` 1.23s |
| Lời gọi mỗi lượt | 1.23–1.72 | |
| Emergency recall | **48.9% (22/45)** | Con số quan trọng nhất đang có |
| Red-flag recall | **0%** | Do lệch từ vựng mã — xem `B01` |
| Số lượt ca lành tính | **21** | Mục tiêu của `F01` |
| Tỉ lệ bị `output_guard` chặn | 0% (13 lượt, model thật) | |

`triage accuracy 33.3%` **không** đọc được như chỉ số chất lượng (chạy nhầm pipeline legacy).
