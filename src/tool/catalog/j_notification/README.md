# Nhom J - Notification

Nhom nay mo cac tool gui thong bao. Trong local implementation, cac thao tac thuong duoc ghi vao outbox/state va `sent=false`/`delivered=false` neu chua co provider that.

| File | Tool | Lam gi |
|---|---|---|
| `__init__.py` | Package marker | Danh dau package tool group J. |
| `tool_065_sms_notification_tool.py` | `sms_notification_tool` | Gui SMS sau khi co approval. |
| `tool_066_email_notification_tool.py` | `email_notification_tool` | Gui email workflow/summary da duyet. |
| `tool_067_push_notification_tool.py` | `push_notification_tool` | Gui push notification toi app/dashboard/device. |
| `tool_068_on_call_paging_tool.py` | `on_call_paging_tool` | Page staff truc khi case escalation/emergency. |
| `tool_069_appointment_scheduler.py` | `appointment_scheduler` | Dat lich phong kham sau confirmation va approval. |

