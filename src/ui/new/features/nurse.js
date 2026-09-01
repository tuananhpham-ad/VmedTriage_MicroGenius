import { api } from "../api.js";
import { accountMenu, bindAccountMenu, openAccountInfo } from "./account.js?v=design-20260827d";
import { completedStatuses, state } from "../state.js";
import {
  appHeader,
  readAppTheme,
  saveAppTheme,
  escapeHtml,
  formatDate,
  formatChatTime,
  icon,
  identityBlock,
  paragraphs,
  priorityClass,
  priorityDot,
  priorityLabels,
  shortCaseId,
  showToast,
  statusLabels,
  symptomGroupLabels,
  waitingLabel,
} from "../shared.js";

let polling = null;
let selectedMessageCaseId = null;

export function stopQueuePolling() {
  if (polling) window.clearInterval(polling);
  polling = null;
}

// ── Polling khi đang chat trực tiếp với bệnh nhân (status "needs_more_info") ────────────────────
// Mirror đúng cơ chế `casePolling` phía patient.js (ADR-005: polling thay WebSocket cho MVP) - điều
// dưỡng cần thấy tin nhắn mới của bệnh nhân mà không phải tự bấm làm mới.
let chatPolling = null;

export function stopNurseChatPolling() {
  if (chatPolling) window.clearInterval(chatPolling);
  chatPolling = null;
}

function chatSignature(item) {
  return [item?.status, item?.conversation?.length].join("|");
}

function startNurseChatPolling(root, context) {
  stopNurseChatPolling();
  const item = state.selectedNurseCase;
  if (!item || item.status !== "needs_more_info") return;
  chatPolling = window.setInterval(async () => {
    let fresh;
    try { fresh = await api(`/api/v1/cases/${item.case_id}`); } catch { return; }
    if (chatSignature(fresh) === chatSignature(state.selectedNurseCase)) return;
    state.selectedNurseCase = fresh;
    renderNurseCase(root, context);
  }, 10000);
}

export function nurseHeader(active, { title = "", right = "" } = {}) {
  return appHeader({
    nav: active
      ? [
          { label: "Hàng đợi", active: active === "queue", action: "queue" },
          { label: "Ca đã duyệt", active: active === "done", action: "done" },
    ]
      : [],
    title,
    right,
  });
}

// Màn danh sách vừa mở, để nút quay lại của W-07 trả điều dưỡng về ĐÚNG chỗ họ vừa rời: mở một ca
// từ "Ca đã duyệt" rồi bị đẩy về hàng đợi là mất vị trí đang đọc.
let lastListView = "nurse-queue";

// Hai màn W-06 dùng CHUNG một hàm render, khác nhau đúng ở `scope`. Tách thành hai hàm copy-paste
// thì mỗi lần sửa cột/bộ lọc phải sửa hai chỗ và chúng sẽ lệch nhau - đây là lý do "Ca đã duyệt" có
// UI giống hệt hàng đợi mà không tốn thêm markup nào.
const listScopes = {
  queue: {
    nav: "queue",
    title: "Hàng đợi",
    intro: "Ca có red flag luôn được hiển thị trước để nhân viên y tế nắm tình huống.",
    // Ca đã duyệt/từ chối/đóng đã rời hàng đợi - chúng nằm trọn ở màn "Ca đã duyệt". `escalated`
    // KHÔNG phải trạng thái đã xong (xem `completedStatuses` trong state.js) nên vẫn ở lại đây.
    includes: (item) => !completedStatuses.has(item.status),
    action: "Duyệt ca →",
    emptyTitle: "Không có ca nào đang chờ duyệt 🎉",
    emptyCopy: "Danh sách sẽ tự cập nhật khi có ca mới.",
  },
  done: {
    nav: "done",
    title: "Ca đã duyệt",
    intro: "Ca đã xử lý xong, sắp theo mức ưu tiên rồi tới thời gian chờ như hàng đợi.",
    includes: (item) => completedStatuses.has(item.status),
    // KHÔNG dùng lại chữ "Duyệt ca →": ca ở đây đã chốt, màn W-07 mở ra ở chế độ chỉ đọc.
    action: "Xem chi tiết →",
    emptyTitle: "Chưa có ca nào được duyệt",
    emptyCopy: "Ca sẽ chuyển sang đây ngay khi bạn duyệt hoặc từ chối.",
  },
};

const SIDEBAR_KEY = "vmed_nurse_sidebar";
let queueFilter = "all";
let queueSubnavOpen = true;
// "Ca đã duyệt" có menu con riêng (Tất cả/Cấp cứu/Khám sớm/Tự theo dõi) y hệt Hàng đợi, nhưng là một
// bộ lọc và một trạng thái đóng/mở ĐỘC LẬP - hai màn phải nhớ lựa chọn của nhau khi qua lại.
let doneFilter = "all";
let doneSubnavOpen = true;

/** Cột điều hướng đang thu gọn hay không. Nhớ trong `localStorage` vì mỗi lần đổi màn là một lần
 *  render lại từ đầu - không nhớ thì thanh này bung ra lại sau mỗi cú bấm. */
function sidebarCollapsed() {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "1";
  } catch {
    return false;
  }
}

/** Cột điều hướng bên trái, DÙNG CHUNG cho cả ba màn của điều dưỡng. Sau khi bỏ tab trên header,
 *  đây là đường duy nhất đi giữa các màn - nên nó phải giống hệt nhau ở mọi màn, và cách duy nhất
 *  bảo đảm điều đó là chỉ có một chỗ dựng ra nó.
 *
 *  Chỉ hiển thị icon, nhãn và số ca. Riêng các mức ưu tiên là menu con của Hàng đợi VÀ Ca đã duyệt để
 *  điều dưỡng mở đúng danh sách cần xem ngay từ sidebar (hai bộ lọc độc lập); các chi tiết ca vẫn nằm
 *  ở vùng nội dung. */
export function nurseSideNav(activeKey) {
  const theme = readAppTheme();
  const collapsed = sidebarCollapsed();
  const toggleLabel = collapsed ? "Mở rộng" : "Thu gọn";
  const item = (key, name, glyph, badge) => `<button class="nav-item${key === activeKey ? " is-on" : ""}" type="button" data-nav="${key}" title="${name}">
    <span class="nav-glyph">${icon(glyph, 17)}</span>
    <span class="nav-text">${name}</span>
    ${badge ? `<b class="nav-count" id="${badge}">0</b>` : ""}
  </button>`;
  const queueFilterItem = (filter, label, priority = "") => `<button class="nav-subnav-item${activeKey === "queue" && queueFilter === filter ? " is-active" : ""}${priority ? ` is-${priority}` : ""}" type="button" data-queue-filter="${filter}">
    ${priority ? `<span class="priority-dot is-${priority}"></span>` : ""}
    <span>${label}</span>
    <b id="overview-filter-${filter}">0</b>
  </button>`;
  const doneFilterItem = (filter, label, priority = "") => `<button class="nav-subnav-item${activeKey === "done" && doneFilter === filter ? " is-active" : ""}${priority ? ` is-${priority}` : ""}" type="button" data-done-filter="${filter}">
    ${priority ? `<span class="priority-dot is-${priority}"></span>` : ""}
    <span>${label}</span>
    <b id="overview-done-filter-${filter}">0</b>
  </button>`;
  return `<aside class="queue-side${collapsed ? " is-collapsed" : ""}" data-sidebar>
    <div class="nurse-side-top">
      <a class="brand nurse-side-brand" href="/" aria-label="VMedTriage">${icon("logo", 27)}<span class="brand-word">VMed<span>Triage</span></span></a>
      <button class="nav-toggle" type="button" data-sidebar-toggle aria-label="${toggleLabel}" aria-expanded="${!collapsed}" data-tooltip="${toggleLabel}">${icon(collapsed ? "sidebarExpand" : "sidebarCollapse", 17)}</button>
    </div>
    <nav class="nav-list" aria-label="Điều hướng nhân viên y tế">
      <p class="nav-group">Theo dõi</p>
      ${item("dashboard", "Bảng điều khiển", "pulse", "")}
      <div class="nav-parent">
        ${item("queue", "Hàng đợi", "clipboard", "overview-queue")}
        <div class="nav-subnav" ${activeKey === "queue" && queueSubnavOpen ? "" : "hidden"}>
          ${queueFilterItem("all", "Tất cả")}
          ${queueFilterItem("Emergency", "Cấp cứu", "emergency")}
          ${queueFilterItem("Urgent", "Khám sớm", "urgent")}
          ${queueFilterItem("Self-care", "Tự theo dõi", "self-care")}
        </div>
      </div>
      <div class="nav-parent">
        ${item("done", "Ca đã duyệt", "shieldCheck", "overview-done")}
        <div class="nav-subnav" ${activeKey === "done" && doneSubnavOpen ? "" : "hidden"}>
          ${doneFilterItem("all", "Tất cả")}
          ${doneFilterItem("Emergency", "Cấp cứu", "emergency")}
          ${doneFilterItem("Urgent", "Khám sớm", "urgent")}
          ${doneFilterItem("Self-care", "Tự theo dõi", "self-care")}
        </div>
      </div>

      <p class="nav-group">Ca làm việc</p>
      ${item("shift", "Ca trực", "clock", "")}
      <button class="nav-item" type="button" data-refresh title="Làm mới">
        <span class="nav-glyph">${icon("retry", 17)}</span>
        <span class="nav-text">Làm mới</span>
      </button>

      <p class="nav-group">Tiện ích</p>
      ${item("messages", "Tin nhắn", "chat", "overview-messages")}
      <button class="nav-item" type="button" data-nurse-info="settings" title="Cài đặt">
        <span class="nav-glyph">${icon("settings", 17)}</span>
        <span class="nav-text">Cài đặt</span>
      </button>
      <button class="nav-item" type="button" data-nurse-info="help" title="Trợ giúp & liên hệ">
        <span class="nav-glyph">${icon("ask", 17)}</span>
        <span class="nav-text">Trợ giúp &amp; liên hệ</span>
      </button>
      <button class="nurse-theme-toggle" type="button" data-nurse-theme-toggle data-theme="${theme}" aria-pressed="${theme === "dark"}" aria-label="Chuyển sang chủ đề ${theme === "dark" ? "sáng" : "tối"}">
        <span class="nurse-theme-icon">${icon("sun", 17)}${icon("moon", 17)}</span>
        <span data-nurse-theme-label>Chủ đề ${theme === "dark" ? "sáng" : "tối"}</span>
      </button>
    </nav>
    <div class="nurse-side-account">
      ${accountMenu()}
      ${identityBlock("Nhân viên y tế")}
    </div>
  </aside>`;
}

/** Khung chung của ba màn điều dưỡng: header, rail trái, vùng nội dung cuộn được.
 *
 *  `is-fixed` khoá chiều cao vào đúng một khung nhìn và để `.nurse-main` cuộn - nhờ vậy rail luôn
 *  cao hết màn hình mà không cần biết header cao bao nhiêu, không có con số ma nào trong CSS. */
export function nurseShell(activeKey, content) {
  return `<section class="app-shell is-fixed">
    <div class="nurse-body">
      ${nurseSideNav(activeKey)}
      <main class="nurse-main">${content}</main>
    </div>
  </section>`;
}

/** Điều hướng của cột trái. Tách ra vì cả ba màn đều phải nối `[data-nav]` y hệt nhau. */
export function bindSideNav(root, { navigate, logout }, activeKey) {
  root.querySelector("[data-sidebar-toggle]")?.addEventListener("click", () => {
    const bar = root.querySelector("[data-sidebar]");
    const collapsed = bar.classList.toggle("is-collapsed");
    const toggle = root.querySelector("[data-sidebar-toggle]");
    const label = collapsed ? "Mở rộng" : "Thu gọn";
    toggle.setAttribute("aria-label", label);
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.dataset.tooltip = label;
    toggle.innerHTML = icon(collapsed ? "sidebarExpand" : "sidebarCollapse", 17);
    try {
      localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
    } catch {
      // Trình duyệt chặn storage thì thanh vẫn thu gọn được, chỉ là không nhớ qua lần render sau.
    }
  });
  root.querySelector("[data-nurse-theme-toggle]")?.addEventListener("click", (event) => {
    const next = event.currentTarget.dataset.theme === "dark" ? "light" : "dark";
    saveAppTheme(next);
    event.currentTarget.dataset.theme = next;
    event.currentTarget.setAttribute("aria-pressed", String(next === "dark"));
    event.currentTarget.setAttribute("aria-label", `Chuyển sang chủ đề ${next === "dark" ? "sáng" : "tối"}`);
    event.currentTarget.querySelector("[data-nurse-theme-label]").textContent = `Chủ đề ${next === "dark" ? "sáng" : "tối"}`;
  });
  root.querySelectorAll("[data-queue-filter]").forEach((button) =>
    button.addEventListener("click", () => {
      queueFilter = button.dataset.queueFilter;
      if (activeKey !== "queue") {
        navigate("nurse-queue");
        return;
      }
      root.dataset.filter = queueFilter;
      root.querySelectorAll("[data-queue-filter]").forEach((item) => item.classList.toggle("is-active", item === button));
      paintQueue(root, { navigate, logout });
    }),
  );
  root.querySelectorAll("[data-done-filter]").forEach((button) =>
    button.addEventListener("click", () => {
      doneFilter = button.dataset.doneFilter;
      if (activeKey !== "done") {
        navigate("nurse-done");
        return;
      }
      root.dataset.filter = doneFilter;
      root.querySelectorAll("[data-done-filter]").forEach((item) => item.classList.toggle("is-active", item === button));
      paintQueue(root, { navigate, logout });
    }),
  );
  root.querySelectorAll("[data-nav]").forEach((button) =>
    button.addEventListener("click", () => {
      const nav = button.dataset.nav;
      // Bấm vào chính màn đang mở thì không render lại: render dựng lại toàn bộ innerHTML nên bộ lọc
      // và ô tìm kiếm đang gõ dở sẽ bị xoá sạch. Riêng "queue"/"done" có menu con thì bấm lại chỉ
      // đóng/mở menu đó, KHÔNG render lại (còn navTargets khác không có menu con nên bỏ qua).
      if (nav === activeKey) {
        if (nav === "queue") {
          queueSubnavOpen = !queueSubnavOpen;
          button.closest(".nav-parent").querySelector(".nav-subnav").hidden = !queueSubnavOpen;
        } else if (nav === "done") {
          doneSubnavOpen = !doneSubnavOpen;
          button.closest(".nav-parent").querySelector(".nav-subnav").hidden = !doneSubnavOpen;
        }
        return;
      }
      // Lần sau quay lại Hàng đợi/Ca đã duyệt, menu con luôn mở để thấy ngay danh sách tương ứng.
      if (nav !== "queue") queueSubnavOpen = true;
      if (nav !== "done") doneSubnavOpen = true;
      navigate(navTargets[nav] || "nurse-queue");
    }),
  );
  root.querySelectorAll("[data-nurse-info]").forEach((button) =>
    button.addEventListener("click", () => openAccountInfo(button.dataset.nurseInfo)),
  );
}

const navTargets = {
  dashboard: "nurse-dashboard",
  queue: "nurse-queue",
  done: "nurse-done",
  shift: "nurse-shift",
  messages: "nurse-messages",
};

/** Màn "Ca trực" — MỚI CHỈ CÓ KHUNG. Nội dung còn chờ chốt, nên ở đây cố tình chưa có số liệu nào:
 *  bịa ra vài ô "đang trực / đã duyệt hôm nay" rồi sau phải gỡ đi thì tệ hơn một trạng thái rỗng
 *  nói thẳng rằng phần này chưa làm. */
export function renderNurseShift(root, { navigate, logout }) {
  root.innerHTML = nurseShell("shift", `
    <div class="queue-head">
      <div>
        <h1>Ca trực</h1>
        <p>Thông tin phiên trực của nhân viên y tế.</p>
      </div>
    </div>
    <div class="queue-empty">
      <span class="state-icon is-neutral">${icon("clock", 32)}</span>
      <h2>Chưa có nội dung</h2>
      <p>Phần này đang chờ chốt sẽ hiển thị những gì.</p>
    </div>
  `);

  bindAccountMenu(root, { logout, onProfileSaved: () => renderNurseShift(root, { navigate, logout }) });
  bindSideNav(root, { navigate, logout }, "shift");
  root.querySelectorAll("[data-refresh]").forEach((button) => button.addEventListener("click", () => refreshSideCounts(root)));
  refreshSideCounts(root);
}

/** Nạp lại danh sách case CHỈ để cập nhật hai con số trên thanh điều hướng. Không dùng `refreshQueue`
 *  ở đây: hàm đó còn vẽ bảng và sẽ ngã ngay vì màn này không có `#queue-list`. */
async function refreshSideCounts(root) {
  try {
    state.queue = await api("/api/v1/nurse/queue");
  } catch {
    // Giữ nguyên số cũ trên thanh điều hướng - xoá đi khi mất mạng không giúp được gì.
  }
  paintOverview(root);
}

/** Hộp thư chỉ gom những ca mà điều dưỡng đã chủ động mở luồng hỏi thêm. Một ca có thể được chọn
 *  rồi nhắn tiếp độc lập với các ca khác; nội dung hướng xử trí vẫn chỉ được gửi qua bước duyệt. */
export function renderNurseMessages(root, { navigate, logout }) {
  root.innerHTML = nurseShell("messages", `
    <div class="queue-head">
      <div>
        <h1>Tin nhắn</h1>
        <p>Trao đổi trực tiếp với các bệnh nhân đang cần bổ sung thông tin.</p>
      </div>
      <span class="polling-chip">${icon("retry", 15)}<span id="messages-updated">Đang tải hội thoại…</span></span>
    </div>
    <div class="message-inbox">
      <aside class="message-inbox-list" aria-label="Danh sách hội thoại">
        <header class="message-inbox-list-head"><span><strong>Hội thoại</strong><small>Đang chờ phản hồi</small></span><b id="message-case-count">0</b></header>
        <div class="message-inbox-search">
          <label class="sr-only" for="message-search">Tìm hội thoại</label>
          <input id="message-search" placeholder="Mã ca hoặc triệu chứng" autocomplete="off" />
        </div>
        <div id="message-case-list" class="message-case-list"></div>
      </aside>
      <section id="message-thread-panel" class="message-thread-panel" aria-live="polite"></section>
      <aside id="message-case-context" class="message-case-context" aria-label="Ngữ cảnh ca"></aside>
    </div>
    <aside id="nurse-message-ticker" class="nurse-new-case-ticker" aria-live="polite"></aside>
  `);

  bindAccountMenu(root, { logout, onProfileSaved: () => renderNurseMessages(root, { navigate, logout }) });
  bindSideNav(root, { navigate, logout }, "messages");
  root.querySelectorAll("[data-refresh]").forEach((button) => button.addEventListener("click", () => refreshNurseMessages(root, { navigate, logout })));
  root.querySelector("#message-search").addEventListener("input", () => paintNurseMessages(root, { navigate, logout }));
  root.querySelector("#nurse-message-ticker")?.addEventListener("click", (event) => {
    const item = event.target.closest("[data-message-ticker-case]");
    if (item) loadCase(item.dataset.messageTickerCase, { navigate, logout });
  });
  refreshNurseMessages(root, { navigate, logout });
  polling = window.setInterval(() => refreshNurseMessages(root, { navigate, logout, silent: true }), 15000);
}

async function refreshNurseMessages(root, context) {
  try {
    state.queue = await api("/api/v1/nurse/queue");
    root.querySelector("#messages-updated").textContent = `Cập nhật lúc ${formatDate(new Date())}`;
    paintOverview(root);
    // Không giật lại khung chat khi điều dưỡng đang gõ; lần polling tiếp theo sẽ cập nhật đầy đủ.
    if (!context.silent || !root.querySelector("#nurse-message-input:focus")) paintNurseMessages(root, context);
    paintMessageTicker(root);
  } catch (problem) {
    root.querySelector("#messages-updated").textContent = problem.message || "Không tải được hội thoại mới";
    if (!state.queue.length) paintNurseMessages(root, context);
    paintMessageTicker(root);
  }
}

/** Dải chạy ở màn Tin nhắn: ca khẩn/chưa chốt vẫn hiện cả khi điều dưỡng đang mở một hội thoại khác.
 * Nó chỉ là lối tắt tới hồ sơ; quyết định và nội dung gửi người bệnh vẫn phải qua màn duyệt. */
function paintMessageTicker(root) {
  const ticker = root.querySelector("#nurse-message-ticker");
  if (!ticker) return;
  const cases = state.queue
    .filter((item) => !completedStatuses.has(item.status))
    .sort((left, right) => {
      const urgent = (item) => item.status === "escalated" || item.red_flags?.length || displayLevel(item) === "Emergency";
      return Number(urgent(right)) - Number(urgent(left)) || new Date(right.created_at) - new Date(left.created_at);
    })
    .slice(0, 6);

  if (!cases.length) {
    const waiting = `${icon("pulse", 15)} VMedTriage đang theo dõi ca mới trong hàng đợi. Khi có bệnh nhân cần xử lý, thông báo sẽ xuất hiện tại đây để nhân viên y tế mở hồ sơ và xem xét.`;
    ticker.classList.add("is-empty");
    ticker.innerHTML = `<div class="nurse-new-case-ticker-viewport"><div class="nurse-new-case-ticker-track">
      <div class="nurse-new-case-ticker-group"><span class="nurse-new-case-ticker-empty">${waiting}</span><i aria-hidden="true">•</i><span class="nurse-new-case-ticker-empty">${waiting}</span></div>
      <div class="nurse-new-case-ticker-group" aria-hidden="true"><span class="nurse-new-case-ticker-empty">${waiting}</span><i>•</i><span class="nurse-new-case-ticker-empty">${waiting}</span></div>
    </div></div>`;
    return;
  }

  const message = (item, interactive) => {
    const level = displayLevel(item);
    const urgent = item.status === "escalated" || item.red_flags?.length || level === "Emergency";
    const name = patientName(item);
    const text = `${urgent ? "Ca cần ưu tiên" : "Ca mới"}: ${name}, ${complaint(item)}. ${priorityLabels[level] || "Cần điều dưỡng xem xét"}.`;
    const content = `<span class="nurse-ticker-status${urgent ? " is-urgent" : ""}">${urgent ? "Ưu tiên" : "Ca mới"}</span><b>${escapeHtml(name)}</b><span>${escapeHtml(complaint(item))}</span><small>${escapeHtml(priorityLabels[level] || "Cần xem xét")}</small>`;
    return interactive
      ? `<button class="nurse-ticker-item" type="button" data-message-ticker-case="${escapeHtml(item.case_id)}" aria-label="${escapeHtml(text)}">${content}</button>`
      : `<span class="nurse-ticker-item" aria-hidden="true">${content}</span>`;
  };
  const visible = cases.map((item) => message(item, true));
  const filler = Array.from({ length: Math.max(0, 8 - cases.length) }, (_, index) => message(cases[index % cases.length], false));
  ticker.classList.remove("is-empty");
  ticker.innerHTML = `<div class="nurse-new-case-ticker-viewport"><div class="nurse-new-case-ticker-track">
    <div class="nurse-new-case-ticker-group">${visible.concat(filler).join("")}</div>
    <div class="nurse-new-case-ticker-group" aria-hidden="true">${cases.map((item) => message(item, false)).concat(filler).join("")}</div>
  </div></div>`;
}

function messageCases() {
  return state.queue
    .filter((item) => item.status === "needs_more_info")
    .sort((left, right) => new Date(right.updated_at) - new Date(left.updated_at));
}

function directMessages(item) {
  return (item?.conversation || []).filter((message) => message.role === "patient" || message.role === "nurse");
}

function lastDirectMessage(item) {
  const messages = directMessages(item);
  return messages.at(-1) || null;
}

function nurseUserInitials(name = "") {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "BN";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function nurseAvatar(name, role = "patient", size = 40) {
  const initials = nurseUserInitials(name);
  const isNurse = role === "nurse";
  return `<div class="nurse-msg-avatar ${isNurse ? "is-nurse" : "is-patient"}" style="width:${size}px;height:${size}px;min-width:${size}px;min-height:${size}px;font-size:${Math.round(size * 0.38)}px;" aria-hidden="true"><span>${escapeHtml(initials)}</span></div>`;
}

function patientName(item) {
  return item.patient_display_name || `Bệnh nhân · ${shortCaseId(item.case_id)}`;
}

function paintNurseMessages(root, { navigate, logout }) {
  const search = root.querySelector("#message-search")?.value.trim().toLocaleLowerCase("vi-VN") || "";
  const allItems = messageCases();
  const items = allItems.filter((item) => !search || [item.case_id, complaint(item), lastDirectMessage(item)?.content || ""].join(" ").toLocaleLowerCase("vi-VN").includes(search));
  if (!items.some((item) => item.case_id === selectedMessageCaseId)) selectedMessageCaseId = items[0]?.case_id || null;
  const selected = allItems.find((item) => item.case_id === selectedMessageCaseId) || null;
  const list = root.querySelector("#message-case-list");
  const panel = root.querySelector("#message-thread-panel");
  const contextPanel = root.querySelector("#message-case-context");
  root.querySelector("#message-case-count").textContent = items.length;

  list.innerHTML = items.length
    ? items.map((item) => messageCaseRow(item, item.case_id === selectedMessageCaseId)).join("")
    : `<div class="message-inbox-empty"><span class="state-icon is-neutral">${icon("chat", 28)}</span><strong>Chưa có cuộc trò chuyện</strong><p>Những ca được chọn “Hỏi thêm” sẽ xuất hiện tại đây.</p></div>`;
  panel.innerHTML = selected ? messageThread(selected) : `<div class="message-thread-empty"><span class="state-icon is-neutral">${icon("chat", 36)}</span><h2>Chọn một cuộc trò chuyện</h2><p>Danh sách chỉ hiển thị các ca đang chờ bệnh nhân phản hồi.</p></div>`;
  contextPanel.innerHTML = selected ? messageCaseContext(selected) : `<div class="message-context-empty">${icon("clipboard", 28)}<span>Thông tin ca sẽ hiện ở đây.</span></div>`;

  list.querySelectorAll("[data-message-case]").forEach((button) => button.addEventListener("click", () => {
    selectedMessageCaseId = button.dataset.messageCase;
    paintNurseMessages(root, { navigate, logout });
  }));

  const nurseInput = panel.querySelector("#nurse-message-input");
  const nurseForm = panel.querySelector("[data-nurse-message-form]");
  const micBtn = panel.querySelector("#nurse-mic-btn");
  const fileInput = panel.querySelector("#nurse-file-attachment");

  nurseInput?.addEventListener("input", () => {
    nurseInput.style.height = "36px";
    nurseInput.style.height = `${Math.max(36, Math.min(nurseInput.scrollHeight, 120))}px`;
  });
  nurseInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      nurseForm?.requestSubmit();
    }
  });

  // Tích hợp Speech-to-Text bằng Web Speech API
  if (micBtn && nurseInput) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      let recognition = null;
      let isRecording = false;

      micBtn.addEventListener("click", () => {
        if (isRecording && recognition) {
          recognition.stop();
          return;
        }
        try {
          recognition = new SpeechRecognition();
          recognition.lang = "vi-VN";
          recognition.continuous = false;
          recognition.interimResults = true;

          recognition.onstart = () => {
            isRecording = true;
            micBtn.classList.add("is-recording");
            micBtn.setAttribute("title", "Đang nghe... Nhấp để dừng");
            showToast("Đang lắng nghe giọng nói tiếng Việt…");
          };

          recognition.onresult = (event) => {
            let transcript = "";
            for (let i = event.resultIndex; i < event.results.length; ++i) {
              transcript += event.results[i][0].transcript;
            }
            if (transcript) {
              const current = nurseInput.value;
              const separator = current && !current.endsWith(" ") ? " " : "";
              nurseInput.value = (current + separator + transcript).trim();
              nurseInput.dispatchEvent(new Event("input"));
            }
          };

          recognition.onend = () => {
            isRecording = false;
            micBtn.classList.remove("is-recording");
            micBtn.setAttribute("title", "Nhập bằng giọng nói (Speech-to-Text)");
          };

          recognition.onerror = (event) => {
            isRecording = false;
            micBtn.classList.remove("is-recording");
            if (event.error !== "no-speech") {
              showToast(`Lỗi micro: ${event.error}`, true);
            }
          };

          recognition.start();
        } catch (err) {
          isRecording = false;
          micBtn.classList.remove("is-recording");
          showToast(`Không thể bật micro: ${err.message || err}`, true);
        }
      });
    } else {
      micBtn.addEventListener("click", () => {
        showToast("Trình duyệt hiện tại không hỗ trợ Web Speech API. Hãy dùng Chrome hoặc Edge.", true);
      });
    }
  }

  // Xử lý tệp tin đính kèm
  fileInput?.addEventListener("change", () => {
    if (fileInput.files?.length) {
      const names = Array.from(fileInput.files).map((f) => f.name).join(", ");
      showToast(`Đã chọn tệp đính kèm: ${names}`);
      if (nurseInput) {
        nurseInput.value = (nurseInput.value ? `${nurseInput.value}\n` : "") + `[Tệp đính kèm: ${names}]`;
        nurseInput.dispatchEvent(new Event("input"));
        nurseInput.focus();
      }
    }
  });

  // Đọc tin nhắn bằng giọng nói (Text-to-Speech)
  panel.querySelectorAll("[data-read-aloud]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const text = btn.dataset.readAloud;
      if (!text || !window.speechSynthesis) {
        showToast("Trình duyệt không hỗ trợ phát giọng nói (Text-to-Speech)", true);
        return;
      }
      if (window.speechSynthesis.speaking) {
        window.speechSynthesis.cancel();
        panel.querySelectorAll(".chat-tts-icon-btn").forEach((b) => b.classList.remove("is-speaking"));
        return;
      }
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "vi-VN";
      utterance.rate = 1.0;
      btn.classList.add("is-speaking");
      utterance.onend = () => btn.classList.remove("is-speaking");
      utterance.onerror = () => btn.classList.remove("is-speaking");
      window.speechSynthesis.speak(utterance);
    });
  });

  panel.querySelector("[data-open-message-case]")?.addEventListener("click", () => {
    lastListView = "nurse-messages";
    loadCase(selected.case_id, { navigate, logout });
  });
  contextPanel.querySelector("[data-open-message-case]")?.addEventListener("click", () => {
    lastListView = "nurse-messages";
    loadCase(selected.case_id, { navigate, logout });
  });
  panel.querySelector("[data-nurse-message-form]")?.addEventListener("submit", (event) => sendNurseMessage(event, root, { navigate, logout }, selected));
  
  // Tự động cuộn xuống tin nhắn mới nhất
  const stream = panel.querySelector("#nurse-chat-stream");
  if (stream) stream.scrollTop = stream.scrollHeight;
}

function messageCaseRow(item, active) {
  const latest = lastDirectMessage(item);
  const author = latest?.role === "nurse" ? "Bạn" : "Bệnh nhân";
  const preview = latest?.content || "Đang chờ tin nhắn đầu tiên";
  const level = displayLevel(item);
  const pName = patientName(item);
  const timeStr = formatChatTime(item.updated_at);

  return `<button class="message-case-row${active ? " is-active" : ""}" type="button" data-message-case="${escapeHtml(item.case_id)}">
    <div class="message-case-row-avatar">
      ${nurseAvatar(pName, "patient", 40)}
    </div>
    <div class="message-case-row-body">
      <div class="message-case-row-top">
        <strong class="message-case-name">${escapeHtml(pName)}</strong>
        <span class="priority-badge is-compact ${priorityClass(level)}">${priorityLabels[level] || level}</span>
      </div>
      <div class="message-case-meta">
        <span class="message-case-complaint">${escapeHtml(complaint(item))}</span>
        ${timeStr ? `<time class="message-case-time">${timeStr}</time>` : ""}
      </div>
      <div class="message-case-preview">
        <span class="preview-text"><span class="preview-author">${author}:</span> ${escapeHtml(preview)}</span>
        <span class="message-case-id">#${shortCaseId(item.case_id)}</span>
      </div>
    </div>
  </button>`;
}

function messageThread(item) {
  const messages = directMessages(item);
  const level = displayLevel(item);
  const pName = patientName(item);
  const transcript = messages.length
    ? messages.map((message) => directMessageMarkup(message, item)).join("")
    : `<div class="message-thread-empty-prompt">${icon("chat", 32)}<h3>Bắt đầu cuộc trò chuyện</h3><p>Gửi câu hỏi để thu thập thêm thông tin bệnh sử cần thiết cho ca bệnh này.</p></div>`;

  return `
    <header class="message-thread-head">
      <div class="message-thread-identity">
        <div class="message-thread-avatar-wrap">
          ${nurseAvatar(pName, "patient", 44)}
          <span class="online-status-dot"></span>
        </div>
        <div class="message-thread-identity-text">
          <div class="message-thread-name-row">
            <strong>${escapeHtml(pName)}</strong>
            <span class="priority-badge ${priorityClass(level)}">${priorityLabels[level] || level}</span>
            <span class="message-thread-status">${icon("clock", 13)}Đang chờ phản hồi</span>
          </div>
          <small>Mã ca: <b>#${shortCaseId(item.case_id)}</b> · Triệu chứng: <b>${escapeHtml(complaint(item))}</b></small>
        </div>
      </div>
      <div class="message-thread-head-actions">
        <button class="secondary-button btn-sm" type="button" data-open-message-case>${icon("clipboard", 15)}<span>Mở hồ sơ ca</span></button>
      </div>
    </header>

    <div class="message-safety-note">
      ${icon("info", 16)}
      <span><b>Lưu ý chuyên môn:</b> Đây là kênh trao đổi trực tiếp để bổ sung thông tin. Kết luận phân loại và hướng dẫn xử trí chính thức chỉ được gửi sau khi bạn duyệt ca.</span>
    </div>

    <div class="message-thread-log" id="nurse-chat-stream">
      <div class="message-day-divider"><span>Hôm nay</span></div>
      ${transcript}
    </div>

    <div class="message-composer-wrapper">
      <form class="message-thread-composer" data-nurse-message-form>
        <div class="message-input-capsule">
          <div class="composer-actions-left">
            <button class="composer-icon-btn mic-speech-btn" type="button" id="nurse-mic-btn" title="Nhập bằng giọng nói (Speech-to-Text)">
              ${icon("mic", 18)}
            </button>
            <label class="composer-icon-btn file-attach-btn" title="Đính kèm tệp tin / hình ảnh">
              <input type="file" id="nurse-file-attachment" multiple accept="image/*,.pdf,.doc,.docx" class="sr-only" />
              ${icon("paperclip", 18)}
            </label>
          </div>
          <textarea id="nurse-message-input" name="message" rows="1" maxlength="5000" placeholder="Nhập tin nhắn, Enter để gửi, Shift+Enter xuống dòng"></textarea>
          <button class="composer-send-circle-btn" type="submit" title="Gửi tin nhắn (Enter)">
            ${icon("send", 17)}
          </button>
        </div>
        <div class="message-composer-note">
          ${icon("lock", 12)}
          <span>Trao đổi bổ sung thông tin · Không thay thế kết luận chốt ca</span>
        </div>
      </form>
    </div>
  `;
}

function messageCaseContext(item) {
  const level = displayLevel(item);
  const pName = patientName(item);
  const redFlags = item.red_flags || [];
  return `
    <header class="message-context-head">
      <div>
        <strong>${icon("clipboard", 16)} Ngữ cảnh ca lâm sàng</strong>
        <small>Đọc nhanh thông tin trước khi phản hồi</small>
      </div>
    </header>

    <div class="message-context-body">
      <div class="message-context-patient-box">
        ${nurseAvatar(pName, "patient", 46)}
        <div class="patient-box-meta">
          <strong class="patient-box-name">${escapeHtml(pName)}</strong>
          <small class="patient-box-id">Mã ca: <b>#${shortCaseId(item.case_id)}</b></small>
          <span class="patient-box-time">${icon("clock", 12)} Khởi tạo: ${formatDate(item.created_at)}</span>
        </div>
      </div>

      <div class="message-context-card-stack">
        <div class="message-context-card">
          <span class="context-card-label">Triệu chứng chính</span>
          <div class="context-card-val is-complaint">${escapeHtml(complaint(item))}</div>
        </div>

        <div class="message-context-card">
          <span class="context-card-label">Đề xuất phân loại AI</span>
          <div class="context-card-val">
            <span class="priority-badge ${priorityClass(level)}">${priorityDot(level)}${priorityLabels[level] || level}</span>
          </div>
        </div>

        ${redFlags.length ? `
          <div class="message-context-alert-card">
            <div class="alert-card-head">${icon("warning", 16)} <b>Phát hiện dấu hiệu nguy hiểm</b></div>
            <p>${escapeHtml(redFlags.map(rf => typeof rf === "string" ? rf : rf.label || rf.name).join(", "))}</p>
          </div>
        ` : ""}

        <div class="message-context-card">
          <span class="context-card-label">Trạng thái ca</span>
          <div class="context-card-val">
            <span class="message-context-state-pill">${icon("clock", 12)} Chờ bệnh nhân phản hồi</span>
          </div>
        </div>
      </div>

      <div class="message-context-action-wrap">
        <button class="primary-button wide-cta" type="button" data-open-message-case>
          ${icon("clipboard", 16)}<span>Duyệt ca & Chốt xử trí</span>
        </button>
      </div>

      <aside class="message-context-safety-banner">
        ${icon("shieldCheck", 16)}
        <span>Trao đổi trực tiếp không thay thế bước duyệt. Hướng dẫn chỉ được gửi sau khi bạn chốt ca.</span>
      </aside>
    </div>
  `;
}

function directMessageMarkup(message, item) {
  const isNurse = message.role === "nurse";
  const name = isNurse ? (message.author_name || state.user?.full_name || "Nhân viên y tế") : patientName(item);
  const time = message.created_at ? formatChatTime(message.created_at) : "";
  const avatar = nurseAvatar(name, isNurse ? "nurse" : "patient", 36);

  return `
    <div class="nurse-chat-turn is-${isNurse ? "nurse" : "patient"}">
      <div class="nurse-chat-turn-avatar">${avatar}</div>
      <div class="nurse-chat-turn-content">
        <div class="nurse-chat-turn-header">
          <span class="nurse-chat-turn-author">${escapeHtml(name)}${isNurse ? " (Bạn)" : ""}</span>
          ${time ? `<time class="nurse-chat-turn-time" title="${formatDate(message.created_at)}">${time}</time>` : ""}
          <button class="chat-tts-icon-btn" type="button" data-read-aloud="${escapeHtml(message.content)}" title="Đọc tin nhắn bằng giọng nói (Text-to-Speech)">
            ${icon("volume", 14)}
          </button>
        </div>
        <div class="nurse-chat-bubble">${paragraphs(message.content)}</div>
      </div>
    </div>
  `;
}

async function sendNurseMessage(event, root, context, item) {
  event.preventDefault();
  const form = event.currentTarget;
  const input = form.elements.message;
  const message = String(input.value || "").trim();
  if (!message) return;
  const submit = form.querySelector("button[type=submit]");
  submit.disabled = true;
  try {
    await api(`/api/v1/cases/${item.case_id}/review`, { method: "POST", body: JSON.stringify({ action: "ask_more", ask_more_question: message }) });
    input.value = "";
    await refreshNurseMessages(root, context);
  } catch (problem) {
    showToast(problem.message || "Không thể gửi tin nhắn lúc này.", true);
  }
}

/** W-06 — hàng đợi ca chờ duyệt. Bộ lọc mức ưu tiên nằm ở menu con của Hàng đợi. */
export function renderNurseQueue(root, context) {
  renderNurseList(root, context, "queue");
}

/** W-06b — ca đã duyệt. Cùng bộ lọc, cùng cột, cùng cách sắp xếp với hàng đợi. */
export function renderNurseDone(root, context) {
  renderNurseList(root, context, "done");
}

function renderNurseList(root, { navigate, logout }, scopeKey) {
  const scope = listScopes[scopeKey];
  lastListView = scope.nav === "done" ? "nurse-done" : "nurse-queue";
  root.innerHTML = nurseShell(scopeKey, `
    <div class="queue-head">
      <div>
        <h1>${scope.title}</h1>
        <p>${scope.intro}</p>
      </div>
      <div class="queue-head-actions">
        <span class="polling-chip">${icon("retry", 15)}<span id="queue-updated">Làm mới (polling tự động)</span></span>
        <div class="queue-search queue-head-search"><input id="queue-search" aria-label="Tìm ca" placeholder="Mã ca hoặc triệu chứng" /></div>
      </div>
    </div>
    <div class="banner is-warning" id="queue-message" hidden>${icon("warning", 19)}<span class="banner-text"></span><button class="secondary-button btn-sm" type="button" data-refresh>${icon("retry", 15)}<span>Thử lại</span></button></div>

    <div id="queue-list" class="queue-table"></div>
  `);

  bindAccountMenu(root, { logout, onProfileSaved: () => renderNurseList(root, { navigate, logout }, scopeKey) });
  bindSideNav(root, { navigate, logout }, scopeKey);
  root.querySelectorAll("[data-refresh]").forEach((button) => button.addEventListener("click", () => refreshQueue(root, { navigate, logout })));
  root.querySelector("#queue-search").addEventListener("input", () => paintQueue(root, { navigate, logout }));
  root.dataset.filter = scopeKey === "queue" ? queueFilter : doneFilter;
  root.dataset.scope = scopeKey;
  refreshQueue(root, { navigate, logout });
  polling = window.setInterval(() => refreshQueue(root, { navigate, logout, silent: true }), 15000);
}

export async function refreshQueue(root, context) {
  const message = root.querySelector("#queue-message");
  try {
    state.queue = await api("/api/v1/nurse/queue");
    message.hidden = true;
    root.querySelector("#queue-updated").textContent = `Cập nhật lúc ${formatDate(new Date())}`;
    paintQueue(root, context);
  } catch (problem) {
    // Trạng thái "stale" của bản thiết kế: giữ nguyên danh sách đã có trên màn hình và nói rõ nó là
    // dữ liệu cũ. Xoá danh sách đi khi mất mạng còn tệ hơn - điều dưỡng mất luôn các ca đang xử lý.
    message.hidden = false;
    message.querySelector(".banner-text").textContent = state.queue.length
      ? "Không tải được danh sách mới nhất — đang hiển thị dữ liệu đã lưu trước đó"
      : problem.message || "Không thể tải hàng đợi.";
  }
}

function paintQueue(root, { navigate, logout }) {
  const scope = listScopes[root.dataset.scope] || listScopes.queue;
  const filter = root.dataset.filter || "all";
  const query = root.querySelector("#queue-search").value.trim().toLocaleLowerCase("vi-VN");
  const scoped = state.queue.filter(scope.includes);
  paintOverview(root);

  const items = scoped
    .filter((item) => {
      if (filter !== "all" && displayLevel(item) !== filter) return false;
      if (!query) return true;
      return [item.case_id, complaint(item), priorityLabels[displayLevel(item)], statusLabels[item.status], item.red_flags?.length ? "red flag" : ""].join(" ").toLocaleLowerCase("vi-VN").includes(query);
    })
    .sort(compareCases);

  const list = root.querySelector("#queue-list");
  if (!items.length) {
    list.innerHTML = `<div class="queue-empty"><span class="state-icon is-ok">${icon("check", 32)}</span><h2>${escapeHtml(scope.emptyTitle)}</h2><p>${escapeHtml(scope.emptyCopy)}</p></div>`;
    return;
  }
  const header = `<div class="queue-head-row"><span></span><span class="col-label">Mã bệnh nhân</span><span class="col-label">Nhóm triệu chứng</span><span class="col-label">Mức ưu tiên AI</span><span class="col-label align-right">Thời gian chờ</span><span></span></div>`;
  list.innerHTML = header + items.map((item) => queueRow(item, scope)).join("");
  list.querySelectorAll("[data-case]").forEach((button) => button.addEventListener("click", () => loadCase(button.dataset.case, { navigate, logout })));
}

/** Ba thẻ số liệu cột phải. Đếm trên TOÀN BỘ `state.queue` chứ không theo scope - đó là điểm của
 *  một bảng tổng quan: đứng ở màn nào cũng thấy đủ số của cả hai, và bấm được để sang màn kia.
 *
 *  Chỉ hai con số, và cả hai đếm trên TOÀN BỘ `state.queue` chứ không theo màn đang mở - đó là điểm
 *  của một thanh điều hướng: đứng ở đâu cũng thấy đủ. */
export function paintOverview(root) {
  const pending = state.queue.filter((item) => !completedStatuses.has(item.status));
  const done = state.queue.filter((item) => completedStatuses.has(item.status));
  // Chưa có trạng thái "đã đọc" bền vững cho điều dưỡng, vì vậy badge đỏ biểu thị chính xác điều
  // cần hành động: cuộc trò chuyện mà lượt nhắn trực tiếp mới nhất là của bệnh nhân.
  const waitingReplies = state.queue.filter((item) => item.status === "needs_more_info" && lastDirectMessage(item)?.role === "patient").length;
  const countByLevel = (items) => {
    const counts = { Emergency: 0, Urgent: 0, "Self-care": 0 };
    for (const item of items) {
      const level = displayLevel(item);
      if (level in counts) counts[level] += 1;
    }
    return counts;
  };
  const counts = countByLevel(pending);
  const doneCounts = countByLevel(done);
  root.querySelector("#overview-queue").textContent = pending.length;
  root.querySelector("#overview-done").textContent = done.length;
  root.querySelector("#overview-filter-all").textContent = pending.length;
  root.querySelector("#overview-filter-Emergency").textContent = counts.Emergency;
  root.querySelector("#overview-filter-Urgent").textContent = counts.Urgent;
  root.querySelector("#overview-filter-Self-care").textContent = counts["Self-care"];
  root.querySelector("#overview-done-filter-all").textContent = done.length;
  root.querySelector("#overview-done-filter-Emergency").textContent = doneCounts.Emergency;
  root.querySelector("#overview-done-filter-Urgent").textContent = doneCounts.Urgent;
  root.querySelector("#overview-done-filter-Self-care").textContent = doneCounts["Self-care"];
  const messageBadge = root.querySelector("#overview-messages");
  if (messageBadge) {
    messageBadge.textContent = waitingReplies;
    messageBadge.classList.toggle("is-alert", waitingReplies > 0);
    messageBadge.setAttribute("aria-label", `${waitingReplies} cuộc trò chuyện đang chờ phản hồi`);
  }
}

function queueRow(item, scope) {
  const level = displayLevel(item);
  const hasRedFlag = item.status === "escalated" || Boolean(item.red_flags?.length);
  const emergency = level === "Emergency";
  return `<button class="queue-row ${emergency ? "is-emergency" : ""}" type="button" data-case="${item.case_id}">
    ${priorityDot(level)}
    <span class="case-code">${shortCaseId(item.case_id)}</span>
    <span class="group">${escapeHtml(complaint(item))}</span>
    <span class="signal">
      <span class="priority-badge ${priorityClass(level)}">${emergency ? icon("warning", 13) : ""}${priorityLabels[level] || level}</span>
      ${hasRedFlag ? `<span class="redflag-queue-tag">Red flag</span>` : ""}
    </span>
    <span class="wait">${waitingLabel(item.created_at)}${slaBadge(item)}</span>
    <span class="go">${scope.action}</span>
  </button>`;
}

async function loadCase(caseId, { navigate, logout }) {
  try { state.selectedNurseCase = await api(`/api/v1/cases/${caseId}`); sessionStorage.setItem("vmed_active_nurse_case_id", caseId); navigate("nurse-case"); } catch (problem) { showToast(problem.message, true); }
}

/**
 * W-07 — duyệt ca, điểm chốt HITL.
 *
 * Trái: phiếu tóm tắt (mọi trường đã thu thập, tag "Thiếu thông tin", hai dòng nguồn đối chiếu) rồi
 * hội thoại đầy đủ. Phải: red-flag (nếu có), thẻ mức ưu tiên AI kèm ĐỘ TIN CẬY, rồi ngăn hành động
 * xếp theo đúng thứ tự thiết kế: duyệt nguyên trạng → chỉnh mức → từ chối → (gạch) → hỏi thêm.
 */
export function renderNurseCase(root, { navigate, logout }) {
  const item = state.selectedNurseCase;
  if (!item) { navigate(lastListView); return; }
  const summary = item.summary || {};
  const structured = item.structured_data || {};
  const validation = item.validation || {};
  const proposal = item.triage_proposal || {};
  const missing = summary.missing_information || validation.missing_fields || structured.missing_fields || [];
  const isDone = completedStatuses.has(item.status);
  const isChatting = item.status === "needs_more_info";
  const level = priority(item);

  // Trạng thái "lỗi lưu" của thiết kế thay nút "Về hàng đợi" bằng chip khoá — cố ý: khi chưa lưu
  // được quyết định thì rời màn hình là mất nó.
  const headerRight = state.nurseSaveError
    ? `<span class="header-meta"><span class="pill is-muted">${icon("lock", 15)}<span>Đang khoá — chưa lưu được quyết định</span></span></span>`
    : `<div class="header-right"><button class="back-button" type="button" data-back>${icon("chevronLeft", 15)}<span>${lastListView === "nurse-done" ? "Về ca đã duyệt" : "Về hàng đợi"}</span></button>${accountMenu()}</div>`;

  root.innerHTML = `<section class="app-shell">
    ${nurseHeader("", { title: `Duyệt ca <b>${shortCaseId(item.case_id)}</b> · chờ ${waitingLabel(item.created_at)}`, right: headerRight })}
    <main class="page">
      <form id="review-form" class="review-grid">
        <div class="review-main">
          <section class="record-card" id="intake-summary">
            <div class="record-head"><b>Phiếu tóm tắt · Nhóm: ${escapeHtml(symptomGroupLabels[structured.symptom_group] || "Chưa xác định")}</b><span>Tạo lúc ${formatDate(item.created_at)}</span>${cardToggleButton()}</div>
            <div class="record-body" data-card-body>
              ${editableField("summary.chief_complaint", "Triệu chứng chính", summary.chief_complaint || symptomGroupLabels[structured.symptom_group] || "", isDone)}
              ${editableField("summary.onset", "Khởi phát", summary.onset || "", isDone)}
              ${editableField("summary.severity", "Mức độ", summary.severity ?? "", isDone)}
              ${collectedFields(item, missing)}
              <div class="field-row"><span class="label">Triệu chứng đi kèm</span><span class="value">${escapeHtml((summary.associated_symptoms || []).map((value) => String(value).replaceAll("_", " ")).join(", ") || "Chưa ghi nhận")}</span></div>
              ${provenanceRow("Nguồn đối chiếu detect", proposal.detect_source)}
              ${provenanceRow("Nguồn grounding kết luận", proposal.grounding_source)}
            </div>
          </section>

          <section class="record-card" id="handoff-summary">
            <div class="record-head"><b>Phiếu bàn giao (ISBAR)</b>${cardToggleButton()}</div>
            <div class="record-body" data-card-body><p class="muted-copy">Đang tải…</p></div>
          </section>

          ${sourceSupportCard(item)}

          <section class="record-card">
            <div class="record-head"><b>Hội thoại với trợ lý</b></div>
            <div class="transcript">${conversation(item.conversation)}</div>
          </section>
        </div>

        <div class="review-side">
          <div class="banner is-error" id="review-error" role="alert" hidden>${icon("alert", 19)}<span class="banner-text"></span></div>
          ${redFlagCallout(item, isDone)}

          ${graphDecisionBlock(item)}

          <label class="field">Phản hồi gửi bệnh nhân<textarea name="approved_response" rows="6" required ${isDone ? "disabled" : ""}>${escapeHtml(patientDraft(item, isDone))}</textarea></label>
          <label class="field">Ghi chú nội bộ <small>(không bắt buộc)</small><textarea name="nurse_notes" rows="2" ${isDone ? "disabled" : ""}></textarea></label>

          <div class="action-stack">
            <button class="primary-button" type="submit" data-approve ${isDone ? "disabled" : ""}>${icon("check", 18)}<span data-approve-label>Duyệt nguyên trạng</span></button>

            <div>
              <button class="secondary-button" type="button" data-priority-toggle aria-expanded="false" ${isDone ? "disabled" : ""}><span>Chỉnh sửa mức ưu tiên</span>${icon("chevronDown", 16)}</button>
              <div class="dropdown-menu" data-priority-menu hidden role="listbox" aria-label="Mức ưu tiên">
                ${["Emergency", "Urgent", "Self-care"].map((option) => `<button type="button" role="option" aria-selected="${option === level}" data-priority="${option}">${priorityDot(option)}<span>${priorityLabels[option]}</span>${option === level ? icon("check", 16) : ""}</button>`).join("")}
              </div>
              <input type="hidden" name="edited_priority" value="${escapeHtml(level)}" />
            </div>

            <div>
              <button class="soft-danger-button" type="button" data-reject-toggle aria-expanded="false" ${isDone ? "disabled" : ""}><span>Từ chối ca</span>${icon("chevronDown", 16)}</button>
              <div class="panel-inline is-reject" data-reject-panel hidden>
                <h3>Lý do từ chối (bắt buộc)</h3>
                <label class="field"><span class="section-label">Nhóm lý do</span>
                  <select name="reject_reason_code">
                    <option value="ai_incorrect">Đề xuất của AI không chính xác</option>
                    <option value="already_handled_offline">Ca đã được xử lý ngoài hệ thống</option>
                    <option value="other">Lý do khác</option>
                  </select>
                </label>
                <textarea name="reject_reason" placeholder="Ví dụ: Thông tin khai báo không đủ tin cậy, cần liên hệ lại bệnh nhân..."></textarea>
                <button class="danger-button btn-confirm" type="button" data-reject-confirm disabled>Xác nhận từ chối</button>
              </div>
            </div>

            <div class="stack-divider"></div>

            <div>
              <button class="tint-button wide" type="button" data-ask-toggle aria-expanded="${isChatting}" ${isDone ? "disabled" : ""}>${icon("ask", 18)}<span>Hỏi thêm</span></button>
              <div class="panel-inline is-ask" data-ask-panel ${isChatting ? "" : "hidden"}>
                <h3>Chat trực tiếp với bệnh nhân</h3>
                <p>Agent tạm dừng đặt câu hỏi trong lúc chat đang mở. Bạn trao đổi trực tiếp và tự đưa ra mức ưu tiên cuối cùng thay cho đề xuất của AI.</p>
                <span class="pill who-chip">${icon("user", 13)}<span>${escapeHtml(state.user?.full_name || "Nhân viên y tế")} đang trao đổi trực tiếp</span></span>
                <div class="ask-chat-thread" data-ask-thread>${conversation(item.conversation)}</div>
                <textarea name="ask_more_question" placeholder="${isChatting ? "Nhắn tiếp cho bệnh nhân..." : "Câu hỏi gửi tới bệnh nhân, ví dụ: Anh có tiền sử bệnh tim hoặc từng đặt stent chưa?"}" ${isDone ? "disabled" : ""}></textarea>
                <button class="primary-button btn-confirm" type="button" data-ask-confirm disabled ${isDone ? "disabled" : ""}>${icon("send", 16)}<span>Gửi</span></button>
              </div>
            </div>

            <p class="fine-print">Khi bạn vào chat, mức ưu tiên cuối cùng do <strong>bạn quyết định</strong>, không dùng đề xuất của agent. Khi đã đủ thông tin, dùng "Chỉnh sửa mức ưu tiên" rồi "Duyệt và gửi" ở trên để chốt mức ưu tiên cuối cùng và kết thúc ca.</p>
            ${isDone ? `<p class="fine-print">Ca này đã được xử lý và không thể thay đổi.</p>` : ""}
          </div>
        </div>
      </form>
    </main>
  </section>`;

  root.querySelector("[data-back]")?.addEventListener("click", () => navigate(lastListView));
  bindAccountMenu(root, { logout, onProfileSaved: () => renderNurseCase(root, { navigate, logout }) });
  bindRedFlagEditor(root);
  bindReviewActions(root, { navigate, logout, currentPriority: level });
  bindCardToggles(root);
  loadHandoffSummary(root, item.case_id);
  startNurseChatPolling(root, { navigate, logout });
}

function bindReviewActions(root, context) {
  const form = root.querySelector("#review-form");
  const priorityInput = form.querySelector("[name=edited_priority]");
  const approveLabel = form.querySelector("[data-approve-label]");

  const toggle = (button, panel) => {
    if (!button || !panel) return;
    button.addEventListener("click", () => {
      const open = panel.hidden;
      panel.hidden = !open;
      button.setAttribute("aria-expanded", String(open));
    });
  };
  toggle(form.querySelector("[data-priority-toggle]"), form.querySelector("[data-priority-menu]"));
  toggle(form.querySelector("[data-reject-toggle]"), form.querySelector("[data-reject-panel]"));
  toggle(form.querySelector("[data-ask-toggle]"), form.querySelector("[data-ask-panel]"));

  // Chọn mức khác trong dropdown chỉ ĐỔI Ý ĐỊNH, chưa gửi gì cả - nút duyệt phía trên đổi nhãn để
  // nói ra điều đó. Nút "Chuyển cấp cứu" riêng đã bỏ: chọn "Cấp cứu" ở đây rồi duyệt gửi đúng
  // `action=edit, edited_priority=Emergency` như nút cũ, nên không mất khả năng nào.
  form.querySelectorAll("[data-priority]").forEach((button) =>
    button.addEventListener("click", () => {
      const picked = button.dataset.priority;
      priorityInput.value = picked;
      form.querySelectorAll("[data-priority]").forEach((option) => option.setAttribute("aria-selected", String(option === button)));
      approveLabel.textContent = picked === context.currentPriority ? "Duyệt nguyên trạng" : `Duyệt với mức "${priorityLabels[picked]}"`;
      form.querySelector("[data-priority-menu]").hidden = true;
      form.querySelector("[data-priority-toggle]").setAttribute("aria-expanded", "false");
    }),
  );

  // Không có gì tự gửi: cả từ chối lẫn hỏi thêm đều đòi nội dung khác rỗng trước khi nút bật.
  const gate = (textarea, button) => {
    if (!textarea || !button) return;
    const sync = () => { button.disabled = !textarea.value.trim(); };
    textarea.addEventListener("input", sync);
    sync();
  };
  gate(form.querySelector("[name=reject_reason]"), form.querySelector("[data-reject-confirm]"));
  gate(form.querySelector("[name=ask_more_question]"), form.querySelector("[data-ask-confirm]"));

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const action = priorityInput.value === context.currentPriority ? "approve" : "edit";
    review(form, action, context);
  });
  form.querySelector("[data-reject-confirm]")?.addEventListener("click", () => review(form, "reject", context));
  form.querySelector("[data-ask-confirm]")?.addEventListener("click", () => review(form, "ask_more", context));
}

function showReviewError(form, message) {
  const banner = form.querySelector("#review-error");
  banner.querySelector(".banner-text").textContent = message;
  banner.hidden = !message;
  state.nurseSaveError = Boolean(message);
}

async function review(form, action, context) {
  const item = state.selectedNurseCase;
  const values = new FormData(form);
  showReviewError(form, "");

  const payload = { action, nurse_notes: String(values.get("nurse_notes") || "").trim() || null };

  if (action === "ask_more") {
    payload.ask_more_question = String(values.get("ask_more_question") || "").trim();
    if (!payload.ask_more_question) { showReviewError(form, "Vui lòng nhập câu hỏi gửi bệnh nhân."); return; }
  } else if (action === "reject") {
    const reason = String(values.get("reject_reason") || "").trim();
    if (!reason) { showReviewError(form, "Từ chối ca phải kèm lý do."); return; }
    payload.reject_reason_code = values.get("reject_reason_code") || "other";
    // Lý do tự do đi vào ghi chú nội bộ; `reject_reason_code` là MÃ dùng cho thống kê độ chính xác
    // AI-vs-điều dưỡng, không thay thế được cho nhau (xem NurseReviewRequest).
    payload.nurse_notes = payload.nurse_notes ? `${payload.nurse_notes}\n${reason}` : reason;
  } else {
    const response = String(values.get("approved_response") || "").trim();
    if (!response) { showReviewError(form, "Vui lòng nhập phản hồi dành cho bệnh nhân."); return; }
    payload.approved_response = response;
    if (action === "edit") payload.edited_priority = values.get("edited_priority");
  }

  const edits = collectFieldEdits(form, item);
  if (edits.error) { showReviewError(form, edits.error); return; }
  payload.field_edits = edits.list;

  try {
    await api(`/api/v1/cases/${item.case_id}/review`, { method: "POST", body: JSON.stringify(payload) });
    state.selectedNurseCase = await api(`/api/v1/cases/${item.case_id}`);
    state.nurseSaveError = false;
    showToast(action === "reject" ? "Đã từ chối ca." : action === "ask_more" ? "Đã gửi câu hỏi tới bệnh nhân." : "Đã lưu quyết định.");
    renderNurseCase(document.querySelector("#app"), context);
  } catch (problem) {
    showReviewError(form, problem.message || "Không thể lưu quyết định — vui lòng thử lại");
  }
}

/** Các trường còn lại của phiếu (`summary_fields` do agent dựng, đã kèm nhãn tiếng Việt). Trường
 *  thiếu hiện tag hổ phách "Thiếu thông tin" đúng như thiết kế — điều dưỡng cần biết chính xác ca
 *  này còn hổng gì TRƯỚC khi bấm duyệt.
 *
 *  Rơi về `missing_fields` (danh sách KEY thô) khi phiên chưa dựng được `summary_fields`: điều dưỡng
 *  đọc `urine_output` vẫn hiểu, khác hẳn bệnh nhân - nên nhánh dự phòng này giữ nguyên ở đây. */
function cardToggleButton() {
  return `<button class="card-toggle" type="button" data-card-toggle aria-expanded="true">${icon("chevronDown", 16)}</button>`;
}

function bindCardToggles(root) {
  root.querySelectorAll("[data-card-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const body = button.closest(".record-card")?.querySelector("[data-card-body]");
      if (!body) return;
      const expanded = button.getAttribute("aria-expanded") !== "false";
      button.setAttribute("aria-expanded", String(!expanded));
      body.hidden = expanded;
    });
  });
}

function collectedFields(item, fallbackMissing) {
  const rows = item?.summary_fields || [];
  if (rows.length) {
    // Trường thiếu đẩy xuống cuối phiếu: điều dưỡng đọc lướt các thông tin ĐÃ CÓ trước, tag "Thiếu
    // thông tin" gom lại cuối danh sách để không xen giữa làm rối luồng đọc top-down.
    return [...rows]
      .sort((a, b) => Number(Boolean(a.is_missing)) - Number(Boolean(b.is_missing)))
      .map(
        (row) =>
          `<div class="field-row"><span class="label">${escapeHtml(row.label)}</span>${
            row.is_missing
              ? `<span class="value"><span class="missing-tag">${icon("alert", 13)}Thiếu thông tin</span></span>`
              : `<span class="value">${escapeHtml(String(row.value ?? "—"))}</span>`
          }</div>`,
      )
      .join("");
  }
  if (!fallbackMissing.length) return "";
  return fallbackMissing
    .map((key) => `<div class="field-row"><span class="label">${escapeHtml(String(key).replaceAll("_", " "))}</span><span class="value"><span class="missing-tag">${icon("alert", 13)}Thiếu thông tin</span></span></div>`)
    .join("");
}

/** Hai dòng provenance của W-07. Không bịa nội dung khi backend chưa gán nguồn: một dòng "đối chiếu
 *  Bộ Y tế" hiện ra dù chẳng có nguồn nào là đúng thứ nguyên tắc grounded của dự án cấm. */
function provenanceRow(label, value) {
  if (!value) return "";
  return `<div class="provenance"><span class="label">${label}</span><span class="value">${escapeHtml(value)}</span></div>`;
}

function priority(item) { return item.triage_proposal?.priority || "Manual review"; }

// Nhãn 3 mức của Part 2 -> vocab priority của UI. Dùng ở CẢ hàng đợi (`displayLevel`) lẫn thẻ mức
// ưu tiên của W-07, nên chỉ được có MỘT bảng này. Giữ khớp với `C6_TRIAGE_LABEL_TO_PRIORITY`
// (src/services/engines/priority_labels.py).
const graphLabelPriority = { theo_doi_tai_nha: "Self-care", kham_som: "Urgent", cap_cuu: "Emergency" };

/** Mức mà điều dưỡng THẤY trên một hàng: KẾT LUẬN CỦA PART 2 (`graph_decision.triage_label`), đúng
 *  thứ thẻ mức ưu tiên ở màn duyệt W-07 hiển thị. Hai màn đọc chung một nguồn thì không thể nói hai
 *  mức khác nhau cho cùng một ca.
 *
 *  An toàn khi làm vậy vì `service._effective_c6_label` đã so nhãn C6 với `triage_proposal.priority`
 *  của rule engine và giữ mức NẶNG HƠN trước khi lưu - nhãn ở đây không bao giờ thấp hơn mức rule
 *  engine chốt.
 *
 *  Chưa có `graph_decision` (Part 2 chưa chạy xong hoặc lỗi API) thì rơi về `triage_proposal.priority`,
 *  và ca `escalated` luôn đọc là Cấp cứu - hàng đợi không được để trống mức của một ca red-flag.
 *
 *  MỌI chỗ hiển thị mức đều phải gọi hàm này - huy hiệu, viền đỏ, chip lọc, số đếm, thứ tự sắp xếp,
 *  ô tìm kiếm. Trước đây huy hiệu tự nâng lên "Cấp cứu" khi ca có `red_flags` còn bộ lọc lại đọc
 *  `triage_proposal.priority`, nên một ca hiện huy hiệu "Cấp cứu" mà nằm trong bộ lọc "Khám sớm".
 *
 *  `red_flags` KHÔNG được tự nâng mức: `symptom_case_bridge._red_flags` ánh xạ MỌI `reason_codes` của
 *  phiên thành RedFlagFinding, kể cả mã mức hổ phách như RF-28 "Rét run dữ dội" (rule engine chốt
 *  EARLY_VISIT chứ không phải EMERGENCY). Coi mọi red flag là cấp cứu làm chữ "Cấp cứu" mất nghĩa.
 *  Dấu hiệu nguy hiểm vẫn hiện, nhưng bằng thẻ "Red flag" riêng bên cạnh mức. */
export function displayLevel(item) {
  const fromPart2 = graphLabelPriority[item.graph_decision?.triage_label];
  if (fromPart2) return fromPart2;
  return item.status === "escalated" ? "Emergency" : priority(item);
}

// Nhãn của agent quyết định (src/graph_triage/) dùng bộ 3 mức riêng. `triage_label` KHÔNG phải nhãn
// thô của C6: `service._effective_c6_label` đã so với `triage_proposal.priority` của rule engine và
// nâng lên trước khi lưu, nên nhãn ở đây luôn >= mức của hàng đợi.
const graphLabels = { theo_doi_tai_nha: "Theo dõi tại nhà", kham_som: "Khám sớm", cap_cuu: "Cấp cứu" };

/** THẺ MỨC ƯU TIÊN DUY NHẤT của W-07. Thẻ "Mức ưu tiên AI đề xuất" của rule engine (part 1) đã được
 *  gỡ khỏi màn này: ở mode `c6`, `graph_decision.triage_label` và `triage_proposal.priority` luôn
 *  bằng nhau (gate chỉ nâng, không bao giờ hạ - `_raise_priority_from_c6` + `_effective_c6_label`),
 *  nên hiện cả hai chỉ là một mức nói hai lần.
 *
 *  `triage_proposal.priority` VẪN là field quyết định của hệ thống - hàng đợi, bản nháp phản hồi và
 *  giá trị mặc định của dropdown "Chỉnh sửa mức ưu tiên" đều đọc nó. Đây chỉ là thay đổi HIỂN THỊ.
 *
 *  Chỉ hiện kết luận cuối - không hiện xác suất hay evidence graph. Khi chưa có `graph_decision`
 *  (part 2 chưa chạy xong, hoặc lỗi API), thẻ không hiện: điều dưỡng tự đánh giá và vẫn là người
 *  duyệt cuối. KHÔNG được rơi về một mức đoán bừa ở đây. */
function graphDecisionBlock(item) {
  const decision = item.graph_decision;
  if (!decision) return "";
  const label = graphLabels[decision.triage_label] || decision.triage_label || "Không xác định";
  const tone = priorityClass(graphLabelPriority[decision.triage_label] || "Manual review");
  const raised = (decision.escalated_by || []).length
    ? `<p class="advisory-review">Đã nâng mức theo nhánh an toàn: ${escapeHtml(decision.escalated_by.join(", "))}.</p>`
    : "";
  return `<section class="ai-priority-card ${tone}">
    <div class="ai-priority-head"><span class="section-label">Mức ưu tiên AI đề xuất</span></div>
    <div class="ai-priority-value"><span class="priority-dot ${tone}" aria-hidden="true"></span><b>${escapeHtml(label)}</b></div>
    ${raised}
    <p>${escapeHtml(decision.disclaimer || "Quyết định cuối cùng thuộc về nhân viên y tế.")}</p>
  </section>`;
}
/** Khối nguồn y văn ĐỌC-CHỈ của part 3 (src/source_support/), tách biệt khỏi ô nháp phản hồi bệnh
 *  nhân - trích dẫn không còn tự đổ vào bản nháp có thể sửa (xem `patientDraft`), chỉ hiện ở đây.
 *  Card này KHÔNG được đưa vào form duyệt (không có `name=`), chỉ để đọc trước khi sửa ô phản hồi. */
function sourceSupportCard(item) {
  const support = item.graph_decision?.source_support;
  if (!support?.explanation_vi) return "";
  const summary = support.summary || {};
  const contradicted = summary.contradicted_claims || [];
  const citations = (support.explanation_citations || [])
    .map((cite) => {
      const quote = String(cite.quote || "").split(/\s+/).join(" ").trim();
      const label = escapeHtml(cite.publisher || cite.title || "Nguồn");
      const url = escapeHtml(cite.url || "");
      return `<li><span class="marker">${escapeHtml(cite.marker || "")}</span> <a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>${quote ? `<blockquote>"${escapeHtml(quote)}"</blockquote>` : ""}</li>`;
    })
    .join("");
  const contradictedNote = contradicted.length
    ? `<p class="advisory-review">Nguồn có mệnh đề TRÁI NGƯỢC với kết luận: ${escapeHtml(contradicted.join("; "))}. Cần xem lại trước khi duyệt.</p>`
    : "";
  return `<section class="advisory-card"><h3>Trích nguồn y văn (tham khảo)</h3><p class="advisory-note">${escapeHtml(support.method?.scope_note || "Nguồn tham khảo hỗ trợ mệnh đề lâm sàng tổng quát, không phải chẩn đoán cho ca này.")}</p><p class="advisory-summary">${escapeHtml(support.explanation_vi)}</p>${citations ? `<ul class="citation-list">${citations}</ul>` : ""}${contradictedNote}</section>`;
}

/** Nội dung mặc định của ô "Phản hồi gửi bệnh nhân". ĐÂY LÀ BẢN NHÁP, KHÔNG PHẢI ĐƯỜNG GỬI: điều
 *  dưỡng đọc, sửa rồi bấm duyệt. Không có đường nào ghi thẳng vào `patient_visible_response` - làm
 *  vậy sẽ khiến ca ESCALATED gửi thẳng cho bệnh nhân không qua ai.
 *
 *  Phần suy luận/trích nguồn của agent KHÔNG còn đổ vào đây - hiển thị riêng ở `graphDecisionBlock`
 *  (dưới card "Mức ưu tiên AI đề xuất") và `sourceSupportCard` (đọc-chỉ, cột chính), để điều dưỡng
 *  không nhầm nội dung tham khảo với bản nháp gửi bệnh nhân. Với ca red-flag, `patient_visible_response`
 *  giữ EMERGENCY_MESSAGE cố định (triage_pipeline._build_patient_safe_response) và câu đó không được mất. */
function patientDraft(item, isDone) {
  const stored = item.patient_visible_response;
  if (isDone) return stored || "";
  return stored || defaultResponse(priority(item));
}

function complaint(item) { return item.summary?.chief_complaint || symptomGroupLabels[item.structured_data?.symptom_group] || "Triệu chứng chung"; }
function compareCases(left, right) { const ranks = { Emergency: 0, Urgent: 1, "Manual review": 2, Routine: 3, "Self-care": 4 }; return (ranks[displayLevel(left)] ?? 9) - (ranks[displayLevel(right)] ?? 9) || new Date(left.created_at) - new Date(right.created_at); }

/** `ActorRole` chỉ có patient / nurse / system - KHÔNG có "agent", nên mọi lượt trả lời của trợ lý
 *  đi qua `symptom_case_bridge._conversation` đều mang role `system`. Vì vậy ở phiên bản trước, câu
 *  hỏi dài của trợ lý bị vẽ thành viên thuốc bo tròn `is-system` (kiểu dành cho một dòng thông báo
 *  ngắn) và tràn ra khỏi khung; lượt của điều dưỡng cũng rơi vào đúng kiểu đó nên không phân biệt
 *  được ai nói.
 *
 *  Ánh xạ ở đây bám nguồn thật: `system` là trợ lý (chỗ duy nhất sinh ra nó là bridge), `nurse` là
 *  điều dưỡng (`hitl_review`). Nếu sau này backend thêm role thật cho agent thì sửa lại bảng này. */
const bubbleRole = { patient: "patient", nurse: "nurse" };

function conversation(items = []) {
  if (!items.length) return `<p class="muted-copy">Chưa có lịch sử trao đổi.</p>`;
  return items
    .map((item) => `<div class="bubble is-${bubbleRole[item.role] || "agent"}">${paragraphs(item.content)}</div>`)
    .join("");
}

// ADR-007: `EMERGENCY_MESSAGE` là câu ĐIỀU DƯỠNG gửi đi sau khi duyệt, không phải câu hệ thống tự
// nói trong phiên. Nguyên văn giữ đúng như `common_safety/emergency_message.py` - hai bản lệch nhau
// nghĩa là bệnh nhân đọc hai câu khác nhau tuỳ đường đi, mà đây là câu quyết định gọi 115 hay không.
function defaultResponse(priorityValue) { if (priorityValue === "Emergency") return "Đây là tình huống cần được cấp cứu ngay bây giờ — vui lòng gọi 115 hoặc đến ngay cơ sở y tế/khoa cấp cứu gần nhất, không chờ thêm. Thông tin đã được chuyển cho điều dưỡng ưu tiên hỗ trợ."; if (priorityValue === "Urgent") return "Nhân viên y tế khuyến nghị bạn được khám sớm. Hãy gọi 115 nếu triệu chứng nặng lên."; return "Nhân viên y tế đã xem thông tin bạn cung cấp. Hãy tiếp tục theo dõi và liên hệ cơ sở y tế nếu triệu chứng nặng hơn."; }


// --- điều dưỡng sửa trường của phiếu (§4.4 `_guidance/what_to_do_next.md`) -----------------------
//
// Trước đây red flag là một banner ĐỌC-CHỈ và form duyệt chỉ có ba ô (mức ưu tiên, phản hồi, ghi
// chú) - tức là người có thẩm quyền lâm sàng cao nhất trong luồng lại là người duy nhất không sửa
// được phiếu. Đó là làm ngược chính mô hình HITL của dự án.
//
// Hai điều KHÔNG được nới cùng lúc, và chúng không phải một:
//  - `escalation_lock` (agent, trong phiên) chặn MODEL tự hạ escalation - giữ nguyên, không có UI nào ở đây chạm tới nó;
//  - quyền của điều dưỡng ở bước duyệt - chính là thứ màn hình này mở ra.
//
// Bản gốc do hệ thống sinh KHÔNG bị ghi đè: server ghi mọi thay đổi vào lớp overlay
// (`nurse_field_edits`) kèm `generated_value`. UI chỉ gửi giá trị mới + lý do.

function redFlagCallout(item, isDone) {
  const flags = item.red_flags || [];
  if (!flags.length) return "";
  const notice = item.emergency_notice_sent
    ? `<p class="red-flag-notice">Thông điệp cấp cứu ĐÃ hiển thị cho bệnh nhân. Hạ cờ bây giờ chỉ đổi phiếu và luồng xử trí - không thu hồi được nội dung bệnh nhân đã đọc.</p>`
    : "";
  const rows = flags
    .map((flag) => {
      const code = flag.code || "";
      const lowered = isLowered(item, code);
      return `<div class="red-flag-row" data-flag="${escapeHtml(code)}"><label><input type="checkbox" data-flag-active ${lowered ? "" : "checked"} ${isDone ? "disabled" : ""} /> ${escapeHtml(flag.label || code)}</label><input class="red-flag-reason" data-flag-reason placeholder="Lý do hạ dấu hiệu này (bắt buộc)" ${lowered ? "" : "hidden"} ${isDone ? "disabled" : ""} /></div>`;
    })
    .join("");
  return `<div class="redflag-callout"><div class="head">${icon("flag", 19)}<span>Red-flag: Có</span></div>${notice}${rows}</div>`;
}

// Trạng thái HIỆN TẠI của một cờ = bản overlay MỚI NHẤT của đúng trường đó, không phải bản đầu tiên.
function isLowered(item, code) {
  const edits = (item.nurse_field_edits || []).filter((edit) => edit.field === `red_flags.${code}`);
  if (!edits.length) return false;
  const last = edits[edits.length - 1];
  return last.current_value === false || last.current_value === "false" || last.current_value === null;
}

function bindRedFlagEditor(root) {
  root.querySelectorAll("[data-flag]").forEach((row) => {
    const active = row.querySelector("[data-flag-active]");
    const reason = row.querySelector("[data-flag-reason]");
    if (!active || !reason) return;
    active.addEventListener("change", () => { reason.hidden = active.checked; if (active.checked) reason.value = ""; });
  });
}

function editableField(path, label, value, isDone) {
  return `<div class="field-row"><span class="label">${label}</span><span class="value"><input class="clinical-input" data-edit-field="${path}" data-original="${escapeHtml(String(value))}" value="${escapeHtml(String(value))}" ${isDone ? "disabled" : ""} /></span></div>`;
}

/** Chỉ gửi trường THỰC SỰ đổi. Gửi cả những ô điều dưỡng không chạm tới sẽ tạo ra một overlay ghi
 *  "điều dưỡng đã xác nhận lại giá trị này" cho mọi lần duyệt - dấu vết audit mất hết ý nghĩa. */
function collectFieldEdits(root, item) {
  const list = [];
  root.querySelectorAll("[data-edit-field]").forEach((input) => {
    if (input.value === input.dataset.original) return;
    list.push({ field: input.dataset.editField, value: input.value, reason: "" });
  });
  for (const row of root.querySelectorAll("[data-flag]")) {
    const code = row.dataset.flag;
    const active = row.querySelector("[data-flag-active]");
    const reason = row.querySelector("[data-flag-reason]");
    const lowered = !active.checked;
    if (lowered === isLowered(item, code)) continue;
    if (lowered && !reason.value.trim()) {
      return { list: [], error: "Hạ một dấu hiệu nguy hiểm phải kèm lý do." };
    }
    list.push({ field: `red_flags.${code}`, value: !lowered, reason: reason.value.trim() });
  }
  return { list, error: "" };
}


// --- đồng hồ SLA cho ca nghi ngờ red-flag (ADR-007, §4.12) --------------------------------------
//
// Ngưỡng phải khớp `src/services/sessions/red_flag_sla.py`. Hai bản lệch nhau thì điều dưỡng thấy
// "còn 40 giây" trong khi server đã gửi `SLA_BREACH_MESSAGE` cho bệnh nhân - tức là UI đang nói dối
// đúng lúc nó cần nói thật nhất.
const SLA_CLINICAL_SECONDS = 300;
const SLA_WARNING_SECONDS = 180;

/** Cảnh báo NỘI BỘ, chỉ hiện cho điều dưỡng. Đồng hồ dừng khi ca đã được mở lần đầu. */
function slaBadge(item) {
  if (!item.queued_at || item.first_opened_at) return "";
  const waited = (Date.now() - new Date(item.queued_at).getTime()) / 1000;
  if (waited >= SLA_CLINICAL_SECONDS) return `<small class="sla-badge is-breached">Quá hạn phản hồi</small>`;
  if (waited >= SLA_WARNING_SECONDS) return `<small class="sla-badge is-warning">Sắp quá hạn · còn ${Math.max(0, Math.round((SLA_CLINICAL_SECONDS - waited) / 60 * 10) / 10)} phút</small>`;
  return "";
}


// --- phiếu bàn giao: hai output của ADR-006 ------------------------------------------------------
//
// Nạp RIÊNG bằng `GET /cases/{id}/summary` thay vì lấy từ `state.selectedNurseCase`: hai output này
// là dữ liệu DẪN XUẤT (map ISBAR + render theo field) và chỉ có nghĩa khi phiên đã đóng. Nhồi chúng
// vào payload của mọi lần `GET /cases/{id}` là bắt màn hình hàng đợi tải theo thứ nó không dùng tới.
//
// Lỗi khi nạp KHÔNG được làm hỏng màn hình duyệt: điều dưỡng vẫn phải bấm duyệt được kể cả khi khối
// tóm tắt không hiện ra. Vì thế nó nạp SAU khi render và tự thay nội dung của chính nó.

const ISBAR_TITLES = {
  I: "I · Nhận diện",
  S: "S · Tình huống",
  B: "B · Bối cảnh, tiền sử",
  A: "A · Đánh giá",
  R: "R · Đề xuất",
};

async function loadHandoffSummary(root, caseId) {
  const host = root.querySelector("#handoff-summary .record-body");
  if (!host) return;
  try {
    const data = await api(`/api/v1/cases/${caseId}/summary`);
    host.innerHTML = `${narrativeMarkup(data)}${isbarMarkup(data.isbar)}`;
  } catch (problem) {
    host.innerHTML = `<p class="muted-copy">${escapeHtml(problem.message || "Ca chưa có phiếu tóm tắt.")}</p>`;
  }
}

function isbarMarkup(blocks) {
  if (!blocks || !Object.keys(blocks).length) return `<p class="muted-copy">Chưa có dữ liệu.</p>`;
  return Object.entries(blocks)
    .map(([key, rows]) => {
      const items = Object.entries(rows)
        .map(([label, value]) => `<div class="field-row"><span class="label">${escapeHtml(label)}</span><span class="value">${escapeHtml(isbarValue(value))}</span></div>`)
        .join("");
      return `<div class="isbar-block"><h4>${escapeHtml(ISBAR_TITLES[key] || key)}</h4>${items}</div>`;
    })
    .join("");
}

function isbarValue(value) {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "Có" : "Không";
  return String(value);
}

/** Văn xuôi VÀ bản render theo field, cạnh nhau — bản thứ hai là ĐỐI CHỨNG của bản thứ nhất (§4.3).
 *  Đặt chúng xa nhau thì không ai đối chiếu, mà đó chính là việc khối này tồn tại để làm.
 *
 *  Khối "Chưa xác định được" chỉ liệt kê field AN TOÀN, và nó luôn hiện kể cả khi rỗng ý nghĩa:
 *  "chưa ai hỏi về ngất" và "người nhà nói bé không ngất" là hai hồ sơ khác hẳn nhau, và đó là chỗ
 *  điều dưỡng cần nhìn đầu tiên. */
function narrativeMarkup(data) {
  const fields = data.field_summary || {};
  const narrative = data.narrative
    ? `<div class="field-row is-block"><span class="label">Tóm tắt văn xuôi</span><div class="value prose">${paragraphs(data.narrative)}</div></div>`
    : "";
  const denied = (fields.denied || []).length
    ? `<div class="field-row"><span class="label">Người bệnh phủ nhận</span><span class="value">${escapeHtml(fields.denied.join(", "))}</span></div>`
    : "";
  const unknown = (fields.unknown_safety || []).length
    ? `<div class="field-row is-missing"><span class="label">Chưa xác định được (dấu hiệu an toàn)</span><span class="value">${escapeHtml(fields.unknown_safety.join(", "))}</span></div>`
    : "";
  return `${narrative}${denied}${unknown}`;
}
