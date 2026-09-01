# VMedTriage — Weekly Log (5 tuần: 1/8 – 1/9/2026)

**Team:** MicroGenius
**Ngày lập:** 2026-09-01

---

## Tuần 1 — Sprint 1: Khởi động

| ID | Việc | Người phụ trách | Ngày xong | Trạng thái | Ghi chú |
|---|---|---|---|---|---|
| T-000 | Lên kế hoạch Sprint 1 | Thương | 1/8 | Hoàn thành | |
| T-001 | Project Charter (mục tiêu, phạm vi, người dùng, chỉ số đo lường) | Thương | 1/8 | Hoàn thành | |
| T-002 | Thiết lập GitHub + quy trình nhánh | Dũng | 1/8 | Hoàn thành | Mới có CI, chưa có CD — bổ sung CD ở sprint sau, sau khi có nơi deploy rõ ràng |
| T-003 | Tìm hiểu luồng nghiệp vụ → BRD, Gateway 1 (Brief, PRD, Wireframe/UI Flow) | Thương | 2/8 | Hoàn thành | Chưa kịp làm BRD, tiếp tục bổ sung |
| T-005 | Data v1 (thu thập dữ liệu, bộ test v1, check kỹ red-flag) | Đức Anh | 3/8 | Hoàn thành | Cần trao đổi thêm |

**Tóm tắt tuần 1:** Chốt phạm vi/mục tiêu dự án, dựng hạ tầng repo + CI cơ bản, bắt đầu thu thập dữ liệu và tìm hiểu nghiệp vụ. Đây là tuần nền tảng, chưa có code sản phẩm.

---

## Tuần 2 (4/8 – 10/8) — Sprint 2: Phát triển vòng 1 (phần đầu)

| ID | Việc | Người phụ trách | Ngày xong | Trạng thái | Ghi chú |
|---|---|---|---|---|---|
| T-004 | Sơ đồ kiến trúc hệ thống (system overview, agent flow, deployment diagram) | Tuấn Anh (+Dũng hỗ trợ) | 4/8 | Hoàn thành | Cần trao đổi thêm — hoàn thiện v1 trước, chỉnh sau nếu vướng |
| T-006 | Thiết kế DB schema: users, cases, checklist_responses | Đức Anh | 4/8 | Hoàn thành | Done |
| T-007 | Chọn LLM provider, đăng ký API key, spike gọi LLM thật | Tuấn Anh | — | Hoàn thành | Chốt: deepseek-chat (reasoning) + SLM (query processing, mapping) |
| T-008 | Checklist nhóm Sốt | Thương | — | Hoàn thành | |
| T-009 | API đăng ký/đăng nhập + middleware phân quyền 2 role | Dũng | — | Hoàn thành | Cần trao đổi thêm |
| T-010 | Tổng hợp ngưỡng Cấp cứu/Khám sớm theo Bộ Y tế VN/WHO, cả 5 nhóm triệu chứng | Thương | 6/8 | Đợi Review | Mới xong 1 phần, chưa đủ 5 nhóm — ưu tiên làm sâu 1-2 nhóm để kịp demo |
| T-011 | Data detect triệu chứng (tham khảo Mayo Clinic) | Đức Anh | 6/8 | Hoàn thành | Done |
| T-012 | API spec (dummy) | Tuấn Anh | 7/8 | Hoàn thành | Done |
| T-013 | Mockup UI toàn hệ thống (W-01 → W-07) | Dũng | 7/8 | Đợi Review | Done |
| T-014 | Kiến trúc hội thoại free-text (detect + schema + hỏi bù) | Tuấn Anh | — | Hoàn thành | Done |
| T-015 | Nối backend dummy API với frontend mockup | Tuấn Anh + Dũng | 8/8 | Hoàn thành | |
| T-016 | Tiêu chí nghiệm thu cho từng tính năng trong PRD | Thương | — | Hoàn thành | |

**Tóm tắt tuần 2:** Bắt đầu xây song song 3 mảng — kiến trúc/DB, LLM + luồng hội thoại, UI mockup. Điểm nghẽn: ngưỡng lâm sàng (T-010) mới làm được 1 phần trên 5 nhóm triệu chứng — rủi ro cho demo sắp tới.

---

## Tuần 3 (11/8 – 18/8) — Sprint 2: Phát triển vòng 1 (phần cuối) + Demo/Gate 2

| ID | Việc | Người phụ trách | Ngày xong | Trạng thái | Ghi chú |
|---|---|---|---|---|---|
| T-017 | Chốt protocol/rule đánh giá agent làm đúng | Cả team | — | **Chưa hoàn thiện** | Tồn đọng |
| T-018 | Chuẩn hoá bộ data phục vụ model triage | Đức Anh | 8/8 | Hoàn thành | |
| T-019 | Vẽ luồng toàn hệ thống + luồng chi tiết tính năng triage | Thương | 8/8 | Hoàn thành | Sửa lại: cảnh báo red-flag không cần chờ duyệt trước khi hiện; thêm gợi ý hiển thị bệnh viện phù hợp |
| T-024 | Tài liệu Knowledge Model cho triệu chứng Fever | Thương | 11/8 | Hoàn thành | |
| T-025 | Tài liệu Conversation Flow cho agent hội thoại + triage | Thương | 12/8 | Hoàn thành | |
| T-026 | Test tính năng core Sprint 2 + tài liệu eval evidence | Thương | 12/8 | Hoàn thành | |
| T-027 | Deploy demo | Tuấn Anh | 12/8 | Hoàn thành | |
| T-021 | Triển khai agent hội thoại round 1 | Tuấn Anh | 14/8 | Hoàn thành | |
| T-022 | Triển khai agent triage round 1 | Dũng + Đức Anh | 14/8 | Hoàn thành | |
| T-023 | Triển khai hàng đợi (queue), HITL | Dũng | 14/8 | Đợi Review | |
| T-020 | Test/Gate 2: tối thiểu 5 test case manual | Thương | 15/8 | Hoàn thành | |
| T-028 | Viết README | Thương | 15/8 | Hoàn thành | |
| T-029 | Feedback UI, điểm cần chỉnh sửa | Thương | 15/8 | Hoàn thành | |
| T-030 | Chỉnh sửa UI | Dũng | 16/8 | Hoàn thành | |
| T-031 | Nối backend với UI (lần 2) | Dũng | 16/8 | Hoàn thành | |

**Tóm tắt tuần 3:** Hoàn thành agent hội thoại + triage round 1, hàng đợi/HITL, deploy demo, qua Gate 2 với 5 test case manual, README, và một vòng feedback/sửa UI. Tồn đọng đáng chú ý: **T-017 (chốt protocol/rule đánh giá agent) chưa làm** — cần xử lý sớm vì đây là nền cho toàn bộ việc kiểm thử sau này.

---

## Tuần 4 (19/8 – 25/8) — Sprint 3: Phát triển vòng 2 và sửa lỗi (phần đầu)

| ID | Việc | Người phụ trách | Ngày xong | Trạng thái | Ghi chú |
|---|---|---|---|---|---|
| T-032 | Form phiếu summary theo chuẩn ISBAR cho mỗi ca | Thương | 19/8 | Hoàn thành | Input cho model, output cho nhân viên y tế |
| T-035 | Thêm rule cho safety-gate (check red-flag) | Thương | 20/8 | Hoàn thành | Hoàn thiện trước 26/8 |
| T-033 | Chỉnh sửa luồng hội thoại (tối ưu lượt hỏi, output chuẩn) | Tuấn Anh | 20/8 | Hoàn thành | |
| T-034 | Bổ sung explainable trong summary (dùng RAG) | Đức Anh | 21/8 | Hoàn thành | Làm xong nhưng **latency cao** — nguyên nhân do dùng web search |
| T-036 | Chỉnh sửa phần deploy (kết nối DB lưu trữ, demo có người dùng thật) | Tuấn Anh | 21/8 | Hoàn thành | |
| T-037 | Xử lý phản hồi từ Demo 1 | Tuấn Anh | 22/8 | Hoàn thành | |
| T-043 | Soạn tài liệu tham chiếu (basic docs) cho 4 nhóm triệu chứng còn lại làm nguồn RAG/prompt | Thương | 24/8 | Hoàn thành | |

**Tóm tắt tuần 4:** Tập trung hoàn thiện phiếu tóm tắt ISBAR, safety-gate, và xử lý phản hồi Demo 1. Vấn đề kỹ thuật nổi lên: **latency cao do RAG dùng web search real-time**.

---

## Tuần 5 (26/8 – 1/9) — Kiểm thử và hoàn thiện tài liệu bàn giao

*Tuần trọng tâm: chuyển từ "phát triển tính năng" sang "kiểm thử toàn diện + đóng gói tài liệu bàn giao".*

### Task tracker

| ID | Việc | Người phụ trách | Ngày | Trạng thái | Ghi chú |
|---|---|---|---|---|---|
| T-039 | Lập file feedback lỗi — chạy thử full luồng trên production | Thương | 26/8 | Hoàn thành | |
| T-045 | Eval lại Triage trên Production / cập nhật Evaluation Evidence | Thương | 26/8 | Hoàn thành | |
| T-040 | Chẩn đoán lỗi retrieval/citation (nghi lỗi chuỗi: detect sai trọng tâm → embedding sai → retrieval sai) | Tuấn Anh | 26/8 | Đang làm | Cần khoanh vùng lỗi ở tầng detect/intent-slot hay embedding/retrieval |
| T-041 | Migrate RAG sang Vector DB tĩnh (Weaviate cloud) thay vì web search real-time | Đức Anh | — | **Không làm** | Quyết định không triển khai trong sprint này |
| T-038 | Tính năng gợi ý bệnh viện gần nhất theo mức khẩn cấp sau triage | Đức Anh | 27/8 | Hoàn thiện | Từ phản hồi Demo 1 |
| T-042 | Mở rộng phạm vi hỏi đáp — router nhận diện đúng nhóm bệnh trước khi hỏi (hiện chỉ cover tốt nhóm Sốt) | Tuấn Anh | 27/8 | Hoàn thành | |
| T-044 | Cải thiện Agent: memory qua nhiều lượt + detect chính xác hơn | Tuấn Anh | 28/8 | Hoàn thành | |

