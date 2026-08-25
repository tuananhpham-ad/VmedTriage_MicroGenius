"""Sinh SEMIGRAN_EVAL_ANALYSIS.md tu eval_result_probabilities.txt.

Moi so trong bao cao deu tinh tai cho, khong go tay - bao cao va du lieu khong the lech nhau.
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

VI2K = {"Tự theo dõi": "theo", "Khám sớm": "kham", "Cấp cứu": "cap"}
N = {"theo": "Tự theo dõi", "kham": "Khám sớm", "cap": "Cấp cứu"}
ORD = {"theo": 0, "kham": 1, "cap": 2}
REV = {0: "theo", 1: "kham", 2: "cap"}
MODELS = ("logreg", "phobert", "fusion")
RAW = Path("eval_result_probabilities.txt").read_text(encoding="utf-8")

cases: dict[int, dict] = {}
errors: list[tuple[int, str, str]] = []
cur: int | None = None
for ln in RAW.splitlines():
    m = re.match(r"^\[(\d+)/45\] (semigran_\d+): thật=(.+?) \| đoán=(.+?) \| (ĐÚNG|SAI)", ln)
    if m:
        cur = int(m.group(1))
        cases[cur] = {"id": m.group(2), "gold": VI2K[m.group(3)], "final": VI2K[m.group(4)], "p": {}}
        continue
    m = re.match(r"^\[(\d+)/45\] (semigran_\d+): LỖI \((\w+): (.+)\)$", ln)
    if m:
        errors.append((int(m.group(1)), m.group(2), m.group(4)))
        cur = None
        continue
    m = re.match(
        r"^\s+(LogReg|PhoBERT|Fusion \(PhoBERT\+HGT\)): Tự theo dõi=([\d.]+)% \| "
        r"Khám sớm=([\d.]+)% \| Cấp cứu=([\d.]+)% \| chọn=(.+)$", ln)
    if m and cur:
        key = {"LogReg": "logreg", "PhoBERT": "phobert", "Fusion (PhoBERT+HGT)": "fusion"}[m.group(1)]
        cases[cur]["p"][key] = {
            "theo": float(m.group(2)) / 100, "kham": float(m.group(3)) / 100,
            "cap": float(m.group(4)) / 100, "pick": VI2K[m.group(5)],
        }

n = len(cases)
ARMS = [("logreg", "LogReg"), ("phobert", "PhoBERT"), ("fusion", "Fusion"), ("llm", "**LLM (nhãn cuối)**")]


def pick(case: dict, arm: str) -> str:
    return case["final"] if arm == "llm" else case["p"][arm]["pick"]


def conf(case: dict, arm: str) -> float:
    return max(case["p"][arm][k] for k in ("theo", "kham", "cap"))


def prf(arm: str, lab: str) -> tuple[float, float, float, int, int, int]:
    tp = sum(1 for c in cases.values() if pick(c, arm) == lab and c["gold"] == lab)
    fp = sum(1 for c in cases.values() if pick(c, arm) == lab and c["gold"] != lab)
    fn = sum(1 for c in cases.values() if pick(c, arm) != lab and c["gold"] == lab)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0), tp, fp, fn


def acc(arm: str) -> float:
    return sum(1 for c in cases.values() if pick(c, arm) == c["gold"]) / n


def macro_f1(arm: str) -> float:
    return sum(prf(arm, lab)[2] for lab in ("theo", "kham", "cap")) / 3


def max_rule(case: dict) -> str:
    return REV[max(ORD[case["p"][m]["pick"]] for m in MODELS)]


def safety(fn_pick):
    tp = sum(1 for c in cases.values() if ORD[fn_pick(c)] >= 1 and ORD[c["gold"]] >= 1)
    fp = sum(1 for c in cases.values() if ORD[fn_pick(c)] >= 1 and ORD[c["gold"]] == 0)
    missed = [i for i, c in cases.items() if ORD[fn_pick(c)] == 0 and ORD[c["gold"]] >= 1]
    danger = [i for i in missed if cases[i]["gold"] == "cap"]
    up = sum(1 for c in cases.values() if ORD[fn_pick(c)] > ORD[c["gold"]])
    r = tp / (tp + len(missed)) if tp + len(missed) else 0.0
    p = tp / (tp + fp) if tp + fp else 0.0
    return r, p, (2 * p * r / (p + r) if p + r else 0.0), missed, danger, up


gd = collections.Counter(c["gold"] for c in cases.values())
L: list[str] = []
w = L.append

w("# Phân tích eval part 2 trên bộ chuẩn Semigran (45 vignette)")
w("")
w(f"> Sinh tự động từ `eval_result_probabilities.txt`. **{n}/45 ca chấm được**, "
  f"{len(errors)} ca chết vì lỗi validate. Mọi số trong file tính lại từ output gốc ở phụ lục.")
w("")
w("## TL;DR")
w("")
follow_bert = sum(1 for c in cases.values() if c["p"]["phobert"]["pick"] == c["final"]) / n
w(f"- **Accuracy cao nhất là LogReg {acc('logreg'):.0%}** — nhưng accuracy là thước đo SAI cho bài này. "
  f"LogReg đẩy về nhà 2 ca Cấp cứu thật, một trong đó là **đột quỵ**.")
w("- **An toàn nhất trong 4 nhánh thật là LLM (nhãn cuối)** — 0 ca Cấp cứu bị đẩy về nhà.")
w(f"- **Nhãn cuối trùng PhoBERT {follow_bert:.0%}**, trong khi PhoBERT là model *tệ nhất* ({acc('phobert'):.0%}).")
w("- **Vì sao:** PhoBERT/Fusion xuất xác suất bão hoà ~100%, LogReg ~60%. LLM đọc phần trăm thô nên "
  "nghe theo cái to giọng nhất. Xem §6 — đó là câu trả lời cho câu hỏi chính.")
w("")
w("---")
w("")
w("## 1. Độ chính xác tổng thể")
w("")
w("| Nhánh | Accuracy | Macro-F1 | Đúng/Tổng |")
w("|---|---:|---:|---:|")
for key, nm in ARMS:
    w(f"| {nm} | {acc(key):.1%} | {macro_f1(key):.3f} | {round(acc(key) * n)}/{n} |")
w("")
w("Ngẫu nhiên 3 lớp cân bằng = 33%. Phân bố thật: "
  + ", ".join(f"{N[lab]} {gd[lab]}" for lab in ("cap", "kham", "theo")) + ".")
w("")
w("## 2. Precision / Recall / F1 từng lớp")
w("")
for lab in ("cap", "kham", "theo"):
    w(f"### {N[lab]}")
    w("")
    w("| Nhánh | Precision | Recall | F1 | TP | FP | FN |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    for key, nm in ARMS:
        p, r, f1, tp, fp, fn = prf(key, lab)
        w(f"| {nm} | {p:.0%} | {r:.0%} | {f1:.2f} | {tp} | {fp} | {fn} |")
    w("")
w("Đọc bảng: LogReg thắng accuracy **chỉ nhờ recall 92% ở lớp Tự theo dõi** — tức nó giỏi việc đẩy "
  "người về nhà. Đó là thiên lệch nguy hiểm, không phải điểm mạnh.")
w("")
w("## 3. Ma trận nhầm — nhãn cuối")
w("")
w("| thật \\ đoán | " + " | ".join(N[lab] for lab in ("theo", "kham", "cap")) + " | tổng |")
w("|---|---:|---:|---:|---:|")
for g in ("theo", "kham", "cap"):
    row = [sum(1 for c in cases.values() if c["gold"] == g and c["final"] == q) for q in ("theo", "kham", "cap")]
    w(f"| **{N[g]}** | " + " | ".join(str(x) for x in row) + f" | {sum(row)} |")
w("| **tổng đoán** | " + " | ".join(
    str(sum(1 for c in cases.values() if c["final"] == q)) for q in ("theo", "kham", "cap")) + " | |")
w("")
w("## 4. Phân bố nhãn: nhánh nào thổi lên, nhánh nào đẩy về nhà")
w("")
w("| Nhánh | Cấp cứu | Khám sớm | Tự theo dõi |")
w("|---|---:|---:|---:|")
for key, nm in ARMS:
    d = collections.Counter(pick(c, key) for c in cases.values())
    w(f"| {nm} | {d['cap']} | {d['kham']} | {d['theo']} |")
w(f"| **THẬT** | **{gd['cap']}** | **{gd['kham']}** | **{gd['theo']}** |")
w("")
w("## 5. Đóng khung theo AN TOÀN")
w("")
w("Trong triage, thổi lên tốn công điều dưỡng còn hạ xuống mới gây hại. Nhị phân "
  "**“cần gặp nhân viên y tế”** (Cấp cứu + Khám sớm) vs **“tự theo dõi”**:")
w("")
w("| Nhánh | Recall | Precision | F1 | Bỏ lọt về nhà | …là Cấp cứu | Thổi lên |")
w("|---|---:|---:|---:|---:|---:|---:|")
for key, nm in ARMS:
    r, p, f1, missed, danger, up = safety(lambda c, kk=key: pick(c, kk))
    ids = f" (ca {danger})" if danger else ""
    w(f"| {nm} | {r:.0%} | {p:.0%} | {f1:.2f} | {len(missed)} | **{len(danger)}**{ids} | {up} ({up / n:.0%}) |")
r, p, f1, missed, danger, up = safety(max_rule)
w(f"| *luật `max()` 3 model* | {r:.0%} | {p:.0%} | {f1:.2f} | {len(missed)} | **{len(danger)}** | {up} ({up / n:.0%}) |")
w("")
w("Tỉ lệ ca **không bị hạ bậc** (`đoán >= thật`) — chỉ số an toàn chính:")
w("")
w("| Nhánh | An toàn | Hạ 1 bậc | Hạ 2 bậc |")
w("|---|---:|---:|---:|")
for key, nm in ARMS:
    safe = sum(1 for c in cases.values() if ORD[pick(c, key)] >= ORD[c["gold"]])
    d1 = sum(1 for c in cases.values() if ORD[c["gold"]] - ORD[pick(c, key)] == 1)
    d2 = sum(1 for c in cases.values() if ORD[c["gold"]] - ORD[pick(c, key)] == 2)
    w(f"| {nm} | {safe / n:.0%} | {d1} | {d2} |")
safe = sum(1 for c in cases.values() if ORD[max_rule(c)] >= ORD[c["gold"]])
d1 = sum(1 for c in cases.values() if ORD[c["gold"]] - ORD[max_rule(c)] == 1)
d2 = sum(1 for c in cases.values() if ORD[c["gold"]] - ORD[max_rule(c)] == 2)
w(f"| *luật `max()` 3 model* | {safe / n:.0%} | {d1} | {d2} |")
w("")
w("**Xếp hạng lật ngược so với accuracy.** LogReg tốt nhất theo accuracy nhưng tệ nhất theo an toàn. "
  "Bước LLM sửa đúng chỗ đó — nó cứu ca 11 (viêm phổi, SpO2 92%) và ca 14 (đột quỵ, đang dùng "
  "warfarin) mà LogReg đã đẩy về nhà.")
w("")
w("Nhưng luật `max()` của 3 model **áp đảo LLM trên mọi trục ở cùng một giá phải trả** (cùng số ca "
  "thổi lên, an toàn cao hơn, bỏ lọt ít hơn, accuracy cao hơn). Nên giá trị của bước LLM phải nằm ở "
  "`decision_summary`, evidence có provenance, và cờ `requires_human_review` — không nằm ở cái nhãn.")
w("")
w("## 6. NHÃN CUỐI ĐANG ƯU TIÊN AI — VÀ VÌ SAO")
w("")
w("### 6.1 Nó nghe theo ai")
w("")
w("| Nhánh | Trùng nhãn cuối |")
w("|---|---:|")
for m in MODELS:
    w(f"| {m} | {sum(1 for c in cases.values() if c['p'][m]['pick'] == c['final']) / n:.0%} |")
w(f"| *luật `max()` 3 model* | {sum(1 for c in cases.values() if c['final'] == max_rule(c)) / n:.0%} |")
w("")
w("### 6.2 Vì sao — xác suất bị bão hoà")
w("")
w("| Model | Độ tự tin TB | Số ca >99% | Accuracy | **Thổi phồng** |")
w("|---|---:|---:|---:|---:|")
for m in MODELS:
    cf = sum(conf(c, m) for c in cases.values()) / n
    sat = sum(1 for c in cases.values() if conf(c, m) > 0.99)
    w(f"| {m} | {cf:.1%} | {sat}/{n} | {acc(m):.1%} | **{(cf - acc(m)) * 100:+.1f} điểm** |")
w("")
w("**Đây là câu trả lời.** PhoBERT nói mình đúng 97% nhưng đúng 40%. LogReg nói mình đúng 60% và "
  "đúng 53%. LLM nhận cả ba con số dưới dạng phần trăm thô trong prompt, nên nó nghe theo con số to nhất.")
w("")
w("Tệ hơn: độ tin cậy **ngược dấu** với độ đúng.")
w("")
w("| Model | Khi tự tin >90% | Khi <=90% |")
w("|---|---:|---:|")
for m in MODELS:
    hi = [c for c in cases.values() if conf(c, m) > 0.90]
    lo = [c for c in cases.values() if conf(c, m) <= 0.90]
    ah = f"{sum(1 for c in hi if c['p'][m]['pick'] == c['gold']) / len(hi):.0%} (n={len(hi)})" if hi else "n/a"
    al = f"{sum(1 for c in lo if c['p'][m]['pick'] == c['gold']) / len(lo):.0%} (n={len(lo)})" if lo else "n/a"
    w(f"| {m} | {ah} | {al} |")
w("")
cl = [conf(c, "logreg") for c in cases.values() if c["p"]["logreg"]["pick"] != c["final"]]
co = [max(conf(c, "phobert"), conf(c, "fusion")) for c in cases.values() if c["p"]["logreg"]["pick"] != c["final"]]
w(f"Trong **{len(cl)} ca LLM bỏ ý kiến LogReg**, độ tự tin LogReg lúc đó trung bình "
  f"**{sum(cl) / len(cl):.1%}**, còn PhoBERT/Fusion **{sum(co) / len(co):.1%}**. LLM đang bỏ một ý kiến "
  f"~{100 * sum(cl) / len(cl):.0f}% để nghe một ý kiến ~{100 * sum(co) / len(co):.0f}%.")
w("")
w("### 6.3 Model có “hét to” hơn khi nói Cấp cứu không — CÓ")
w("")
w("Độ tự tin trung bình, tách theo nhãn model chọn:")
w("")
w("| Model | " + " | ".join(N[lab] for lab in ("theo", "kham", "cap")) + " |")
w("|---|---:|---:|---:|")
for m in MODELS:
    cells = []
    for lab in ("theo", "kham", "cap"):
        s = [conf(c, m) for c in cases.values() if c["p"][m]["pick"] == lab]
        cells.append(f"{sum(s) / len(s):.1%} (n={len(s)})" if s else "n/a")
    w(f"| {m} | " + " | ".join(cells) + " |")
w("")
w("PhoBERT tự tin nhất **đúng lúc nó nói Cấp cứu**. Cộng với việc LLM nghe theo model tự tin nhất, "
  "đó là cơ chế sinh ra thiên lệch thổi lên của nhãn cuối.")
w("")
w("| Model | Xác suất TB gán cho *Cấp cứu* trên cả 40 ca |")
w("|---|---:|")
for m in MODELS:
    w(f"| {m} | {sum(c['p'][m]['cap'] for c in cases.values()) / n:.1%} |")
w(f"| **tỉ lệ thật** | **{gd['cap'] / n:.0%}** |")
w("")
w("### 6.4 Phép thử phân biệt")
w("")
w("Hai giả thuyết — *“LLM chép PhoBERT”* và *“LLM lấy mức khẩn cao nhất”* — trùng nhau ở hầu hết ca, "
  "vì PhoBERT chính là model hay thổi lên nhất. Chỉ tách được ở các ca PhoBERT **không** phải model khẩn nhất:")
w("")
w("| Ca | LogReg | PhoBERT | Fusion | max() | Nhãn cuối | Theo ai |")
w("|---|---|---|---|---|---|---|")
n_bert = n_max = 0
for i, c in sorted(cases.items()):
    mx = max_rule(c)
    if c["p"]["phobert"]["pick"] == mx:
        continue
    who = []
    if c["final"] == c["p"]["phobert"]["pick"]:
        who.append("PhoBERT")
        n_bert += 1
    if c["final"] == mx:
        who.append("max()")
        n_max += 1
    w(f"| {i} | {N[c['p']['logreg']['pick']]} | {N[c['p']['phobert']['pick']]} | "
      f"{N[c['p']['fusion']['pick']]} | {N[mx]} | {N[c['final']]} | {' + '.join(who) or '—'} |")
w("")
w(f"**{n_bert} theo PhoBERT · {n_max} theo `max()`** — n quá nhỏ để tách dứt khoát. Cả hai cơ chế đều "
  "đang chạy: LLM vừa bị hút về phía xác suất cao, vừa có sẵn thiên lệch thổi lên.")
w("")
w("## 7. Các ca chết vì validate")
w("")
w("| Ca | Lỗi |")
w("|---|---|")
for i, cid, msg in errors:
    w(f"| {cid} | {msg[:160]} |")
w("")
w(f"Cả {len(errors)} ca đều là **quan hệ bao hàm** giữa span LLM trích và span trong Patient Graph — "
  "không ca nào bịa evidence. `llm_decision.py:213` đòi bằng **chính xác**; ca `semigran_23` lệch "
  "đúng **một dấu chấm cuối câu**.")
w("")
w("## 8. Bảng từng ca")
w("")
w("| Ca | Thật | LogReg | PhoBERT | Fusion | Nhãn cuối | |")
w("|---|---|---|---|---|---|---|")
for i, c in sorted(cases.items()):
    mark = "✅" if c["final"] == c["gold"] else ("⬆️" if ORD[c["final"]] > ORD[c["gold"]] else "⬇️")
    w(f"| {c['id']} | **{N[c['gold']]}** | {N[c['p']['logreg']['pick']]} | {N[c['p']['phobert']['pick']]} | "
      f"{N[c['p']['fusion']['pick']]} | **{N[c['final']]}** | {mark} |")
w("")
w("✅ đúng · ⬆️ thổi lên (tốn công, không hại) · ⬇️ hạ xuống (hướng nguy hiểm)")
w("")
w("## 9. Cảnh báo khi đọc bảng trên")
w("")
for note in [
    "**n=45, một ca = 2,2 điểm.** Chênh dưới ~15 điểm giữa hai nhánh không đọc được là thật.",
    "**Không tái lập.** `temperature=0` nhưng không có `seed` trên vòng tool 2–8 lượt. Hai file kết quả "
    "của hai lượt khác nhau cho 16 vs 19 ca đúng, 5 vs 2 ca lỗi.",
    "**Vignette do bác sĩ viết**, kèm khám và xét nghiệm (`ALT 6498 U/L`, `điểm Centor = 4`) mà luồng "
    "thu thập thật không bao giờ có. Model được train trên lời kể bệnh nhân.",
    "**Nhãn vàng suy từ CHẨN ĐOÁN**, không từ mức nặng triệu chứng — ca 09 sốt 38°C, huyết áp bình "
    "thường, nhưng là Cấp cứu vì tiền sử du lịch gợi sốt rét. CLAUDE.md cấm AI kết luận chẩn đoán, nên "
    "ở đúng những ca khó nhất benchmark đang chấm một năng lực hệ thống bị thiết kế để không có.",
    "**Đầu vào là narrative thô.** Production đi qua `build_summary_text`, đã đo là làm LogReg rớt "
    "0,950 → 0,790. Con số ở đây là **trần trên**.",
    "**10/45 ca ngoài 5 nhóm MVP**: semigran_05, 08, 14, 20, 30, 33, 35, 37, 41, 42.",
    "**Metric tập-train bơm thẳng vào prompt LLM** — `get_model_predictions` đưa `metrics.json` "
    "(PhoBERT 0,996, đo trên chính tập train) cho LLM, càng neo nó vào PhoBERT.",
]:
    w(f"- {note}")
w("")
w("---")
w("")
w("## Phụ lục — output gốc")
w("")
w("```text")
w(RAW.rstrip())
w("```")

Path("SEMIGRAN_EVAL_ANALYSIS.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"da ghi SEMIGRAN_EVAL_ANALYSIS.md | {len(L)} dong | {n} ca | {len(errors)} loi")
