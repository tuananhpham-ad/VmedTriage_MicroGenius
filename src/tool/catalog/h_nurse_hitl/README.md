# Nhom H - Nurse workflow va HITL

Nhom nay ho tro human-in-the-loop: tao/read queue, assign case, alert, submit review, gui response da duyet va update status.

| File | Tool | Lam gi |
|---|---|---|
| `__init__.py` | Package marker | Danh dau package tool group H. |
| `tool_049_nurse_queue_create_item.py` | `nurse_queue_create_item` | Tao queue item cho dieu duong tu case va proposal. |
| `tool_050_nurse_queue_read.py` | `nurse_queue_read` | Doc danh sach case dang cho review. |
| `tool_051_nurse_case_assign.py` | `nurse_case_assign` | Gan case cho mot nurse/clinical reviewer. |
| `tool_052_nurse_priority_alert.py` | `nurse_priority_alert` | Gui alert uu tien cao toi dashboard/paging. |
| `tool_053_human_review_submit.py` | `human_review_submit` | Nop hanh dong approve/edit/reject/escalate/ask_more. |
| `tool_054_approved_response_sender.py` | `approved_response_sender` | Gui response chi sau khi da duoc nurse duyet. |
| `tool_055_handoff_summary_generator.py` | `handoff_summary_generator` | Tao tom tat ban giao cho nurse. |
| `tool_056_case_status_updater.py` | `case_status_updater` | Cap nhat workflow status cua case. |

