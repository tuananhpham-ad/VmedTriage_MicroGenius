# CLAUDE.md

> File này được đọc đầu mỗi session làm việc trên repo VMedTriage. Giữ ngắn gọn, cập nhật khi có thay đổi lớn — chi tiết lịch sử nằm ở `docs/context/decisions.md` và `docs/context/sessions/`.

## Bối cảnh dự án

**VMedTriage** — AI Agent hỗ trợ điều dưỡng phân loại mức độ ưu tiên ban đầu cho bệnh nhân tư vấn online, thông qua hội thoại có cấu trúc thu thập triệu chứng, phát hiện red-flag, và đề xuất mức ưu tiên — **luôn cần điều dưỡng xác nhận trước khi gửi cho bệnh nhân**.

- **Team:** MicroGenius — Thương (PM/PO/QA), Tuấn Anh (Agent Lead), Đức Anh (Data Lead), Dũng (Fullstack AI Engineer)
- **Timeline:** 6 tuần (29/07–05/09/2026), đang ở Sprint 2 (W2–W3)
- **Nền tảng:** Web app responsive, 2 role: Bệnh nhân / Nhân viên y tế
- Tài liệu gốc: `docs/brief.md`, `docs/prd.md`, `docs/wireframe/`, `docs/planning/Feature_Specification_VMedTriage.md`

## Nguyên tắc an toàn — KHÔNG BAO GIỜ VI PHẠM

Đây là ràng buộc cứng của toàn dự án, áp dụng cho mọi tính năng, mọi đoạn code liên quan đến Agent:

1. **HITL bắt buộc 100%** — kết quả AI luôn là *đề xuất*; không có đường nào gửi hướng xử trí cho bệnh nhân mà bỏ qua bước duyệt của nhân viên y tế. Không auto-approve, kể cả mức "Tự theo dõi".
2. **AI tuyệt đối không kết luận chẩn đoán** bệnh cụ thể — chỉ đề xuất mức ưu tiên (Cấp cứu / Khám sớm / Tự theo dõi).
3. **Grounded, chống bịa** — mọi câu hỏi/output của agent phải bám checklist chuẩn đã định nghĩa, không tự suy diễn thêm chi tiết y khoa không có trong câu trả lời của bệnh nhân.
4. **Red-flag escalate ngay lập tức** — không chờ hết checklist, không chờ duyệt (đây là ngoại lệ có chủ đích của HITL, vì an toàn tức thời quan trọng hơn).
5. **Bảo vệ PII/PHI** — dữ liệu triệu chứng là dữ liệu y tế nhạy cảm, chỉ nhân viên y tế được gán ca mới truy cập được.

## Phạm vi MVP

- **5 nhóm triệu chứng cố định:** Sốt, Đau bụng, Đau ngực, Khó thở, Đau đầu/Chấn thương đầu nhẹ — không mở rộng thêm nhóm trong MVP.
- **3 mức ưu tiên cố định:** Cấp cứu / Khám sớm / Tự theo dõi.
- **Ngoài phạm vi:** chẩn đoán bệnh cụ thể, đặt lịch khám, đa kênh (voice/hình ảnh), realtime WebSocket, giải thích trích dẫn guideline.

## Quy ước code
- quy ước chuẩn code Python áp dụng cho toàn bộ dự án: xem chi tiet tai `docs/guide/code-style/python.md` — Type hints, quy tắc hàm, naming, imports, error handling và Ruff


- **Ngôn ngữ:** identifier/code (biến, hàm, bảng, cột) viết bằng tiếng Anh; nội dung hiển thị cho người dùng (checklist, disclaimer, UI text) viết bằng tiếng Việt.
- **Naming DB:** snake_case (`checklist_responses`, `priority_flag`, `approval_status`, `audit_log`, `summary_json`).
- **API:** RESTful, resource theo case (`/cases`, `/cases/{id}/responses`, `/cases/{id}/approve`); mọi response liên quan đến kết quả cho bệnh nhân phải kiểm tra `approval_status` trước khi trả nội dung xử trí.
- **Branch naming:** `<type>/<mô-tả-ngắn>-<ddmm>`, ví dụ `docs/sprint2-planning-0408`.
- **Commit message:** theo Conventional Commits — `feat:`, `fix:`, `docs:`, `chore:`, `test:`.
- **Task reference:** mọi commit/PR liên quan đến 1 task cụ thể nên trỏ về mã `T-xxx` trong `Plan.xlsx` (ví dụ: `feat: implement red-flag detection logic (T-031)`).
- **Testing:** mọi thay đổi liên quan đến Agent/red-flag/priority phải chạy qua bộ ≥20 test case chuẩn (`docs/planning/`) trước khi merge; không giảm số lượng hoặc độ phủ 5 nhóm triệu chứng của bộ test.

## Trạng thái hiện tại

Xem chi tiết cập nhật mới nhất tại `docs/context/sessions/`. Tóm tắt nhanh: Sprint 2 (W2–W3) đang triển khai 5 đặc tả tính năng đã hoàn thành trong `Feature_Specification_VMedTriage.md`. Mục tiêu Demo V1 cuối Sprint 2.

# M