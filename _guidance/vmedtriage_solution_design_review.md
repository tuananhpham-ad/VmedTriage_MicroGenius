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

### 3.1. Kiến trúc tổng thể

VMedTriage được thiết kế theo kiến trúc **Single-Agent Hybrid** với cơ chế **Human-in-the-Loop (HITL)** bắt buộc nhằm đảm bảo an toàn trong môi trường y tế.

Hệ thống sử dụng **Gemma 3 4B** để hiểu ngôn ngữ tự nhiên của bệnh nhân và chuyển đổi mô tả triệu chứng thành dữ liệu có cấu trúc theo checklist chuẩn. Sau khi dữ liệu được chuẩn hóa, hệ thống kiểm tra tính đầy đủ, phát hiện red-flag, tra protocol triage, đề xuất mức độ ưu tiên, tạo phiếu tóm tắt và chuyển cho điều dưỡng/bác sĩ xác nhận trước khi gửi kết quả cho bệnh nhân.

Trong toàn bộ quy trình, AI chỉ đóng vai trò **Clinical Decision Support**. Hệ thống không chẩn đoán bệnh, không kê đơn, không thay thế bác sĩ/điều dưỡng và không tự động đưa ra hướng xử trí cuối cùng.

### 3.2. Workflow

```text
Patient
    |
    v
Conversation Agent
    |
    v
Gemma 3 4B Semantic Mapper
(Natural Language -> Structured Data)
    |
    v
Checklist Validator
(Schema / Missing Fields / Contradiction Check)
    |
    v
Red-Flag Safety Layer
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
Nurse Dashboard
(Review / Edit / Approve / Reject)
    |
    v
Approved Response
    |
    v
Patient
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

#### 2. Gemma 3 4B Semantic Mapper

Gemma 3 4B là thành phần AI chính dùng cho hiểu ngôn ngữ tự nhiên và trích xuất thông tin.

Nhiệm vụ:

- Hiểu mô tả triệu chứng bằng ngôn ngữ tự nhiên.
- Chuẩn hóa cách diễn đạt của bệnh nhân.
- Mapping thông tin sang các trường checklist.
- Nhận diện từ đồng nghĩa, lỗi chính tả phổ biến và mô tả không chuẩn.
- Xác định thông tin còn thiếu.
- Sinh output theo JSON schema cố định.

Ví dụ input:

```text
Tôi bị đau ngực từ sáng, đi vài bước là thấy hụt hơi.
```

Ví dụ output:

```json
{
  "symptom_group": "chest_pain",
  "fields": {
    "chest_pain": true,
    "shortness_of_breath": true,
    "onset": "this_morning"
  },
  "missing_fields": [
    "pain_severity",
    "pain_radiation"
  ],
  "confidence": 0.86
}
```

Gemma không đưa ra chẩn đoán, không kết luận bệnh và không trả lời trực tiếp cho bệnh nhân.

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

Thay vì sử dụng rule-based mapping hoặc keyword matching, VMedTriage sử dụng **Gemma 3 4B** để thực hiện Semantic Mapping. Điều này giúp hệ thống hiểu nhiều cách diễn đạt khác nhau của bệnh nhân, bao gồm câu nói tự nhiên, từ đồng nghĩa, lỗi chính tả phổ biến và mô tả không đầy đủ, rồi chuyển đổi về cùng một cấu trúc dữ liệu chuẩn theo checklist.

Điểm mới này làm tăng độ linh hoạt ở bước thu thập triệu chứng, nhưng vẫn giữ an toàn bằng cách đặt Gemma trong phạm vi mapping và extraction. Các bước ra quyết định được kiểm soát bởi validator, red-flag safety layer, protocol-grounded triage engine và cổng phê duyệt của điều dưỡng/bác sĩ.

---

## 4. Đánh giá theo yêu cầu đề bài

| Yêu cầu đề bài | Mức đáp ứng | Ghi chú |
|---|---:|---|
| App deploy | Cần bổ sung trong implementation | Solution Design chưa nói deploy, nhưng có thể triển khai bằng FastAPI + frontend + Docker. |
| 2 role: bệnh nhân, điều dưỡng | Đạt | Cần mô tả rõ quyền của từng role trong UI/API. |
| Agent hỏi đáp triage có cấu trúc | Đạt | Conversation Agent + Checklist Validator đáp ứng. |
| Phân 3-4 mức ưu tiên | Đạt | Emergency, Urgent, Routine, Self-care. |
| Hướng xử trí đề xuất | Đạt có điều kiện | Chỉ được gửi sau khi điều dưỡng/bác sĩ duyệt. |
| Red-flag escalation | Đạt sau khi thêm Safety Layer | Đây là phần bắt buộc, cần đưa vào diagram. |
| Disclaimer rõ | Cần bổ sung ở UI/response layer | Nên có disclaimer trong màn hình bệnh nhân. |
| HITL bắt buộc | Đạt | Nurse Dashboard là approval gate. |
| Không chẩn đoán thay bác sĩ | Đạt | Cần duy trì trong prompt, schema và UI text. |
| Grounded trên protocol triage | Đạt sau khi thêm Protocol Engine | Cần có database/tool chứa guideline. |
| Chống bịa | Cần kiểm soát bằng schema + protocol lookup | Không cho LLM tự tạo guideline. |
| Bảo mật PII/PHI | Cần bổ sung thành module hoặc non-functional requirement | Nên có access control, encryption, audit log. |
| Queue realtime cho điều dưỡng | Phần nâng cao | Nên thiết kế dashboard có trạng thái queue. |
| Memory phiên & phiếu bàn giao | Đạt | Session state + Summary Generator. |
| Giải thích lý do có trích guideline | Đạt sau khi thêm evidence | Triage Engine cần trả về guideline reference. |
| Xử lý thiếu/mâu thuẫn | Đạt | Validator + follow-up questions. |
| Audit log & thống kê accuracy | Đạt sau khi thêm Audit Log | Cần lưu so sánh AI proposal vs nurse final decision. |

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
