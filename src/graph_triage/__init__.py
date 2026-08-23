"""Agent quyết định chạy trên model đã train, tách khỏi luồng triage chính.

Nhận phiếu tóm tắt dạng text -> LogReg + PhoBERT (+ HGT fusion khi có artifact) + Patient Graph trích
xuất qua DeepSeek -> LLM chọn một mức trong 3 nhãn, kèm evidence có provenance.

Port từ repo nghiên cứu `triage_baselines` (`D:\\Vin\\graph\\graph`).

RANH GIỚI: `graph_triage_mode="ensemble"` là ý kiến tham khảo thứ hai cho điều dưỡng. Ở mode
`"c6"`, C6 được phép NÂNG (không hạ) `TriageProposal.priority` sau khi `symptom_protocol.rule_engine`
đã tạo priority tức thời. C6 dùng đúng combiner benchmark: GPT direct OR Fusion OR documented-rule
emergency; nó không nạp LogReg, PhoBERT độc lập hay LLM quyết định tổng của mode ensemble. C6 không đổi red flag và không
bao giờ tự duyệt hay gửi nội dung cho bệnh nhân.

Điểm vào của luồng web là `service.decide_for_case`; `agent/run.py` và `agent/run_llm.py` là CLI để
thử tay. Mọi thứ cần torch nằm sau import lazy - xem docstring của `service.py`.
"""
