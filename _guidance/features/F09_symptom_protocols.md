# F09 — Bốn protocol lâm sàng còn thiếu + pipeline hỏi đáp 5 bước

> **Nâng từ [`B01_backlog_clinical.md`](B01_backlog_clinical.md) §3 "Track PC".** Việc đó nằm ở
> backlog vì thiếu tài liệu lâm sàng và chưa có người chủ trì. Tài liệu grounding nay đã chốt
> (Schmitt-Thompson, NHS 111, SNNOOP10) nên nó chuyển sang track đang làm.
>
> Đọc [`INVARIANTS.md`](INVARIANTS.md) trước. File này KHÔNG chép lại bất biến nào.
>
> Chủ trì: **Agent Lead** (khuôn + code) · **Data Lead + review lâm sàng** (ngưỡng + mapping).

---

## 0. Chốt pipeline hỏi đáp

```
1. Kiểm tra Cấp cứu  →  2. Lấy Hồ sơ  →  3-4. Lấy Triệu chứng  →  5. Quét Rủi ro/Tiền sử  →  XUẤT KẾT QUẢ
```

**Tối đa 5 câu lõi mỗi nhóm** (câu 1 luôn là sàng lọc red-flag) + 1-2 câu mở rộng **có điều kiện**.
Decision tree, không phải checklist tuyến tính: nhánh đã đủ dữ kiện để phân loại thì các câu của
nhánh khác bị bỏ qua.

Bốn nhóm: **Đau ngực · Đau bụng · Khó thở · Đau đầu**. Ngoài 5 nhóm vẫn rơi về `general` như cũ.

---

## 1. Vấn đề

### 1.1. Bốn trong năm nhóm MVP không tồn tại

```python
# src/services/symptom_protocol/registry.py:23-26
PROTOCOL_REGISTRY: dict[str, SymptomProtocol] = {
    FEVER_PROTOCOL.name: FEVER_PROTOCOL,
    GENERIC_PROTOCOL.name: GENERIC_PROTOCOL,
}
```

CLAUDE.md khai phạm vi MVP là 5 nhóm. Bốn nhóm còn lại rơi hết vào `GENERIC_PROTOCOL`.

Đo trên registry đang chạy:

| | `fever` | `general` |
|---|---|---|
| field | 101 | 78 |
| cụm | 43 | 30 |
| rule | 42 | 31 |
| nhóm sàng lọc | 11 | 11 |

`general` **không rỗng** — nó có đủ bộ quét đỏ phổ quát của `common_safety`. Thứ nó thiếu là chiều
sâu đặc thù: trong 78 field **không field nào** mô tả tính chất đau ngực, kiểu khởi phát khó thở, hay
tiêu chí SNOOP của đau đầu. Người nhắn *"đau ngực từ sáng, đi vài bước là hụt hơi"* không bao giờ
được hỏi về cảm giác đè ép hay hướng lan.

### 1.2. `select_protocol` khoá vào fever

```python
# src/services/symptom_protocol/registry.py:48-49
if _has_fever_evidence(answers):
    return FEVER_PROTOCOL.name
```

Khoá ngay khi `temp_c >= 38`, chỉ nhả khi bị **phủ định tường minh**. Đo được: hồ sơ
`{temp_c: 39, breathing_difficulty: "severe"}` → `fever`. Người bệnh khai khó thở vẫn bị hỏi tiếp về
cách đo nhiệt độ và thuốc hạ sốt.

Với 6 protocol trong registry, một hàm chỉ biết một nhóm là chỗ hỏng đầu tiên.

### 1.3. `SWITCH_DETECTION_FIELDS` chỉ biết sốt

```python
# src/services/symptom_protocol/registry.py:138
SWITCH_DETECTION_FIELDS: tuple[str, ...] = ("fever_reported", "fever_status", "temp_c")
```

Docstring của chính hằng số này đã mô tả cơ chế hỏng: *"Một phiên đang chạy `general` không có
`temp_c` trong schema, nên câu 'bé sốt 39.2 độ' ở lượt thứ ba KHÔNG có chỗ nào để ghi."* Cùng cơ chế
đó sẽ lặp lại với 4 nhóm mới — phiên đang chạy `abdominal` không có chỗ ghi khi người bệnh khai đau
ngực ở lượt sau.

### 1.4. ⚠️ Đính chính ước lượng của B01 §3

B01 viết: *"`fever_protocol.py` là **696 dòng** và không phải bảng dữ liệu… Bốn protocol nữa là bốn
lần chừng đó logic lâm sàng viết tay."*

**Con số đó bi quan và làm sai ước lượng sprint.** Khuôn đúng để so không phải fever mà là
`generic_protocol.py` — **211 dòng**, vì mượn gần hết `common_safety/`. Fever dài vì nó mang nhánh
SXHD, thuốc hạ sốt, ngưỡng nhiệt độ theo tuổi, 43 cụm; bốn nhóm mới mỗi nhóm **5 cụm đặc thù**.

Phần công thật nằm ở **quyết ngưỡng lâm sàng**, không ở số dòng Python — vế này của B01 vẫn đúng
nguyên.

---

## 2. Yêu cầu

1. Bốn `SymptomProtocol` mới, đăng ký trong `PROTOCOL_REGISTRY`, phủ đúng bảng câu hỏi + bảng mapping
   mức ưu tiên của tài liệu grounding.
2. Hội thoại đi đúng pipeline 5 bước; câu hỏi **chủ động đầu tiên** luôn là quét cấp cứu, không phải
   hỏi tuổi.
3. Router chọn đúng nhóm khi lời khai chạm nhiều nhóm; `"sốt + khó thở"` → `breathing`.
   **Lời khai chạm nhiều nhóm thì lượt hỏi phải phủ được nhiều nhóm nhất có thể** — không hỏi một
   câu chỉ phục vụ một nhóm rồi bỏ các nhóm còn lại. Trần của yêu cầu này đo được, xem §3.10.
4. `general` **không đổi** hành vi.
5. Không sửa engine (`stage_machine`, `rule_engine`, `screening`, `batching`, `coverage`).

---

## 3. Thiết kế

### 3.1. Thêm một nhóm = 2 file, không đụng engine

```
src/services/checklists/<group>_checklist.py   FieldSpec đặc thù + QUESTION_CLUSTERS + STAGE_ORDER
src/services/engines/<group>_protocol.py       determine_route + budget + skip_rule + RULE_CATALOG
```

`generic_protocol.py` + `generic_checklist.py` là khuôn mẫu. `SymptomProtocol` là ranh giới duy nhất
giữa cơ chế và nội dung lâm sàng — engine chỉ gọi qua chữ ký chuẩn hoá.

### 3.2. Mapping pipeline → stage

| Bước pipeline | Stage | Nguồn cụm |
|---|---|---|
| 1. Kiểm tra Cấp cứu | `E` | `common_clusters.critical_scan_clusters("E")` |
| 2. Lấy Hồ sơ | `0` | `common_clusters.demographic_clusters("0")` |
| 3–4. Lấy Triệu chứng | `1` | **Cụm đặc thù nhóm** |
| " *(quét đỏ phổ quát)* | `2` | `common_clusters.emergency_scan_clusters("2")` |
| " *(quét khám sớm)* | `3` | `common_clusters.early_visit_scan_clusters("3")` |
| 5. Quét Rủi ro/Tiền sử | `4` | Cụm đặc thù + `risk_context_clusters` + `medication_clusters` |

```python
STAGE_ORDER = ("E", "0", "1", "2", "3", "4")
GATE_STAGES = ("E", "2", "3")
CRITICAL_SCAN_STAGE, EMERGENCY_SCAN_STAGE, EARLY_VISIT_SCAN_STAGE = "E", "2", "3"
```

Giống hệt generic — hai stage quét đỏ/khám sớm phải **tách rời** thì cơ chế *"chỉ quét early-visit khi
emergency-scan đã sạch"* mới có chỗ bám.

### 3.3. Câu 1 của mỗi nhóm KHÔNG thành cụm riêng

Câu red-flag số 1 của cả 4 nhóm đều đã nằm trong `critical_scan_clusters` ở stage `E`:

| Nhóm | Câu 1 tài liệu | Cụm đã có |
|---|---|---|
| Đau ngực | không nói hết câu / không tỉnh táo | `Q3-06` (`breathing_difficulty`) + `Q3-01` |
| Khó thở | không nói hết câu / tím tái | `Q3-06` (`breathing_difficulty`, `cyanosis`) |
| Đau bụng | lơ mơ, ngất, da lạnh vã mồ hôi | `Q3-01` + `Q3-08` |
| Đau đầu | **thunderclap** | ❗ chưa có → cụm mới `HA-01` đặt thẳng vào stage `E` |

Viết lại chúng thành cụm riêng của từng nhóm là dựng bản sao thứ hai của cùng một dấu hiệu — hai bản
sẽ lệch nhau ngay lần đầu ai đó sửa.

### 3.4. "5 câu lõi" đối chiếu với bộ quét phổ quát

Tài liệu ghi tối đa 5 câu; `common_safety` có ~20 cụm quét đỏ. Hai con số này **không mâu thuẫn** vì
`screening_groups` nén nhiều cụm thành một câu hỏi gộp. Lượt thật của một ca lành tính:

```
Luot 1  [E]  quet cap cuu pho quat            (1 cau gop, dong 3 cum)
Luot 2  [0]  tuoi / gioi / nguoi khai
Luot 3  [1]  cau 2 dac thu nhom
Luot 4  [1]  cau 3 dac thu nhom
Luot 5  [1]  cau 5 dac thu nhom
Luot 6  [2]  quet do pho quat con lai          (1 cau gop)
Luot 7  [3]  quet kham som                     (1 cau gop)
Luot 8  [4]  cau 4 dac thu: benh nen + nguy co
             -> XUAT KET QUA
```

Ước ~8-10 lượt. Vượt xa con số đó nghĩa là `BUDGET` hoặc `screening_groups` chưa nén được như thiết
kế — đo ở §5.5.

**Nguyên tắc 4 của CLAUDE.md thắng con số 5.** Bỏ bộ quét phổ quát để về đúng 5 lượt nghĩa là một ca
đau bụng đang co giật sẽ không được hỏi tới co giật.

### 3.5. Cụm chốt cuối — "còn gì nữa không"

Thêm vào cuối stage `4` của cả 4 nhóm:

```python
QuestionCluster("<G>-99", "4", ("other_symptoms",),
                script_hint="Ngoài những điều vừa kể, bạn còn thấy gì khác không")
```

`other_symptoms`: field tự do, tier `O`, khai ở `common_safety/fields.py` để 5 protocol dùng chung.
Tier `O` chứ không phải `M1`: nó không được phép chặn kết luận, và không được kéo `mandatory_unasked`
khác 0 ở mọi phiên.

### 3.6. Bốn nhóm — field và cụm

**[mới]** = phải viết `FieldSpec`; còn lại mượn `common_safety/fields.py`.

#### 3.6.1. `chest_pain`

| Câu | Cụm (stage) | Field |
|---|---|---|
| Q2 vị trí / tính chất / lan | `CP-01` (1) | `chest_pain`, **[mới]** `chest_pain_character` (`pressure`/`crushing`/`tightness`/`sharp`/`burning`/`other`), **[mới]** `chest_pain_radiation` (`shoulder`/`arm`/`jaw`/`back`/`none`) |
| Q3 onset / thời lượng | `CP-02` (1) | **[mới]** `chest_pain_duration_min` (số), **[mới]** `chest_pain_pattern` (`continuous`/`intermittent`), `complaint_onset_at` |
| Q5 triệu chứng kèm | `CP-03` (1) | `breathing_difficulty`, **[mới]** `diaphoresis`, `dizziness_on_standing`, `vomiting_severity`, **[mới]** `palpitations` |
| Q5 nguy cơ VTE | `CP-04` (4) | `recent_surgery_30d`, **[mới]** `immobility_or_long_travel` |
| Q4 tuổi / bệnh nền | `CP-05` (4) | `age_value`, `chronic_conditions`, **[mới]** `cardiac_risk_factors` (tự do: THA/ĐTĐ/mỡ máu/hút thuốc/tiền sử tim) |

> `common_rules` **đã có** `CHEST_PAIN_TEXT_MARKERS`, `_has_chest_pain_complaint`, `r_e_22` — dùng
> lại, không viết mới.

Ngưỡng quyết định chính: **đau > 5 phút** (`chest_pain_duration_min > 5`).

#### 3.6.2. `abdominal`

| Câu | Cụm | Field |
|---|---|---|
| Q2 vị trí / lan / mức độ | `AB-01` (1) | `abdominal_pain_location`, `abdominal_pain_severity`, **[mới]** `abdominal_pain_radiation` (`chest`/`back`/`none`) |
| Q3 onset / kiểu / thời lượng | `AB-02` (1) | **[mới]** `abdominal_pain_onset_mode` (`sudden`/`gradual`), **[mới]** `abdominal_pain_pattern`, **[mới]** `abdominal_pain_duration_hours` |
| Q4 XHTH / bí tiểu | `AB-03` (1) | `gi_bleeding`, **[mới]** `urinary_retention_gt_4h` |
| Q5 sốt / vàng da / chướng / tuổi | `AB-04` (4) | `temp_c`, `jaundice_new`, **[mới]** `abdominal_distension`, `age_value` |

Ngưỡng theo giờ: `>1h` (đau nặng), `>2h` (đau vừa liên tục). Ngưỡng sốt theo tuổi/bệnh nền:
`>39.4°C`, hoặc `>38.3°C` nếu `>60` tuổi, hoặc `>38.1°C` nếu ĐTĐ / suy giảm miễn dịch.

#### 3.6.3. `breathing`

| Câu | Cụm | Field |
|---|---|---|
| Q2 onset | `BR-01` (1) | **[mới]** `dyspnea_onset_mode` (`sudden`/`gradual`), `complaint_onset_at` |
| Q3 khó thở khi nghỉ | `BR-02` (1) | **[mới]** `dyspnea_at_rest`, `rapid_breathing` |
| Q4 triệu chứng kèm | `BR-03` (1) | `chest_pain`, `hemoptysis`, `temp_c`, **[mới]** `leg_swelling` |
| Q5 ảnh hưởng chức năng | `BR-04` (4) | **[mới]** `functional_impact` (`none`/`mild`/`marked`), `activity_vs_baseline` |

Ba câu NHS 111 map thẳng: Q1 → `breathing_difficulty=severe` (stage `E`), Q2 → `dyspnea_at_rest`,
Q3 → `functional_impact`.

#### 3.6.4. `headache`

| Câu | Cụm | Field | SNOOP |
|---|---|---|---|
| Q1 thunderclap | `HA-01` (**E**) | **[mới]** `thunderclap_onset` | **O**nset |
| Q2 thần kinh / màng não | `HA-02` (1) | `focal_neuro_deficit`, `new_confusion`, `seizure_occurred`, `neck_stiffness`, `temp_c` | **N** + **S** |
| Q4 tiến triển / khác thường | `HA-03` (1) | **[mới]** `headache_different_from_usual`, **[mới]** `headache_progressive`, **[mới]** `headache_severity`, `age_value` | **P** + **O**lder |
| Q5 tư thế / thị giác | `HA-04` (1) | **[mới]** `headache_positional`, **[mới]** `visual_disturbance` | SNNOOP10 |
| Q3 nguy cơ nền | `HA-05` (4) | `is_pregnant`, `immunocompromised`, `chronic_conditions`, **[mới]** `head_trauma_recent` | SNNOOP10 |

> `thunderclap_onset` và `headache_severity` **đã là tên field** ở `src/config.py:412`
> (`REQUIRED_FIELDS_BY_SYMPTOM_GROUP["headache"]`), kèm câu hỏi mẫu ở `config.py:433-434`. Giữ nguyên
> tên để không sinh hai từ vựng cho cùng một dữ kiện.

`HA-01` là cụm đặc thù **duy nhất** đặt ở stage `E`: thunderclap là red-flag khẩn nhất của nhóm và
tài liệu đặt nó là câu 1. Nó không có skip-rule đọc `age`/`sex` nên thoả điều kiện của stage `E`.

### 3.7. Rule và mã

Tiền tố riêng theo nhóm — đọc log/phiếu bàn giao biết ngay kết luận đến từ tài liệu nào:

| Nhóm | Tiền tố rule | `self_care_default_rule` |
|---|---|---|
| `chest_pain` | `R-CP-` | `R-S-03` |
| `abdominal` | `R-AB-` | `R-S-04` |
| `breathing` | `R-BR-` | `R-S-05` |
| `headache` | `R-HA-` | `R-S-06` |

(fever giữ `R-S-01`, generic giữ `R-S-02`.)

**Mỗi dòng trong bảng mapping mức ưu tiên của tài liệu thành đúng một rule.** Đây là điều kiện để §5.2
đối chiếu được 1-1.

Ghép catalog theo đúng khuôn generic — `r_e_21` (sản khoa) phải đứng **sau** mọi rule EMERGENCY khác,
kể cả rule đặc thù nhóm, vì nó đọc `matches_so_far`:

```python
RULE_CATALOG = (
    *common_rules.EMERGENCY_RULES,
    *GROUP_EMERGENCY_RULES,      # R-CP-01, R-CP-02, ...
    common_rules.r_e_21,
    *common_rules.EARLY_VISIT_RULES,
    *GROUP_EARLY_VISIT_RULES,
    common_rules.r_g_01,
)
```

Nhãn tiếng Việt của reason code mới thêm vào `common_rules.REASON_CODE_LABELS` (chỉ để hiển thị,
không tham gia quyết định nào).

### 3.8. Router — `select_protocol`

Bảng bằng chứng theo nhóm + **ưu tiên theo mức nguy hiểm** khi nhiều nhóm cùng khớp:

```
chest_pain  >  breathing  >  headache  >  abdominal  >  fever  >  general
```

Thứ tự này là **phán đoán lâm sàng, cần Data Lead ký duyệt** — nó quyết định nhóm nào bị bỏ khi lời
khai chạm hai nhóm.

Hai bất biến sẵn có giữ nguyên:
- chỉ chuyển khi có **căn cứ dương tính** rõ ràng;
- chỉ rời một protocol khi bị **phủ định tường minh** (`"false"`/`"none"`), không phải vì im lặng.

`SWITCH_DETECTION_FIELDS` mở rộng sang field mồi của cả 5 nhóm (xem §1.3).

Mỗi protocol mới phải có `temp_c` + `fever_reported` trong `fields_by_key` — cả 4 bảng mapping đều
dùng ngưỡng sốt. Lấy qua `_merged_fields()`.

### 3.9. Ranking — `relevance` mềm

`ranking.py` đã có `WEIGHT_RELEVANCE = 1_000` cho "người bệnh vừa nhắc tới field của cụm này". Chỗ
yếu: nó chỉ bật khi lượt trước trích được **đúng field key**. Người bệnh nói *"đau lan xuống tay
trái"* mà chưa field nào được ghi thì điểm relevance = 0.

Thêm một thành phần: khớp **từ khoá** giữa tin nhắn vừa nhận và `script_hint` của cụm ứng viên.
Trọng số **≤ `WEIGHT_RELEVANCE`** để không bao giờ lật được `safety` hay `overdue`.

> **Vì sao KHÔNG dùng vector DB để chọn câu hỏi.** Ý tưởng đã nêu: nén câu hỏi vào vector DB, lấy
> top-k rồi hỏi — để *tránh đẩy hết câu hỏi vào LLM rồi bắt LLM chọn*.
>
> Mục đích đó **đã là kiến trúc hiện tại, và chặt hơn**:
> - `stage_machine.next_cluster` + `ranking.py` chọn cụm bằng **code thuần** (`ranking.py` mở đầu
>   bằng đúng bất biến này: *"Model KHÔNG tham gia"*);
> - `_field_specs` (`intake_agent.py:137`) chỉ gửi schema của **đúng cụm đang hỏi**
>   (`cluster.fields + safety_keys`), không phải cả registry — `registry.py:134` ghi lý do: *"schema
>   càng rộng thì model càng có xu hướng điền bừa cho đủ"*;
> - LLM chỉ diễn đạt lại `script_hint` đã duyệt.
>
> Thay bộ chọn tất định này bằng top-k là đổi một thứ test được lấy một thứ **chưa đo bao giờ** —
> retrieval hiện chạy `underthesea.word_tokenize` trước khi embed và chưa có eval set nào. Khớp từ
> khoá lấy được phần lớn lợi ích mà vẫn tất định. Đo thấy còn thiếu thì mới tính tới embedding.

### 3.10. Khi lời khai chạm nhiều nhóm

Yêu cầu §2.3: lượt hỏi phải phủ được nhiều nhóm nhất có thể. **Đo trước khi thiết kế**, vì trần của
nó không do ta chọn.

#### Đo 1 — bốn nhóm gần như RỜI NHAU ở mức field

| Cặp | Field chung |
|---|---|
| `chest_pain` × `breathing` | **2** — `chest_pain`, `breathing_difficulty` |
| `chest_pain` × `abdominal` | 1 — `vomiting_severity` |
| `breathing` × `abdominal` | **0** |
| `breathing` × `headache` | **0** |
| `abdominal` × `headache` | **0** |
| `chest_pain` × `headache` | **0** |

**Không tồn tại câu hỏi nào vừa tiến được ca đau đầu vừa tiến được ca đau bụng.** Câu đặc thù của mỗi
nhóm, theo bản chất, chỉ phục vụ nhóm đó — đó là lý do nó đặc thù.

#### Đo 2 — cụm dùng chung phủ chéo rất ít

Trong 16 cụm của `critical_scan` + `emergency_scan` + `early_visit_scan`, chỉ **2 cụm** chạm ≥2 nhóm:

| Cụm | Stage | Nhóm phủ được |
|---|---|---|
| `Q3-06` | `E` | `breathing`, `chest_pain` |
| `Q3-09` | `2` | `abdominal`, `chest_pain` |

#### Kết luận thiết kế — ba điều, theo thứ tự

**(a) Câu phủ nhiều nhóm nhất ĐÃ tồn tại và đã được hỏi đầu tiên.** Quét cấp cứu phổ quát ở stage
`E` phủ **cả 5 nhóm** trong một lượt gộp, và nó là lượt 1 của mọi phiên (§3.4). Yêu cầu §2.3 ở phần
lớn phạm vi của nó **đã được kiến trúc đáp ứng sẵn** — không cần thêm cơ chế.

**(b) Chỗ phủ chéo thật sự chỉ có MỘT cặp — `chest_pain` × `breathing` — và phải khai thác triệt để.**
Đây đúng là cặp gắn nhau về lâm sàng: ACS và thuyên tắc phổi đều biểu hiện *đau ngực + khó thở*, và
**cả hai bảng mapping đều chốt EMERGENCY trên đúng tổ hợp đó**:

> - Đau ngực → Cấp cứu: *"đau kèm khó thở/tim đập nhanh-không đều"*
> - Khó thở → Cấp cứu: *"khó thở đột ngột + đau ngực/ho ra máu"*

Vì thế `CP-03` (đau ngực, triệu chứng kèm) và `BR-03` (khó thở, triệu chứng kèm) **dùng chung một
định nghĩa cụm** khai ở `common_safety/clusters.py`, không phải hai bản viết riêng:

```python
def chest_dyspnea_cluster(stage: str, cluster_id: str) -> QuestionCluster:
    """Cụm phục vụ ĐỒNG THỜI chest_pain và breathing — cặp phủ chéo duy nhất giữa 4 nhóm."""
    return QuestionCluster(
        cluster_id, stage, ("chest_pain", "breathing_difficulty", "hemoptysis", "diaphoresis", "palpitations"),
        script_hint="Có kèm đau ngực, khó thở, ho ra máu, vã mồ hôi, tim đập nhanh/không đều không",
    )
```

Một lượt, hai nhóm, và nó nạp thẳng dữ kiện cho rule EMERGENCY của **cả hai**.

**(c) Với nhóm RỜI nhau, mục tiêu đúng là PHÂN ĐỊNH, không phải phủ.** Không phủ chung được thì việc
đáng làm là tốn đúng **một** lượt để biết mình đang ở nhóm nào, rồi mới đi sâu — thay vì đoán rồi hỏi
sâu nhầm nhóm suốt cả phiên.

Dùng đúng cơ chế `ScreeningGroup` đã có (câu gộp ghép **tĩnh** từ `probe_hint`), thêm một probe phân
định phát ra **chỉ khi** router thấy ≥2 nhóm ứng viên:

```
"Bạn thấy khó chịu nhất ở đâu — tức nặng ngực, khó thở, đau bụng, hay đau đầu?"
```

Một lượt, thu hẹp router, và không câu nào bị hỏi thừa. Probe này **không đóng cụm nào** — nó chỉ
chọn nhánh, nên không đụng tới bảo đảm "chỉ đóng nhóm khi người bệnh đã nhìn thấy danh sách dấu hiệu".

#### KHÔNG thêm trọng số "coverage" vào `ranking.py`

Đã cân nhắc và **loại**: chỉ 2/16 cụm chạm ≥2 nhóm (Đo 2), mà một trong hai (`Q3-06`) vốn đã nằm ở
stage `E` và luôn được hỏi trước. Một trọng số gần như không bao giờ kích hoạt vẫn phải trả giá:
`ranking.py` cố ý giữ bảng điểm **đọc được** — *"một bảng mà mọi thứ đều có thể lật nhau thì không
giải thích được vì sao agent hỏi câu này"*. Ghi lại ở đây để lần sau không ai đề xuất lại mà không
biết nó đã bị loại vì lý do gì.

---

## 4. Thay đổi cụ thể

| File | Việc |
|---|---|
| `src/services/checklists/chest_pain_checklist.py` | **mới** |
| `src/services/checklists/abdominal_checklist.py` | **mới** |
| `src/services/checklists/breathing_checklist.py` | **mới** |
| `src/services/checklists/headache_checklist.py` | **mới** |
| `src/services/engines/chest_pain_protocol.py` | **mới** |
| `src/services/engines/abdominal_protocol.py` | **mới** |
| `src/services/engines/breathing_protocol.py` | **mới** |
| `src/services/engines/headache_protocol.py` | **mới** |
| `common_safety/fields.py` | thêm `other_symptoms` |
| `common_safety/clusters.py` | thêm `chest_dyspnea_cluster` — cụm phủ chéo `chest_pain`×`breathing` (§3.10b) |
| `common_safety/screening_groups.py` | thêm probe **phân định nhóm**, chỉ phát khi ≥2 nhóm ứng viên (§3.10c) |
| `common_safety/rules.py` | nhãn reason code cho `R-CP/AB/BR/HA-*` |
| `symptom_protocol/registry.py` | đăng ký 4 protocol · `select_protocol` trả **primary + nhóm ứng viên** · `SWITCH_DETECTION_FIELDS` |
| `symptom_protocol/ranking.py` | thành phần `relevance` từ khoá (**không** thêm trọng số coverage — §3.10) |

---

## 5. Ràng buộc không được vi phạm

1. **Không sửa engine** để chiều một nhóm cụ thể. Nhóm mới chỉ là dữ liệu cắm vào `SymptomProtocol`.
2. **Không rule nào hạ mức** đã đặt bởi rule khác — `rule_engine.evaluate` lấy `max` theo `LEVEL_RANK`.
3. **Câu sàng lọc gộp ghép TĨNH** từ `probe_hint`, không qua LLM diễn đạt lại: một nhóm chỉ được đóng
   khi người bệnh đã **thực sự nhìn thấy** danh sách dấu hiệu của nó.
4. Cụm mà tài liệu lâm sàng **cấm suy từ phủ định gộp** không được đưa vào `ScreeningGroup` nào.
5. `general` **không đổi** — nhóm ngoài 5 nhóm vẫn rơi vào đó.
6. `thunderclap_onset` / `headache_severity` giữ đúng tên đã có ở `config.py`.

---

## 6. Test bắt buộc

**6.1. Bất biến tự phủ.** [`test_protocol_field_coverage.py`](../../tests/test_services/test_protocol_field_coverage.py)
parameterize trên `registry.PROTOCOL_REGISTRY.items()` — đăng ký 4 protocol là 4 bộ test chạy luôn,
bắt ca "khai field M0/M1 mà quên viết cụm hỏi".

**6.2. Mapping mức ưu tiên.** Mỗi nhóm một file test; **mỗi dòng bảng mapping = một ca**: dựng
`answers` → `rule_engine.evaluate` → so `triage_level`. Đây là chỗ Data Lead đối chiếu tài liệu gốc
mà không phải đọc Python.

**6.3. Router.** `select_protocol({temp_c: 39, breathing_difficulty: "severe"})` → `breathing`, KHÔNG
phải `fever`. Thêm một ca cho mỗi cặp ưu tiên trong §3.8.

**6.3b. Phủ chéo và phân định (§3.10).** Ba bài:
- hồ sơ có `chest_pain=true` + `breathing_difficulty=severe` → cụm phủ chéo được hỏi **một** lần, và
  dữ kiện của nó khớp rule EMERGENCY của **cả** `chest_pain` lẫn `breathing`;
- hồ sơ chạm ≥2 nhóm RỜI nhau (vd đau bụng + đau đầu) → probe phân định được phát **đúng một lượt**,
  và nó **không đóng** cụm nào;
- hồ sơ chỉ chạm 1 nhóm → probe phân định **không** được phát (không tốn lượt thừa).

**6.4. Regression.** `python -m pytest tests/ -q --ignore=tests/test_graph_triage`.
Baseline **10 failed / 966 passed** — 10 lỗi này có sẵn từ trước, **không được tăng**.

**6.5. Chạy thật một phiên mỗi nhóm** qua `eval/scripts/simulated_patient.py`; đếm số lượt tới khi
chốt và đối chiếu ước tính ~8-10 lượt của §3.4.

---

## 7. Tiêu chí chấp nhận

- `PROTOCOL_REGISTRY` có **6** protocol; cả 4 nhóm mới qua sạch bộ test coverage tự phủ (6.1).
- Mọi dòng bảng mapping của tài liệu có đúng một test tương ứng, xanh (6.2).
- Kịch bản *"đau ngực từ sáng, đi vài bước là hụt hơi"* → chọn `chest_pain`, câu hỏi chủ động đầu
  tiên là quét cấp cứu (**không** phải hỏi tuổi), và không đi vào bộ câu hỏi sốt.
- Kịch bản *"sốt 39 + khó thở"* → chọn `breathing`.
- Kịch bản *"đau ngực kèm hụt hơi"* → cụm phủ chéo hỏi **một** lần, nạp dữ kiện cho rule của cả hai
  nhóm; không có lượt nào hỏi lại cùng dấu hiệu cho nhóm thứ hai.
- Kịch bản chạm 2 nhóm rời nhau → **đúng một** lượt phân định trước khi đi sâu.
- Regression không vượt 10 lỗi baseline.

---

## 8. Rủi ro đã biết

- **Ngưỡng + mapping + thứ tự ưu tiên router cần Data Lead ký duyệt.** Cùng lý do
  `generic_protocol.py` ghi trong docstring của nó: *"Đây là thay đổi NỘI DUNG lâm sàng, cần
  Thương/Đức Anh duyệt trước khi lên demo."*
- **Một phiên vẫn chỉ chạy MỘT protocol.** `rule_engine.evaluate(protocol, answers)` nhận đúng một
  protocol, nên *"sốt + khó thở"* sẽ đi `breathing` và bỏ nhánh sốt. Đa protocol cùng lúc
  (`active_protocols` + scheduler + `cross_protocol_rules`) là hạng mục riêng — đã ghi ở
  [`B02_backlog_architecture.md`](B02_backlog_architecture.md) §4 "Multi-protocol đồng thời (PC+)",
  không nằm trong F09.
- **Nhóm thứ 5 của MVP (chấn thương đầu nhẹ)** đi chung `headache` hay tách riêng: chưa chốt.
