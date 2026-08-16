"""Engine hội thoại triệu chứng DÙNG CHUNG cho mọi symptom_group (fever, chest_pain, breathing,
abdominal, neurologic, bleeding, headache, ...).

Tách ra từ agent fever (`_guidance/fever-detect-agent-task.md`) sau khi fever đã chạy qua đủ 6 bước +
qua LLM thật, để nhóm bệnh tiếp theo KHÔNG PHẢI viết lại state machine/rule engine/intake agent/session
- chỉ cần định nghĩa field registry + question cluster + rule catalog + vài hàm quyết định lâm sàng
(route, provisional emergency scan, self-care checklist) rồi đăng ký vào một `SymptomProtocol`
(xem `protocol.py`).

Ranh giới tách module - "cơ chế" (ở đây) vs "nội dung" (ở `fever_*`/tương lai `<disease>_*`):

| Cơ chế (thuần thuật toán, không biết gì về bệnh cụ thể) | Nội dung (đặc thù từng bệnh) |
|---|---|
| Duyệt stage theo thứ tự, chọn cụm chưa hỏi (`stage_machine.py`) | field registry, question cluster, `stage_order`, `budget` |
| Áp ngân sách theo CS Part 6(b) - chỉ cắt cụm thuần O/H (`stage_machine.py`) | tier của từng field |
| Chạy hết catalog rule rồi lấy mức cao nhất (`rule_engine.py`) | các hàm rule cụ thể (điều kiện + RF/rule code) |
| Gọi LLM trích field theo schema cụm, ghép hướng C/E theo stage (`intake_agent.py`) | field cụ thể, câu hỏi mẫu, field an toàn "cơ hội" |
| Vòng đời phiên hỏi-đáp (`session.py`) | `determine_route`, `provisional_emergency_signal`, `self_care_checklist_satisfied` |

Mọi module ở đây nhận `SymptomProtocol` làm tham số đầu tiên - không import bất kỳ thứ gì fever-specific.
"""
