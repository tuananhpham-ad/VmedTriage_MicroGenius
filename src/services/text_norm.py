"""Chuẩn hoá văn bản tiếng Việt do người bệnh gõ. Một chỗ duy nhất cho phép bỏ dấu.

VÌ SAO GOM VỀ ĐÂY. Trước module này, phép bỏ dấu được chép ra SÁU bản gần giống hệt nhau
(`agents/intake_agent.strip_diacritics`, `engines/red_flag_text_rules.normalize_red_flag_text`,
`symptom_protocol/common_safety/rules._fold_text`, `symptom_protocol/controller._normalize`,
`symptom_protocol/intake_agent._fold_bare_reply`, `symptom_protocol/non_clinical._fold`). Cùng lập
luận mà `fetching.py` đưa ra cho Guard 1/2: sáu bản thì sớm muộn một bản sẽ lỏng hơn năm bản kia, và
đường lỏng mới là đường red-flag lọt qua.

Các hàm gọi vẫn giữ phần đuôi riêng của mình (gộp khoảng trắng, bỏ dấu câu) - khác biệt đó là có
chủ đích theo từng chỗ dùng. Chỉ phần LÕI được gom.

KHÔNG DÙNG CHO PROVENANCE. `graph_schema.normalise_span` cố ý GIỮ dấu vì nó kiểm trích dẫn nguyên
văn; thông báo lỗi của nó đòi thẳng "with its original diacritics and spelling". Bỏ dấu ở đó là phá
cơ chế chặn evidence bịa. Đừng thay nó bằng hàm trong file này.
"""

from __future__ import annotations

import unicodedata

__all__ = [
    "expand_chat_shorthand",
    "fold_diacritics",
]


def fold_diacritics(text: str) -> str:
    """Hạ chữ thường + bỏ dấu tiếng Việt. Không gộp khoảng trắng, không đụng dấu câu.

    Cần thiết vì người bệnh gõ tiếng Việt không dấu rất phổ biến trên điện thoại ("li bi", "ngat",
    "co giat"). Chỉ so khớp bản có dấu thì red-flag sẽ lọt - đây là lỗi an toàn, không phải lỗi
    tiện dụng.

    `đ` KHÔNG bị NFD tách ra thành `d` + dấu, nên phải thay tay TRƯỚC khi decompose. Đây đúng là chỗ
    một bản chép lệch sẽ âm thầm bỏ sót mọi cụm có `đ` ("đau ngực", "đột ngột", "bất tỉnh")."""
    lowered = (text or "").casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


# ---------- viết tắt kiểu chat ----------

_CHAT_SHORTHAND: dict[str, str] = {
    # phủ định - nhóm quan trọng nhất, vì "ko tho duoc" mà không mở ra thì
    # "khong tho duoc" sẽ không bao giờ khớp
    "ko": "khong",
    "k": "khong",
    "kh": "khong",
    "kg": "khong",
    "khg": "khong",
    "hok": "khong",
    # thể/trạng thái
    "dc": "duoc",
    "vs": "voi",
    "cx": "cung",
    "nx": "nua",
    "bt": "binh thuong",
    "nvien": "nhap vien",
    # người
    "bs": "bac si",
    "bn": "benh nhan",
    "bv": "benh vien",
}
"""Viết tắt tiếng Việt kiểu chat -> dạng đầy đủ ĐÃ BỎ DẤU.

CHỈ THAY THEO TOKEN, không thay theo chuỗi con: `"k"` -> `"khong"` mà áp lên chuỗi con sẽ phá nát mọi
từ có chữ k. Danh sách cố ý ngắn và chỉ gồm những cụm ảnh hưởng tới việc khớp red-flag; thêm bừa vào
đây là cách tạo ra dương tính giả mà không ai lần ra được nguồn gốc.

KHÔNG thêm đại từ (`m`, `t`, `e`, `a`): chúng vừa mơ hồ vừa không xuất hiện trong cụm red-flag nào.

CỐ Ý KHÔNG CÓ `"hong" -> "khong"` dù đó là cách viết tắt có thật. `họng` bỏ dấu cũng ra `hong`, nên
mở nó sẽ biến "đau họng" thành "đau không" - phá đúng một triệu chứng rất hay gặp. Cùng lý do với
`"0" -> "khong"`: số 0 xuất hiện trong mô tả nhiệt độ và liều thuốc. Một cụm viết tắt chỉ được vào
bảng này khi dạng bỏ dấu của nó KHÔNG trùng với một từ tiếng Việt nào khác."""


def expand_chat_shorthand(folded: str) -> str:
    """Mở viết tắt trên chuỗi ĐÃ bỏ dấu. Vào sao ra vậy nếu không có gì để mở.

    Nhận đầu vào đã fold chứ không tự fold, để chỗ gọi kiểm soát được thứ tự và không fold hai lần. Vì
    thế KHOÁ trong bảng phải viết ở dạng ĐÃ bỏ dấu - `đc` sẽ không bao giờ khớp, vì `đ` đã thành `d`
    trước khi tới đây."""
    if not folded:
        return ""
    return " ".join(_CHAT_SHORTHAND.get(token, token) for token in folded.split(" ") if token)
