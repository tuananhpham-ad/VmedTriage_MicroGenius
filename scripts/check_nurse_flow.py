"""Luồng THẬT qua HTTP: bệnh nhân chat -> phiếu chốt -> điều dưỡng mở hàng đợi -> AI đề xuất.

    python -m scripts.check_nurse_flow                        # server local (localhost:8000)
    python -m scripts.check_nurse_flow --base-url https://... # server da deploy

Khác `trace_end_to_end.py` ở chỗ bài kia gọi thẳng hàm trong tiến trình. Bài này đi qua đúng những
endpoint mà web UI gọi, nên nó kiểm được những thứ chỉ hỏng ở tầng HTTP/deploy:

* `/auth/demo-login` có cấp được tài khoản hai vai không;
* ca có NỔI LÊN trong `/nurse/queue` không - `_is_ready_for_nurse_queue` chỉ cho qua khi
  `graph_decision` đã tồn tại, nên ca vắng mặt ở đây nghĩa là Part 2 chưa chạy xong hoặc chết;
* `graph_decision` có THẬT không, hay `null` vì `GRAPH_TRIAGE_MODE=off` / artifact không nạp được
  (đúng lỗi đã xảy ra trên revision 0000004 khi GRAPH_TRIAGE_ARTIFACT_ROOT bị MSYS dịch sai).

TỐN API THẬT: mỗi lượt chat gọi provider của agent hỏi-đáp, phiếu chốt thêm Part 2 + Part 3.
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ca sốt nhẹ, cùng kịch bản với `trace_end_to_end.py` để hai bài so được với nhau.
TURNS = [
    "Tôi bị sốt.", "18 tuổi", "nam", "tôi 38 độ, đo cách đây 30 phút ở nách",
    "sốt mới được có 4 tiếng thôi", "tôi không thấy rét", "tôi uống para đã đỡ hơn rồi",
    "tôi thấy khỏe hơn rồi", "đúng rồi", "không có", "không có", "không có", "3",
]
FALLBACK = "không"
MAX_TURNS = 40
# Phiên đã đóng: không gửi thêm lượt nào nữa.
CLOSED = {"needs_nurse_review", "awaiting_approval", "escalated", "approved", "rejected"}


def _rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def _demo_login(client: httpx.Client, role: str) -> tuple[str, str]:
    reply = client.post("/api/v1/auth/demo-login", json={"role": role})
    reply.raise_for_status()
    body = reply.json()
    return body["access_token"], body["user"]["username"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000", help="Goc cua server can test.")
    parser.add_argument("--timeout", type=float, default=180.0,
                        help="Timeout moi request (giay). Cold start Azure min-replicas=0 rat lau.")
    parser.add_argument("--json", action="store_true", help="In nguyen graph_decision dang JSON.")
    args = parser.parse_args()

    client = httpx.Client(base_url=args.base_url.rstrip("/"), timeout=args.timeout)

    _rule(f"CHẶNG 0  -  server {args.base_url}")
    health = client.get("/health")
    print(f"  /health -> {health.status_code} {health.text[:200]}")
    health.raise_for_status()

    patient_token, patient_name = _demo_login(client, "patient")
    nurse_token, nurse_name = _demo_login(client, "nurse")
    print(f"  bệnh nhân : {patient_name}")
    print(f"  điều dưỡng: {nurse_name}")
    patient_headers = {"Authorization": f"Bearer {patient_token}"}
    nurse_headers = {"Authorization": f"Bearer {nurse_token}"}

    _rule("CHẶNG 1  -  bệnh nhân chat qua POST /api/v1/chat")
    case_id: str | None = None
    status = "collecting_information"
    for index in range(1, MAX_TURNS + 1):
        message = TURNS[index - 1] if index <= len(TURNS) else FALLBACK
        payload = {"message": message} | ({"case_id": case_id} if case_id else {})
        reply = client.post("/api/v1/chat", json=payload, headers=patient_headers)
        reply.raise_for_status()
        body = reply.json()
        case_id, status = body["case_id"], body["status"]
        print(f"\n[{index:>2}] bệnh nhân: {message}")
        print(f"     agent    : {(body.get('response') or '')[:120]}")
        print(f"     status={status}"
              + (f"  priority={body['triage_proposal']['priority']}" if body.get("triage_proposal") else ""))
        if status in CLOSED:
            print(f"\n>> Phiên chốt sau {index} lượt.")
            break
    else:
        print(f"\n!! Hết {MAX_TURNS} lượt mà phiên chưa chốt - thử force-complete.")
        reply = client.post(f"/api/v1/cases/{case_id}/force-complete", headers=patient_headers)
        reply.raise_for_status()
        status = reply.json()["status"]
        print(f"   force-complete -> status={status}")

    _rule("CHẶNG 2  -  điều dưỡng mở GET /api/v1/nurse/queue")
    reply = client.get("/api/v1/nurse/queue", headers=nurse_headers)
    reply.raise_for_status()
    queue = reply.json()
    print(f"  {len(queue)} ca trong hàng đợi")
    for item in queue[:10]:
        mark = "  <== ca vừa tạo" if item["case_id"] == case_id else ""
        priority = (item.get("triage_proposal") or {}).get("priority", "?")
        print(f"    {item['case_id'][:8]}  {item['status']:22} priority={priority}{mark}")
    if not any(item["case_id"] == case_id for item in queue):
        print(f"\n  !! Ca {case_id} KHÔNG có trong hàng đợi. `_is_ready_for_nurse_queue` chặn vì")
        print("     `graph_decision` còn null -> Part 2 chưa chạy xong hoặc đã chết. Xem log server.")

    _rule("CHẶNG 3  -  điều dưỡng mở ca: GET /api/v1/cases/{case_id}")
    reply = client.get(f"/api/v1/cases/{case_id}", headers=nurse_headers)
    reply.raise_for_status()
    triage_case = reply.json()
    proposal = triage_case.get("triage_proposal") or {}
    print(f"  Rule engine (quyết định thật): {proposal.get('priority', '?')}")
    print(f"  Red flag                     : {[f['label'] for f in triage_case.get('red_flags', [])] or '(không)'}")
    print(f"  summary_ready                : {triage_case.get('summary_ready')}")

    _rule("CHẶNG 4  -  AI ĐỀ XUẤT  (trường `graph_decision`)")
    decision = triage_case.get("graph_decision")
    if not decision:
        print("  graph_decision = null  ->  KHÔNG CÓ AI ĐỀ XUẤT.")
        print("\n  Ba nguyên nhân thường gặp, kiểm theo thứ tự:")
        print("    1. GRAPH_TRIAGE_MODE chưa đặt (mặc định `off` trong src/config.py) -> đặt = c6")
        print("    2. ENABLE_GRAPH_TRIAGE_AGENT=false")
        print("    3. Artifact không nạp được - GRAPH_TRIAGE_ARTIFACT_ROOT trỏ sai (phải là /app/runs")
        print("       trong container; ĐỂ TRỐNG trong deploy/azure/env, Dockerfile đã ENV sẵn).")
        return 1

    print(f"  nhãn AI đề xuất  : {decision.get('triage_label')}")
    print(f"  cần người xem lại: {decision.get('requires_human_review')}")
    print(f"  model            : {decision.get('model')}")
    if "safety_gate" in decision:
        print(f"  safety_gate      : {decision['safety_gate']}")
    print("\n  tóm tắt quyết định:")
    for line in (decision.get("decision_summary") or "(trống)").splitlines():
        print(f"    {line}")

    support = decision.get("source_support")
    if support:
        print("\n  --- Part 3: trích nguồn ---")
        for citation in support.get("explanation_citations", []):
            print(f"    {citation['marker']} {citation['publisher']} · {citation['url']}")
    else:
        print("\n  --- Part 3: KHÔNG CÓ  (SOURCE_SUPPORT_ENABLED=false, hoặc guard chặn) ---")

    if args.json:
        _rule("graph_decision (JSON đầy đủ)")
        print(json.dumps(decision, ensure_ascii=False, indent=2))

    print(f"\n>> Xong. case_id = {case_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
