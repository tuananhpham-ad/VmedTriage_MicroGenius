"""Bước 6 - chấm verdict, **chạy blind**. Và **Guard 0c**.

Đây là **guard ngữ nghĩa DUY NHẤT** của thiết kế post-hoc: bốn lớp còn lại đều là so chuỗi, chỉ lớp
này phán đoán được "đoạn trích có THẬT SỰ khẳng định mệnh đề không". Vì thế nó là chỗ không được hạ
chất lượng để tiết kiệm - model yếu gặp đoạn cùng chủ đề là gật `supports`, và khi nó gật thì không
còn gì đứng giữa một trích dẫn sai và màn hình của điều dưỡng.

BLIND NGHĨA LÀ GÌ Ở ĐÂY. Prompt chấm **không hề biết** có một quyết định triage nào tồn tại: không
nhận `triage_label`, không nhận claim khác, không nhận xác suất model. Nó chỉ thấy một mệnh đề và mấy
đoạn trích. Đó là lý do `contradicts` là kết quả có thật chứ không phải một nấc trang trí - một bộ
chấm biết hệ thống đã kết luận gì sẽ tìm cách hợp thức hoá kết luận ấy.

QUY TẮC MỆNH ĐỀ ĐẢO - phần quan trọng nhất của prompt. Mệnh đề dạng *"vắng X thì loại trừ / bớt lo về
Y"* chỉ được `supports` khi đoạn trích **thật sự phát biểu suy luận đó**. Đoạn chỉ liệt kê X như dấu
hiệu cảnh báo của Y là **mệnh đề ĐẢO** - một mệnh đề khác hẳn - và verdict đúng phải là `unsupported`.
Đây là lỗi logic mà gần như mọi hệ RAG-citation đều mắc, vì hai mệnh đề đó dùng gần hệt bộ từ vựng
nên mọi thước đo tương đồng đều chấm chúng giống nhau.

GUARD 0C nằm ở đây chứ không ở `claims.py` vì nó cần đúng thứ phán đoán ngữ nghĩa nói trên: claim có
khẳng định CÙNG mệnh đề với đoạn lập luận gốc không. Nó KHÔNG phá tính blind - câu hỏi chỉ so claim
với `grounded_in`, không hề nhắc tới nhãn. Guard 0a/0b bắt được trường hợp lập luận thuần vắng mặt;
0c là lớp bắt phần còn lại, gồm cả lập luận lẫn lộn có/không.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from src.services.infra.provider_router import ROLE_SOURCE_VERDICT
from src.source_support.index import SearchHit
from src.source_support.llm import CostMeter, SourceSupportLLMError, call_json
from src.source_support.quotes import trim_to_sentences
from src.source_support.retrieval import ClaimEvidence
from src.source_support.schemas import Claim, SourceHit, VerdictResponse

logger = logging.getLogger("vmedtriage.source_support")

SYSTEM_PROMPT = """Bạn là bộ chấm bằng chứng. Bạn đối chiếu MỘT mệnh đề với vài đoạn trích từ tài liệu
y khoa, và nói các đoạn đó có khẳng định mệnh đề hay không.

Bạn KHÔNG biết mệnh đề này đến từ đâu, KHÔNG biết nó dùng để làm gì, và KHÔNG có bệnh nhân nào ở đây.
Đừng suy đoán về những điều đó. Chỉ đọc mệnh đề, đọc các đoạn trích, rồi chấm.

Thang bốn nấc:
- supports    : đoạn trích phát biểu mệnh đề, hoặc phát biểu điều kéo theo trực tiếp mệnh đề.
- partial     : đoạn trích khẳng định một PHẦN của mệnh đề, hoặc khẳng định nó với điều kiện hẹp hơn.
- unsupported : đoạn trích không nói gì đủ để khẳng định mệnh đề. Cùng chủ đề KHÔNG phải là khẳng định.
- contradicts : đoạn trích nói điều ngược lại với mệnh đề.

QUY TẮC QUAN TRỌNG NHẤT - MỆNH ĐỀ ĐẢO:

Nếu mệnh đề có dạng "vắng X thì loại trừ Y" / "không có X nên bớt lo về Y", thì nó CHỈ được chấm
supports khi đoạn trích THẬT SỰ phát biểu chiều suy luận đó.

Một đoạn chỉ liệt kê X như dấu hiệu cảnh báo của Y - kiểu "gọi cấp cứu nếu có X" - là MỆNH ĐỀ ĐẢO. Nó
nói X có mặt thì nguy hiểm; nó KHÔNG nói X vắng mặt thì an toàn. Hai điều đó khác nhau. Trường hợp
này verdict đúng là unsupported, dù đoạn trích nhắc đúng cả X lẫn Y.

Ví dụ phải chấm unsupported:
  Mệnh đề : "Không khó thở và không sưng mặt thì loại trừ được phản vệ."
  Đoạn    : "Anaphylaxis symptoms include swelling of your throat and difficulty breathing.
             Call 999 immediately if you think someone is having an anaphylactic reaction."
  Vì sao  : đoạn nêu hai dấu hiệu đó là cảnh báo NẾU XUẤT HIỆN; nó không hề nói vắng chúng thì
            loại trừ được phản vệ.

CÁC TRƯỜNG PHẢI TRẢ:
- verdict                 : một trong bốn nấc trên.
- verdict_reason          : một câu tiếng Việt, nói rõ đoạn trích khẳng định được gì và không khẳng
                            định được gì. Đừng nhắc lại mệnh đề, hãy nói về đoạn trích.
- best_chunk_id           : id của đoạn trích mà verdict dựa vào. Không đoạn nào dùng được thì để "".
- claim_matches_reasoning : mệnh đề có khẳng định CÙNG một điều với "lap_luan_goc" trong đầu vào
                            không. false khi mệnh đề đã bị viết lệch, đặc biệt khi nó bị lật thành
                            mệnh đề đảo của lập luận gốc.

Trả về DUY NHẤT một JSON object với đúng bốn trường trên."""


def _user_prompt(claim: Claim, candidates: list[SearchHit]) -> str:
    """Đầu vào của bộ chấm. Cố ý KHÔNG có `triage_label`, không có claim khác, không có xác suất model.

    `lap_luan_goc` là `grounded_in` - đoạn lập luận nguyên văn. Nó cần cho Guard 0c, và nó không tiết
    lộ nhãn: nó là một câu lập luận lâm sàng, không phải một kết luận phân loại."""
    payload = {
        "menh_de": claim.claim_en,
        "lap_luan_goc": claim.grounded_in,
        "cac_doan_trich": [
            {"chunk_id": hit.chunk.chunk_id, "publisher": hit.chunk.publisher, "noi_dung": hit.chunk.text}
            for hit in candidates
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def grade(claim: Claim, candidates: list[SearchHit], *, meter: CostMeter | None = None) -> VerdictResponse:
    """Chấm một claim. Không có đoạn trích nào thì không gọi model - không có gì để chấm."""
    if not candidates:
        return VerdictResponse(
            verdict="unsupported",
            verdict_reason="Không tìm được tài liệu nào phù hợp để đối chiếu.",
            claim_matches_reasoning=True,
            best_chunk_id="",
        )
    response = call_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_user_prompt(claim, candidates),
        schema=VerdictResponse,
        role=ROLE_SOURCE_VERDICT,
        meter=meter,
    )
    assert isinstance(response, VerdictResponse)
    return response


def grade_all(
    evidences: list[ClaimEvidence],
    *,
    meter: CostMeter | None = None,
) -> list[tuple[ClaimEvidence, VerdictResponse]]:
    """Chấm mọi claim SONG SONG.

    Các lời gọi độc lập hoàn toàn với nhau (mỗi claim chấm riêng, không claim nào thấy claim khác), và
    bước này chiếm phần lớn thời gian tường của part 3 - chạy nối tiếp là nhân ba độ trễ mà không đổi
    lấy điều gì. Số luồng bằng số claim, tối đa 3 theo trần của schema.

    Một claim chấm hỏng KHÔNG làm hỏng cả ca: nó thành `unsupported` và ghi log. Đây là hướng an toàn
    - `unsupported` chỉ khiến đoạn diễn giải nói rằng không có nguồn, còn để cả ca trượt thì mất luôn
    cả những trích dẫn đã kiểm được."""
    if not evidences:
        return []

    def _grade(evidence: ClaimEvidence) -> tuple[ClaimEvidence, VerdictResponse]:
        try:
            return evidence, grade(evidence.claim, evidence.candidates, meter=meter)
        except SourceSupportLLMError as error:
            logger.warning("source_support.verdict_failed claim=%r reason=%s", evidence.claim.claim_en[:60], error)
            return evidence, VerdictResponse(
                verdict="unsupported",
                verdict_reason="Không chấm được bằng chứng cho mệnh đề này.",
                claim_matches_reasoning=True,
                best_chunk_id="",
            )

    with ThreadPoolExecutor(max_workers=len(evidences)) as pool:
        return list(pool.map(_grade, evidences))


def to_source_hits(evidence: ClaimEvidence, response: VerdictResponse) -> list[SourceHit]:
    """Đoạn trích mà verdict dựa vào, đóng gói để lưu audit.

    Chỉ giữ ĐÚNG chunk bộ chấm chỉ ra, không giữ cả 5 ứng viên: 4 đoạn còn lại không được chấm nên
    gắn verdict của đoạn thứ nhất vào chúng là gán cho chúng một kết luận chưa từng có."""
    chosen = next(
        (hit for hit in evidence.candidates if hit.chunk.chunk_id == response.best_chunk_id),
        evidence.candidates[0] if evidence.candidates else None,
    )
    if chosen is None:
        return []
    return [
        SourceHit(
            url=chosen.chunk.url,
            title=chosen.chunk.title,
            publisher=chosen.chunk.publisher,
            chunk_id=chosen.chunk.chunk_id,
            quote=trim_to_sentences(chosen.chunk.text),
            verdict=response.verdict,
            verdict_reason=response.verdict_reason,
            retrieved_at=chosen.chunk.retrieved_at,
        )
    ]
