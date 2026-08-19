"""Nạp corpus y văn ban đầu cho `src/source_support/`. Chạy OFFLINE, không tốn một lời gọi LLM nào.

    python -m scripts.build_source_corpus --dry-run   # chỉ kiểm URL, không ghi gì
    python -m scripts.build_source_corpus             # kiểm rồi nạp vào data/source_index/
    python -m scripts.build_source_corpus --rebuild   # bỏ index cũ, nạp lại từ đầu

VÌ SAO NẠP THEO TÀI LIỆU CHỨ KHÔNG THEO CLAIM. Một trang = nhiều chunk = phủ nhiều mệnh đề, nên nạp ở
mức *tài liệu* rẻ hơn và kiểm soát được hơn hẳn tra ở mức *claim*. Chi phí search bằng $0 vì URL do
mình chọn; chỉ tốn thời gian nhúng cục bộ.

DANH SÁCH DƯỚI ĐÂY LÀ ĐỀ XUẤT, KHÔNG PHẢI SỰ THẬT. URL guideline chết và đổi đường dẫn khá thường
xuyên, nên mọi URL đều phải qua `fetch_document` (guard 1 + guard 2) và script **báo rõ cái nào fail**
thay vì âm thầm bỏ qua - một corpus teo dần trong im lặng là cách phần trích nguồn kém đi mà không ai
nhận ra. Chạy `--dry-run` trước, đọc bảng kết quả, sửa/bỏ URL hỏng, rồi mới nạp thật.

CHỌN THEO PHÂN BỐ CONCEPT ĐO ĐƯỢC từ graph cache, không chọn theo cảm tính: top concept phủ phần lớn
số ca, và mỗi nhóm dưới đây bám vào một cụm concept trong đó.

BỎ MSD MANUALS Ở V1 (quyết định 2026-08-19, dựa trên số đo chứ không phải cảm tính). Trang MSD
professional là tài liệu TRA CỨU dạng bảng: hàng thuốc, dấu †, danh mục xét nghiệm. Chúng dày đặc
thuật ngữ nên thắng cosine trước văn xuôi NHS/NICE, và trích dẫn sinh ra là những dòng bảng kiểu
*"if there are signs of dehydration or edema; or if a complex febrile seizure occurs Blood and urine
cultures:"* - không khẳng định điều gì lâm sàng cả. Trong khi câu NHS *"Call 999 if the seizure lasts
longer than 5 minutes..."* nằm sẵn trong index mà không lần nào được chọn.

Ba lớp cắt chuỗi (nắn ranh giới từ, cắt về câu trọn vẹn, cắt mệnh đề cụt) chỉ đưa quote từ rất tệ lên
tạm đọc được - vì vấn đề không nằm ở ranh giới, mà ở thể loại văn bản. Corpus này phục vụ việc TRÍCH
DẪN CHO NGƯỜI ĐỌC, không phải tra cứu chuyên sâu, nên NHS + NICE + WHO là đúng thể loại. Đưa MSD trở
lại khi đã có bộ lọc chunk dạng bảng và ĐO được là nó không lấn nữa.

BỎ NHÓM TIẾNG VIỆT Ở V1 (kcb.vn, moh.gov.vn). Bước tra dùng `claim_en` trong MỘT không gian cosine
với ngưỡng cố định, nên tài liệu tiếng Việt gần như không bao giờ được lấy ra - để chúng trong corpus
chỉ tạo cảm giác đã phủ ngữ cảnh VN mà thực tế thì không. Muốn phủ thật thì phải tra hai lượt
(`claim_en` cho corpus EN, `claim_vi` cho corpus VN); đó là việc của v2.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

from src.config import get_settings
from src.source_support.embedding import embed_many
from src.source_support.fetching import FetchFailure, fetch_document, parse_allowlist
from src.source_support.index import SourceIndex, prepare_chunks

logger = logging.getLogger("vmedtriage.source_support")


@dataclass(frozen=True, slots=True)
class DocumentSpec:
    url: str
    title: str
    group: str
    concepts: str


CORPUS: tuple[DocumentSpec, ...] = (
    # --- Cấp cứu chung: phủ mọi red flag ---------------------------------------------------------
    DocumentSpec("https://www.nhs.uk/nhs-services/urgent-and-emergency-care-services/when-to-call-999/",
                 "When to call 999", "cap_cuu_chung", "mọi red flag"),
    DocumentSpec("https://www.nhs.uk/nhs-services/urgent-and-emergency-care-services/when-to-go-to-ae/",
                 "When to go to A&E", "cap_cuu_chung", "mọi red flag"),
    DocumentSpec("https://www.nhs.uk/conditions/sepsis/",
                 "Sepsis", "cap_cuu_chung", "fever, lethargy"),

    # --- Sốt & nhi: fever, seizure, lethargy -----------------------------------------------------
    DocumentSpec("https://www.nhs.uk/conditions/fever-in-children/",
                 "Fever in children", "sot_nhi", "fever"),
    DocumentSpec("https://www.nhs.uk/conditions/febrile-seizures/",
                 "Febrile seizures", "sot_nhi", "seizure, fever"),
    DocumentSpec("https://www.nhs.uk/conditions/meningitis/",
                 "Meningitis", "sot_nhi", "fever, headache, rash"),
    DocumentSpec("https://www.who.int/publications/i/item/9789241506823",
                 "IMCI chart booklet", "sot_nhi", "fever, nhi khoa"),

    # --- Hô hấp: dyspnea, cough ------------------------------------------------------------------
    DocumentSpec("https://www.nhs.uk/conditions/shortness-of-breath/",
                 "Shortness of breath", "ho_hap", "dyspnea"),
    DocumentSpec("https://www.nhs.uk/conditions/cough/",
                 "Cough", "ho_hap", "cough"),
    DocumentSpec("https://www.nhs.uk/conditions/pneumonia/",
                 "Pneumonia", "ho_hap", "cough, fever, dyspnea"),

    # --- Tim mạch: chest_pain, syncope, numbness, weakness ---------------------------------------
    DocumentSpec("https://www.nhs.uk/conditions/heart-attack/",
                 "Heart attack", "tim_mach", "chest_pain"),
    DocumentSpec("https://www.nhs.uk/conditions/stroke/",
                 "Stroke", "tim_mach", "numbness, weakness, speech"),
    DocumentSpec("https://www.nhs.uk/conditions/chest-pain/",
                 "Chest pain", "tim_mach", "chest_pain"),
    DocumentSpec("https://www.nhs.uk/conditions/fainting/",
                 "Fainting", "tim_mach", "syncope"),

    # --- Tiêu hoá: abdominal_pain, vomiting, diarrhea, bloating ----------------------------------
    DocumentSpec("https://www.nhs.uk/conditions/stomach-ache/",
                 "Stomach ache", "tieu_hoa", "abdominal_pain"),
    DocumentSpec("https://www.nhs.uk/conditions/diarrhoea-and-vomiting/",
                 "Diarrhoea and vomiting", "tieu_hoa", "vomiting, diarrhea"),
    DocumentSpec("https://www.nhs.uk/conditions/appendicitis/",
                 "Appendicitis", "tieu_hoa", "abdominal_pain"),
    # MSD "Overview of GI Bleeding" trả 404 (kiểm 2026-08-19); thay bằng trang NHS tương đương.
    DocumentSpec("https://www.nhs.uk/symptoms/vomiting-blood/",
                 "Vomiting blood", "tieu_hoa", "gi_bleeding, vomiting"),

    # --- Thần kinh: headache, dizziness ----------------------------------------------------------
    DocumentSpec("https://www.nhs.uk/conditions/headaches/",
                 "Headaches", "than_kinh", "headache"),
    DocumentSpec("https://www.nhs.uk/conditions/dizziness/",
                 "Dizziness", "than_kinh", "dizziness"),
    DocumentSpec("https://www.nhs.uk/conditions/head-injury-and-concussion/",
                 "Head injury and concussion", "than_kinh", "head_injury"),
    # MSD xếp bài này dưới tai-mũi-họng, không dưới thần kinh (đường dẫn cũ trả 404).

    # --- Sản phụ khoa: vaginal_bleeding, pelvic_pain ---------------------------------------------
    DocumentSpec("https://www.nhs.uk/pregnancy/related-conditions/common-symptoms/vaginal-bleeding/",
                 "Vaginal bleeding in pregnancy", "san_phu_khoa", "vaginal_bleeding"),
    DocumentSpec("https://www.nhs.uk/conditions/ectopic-pregnancy/",
                 "Ectopic pregnancy", "san_phu_khoa", "pelvic_pain, vaginal_bleeding"),

    # --- Dị ứng / da: itching, swelling, drug_allergy, skin_redness ------------------------------
    # NHÓM QUAN TRỌNG NHẤT cho bài kiểm chứng #7 (ca dị ứng da): đây là chỗ thiết kế post-hoc dễ hỏng
    # nhất, và cần đúng những trang này để bước chấm có cái mà gạt thành `unsupported`.
    DocumentSpec("https://www.nhs.uk/conditions/anaphylaxis/",
                 "Anaphylaxis", "di_ung_da", "swelling, dyspnea, drug_allergy"),
    DocumentSpec("https://www.nhs.uk/conditions/rashes-babies-and-children/",
                 "Rashes in babies and children", "di_ung_da", "skin_redness"),
    DocumentSpec("https://www.nhs.uk/conditions/hives/",
                 "Hives", "di_ung_da", "itching, skin_redness"),

    # --- Bệnh nền: diabetes_mellitus, hypertension -----------------------------------------------
    DocumentSpec("https://www.nhs.uk/conditions/diabetic-ketoacidosis/",
                 "Diabetic ketoacidosis", "benh_nen", "diabetes_mellitus"),
    DocumentSpec("https://www.nhs.uk/conditions/low-blood-sugar-hypoglycaemia/",
                 "Low blood sugar (hypoglycaemia)", "benh_nen", "diabetes_mellitus"),
    DocumentSpec("https://www.nhs.uk/conditions/high-blood-pressure-hypertension/",
                 "High blood pressure", "benh_nen", "hypertension"),

    # --- Tiết niệu: dysuria, flank_pain ----------------------------------------------------------
    DocumentSpec("https://www.nhs.uk/conditions/urinary-tract-infections-utis/",
                 "Urinary tract infections", "tiet_nieu", "dysuria"),
    DocumentSpec("https://www.nhs.uk/conditions/kidney-stones/",
                 "Kidney stones", "tiet_nieu", "flank_pain"),
    # --- Guideline NICE: khuyến cáo chính thức, không phải trang tra cứu -------------------------
    # KHÁC HẲN nhóm trên về thể loại. NHS/MSD là trang mô tả bệnh viết cho người đọc; NICE là khuyến
    # cáo lâm sàng có ngưỡng và tiêu chí rõ ràng ("nếu X thì xếp nhóm đỏ"). Đó chính là dạng câu mà
    # bước chấm verdict cần để trả lời được "đoạn trích có THẬT SỰ khẳng định mệnh đề không".
    #
    # PHẢI DÙNG ĐƯỜNG DẪN /chapter/Recommendations. Trang bìa /guidance/<id> chỉ bóc được ~700-3.800
    # ký tự (tiêu đề + điều hướng); nội dung khuyến cáo nằm ở trang con. Đã kiểm 2026-08-19.
    #
    # NG51 (suspected sepsis) BỊ BỎ: mọi đường dẫn đều chỉ bóc được 719 ký tự - trang dựng bằng JS,
    # httpx+bs4 không lấy được. Nhóm nhiễm khuẩn huyết đã có NHS Sepsis và NICE NG240 phủ.
    DocumentSpec("https://www.nice.org.uk/guidance/ng143/chapter/Recommendations",
                 "NICE NG143: Fever in under 5s - assessment and initial management", "sot_nhi", "fever, nhi khoa"),
    DocumentSpec("https://www.nice.org.uk/guidance/ng240/chapter/Recommendations",
                 "NICE NG240: Meningitis (bacterial) and meningococcal disease", "sot_nhi", "fever, headache, rash"),
    DocumentSpec("https://www.nice.org.uk/guidance/ng232/chapter/Recommendations",
                 "NICE NG232: Head injury - assessment and early management", "than_kinh", "head_injury"),
    DocumentSpec("https://www.nice.org.uk/guidance/cg150/chapter/Recommendations",
                 "NICE CG150: Headaches in over 12s - diagnosis and management", "than_kinh", "headache"),
    DocumentSpec("https://www.nice.org.uk/guidance/cg95/chapter/Recommendations",
                 "NICE CG95: Recent-onset chest pain of suspected cardiac origin", "tim_mach", "chest_pain"),
    DocumentSpec("https://www.nice.org.uk/guidance/ng245/chapter/Recommendations",
                 "NICE NG245: Asthma - diagnosis, monitoring and chronic management", "ho_hap", "dyspnea, cough"),
    DocumentSpec("https://www.nice.org.uk/guidance/cg141/chapter/Recommendations",
                 "NICE CG141: Acute upper gastrointestinal bleeding", "tieu_hoa", "gi_bleeding"),
    DocumentSpec("https://www.nice.org.uk/guidance/cg84/chapter/Recommendations",
                 "NICE CG84: Diarrhoea and vomiting in children under 5", "tieu_hoa", "diarrhea, vomiting"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Chỉ kiểm URL, không nhúng và không ghi.")
    parser.add_argument("--rebuild", action="store_true", help="Bỏ index cũ, nạp lại từ đầu.")
    parser.add_argument("--group", help="Chỉ nạp một nhóm (ví dụ: di_ung_da).")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args()
    allowlist = parse_allowlist(get_settings().source_support_allowlist)

    specs = [spec for spec in CORPUS if not args.group or spec.group == args.group]
    index = SourceIndex(directory=SourceIndex().directory) if args.rebuild else SourceIndex.load()
    print(f"Corpus: {len(specs)} tài liệu · index hiện có {len(index)} chunk\n")

    ok: list[tuple[DocumentSpec, int]] = []
    failed: list[tuple[DocumentSpec, str]] = []
    skipped: list[DocumentSpec] = []

    for position, spec in enumerate(specs, start=1):
        if index.has_document(spec.url) and not args.rebuild:
            skipped.append(spec)
            print(f"[{position:2}/{len(specs)}] BỎ QUA (đã có)  {spec.title}")
            continue

        document = fetch_document(spec.url, allowlist=allowlist, title=spec.title)
        if isinstance(document, FetchFailure):
            failed.append((spec, document.reason))
            print(f"[{position:2}/{len(specs)}] FAIL           {spec.title}\n{'':17}{document.reason}")
            continue

        _, pieces = prepare_chunks(document.text)
        if args.dry_run:
            ok.append((spec, len(pieces)))
            print(f"[{position:2}/{len(specs)}] OK ({len(pieces):3} chunk) {spec.title}")
            continue

        index.add_document(document=document, vectors=embed_many(pieces))
        ok.append((spec, len(pieces)))
        print(f"[{position:2}/{len(specs)}] NẠP ({len(pieces):3} chunk) {spec.title}")

    if not args.dry_run and ok:
        index.save()

    _report(ok, failed, skipped, index, dry_run=args.dry_run)
    # Trả mã lỗi khi có URL hỏng: người chạy phải NHÌN THẤY, và CI thì phải đỏ.
    return 1 if failed else 0


def _report(
    ok: list[tuple[DocumentSpec, int]],
    failed: list[tuple[DocumentSpec, str]],
    skipped: list[DocumentSpec],
    index: SourceIndex,
    *,
    dry_run: bool,
) -> None:
    print("\n" + "=" * 78)
    print(f"OK: {len(ok)}   FAIL: {len(failed)}   BỎ QUA: {len(skipped)}   "
          f"tổng chunk trong index: {len(index)}")
    if failed:
        print("\nURL KHÔNG NẠP ĐƯỢC - sửa hoặc bỏ khỏi CORPUS trước khi chạy thật:")
        for spec, reason in failed:
            print(f"  [{spec.group}] {spec.title}\n      {spec.url}\n      -> {reason}")
    if dry_run:
        print("\n(--dry-run: chưa nhúng và chưa ghi gì xuống đĩa)")


if __name__ == "__main__":
    sys.exit(main())
