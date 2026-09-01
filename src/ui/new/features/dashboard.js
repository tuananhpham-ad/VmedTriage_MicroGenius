import { api } from "../api.js";
import { bindAccountMenu } from "./account.js?v=design-20260827d";
import { bindSideNav, displayLevel, nurseShell, paintOverview } from "./nurse.js?v=design-20260901b";
import { completedStatuses, state } from "../state.js";
import { escapeHtml, icon, priorityLabels, shortCaseId, showToast, symptomGroupLabels } from "../shared.js";

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

const view = { group: "all", days: 7 };

/** Bản ghi `/nurse/review-log`, một dòng một ca. Giữ ở module chứ không nhét vào `state`: chỉ màn
 *  này đọc nó, và `state.queue` được các màn khác dùng chung nên thêm vào đó là mở rộng vùng ảnh
 *  hưởng mà không được gì. */
let reviewLog = [];

/** Toạ độ x + số liệu của từng điểm trên biểu đồ đường, để lớp hover tra cứu. Giữ ở đây thay vì
 *  nhét JSON vào DOM: chỉ có một biểu đồ đường trên màn và nó được vẽ lại đồng bộ ngay trước khi
 *  hover được nối. */
let linePoints = [];

/** Bật đúng MỘT lần cho lần vẽ đầu tiên sau khi vào màn. `paintDashboard` còn chạy lại mỗi 15 giây
 *  do polling và mỗi lần đổi bộ lọc - để hoạt ảnh chạy ở những lần đó thì vòng tròn cứ 15 giây lại
 *  vẽ lại một lần, gây rối chứ không giúp gì. */
let drawDonut = false;

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
  drawDonut = true;
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

  root.querySelector("#dash-body").innerHTML = `
    ${sectionHead("Bảng trực", "Cần xử lý ngay. Số liệu sống, tự làm mới mỗi 15 giây.")}

    <div class="kpi-row">
      ${statTile("Tổng số ca", cases.length, `Trong phạm vi: ${escapeHtml(scopeName)}`)}
      ${statTile("Có dấu hiệu nguy hiểm", redFlags, cases.length ? `${Math.round((redFlags / cases.length) * 100)}% tổng số ca` : "Chưa có dữ liệu")}
      ${statTile("Đang chờ được xác nhận", cases.length - settled, pendingNote(pending, longestWait))}
      ${statTile("Ca quá hạn", overdue, overdueNote(pending, overdue), overdue ? "is-overdue" : "")}
      ${statTile("Đã chốt", settled, "Duyệt, từ chối hoặc đóng")}
    </div>

    <div class="chart-row">
      ${lineChartCard(dailySeries(cases))}
      ${donutCard(cases)}
    </div>

    <div class="chart-row">
      ${timeToOpenCard(cases)}
      ${backlogCard()}
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
  `;
  bindLineHover(root);
  bindBarHover(root);
  paintNewCaseTicker(root);
  drawDonut = false;
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

function statTile(label, value, note, tone = "") {
  return `<div class="kpi-tile ${tone}">
    <span class="kpi-label">${escapeHtml(label)}</span>
    <b class="kpi-value">${escapeHtml(String(value))}</b>
    <span class="kpi-note">${escapeHtml(note)}</span>
  </div>`;
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
  const rows = bucketize(opened);
  const peak = Math.max(1, ...rows.map((row) => row.value));

  return `<section class="chart-card">
    <div class="chart-head">
      <h2>Thời gian tới lượt mở</h2>
      <span class="chart-sub">${unopened ? `${unopened} ca chưa ai mở, không tính vào đây` : "Tính trên ca đã được mở"}</span>
    </div>
    <div class="stat-pair">
      <div><span class="kpi-label">Trung vị</span><b class="kpi-value">${escapeHtml(formatMinutes(median(opened)))}</b></div>
      <div><span class="kpi-label">P90</span><b class="kpi-value">${escapeHtml(formatMinutes(quantile(opened, 0.9)))}</b></div>
      <div><span class="kpi-label">Số ca đo được</span><b class="kpi-value">${opened.length}</b></div>
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
      <span class="chart-sub">Không theo khoảng thời gian</span>
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
    <p class="chart-foot">${pending.length ? "Bấm một hàng để mở hàng đợi." : "Hàng đợi đang trống."}</p>
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
        <path d="${path((day) => day.arrived)}" fill="none" stroke="${SERIES_IN}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
        <path d="${path((day) => day.settled)}" fill="none" stroke="${SERIES_DONE}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
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
      <svg viewBox="0 0 140 140" class="donut${drawDonut ? " is-drawing" : ""}" role="img" aria-label="Tỉ lệ ca theo ba mức ưu tiên">
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
function barCard(title, rows, emptyNote, { sub = "", activeKey = null, stacked = false } = {}) {
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
  </section>`;
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
      return `<rect x="${(hour * slot + slot * 0.11).toFixed(1)}" y="${(HOURS.top + plotHeight - height).toFixed(1)}"
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
