import { api } from "../api.js";
import { bindAccountMenu } from "./account.js?v=design-20260827d";
import { bindSideNav, displayLevel, nurseShell, paintOverview } from "./nurse.js?v=design-20260901c";
import { completedStatuses, state } from "../state.js";
import { escapeHtml, icon, priorityLabels, shortCaseId, showToast, statusLabels, symptomGroupLabels } from "../shared.js";

/**
 * W-08 — bảng điều khiển của điều dưỡng.
 *
 * NGUỒN DỮ LIỆU: dùng lại `/api/v1/nurse/queue` (trả nguyên `TriageCase`), không thêm endpoint mới.
 * Đổi lại phải biết giới hạn của nó: endpoint đó đã lọc theo `_is_ready_for_nurse_queue`, nên mẫu số
 * ở đây là "ca đã vào được hàng đợi", KHÔNG phải mọi ca từng mở. Ca còn đang hỏi checklist và ca
 * Part 2 hỏng không nằm trong bất kỳ con số nào dưới đây - có ý nghĩa cho chỉ số vận hành, nhưng sẽ
 * SAI nếu sau này ai đó dùng màn này để đo tỉ lệ bỏ dở hay tỉ lệ Part 2 thất bại. Hai chỉ số đó cần
 * một endpoint metrics riêng đọc thẳng `case_store`.
 *
 * KHÔNG có ô phần trăm tăng/giảm nào: hệ thống chưa lưu chuỗi thời gian, nên mọi "+15%" sẽ là số bịa.
 *
 * NGUỒN THỨ HAI: `/api/v1/nurse/review-log` (audit log rút gọn). Cần nó vì `hitl_review._apply` GHI
 * ĐÈ `triage_proposal.priority` bằng mức điều dưỡng sửa - đọc case chỉ thấy mức SAU khi sửa, nên
 * không có cách nào so "AI đề xuất gì" với "điều dưỡng chốt gì" nếu chỉ có hàng đợi.
 *
 * MÀN NÀY CÓ HAI PHẦN và chúng trả lời hai câu khác nhau:
 *
 * - **Bảng trực** - "ngay bây giờ tôi phải làm gì": ai đang chờ, chờ bao lâu, ca nào sắp quá hạn.
 *   Số liệu sống, polling 15 giây.
 * - **Bảng chất lượng** - "hệ thống đang chạy tốt tới đâu": AI đề xuất có khớp quyết định điều dưỡng
 *   không, checklist đang hụt field nào, dấu hiệu nguy hiểm nào hay gặp.
 */

// Bảng màu ĐÃ QUA validator của skill dataviz (`validate_palette.js`, light, surface #fff):
// lightness band PASS · chroma floor PASS · CVD ΔE 23.6 (protan) PASS · normal-vision ΔE 35.3 PASS ·
// contrast ≥3:1 PASS. Đổi một trong hai mã màu này thì phải chạy lại validator, đừng chỉnh bằng mắt.
const SERIES_IN = "#1a5ea8";
const SERIES_DONE = "#eb6834";

// Mức ưu tiên là thang TRẠNG THÁI, không phải series identity - nên nó giữ đúng bộ đỏ/hổ phách/xanh
// mà toàn bộ phần còn lại của app đã dùng cho `priority-dot`. Mọi lát bánh đều có nhãn chữ đi kèm,
// không bao giờ chỉ dựa vào màu.
const PRIORITY_TONES = { Emergency: "#c62828", Urgent: "#d68a00", "Self-care": "#1e7a4d" };
const PRIORITY_TEXT = { Emergency: "Cấp cứu", Urgent: "Khám sớm", "Self-care": "Tự theo dõi" };
// Phải khớp `red_flag_sla.SLA_CLINICAL_SECONDS` ở backend và `slaBadge()` ở nurse.js. Đồng hồ
// chỉ chạy từ lúc ca vào hàng đợi (`queued_at`) đến lần đầu có điều dưỡng mở hồ sơ.
const SLA_CLINICAL_SECONDS = 300;

const GROUP_KEYS = ["fever", "abdominal_pain", "chest_pain", "shortness_of_breath", "headache"];
const RANGES = [["yesterday", "Hôm qua"], ["7", "7 ngày"], ["30", "30 ngày"]];

/** Ba mức theo thứ tự NẶNG DẦN XUỐNG - dùng cho cả donut lẫn ma trận AI/điều dưỡng. Chỉ số thứ tự
 *  là thứ phân biệt "điều dưỡng nâng mức" với "điều dưỡng hạ mức", và chỉ chiều NÂNG mới đáng báo
 *  động: AI đề xuất thấp hơn mức thật nghĩa là nó đã bỏ sót một ca nặng. */
const LEVELS = ["Emergency", "Urgent", "Self-care"];

/** Mốc chia thời gian chờ. Dùng CHUNG cho "thời gian tới lượt mở" (ca đã mở) và "backlog theo tuổi"
 *  (ca chưa chốt) - hai thẻ đọc cùng một thang thì so được với nhau bằng mắt. Mốc 5 phút trùng
 *  `SLA_CLINICAL_SECONDS` có chủ đích. */
const WAIT_BUCKETS = [
  { label: "< 1 phút", max: 1 },
  { label: "1–5 phút", max: 5 },
  { label: "5–15 phút", max: 15 },
  { label: "> 15 phút", max: Infinity },
];

/** Bốn hành động của `HITLAction` (`src/models/schemas.py`). Dùng làm CẢ danh sách nhãn LẪN bộ lọc:
 *  `audit_log` còn chứa những action do hệ thống ghi (`raise_priority_from_c6`, `edit_field:*`,
 *  `completed_after_approval`), và chúng KHÔNG phải quyết định của điều dưỡng - đếm chúng vào đây
 *  sẽ biến một ca được C6 nâng mức thành một "lượt duyệt" không ai thực hiện. */
const NURSE_ACTION_TEXT = {
  approve: "Duyệt nguyên đề xuất",
  edit: "Sửa mức rồi duyệt",
  ask_more: "Hỏi thêm bệnh nhân",
  reject: "Từ chối ca",
};

/** Trạng thái theo thứ tự CÒN VIỆC → ĐÃ XONG, không theo bảng chữ cái: thẻ này để đọc lướt xem
 *  khối lượng đang đọng ở khâu nào, nên thứ tự phải là thứ tự của luồng làm việc. Trạng thái không
 *  có ca nào bị ẩn khỏi danh sách - một hàng 0 dài dằng dặc chỉ làm loãng ba hàng có số thật. */
const STATUS_ORDER = [
  "collecting_information",
  "needs_more_info",
  "needs_nurse_review",
  "awaiting_approval",
  "escalated",
  "approved",
  "rejected",
  "withdrawn",
];

const view = { group: "all", days: 7 };

/** Bản ghi `/nurse/review-log`, một dòng một ca. Giữ ở module chứ không nhét vào `state`: chỉ màn
 *  này đọc nó, và `state.queue` được các màn khác dùng chung nên thêm vào đó là mở rộng vùng ảnh
 *  hưởng mà không được gì. */
let reviewLog = [];

/** Toạ độ x + số liệu của từng điểm trên biểu đồ đường, để lớp hover tra cứu. Giữ ở đây thay vì
 *  nhét JSON vào DOM: chỉ có một biểu đồ đường trên màn và nó được vẽ lại đồng bộ ngay trước khi
 *  hover được nối. */
let linePoints = [];

/** Bật đúng MỘT lần cho lần vẽ đầu tiên sau khi vào màn, và điều khiển TOÀN BỘ hoạt ảnh vào màn
 *  (vòng tròn tự vẽ, cột mọc lên, số đếm tăng dần, thẻ trồi lên theo bậc).
 *
 *  `paintDashboard` còn chạy lại mỗi 15 giây do polling và mỗi lần đổi bộ lọc - để hoạt ảnh chạy ở
 *  những lần đó thì cứ 15 giây cả màn hình lại nhảy múa một lần trong khi điều dưỡng đang đọc số,
 *  và số đang đếm dở thì không đọc được. Vì vậy nó chỉ đúng một nhịp: lúc màn hình vừa hiện ra. */
let introMotion = false;

let polling = null;

/** Dừng vòng polling của màn này. PHẢI được `navigate()` gọi như `stopQueuePolling`: interval bị bỏ
 *  quên sẽ tiếp tục gọi API và ghi đè `state.queue` sau khi điều dưỡng đã sang màn khác. */
export function stopDashboardPolling() {
  if (polling) window.clearInterval(polling);
  polling = null;
}

export function renderNurseDashboard(root, { navigate, logout }) {
  root.innerHTML = nurseShell("dashboard", `
    <div class="queue-head">
      <div>
        <h1>Bảng điều khiển</h1>
        <p>Thống kê trên các ca đã vào hàng đợi. Số liệu vận hành, không phải kết luận lâm sàng.</p>
      </div>
      <span class="polling-chip">${icon("retry", 15)}<span id="dash-updated">Đang tải…</span></span>
    </div>

    <div class="dashboard-toolbar">
      <section class="dashboard-filter-group" aria-label="Lọc theo nhóm triệu chứng">
        <span>Nhóm triệu chứng</span>
        <div class="dashboard-filter-options">
          <button class="dashboard-filter-button is-active" type="button" data-group="all">Tất cả nhóm</button>
          ${GROUP_KEYS.map((key) => `<button class="dashboard-filter-button" type="button" data-group="${key}">${escapeHtml(symptomGroupLabels[key] || key)}</button>`).join("")}
        </div>
      </section>
      <section class="dashboard-filter-group dashboard-period-filter" aria-label="Khoảng thời gian">
        <span>Khoảng thời gian</span>
        <div class="dashboard-filter-options">
          ${RANGES.map(([days, label], index) => `<button class="dashboard-filter-button${index === 1 ? " is-active" : ""}" type="button" data-days="${days}">${label}</button>`).join("")}
        </div>
      </section>
    </div>

    <div id="dash-body"></div>
    <aside id="nurse-new-case-ticker" class="nurse-new-case-ticker" aria-live="polite"></aside>
  `);

  bindAccountMenu(root, { logout, onProfileSaved: () => renderNurseDashboard(root, { navigate, logout }) });
  bindSideNav(root, { navigate, logout }, "dashboard");
  root.querySelectorAll("[data-refresh]").forEach((button) => button.addEventListener("click", () => loadDashboard(root)));
  bindChips(root, "[data-group]", (button) => { view.group = button.dataset.group; });
  bindChips(root, "[data-days]", (button) => { view.days = button.dataset.days === "yesterday" ? "yesterday" : Number(button.dataset.days); });
  root.querySelector("#nurse-new-case-ticker")?.addEventListener("click", (event) => {
    const item = event.target.closest("[data-new-case]");
    if (item) openDashboardCase(item.dataset.newCase, { navigate });
  });
  // Uỷ quyền trên `#dash-body` chứ không gắn lại sau mỗi lần vẽ: `paintDashboard` thay toàn bộ
  // innerHTML mỗi 15 giây, nên listener gắn lên từng hàng sẽ bị dựng lại liên tục.
  root.querySelector("#dash-body").addEventListener("click", (event) => {
    if (event.target.closest("[data-backlog]")) navigate("nurse-queue");
  });

  view.group = "all";
  view.days = 7;
  introMotion = true;
  loadDashboard(root);
  polling = window.setInterval(() => loadDashboard(root), 15000);
}

function bindChips(root, selector, apply) {
  root.querySelectorAll(selector).forEach((button) =>
    button.addEventListener("click", () => {
      root.querySelectorAll(selector).forEach((item) => item.classList.toggle("is-active", item === button));
      apply(button);
      paintDashboard(root);
    }),
  );
}

/** Hai nguồn nạp SONG SONG, và lỗi của nguồn phụ KHÔNG được làm hỏng màn.
 *
 *  `review-log` chỉ nuôi phần chất lượng; hàng đợi nuôi phần trực. Để `Promise.all` thì một lỗi 500
 *  ở thống kê sẽ xoá luôn bảng trực - tức mất phần DUY NHẤT có ích khi đang có ca chờ. Vì vậy
 *  `allSettled`, và nguồn phụ hỏng thì phần chất lượng tự báo rỗng. */
async function loadDashboard(root) {
  const [queue, log] = await Promise.allSettled([
    api("/api/v1/nurse/queue"),
    api("/api/v1/nurse/review-log"),
  ]);
  const stamp = root.querySelector("#dash-updated");
  if (queue.status === "fulfilled") {
    state.queue = queue.value;
    stamp.textContent = `Cập nhật lúc ${new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}`;
  } else {
    stamp.textContent = queue.reason?.message || "Không tải được dữ liệu";
  }
  reviewLog = log.status === "fulfilled" ? log.value : [];
  paintDashboard(root);
}

// ── Tổng hợp số liệu ─────────────────────────────────────────────────────────────────────────────

function groupOf(item) {
  return item.structured_data?.symptom_group || "";
}

/** Mức ưu tiên của một ca - ĐI QUA `displayLevel` của `nurse.js`, không đọc thẳng
 *  `triage_proposal.priority`.
 *
 *  Trước đây file này có bản đọc riêng, và nó lệch với hàng đợi ở đúng hai chỗ `displayLevel` sinh
 *  ra để xử lý: ca có `graph_decision.triage_label` (Part 2 đã nâng mức) và ca `escalated` chưa kịp
 *  có đề xuất. Hệ quả là một ca hiện huy hiệu "Cấp cứu" ở màn Hàng đợi nhưng nằm trong lát "Tự theo
 *  dõi" của biểu đồ tròn ở màn này. */
function priorityOf(item) {
  return displayLevel(item);
}

/** Số phút từ lúc ca vào hàng đợi tới lúc điều dưỡng ĐẦU TIÊN mở nó, hoặc `null` khi chưa mở.
 *
 *  `first_opened_at` chứ không phải `reviewed_at`: mốc SLA an toàn là lúc có người thật NHÌN THẤY ca,
 *  không phải lúc bấm duyệt xong (ADR-007). */
function timeToOpen(item) {
  if (!item.queued_at || !item.first_opened_at) return null;
  return (new Date(item.first_opened_at) - new Date(item.queued_at)) / 60000;
}

/** Số phút từ lúc điều dưỡng mở hồ sơ tới lúc ca được chốt - "công xử lý" của một ca.
 *
 *  Đây là NỬA CÒN LẠI của thời gian chờ mà `timeToOpen` đo. Tách đôi vì hai nửa hỏng vì hai lý do
 *  khác hẳn nhau và cần hai cách sửa khác hẳn nhau: nửa đầu dài nghĩa là THIẾU NGƯỜI TRỰC, nửa sau
 *  dài nghĩa là hồ sơ khó đọc hoặc thiếu thông tin để quyết. Gộp lại thành một con số "tổng thời
 *  gian chờ" thì không phân biệt được hai tình huống đó nữa.
 *
 *  Trả `null` khi thiếu một trong hai mốc, hoặc khi hiệu âm - `first_opened_at` được ghi lần đầu có
 *  người mở, còn một ca đã chốt vẫn mở lại được, nên thứ tự hai mốc không được coi là đảm bảo. */
function handleMinutes(item) {
  if (!item.first_opened_at || !item.reviewed_at) return null;
  const minutes = (new Date(item.reviewed_at) - new Date(item.first_opened_at)) / 60000;
  return minutes >= 0 ? minutes : null;
}

/** Tỉ lệ trường ĐÃ ĐIỀN trên phiếu bàn giao của từng ca, chỉ tính ca đã dựng được phiếu.
 *
 *  Ca chưa có `summary_fields` bị loại khỏi mẫu chứ không tính là 0%: phiếu chưa dựng và phiếu dựng
 *  xong nhưng rỗng là hai chuyện khác nhau, và trộn chúng lại sẽ kéo trung vị xuống đúng lúc hàng
 *  đợi đang có nhiều ca mới - tức là chỉ số báo xấu vì lý do không liên quan đến chất lượng hỏi. */
function summaryFillRatios(cases) {
  return cases
    .filter((item) => (item.summary_fields || []).length)
    .map((item) => item.summary_fields.filter((field) => !field.is_missing).length / item.summary_fields.length);
}

/** Tuổi của một ca đang chờ, tính tới BÂY GIỜ. */
function ageMinutes(item, now = Date.now()) {
  if (!item.queued_at) return null;
  return Math.max(0, (now - new Date(item.queued_at).getTime()) / 60000);
}

/** Phân vị theo nội suy tuyến tính. `null` khi không có mẫu nào - KHÔNG trả 0: "không có ca nào để
 *  đo" và "mở ngay tức thì" là hai chuyện khác hẳn, và một số 0 ở đây đọc thành lời khen. */
function quantile(values, ratio) {
  if (!values.length) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const position = (sorted.length - 1) * ratio;
  const lower = Math.floor(position);
  const upper = Math.min(sorted.length - 1, lower + 1);
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower);
}

function bucketize(values) {
  return WAIT_BUCKETS.map((bucket, index) => ({
    label: bucket.label,
    value: values.filter(
      (minutes) => minutes < bucket.max && (index === 0 || minutes >= WAIT_BUCKETS[index - 1].max),
    ).length,
  }));
}

/** Thời lượng cho người đọc. Dưới một phút thì đọc bằng giây - "0,3 phút" là con số không ai hình
 *  dung được, mà đây lại đúng là khoảng hay gặp nhất khi hàng đợi vắng. */
function formatMinutes(minutes) {
  if (minutes === null) return "—";
  if (minutes < 1) return `${Math.round(minutes * 60)} giây`;
  if (minutes < 60) return `${Math.round(minutes * 10) / 10} phút`.replace(".", ",");
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)} giờ ${Math.round(minutes % 60)} phút`;
  // Quá một ngày thì đọc bằng NGÀY. Một ca tồn từ thứ Sáu hiện ra "142 giờ 34 phút" là con số
  // không ai quy đổi trong đầu được, mà đây đúng là ca đáng chú ý nhất trên màn hình. Bỏ luôn phần
  // phút: ở thang ngày thì hai chữ số phút là nhiễu, không phải độ chính xác.
  const days = Math.floor(minutes / (60 * 24));
  const hours = Math.round((minutes % (60 * 24)) / 60);
  return hours ? `${days} ngày ${hours} giờ` : `${days} ngày`;
}

function median(values) {
  return quantile(values, 0.5);
}

function isSlaBreached(item, now = Date.now()) {
  if (!item.queued_at || item.first_opened_at || completedStatuses.has(item.status)) return false;
  return now - new Date(item.queued_at).getTime() >= SLA_CLINICAL_SECONDS * 1000;
}

/** Ca thuộc phạm vi bộ lọc nhóm hiện tại. Bộ lọc áp cho KPI, biểu đồ đường và biểu đồ tròn; biểu đồ
 *  cột nhóm triệu chứng CỐ Ý không lọc - lọc nó xuống còn một cột thì cả biểu đồ mất ý nghĩa, nên nó
 *  làm nổi cột đang chọn thay vì bỏ các cột còn lại (dạng "emphasis"). */
/** Ca nằm trong KHOẢNG THỜI GIAN đang chọn, theo `created_at`.
 *
 *  Trước đây chip "7 ngày / 30 ngày" chỉ đổi biểu đồ đường, còn năm ô KPI vẫn đếm toàn bộ lịch sử -
 *  một bộ lọc bấm vào mà số không nhúc nhích thì tệ hơn là không có bộ lọc. */
function withinRange(item) {
  const created = dayKey(item.created_at);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  if (view.days === "yesterday") {
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    return created === yesterday.getTime();
  }
  const oldest = new Date(today);
  oldest.setDate(oldest.getDate() - (view.days - 1));
  return created >= oldest.getTime();
}

function scopedCases() {
  return state.queue.filter(
    (item) => (view.group === "all" || groupOf(item) === view.group) && withinRange(item),
  );
}

function dayKey(value) {
  const date = new Date(value);
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

/** Chuỗi ngày liên tục cho biểu đồ đường. Phải sinh đủ mọi ngày kể cả ngày 0 ca: bỏ ngày trống làm
 *  trục x co lại và một tuần yên ả trông y hệt một tuần bận rộn. */
function dailySeries(cases) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = [];
  const offsets = view.days === "yesterday" ? [1] : Array.from({ length: view.days }, (_, index) => view.days - index - 1);
  for (const offset of offsets) {
    const date = new Date(today);
    date.setDate(date.getDate() - offset);
    days.push({ at: date, key: date.getTime(), arrived: 0, settled: 0 });
  }
  const index = new Map(days.map((day) => [day.key, day]));
  for (const item of cases) {
    const arrived = index.get(dayKey(item.created_at));
    if (arrived) arrived.arrived += 1;
    if (item.reviewed_at) {
      const settled = index.get(dayKey(item.reviewed_at));
      if (settled) settled.settled += 1;
    }
  }
  return days;
}

// ── Vẽ ───────────────────────────────────────────────────────────────────────────────────────────

function paintDashboard(root) {
  paintOverview(root);
  const cases = scopedCases();
  const scopeName = view.group === "all" ? "tất cả nhóm" : symptomGroupLabels[view.group] || view.group;
  const redFlags = cases.filter((item) => item.status === "escalated" || item.red_flags?.length).length;
  const settled = cases.filter((item) => completedStatuses.has(item.status)).length;
  const overdue = cases.filter((item) => isSlaBreached(item)).length;

  const pending = cases.filter((item) => !completedStatuses.has(item.status));
  const longestWait = pending.length ? Math.max(...pending.map((item) => ageMinutes(item) ?? 0)) : null;

  const days = dailySeries(cases);
  const body = root.querySelector("#dash-body");
  body.innerHTML = `
    ${sectionHead("Bảng trực", "Cần xử lý ngay. Số liệu sống, tự làm mới mỗi 15 giây.")}

    <div class="kpi-row">
      ${statTile("Tổng số ca", cases.length, `Trong phạm vi: ${escapeHtml(scopeName)}`, "", sparkline(days))}
      ${statTile("Có dấu hiệu nguy hiểm", redFlags, cases.length ? `${Math.round((redFlags / cases.length) * 100)}% tổng số ca` : "Chưa có dữ liệu")}
      ${statTile("Đang chờ được xác nhận", cases.length - settled, pendingNote(pending, longestWait))}
      ${statTile("Ca quá hạn", overdue, overdueNote(pending, overdue), overdue ? "is-overdue" : "")}
      ${statTile("Đã chốt", settled, "Duyệt, từ chối hoặc đóng")}
    </div>

    <div class="chart-row">
      ${lineChartCard(days)}
      ${donutCard(cases)}
    </div>

    <div class="chart-row">
      ${timeToOpenCard(cases)}
      ${backlogCard()}
    </div>

    <div class="chart-row">
      ${handleTimeCard(cases)}
      ${statusMixCard(cases)}
    </div>

    ${sectionHead("Bảng chất lượng", "Hệ thống đang chạy tốt tới đâu. Đọc để đánh giá, không để xử lý ca.")}

    ${agreementRow(cases)}

    <div class="chart-row">
      ${agreementMatrixCard(cases)}
      ${groupBarCard()}
    </div>

    <div class="chart-row is-thirds">
      ${barCard("Dấu hiệu nguy hiểm hay gặp", topCounts(cases, redFlagLabels), "Chưa ca nào có dấu hiệu nguy hiểm", { stacked: true })}
      ${barCard("Thông tin hay bị thiếu nhất", topCounts(cases, missingFieldLabels), "Chưa ca nào chốt phiếu bàn giao", { stacked: true })}
      ${hourChartCard(cases)}
    </div>

    <div class="chart-row">
      ${actionMixCard(cases)}
      ${nurseWorkloadCard(cases)}
    </div>
  `;
  // Hoạt ảnh vào màn nằm sau MỘT class duy nhất trên thân màn: gắn/gỡ ở đây thay vì rắc `is-…` lên
  // từng thẻ để chỉ có đúng một chỗ quyết định "lần vẽ này có chạy hiệu ứng không".
  body.classList.toggle("is-intro", introMotion);
  bindLineHover(root);
  bindBarHover(root);
  if (introMotion) runCountUp(body);
  paintNewCaseTicker(root);
  introMotion = false;
}

/** Đếm số từ 0 lên giá trị thật cho các ô KPI, chỉ ở lần vẽ đầu tiên.
 *
 *  Đọc `data-count` do `statTile` gắn sẵn chứ không parse `textContent`: nội dung ô có thể là "—",
 *  "2,4 phút" hay "100%", và một hàm đoán số từ chuỗi hiển thị sẽ vừa đếm nhầm "2,4 phút" thành 24
 *  vừa im lặng khi ai đó đổi cách định dạng.
 *
 *  Người đã tắt hiệu ứng ở cấp hệ điều hành thấy ngay số cuối - hàm thoát trước khi chạm vào DOM,
 *  nên giá trị do `statTile` dựng vẫn còn nguyên. */
function runCountUp(body) {
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
  for (const node of body.querySelectorAll("[data-count]")) {
    const target = Number(node.dataset.count);
    if (!Number.isFinite(target) || target <= 0) continue;
    const suffix = node.dataset.countSuffix || "";
    const start = performance.now();
    const step = (now) => {
      const progress = Math.min(1, (now - start) / 620);
      node.textContent = `${Math.round(target * (1 - (1 - progress) ** 3))}${suffix}`;
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
}

function sectionHead(title, note) {
  return `<div class="dash-section">
    <h2>${escapeHtml(title)}</h2>
    <p>${escapeHtml(note)}</p>
  </div>`;
}

/** Ghi chú của ô "Đang chờ": ca chờ lâu nhất bao lâu rồi. Một ô đứng yên ở 0 với dòng mô tả bất
 *  biến thì không nói được gì; con số này đổi mỗi lần polling và đúng là thứ điều dưỡng cần biết. */
function pendingNote(pending, longestWait) {
  if (!pending.length) return "Không còn ca nào chờ quyết định";
  if (longestWait === null) return "Chưa có quyết định của nhân viên y tế";
  return `Chờ lâu nhất: ${formatMinutes(longestWait)}`;
}

/** Ghi chú của ô "Ca quá hạn". Khi bằng 0 thì nói ca nào GẦN ngưỡng nhất còn bao lâu, thay vì lặp
 *  lại định nghĩa SLA mà người dùng đã đọc ở lần đầu. */
function overdueNote(pending, overdue) {
  if (overdue) return "Quá 5 phút, chưa có nhân viên mở hồ sơ";
  const waiting = pending.filter((item) => !item.first_opened_at && item.queued_at);
  if (!waiting.length) return "Không có ca nào đang đếm giờ";
  const oldest = Math.max(...waiting.map((item) => ageMinutes(item) ?? 0));
  return `Ca sát ngưỡng nhất còn ${formatMinutes(Math.max(0, SLA_CLINICAL_SECONDS / 60 - oldest))}`;
}

/** Dải ở đáy dashboard là một tín hiệu vận hành, không thay thế hàng đợi: chỉ nhắc những ca chưa
 * được chốt và dẫn điều dưỡng tới đúng hồ sơ để vẫn thực hiện bước duyệt HITL. */
function paintNewCaseTicker(root) {
  const ticker = root.querySelector("#nurse-new-case-ticker");
  if (!ticker) return;

  const cases = state.queue
    .filter((item) => !completedStatuses.has(item.status))
    .sort((left, right) => {
      const urgency = (item) => (item.status === "escalated" || item.red_flags?.length || priorityOf(item) === "Emergency" ? 0 : 1);
      return urgency(left) - urgency(right) || new Date(right.created_at) - new Date(left.created_at);
    })
    .slice(0, 6);

  if (!cases.length) {
    ticker.classList.add("is-empty");
    const waitingMessage = `${icon("pulse", 15)} VMedTriage đang theo dõi ca mới trong hàng đợi. Khi có bệnh nhân cần xử lý, thông báo sẽ xuất hiện tại đây để nhân viên y tế mở hồ sơ và xem xét.`;
    ticker.innerHTML = `<div class="nurse-new-case-ticker-viewport">
      <div class="nurse-new-case-ticker-track">
        <div class="nurse-new-case-ticker-group"><span class="nurse-new-case-ticker-empty">${waitingMessage}</span><i aria-hidden="true">•</i><span class="nurse-new-case-ticker-empty">${waitingMessage}</span></div>
        <div class="nurse-new-case-ticker-group" aria-hidden="true"><span class="nurse-new-case-ticker-empty">${waitingMessage}</span><i>•</i><span class="nurse-new-case-ticker-empty">${waitingMessage}</span></div>
      </div>
    </div>`;
    return;
  }

  const itemMarkup = (item, interactive) => {
    const priority = priorityOf(item);
    const isUrgent = item.status === "escalated" || item.red_flags?.length || priority === "Emergency";
    const name = item.patient_display_name || `Bệnh nhân · ${shortCaseId(item.case_id)}`;
    const symptom = symptomGroupLabels[groupOf(item)] || "Triệu chứng chưa xác định";
    const label = `${isUrgent ? "Ca cần ưu tiên" : "Ca mới"}: ${name}, ${symptom}. ${priorityLabels[priority] || "Cần điều dưỡng xem xét"}.`;
    const content = `<span class="nurse-ticker-status${isUrgent ? " is-urgent" : ""}">${isUrgent ? "Ưu tiên" : "Ca mới"}</span>
      <b>${escapeHtml(name)}</b><span>${escapeHtml(symptom)}</span>
      <small>${escapeHtml(priorityLabels[priority] || "Cần xem xét")}</small>`;
    return interactive
      ? `<button class="nurse-ticker-item" type="button" data-new-case="${escapeHtml(item.case_id)}" aria-label="${escapeHtml(label)}">${content}</button>`
      : `<span class="nurse-ticker-item" aria-hidden="true">${content}</span>`;
  };

  // Một hàng đợi ngắn cũng phải đủ dài để cuộn liên tục trên màn hình rộng. Các bản sao bổ sung
  // chỉ để lấp dải chạy nên được ẩn khỏi trình đọc màn hình và không nhận focus.
  const displayedItems = cases.map((item) => itemMarkup(item, true));
  const fillerItems = Array.from({ length: Math.max(0, 8 - cases.length) }, (_, index) => itemMarkup(cases[index % cases.length], false));
  const tickerItems = displayedItems.concat(fillerItems).join("");

  ticker.classList.remove("is-empty");
  ticker.innerHTML = `<div class="nurse-new-case-ticker-viewport">
    <div class="nurse-new-case-ticker-track">
      <div class="nurse-new-case-ticker-group">${tickerItems}</div>
      <div class="nurse-new-case-ticker-group" aria-hidden="true">${cases.map((item) => itemMarkup(item, false)).concat(fillerItems).join("")}</div>
    </div>
  </div>`;
}

async function openDashboardCase(caseId, { navigate }) {
  try {
    state.selectedNurseCase = await api(`/api/v1/cases/${caseId}`);
    sessionStorage.setItem("vmed_active_nurse_case_id", caseId);
    navigate("nurse-case");
  } catch (problem) {
    showToast(problem.message || "Không thể mở hồ sơ ca.", true);
  }
}

function statTile(label, value, note, tone = "", spark = "") {
  return `<div class="kpi-tile ${tone}">
    <span class="kpi-label">${escapeHtml(label)}</span>
    <b class="kpi-value"${countAttrs(value)}>${escapeHtml(String(value))}</b>
    ${spark}
    <span class="kpi-note">${escapeHtml(note)}</span>
  </div>`;
}

/** Thuộc tính cho hiệu ứng đếm số, CHỈ khi giá trị là một số nguyên (kèm `%` nếu có).
 *
 *  Đếm được thì đếm, không thì thôi - "—", "2,4 phút" hay "1 ngày 4 giờ" đều đi qua đây và không
 *  nhận thuộc tính nào, nên `runCountUp` bỏ qua chúng và ô hiện thẳng giá trị thật. Không cố xử lý
 *  các dạng đó: đếm tăng dần một khoảng thời gian thì con số ở giữa đường là một khoảng thời gian
 *  SAI đang được trưng ra, còn đếm một dấu gạch ngang thì vô nghĩa. */
function countAttrs(value) {
  const match = /^(\d+)(%?)$/.exec(String(value));
  return match ? ` data-count="${match[1]}" data-count-suffix="${match[2]}"` : "";
}

// Cao 30px và không có trục: đây là một dấu hiệu HÌNH DẠNG đặt cạnh con số, không phải biểu đồ thứ
// hai. Biểu đồ đường đầy đủ ngay bên dưới mới là chỗ đọc giá trị từng ngày.
const SPARK = { width: 132, height: 30 };

/** Đường xu hướng tí hon trong ô "Tổng số ca": số ca vào theo từng ngày của khoảng đang chọn.
 *
 *  Có nó vì một ô chỉ hiện "5" không nói được 5 ca đó dồn vào một hôm hay rải đều cả tuần - mà đó
 *  đúng là điều đầu tiên người đọc muốn biết khi liếc vào con số tổng. Vẫn KHÔNG có ô "+15%": so
 *  sánh hai kỳ cần một chuỗi thời gian được lưu lại, còn đây chỉ vẽ đúng dữ liệu đang có trong
 *  phạm vi lọc, không suy ra con số nào không đo được. */
function sparkline(days) {
  if (days.length < 2 || !days.some((day) => day.arrived)) return "";
  const peak = Math.max(1, ...days.map((day) => day.arrived));
  const stepX = SPARK.width / (days.length - 1);
  const yAt = (value) => SPARK.height - 3 - ((SPARK.height - 9) * value) / peak;
  const line = days
    .map((day, index) => `${index ? "L" : "M"}${(index * stepX).toFixed(1)},${yAt(day.arrived).toFixed(1)}`)
    .join(" ");
  const last = days[days.length - 1];
  return `<svg class="kpi-spark" viewBox="0 0 ${SPARK.width} ${SPARK.height}" role="img" aria-label="Xu hướng số ca vào theo ngày trong khoảng đang chọn">
    <path d="${line} L${SPARK.width},${SPARK.height} L0,${SPARK.height} Z" fill="${SERIES_IN}" fill-opacity=".12" />
    <path class="kpi-spark-line" pathLength="1" d="${line}" fill="none" stroke="${SERIES_IN}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" />
    <circle cx="${SPARK.width}" cy="${yAt(last.arrived).toFixed(1)}" r="2.4" fill="${SERIES_IN}" />
  </svg>`;
}

// ── Thời gian tới lượt mở + backlog ──────────────────────────────────────────────────────────────

/** Trung vị và p90 thời gian từ lúc ca vào hàng đợi tới lúc có người mở.
 *
 *  CHỈ TÍNH TRÊN CA ĐÃ MỞ, và số ca chưa mở được ghi riêng bên cạnh. Đây không phải chi tiết vụn:
 *  ca chưa mở là dữ liệu bị CẮT PHẢI - ta biết nó đã chờ ít nhất X phút, không biết cuối cùng chờ
 *  bao lâu. Trộn X vào mẫu sẽ kéo trung vị XUỐNG đúng lúc hàng đợi đang tắc nhất, tức là chỉ số báo
 *  đẹp nhất vào lúc tình hình xấu nhất. Bỏ chúng đi và nói rõ đã bỏ mấy ca là cách duy nhất trung
 *  thực mà không cần thêm cột dữ liệu nào. */
function timeToOpenCard(cases) {
  const opened = cases.map(timeToOpen).filter((minutes) => minutes !== null);
  const unopened = cases.filter((item) => item.queued_at && !item.first_opened_at).length;
  return durationCard({
    title: "Thời gian tới lượt mở",
    sub: unopened ? `${unopened} ca chưa ai mở, không tính vào đây` : "Tính trên ca đã được mở",
    values: opened,
  });
}

/** Nửa sau của thời gian chờ: từ lúc điều dưỡng MỞ hồ sơ tới lúc ca được chốt.
 *
 *  Đặt cạnh "thời gian tới lượt mở" và dùng CHUNG mốc chia (`WAIT_BUCKETS`) có chủ đích - hai thẻ
 *  cùng thang thì đọc được ngay nửa nào đang ăn hết thời gian chờ của người bệnh, mà mỗi nửa lại
 *  cần một cách sửa khác nhau (xem `handleMinutes`).
 *
 *  Ca đã mở nhưng CHƯA chốt bị loại khỏi mẫu và được đếm riêng ở dòng phụ, đúng cách `timeToOpen`
 *  loại ca chưa mở: chúng là dữ liệu bị cắt phải, mà một ca điều dưỡng còn đang cân nhắc thì tính
 *  vào trung vị sẽ kéo con số xuống đúng lúc có ca khó. */
function handleTimeCard(cases) {
  const handled = cases.map(handleMinutes).filter((minutes) => minutes !== null);
  const openPending = cases.filter((item) => item.first_opened_at && !item.reviewed_at).length;
  return durationCard({
    title: "Thời gian mở tới lúc chốt",
    sub: openPending ? `${openPending} ca đã mở nhưng chưa chốt, không tính vào đây` : "Tính trên ca đã chốt",
    values: handled,
    foot: "Cùng mốc chia với thẻ “Thời gian tới lượt mở”: hai thẻ cộng lại là toàn bộ thời gian người bệnh chờ.",
  });
}

/** Khung chung của hai thẻ đo thời lượng: ba số dẫn (trung vị / P90 / cỡ mẫu) rồi tới phân bố theo
 *  `WAIT_BUCKETS`. Tách ra vì hai thẻ phải trông GIỐNG HỆT nhau mới so sánh bằng mắt được, và hai
 *  bản sao markup thì chỉ cần một lần sửa lệch là mất đúng điều đó. */
function durationCard({ title, sub, values, foot = "" }) {
  const rows = bucketize(values);
  const peak = Math.max(1, ...rows.map((row) => row.value));

  return `<section class="chart-card">
    <div class="chart-head">
      <h2>${escapeHtml(title)}</h2>
      <span class="chart-sub">${escapeHtml(sub)}</span>
    </div>
    <div class="stat-pair">
      <div><span class="kpi-label">Trung vị</span><b class="kpi-value">${escapeHtml(formatMinutes(median(values)))}</b></div>
      <div><span class="kpi-label">P90</span><b class="kpi-value">${escapeHtml(formatMinutes(quantile(values, 0.9)))}</b></div>
      <div><span class="kpi-label">Số ca đo được</span><b class="kpi-value">${values.length}</b></div>
    </div>
    <ul class="bar-list">
      ${rows
        .map(
          (row) => `<li class="bar-row" data-bar tabindex="0" aria-label="${escapeHtml(row.label)}: ${row.value} ca">
            <span class="bar-name">${escapeHtml(row.label)}</span>
            <span class="bar-track"><span class="bar-fill" style="width:${row.value ? Math.max(2, (row.value / peak) * 100) : 0}%"></span></span>
            <b class="bar-value">${row.value}</b>
          </li>`,
        )
        .join("")}
    </ul>
    ${foot ? `<p class="chart-foot">${escapeHtml(foot)}</p>` : ""}
  </section>`;
}

/** Ca CHƯA CHỐT chia theo tuổi, và CỐ Ý không áp bộ lọc khoảng thời gian.
 *
 *  Một ca mở từ ba hôm trước mà chưa ai xử lý vẫn đang chờ ngay lúc này. Cho nó biến mất chỉ vì
 *  người dùng bấm chip "Hôm qua" là giấu đúng ca đáng lo nhất - cùng lý do biểu đồ nhóm triệu chứng
 *  không lọc. Bộ lọc nhóm thì vẫn áp, vì nó không giấu ca khỏi tổng. */
function backlogCard() {
  const pending = state.queue.filter(
    (item) =>
      !completedStatuses.has(item.status)
      && item.queued_at
      && (view.group === "all" || groupOf(item) === view.group),
  );
  const rows = bucketize(pending.map((item) => ageMinutes(item)));
  const peak = Math.max(1, ...rows.map((row) => row.value));

  return `<section class="chart-card">
    <div class="chart-head">
      <h2>Ca đang chờ, theo tuổi</h2>
      <span class="chart-sub">${pending.length} ca chưa chốt · mọi thời điểm</span>
    </div>
    <ul class="bar-list">
      ${rows
        .map(
          (row, index) => `<li class="bar-row${index >= 2 && row.value ? " is-alarm" : ""}" data-bar data-backlog role="button" tabindex="0" aria-label="${escapeHtml(row.label)}: ${row.value} ca đang chờ, mở hàng đợi">
            <span class="bar-name">${escapeHtml(row.label)}</span>
            <span class="bar-track"><span class="bar-fill" style="width:${row.value ? Math.max(2, (row.value / peak) * 100) : 0}%"></span></span>
            <b class="bar-value">${row.value}</b>
          </li>`,
        )
        .join("")}
    </ul>
    <p class="chart-foot">${pending.length ? "Không áp bộ lọc khoảng thời gian, nên tổng ở đây cao hơn ô “Đang chờ được xác nhận” khi có ca tồn từ trước. Bấm một hàng để mở hàng đợi." : "Hàng đợi đang trống."}</p>
  </section>`;
}

// ── Biểu đồ đường: ca vào vs ca chốt ─────────────────────────────────────────────────────────────

const LINE = { width: 660, height: 236, left: 38, right: 58, top: 18, bottom: 30 };

function lineChartCard(days) {
  const peak = Math.max(1, ...days.map((day) => Math.max(day.arrived, day.settled)));
  const top = niceCeiling(peak);
  const plotWidth = LINE.width - LINE.left - LINE.right;
  const plotHeight = LINE.height - LINE.top - LINE.bottom;
  const xAt = (index) => LINE.left + (days.length === 1 ? plotWidth / 2 : (plotWidth * index) / (days.length - 1));
  const yAt = (value) => LINE.top + plotHeight - (plotHeight * value) / top;

  const ticks = [0, top / 2, top];
  const grid = ticks
    .map((tick) => `<line x1="${LINE.left}" y1="${yAt(tick)}" x2="${LINE.left + plotWidth}" y2="${yAt(tick)}" stroke="#e3e8ef" stroke-width="1" />
       <text x="${LINE.left - 9}" y="${yAt(tick) + 4}" text-anchor="end" class="axis-text">${tick}</text>`)
    .join("");

  // Nhãn trục x thưa dần khi khoảng thời gian dài: 30 nhãn chen nhau thì không đọc được nhãn nào.
  const labelEvery = Math.ceil(days.length / 7);
  const xLabels = days
    .map((day, index) =>
      index % labelEvery === 0 || index === days.length - 1
        ? `<text x="${xAt(index)}" y="${LINE.height - 9}" text-anchor="middle" class="axis-text">${day.at.getDate()}/${day.at.getMonth() + 1}</text>`
        : "",
    )
    .join("");

  const path = (pick) => days.map((day, index) => `${index ? "L" : "M"}${xAt(index).toFixed(1)},${yAt(pick(day)).toFixed(1)}`).join(" ");
  // Vệt nền dưới đường "ca vào" - đóng xuống đường gốc rồi về điểm đầu. CHỈ một series được tô:
  // tô cả hai thì hai vệt chồng lên nhau và vùng giao có màu thứ ba không mang nghĩa gì. Series
  // được chọn là "ca vào" vì nó là lượng việc đổ đến, còn "ca chốt" đọc như một đường bám theo nó.
  const areaPath = `${path((day) => day.arrived)} L${xAt(days.length - 1).toFixed(1)},${yAt(0).toFixed(1)} L${xAt(0).toFixed(1)},${yAt(0).toFixed(1)} Z`;
  const last = days[days.length - 1];
  linePoints = days.map((day, index) => ({
    label: `${day.at.getDate()}/${day.at.getMonth() + 1}`,
    arrived: day.arrived,
    settled: day.settled,
    x: xAt(index),
  }));

  return `<section class="chart-card">
    <div class="chart-head">
      <h2>Ca vào và ca chốt theo ngày</h2>
      <div class="chart-legend">
        <span><i class="key-line" style="background:${SERIES_IN}"></i>Ca vào</span>
        <span><i class="key-line" style="background:${SERIES_DONE}"></i>Ca chốt</span>
      </div>
    </div>
    <div class="chart-plot" data-line>
      <svg viewBox="0 0 ${LINE.width} ${LINE.height}" role="img" aria-label="Số ca vào hàng đợi và số ca được chốt theo từng ngày">
        <defs>
          <linearGradient id="line-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="${SERIES_IN}" stop-opacity="0.16" />
            <stop offset="100%" stop-color="${SERIES_IN}" stop-opacity="0" />
          </linearGradient>
        </defs>
        ${grid}${xLabels}
        <path d="${areaPath}" fill="url(#line-area)" stroke="none" />
        <path class="line-series" pathLength="1" d="${path((day) => day.arrived)}" fill="none" stroke="${SERIES_IN}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
        <path class="line-series is-second" pathLength="1" d="${path((day) => day.settled)}" fill="none" stroke="${SERIES_DONE}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
        <circle cx="${xAt(days.length - 1)}" cy="${yAt(last.arrived)}" r="4.5" fill="${SERIES_IN}" stroke="#fff" stroke-width="2" />
        <circle cx="${xAt(days.length - 1)}" cy="${yAt(last.settled)}" r="4.5" fill="${SERIES_DONE}" stroke="#fff" stroke-width="2" />
        <text x="${xAt(days.length - 1) + 10}" y="${yAt(last.arrived) + 4}" class="end-label">${last.arrived}</text>
        <text x="${xAt(days.length - 1) + 10}" y="${yAt(last.settled) + 4}" class="end-label">${last.settled}</text>
        <line class="crosshair" x1="0" y1="${LINE.top}" x2="0" y2="${LINE.top + plotHeight}" stroke="#8494a4" stroke-width="1" hidden />
        <rect x="${LINE.left}" y="${LINE.top}" width="${plotWidth}" height="${plotHeight}" fill="transparent" data-line-hit />
      </svg>
      <div class="chart-tip" hidden></div>
    </div>
  </section>`;
}

function niceCeiling(value) {
  if (value <= 5) return 5;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / magnitude) * magnitude;
}

function bindLineHover(root) {
  const plot = root.querySelector("[data-line]");
  if (!plot) return;
  const days = linePoints;
  if (!days.length) return;
  const svg = plot.querySelector("svg");
  const crosshair = plot.querySelector(".crosshair");
  const tip = plot.querySelector(".chart-tip");

  const move = (event) => {
    const box = svg.getBoundingClientRect();
    const svgX = ((event.clientX - box.left) / box.width) * LINE.width;
    // Bắt dính vào điểm dữ liệu GẦN NHẤT chứ không đòi trỏ đúng đường 2px: người đọc nhắm vào một
    // ngày, không nhắm vào nét vẽ.
    const nearest = days.reduce((found, day) => (Math.abs(day.x - svgX) < Math.abs(found.x - svgX) ? day : found), days[0]);
    crosshair.setAttribute("x1", nearest.x);
    crosshair.setAttribute("x2", nearest.x);
    crosshair.hidden = false;
    tip.hidden = false;
    tip.replaceChildren(
      tipRow(nearest.label, "", true),
      tipRow("Ca vào", nearest.arrived, false, SERIES_IN),
      tipRow("Ca chốt", nearest.settled, false, SERIES_DONE),
    );
    tip.style.left = `${(nearest.x / LINE.width) * 100}%`;
  };

  plot.addEventListener("pointermove", move);
  plot.addEventListener("pointerleave", () => { crosshair.hidden = true; tip.hidden = true; });
}

/** Nhãn đi vào DOM bằng `textContent`, không ghép chuỗi HTML: nội dung này bắt nguồn từ dữ liệu ca. */
function tipRow(label, value, isHead, tone) {
  const row = document.createElement("div");
  row.className = isHead ? "tip-head" : "tip-row";
  if (tone) {
    const key = document.createElement("i");
    key.className = "key-line";
    key.style.background = tone;
    row.append(key);
  }
  const name = document.createElement("span");
  name.textContent = label;
  row.append(name);
  if (!isHead) {
    const amount = document.createElement("b");
    amount.textContent = String(value);
    row.append(amount);
  }
  return row;
}

// ── Biểu đồ tròn: phân bố mức ưu tiên ────────────────────────────────────────────────────────────

function donutCard(cases) {
  const counts = Object.keys(PRIORITY_TONES).map((key) => ({
    key,
    label: PRIORITY_TEXT[key],
    tone: PRIORITY_TONES[key],
    value: cases.filter((item) => priorityOf(item) === key).length,
  }));
  const total = counts.reduce((sum, slice) => sum + slice.value, 0);

  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  let drawn = 0;
  const arcs = counts
    .filter((slice) => slice.value)
    .map((slice) => {
      const share = slice.value / total;
      // Khe 2px màu nền tách các lát - đúng cơ chế "surface gap", không vẽ viền quanh lát.
      const length = Math.max(0, share * circumference - 2);
      const arc = `<circle data-arc cx="70" cy="70" r="${radius}" fill="none" stroke="${slice.tone}" stroke-width="20"
        stroke-dasharray="${length} ${circumference - length}" stroke-dashoffset="${-offset}"
        transform="rotate(-90 70 70)" style="--circ:${circumference.toFixed(2)}; animation-delay:${(drawn * 0.12).toFixed(2)}s" />`;
      offset += share * circumference;
      drawn += 1;
      return arc;
    })
    .join("");

  return `<section class="chart-card">
    <div class="chart-head"><h2>Phân bố mức ưu tiên</h2></div>
    <div class="donut-wrap">
      <svg viewBox="0 0 140 140" class="donut${introMotion ? " is-drawing" : ""}" role="img" aria-label="Tỉ lệ ca theo ba mức ưu tiên">
        ${total ? arcs : `<circle cx="70" cy="70" r="${radius}" fill="none" stroke="#f1f4f8" stroke-width="20" />`}
        <text x="70" y="66" text-anchor="middle" class="donut-total">${total}</text>
        <text x="70" y="84" text-anchor="middle" class="donut-caption">ca</text>
      </svg>
      <ul class="donut-table">
        ${counts
          .map(
            (slice) => `<li>
              <span class="priority-dot ${slice.key === "Emergency" ? "is-emergency" : slice.key === "Urgent" ? "is-urgent" : "is-self-care"}"></span>
              <span class="donut-name">${escapeHtml(slice.label)}</span>
              <b>${slice.value}</b>
              <span class="donut-share">${total ? Math.round((slice.value / total) * 100) : 0}%</span>
            </li>`,
          )
          .join("")}
      </ul>
    </div>
  </section>`;
}

// ── AI đề xuất so với điều dưỡng chốt ────────────────────────────────────────────────────────────

/** Các dòng review-log ĐƯỢC TÍNH vào thống kê độ chính xác, đã join với hàng đợi để áp bộ lọc.
 *
 *  BA ĐIỀU KIỆN LOẠI, cả ba đều bắt buộc:
 *
 *  1. `withdrawn` - điều dưỡng đóng ca vì lý do ngoài chuyên môn (đã xử lý offline). Không phải một
 *     phán quyết về mức ưu tiên.
 *  2. `reject` với lý do KHÁC `ai_incorrect` - chính `hitl_review` ghi rõ hai mã còn lại phải bị
 *     loại NGAY TỪ NGUỒN. Đếm chúng vào mẫu số là đổ lỗi cho AI về những ca nó không sai.
 *  3. Dòng thiếu mức ở một trong hai đầu, hoặc mức nằm ngoài ba mức hiển thị (`Routine`,
 *     `Manual review`). Ma trận 3×3 không có ô cho chúng, và nhét đại vào một ô là bịa số. */
function agreementRows(cases) {
  const inScope = new Set(cases.map((item) => item.case_id));
  return reviewLog.filter(
    (row) =>
      inScope.has(row.case_id)
      && row.action !== "withdrawn"
      && !(row.action === "reject" && row.reject_reason !== "ai_incorrect")
      && LEVELS.includes(row.ai_priority)
      && LEVELS.includes(row.final_priority),
  );
}

function agreementRow(cases) {
  const rows = agreementRows(cases);
  const kept = rows.filter((row) => row.ai_priority === row.final_priority).length;
  // Chiều NÂNG là chiều đáng lo: AI đề xuất nhẹ hơn mức điều dưỡng chốt nghĩa là nó đã đánh giá
  // thấp một ca thật. `LEVELS` xếp nặng dần xuống nên "nâng" là chỉ số GIẢM.
  const raised = rows.filter((row) => LEVELS.indexOf(row.final_priority) < LEVELS.indexOf(row.ai_priority)).length;
  const turns = cases.map((item) => (item.conversation || []).length).filter(Boolean);
  const confidences = cases
    .map((item) => item.structured_data?.confidence)
    .filter((value) => typeof value === "number" && value > 0);
  const fillRatios = summaryFillRatios(cases);
  const lowQuality = cases.filter((item) => item.quality_flag === "low_quality").length;

  return `<div class="kpi-row">
    ${statTile(
      "Điều dưỡng giữ nguyên mức AI",
      rows.length ? `${Math.round((kept / rows.length) * 100)}%` : "—",
      rows.length ? `${kept}/${rows.length} ca được tính` : "Chưa có ca nào đủ điều kiện tính",
    )}
    ${statTile(
      "AI đề xuất nhẹ hơn thực tế",
      raised,
      rows.length ? "Ca bị điều dưỡng nâng mức" : "Chưa có dữ liệu",
      raised ? "is-overdue" : "",
    )}
    ${statTile("Số lượt hội thoại trung vị", turns.length ? Math.round(median(turns)) : "—", "Tính cả câu hỏi của trợ lý")}
    ${statTile(
      "Độ tin cậy trích xuất trung vị",
      confidences.length ? `${Math.round(median(confidences) * 100)}%` : "—",
      "Do bước trích xuất tự chấm",
    )}
    ${statTile(
      "Phiếu bàn giao đã điền",
      fillRatios.length ? `${Math.round(median(fillRatios) * 100)}%` : "—",
      fillRatios.length ? `Trung vị trên ${fillRatios.length} phiếu đã dựng` : "Chưa ca nào dựng được phiếu",
    )}
    ${statTile(
      "Hội thoại chất lượng thấp",
      lowQuality,
      cases.length ? `${Math.round((lowQuality / cases.length) * 100)}% tổng số ca` : "Chưa có dữ liệu",
      lowQuality ? "is-watch" : "",
    )}
  </div>`;
}

/** Ma trận 3×3: hàng là mức AI đề xuất, cột là mức điều dưỡng chốt.
 *
 *  Chỉ TÔ ĐỎ nửa dưới đường chéo (AI nhẹ hơn thực tế). Nửa trên - điều dưỡng hạ mức - là AI thận
 *  trọng quá mức, tốn công người đọc chứ không nguy hiểm cho người bệnh; tô cả hai bằng một màu sẽ
 *  làm mất đúng sự phân biệt khiến ma trận này đáng vẽ. */
function agreementMatrixCard(cases) {
  const rows = agreementRows(cases);
  const cell = (from, to) => rows.filter((row) => row.ai_priority === from && row.final_priority === to).length;

  return `<section class="chart-card">
    <div class="chart-head">
      <h2>AI đề xuất so với điều dưỡng chốt</h2>
      <span class="chart-sub">${rows.length} ca được tính</span>
    </div>
    <div class="matrix-scroll">
      <table class="agreement-matrix">
        <caption class="sr-only">Số ca theo mức AI đề xuất và mức điều dưỡng chốt</caption>
        <thead>
          <tr>
            <th scope="col"><span class="matrix-corner">AI ↓ / Chốt →</span></th>
            ${LEVELS.map((level) => `<th scope="col">${escapeHtml(PRIORITY_TEXT[level])}</th>`).join("")}
          </tr>
        </thead>
        <tbody>
          ${LEVELS.map(
            (from) => `<tr>
              <th scope="row">${escapeHtml(PRIORITY_TEXT[from])}</th>
              ${LEVELS.map((to) => {
                const value = cell(from, to);
                const isSame = from === to;
                const isUnderCall = LEVELS.indexOf(to) < LEVELS.indexOf(from);
                const tone = isSame ? " is-same" : isUnderCall && value ? " is-under" : "";
                return `<td class="matrix-cell${tone}">${value}</td>`;
              }).join("")}
            </tr>`,
          ).join("")}
        </tbody>
      </table>
    </div>
    <p class="chart-foot">Đã loại ca đóng vì lý do ngoài chuyên môn và ca từ chối không phải do AI sai. Ô tô đỏ là ca AI đánh giá nhẹ hơn mức điều dưỡng chốt.</p>
  </section>`;
}

// ── Đếm nhãn: red flag và thông tin còn thiếu ────────────────────────────────────────────────────

function redFlagLabels(item) {
  return (item.red_flags || []).map((flag) => flag.label).filter(Boolean);
}

/** Nhãn của các trường CHƯA điền trong phiếu bàn giao.
 *
 *  Đọc `summary_fields[].label` chứ không đọc `validation.missing_fields`: `summary_fields` đã mang
 *  sẵn nhãn tiếng Việt do `symptom_case_bridge` lấy từ `protocol.fields_by_key[key].label`, còn
 *  `missing_fields` là khoá thô (`fever_onset_days`) và làm đẹp nó bằng `humanize()` sẽ ra một chuỗi
 *  không khớp với bất cứ chữ nào điều dưỡng thấy ở màn duyệt. */
function missingFieldLabels(item) {
  return (item.summary_fields || []).filter((field) => field.is_missing).map((field) => field.label).filter(Boolean);
}

function topCounts(cases, pick, limit = 6) {
  const tally = new Map();
  for (const item of cases) {
    for (const label of pick(item)) tally.set(label, (tally.get(label) || 0) + 1);
  }
  return [...tally.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], "vi"))
    .slice(0, limit)
    .map(([label, value]) => ({ label, value }));
}

/** Danh sách cột ngang dùng chung. Tách ra từ `groupBarCard` để ba thẻ đếm nhãn không phải chép lại
 *  cùng một khối markup ba lần. */
function barCard(title, rows, emptyNote, { sub = "", activeKey = null, stacked = false, foot = "" } = {}) {
  const peak = Math.max(1, ...rows.map((row) => row.value));
  return `<section class="chart-card">
    <div class="chart-head">
      <h2>${escapeHtml(title)}</h2>
      ${sub ? `<span class="chart-sub">${escapeHtml(sub)}</span>` : ""}
    </div>
    ${
      rows.length
        ? `<ul class="bar-list${stacked ? " is-stacked" : ""}">
            ${rows
              .map(
                (row) => `<li class="bar-row${activeKey && row.key === activeKey ? " is-on" : ""}" data-bar tabindex="0" aria-label="${escapeHtml(row.label)}: ${row.value} ca">
                  <span class="bar-name" title="${escapeHtml(row.label)}">${escapeHtml(row.label)}</span>
                  <span class="bar-track"><span class="bar-fill" style="width:${row.value ? Math.max(2, (row.value / peak) * 100) : 0}%"></span></span>
                  <b class="bar-value">${row.value}</b>
                </li>`,
              )
              .join("")}
          </ul>`
        : `<p class="chart-empty">${escapeHtml(emptyNote)}</p>`
    }
    ${rows.length && foot ? `<p class="chart-foot">${escapeHtml(foot)}</p>` : ""}
  </section>`;
}

// ── Ca theo trạng thái · điều dưỡng đã làm gì · khối lượng theo người ────────────────────────────

/** Khối lượng đang ĐỌNG Ở KHÂU NÀO của luồng.
 *
 *  Ô KPI phía trên chỉ chia đôi "đang chờ / đã chốt", mà hai nửa đó gộp chung những tình huống cần
 *  hành động khác hẳn nhau: một ca `needs_more_info` đang chờ BỆNH NHÂN trả lời, còn một ca
 *  `needs_nurse_review` đang chờ ĐIỀU DƯỠNG - không thẻ nào trên màn phân biệt được hai thứ đó
 *  trước khi có thẻ này. Trạng thái 0 ca bị bỏ khỏi danh sách (xem `STATUS_ORDER`). */
function statusMixCard(cases) {
  const rows = STATUS_ORDER
    .map((key) => ({ key, label: statusLabels[key] || key, value: cases.filter((item) => item.status === key).length }))
    .filter((row) => row.value);
  return barCard("Ca theo trạng thái", rows, "Chưa có ca nào trong phạm vi này", {
    sub: `${cases.length} ca trong phạm vi`,
    stacked: true,
  });
}

/** Điều dưỡng đã CHỌN gì ở màn duyệt, theo lần duyệt gần nhất của mỗi ca.
 *
 *  Ma trận AI/điều dưỡng ngay phía trên chỉ nói mức có bị đổi hay không - nó không thấy được hai
 *  hành động KHÔNG đổi mức nhưng tốn công nhất: `ask_more` (hồ sơ thiếu tới mức phải hỏi lại bệnh
 *  nhân) và `reject`. Một hệ thống mà `ask_more` chiếm phần lớn là hệ thống hỏi checklist chưa đủ,
 *  dù tỉ lệ "giữ nguyên mức AI" vẫn đẹp.
 *
 *  Một dòng một CA, không phải một lượt bấm: `/nurse/review-log` đã gộp mỗi ca về bản ghi cuối. */
function actionMixCard(cases) {
  const inScope = new Set(cases.map((item) => item.case_id));
  const decided = reviewLog.filter((row) => inScope.has(row.case_id) && NURSE_ACTION_TEXT[row.action]);
  const rows = decided.length
    ? Object.entries(NURSE_ACTION_TEXT).map(([key, label]) => ({
        key,
        label,
        value: decided.filter((row) => row.action === key).length,
      }))
    : [];
  const rejected = decided.filter((row) => row.action === "reject");
  const aiFault = rejected.filter((row) => row.reject_reason === "ai_incorrect").length;

  return barCard("Điều dưỡng đã làm gì", rows, "Chưa ca nào qua tay nhân viên y tế", {
    sub: decided.length ? `${decided.length} ca đã có quyết định` : "",
    stacked: true,
    foot: rejected.length
      ? `${aiFault}/${rejected.length} ca từ chối là do đề xuất của AI không chính xác; số còn lại vì lý do ngoài chuyên môn.`
      : "Chỉ tính bốn hành động của nhân viên y tế, không tính thao tác do hệ thống ghi.",
  });
}

/** Ai đã chốt bao nhiêu ca, kèm trung vị thời gian xử lý của cả kíp.
 *
 *  Đây là số liệu PHÂN CÔNG, không phải bảng xếp hạng năng suất: một người chốt nhiều ca có thể vì
 *  trực ca đông chứ không vì làm nhanh hơn, nên thẻ cố ý không xếp hạng theo tốc độ và không tách
 *  thời gian xử lý theo từng người - cỡ mẫu mỗi người quá nhỏ để con số đó nói được điều gì.
 *
 *  Ca thiếu `reviewed_by_name` vẫn được đếm dưới nhãn riêng thay vì bỏ đi: giấu chúng làm tổng của
 *  thẻ không khớp với ô "Đã chốt" mà không có chỗ nào giải thích vì sao. */
function nurseWorkloadCard(cases) {
  const tally = new Map();
  for (const item of cases) {
    if (!item.reviewed_at) continue;
    const name = item.reviewed_by_name || "Không rõ người duyệt";
    tally.set(name, (tally.get(name) || 0) + 1);
  }
  const rows = [...tally.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], "vi"))
    .slice(0, 6)
    .map(([label, value]) => ({ label, value }));
  const handled = cases.map(handleMinutes).filter((minutes) => minutes !== null);

  return barCard("Ca đã chốt, theo nhân viên y tế", rows, "Chưa ca nào được chốt trong phạm vi này", {
    sub: tally.size ? `${tally.size} người đã tham gia` : "",
    stacked: true,
    foot: handled.length
      ? `Trung vị thời gian xử lý một ca của cả kíp: ${formatMinutes(median(handled))}.`
      : "",
  });
}

// ── Giờ trong ngày ───────────────────────────────────────────────────────────────────────────────

const HOURS = { width: 340, height: 150, top: 10, bottom: 22 };

/** Ca vào theo giờ trong ngày - phục vụ bố trí ca trực.
 *
 *  Vẽ 24 cột dọc chứ không dùng `bar-list` ngang: 24 hàng ngang chiếm hết chiều cao thẻ, mà thứ
 *  người đọc cần thấy ở đây là HÌNH DẠNG một ngày, không phải giá trị từng giờ. */
function hourChartCard(cases) {
  const counts = Array.from({ length: 24 }, () => 0);
  for (const item of cases) {
    const hour = new Date(item.created_at).getHours();
    if (Number.isInteger(hour)) counts[hour] += 1;
  }
  const peak = Math.max(1, ...counts);
  const plotHeight = HOURS.height - HOURS.top - HOURS.bottom;
  const slot = HOURS.width / 24;
  const busiest = counts.indexOf(Math.max(...counts));

  const bars = counts
    .map((value, hour) => {
      const height = (value / peak) * plotHeight;
      // Màu lấy từ token `--bar` / `--bar-on` chứ KHÔNG dùng `SERIES_DONE`: cam là màu NHẬN DIỆN
      // của series "ca chốt" ở biểu đồ đường phía trên, mượn nó để tô cột cao nhất ở đây là gán cho
      // một màu hai nghĩa khác nhau trên cùng một màn hình. Nhấn mạnh trong một biểu đồ đơn series
      // là việc của đậm/nhạt CÙNG một hue. Biến CSS cũng khiến biểu đồ đúng màu ở giao diện tối,
      // điều mà mã hex nội tuyến không làm được.
      return `<rect class="hour-bar" x="${(hour * slot + slot * 0.11).toFixed(1)}" y="${(HOURS.top + plotHeight - height).toFixed(1)}"
        width="${(slot * 0.78).toFixed(1)}" height="${Math.max(value ? 1.5 : 0, height).toFixed(1)}" rx="1.5"
        fill="${hour === busiest && counts[busiest] ? "var(--bar-on)" : "var(--bar)"}" opacity="${value ? 1 : 0.15}" />`;
    })
    .join("");

  const labels = [0, 6, 12, 18, 23]
    .map((hour) => `<text x="${(hour * slot + slot / 2).toFixed(1)}" y="${HOURS.height - 6}" text-anchor="middle" class="axis-text">${hour}h</text>`)
    .join("");

  return `<section class="chart-card">
    <div class="chart-head">
      <h2>Ca vào theo giờ</h2>
      <span class="chart-sub">${counts[busiest] ? `Đông nhất: ${busiest}h` : "Chưa có dữ liệu"}</span>
    </div>
    <div class="chart-plot">
      <svg viewBox="0 0 ${HOURS.width} ${HOURS.height}" role="img" aria-label="Số ca vào hàng đợi theo từng giờ trong ngày">
        <line x1="0" y1="${HOURS.top + plotHeight}" x2="${HOURS.width}" y2="${HOURS.top + plotHeight}" stroke="#e3e8ef" stroke-width="1" />
        ${bars}${labels}
      </svg>
    </div>
  </section>`;
}

// ── Biểu đồ cột: ca theo nhóm triệu chứng ────────────────────────────────────────────────────────

/** Dạng "emphasis": nhóm đang chọn tô xanh, các nhóm còn lại xám. KHÔNG lọc bớt cột - so sánh giữa
 *  các nhóm chính là việc của biểu đồ này, lọc xuống một cột thì nó không còn gì để so. */
function groupBarCard() {
  const rows = GROUP_KEYS.map((key) => ({
    key,
    label: symptomGroupLabels[key] || key,
    value: state.queue.filter((item) => groupOf(item) === key).length,
  }));
  return barCard("Ca theo nhóm triệu chứng", rows, "Chưa có ca nào", {
    sub: view.group === "all" ? "Toàn bộ hàng đợi" : `Đang lọc: ${symptomGroupLabels[view.group] || view.group}`,
    activeKey: view.group,
  });
}

function bindBarHover(root) {
  root.querySelectorAll("[data-bar]").forEach((row) => {
    row.addEventListener("pointerenter", () => row.classList.add("is-hover"));
    row.addEventListener("pointerleave", () => row.classList.remove("is-hover"));
  });
}
