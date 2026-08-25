"""Bước 1 - tách claim, và **Guard 0**: lớp kiểm mà đặc tả gốc còn thiếu.

VÌ SAO GUARD 0 TỒN TẠI. Năm lớp guard của thiết kế gốc đều kiểm *claim ↔ nguồn*: domain hợp lệ, fetch
được, quote nằm trong trang, đoạn trích có thật sự khẳng định mệnh đề, URL/quote trong đoạn văn khớp
tập đã verify. Không lớp nào kiểm *claim ↔ QUYẾT ĐỊNH GỐC*. Bước 1 là mắt xích duy nhất nối hai thứ
đó, và trước module này nó không có guard nào - chỉ có một câu dặn trong prompt.

Đây là lỗi thật, không phải lo xa. Lấy ca dị ứng da (`kham_som`), lập luận gốc là *"không khó thở,
mặt không sưng, nên chưa có dấu hiệu phản vệ"*:

* **Bước 1 làm đúng** -> claim "vắng khó thở và sưng mặt thì loại trừ phản vệ", cosine 0.52 với đoạn
  NHS về phản vệ, bước 6 chấm `unsupported` (đoạn trích liệt kê hai dấu hiệu đó như cảnh báo NẾU xuất
  hiện, không hề nói vắng chúng thì loại trừ được) -> đoạn diễn giải nói thẳng là không có nguồn.
* **Bước 1 làm mềm đi** -> claim thành "khó thở và sưng mặt là dấu hiệu cảnh báo phản vệ", cosine
  **0.78** (cao hơn hẳn, vì giờ nó gần như chép lại đoạn trích), bước 6 chấm `supports` - và verdict
  đó ĐÚNG với claim được đưa cho nó. Cả năm guard xanh, output vẫn trích NHS để chống lưng cho một
  lập luận NHS không nói.

Chỗ độc nhất: claim bị làm mềm cho điểm cosine CAO HƠN, nên chỉ số hit-rate trông đẹp lên đúng lúc hệ
thống bớt trung thực.

BA LỚP, XẾP TỪ RẺ TỚI ĐẮT:

* **0a** (`guard_grounded_in`) - `grounded_in` phải là trích nguyên văn của lập luận gốc. Chặn claim
  bịa ra một lý lẽ quyết định chưa từng đưa.
* **0b** (`guard_polarity`) - suy `claim_kind` từ `status` của evidence, bằng CODE. Bắt đúng ca ở
  trên mà không cần model nào.
* **0c** - nằm ở bước 6 (`verdict.py`), vì nó cần phán đoán ngữ nghĩa.

Cả 0a lẫn 0b dùng `normalise_span` của `graph_schema` - đúng hàm mà `llm_decision.py` đang dùng để
chặn evidence bịa. Hai bản sao lệch nhau nghĩa là một chuỗi lọt được ở đây nhưng bị chặn ở kia.
"""

from __future__ import annotations

import json
from typing import Any

from src.graph_triage.graph_schema import normalise_span
from src.services.infra.provider_router import ROLE_CLAIM_SPLITTER
from src.source_support.llm import CostMeter, call_json
from src.source_support.schemas import Claim, ClaimBatch

MAX_CLAIMS = 3


class ClaimGuardError(ValueError):
    """Guard 0 chặn một claim. KHÔNG bắt rồi bỏ qua: claim không neo được vào quyết định gốc thì mọi
    trích dẫn dựng trên nó đều vô nghĩa, và một đoạn văn thiếu trích dẫn tốt hơn hẳn một đoạn văn
    trích dẫn sai chỗ."""


SYSTEM_PROMPT = """Bạn là bộ tách mệnh đề lâm sàng. Bạn KHÔNG chẩn đoán và KHÔNG đánh giá mức độ khẩn.

Đầu vào là phần lập luận của một đánh giá đã hoàn tất, kèm danh sách dấu hiệu và yếu tố nguy cơ đã
ghi nhận. Nhiệm vụ: viết lại lập luận đó thành tối đa 3 MỆNH ĐỀ LÂM SÀNG TỔNG QUÁT để tra cứu y văn.

Vì sao phải tổng quát: không tài liệu y khoa nào nói về bệnh nhân cụ thể này. "Bệnh nhân này cần cấp
cứu" là thứ không tra được; "co giật do sốt ở trẻ dưới 5 tuổi kèm không đáp ứng kéo dài sau cơn cần
được đánh giá cấp cứu" thì tra được.

Mỗi mệnh đề gồm bốn trường:
- claim_en: bản tiếng Anh, dùng để tra tài liệu.
- claim_vi: bản tiếng Việt, dùng để hiển thị. Cùng nội dung với claim_en.
- claim_kind: một trong red_flag | rule_out | temporal | risk_modifier | management.
- grounded_in: đoạn văn CHÉP NGUYÊN VĂN từ phần lập luận đầu vào mà mệnh đề này rút ra.

QUY TẮC BẮT BUỘC:

1. grounded_in phải là một đoạn liên tục, chép ĐÚNG TỪNG KÝ TỰ từ phần lập luận đầu vào. Không tóm
   tắt, không diễn đạt lại, không ghép hai đoạn rời nhau. Đây là trường bị máy đối chiếu.

2. Nếu lập luận dựa vào việc VẮNG MẶT một dấu hiệu ("không khó thở nên chưa đến mức cấp cứu"), thì:
   - claim_kind PHẢI là rule_out;
   - claim_en phải viết ĐÚNG suy luận đang được dựa vào, tức là chiều "vắng X thì loại trừ / bớt lo
     về Y".
   TUYỆT ĐỐI KHÔNG được làm mềm thành "X là dấu hiệu cảnh báo của Y". Đó là MỆNH ĐỀ ĐẢO - một mệnh đề
   khác hẳn, và viết như vậy là trình bày sai lập luận thật của đánh giá.

3. Chỉ viết lại điều lập luận đầu vào đã nói. Không thêm dấu hiệu, không thêm suy luận, không thêm
   chi tiết y khoa nào không có trong đầu vào.

3b. VIẾT Ở MỨC KHÁI QUÁT CỦA SÁCH HƯỚNG DẪN, không ở mức của ca bệnh. Mệnh đề sẽ được đem đối chiếu
   với tài liệu y khoa, mà tài liệu viết theo NHÓM dấu hiệu và NHÓM thuốc chứ không theo từng ca.
   Mệnh đề càng bám sát câu chữ của ca thì càng không tìm được tài liệu nào nói về nó.
   - Dùng tên nhóm thay vì chi tiết riêng của ca: "phát ban do thuốc" thay vì "nổi mẩn sau khi uống
     kháng sinh 2 ngày"; "trẻ dưới 5 tuổi" thay vì "cháu 14 tháng".
   - Bỏ mốc thời gian, liều lượng, số lần cụ thể của ca trừ khi chính chúng là điều cần tra.
   - Nêu HỆ QUẢ LÂM SÀNG (cần đánh giá cấp cứu / cần khám sớm / theo dõi được tại nhà) chứ đừng chỉ
     mô tả lại triệu chứng - một mệnh đề chỉ mô tả thì không có gì để tài liệu ủng hộ hay bác bỏ.

4. Không nhắc tên bệnh cụ thể như một kết luận, không nêu hướng điều trị, không nêu liều thuốc.

Trả về DUY NHẤT một JSON object dạng:
{"claims": [{"claim_en": "...", "claim_vi": "...", "claim_kind": "...", "grounded_in": "..."}]}"""


def build_user_prompt(decision: dict[str, Any]) -> str:
    """Dựng phần đầu vào cho bước 1.

    CỐ Ý KHÔNG GỬI `triage_label`, `model_assessments` hay xác suất model. Nhãn không giúp gì cho việc
    tách mệnh đề, nhưng biết nhãn thì model có xu hướng viết mệnh đề sao cho hợp với nhãn - đúng thứ
    thiết kế này đang cố đo chứ không phải cố tạo ra."""
    payload = {
        "lap_luan": decision.get("decision_summary", ""),
        "phan_khong_chac_chan": decision.get("uncertainty_summary", ""),
        "dau_hieu_ghi_nhan": [
            {
                "khai_niem": item.get("concept"),
                "trang_thai": item.get("status"),
                "trich_dan": item.get("source_span"),
            }
            for item in decision.get("evidence", [])
        ],
        "yeu_to_nguy_co": [
            {"yeu_to": item.get("factor"), "trich_dan": item.get("source_span")}
            for item in decision.get("risk_modifiers", [])
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------- Guard 0a ----------


def guard_grounded_in(claims: list[Claim], decision: dict[str, Any]) -> None:
    """`grounded_in` phải nằm nguyên văn trong lập luận gốc. Sai -> raise.

    Đây đúng cơ chế mà `llm_decision.py` dùng để chặn evidence bịa: chuẩn hoá khoảng trắng/hoa-thường
    rồi đòi quan hệ substring. Nó không đòi model trung thực - nó làm việc nói dối bất khả thi ở đúng
    trường này."""
    haystacks = [
        normalise_span(str(decision.get(key, "") or ""))
        for key in ("decision_summary", "uncertainty_summary", "model_agreement_summary")
    ]
    for claim in claims:
        needle = normalise_span(claim.grounded_in)
        if not needle:
            raise ClaimGuardError(f"Claim {claim.claim_vi!r} có grounded_in rỗng.")
        if not any(needle in hay for hay in haystacks if hay):
            raise ClaimGuardError(
                "Guard 0a: grounded_in không phải trích nguyên văn của lập luận gốc.\n"
                f"  claim      : {claim.claim_vi!r}\n"
                f"  grounded_in: {claim.grounded_in!r}\n"
                "Bước tách claim đã bịa ra một lý lẽ mà quyết định chưa từng đưa."
            )


# ---------- Guard 0b ----------


def guard_polarity(claims: list[Claim], evidence: list[dict[str, Any]]) -> None:
    """Suy `claim_kind` từ `status` của evidence, bằng code. Đây là lớp bắt được ca dị ứng da.

    QUY TẮC: lập luận CHỈ dựa trên dấu hiệu VẮNG MẶT thì mệnh đề rút ra bắt buộc là `rule_out`. Khai
    khác đi nghĩa là bước 1 đã lật chiều mệnh đề.

    ĐIỀU KIỆN "CHỈ" LÀ CỐ Ý VÀ QUAN TRỌNG. Một đoạn lập luận nhắc cả dấu hiệu có lẫn dấu hiệu không
    ("sốt cao kèm co giật, không có ban xuất huyết, cần đánh giá cấp cứu") thì mệnh đề chính đáng có
    thể là `red_flag` về sốt và co giật - bắt nó thành `rule_out` là chặn nhầm. Cổng này vì thế chỉ
    đóng khi lập luận KHÔNG dựa vào một dấu hiệu có mặt nào. Trường hợp lẫn lộn do Guard 0c ở bước 6
    xử lý, vì nó cần phán đoán ngữ nghĩa chứ không suy ra được bằng code.

    `status` lấy từ `Status = Literal["present", "absent", "uncertain"]` của `patient_graph_v1`;
    `uncertain` không tính vào cả hai phía - chưa rõ thì không suy ra được chiều nào."""
    absent = [
        normalise_span(str(item.get("source_span", "")))
        for item in evidence
        if item.get("status") == "absent"
    ]
    present = [
        normalise_span(str(item.get("source_span", "")))
        for item in evidence
        if item.get("status") == "present"
    ]

    for claim in claims:
        reasoning = normalise_span(claim.grounded_in)
        leans_on_absent = sorted({span for span in absent if span and span in reasoning})
        leans_on_present = sorted({span for span in present if span and span in reasoning})
        if leans_on_absent and not leans_on_present and claim.claim_kind != "rule_out":
            raise ClaimGuardError(
                "Guard 0b: lập luận chỉ dựa trên dấu hiệu VẮNG MẶT nhưng claim khai "
                f"claim_kind={claim.claim_kind!r} thay vì 'rule_out'.\n"
                f"  claim       : {claim.claim_en!r}\n"
                f"  grounded_in : {claim.grounded_in!r}\n"
                f"  dấu hiệu vắng mặt được dựa vào: {leans_on_absent}\n"
                "Đây là dấu hiệu bước tách claim đã lật ngược mệnh đề (mệnh đề đảo)."
            )


# ---------- điều phối ----------


def extract_claims(decision: dict[str, Any], *, meter: CostMeter | None = None) -> list[Claim]:
    """Bước 1 + Guard 0a + Guard 0b. Trả về các claim đã neo được vào quyết định gốc.

    Raise `ClaimGuardError` khi guard chặn, `SourceSupportLLMError` khi model không cho ra JSON hợp
    lệ. Cả hai đều để người gọi ở tầng trên quyết định - part 3 là best-effort, nhưng "best-effort"
    nghĩa là bỏ phần trích nguồn của ca đó, KHÔNG phải đi tiếp với claim hỏng."""
    batch = call_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(decision),
        schema=ClaimBatch,
        role=ROLE_CLAIM_SPLITTER,
        meter=meter,
    )
    claims = list(batch.claims)[:MAX_CLAIMS]
    guard_grounded_in(claims, decision)
    guard_polarity(claims, decision.get("evidence", []))
    return claims
