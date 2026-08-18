"""Metric trải nghiệm + độ phủ (§12) - P4.3.

Bài quan trọng nhất ở đây KHÔNG phải "công thức có đúng không" mà là **mẫu số có đúng không**. §12
kết thúc bằng "mọi ngưỡng phần trăm phải đi kèm mẫu số; không có mẫu số thì không phải gate", và
những lỗi đắt nhất của một bộ chỉ số đều là lỗi mẫu số: đếm nhầm một phiên chưa đóng thành một phiên
đóng-mà-thiếu-field sẽ biến giới hạn của công cụ đo thành lỗi của hệ thống, và ngược lại có thể che
một lỗi thật.

Toàn bộ file không gọi model - metric là phép đếm thuần.
"""

from __future__ import annotations

import pytest

from src import paths
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.symptom_protocol import metrics
from src.services.symptom_protocol.models import QuestionCluster


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)


def _cluster(cluster_id: str, *fields: str) -> QuestionCluster:
    return QuestionCluster(cluster_id, "1", fields, script_hint="?")


def _summary(**overrides) -> dict[str, object]:
    """Một phiên đã đóng bình thường, đủ độ phủ - mốc để mỗi bài chỉ đổi đúng thứ nó quan tâm."""
    base: dict[str, object] = {
        "turns": 10,
        "stop_reason": "COVERAGE_COMPLETE",
        "triage_level": "SELF_CARE",
        "mandatory_coverage_at_close": True,
        "mandatory_remaining": [],
        "mandatory_unasked": [],
        "questions_asked": 10,
        "user_led_ratio": 0.5,
        "repeat_question_rate": 0.0,
        "deferral_depth": 0.0,
        "catch_all_asked": True,
        "catch_all_yielded": False,
    }
    base.update(overrides)
    return base


# --- đếm theo lượt --------------------------------------------------------------------------------


def test_a_question_touching_a_field_the_patient_just_raised_counts_as_user_led() -> None:
    """§8.4 - đây là chỉ số đo trực tiếp cảm giác "được lắng nghe", và là lý do follow-the-user tồn tại."""
    counter = metrics.ConversationMetrics()
    counter.record_question(_cluster("Q1", "cough"), recent_fields=frozenset({"cough"}), deferral_count=0)
    counter.record_question(_cluster("Q2", "rash"), recent_fields=frozenset({"cough"}), deferral_count=0)
    assert counter.user_led_questions == 1
    assert counter.questions_asked == 2


def test_asking_the_same_cluster_twice_is_counted_as_a_repeat() -> None:
    counter = metrics.ConversationMetrics()
    counter.record_question(_cluster("Q1", "cough"), recent_fields=frozenset(), deferral_count=0)
    counter.record_question(_cluster("Q1", "cough"), recent_fields=frozenset(), deferral_count=0)
    assert counter.repeated_questions == 1


def test_no_cluster_means_no_question_was_asked() -> None:
    """Lượt cuối của phiên không có cụm kế tiếp. Đếm nó thành một câu hỏi sẽ làm mẫu số phình lên
    đúng một đơn vị ở MỌI phiên - một sai lệch nhỏ nhưng có hệ thống."""
    counter = metrics.ConversationMetrics()
    counter.record_question(None, recent_fields=frozenset(), deferral_count=0)
    assert counter.questions_asked == 0


def test_deferral_depth_is_sampled_when_the_cluster_is_finally_asked() -> None:
    """Phải đo TẠI THỜI ĐIỂM cụm được chọn: `CoverageLedger` xoá nợ ngay sau đó, nên suy lại từ trạng
    thái cuối phiên sẽ luôn ra 0."""
    counter = metrics.ConversationMetrics()
    counter.record_question(_cluster("Q1", "a"), recent_fields=frozenset(), deferral_count=3)
    counter.record_question(_cluster("Q2", "b"), recent_fields=frozenset(), deferral_count=1)
    assert counter.summary(
        FEVER_PROTOCOL, {}, turns=2, stop_reason=None, triage_level=None,
    )["deferral_depth"] == 2.0


def test_catch_all_asked_and_answered_are_two_separate_events() -> None:
    """Phiên có thể kết thúc sau khi hỏi mà chưa nhận được trả lời. Lúc đó `asked=True, yielded=False`
    là mô tả ĐÚNG, không phải dữ liệu thiếu."""
    counter = metrics.ConversationMetrics()
    counter.record_catch_all_asked()
    assert counter.catch_all_asked and not counter.catch_all_yielded
    counter.record_catch_all_answer(yielded=True)
    assert counter.catch_all_yielded


# --- tỉ lệ không có mẫu số phải là None, không phải 0 ----------------------------------------------


def test_a_ratio_with_no_denominator_is_none_not_zero() -> None:
    """`0.0` và "không xác định" là hai việc khác nhau. Một phiên chưa hỏi câu nào mà báo
    `user_led_ratio = 0` sẽ kéo trung bình của cả tập xuống ngang những phiên chưa hề chạy."""
    counter = metrics.ConversationMetrics()
    summary = counter.summary(FEVER_PROTOCOL, {}, turns=0, stop_reason=None, triage_level=None)
    assert summary["user_led_ratio"] is None
    assert summary["repeat_question_rate"] is None
    assert summary["deferral_depth"] is None


# --- mẫu số của bảng gộp: phần dễ sai nhất --------------------------------------------------------


def test_a_session_that_never_closed_is_kept_out_of_the_coverage_gate() -> None:
    """Tên chỉ số là "at close". Phiên chạm trần lượt của harness chưa có cơ hội đạt độ phủ, nên tính
    nó là "đóng mà thiếu field" biến một giới hạn của CÔNG CỤ ĐO thành một lỗi của HỆ THỐNG."""
    result = metrics.aggregate([
        _summary(),
        _summary(stop_reason=None, mandatory_coverage_at_close=False),
    ])
    assert result["mandatory_coverage_at_close"] == {"value": 1.0, "n": 1, "covered": 1}
    assert result["sessions_never_closed"] == 1
    assert result["sessions"] == 2  # vẫn được đếm, không bị giấu đi


def test_a_red_flag_session_is_kept_out_of_the_coverage_gate() -> None:
    """§8.2 mục 1: escalate ngay quan trọng hơn hỏi nốt checklist, nên ca đỏ ĐƯỢC PHÉP thiếu field.
    Gộp vào thì chỉ số không bao giờ đạt 100% dù hệ thống chạy đúng."""
    result = metrics.aggregate([
        _summary(),
        _summary(stop_reason="RED_FLAG", mandatory_coverage_at_close=False, triage_level="EMERGENCY"),
    ])
    assert result["mandatory_coverage_at_close"] == {"value": 1.0, "n": 1, "covered": 1}
    assert result["sessions_red_flag"] == 1


def test_a_real_coverage_gap_is_not_hidden_by_the_filters() -> None:
    """Chiều ngược lại của hai bài trên: lọc mẫu số KHÔNG được biến thành lọc lỗi. Một phiên đóng
    bình thường mà thiếu field M0/M1 phải kéo chỉ số xuống - đó đúng là thứ gate này canh."""
    result = metrics.aggregate([
        _summary(),
        _summary(mandatory_coverage_at_close=False, mandatory_remaining=["age_value"]),
    ])
    assert result["mandatory_coverage_at_close"] == {"value": 0.5, "n": 2, "covered": 1}


def test_ratios_are_weighted_by_question_count_not_averaged_across_sessions() -> None:
    """Câu hỏi mới là đơn vị cần đếm. Trung bình của các tỉ lệ cho một phiên 2 câu cùng sức nặng với
    một phiên 20 câu, trong khi câu hỏi cần trả lời là "trong TẤT CẢ câu hỏi đã đặt ra, bao nhiêu
    phần trăm đi theo mạch người bệnh"."""
    result = metrics.aggregate([
        _summary(questions_asked=2, user_led_ratio=1.0),
        _summary(questions_asked=18, user_led_ratio=0.0),
    ])
    # Trung bình cộng của tỉ lệ sẽ ra 0.5 - con số đó nói sai hẳn về 20 câu hỏi đã đặt ra.
    assert result["user_led_ratio"] == {"value": 0.1, "n": 20}


def test_catch_all_yield_is_measured_only_over_sessions_that_ran_the_step() -> None:
    """Ca cấp cứu cố ý bỏ bước quét sót (§8.6). Gộp chúng vào mẫu số làm chỉ số trông như câu quét
    sót đang vô dụng, trong khi nó chỉ đơn giản là không được chạy."""
    result = metrics.aggregate([
        _summary(catch_all_asked=True, catch_all_yielded=True),
        _summary(catch_all_asked=False, catch_all_yielded=False, stop_reason="RED_FLAG"),
    ])
    assert result["catch_all_yield"] == {"value": 1.0, "n": 1, "yielded": 1}


# --- "chưa hỏi" vs "đã hỏi mà không biết": hai thứ `mandatory_remaining` gộp làm một -------------


def test_a_field_left_unknown_after_being_asked_is_not_counted_as_a_gap() -> None:
    """§8.5 quy tắc 3: người bệnh trả lời "không biết" là một KẾT QUẢ HỢP LỆ, không phải nợ.

    Đây là lý do §12 đặt gate `mandatory_coverage_at_close = 100%` lên nhầm chỉ số: hệ thống cố ý
    KHÔNG bảo đảm mọi field M0/M1 có căn cứ, vì nó không ép được người bệnh biết điều họ không biết."""
    counter = metrics.ConversationMetrics()
    cluster = next(c for c in FEVER_PROTOCOL.clusters if c.fields)
    counter.record_question(cluster, recent_fields=frozenset(), deferral_count=0)
    summary = counter.summary(FEVER_PROTOCOL, {}, turns=1, stop_reason="DONE", triage_level="SELF_CARE")
    assert not set(summary["mandatory_unasked"]) & set(cluster.fields)


def test_a_cluster_that_was_never_asked_shows_up_as_a_real_gap() -> None:
    """Bất biến hệ thống THẬT SỰ giữ: linh hoạt đổi được THỨ TỰ hỏi, không được BỎ hỏi (§8.2 mục 1)."""
    counter = metrics.ConversationMetrics()
    summary = counter.summary(FEVER_PROTOCOL, {}, turns=0, stop_reason="DONE", triage_level=None)
    assert summary["mandatory_unasked"], "chưa hỏi cụm nào thì mọi field M0/M1 phải là bỏ sót"


def test_a_synthesised_cluster_still_counts_its_fields_as_asked() -> None:
    """Regression của một lỗi ĐO, không phải lỗi hệ thống.

    Bản đầu so MÃ CỤM và báo `indwelling_device` bỏ sót ở 6/6 phiên chạy thật. Sai: cụm tổng hợp mang
    mã tự sinh không có trong `protocol.clusters` - `BATCH-<stage>-<id>+<id>` mã hoá cụm thành phần
    còn `SCREEN-<stage>` thì không mã hoá gì cả. Field là đơn vị duy nhất đúng cho mọi loại cụm.

    Bài này dùng mã `SCREEN-` vì đó đúng là loại mã mà cách đếm cũ không có đường nào bung ra được."""
    from src.services.symptom_protocol import screening

    fields = ("indwelling_device", "chronic_conditions")
    probe = QuestionCluster(f"{screening.PROBE_ID_PREFIX}3A", "3A", fields, script_hint="?")
    counter = metrics.ConversationMetrics()
    counter.record_question(probe, recent_fields=frozenset(), deferral_count=0)
    unasked = set(counter.summary(
        FEVER_PROTOCOL, {}, turns=1, stop_reason="DONE", triage_level=None,
    )["mandatory_unasked"])
    assert not unasked & set(fields)


def test_the_aggregate_counts_sessions_that_silently_skipped_a_mandatory_cluster() -> None:
    result = metrics.aggregate([_summary(), _summary(mandatory_unasked=["age_value"])])
    assert result["sessions_with_unasked_mandatory"] == 1


def test_an_empty_run_reports_no_numbers_instead_of_perfect_scores() -> None:
    """Chạy 0 ca phải ra `None`, không phải 100%. "100% trên 0 ca" là đúng cách một gate mềm bị đọc
    nhầm thành đã đạt."""
    result = metrics.aggregate([])
    assert result["mandatory_coverage_at_close"]["value"] is None
    assert result["user_led_ratio"]["value"] is None
    assert result["turns_median"] is None
