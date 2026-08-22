# Kế hoạch V2 — Medical Conversation Agent

> **Phạm vi của bản này:** chỉ mô tả **Input → Actions của Agent → Output**.  
> Phần **triage RED/YELLOW/GREEN sau summary**, so sánh giữa các model/rule, recommendation cuối cùng và các xử lý downstream sẽ do module khác đảm nhiệm.

---

## 1. Mục tiêu của Agent

Medical Conversation Agent nhận một cuộc hội thoại nhiều lượt với người dùng và có nhiệm vụ:

1. Detect **đúng và đủ thông tin triệu chứng** mà user cung cấp.
2. Chủ động hỏi thêm để thu thập các thông tin y tế cần thiết.
3. Không bị hard-code vào một bệnh cụ thể như `fever`.
4. Theo dõi trạng thái các trường thông tin xuyên suốt conversation.
5. Biết **khi nào tiếp tục hỏi và khi nào nên dừng để tạo summary**.
6. Sau khi conversation kết thúc, sinh ra:
   - **Natural-language summary**.
   - **Structured nurse summary JSON**.
7. Lưu conversation summary để phục vụ long-term memory sau này.
8. Agent **không quyết định triage cuối cùng**.

---

## 2. Tổng quan luồng

```text
Multi-turn User Chat
        │
        ▼
┌─────────────────────┐
│ 1. Protocol Router  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 2. Entity / Symptom │
│    Extraction       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 3. Update State     │
│    True/False/...   │
└──────────┬──────────┘
           │
           ├───────────────┐
           ▼               ▼
┌────────────────┐   ┌─────────────────┐
│ Red-flag       │   │ Coverage /      │
│ Detection      │   │ Missing Fields  │
└───────┬────────┘   └────────┬────────┘
        │                     │
        └──────────┬──────────┘
                   ▼
          ┌─────────────────┐
          │ Question Planner│
          └────────┬────────┘
                   ▼
          ┌─────────────────┐
          │ LLM Response    │
          └────────┬────────┘
                   ▼
          ┌─────────────────┐
          │ Continue / Stop │
          │ Decision Agent  │
          └───────┬─────────┘
                  │
          ┌───────┴────────┐
          │                │
       CONTINUE           STOP
          │                │
          └── next turn    ▼
                    ┌──────────────┐
                    │ Summarizer   │
                    └──────┬───────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
      NLP Summary                Nurse JSON
```

---

## 3. Input

### 3.1. Input chính

```text
Multi-turn conversation
```

Ví dụ:

```text
User:
Tôi đau bụng từ sáng.

Agent:
Bạn đau ở vị trí nào của bụng?

User:
Bên phải, hơi buồn nôn.

Agent:
Cơn đau có tăng dần không? Bạn có nôn hoặc sốt không?

User:
Đau tăng lên, không nôn, không biết có sốt không.
```

### 3.2. Metadata

Mỗi conversation cần ít nhất:

```json
{
  "user_id": "user_123",
  "conversation_id": "2026-08-18T23:30:21",
  "created_at": "2026-08-18T23:30:21"
}
```

Composite key:

```text
user_id + conversation_id
```

Ví dụ:

```text
user_123#2026-08-18T23:30:21
```

Mỗi conversation được coi là một collection/state độc lập.

---

## 4. Conversation State

Đây nên là thành phần trung tâm của Agent.

Ban đầu các trường có trạng thái:

```text
NULL
```

Ý nghĩa:

```text
NULL = chưa hỏi / chưa có thông tin
```

Sau khi hỏi:

| State | Ý nghĩa |
|---|---|
| `NULL` | Chưa hỏi/chưa xử lý |
| `TRUE` | User xác nhận có |
| `FALSE` | User xác nhận không có |
| `UNKNOWN` | Đã hỏi nhưng user không biết / từ chối / câu trả lời không đủ để xác định |

Ví dụ:

```json
{
  "fever": null,
  "vomiting": null,
  "nausea": null,
  "diarrhea": null,
  "shortness_of_breath": null
}
```

User:

> Tôi hơi buồn nôn nhưng không nôn.

Sau extraction:

```json
{
  "fever": null,
  "vomiting": false,
  "nausea": true,
  "diarrhea": null,
  "shortness_of_breath": null
}
```

Agent tiếp tục ưu tiên các field `NULL`.

---

## 5. Không cố fill NULL của toàn bộ hệ thống

Không nên có:

```text
500 symptom fields
→ cố gắng hỏi cho hết 500 NULL
```

Điều đó không khả thi.

Thay vào đó:

```text
Global Schema
     ↓
Protocol Router
     ↓
Active Field Set
```

Ví dụ user nói:

> Tôi đau bụng bên phải.

Không cần hỏi ngay:

```text
đau tai?
đau lưng?
ngứa da?
đau đầu?
đau đầu gối?
...
```

Router có thể activate:

```text
General fields
+
Abdominal fields
+
Safety/red-flag fields
```

Ví dụ:

```text
Active fields
├── onset
├── duration
├── location
├── severity
├── nausea
├── vomiting
├── diarrhea
├── fever
├── urinary symptoms
├── medication
├── relevant history
└── abdominal red flags
```

Agent chỉ cố gắng giảm `NULL` trong **Active Field Set**, không phải toàn bộ database triệu chứng.

---

## 6. Action 1 — Protocol Router

System hiện tại có:

```text
General Protocol
Fever Protocol
```

nhưng sau này có thể mở rộng:

```text
General
Fever
Stomach / Abdominal
Headache
Back pain
Skin
Respiratory
Medication
Sexual health
Lifestyle
Chitchat
Summarize
Search DB
...
```

Có thể sử dụng model nhỏ như:

```text
Qwen/Qwen3.5-4B
```

để route.

Ví dụ:

```text
"Tôi bị sốt từ tối qua"
→ General + Fever
```

```text
"Tôi đau bụng bên phải"
→ General + Abdominal
```

```text
"Tôi bị ngứa chân"
→ General + Skin
```

```text
"Tôi bị ê mông"
→ General / Musculoskeletal
```

```text
"Tôi nghi mình bị giang mai"
→ General + Sexual Health
```

```text
"Tôi muốn uống bia tối nay"
→ Lifestyle / Medication Safety
```

```text
"Tôi muốn ra ngoài chạy bộ"
→ Lifestyle / General
```

Router cũng không nhất thiết chỉ trả về **một protocol**.

Có thể:

```json
{
  "primary": "abdominal",
  "secondary": [
    "general",
    "medication"
  ]
}
```

---

## 7. Fallback Protocol

Đây là cách giải quyết các triệu chứng hệ thống chưa hỗ trợ riêng.

Ví dụ chưa có:

```text
Buttock pain protocol
```

không có nghĩa Agent không xử lý được.

Flow:

```text
Không tìm thấy protocol chuyên biệt
              ↓
       General Protocol
              +
      RAG medical context
              ↓
       Dynamic questions
```

Nhờ đó hệ thống vẫn xử lý được long-tail cases.

---

## 8. Action 2 — Entity & Symptom Detection

Sau **mỗi user turn**, Agent chạy extraction.

Ví dụ:

> Tôi đau bụng bên phải từ sáng, hơi buồn nôn nhưng chưa nôn.

Output:

```json
{
  "symptoms": {
    "abdominal_pain": true,
    "nausea": true,
    "vomiting": false
  },
  "attributes": {
    "pain_location": "right abdomen",
    "onset": "this morning"
  }
}
```

Sau đó merge vào Conversation State.

---

## 9. Không chỉ detect True

Agent cần detect cả:

```text
Positive
Negative
Unknown
```

Ví dụ:

### Positive

> Tôi có sốt.

```text
fever = TRUE
```

### Negative

> Tôi không sốt.

```text
fever = FALSE
```

### Unknown

> Tôi không biết có sốt không vì chưa đo.

```text
fever = UNKNOWN
```

### Chưa từng hỏi

```text
fever = NULL
```

Như vậy:

```text
NULL ≠ UNKNOWN
```

Đây là distinction rất cần thiết.

---

## 10. User sửa thông tin cũ

Conversation State phải hỗ trợ correction.

Ví dụ:

```text
Turn 3:
Tôi đau bên phải.
```

State:

```text
location = right
```

Turn 6:

> À tôi nói nhầm, là bên trái.

State mới:

```text
location = left
```

Natural summary chỉ nên dùng thông tin mới nhất:

> Đau bụng bên trái.

Không nên:

> Đau bụng bên phải và bên trái.

Có thể giữ audit log:

```json
{
  "field": "pain_location",
  "current_value": "left",
  "history": [
    {
      "value": "right",
      "turn": 3
    },
    {
      "value": "left",
      "turn": 6,
      "type": "correction"
    }
  ]
}
```

---

## 11. Action 3 — Red-flag Detection

Flow:

```text
Entity Extraction
       ↓
Symptom State
       ↓
Red-flag Detection
```

Nhưng:

```text
Red Flag
   ≠
Triage Decision
```

Red flag chỉ tạo **evidence**.

Ví dụ:

```json
{
  "red_flag_candidates": [
    {
      "flag": "progressively_worsening_abdominal_pain",
      "evidence": "Người dùng nói đau tăng dần từ sáng."
    }
  ]
}
```

Không làm:

```text
red_flag == true
→ TRIAGE RED
```

ngay trong Agent này.

Triage được chuyển xuống downstream.

---

## 12. Guardrails thay cho rule cứng

Không nên xây toàn bộ Agent bằng:

```python
if fever:
    ...
if chest_pain:
    ...
if ...
```

Rule nên tập trung vào **guardrails**.

Ví dụ:

```text
Safety guardrail
Critical information guardrail
Unsupported recommendation guardrail
Conversation stop guardrail
Output validation guardrail
```

LLM có quyền reasoning linh hoạt trong phạm vi guardrail.

---

## 13. RAG

RAG cung cấp grounding cho:

```text
Protocol Router
Question Planner
Red-flag Detector
LLM Response
Summarizer
```

Có thể hình dung:

```text
User
  ↓
Router
  ↓
Retrieve
  │
  ├── General Protocol
  ├── Fever Protocol
  ├── Abdominal Protocol
  ├── Safety Guidance
  └── ...
          ↓
      Agent Context
```

RAG không cần trực tiếp quyết định triage.

---

## 14. Action 4 — Coverage Checker

Coverage Checker kiểm tra:

```text
Active Fields
vs.
Current State
```

Ví dụ:

```json
{
  "abdominal_pain": true,
  "location": "right abdomen",
  "onset": "this morning",
  "severity": null,
  "vomiting": false,
  "fever": null,
  "urinary_symptom": null
}
```

Coverage Checker thấy:

```text
Need:
- severity
- fever
- urinary symptoms
```

Sau đó đưa cho Question Planner.

---

## 15. Action 5 — Question Planner

Question Planner quyết định **hỏi gì tiếp theo**, thay vì để LLM tự nghĩ hoàn toàn.

Input:

```text
Conversation State
+
Active Protocol
+
NULL fields
+
Red flags
+
Previous questions
+
RAG context
```

Output:

```json
{
  "next_fields": [
    "severity",
    "fever",
    "urinary_symptoms"
  ]
}
```

Sau đó LLM chuyển thành ngôn ngữ tự nhiên.

---

## 16. Hỏi nhiều field trong một lượt

Đây là cách chính để giảm conversation length.

Không nên:

```text
Agent: Bạn có sốt không?
User: Không.

Agent: Bạn có nôn không?
User: Không.

Agent: Bạn có tiêu chảy không?
User: Không.
```

Có thể:

> Ngoài đau bụng, bạn giúp mình kiểm tra thêm 3 điều nhé:
>
> - Bạn có sốt không?
> - Có buồn nôn hoặc nôn không?
> - Có tiêu chảy không?

User:

> Buồn nôn thôi, còn hai cái kia không.

Extractor:

```json
{
  "fever": false,
  "nausea": true,
  "vomiting": false,
  "diarrhea": false
}
```

Một turn fill được nhiều field.

---

## 17. Nhưng không hỏi một đống 20 câu

Không nên tối ưu thành:

```text
1 message
→ 20 questions
```

vì user có thể:

- bỏ sót;
- trả lời không theo thứ tự;
- mất kiên nhẫn;
- trả lời "không" nhưng không rõ áp dụng cho câu nào.

Nên **batch theo nhóm**.

Ví dụ:

```text
Turn 1:
2–4 câu về triệu chứng chính

Turn 2:
2–4 câu về triệu chứng đi kèm

Turn 3:
2–4 câu về tiền sử/thuốc nếu cần
```

Tức là:

> **Batch nhỏ, không hỏi từng field, cũng không dump toàn bộ questionnaire.**

---

## 18. Cơ chế ưu tiên câu hỏi

Không phải mọi `NULL` đều quan trọng như nhau.

Nên có:

```text
Priority 1 — Safety / red flag
Priority 2 — Required clinical information
Priority 3 — Protocol-specific information
Priority 4 — Useful but optional
```

Question Planner hỏi:

```text
P1 → P2 → P3 → P4
```

Khi conversation gần kết thúc, có thể bỏ P4.

---

## 19. Memory

### 19.1. Short-term memory

Trong một conversation cần nhớ toàn bộ thông tin trước đó.

Có ba cách.

#### Cách 1 — Full context

```text
Entire conversation
→ LLM context
```

Ưu:

- dễ implement;
- hiểu conversation tốt.

Nhược:

- càng chat càng nhiều token.

#### Cách 2 — Structured fields

```json
{
  "fever": false,
  "pain": true,
  "pain_location": "right abdomen"
}
```

Ưu:

- rất gọn;
- dễ query;
- rất phù hợp symptom extraction.

Nhược:

- mất nuance của conversation.

#### Cách 3 — Hybrid — nên dùng

```text
Structured State
+
Old Conversation Summary
+
Last N Raw Turns
```

Ví dụ:

```text
Medical State
      +
Summary turn 1–15
      +
Raw turn 16–20
```

Đây là thiết kế phù hợp nhất cho trường hợp:

> User nói vu vơ một lúc rồi quay lại hỏi về vấn đề trước.

---

## 20. Summarizer Agent cho context dài

Khi token/context vượt threshold:

```text
Old messages
     ↓
Context Summarizer
     ↓
Compact Memory
```

Nhưng **structured medical state vẫn giữ nguyên**.

Không:

```text
Summary
→ overwrite toàn bộ state
```

Mà:

```text
Structured State
+
Compressed Conversation
+
Recent Turns
```

---

## 21. Long-term memory

Kết thúc conversation:

```text
Conversation
     ↓
Nurse JSON
     ↓
Database
```

DB có thể lưu:

```text
user_id
conversation_id
created_at
raw_conversation
natural_summary
nurse_summary_json
```

---

## 22. Conversation mới

Khi user mở conversation mới:

```text
user_id
  ↓
DB
  ↓
Get last 3 conversation summaries
  ↓
History Summarizer
  ↓
Context
```

Ví dụ agent có thể hỏi:

> Lần trước bạn có nói về tình trạng đau bụng. Hiện tại đã đỡ hơn chưa?

Hoặc:

> Lần trước bạn được khuyên theo dõi thêm tình trạng này. Hiện giờ có thay đổi gì không?

**Không tự động merge triệu chứng cũ thành triệu chứng hiện tại.**

Ví dụ:

```text
previous_conversation:
fever = true
```

Không được:

```text
new_conversation:
fever = true
```

mà phải coi nó là:

```text
history:
previous fever = true

current fever = NULL
```

---

## 23. Vấn đề quan trọng nhất: Khi nào dừng để Summary?

Không dùng điều kiện:

```text
ALL fields != NULL
```

Bởi vì với hệ thống general medical agent:

```text
số field tiềm năng ≈ rất lớn
```

và nhiều triệu chứng không thể biết trước từ đầu.

Do đó **Stop Decision phải là một quyết định đa điều kiện**.

---

## 24. Đề xuất: Stop Policy 3 tầng

Nên chia thành:

```text
1. Hard Stop
2. Clinical Completion Stop
3. Soft Turn Limit
```

---

## 25. Tầng 1 — Hard Stop theo ý định User

Dừng ngay và summary khi user thể hiện rõ:

### User yêu cầu summary

> Tóm tắt cho tôi đi.

```text
STOP
```

### User muốn kết thúc

> Thôi tôi không muốn trả lời nữa.

```text
STOP
```

### User xác nhận không còn thông tin

> Không còn triệu chứng gì khác.

```text
STOP candidate
```

### User từ chối tiếp tục

> Tôi không muốn trả lời các câu này.

```text
STOP
```

### User kết thúc conversation

> Cảm ơn, vậy thôi.

```text
STOP
```

---

## 26. Tầng 2 — Clinical Completion Stop

Đây mới là điều kiện chính.

Không cần tất cả field được fill.

Agent hỏi:

> **Tôi đã có đủ thông tin cần thiết để tạo một summary hữu ích chưa?**

Có thể đánh giá bằng 4 yếu tố:

```text
1. Chief complaint captured?
2. Critical / safety fields sufficiently checked?
3. Core protocol fields sufficiently covered?
4. Asking another question có đem lại nhiều thông tin quan trọng không?
```

Ví dụ:

```text
Chief complaint       ✓
Onset                 ✓
Severity              ✓
Major associated sx   ✓
Critical red flags    ✓
Relevant history      ✓
Medication            UNKNOWN
Minor optional field  NULL
```

Không cần cố hỏi optional field cuối cùng.

```text
→ STOP
```

---

## 27. Coverage Threshold thay vì Full Coverage

Ví dụ mỗi field có trọng số:

```text
Critical field = 3
Important field = 2
Optional field = 1
```

Coverage:

```text
known_weight
----------------
total_active_weight
```

Ví dụ:

```text
Clinical coverage = 87%
```

Có thể quy định:

```text
Critical fields covered
AND
coverage >= threshold
→ eligible for summary
```

Không nhất thiết threshold phải cố định ngay từ đầu; có thể tune qua evaluation dataset.

---

## 28. Information Gain

Một cơ chế tốt hơn nữa:

Question Planner dự đoán:

> Câu hỏi tiếp theo còn giúp ích nhiều không?

Ví dụ sau 5 turn:

```text
Next question:
"Bạn có bị khô miệng không?"
```

nhưng field này:

- priority thấp;
- không ảnh hưởng summary nhiều;
- conversation đã đủ dữ liệu.

```text
Expected information gain = LOW
```

→ Summary.

Tư tưởng:

```text
continue asking
IF
expected clinical value > conversation cost
```

---

## 29. User nói "không còn triệu chứng"

Đây nên là một signal mạnh nhưng **không nhất thiết absolute stop**.

Ví dụ:

```text
Agent:
Ngoài đau ngực ra bạn còn triệu chứng nào khác không?

User:
Không.
```

Nhưng Agent chưa hỏi:

```text
đau có lan xuống tay/hàm?
khó thở?
ngất?
```

thì vẫn cần hỏi **critical follow-up**.

Flow:

```text
User: "Không còn triệu chứng."
          ↓
Stop intent detected
          ↓
Critical fields còn NULL?
        /       \
      YES        NO
       │          │
 ask critical    STOP
 questions
```

---

## 30. User từ chối trả lời

Ví dụ:

> Tôi không muốn nói về thuốc tôi đang uống.

Set:

```text
medication = UNKNOWN
```

Không tiếp tục hỏi medication lặp đi lặp lại.

Nếu không còn critical field khác:

```text
→ summary
```

Summary có thể nói:

> Người dùng không cung cấp thông tin về thuốc đang sử dụng.

Hoặc Nurse JSON có thể giữ metadata nội bộ:

```json
{
  "medication_status": "unknown"
}
```

Nếu yêu cầu cuối cùng là **không hiển thị Unknown**, UI có thể không render field đó.

---

## 31. Off-topic / chửi tục

Không nên:

```text
user chửi
→ lập tức summary
```

Nên detect:

```text
off_topic_count
uncooperative_count
clinical_information_gain
```

Ví dụ:

```text
2–3 lượt liên tiếp
+
không có thông tin clinical mới
+
không trả lời câu hỏi
```

→ Agent có thể hỏi:

> Nếu bạn không muốn bổ sung thêm thông tin, mình có thể tổng hợp những gì đã có. Bạn muốn dừng tại đây không?

Nếu tiếp tục không hợp tác:

```text
STOP
→ summary available information
```

---

## 32. Có nên định nghĩa số lượt hội thoại tối đa?

## Có — nhưng chỉ nên dùng như **soft limit**, không phải hard limit.

Không nên:

```text
turn == 8
→ luôn summary
```

Vì:

```text
Turn 8
User vừa nói một triệu chứng nguy hiểm mới
```

mà hệ thống lập tức summary thì không hợp lý.

---

## 33. Soft Turn Budget

Có thể đặt ví dụ:

```text
Target:
4–6 question turns

Soft limit:
6 turns

Extended limit:
8–10 turns khi vẫn còn thông tin quan trọng
```

Không cần chốt con số này ngay; sau này tune bằng data.

Logic:

```text
turn < soft_limit
        ↓
normal interview

turn >= soft_limit
        ↓
Stop Agent kiểm tra:
"còn critical question nào không?"

        ├─ YES → hỏi tiếp
        │
        └─ NO → summary
```

---

## 34. Sau soft limit có thể hỏi User

Một UX khá tốt:

> Mình đã có đủ thông tin chính để tạo bản tóm tắt.  
> Bạn muốn:
>
> **1. Tạo tóm tắt ngay**  
> **2. Bổ sung thêm thông tin**

Nếu user chọn 2:

```text
continue
```

Sau đó fill thêm field.

Đây là hướng **OK và nên dùng**.

---

## 35. Stop Agent — Input / Output

### Input

```json
{
  "conversation_state": {},
  "active_protocols": [],
  "coverage": {},
  "red_flag_candidates": [],
  "user_intent": "",
  "turn_count": 5,
  "last_user_message": ""
}
```

### Output

```json
{
  "decision": "CONTINUE",
  "reason": "Critical abdominal red-flag fields are still missing",
  "next_priority_fields": [
    "pain_severity",
    "loss_of_consciousness"
  ]
}
```

hoặc:

```json
{
  "decision": "SUMMARIZE",
  "reason": "Core information collected and user reported no additional symptoms"
}
```

---

## 36. Stop Policy tổng hợp

Pseudo logic:

```text
IF explicit_summary_request:
    SUMMARIZE

ELSE IF explicit_end_intent:
    SUMMARIZE

ELSE IF user_refuses_to_continue:
    SUMMARIZE

ELSE IF safety_critical_fields_missing:
    CONTINUE

ELSE IF core_information_sufficient
        AND information_gain_low:
    SUMMARIZE

ELSE IF no_new_clinical_information_for_N_turns:
    OFFER_SUMMARY

ELSE IF soft_turn_limit_reached
        AND no_critical_missing_fields:
    OFFER_SUMMARY

ELSE:
    CONTINUE
```

Đây tốt hơn rất nhiều so với:

```text
IF all_fields_filled:
    SUMMARIZE
```

---

## 37. Action Flow cuối cùng

```text
USER MESSAGE
     │
     ▼
Protocol Router
     │
     ├── General
     ├── Fever
     ├── Abdominal
     ├── Skin
     ├── Chitchat
     └── ...
     │
     ▼
RAG Retrieval
     │
     ▼
Entity / Symptom Extraction
     │
     ▼
Update Conversation State
NULL → TRUE / FALSE / UNKNOWN
     │
     ▼
Detect Red-flag Candidates
     │
     ▼
Determine Active Fields
     │
     ▼
Coverage Checker
     │
     ▼
Stop Decision
     │
 ┌───┴──────────────────────────┐
 │                              │
CONTINUE                       STOP
 │                              │
 ▼                              ▼
Question Planner             Summarizer
 │                         ┌────┴────┐
 ▼                         ▼         ▼
LLM question             NLP      Nurse
 │                      Summary    JSON
 ▼
USER
```

---

## 38. Output 1 — Natural-language Summary

### Option A — NLP Summary

Đây là cách đơn giản nhất cho model/user.

Input:

```text
all user answers
+
structured state
```

Processing:

```text
Remove duplication
Remove irrelevant chitchat
Resolve corrections
Preserve meaningful information
```

Ví dụ:

> Người dùng báo đau bụng bên phải từ sáng, cơn đau tăng dần và kèm buồn nôn. Người dùng phủ nhận nôn và tiêu chảy. Chưa xác định được có sốt hay không vì chưa đo nhiệt độ.

---

## 39. Output 1B — Field-based Natural Summary

Phương án chặt chẽ hơn:

Chỉ lấy các field được detect.

Ví dụ:

```json
{
  "abdominal_pain": true,
  "pain_location": "right abdomen",
  "nausea": true,
  "vomiting": false,
  "fever": "unknown"
}
```

Render thành:

```text
Triệu chứng ghi nhận:
- Đau bụng bên phải.
- Buồn nôn.

Người dùng phủ nhận:
- Nôn.
```

Nếu yêu cầu:

> chỉ hiện `True`

thì:

```text
- Đau bụng bên phải.
- Buồn nôn.
```

Tuy nhiên về mặt dữ liệu, **không nên xóa `False` khỏi state**, vì việc bệnh nhân phủ nhận một triệu chứng cũng là thông tin có giá trị. Chỉ cần không render nó ở UI nếu product không muốn hiển thị.

---

## 40. Output 2 — Nurse Structured Summary

Output:

```json
{
  "identify": {
    "age": 45,
    "sex": "male"
  },

  "situation": {
    "chief_complaint": "Right-sided abdominal pain"
  },

  "background": {
    "medications": [
      "..."
    ],
    "allergies": [
      "..."
    ]
  },

  "assessment": {
    "onset": "This morning",
    "symptoms": [
      {
        "name": "abdominal_pain",
        "status": true,
        "location": "right abdomen"
      },
      {
        "name": "nausea",
        "status": true
      },
      {
        "name": "vomiting",
        "status": false
      }
    ],
    "red_flag_candidates": [
      "progressively worsening pain"
    ]
  }
}
```

---

## 41. Field không có giá trị thì không xuất

Ví dụ không biết allergy:

Không cần:

```json
{
  "allergies": null
}
```

Có thể output:

```json
{
  "background": {
    "medications": ["..."]
  }
}
```

HTML renderer chỉ render những field tồn tại.

---

## 42. Vấn đề `triage_category` trong ISBAR

Phiếu hiện tại có:

```text
[I] Identify
- Patient
- Triage Category: RED / YELLOW / GREEN
```

Nhưng theo architecture mới:

```text
Summary
   ↓
Triage
```

Do đó **Agent này chưa thể ghi `triage_category`**, vì sẽ tạo circular dependency:

```text
cần triage để tạo summary
nhưng
cần summary để chạy triage
```

Nên output của Agent:

```json
{
  "identify": {
    "age": 45,
    "sex": "male"
  }
}
```

Sau downstream triage:

```text
Nurse JSON
   ↓
Triage system
   ↓
RED/YELLOW/GREEN
```

mới enrich:

```json
{
  "identify": {
    "age": 45,
    "sex": "male",
    "triage_category": "YELLOW"
  }
}
```

---

## 43. Recommendation cũng tương tự

Nếu Recommendation thực sự được tạo bởi module downstream:

```text
Conversation Agent
→ Summary
→ Triage / Recommendation module
```

thì Conversation Agent **không nên hallucinate Recommendation**.

ISBAR ban đầu:

```text
I
S
B
A
R
```

Có thể ở boundary của Agent chỉ tạo:

```text
I
S
B
A
```

Sau downstream mới append:

```text
R
```

Hoặc giữ:

```json
{
  "recommendation": {}
}
```

nhưng nếu yêu cầu *field không có value thì không xuất*, tốt nhất bỏ luôn.

---

## 44. Nurse có quyền chỉnh sửa

Sau JSON → HTML:

```text
Nurse
  ↓
Edit any field
```

Bao gồm:

```text
Identify
Situation
Background
Assessment
Symptoms
Red flags
Recommendation
Triage
```

**Không khóa red flag.**

Nên giữ audit:

```json
{
  "generated_value": true,
  "current_value": false,
  "edited_by": "nurse_123",
  "edited_at": "..."
}
```

---

## 45. Functional Requirements

### FR1 — Symptom Detection

Hệ thống phải detect:

```text
Symptom
Presence / absence
Onset
Duration
Location
Severity
Associated symptoms
Relevant medical history
Medication
Allergy
Red-flag candidates
```

### FR2 — Dynamic Question Generation

LLM sinh câu hỏi dựa trên:

```text
Conversation state
+
Active protocol
+
NULL fields
+
Question priority
+
RAG
```

Không hỏi theo questionnaire cố định.

### FR3 — Coverage đa nhóm bệnh

Không tập trung quá nhiều vào Fever.

Thiết kế:

```text
Base General Protocol
        +
Dynamic Specialized Protocol
```

Ví dụ:

```text
General + Fever
General + Abdominal
General + Headache
General + Skin
...
```

Nếu không có specialized protocol:

```text
General + RAG fallback
```

### FR4 — Efficient Questioning

Mục tiêu không phải:

```text
minimum questions
```

mà là:

```text
minimum conversational burden
while maintaining sufficient clinical information
```

Cơ chế:

```text
Batch questions
Prioritize critical fields
Reuse previous answers
Do not ask UNKNOWN repeatedly
Skip low-value optional fields
Stop based on information sufficiency
```

### FR5 — Field Refill

Lifecycle:

```text
NULL
 │
 ├─ affirmative answer → TRUE
 │
 ├─ negative answer    → FALSE
 │
 └─ cannot determine /
    refuses / doesn't know → UNKNOWN
```

Question Planner ưu tiên:

```text
NULL
```

Không mặc định hỏi lại:

```text
UNKNOWN
```

trừ khi field critical.

### FR6 — Memory

Short memory:

```text
Structured state
+
Compressed old context
+
Recent raw turns
```

Long memory:

```text
Nurse JSON
→ Database
```

Conversation mới:

```text
Get last 3 summaries
→ summarize history
→ context
```

### FR7 — Stop Decision

Không dựa vào:

```text
all fields filled
```

Mà dựa trên:

```text
User intent
+
Critical field coverage
+
Core information coverage
+
Information gain
+
Conversation stagnation
+
Soft turn budget
```

### FR8 — Summary

Mỗi conversation kết thúc phải tạo:

```text
1. Natural-language summary
2. Structured nurse JSON
```

Hai output phải xuất phát từ **cùng một Conversation State** để hạn chế contradiction.

---

## 46. Non-functional Requirements

### NFR1 — UX

Response cần:

- Streaming.
- Loading indicator.
- Xuống dòng hợp lý.
- Không có paragraph quá dài.
- Hỏi theo từng nhóm nhỏ.
- Có thể dùng bullet cho nhiều câu Có/Không.

### NFR2 — Ngôn ngữ tự nhiên

User không có chuyên môn y tế.

Không:

> Bạn có dyspnea hay orthopnea không?

Nên:

> Bạn có thấy khó thở không?

Nếu cần:

> Khi nằm xuống, bạn có thấy khó thở hơn không?

Câu hỏi ưu tiên:

```text
Có / Không
Mức độ
Thời gian
Vị trí
Con số cụ thể nếu user biết
```

### NFR3 — Giảm dài dòng

Sử dụng đồng thời:

```text
Protocol routing
+
Active field selection
+
Priority scoring
+
Question batching
+
State reuse
+
Information gain
+
Soft turn budget
+
Stop Agent
```

Thay vì:

```text
cứ còn NULL → cứ hỏi
```

### NFR4 — Medical Safety

Các câu liên quan thuốc/lifestyle cần dựa vào protocol/RAG cụ thể thay vì hard-code những giả định rộng.

Ví dụ:

> Tôi muốn uống bia, có được không?

Không nên hard-code:

```text
đang dùng kháng sinh
→ uống bia
→ tê liệt thần kinh
```

vì tương tác với alcohol phụ thuộc vào **thuốc cụ thể, liều, bệnh nền và bối cảnh**.

Agent nên hỏi:

```text
Bạn đang sử dụng thuốc gì?
Bạn đang điều trị bệnh gì?
```

rồi retrieve guidance liên quan.

---

## 47. Kiến trúc đề xuất cuối cùng

```text
                         INPUT
                           │
                  Multi-turn Chat
                           │
                           ▼
                ┌──────────────────┐
                │ Protocol Router  │
                └────────┬─────────┘
                         │
                         ▼
                    RAG Retrieval
                         │
                         ▼
                ┌──────────────────┐
                │ Entity/Symptom   │
                │ Extraction       │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │ Conversation     │
                │ State            │
                │                  │
                │ NULL             │
                │ TRUE             │
                │ FALSE            │
                │ UNKNOWN          │
                └────────┬─────────┘
                         │
              ┌──────────┴───────────┐
              ▼                      ▼
       Red-flag Detector       Coverage Checker
              │                      │
              └──────────┬───────────┘
                         ▼
                Question Planner
                         │
                         ▼
                     Stop Agent
                  ┌──────┴───────┐
                  │              │
              CONTINUE          STOP
                  │              │
                  ▼              ▼
            LLM Question     Summarizer
                  │          ┌────┴─────┐
                  │          │          │
                  ▼          ▼          ▼
                USER     NLP Summary  Nurse JSON
                                         │
                                         ▼
                             ─────────────────────
                                  AGENT BOUNDARY
                             ─────────────────────
                                         │
                                    Downstream
                                         │
                              Triage / Recommendation
```

---

## 48. Điểm chốt về Stop Condition

**Không dùng `fill hết field → summary`.**

Nên dùng:

```text
STOP =
    explicit user stop
 OR explicit summary request
 OR refusal to continue
 OR (
      critical information sufficiently covered
      AND core information sufficiently covered
      AND next-question information gain is low
    )
 OR (
      soft turn limit reached
      AND no critical field remains
    )
 OR (
      conversation is no longer yielding clinical information
    )
```

Trong đó **turn limit chỉ là soft limit**.

Thiết kế conversation có thể là:

```text
Turn 1–4:
Thu thập bình thường.

Turn 5–6:
Ưu tiên các field quan trọng còn thiếu.

Đến soft limit:
 ├─ Critical field còn thiếu
 │      → tiếp tục hỏi.
 │
 └─ Không còn critical field
        → "Mình đã có đủ thông tin chính.
           Bạn muốn tạo bản tóm tắt hay bổ sung thêm?"
```

Nếu user chọn bổ sung:

```text
Continue
→ update state
→ summary lại sau
```

Nếu user chọn dừng:

```text
Summary
```

### Kết luận

Phương án hợp lý nhất không phải:

**`Fill hết field → Summary`**

cũng không phải:

**`Đủ N turn → Summary`**

mà là:

> **`User intent + Clinical coverage + Critical-field coverage + Information gain + Soft turn budget → Stop decision.`**

Cơ chế này giúp hệ thống vừa xử lý được **Fever Protocol cụ thể**, vừa mở rộng sang hàng loạt case general mà không phải định nghĩa trước toàn bộ triệu chứng có thể tồn tại.
