"""Agent quyết định chạy trên model đã train, tách khỏi luồng triage chính.

Nhận phiếu tóm tắt dạng text -> LogReg + PhoBERT (+ HGT fusion khi có artifact) + Patient Graph trích
xuất qua DeepSeek -> LLM chọn một mức trong 3 nhãn, kèm evidence có provenance.

Port từ repo nghiên cứu `triage_baselines` (`D:\\Vin\\graph\\graph`).

RANH GIỚI: kết quả của package này là Ý KIẾN THAM KHẢO THỨ HAI cho điều dưỡng. Nó KHÔNG BAO GIỜ được
gán vào `TriageProposal.priority` hay ghi đè `RedFlagFinding` - `ProtocolTriageEngine` và
`RedFlagSafetyLayer` vẫn là nguồn quyết định mức ưu tiên duy nhất.

Điểm vào của luồng web là `service.decide_for_case`; `agent/run.py` và `agent/run_llm.py` là CLI để
thử tay. Mọi thứ cần torch nằm sau import lazy - xem docstring của `service.py`.
"""
