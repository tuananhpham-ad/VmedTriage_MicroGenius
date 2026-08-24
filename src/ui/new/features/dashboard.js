import { api } from "../api.js";
import { bindAccountMenu } from "./account.js?v=design-20260819b";
import { bindSideNav, nurseShell, paintOverview } from "./nurse.js?v=design-20260824g";
import { completedStatuses, state } from "../state.js";
import { escapeHtml, icon, symptomGroupLabels } from "../shared.js";

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

const GROUP_KEYS = ["fever", "abdominal_pain", "chest_pain", "shortness_of_breath", "headache"];
const RANGES = { 7: "7 ngày", 30: "30 ngày" };

const view = { group: "all", days: 7 };

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

    <div class="queue-toolbar">
      <div class="filter-chips" role="group" aria-label="Lọc theo nhóm triệu chứng">
        <button class="filter-chip is-active" type="button" data-group="all"><span>Tất cả nhóm</span></button>
        ${GROUP_KEYS.map((key) => `<button class="filter-chip" type="button" data-group="${key}"><span>${escapeHtml(symptomGroupLabels[key] || key)}</span></button>`).join("")}
      </div>
      <div class="filter-chips" role="group" aria-label="Khoảng thời gian">
        ${Object.entries(RANGES).map(([days, label], index) => `<button class="filter-chip${index === 0 ? " is-active" : ""}" type="button" data-days="${days}"><span>${label}</span></button>`).join("")}
      </div>
    </div>

    <div id="dash-body"></div>
  `);

  bindAccountMenu(root, { logout, onProfileSaved: () => renderNurseDashboard(root, { navigate, logout }) });
  bindSideNav(root, { navigate }, "dashboard");
  root.querySelectorAll("[data-refresh]").forEach((button) => button.addEventListener("click", () => loadDashboard(root)));
  bindChips(root, "[data-group]", (button) => { view.group = button.dataset.group; });
  bindChips(root, "[data-days]", (button) => { view.days = Number(button.dataset.days); });

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

async function loadDashboard(root) {
  try {
    state.queue = await api("/api/v1/nurse/queue");
    root.querySelector("#dash-updated").textContent = `Cập nhật lúc ${new Date().toLocaleTimeString("vi-VN")}`;
  } catch (problem) {
    root.querySelector("#dash-updated").textContent = problem.message || "Không tải được dữ liệu";
  }
  paintDashboard(root);
}

// ── Tổng hợp số liệu ─────────────────────────────────────────────────────────────────────────────

function groupOf(item) {
  return item.structured_data?.symptom_group || "";
}

function priorityOf(item) {
  return item.triage_proposal?.priority || "Manual review";
}

/** Ca thuộc phạm vi bộ lọc nhóm hiện tại. Bộ lọc áp cho KPI, biểu đồ đường và biểu đồ tròn; biểu đồ
 *  cột nhóm triệu chứng CỐ Ý không lọc - lọc nó xuống còn một cột thì cả biểu đồ mất ý nghĩa, nên nó
 *  làm nổi cột đang chọn thay vì bỏ các cột còn lại (dạng "emphasis"). */
function scopedCases() {
  return view.group === "all" ? state.queue : state.queue.filter((item) => groupOf(item) === view.group);
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
  for (let offset = view.days - 1; offset >= 0; offset -= 1) {
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

  root.querySelector("#dash-body").innerHTML = `
    <div class="kpi-row">
      ${statTile("Tổng số ca", cases.length, `Trong phạm vi: ${escapeHtml(scopeName)}`)}
      ${statTile("Có dấu hiệu nguy hiểm", redFlags, cases.length ? `${Math.round((redFlags / cases.length) * 100)}% tổng số ca` : "Chưa có dữ liệu")}
      ${statTile("Đang chờ được xác nhận", cases.length - settled, "Chưa có quyết định của nhân viên y tế")}
      ${statTile("Đã chốt", settled, "Duyệt, từ chối hoặc đóng")}
    </div>

    <div class="chart-row">
      ${lineChartCard(dailySeries(cases))}
      ${donutCard(cases)}
    </div>

    ${groupBarCard()}
  `;
  bindLineHover(root);
  bindBarHover(root);
  drawDonut = false;
}

function statTile(label, value, note) {
  return `<div class="kpi-tile">
    <span class="kpi-label">${escapeHtml(label)}</span>
    <b class="kpi-value">${escapeHtml(String(value))}</b>
    <span class="kpi-note">${escapeHtml(note)}</span>
  </div>`;
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
        ${grid}${xLabels}
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

// ── Biểu đồ cột: ca theo nhóm triệu chứng ────────────────────────────────────────────────────────

/** Dạng "emphasis": nhóm đang chọn tô xanh, các nhóm còn lại xám. KHÔNG lọc bớt cột - so sánh giữa
 *  các nhóm chính là việc của biểu đồ này, lọc xuống một cột thì nó không còn gì để so. */
function groupBarCard() {
  const rows = GROUP_KEYS.map((key) => ({
    key,
    label: symptomGroupLabels[key] || key,
    value: state.queue.filter((item) => groupOf(item) === key).length,
  }));
  const peak = Math.max(1, ...rows.map((row) => row.value));

  return `<section class="chart-card">
    <div class="chart-head">
      <h2>Ca theo nhóm triệu chứng</h2>
      <span class="chart-sub">${view.group === "all" ? "Bấm một nhóm ở trên để lọc các biểu đồ còn lại" : `Đang lọc: ${escapeHtml(symptomGroupLabels[view.group] || view.group)}`}</span>
    </div>
    <ul class="bar-list">
      ${rows
        .map(
          (row) => `<li class="bar-row${row.key === view.group ? " is-on" : ""}" data-bar tabindex="0" aria-label="${escapeHtml(row.label)}: ${row.value} ca">
            <span class="bar-name">${escapeHtml(row.label)}</span>
            <span class="bar-track"><span class="bar-fill" style="width:${Math.max(2, (row.value / peak) * 100)}%"></span></span>
            <b class="bar-value">${row.value}</b>
          </li>`,
        )
        .join("")}
    </ul>
  </section>`;
}

function bindBarHover(root) {
  root.querySelectorAll("[data-bar]").forEach((row) => {
    row.addEventListener("pointerenter", () => row.classList.add("is-hover"));
    row.addEventListener("pointerleave", () => row.classList.remove("is-hover"));
  });
}
