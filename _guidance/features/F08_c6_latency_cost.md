# F08 — Latency & chi phí của C6: đo đúng chỗ trước khi cắt

> Chủ trì: Agent Lead + Fullstack.
> Nguồn: câu hỏi ngày **2026-08-24** — *"phần model fusion kia chỉ tham khảo thôi, mà phần nớ lại là
> phần gây latency và cost cao nhất, cải thiện như nào?"*
>
> File này **bác bỏ một phần tiền đề đó** bằng `file:line`, rồi mới đề xuất. Đọc mục 1 trước khi bàn
> giải pháp — nếu cắt sai chỗ thì vừa mất an toàn lâm sàng vừa không nhanh lên bao nhiêu.

---

## 1. Ba đính chính với tiền đề

### 1.1. Fusion KHÔNG "chỉ tham khảo" — nó là cổng leo thang một chiều

```python
# src/graph_triage/service.py:257-260
if escalated_by and updated["triage_label"] != "cap_cuu":
    updated["triage_label"] = "cap_cuu"
    updated["requires_human_review"] = True
    updated["escalated_by"] = escalated_by
```

Fusion không hạ nhãn, nhưng nó **nâng**. Bằng chứng từ ca thật `d008b6a9` chạy trên bản deploy
japaneast ngày 2026-08-24:

```
safety_gate.direct  = kham_som
safety_gate.fusion  = cap_cuu      <- nhánh DUY NHẤT hô cấp cứu
→ nhãn cuối        = cap_cuu
```

Ở ca đó `documented_rule.emergency = False` và `direct = kham_som`. Bỏ fusion đi thì ca này **tụt từ
cấp cứu xuống khám sớm**. Đây là thay đổi hành vi an toàn, không phải gỡ một món trang trí — và theo
`INVARIANTS.md` nó cần người lâm sàng ký, không phải một quyết định tối ưu hoá.

### 1.2. Phần đắt nhất trong nhánh fusion KHÔNG phải mô hình fusion

```python
# src/graph_triage/agent/decision.py:116-134
def resolve(self, text: str) -> ClinicalGraph:
    fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
    graph = self.graph_by_text_hash.get(fingerprint)
    if graph is not None:
        ...
        return graph
    ...
    from src.graph_triage.deepseek_extractor import DeepSeekExtractor
    graph = DeepSeekExtractor().extract(text)      # <- MỘT LỜI GỌI LLM
```

`_C6FusionGate.predict_label` ([service.py:129-135](../../src/graph_triage/service.py#L129-L135)) gọi
`resolve()` **trước** forward pass. Cache tra bằng **sha256 khớp tuyệt đối** của summary text — mà
summary của mỗi bệnh nhân là một chuỗi riêng biệt, nên ở production **cache miss gần như 100%**.
Cache `data/graphs/semigran_cache.jsonl` được dựng cho `golden.csv` lúc eval, không phục vụ ca thật.

Nên mỗi ca, nhánh "fusion" = **1 lời gọi DeepSeek** + 1 forward pass torch. Forward pass là phần rẻ
(mili giây → ~1s trên CPU); lời gọi mạng mới là phần đắt.

Chi phí thật của việc *có* mô hình fusion trong image là chi phí **hạ tầng**, không phải per-request:

| Khoản | Con số |
| --- | --- |
| RAM lúc chạy (torch + fusion) | buộc `--cpu 2 --memory 4Gi` — [deploy_azure.sh](../../scripts/deploy_azure.sh) |
| Kích thước image | +~1 GB |
| Cold start (`min-replicas 0`) | nạp torch + model trước request đầu |

### 1.3. Latency người dùng cảm nhận nằm ở Part 3, không phải C6

Đo từ log chạy thật (máy local, 2026-08-24):

| Chặng | Thời gian |
| --- | --- |
| `direct` (gpt-4o-mini) | **1.3s** |
| `source_support` (Part 3) — `16:41:56 → 16:42:29` | **33s** |

Part 3 làm: claim_splitter → Tavily search → fetch 8+ trang (một số 301/303 phải đi hai vòng) →
embeddings cho từng đoạn → `source_verdict` → `source_explain`. Cả ba nhánh C6 cộng lại không tới
1/5 con số đó.

> ⚠️ Hai số trên đo ở **máy local**, chưa đo trên bản deploy japaneast. Xem mục 4.

---

## 2. Đường đi hiện tại

### 2.1. Toàn bộ nằm trên đường request của bệnh nhân

```python
# src/api/routes.py:315-336  (_finish_chat_turn)
if _should_background_safety_gate(triage_case, previous):
    case_store.save(triage_case)
    _schedule_safety_gate(triage_case.case_id)      # nền — CHỈ cho ca ESCALATED
else:
    await _attach_graph_decision(triage_case, previous)   # chặn — mọi ca còn lại
```

```python
# src/api/routes.py:522
triage_case.graph_decision = await run_in_threadpool(graph_triage_service.decide_for_case, triage_case)
```

`run_in_threadpool` **không** làm nó thành nền — nó chỉ tránh chặn event loop cho *các request khác*.
Request của chính bệnh nhân đó vẫn `await` tới khi xong. Bệnh nhân bấm "Tôi đã khai báo hết" và ngồi
chờ **cả ba nhánh C6 + Part 3**.

Cơ chế chạy nền **đã tồn tại sẵn** (`_should_background_safety_gate` →
[routes.py:541-559](../../src/api/routes.py#L541-L559)) nhưng chỉ mở cho ca `ESCALATED`.

### 2.2. Ba nhánh chạy TUẦN TỰ dù hoàn toàn độc lập

[`_apply_c6_safety_gate`](../../src/graph_triage/service.py#L215-L256) là ba khối `try/except` nối
đuôi nhau:

| Thứ tự | Nhánh | Gọi gì |
| --- | --- | --- |
| 1 | `direct` | `decide_direct` → 1 lời gọi `graph_triage_safety_model` |
| 2 | `fusion` | 1 lời gọi DeepSeek (graph) + forward pass torch |
| 3 | `documented_rule` | `extract_and_evaluate` → 1 lời gọi `graph_triage_safety_model` nữa |

Không nhánh nào đọc kết quả của nhánh khác — chúng chỉ được gộp phiếu ở
[dòng 257](../../src/graph_triage/service.py#L257). Việc xếp hàng chờ nhau là thuần lãng phí.

### 2.3. Ba nhánh cùng đọc MỘT chuỗi

Cả ba đều nhận `summary_text` từ `build_summary_text(triage_case)`
([service.py:350](../../src/graph_triage/service.py#L350)). `direct` và `documented_rule` còn dùng
**cùng một model** (`graph_triage_safety_model`) trên cùng chuỗi đó — hai lời gọi riêng cho cùng một
đầu vào.

---

## 3. Đề xuất, xếp theo tỉ lệ lợi/hại

### P1 — Đưa C6 + Part 3 ra khỏi đường request  ⭐ làm trước

Mở rộng `_should_background_safety_gate` cho **mọi** ca chốt phiếu, không chỉ `ESCALATED`.

- **Được:** bệnh nhân nhận phản hồi ngay; toàn bộ ~35s biến mất khỏi cảm nhận người dùng.
- **Không đổi:** nhãn, công thức C6, độ chính xác — không đụng một dòng nào trong `graph_triage/`.
- **Phải xử lý:** hàng đợi điều dưỡng đang lọc theo `graph_decision is not None`
  ([routes.py:705](../../src/api/routes.py#L705)). Ca sẽ vào hàng đợi chậm vài chục giây. Hai lựa chọn:
  lùi cổng lọc về `summary_ready`, hoặc cho ca vào ngay kèm trạng thái "đang phân tích" ở UI.
  **Không được** để ca biến mất khỏi hàng đợi trong lúc chờ — đó đúng là lỗi đã gặp ngày 2026-08-24.

### P2 — Chạy ba nhánh song song  ⭐ làm cùng P1

Ba nhánh độc lập → `asyncio.gather` hoặc `ThreadPoolExecutor` ba luồng.

- **Được:** thời gian C6 ≈ nhánh chậm nhất thay vì tổng ba nhánh. Cắt ~40-50%.
- **Không đổi:** kết quả — thứ tự gộp phiếu ở dòng 257 không phụ thuộc thứ tự chạy.
- **Lưu ý:** `_c6_fusion_lock` ([service.py:172](../../src/graph_triage/service.py#L172)) đã lo phần
  dựng singleton; chỉ cần kiểm forward pass torch có an toàn đa luồng không.

### P3 — Hoãn Part 3 tới lúc điều dưỡng mở ca

33 giây đang được trả trước cho thứ điều dưỡng có thể không đọc. Chuyển sang tính lười ở
`GET /cases/{case_id}`, hoặc chạy nền sau khi đã có nhãn.

- **Phải giữ:** `merge_human_review` ([service.py:322](../../src/graph_triage/service.py#L322)) —
  Part 3 có quyền **bật thêm** `requires_human_review`. Hoãn Part 3 nghĩa là cờ đó tới muộn, phải
  chắc UI điều dưỡng đọc lại được sau khi nó đổi.

### P4 — Gộp lời gọi DeepSeek của fusion  ⚠️ cần đo lại accuracy

`direct` và `fusion` cùng đọc một `summary_text`. Có thể gộp graph extraction vào chung, hoặc thử cho
fusion chạy với graph rỗng và đo lệch nhãn.

- **Đây là chỗ đụng vào công thức đã benchmark.** Không sửa trước khi có bảng đối chiếu nhãn trên
  `golden.csv`, và không sửa mà không có người lâm sàng xem kết quả.

### Không khuyến nghị — gỡ fusion khỏi C6

Xem mục 1.1: nó là nhánh duy nhất hô cấp cứu ở ca `d008b6a9`. Nếu mục tiêu là giảm hạ tầng
(`4Gi` RAM, +1GB image) thì đó là bài toán khác — và lời giải là hạ tầng, không phải gỡ nhánh.

---

## 4. Đo trước, sửa sau — bắt buộc

Mọi con số ở mục 1.3 đo trên **máy local**, nơi fusion còn không nạp được
(`c6_fusion_unavailable: FileNotFoundError ... runs/fusion_full`). Nghĩa là **chưa ai đo nhánh fusion
chạy thật**, kể cả câu "fusion là phần chậm nhất" trong tiền đề ban đầu.

Trước khi sửa:

1. Thêm log timing cho từng nhánh trong `_apply_c6_safety_gate` — mỗi nhánh một
   `latency_ms`, giống định dạng `provider.selected` đang dùng.
2. Thêm `latency_ms` cho `DeepSeekExtractor().extract` tách khỏi forward pass torch, để biết trong
   nhánh fusion phần nào chiếm bao nhiêu.
3. Chạy `python -m scripts.check_nurse_flow --base-url <URL japaneast>` vài ca, đọc log.
4. Chỉ khi bảng số liệu xác nhận thì mới chọn P1-P4.

---

## 5. Test bắt buộc

| Thay đổi | Test |
| --- | --- |
| P1 | Ca không phải cấp cứu vẫn xuất hiện trong `/nurse/queue` — đây là hồi quy của lỗi 2026-08-24 |
| P1 | `graph_decision` cuối cùng vẫn được gắn vào case, không mất khi bệnh nhân đóng tab |
| P2 | Ba nhánh chạy song song cho ra `safety_gate` giống hệt bản tuần tự trên cùng đầu vào |
| P2 | Hai request đồng thời không làm hỏng forward pass torch |
| P3 | `requires_human_review` bật thêm bởi Part 3 vẫn tới được UI điều dưỡng |
| P4 | Bảng đối chiếu nhãn trên `golden.csv`, trước/sau |

---

## 6. Tiêu chí chấp nhận

- Bệnh nhân nhận phản hồi cho lượt chốt phiếu trong **< 3s** (hiện ~35s).
- Ca không phải cấp cứu vào `/nurse/queue` trong **< 60s** kể từ lúc chốt phiếu, và **không bao giờ
  biến mất** trong lúc chờ.
- `safety_gate` sau khi sửa khớp 100% với bản hiện tại trên bộ ca test — trừ P4, vốn phải có bảng
  đối chiếu riêng và người lâm sàng duyệt.
- Có bảng `latency_ms` từng nhánh đo trên bản deploy, không phải local.
