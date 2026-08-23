# F01 — Quy trình hỏi đáp: đúng thứ tự, ít lượt, tự sinh câu hỏi

> **Ưu tiên `***`** — việc lớn nhất của đợt này. Chủ trì: Agent Lead.
> Đọc `INVARIANTS.md` trước. Tiêu thụ `F02` (hợp đồng trạng thái trường).

---

## 0. Chốt luồng hội thoại mới

Agent hỏi-đáp chỉ còn một mục tiêu: thu đủ thông tin để **tư vấn mức xử trí/đường đi tiếp theo**, không đoán bệnh và không chẩn đoán.

Luồng chuẩn:

```text
Kiểm tra Cấp cứu (1)
-> Lấy Hồ sơ (2)
-> Lấy Triệu chứng chính (3, 4)
-> Quét Rủi ro/Tiền sử (5)
-> Hỏi quét sót triệu chứng khác
-> Xuất kết quả tư vấn
```

Luật hỏi:

1. Agent bắt intent ngay từ câu đầu: người dùng đang khai triệu chứng mới, bổ sung thông tin, sửa thông tin cũ, hỏi ngoài lâm sàng, hay muốn dừng.
2. Agent vừa hỏi vừa detect. Mỗi câu trả lời phải được trích xuất vào field tương ứng trước khi chọn câu hỏi tiếp theo.
3. Thông tin người dùng đã nói rồi thì không hỏi lại. Nếu câu trả lời đã có tuổi, giới, thời điểm khởi phát, mức độ đau, thuốc đã dùng, tiền sử hoặc dấu hiệu nguy hiểm thì field đó chuyển khỏi `unknown` và bị loại khỏi kế hoạch hỏi.
4. Mỗi cụm hỏi chỉ hỏi một lần. Nếu người dùng chỉ trả lời một ý trong cụm nhiều ý thì lưu ý đó; các ý đã hỏi mà không được nhắc tới giữ `unknown`, không hỏi lại để ép đủ checklist.
5. Không được đoán bệnh. Câu trả lời cuối chỉ nói mức ưu tiên, lý do dựa trên dấu hiệu đã khai, việc nên làm tiếp theo, và khi nào cần gọi cấp cứu/đi khám.
6. Trước khi xuất kết quả tư vấn, agent phải hỏi một câu quét sót:

> Ngoài những điều mình vừa hỏi, bạn còn thấy triệu chứng nào khác không?

Nếu người dùng trả lời không có triệu chứng khác, agent mới được chốt tư vấn. Nếu có triệu chứng mới, quay lại bước detect và chỉ hỏi thêm field còn thiếu của triệu chứng mới.

Năm câu trong quy trình là **khung intent**, không phải script cố định. Agent có thể gộp hoặc diễn đạt tự nhiên hơn, miễn là vẫn giữ thứ tự ưu tiên và không hỏi lại field đã biết.

---

## 1. Vấn đề

Ba vấn đề tách bạch. Gộp chúng lại là lý do các lần sửa trước không nhích được gì.

### 1.1. Thứ tự hỏi đang ngược đúng cái yêu cầu mô tả

```python
# src/services/engines/fever_protocol.py:40-46
STAGE_ORDER: tuple[str, ...] = ("0", "1", "2", "3A", "3B", "4", "5")
GATE_STAGES: tuple[str, str] = ("3A", "3B")
BUDGET_FLOOR_STAGE = "4"
```

| Stage | Nội dung |
| --- | --- |
| **0** | Xác định đối tượng — `Q0-01` tuổi/người khai, `Q0-02` giới |
| 1 | Phát hiện bênh |
| 2 | Đặc điểm bệnh (triệu chứng) |
| **3A** | **Quét cấp cứu** (11 cụm, tất cả `batch_negation=True`) — gate |
| 3B | Quét khám sớm / tự theo dõi (5 cụm) — gate |
| 4 | Quần thể nguy cơ |
| 5 | Thu thập phần còn lại |

Generic tương tự — `src/services/checklists/generic_checklist.py:57-58`:
`STAGE_ORDER = ("0","1","2","3","4")`, `GATE_STAGES = ("2","3")`.

Tức là hệ thống hỏi **tuổi và giới trước, quét cấp cứu mãi ở lượt thứ 3–4**. Yêu cầu là ngược lại:

```text
Kiểm tra Cấp cứu (1) -> Lấy Hồ sơ (2) -> Lấy Triệu chứng (3,4) -> Quét Rủi ro/Tiền sử (5) -> XUẤT KẾT QUẢ
```

Chính `registry.py:8` đã ghi lại đúng lời phàn nàn này: người nhắn *"tôi đau ngực từ sáng, đi vài bước
là hụt hơi"* bị hỏi *"bé hay người lớn, bao nhiêu tuổi"* đầu tiên.

> **Hai cơ chế đang bù, và vì sao chúng không đủ.** `registry.OPENING_CLUSTER` (`registry.py:135-154`)
> thu ~35 field gồm mọi red flag phổ quát từ tin nhắn tự do đầu tiên, và L0 `text_safety_signals`
> short-circuit trước mọi logic stage. Cả hai đều **thụ động** — chúng chỉ bắt được thứ người bệnh
> *tự nói ra*. Người bệnh nhắn "tôi bị sốt" thì không có gì để bắt, và câu hỏi chủ động đầu tiên vẫn
> là hỏi tuổi. Yêu cầu là hỏi **chủ động** một câu quét cấp cứu ngay lượt 1.

### 1.2. Quá nhiều lượt

Ca lành tính đi **21 lượt** (baseline 2026-08-17), trung vị **19.5** (`experience_report`, 2026-08-19).
Yêu cầu mô tả khoảng **5 câu**. Chênh 4 lần.

### 1.3. Câu hỏi cố định trong code

Mọi câu là một chuỗi literal Python. Không nạp từ YAML/DB:

```python
# src/services/checklists/fever_checklist.py:151-193
QuestionCluster("Q2-03", "2", ("antipyretic_taken", "antipyretic_drug", "antipyretic_response"),
    script_hint="Đã dùng thuốc hạ sốt chưa - thuốc gì, uống lúc nào, có đỡ không"),

# src/services/symptom_protocol/common_safety/clusters.py:44
QuestionCluster("Q3-09", stage, ("urine_output", "feeding_intake", "vomiting_severity"),
    batch_negation=True,
    script_hint="6 giờ qua có đi tiểu không, ăn uống được không, có nôn nhiều không"),
```

`intake_agent._generate_question` (`intake_agent.py:922-1020`) chỉ **diễn đạt lại đúng câu đó**:
`script_hint` đi vào prompt, LLM viết lại cho mượt, `output_guard` kiểm, hỏng thì rơi về nguyên văn
`script_hint`. Không gian sáng tạo bằng 0 về mặt *hỏi cái gì* và rất hẹp về *hỏi thế nào*.

---

## 2. Yêu cầu

1. Agent hỏi **theo quy trình 5 bước** ở §1.1, không fix cứng từng câu.
2. **Tự sinh câu hỏi** — vừa sáng tạo, vừa đúng mô tả. Không hỏi quá nhiều, không hỏi ngu.
3. **Thông tin user đã đưa thì không hỏi lại.**
4. Trường khởi tạo `Null`; agent tự điền `true/false/unknown` khi hỏi tới (xem `F02`).

Năm câu ví dụ chủ dự án đưa (**ví dụ, không phải script**):

1. "Người bệnh có đang bị khó thở dữ dội, đau tức ngực, co giật, hay chảy máu không cầm được không?"
2. "Người bệnh là nam hay nữ, và hiện bao nhiêu tuổi?"
3. "Triệu chứng hiện tại là gì và bắt đầu từ bao giờ?"
4. "Mức độ đau hiện tại (1–10) là bao nhiêu và ở nhà đã tự uống thuốc hay làm gì chưa?"
5. "Hiện có mắc bệnh mãn tính nào, đang mang thai, hoặc đang dùng thuốc/thực phẩm chức năng nào không?"

---

## 3. Thiết kế — ba thay đổi độc lập

Làm được riêng lẻ, theo thứ tự rủi ro tăng dần. Mỗi cái có giá trị riêng kể cả khi hai cái kia chưa làm.

### 3.1. Chèn stage `E` — quét cấp cứu phổ quát, trước stage `0`

```python
STAGE_ORDER = ("E", "0", "1", "2", "3A", "3B", "4", "5")   # fever
STAGE_ORDER = ("E", "0", "1", "2", "3", "4")               # generic
GATE_STAGES  = ("E", "3A", "3B")                           # E là gate thứ ba
```

Stage `E` chứa **đúng một** `ScreeningGroup` gom các dấu hiệu **không phụ thuộc tuổi/giới**, để một
chữ "không" đóng cả nhóm một cách tường minh:

> Trước khi hỏi kỹ, mình xác nhận nhanh mấy dấu hiệu cần xử lý gấp: khó thở dữ dội; đau tức ngực;
> co giật; chảy máu không cầm được. Bạn có dấu hiệu nào trong số đó không?

> ⚠️ **Ràng buộc chặn — đọc trước khi code.** Phần lớn cụm 3A có skip-rule theo tuổi/giới
> (`cluster_is_skipped`, `stage_machine.py:108-116`; `fever_protocol` có ~10 hàm skip-rule). Chuyển
> **nguyên** 3A lên trước stage 0 sẽ hỏi câu dành cho trẻ sơ sinh cho người lớn 40 tuổi, và đó đúng là
> loại "hỏi ngu" mà yêu cầu muốn bỏ. Vì thế: **chỉ tách phần phổ quát vào `E`; phần phụ thuộc tuổi ở
> nguyên 3A.** Tiêu chí chọn field cho `E`: skip-rule của nó không đọc `age` hay `sex`.

Tương thích với cơ chế đang có:

- `_gate_stages_cleared` (`stage_machine.py:283-297`) chặn mọi đường dừng sớm cho tới khi gate xong —
  thêm `E` vào `gate_stages` là mở rộng đúng cơ chế đó, không phải ngoại lệ mới.
- Field của `E` khai tier **M0**, nên `should_stop` không bao giờ bỏ qua được.

#### 🔥 Cạm bẫy lớn nhất: `gate_stages[0]` đang là "stage quét cấp cứu" ở BỐN chỗ

Thêm `"E"` vào **đầu** `GATE_STAGES` sẽ **âm thầm định nghĩa lại cả bốn**, và không chỗ nào báo lỗi:

| Nơi | Dùng `gate_stages[0]` để làm gì | Hỏng thế nào nếu `[0]` thành `"E"` |
| --- | --- | --- |
| `ranking.safety_field_keys` (`ranking.py:69-82`) | Suy ra tập field an toàn = field của mọi cụm thuộc stage đó | Tập an toàn co lại còn **mỗi field của `E`**; 11 cụm 3A **mất `WEIGHT_SAFETY = 10_000`** và tụt hạng |
| `batching.py:126` | `order.index(stage) < order.index(gate_stages[0])` — vùng được phép gộp là trước gate | `E` đứng đầu nên **không stage nào ở trước nó** ⇒ vùng gộp thành **rỗng**, tắt batching ở stage 0/1/2 — ngược hẳn §3.2 |
| `fever_protocol.py:657` | `common_screening.emergency_scan_groups(GATE_STAGES[0])` | Nhóm sàng lọc cấp cứu bị gắn vào `E` thay vì 3A |
| `generic_protocol.py:170` | như trên | như trên |

**Cách xử lý — chọn một, đừng vá từng chỗ:**

- **Khuyến nghị:** tách khái niệm ra khỏi vị trí. Thêm `SymptomProtocol.emergency_scan_stage` tường
  minh (vẫn trỏ `"3A"` / `"2"`), đổi cả bốn chỗ sang đọc thuộc tính đó, rồi mới thêm `"E"` vào
  `gate_stages`. Đây là chỗ `ranking.py:69-71` đã nói đúng nguyên tắc — "suy ra từ dữ liệu đã khai báo
  chứ không thêm một danh sách mới" — nhưng suy sai **chiều**: nó suy từ *vị trí trong tuple*, mà vị
  trí là thứ `F01` đang đổi.
- *Hoặc* đặt `GATE_STAGES = ("3A", "3B", "E")` (E ở cuối tuple, vẫn đứng đầu `STAGE_ORDER`). Rẻ hơn
  nhưng để lại một tuple mà thứ tự không còn nghĩa gì — sẽ bẫy người sau.

Kèm theo: annotation hiện là `GATE_STAGES: tuple[str, str]` (`fever_protocol.py:41`,
`generic_checklist.py:58`) — phải nới thành `tuple[str, ...]`.

### 3.2. Gộp bước hồ sơ thành một lượt

`Q0-01` (tuổi/người khai) và `Q0-02` (giới) đang là **hai** cluster nên tốn hai lượt. Gộp thành một
cụm, đúng ví dụ 2 của yêu cầu. Cơ chế đã sẵn — `batching.next_batch` (`batching.py`), trần **4 cụm /
tối đa 7 ý** mỗi lượt.

Áp cùng cách cho stage 4/5: fever có **13 field tier O/H tri-state ở Stage 4/5** hiện **không** nằm
trong vùng gộp — đây là chỗ cơ chế suy `false` (`batching.py:240-265`) lần đầu bắn thật, và là đòn bẩy
lớn nhất để kéo 21 lượt xuống.

### 3.3. Nới renderer: từ "diễn đạt lại một câu" sang "soạn câu từ danh sách field"

Đây là phần "vừa sáng tạo vừa đúng mô tả".

**Hôm nay:** `ResponsePlan` (`dialogue.py:155-178`) mang `act, cluster_id, missing_fields,
max_questions, acknowledge, ...`; prompt được dựng từ **`cluster.script_hint`** cộng nhãn field còn thiếu.

**Đổi thành:** prompt dựng từ **danh sách `(label, hint, tier)` của các field còn thiếu**;
`script_hint` **giữ nguyên** nhưng đổi vai — chỉ còn là fallback khi `output_guard` chặn hoặc
`flags.synthesis_enabled()` tắt (`intake_agent.py:1016-1020` đã sẵn đường này).

Ranh giới không nới:

| LLM được quyết | Code vẫn quyết |
| --- | --- |
| Cách nói, ghép mấy ý vào một câu, giọng điệu | **Hỏi field nào** (`stage_machine` + `ranking`) |
| Thứ tự các ý *trong cùng một lượt* | Số ý tối đa (`ResponsePlan.max_questions`) |
| Câu chuyển tiếp, câu ghi nhận | Dừng hay hỏi tiếp (`should_stop`) |

**Ngoại lệ đã chốt, KHÔNG "cải thiện":** câu sàng lọc gộp ghép **tĩnh** từ `ScreeningGroup.probe_hint`
(`common_safety/screening_groups.py:17-18`), không cho LLM diễn đạt lại — "LLM diễn đạt lại thì có thể
lược mất vài ý trong danh sách" (`models.py:52-56`). Với một danh sách dấu hiệu nguy hiểm, lược một ý
là mất một cơ hội phát hiện. **Stage `E` ở §3.1 là một `ScreeningGroup`, nên nó thuộc ngoại lệ này** —
câu quét cấp cứu là văn bản tĩnh.

### 3.4. "Không hỏi lại thứ user đã nói" — đã có, đừng viết mới

Ba cơ chế đang chạy:

| Cơ chế | Nơi |
| --- | --- |
| Thu field cơ hội từ mọi tin nhắn, kể cả ngoài cụm đang hỏi | `intake_agent.scan_opportunistic_fields:1149` |
| Không chọn lại cụm đã đủ dữ kiện | `stage_machine.cluster_needs_answer` |
| Chặn câu hỏi chạm field đã biết | `output_guard` check 4 `VIOLATION_ASKS_KNOWN_FIELD` (`:204-221`) |

Con số `repeat_question_rate = 0.32` **đã được điều tra và không phải bug**: chuỗi cụm của phiên tệ
nhất là `Q3-01` lặp 3 lần — đúng 1 lần hỏi + 2 retry, khớp `MAX_RETRIES_PER_CLUSTER = 2`. Chỉ số cũ gộp
hai khái niệm; đã tách thành `retry_rate` (hỏi lại ngay cùng cụm) và `repeat_question_rate` (quay lại
cụm sau khi đã đi qua cụm khác — **thứ này mới phải gần 0**).

Việc phải làm ở đây là **đọc đúng hai chỉ số đã tách**, không phải thêm cơ chế thứ tư. Nếu `retry_rate`
cao thì nguyên nhân là câu hỏi khó hiểu hoặc extractor không khớp — cả hai đều được §3.3 chạm tới.

---

## 4. Thay đổi cụ thể

| File | Sửa gì |
| --- | --- |
| `src/services/engines/fever_protocol.py:40-46` | Thêm `"E"` đầu `STAGE_ORDER`, thêm vào `GATE_STAGES` |
| `src/services/checklists/generic_checklist.py:57-58` | Như trên |
| `src/services/symptom_protocol/common_safety/screening_groups.py` | Thêm `ScreeningGroup` phổ quát cho stage `E` |
| `src/services/symptom_protocol/common_safety/clusters.py` | Tách các cụm cấp cứu phổ quát khỏi 3A sang `E` |
| `src/services/checklists/fever_checklist.py:151-193` | Gộp `Q0-01`+`Q0-02`; mở vùng gộp cho 13 field O/H Stage 4/5 |
| `src/services/symptom_protocol/dialogue.py:155-178` | `ResponsePlan` mang `(label, hint, tier)` field còn thiếu |
| `src/services/symptom_protocol/intake_agent.py:922-1020` | Dựng prompt từ danh sách field; `script_hint` thành fallback |

**Không được đụng:** `should_stop` 6 luật (`stage_machine.py:327-401`), `ranking` 5 trọng số
(`ranking.py:40-44`), `_gate_stages_cleared` (`:283-297`), `output_guard.check` 5 kiểm tra, và mọi
tầng ghi "KHÔNG model" ở `INVARIANTS.md`.

---

## 5. Test bắt buộc

1. **Property test hoán vị**: với mọi hoán vị thứ tự trả lời, phiên đóng bình thường thì
   `mandatory_unasked` **rỗng**. Đây là thứ duy nhất chặn được việc nới thứ tự làm mất field bắt buộc.
2. Stage `E` chạy **trước khi biết tuổi** mà **không** bắn skip-rule theo tuổi/giới.
3. Một chữ "không" ở stage `E` đóng đúng các field trong danh sách vừa đọc lên, không đóng field khác.
3b. **Ca chặn của cạm bẫy `gate_stages[0]`** — sau khi thêm `E`, khẳng định lại ba điều:
   `safety_field_keys()` vẫn chứa đủ field của 11 cụm 3A; vùng gộp của `batching` vẫn khác rỗng ở
   stage 0/1/2; `emergency_scan_groups` vẫn gắn vào 3A. Không có ca này thì lỗi đi qua CI im lặng.
4. Câu quét cấp cứu của `E` là **văn bản tĩnh** — test khẳng định không có đường nào để model sinh ra nó.
5. `flags.synthesis_enabled()` tắt thì vẫn chạy đúng, phát nguyên văn `script_hint`.
6. Renderer §3.3 không bao giờ hỏi field ngoài `ResponsePlan.missing_fields` (`output_guard` check 4).
7. Toàn bộ test hiện có vẫn xanh — **không giảm số lượng, không giảm độ phủ 5 nhóm triệu chứng**.

---

## 6. Tiêu chí chấp nhận

| Chỉ số | Ngưỡng | Đo bằng |
| --- | --- | --- |
| `mandatory_unasked` rỗng | **100% phiên, không ngoại lệ** — gate cứng | `experience_report.py` |
| Lượt tới câu hỏi cấp cứu đầu tiên | **1** (hiện: 3–4) | transcript |
| `median_turns` ca lành tính | **giảm** so với 19.5 | `experience_report.py` |
| `repeat_question_rate` (định nghĩa mới) | gần 0 | `experience_report.py` |
| `retry_rate` | giảm so với baseline | `experience_report.py` |
| Emergency recall | **không tệ hơn** 48.9% | eval, model thật |
| `abandonment_rate` | giảm | `experience_report.py` |

**Mọi ngưỡng phần trăm phải đi kèm mẫu số. Không có mẫu số thì không phải gate.**

Đọc `median_turns` **cùng lúc** với `mandatory_unasked`: rút ngắn hội thoại bằng cách bỏ hỏi field bắt
buộc là làm hỏng đúng thứ sản phẩm này tồn tại để làm (bất biến 8).
