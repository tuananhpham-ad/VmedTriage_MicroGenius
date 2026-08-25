"""`DialoguePolicy` — quyết định NÓI GÌ ở lượt này, dưới dạng BẢNG TRA CỨU thuần code.

Ba trách nhiệm tách rời (§6.1 của `_guidance/what_to_do_next.md`), đừng gộp:

- `stage_machine` + `ranking` chọn CỤM (đã có);
- `DialoguePolicy` (module này) tạo `ResponsePlan`: công nhận gì, trả lời câu hỏi ngược ra sao, hỏi
  mấy ý, có được đi tiếp không;
- renderer chỉ chuyển `ResponsePlan` thành tiếng Việt - không chọn field, không thêm câu hỏi y khoa.

**Vì sao là BẢNG chứ không phải chuỗi `if`.** Sau khi bỏ mọi tính thích ứng đến từ model, toàn bộ sự
tự nhiên của hệ thống dồn vào ranking (§8.3) và số nhánh của policy này. Số nhánh phình theo
`dialogue_act × trạng thái cụm × trạng thái protocol`. Khai báo dạng bảng vì:

- thiếu tổ hợp nào nhìn ra ngay, thay vì lẩn trong nhánh `else`;
- test được bằng cách DUYỆT TOÀN BẢNG (`test_every_dialogue_act_has_a_policy_row`), không phải nghĩ
  ra từng ca;
- thêm một `dialogue_act` mới là thêm một HÀNG, không phải sửa một hàm dài.

Chiều `dialogue_act` là bảng đủ (8/8 hàng). Hai chiều còn lại - protocol vừa đổi, cụm đang hỏi lại -
là **trường tường minh** trên `ResponsePlan` chứ không nhân thành 32 hàng gần như trùng nhau; chúng
chỉ THÊM một câu chuyển hướng hoặc bật cờ diễn đạt lại, không đổi bản chất hành động.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.services.symptom_protocol import stage_machine
from src.services.symptom_protocol.models import QuestionCluster
from src.services.symptom_protocol.protocol import SymptomProtocol


class DialogueAct(str, Enum):
    """Tin nhắn vừa rồi thuộc loại gì. Đây là `dialogue_act` của §4.1, hiện suy ra từ nhãn
    `answer_quality` mà extractor đã trả về - KHÔNG tốn thêm một lời gọi model nào."""

    ANSWER = "answer"
    PARTIAL_ANSWER = "partial_answer"
    CORRECTION = "correction"
    NEW_SYMPTOM = "new_symptom"
    ASKS_CLARIFICATION = "asks_clarification"
    CANNOT_ANSWER = "cannot_answer"
    OFF_TOPIC = "off_topic"
    GREETING = "greeting"


# `answer_quality` (nhãn extractor đang trả) -> `DialogueAct`. Giữ hai từ vựng vì chúng có vòng đời
# khác nhau: `answer_quality` là hợp đồng với model và phải đổi cùng prompt; `DialogueAct` là hợp
# đồng nội bộ của policy. Nhãn lạ rơi về `ANSWER` - an toàn nhất, vì nó không kích hoạt nhánh UX đặc
# biệt nào và quyết định retry thật sự vẫn do CODE tính trên `answers`.
_QUALITY_TO_ACT: dict[str, DialogueAct] = {
    "answered": DialogueAct.ANSWER,
    "partial": DialogueAct.PARTIAL_ANSWER,
    "correction": DialogueAct.CORRECTION,
    "asks_question": DialogueAct.ASKS_CLARIFICATION,
    "evasive": DialogueAct.CANNOT_ANSWER,
    "non_answer": DialogueAct.OFF_TOPIC,
}


@dataclass(frozen=True, slots=True)
class ActPolicy:
    """Một HÀNG của bảng. Mọi trường đều là dữ liệu - không có hàm, không có nhánh."""

    acknowledge_instruction: str
    """HƯỚNG DẪN cho renderer về việc công nhận, KHÔNG phải văn bản gửi người bệnh.

    Tách khỏi dữ kiện là bắt buộc, không phải sạch sẽ hình thức: bản đầu nhét cả tiền tố ngôi thứ ba
    ("Người bệnh vừa cho biết") vào cùng một chuỗi với dữ kiện, và model chép nguyên văn tiền tố đó
    ra tin nhắn - người bệnh đọc được một câu nói VỀ mình thay vì nói VỚI mình (đo được trên
    transcript thật với deepseek-chat). Rỗng = lượt này không công nhận gì."""

    answer_user_question: str = ""
    """Trả lời câu hỏi NGƯỢC của người bệnh, đặt TRƯỚC câu hỏi mới (§6.2). Chỉ dùng cho
    `asks_clarification`: không được xin lỗi rồi lặp nguyên văn câu cũ."""

    rephrase: bool = False
    """Yêu cầu renderer diễn đạt KHÁC HẲN lần trước, thay vì đọc lại cùng một câu."""

    max_questions: int = 1
    """Trần số ý hỏi trong một tin nhắn. `output_guard` kiểm lại con số này trên văn bản đã sinh."""

    simplify: bool = True
    """Dùng từ ngữ đơn giản hơn ở lượt này."""


# BẢNG. Phải phủ ĐỦ mọi `DialogueAct` - có test duyệt toàn bảng canh việc đó.
DIALOGUE_POLICY: dict[DialogueAct, ActPolicy] = {
    DialogueAct.ANSWER: ActPolicy(
        acknowledge_instruction="",
        simplify=False,
    ),
    DialogueAct.PARTIAL_ANSWER: ActPolicy(
        # Mới trả lời một phần: công nhận phần đã có rồi hỏi ĐÚNG phần còn thiếu, không hỏi lại cả cụm.
        acknowledge_instruction=(
            "Người bệnh mới trả lời được một phần. Công nhận phần đã có rồi hỏi ĐÚNG phần còn thiếu, "
            "đừng hỏi lại cả cụm."
        ),
        simplify=False,
    ),
    DialogueAct.CORRECTION: ActPolicy(
        # Đính chính là lúc dễ mất lòng tin nhất: người bệnh cần thấy hệ thống ĐÃ ghi nhận bản sửa.
        acknowledge_instruction=(
            "Người bệnh vừa ĐÍNH CHÍNH thông tin. Nói rõ là bạn đã ghi nhận bản sửa MỚI NHẤT trước khi "
            "hỏi tiếp - đây là lúc dễ mất lòng tin nhất."
        ),
        simplify=False,
    ),
    DialogueAct.NEW_SYMPTOM: ActPolicy(
        acknowledge_instruction="Người bệnh vừa nêu thêm một triệu chứng mới. Công nhận điều đó trước khi hỏi tiếp.",
        simplify=False,
    ),
    DialogueAct.ASKS_CLARIFICATION: ActPolicy(
        acknowledge_instruction="",
        answer_user_question=(
            "Người bệnh đang hỏi ngược lại. Hãy GIẢI THÍCH NGẮN mục đích của câu hỏi vừa rồi TRƯỚC, "
            "rồi mới hỏi lại đúng MỘT ý bằng từ ngữ đơn giản hơn. Không xin lỗi rồi lặp nguyên văn "
            "câu cũ."
        ),
        rephrase=True,
    ),
    DialogueAct.CANNOT_ANSWER: ActPolicy(
        # "Quên/không biết/không có dụng cụ đo" là KẾT QUẢ HỢP LỆ. Hỏi lại y hệt là lỗi trải nghiệm
        # nặng, nên lượt này phải đổi cách hỏi (ước lượng, mô tả cảm nhận) thay vì lặp yêu cầu đo.
        acknowledge_instruction="",
        answer_user_question=(
            "Người bệnh vừa cho biết họ KHÔNG BIẾT hoặc không đo được. Đừng lặp lại yêu cầu cũ - hãy "
            "hỏi theo cách khác (ước lượng, mô tả cảm nhận), hoặc nói rõ là không sao nếu không biết."
        ),
        rephrase=True,
    ),
    DialogueAct.OFF_TOPIC: ActPolicy(
        acknowledge_instruction="",
        answer_user_question=(
            "Tin nhắn vừa rồi chưa trả lời vào ý đang hỏi. Hãy dẫn dắt nhẹ nhàng quay lại, không "
            "trách móc, và hỏi lại đúng một ý."
        ),
        rephrase=True,
    ),
    DialogueAct.GREETING: ActPolicy(
        acknowledge_instruction="",
        answer_user_question="Người bệnh mới chào hỏi. Chào lại một câu thật ngắn rồi hỏi ý đầu tiên.",
        simplify=False,
    ),
}

PROTOCOL_SWITCH_NOTE = (
    "Hướng hỏi vừa chuyển sang nhóm triệu chứng khác theo điều người bệnh vừa kể. Hãy có MỘT câu "
    "chuyển hướng dễ hiểu trước khi hỏi, đừng đổi sang một loạt câu hỏi mới mà không nói gì."
)
"""§6.3: không để người dùng thấy hệ thống đột ngột hỏi một checklist mới."""


@dataclass(frozen=True, slots=True)
class ResponsePlan:
    """Hợp đồng ĐÓNG giữa policy và renderer. Renderer không được thêm gì ngoài những gì ở đây."""

    act: DialogueAct
    cluster_id: str
    missing_fields: tuple[str, ...]
    max_questions: int = 1
    acknowledge: str = ""
    """DỮ KIỆN vừa nhận được, dạng `nhãn = giá trị`. CHỈ là dữ liệu - không có chữ nào để chép thẳng
    ra tin nhắn."""
    acknowledge_instruction: str = ""
    """Hướng dẫn công nhận dữ kiện đó, theo `dialogue_act`."""
    answer_user_question: str = ""
    rephrase: bool = False
    simplify: bool = True
    transition_note: str = ""
    """Câu chuyển hướng khi vừa đổi protocol."""
    static_only: bool = False
    """Cụm an toàn / thông điệp cấp cứu: BỎ renderer, dùng nguyên văn template đã duyệt (§6.1)."""

    @property
    def uses_model(self) -> bool:
        return not self.static_only


def dialogue_act_from_quality(answer_quality: str, *, new_symptom: bool = False) -> DialogueAct:
    """Nhãn extractor -> `DialogueAct`.

    `new_symptom` do CODE tính (protocol vừa đổi), không lấy từ model: đó là căn cứ để chuyển hướng
    hỏi nên không được dựa vào một nhãn chưa validate.

    **`correction` THẮNG `new_symptom`.** Protocol đổi vì hai lý do trái ngược nhau: người bệnh nêu
    THÊM một triệu chứng, hoặc người bệnh RÚT LẠI lời khai cũ ("mình quên mất, mình không sốt" làm
    `_fever_ruled_out` bật). Gộp cả hai thành `new_symptom` khiến đúng lượt đính chính - lượt dễ mất
    lòng tin nhất trong cả phiên - được chào đón như một triệu chứng mới."""
    act = _QUALITY_TO_ACT.get((answer_quality or "").strip().casefold(), DialogueAct.ANSWER)
    if act is DialogueAct.CORRECTION:
        return act
    if new_symptom:
        return DialogueAct.NEW_SYMPTOM
    return act


def build_response_plan(
    protocol: SymptomProtocol,
    cluster: QuestionCluster | None,
    *,
    act: DialogueAct,
    answers: dict[str, object],
    recent_fields: frozenset[str] = frozenset(),
    protocol_switched: bool = False,
    rephrase: bool = False,
    parts: int = 1,
    static_only: bool = False,
    label_protocol: SymptomProtocol | None = None,
) -> ResponsePlan | None:
    """Tra bảng rồi điền dữ kiện của lượt này vào. THUẦN - không gọi model, không side-effect.

    `label_protocol`: nơi TRA NHÃN cho câu công nhận, khi nó khác `protocol`. Cần vì đúng lượt đổi
    protocol, dữ kiện gây ra việc đổi lại thường KHÔNG có trong protocol mới - "mình không sốt" làm
    phiên chuyển sang `general`, mà `general` không khai `fever_reported`. Không có tham số này thì
    lượt đính chính quan trọng nhất lại là lượt duy nhất không được công nhận.

    Trả `None` khi không còn cụm nào để hỏi: lúc đó không có gì để nói, và bịa ra một câu là cách
    nhanh nhất để hỏi một thứ ngoài checklist."""
    if cluster is None:
        return None

    policy = DIALOGUE_POLICY[act]
    missing = tuple(key for key in cluster.fields if not stage_machine.is_filled(answers.get(key)))
    return ResponsePlan(
        act=act,
        cluster_id=cluster.id,
        missing_fields=missing,
        # Trần số ý = số FIELD còn thiếu, không phải số CỤM. Một cụm đã là nhiều ý theo đúng tài liệu
        # lâm sàng ("6 giờ qua có đi tiểu không, ăn uống được không, có nôn nhiều không" là ba ý
        # trong MỘT cụm), nên đếm theo cụm làm `output_guard` chặn nhầm chính câu hỏi chuẩn - đo được
        # 2/13 lượt bị chặn trên transcript thật trước khi sửa.
        #
        # Trần này KHÔNG cần cap tuỳ tiện: `missing_fields` bị chặn sẵn bởi định nghĩa cụm/gói, mà
        # định nghĩa đó là nội dung lâm sàng đã duyệt. Guard vẫn giữ đúng nhiệm vụ của nó - chặn model
        # hỏi VƯỢT ra ngoài plan.
        max_questions=max(policy.max_questions, parts, len(missing)),
        acknowledge=_acknowledge_facts(
            label_protocol or protocol, policy.acknowledge_instruction, recent_fields, answers,
        ),
        acknowledge_instruction=policy.acknowledge_instruction,
        answer_user_question=policy.answer_user_question,
        rephrase=policy.rephrase or rephrase,
        simplify=policy.simplify,
        transition_note=PROTOCOL_SWITCH_NOTE if protocol_switched else "",
        static_only=static_only,
    )


_ACKNOWLEDGE_LIMIT = 2
"""Số dữ kiện tối đa được nhắc lại. §6.3: công nhận NGẮN điều vừa nhận được, không đọc lại cả hồ sơ."""


def _acknowledge_facts(
    protocol: SymptomProtocol,
    instruction: str,
    recent_fields: frozenset[str],
    answers: dict[str, object],
) -> str:
    """Dữ kiện VỪA thu được, dạng `nhãn = giá trị`, để renderer công nhận đúng thứ người bệnh vừa nói.

    Cố ý KHÔNG tự ghép thành câu tiếng Việt ở đây: ghép `"không " + "Người dùng khai có sốt"` ra một
    câu sai ngữ pháp. Việc ghép câu là của renderer; việc của policy là CHỌN ĐÚNG dữ kiện nào được
    nhắc tới - và đó mới là phần không được giao cho model."""
    if not instruction:
        return ""
    facts = [
        f"{protocol.fields_by_key[key].label} = {answers[key]}"
        for key in sorted(recent_fields)
        if key in protocol.fields_by_key and stage_machine.is_filled(answers.get(key))
    ][:_ACKNOWLEDGE_LIMIT]
    return "; ".join(facts)
