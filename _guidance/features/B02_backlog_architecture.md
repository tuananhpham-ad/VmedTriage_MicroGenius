# B02 — Backlog kiến trúc & eval (NGOÀI phạm vi đợt này)

> **Không thuộc 6 việc ưu tiên hiện tại.** Ghi ở đây để không mất thông tin.
> Chủ trì: Agent Lead. Bản đầy đủ: `_guidance/archive/what_to_do_next_2026-08-22_full.md`.

---

## 1. Dọn kiến trúc (P5)

Không để hai runtime path cùng có vẻ authoritative. Ba quyết định:

- Số phận `src/tool/catalog/` + `triage_pipeline.py` — tái dụng registry/policy/audit, hoặc deprecate.
- Số phận `routers/fever_intake.py` + `sessions/fever_session.py` (đang mount tại `src/main.py:57`).
- Chuyển endpoint/UI còn lại sang `symptom_protocol.session.SessionStore`.

**Không xoá trước khi kiểm tra toàn bộ caller.**

Chặn `F06` §2.1 một phần: chừng nào còn hai đường ghi log song song thì số đo còn lẫn.

---

## 2. RAG vào luồng chuẩn

`pipeline/weaviate_cloud.py` đã có nhưng đang là nhánh tooling **ngoài** luồng chuẩn. Việc đầu tiên là
quyết định nó có vào luồng hay không, **trước** khi bàn ground cho tầng nào.

Phạm vi đã chốt, hẹp hơn đề xuất ban đầu. Ranh giới quyết bởi một câu hỏi: *nếu RAG trả về rác, hậu quả
là câu chữ xấu hay là câu hỏi lâm sàng sai?*

| Tầng | RAG được ground | Vì sao |
| --- | --- | --- |
| Protocol router | ✅ | Chọn sai thì rơi về `GENERIC_PROTOCOL`, không mất red flag |
| Model red-flag branch | ✅ | Chỉ được **thêm** phát hiện; nhánh rule vẫn chạy độc lập |
| Summarizer (NLP) | ✅ | Ground để diễn đạt đúng thuật ngữ, không để thêm dữ kiện |
| Diễn đạt câu hỏi | ✅ | Chỉ đổi **cách nói**, không đổi **hỏi cái gì** |
| **Chọn hỏi field nào** | ❌ | Đây là checklist lâm sàng — ADR-003, `output_guard.py:145-163` |

**RAG ground cách nói và cách nhận diện, không ground việc chọn câu hỏi lâm sàng.** Muốn thêm câu hỏi
mới thì thêm vào protocol (`B01` §3) và qua review lâm sàng — con đường đó chậm hơn RAG đúng ở chỗ nó
**nên** chậm.

Lưu ý giao thoa với `F01` §3.3: F01 nới *cách nói*, không nới *hỏi cái gì* — cùng một ranh giới.

---

## 3. Controller bằng Qwen3.5-4B

**Bước 1 (shadow mode) đã xong**, mặc định TẮT (`flags.llm_controller_shadow_enabled`). Bật lên là có
`controller_agreement_rate`.

Còn bước 2 (bật cho nhánh `non_clinical` trước) và bước 3 (bật toàn phần, chỉ khi
`controller_agreement_rate` ≥ 95% cho nhánh `clinical` và không ca an toàn nào đỏ).

Ranh giới không nới — controller **không được quyết** bốn thứ:

| Không được quyết | Vẫn ở đâu |
| --- | --- |
| Cụm câu hỏi lâm sàng tiếp theo | `ranking.py` + `stage_machine.select_cluster` |
| Dừng hay hỏi tiếp | `should_stop` — controller chỉ *báo* `user_intent.stop` |
| Mức ưu tiên | `rule_engine` |
| Red flag | L0 + `common_safety/rules.py`, chạy độc lập với controller |

`next_action` **không có giá trị `stop`**. Timeout cứng **300ms**. Toàn bộ test hiện có phải xanh khi
tắt cờ.

**Ba dữ kiện cần trước khi quyết dựng GPU hay dùng endpoint bên thứ ba:** `skippable_turn_ratio`, hoá
đơn Gemini thật, và ai vận hành GPU service sau khi sprint kết thúc. `F07` §2.2 cho dữ kiện thứ nhất.

---

## 4. Multi-protocol đồng thời (PC+)

`registry.select_protocol` trả **một** tên protocol cho một phiên; ca thật "đau bụng kèm sốt 39" phải
chọn một. **Xếp sau `B01` §3** — merge hai protocol chỉ có nghĩa khi có hơn một protocol thật để merge.

Bốn câu hỏi phải trả lời **trước khi viết dòng code nào**:

1. Field trùng tên khác nghĩa giữa hai protocol merge thế nào?
2. Tier / budget / luật triage của protocol nào thắng khi mâu thuẫn?
3. Đổi `primary` giữa phiên thì các cụm đã hỏi map sang protocol mới ra sao?
4. **`CoverageLedger.reset()` hiện xoá sạch nợ hoãn khi đổi protocol** vì mã cụm dùng chung
   (`coverage.py:80-86`). Multi-protocol phá giả định này — hoặc namespace mã cụm theo protocol, hoặc
   bỏ `reset()`. Đây là câu tốn công nhất.

---

## 5. Metric và acceptance gate

Đo **tách theo vai trò**, không gộp một con số: controller, `symptom_group_router`, `fact_extractor`,
reducer/rule engine, synthesis, red flag hai nhánh, controller model, trải nghiệm + độ phủ.

### Gate cứng, chạy trong CI (không gọi model thật)

- 100% nhóm test an toàn, gồm ca JSON hỏng/timeout, negation text signal, tắt SLM, invalid state;
- 100% property test hoán vị thứ tự trả lời — thứ duy nhất chặn được việc nới thứ tự hỏi làm mất field
  bắt buộc (**`F01` phụ thuộc trực tiếp vào gate này**);
- không regression các test hiện có.

### Gate mềm, chạy tay theo release (model thật, 120 golden case)

- red-flag recall 100% — **kèm cỡ mẫu** (chặn bởi `B01` §1);
- correction/retraction accuracy ≥ 98% (tối thiểu 50 ca có nhãn);
- hallucinated negative rate **0%** trên tập safety (`F06` §3);
- `symptom_group_router` accuracy ≥ 98%;
- `mandatory_unasked` rỗng ở **100%** phiên — không ngoại lệ;
- latency p95 không tệ hơn baseline;
- `median_turns` không tăng; `repeat_question_rate` giảm;
- reviewer chấm "rõ, đúng ngữ cảnh, không lặp máy móc" ≥ 90% transcript;
- reviewer chấm "agent có phản ứng theo điều tôi vừa nói" ≥ 90% transcript — **không thay thế được bằng
  chỉ số tự động nào**.

**Mọi ngưỡng phần trăm phải đi kèm mẫu số. Không có mẫu số thì không phải gate.**

---

## 6. Việc còn nợ vì cần API key và chi phí model thật

Hạ tầng đã sẵn, chạy eval là ra bảng. Riêng việc hạ `synthesis` xuống SLM hiện **không đáng làm**: lãi
tối đa ~1.2s/lượt, trong khi phần chiếm thời gian là `fact_extractor` 3.83s mà thứ đó **đã chốt không
hạ** (`INVARIANTS.md` §5).
