import { api, ApiError, apiStream } from "../api.js";
import { accountMenu, bindAccountMenu, openAccountInfo, openSettings } from "./account.js?v=design-20260827c";
import { completedStatuses, setActiveCase, state } from "../state.js";
import {
  appHeader,
  escapeHtml,
  formatDate,
  icon,
  identityBlock,
  paragraphs,
  priorityClass,
  priorityDot,
  priorityLabels,
  shortCaseId,
  showToast,
  statusClass,
  statusLabels,
  symptomGroupLabels,
} from "../shared.js?v=design-20260827c";

// G1 "make capabilities explicit" — nguyên văn của bản thiết kế, dùng ở CẢ W-02 (mục 1) và dải năng
// lực của W-03. Một hằng số cho cả hai chỗ: hai bản chép tay lệch nhau nghĩa là phạm vi của trợ lý
// được mô tả hai kiểu khác nhau tuỳ người bệnh đang đứng ở màn nào.
const AI_SCOPE_VI =
  "Trợ lý AI hỗ trợ người dùng đánh giá mức độ khẩn cấp dựa trên các triệu chứng được cung cấp — không chẩn đoán bệnh, không kê đơn thuốc.";

// ── Đồng bộ trạng thái ca ─────────────────────────────────────────────────────────────────────
// Điều dưỡng duyệt ở máy khác, nên màn hình bệnh nhân không có cách nào tự biết ngoài việc hỏi lại.
// ADR-005 đã chốt polling thay vì WebSocket cho MVP; hàng đợi điều dưỡng vốn đã polling 15s, phía
// bệnh nhân thì chưa có gì - đó là lý do trước đây phải F5 mới thấy kết quả.
let casePolling = null;
let quickChatPolling = null;
const PATIENT_THEME_KEY = "vmed_patient_theme";
const PATIENT_SIDEBAR_KEY = "vmed_patient_sidebar_collapsed";
const QUICK_CHAT_OPEN_KEY = "vmed_quick_chat_open";
const QUICK_CHAT_SEEN_PREFIX = "vmed_quick_chat_seen_";
const QUICK_CHAT_POSITION_KEY = "vmed_quick_chat_position";

function patientSidebarCollapsed() {
  try {
    return localStorage.getItem(PATIENT_SIDEBAR_KEY) === "1";
  } catch {
    return false;
  }
}

function readPatientTheme() {
  try {
    return localStorage.getItem(PATIENT_THEME_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

function applyPatientTheme(theme) {
  document.documentElement.dataset.theme = theme;
}

/** Chủ đề là tuỳ chọn trong phiên bệnh nhân. Màn công khai không có bộ dark theme riêng, nên khi
 * đăng xuất phải trả token về sáng thay vì để màu chữ tối kế thừa trên các hero nền sáng. */
export function resetPatientTheme() {
  try {
    localStorage.removeItem(PATIENT_THEME_KEY);
  } catch {
    // Vẫn trả giao diện về sáng nếu trình duyệt không cho truy cập localStorage.
  }
  applyPatientTheme("light");
}

function bindPatientTheme(root) {
  root.querySelector("[data-theme-toggle]")?.addEventListener("click", (event) => {
    const next = event.currentTarget.dataset.theme === "dark" ? "light" : "dark";
    try {
      localStorage.setItem(PATIENT_THEME_KEY, next);
    } catch {
      // Chế độ vẫn đổi trong phiên hiện tại nếu trình duyệt chặn localStorage.
    }
    applyPatientTheme(next);
    event.currentTarget.dataset.theme = next;
    event.currentTarget.setAttribute("aria-pressed", String(next === "dark"));
    event.currentTarget.querySelector("[data-theme-label]").textContent = `Chủ đề ${next === "dark" ? "sáng" : "tối"}`;
    event.currentTarget.setAttribute("aria-label", `Chuyển sang chủ đề ${next === "dark" ? "sáng" : "tối"}`);
  });
}

function bindPatientSidebar(root) {
  root.querySelector("[data-patient-sidebar-toggle]")?.addEventListener("click", (event) => {
    const sidebar = root.querySelector("[data-patient-sidebar]");
    const workspace = root.querySelector("[data-patient-workspace]");
    if (!sidebar || !workspace) return;
    const collapsed = sidebar.classList.toggle("is-collapsed");
    workspace.classList.toggle("is-sidebar-collapsed", collapsed);
    const label = collapsed ? "Mở rộng" : "Thu gọn";
    event.currentTarget.setAttribute("aria-label", label);
    event.currentTarget.setAttribute("aria-expanded", String(!collapsed));
    event.currentTarget.dataset.tooltip = label;
    event.currentTarget.innerHTML = icon(collapsed ? "chevronRight" : "chevronLeft", 16);
    try {
      localStorage.setItem(PATIENT_SIDEBAR_KEY, collapsed ? "1" : "0");
    } catch {
      // Thanh vẫn đổi trạng thái trong phiên hiện tại nếu trình duyệt chặn localStorage.
    }
  });
}

applyPatientTheme(readPatientTheme());

export function stopCasePolling() {
  if (casePolling) window.clearInterval(casePolling);
  if (quickChatPolling) window.clearInterval(quickChatPolling);
  casePolling = null;
  quickChatPolling = null;
}

/** Chỉ vẽ lại khi có thay đổi THẬT. Vẽ lại mỗi 10s vô điều kiện sẽ nháy màn hình và cuộn lại khung
 *  chat trong lúc người bệnh đang đọc. */
function statusSignature(item) {
  return [item?.status, item?.triage_proposal?.priority, item?.patient_visible_response, item?.red_flags?.length, item?.conversation?.length].join("|");
}

function startCasePolling(root, context, render) {
  stopCasePolling();
  if (!state.caseId) return;
  casePolling = window.setInterval(async () => {
    // Đang giữa một lượt chat thì không chen: `submitMessage` sẽ tự cập nhật case khi xong.
    if (state.patientBusy) return;
    let fresh;
    try {
      fresh = await api(`/api/v1/cases/${state.caseId}`);
    } catch {
      return; // Mất mạng tạm thời không được làm hỏng màn hình đang xem.
    }
    if (statusSignature(fresh) === statusSignature(state.currentPatientCase)) return;
    state.currentPatientCase = fresh;
    // Giữ lại phần người bệnh đang gõ dở - vẽ lại mà mất chữ thì tệ hơn là chậm cập nhật.
    const draft = root.querySelector("#patient-message")?.value || "";
    render(root, context);
    const input = root.querySelector("#patient-message");
    if (input && draft) input.value = draft;
    // Ca đã có kết luận thì không còn gì để chờ.
    if (fresh.status === "approved" || fresh.status === "rejected") stopCasePolling();
  }, 10000);
}

/** Thanh điều hướng giữ lối vào ca mới sát ngay sau trang chủ. Nút luôn đi qua màn lưu ý an toàn
 * trước khi tạo ca, nên không nhảy thẳng qua bước xác nhận bắt buộc. */
function patientNav(active) {
  return [
    { label: "Trang chủ", active: active === "home", action: "home" },
    { label: "Khai báo triệu chứng", active: false, action: "start" },
    { label: "Kết quả của tôi", active: active === "cases", action: "cases" },
  ];
}

function bindPatientNav(root, { navigate }) {
  root.querySelectorAll("[data-nav]").forEach((button) =>
    button.addEventListener("click", () => {
      if (button.dataset.nav === "home") navigate("patient-home");
      if (button.dataset.nav === "start") navigate("disclaimer");
      if (button.dataset.nav === "cases") navigate("patient-cases");
      if (button.dataset.nav === "health") navigate("patient-health");
      if (button.dataset.nav === "maps") showToast("Bản đồ cơ sở y tế đang được phát triển.");
      if (button.dataset.nav === "settings") openSettings();
      if (button.dataset.nav === "help") openAccountInfo("help");
    }),
  );
}

/** Dải "Trường hợp khẩn cấp - Gọi 115". Nằm TRÊN header và có mặt ở MỌI màn bệnh nhân, kể cả màn
 *  chỉ đọc lịch sử: người đang có triệu chứng nguy hiểm không nhất thiết đang đứng ở trang chủ, và
 *  câu này chỉ có tác dụng nếu nó ở chỗ họ đang nhìn. */
function emergencyBar() {
  return `<div class="patient-emergency-bar"><div><span class="patient-emergency-signal" aria-hidden="true"></span><span><strong>Trường hợp khẩn cấp:</strong> Đau ngực dữ dội, khó thở cấp, ngất xỉu hoặc chấn thương nặng, vui lòng không chờ trong ứng dụng.</span></div><a href="tel:115">${icon("phone", 15)}<span>Gọi 115</span></a></div>`;
}

/** Header chuẩn của mọi màn bệnh nhân. Đi qua đây thay vì gọi thẳng `appHeader` để dải khẩn cấp
 *  không thể sót ở màn nào. */
function patientHeader(active, { title = "", right = "" } = {}) {
  return emergencyBar() + appHeader({
    nav: patientNav(active),
    title,
    right: right || `<div class="header-right">${identityBlock("Bệnh nhân")}${accountMenu()}</div>`,
  });
}

/** Khung điều hướng của khu vực bệnh nhân. Thanh bên chỉ áp dụng cho hai màn tổng quan, nơi người
 * bệnh cần quay lại giữa trang chủ và kết quả; luồng khai báo vẫn dùng header gọn để tập trung vào
 * từng bước và không làm gián đoạn cảnh báo an toàn. */
function patientSideNav(active) {
  const theme = readPatientTheme();
  const collapsed = patientSidebarCollapsed();
  const toggleLabel = collapsed ? "Mở rộng" : "Thu gọn";
  const item = (key, label, glyph) => `<button class="patient-side-nav-item${key === active ? " is-active" : ""}" type="button" data-nav="${key}">
    ${icon(glyph, 18)}<span>${label}</span>
  </button>`;

  return `<aside class="patient-side-nav${collapsed ? " is-collapsed" : ""}" data-patient-sidebar>
    <button class="patient-side-toggle" type="button" data-patient-sidebar-toggle aria-label="${toggleLabel}" aria-expanded="${!collapsed}" data-tooltip="${toggleLabel}">${icon(collapsed ? "chevronRight" : "chevronLeft", 16)}</button>
    <a class="patient-side-brand brand" href="/" aria-label="VMedTriage">${icon("logo", 27)}<span class="brand-word">VMed<span>Triage</span></span></a>
    <nav aria-label="Điều hướng bệnh nhân">
      ${item("home", "Trang chủ", "pulse")}
      ${item("start", "Khai báo triệu chứng", "chat")}
      ${item("cases", "Kết quả của tôi", "shieldCheck")}
    </nav>
    <div class="patient-side-tools">
      <p>Tiện ích</p>
      ${item("health", "Hồ sơ sức khỏe", "user")}
      ${item("maps", "Bản đồ cơ sở y tế", "mapPin")}
      ${item("settings", "Cài đặt", "settings")}
      ${item("help", "Trợ giúp & liên hệ", "ask")}
      <button class="patient-theme-toggle" type="button" data-theme-toggle data-theme="${theme}" aria-pressed="${theme === "dark"}" aria-label="Chuyển sang chủ đề ${theme === "dark" ? "sáng" : "tối"}">
        <span class="patient-theme-icon">${icon("sun", 17)}${icon("moon", 17)}</span>
        <span data-theme-label>Chủ đề ${theme === "dark" ? "sáng" : "tối"}</span>
      </button>
    </div>
    <div class="patient-side-account">${accountMenu()}${identityBlock("Bệnh nhân")}</div>
  </aside>`;
}

function patientDashboardShell(active, content, { quickChat = true } = {}) {
  const collapsed = patientSidebarCollapsed();
  return `<section class="app-shell patient-dashboard-shell">
    ${emergencyBar()}
    <div class="patient-workspace${collapsed ? " is-sidebar-collapsed" : ""}" data-patient-workspace>
      ${patientSideNav(active)}
      <main class="patient-main">${content}</main>
      ${quickChat ? quickChatDockMarkup() : ""}
      ${patientSafetyMarquee()}
    </div>
  </section>`;
}

function quickChatDockMarkup() {
  return `<aside id="quick-chat-dock" class="quick-chat-dock" hidden aria-label="Trao đổi nhanh với nhân viên y tế"></aside>`;
}

function patientSafetyMarquee() {
  return `<div class="patient-safety-marquee" role="note" aria-label="Lưu ý an toàn">
    <div class="patient-safety-marquee-track"><span>VMedTriage hỗ trợ sàng lọc mức độ ưu tiên ban đầu, không thay thế chẩn đoán. Mọi hướng dẫn xử trí đều do nhân viên y tế xác nhận trước khi gửi.</span><i aria-hidden="true">•</i><span aria-hidden="true">VMedTriage hỗ trợ sàng lọc mức độ ưu tiên ban đầu, không thay thế chẩn đoán. Mọi hướng dẫn xử trí đều do nhân viên y tế xác nhận trước khi gửi.</span><i aria-hidden="true">•</i></div>
  </div>`;
}

function quickChatOpen() {
  try {
    return sessionStorage.getItem(QUICK_CHAT_OPEN_KEY) === "1";
  } catch {
    return false;
  }
}

function setQuickChatOpen(open) {
  try {
    sessionStorage.setItem(QUICK_CHAT_OPEN_KEY, open ? "1" : "0");
  } catch {
    // Không cần lưu trạng thái mở nếu trình duyệt chặn sessionStorage.
  }
}

function quickChatPosition() {
  try {
    const saved = JSON.parse(localStorage.getItem(QUICK_CHAT_POSITION_KEY) || "null");
    if (Number.isFinite(saved?.left) && Number.isFinite(saved?.top)) return saved;
  } catch {
    // Vị trí mặc định từ CSS vẫn dùng được nếu localStorage không khả dụng.
  }
  return null;
}

function clampQuickChatPosition(left, top) {
  const margin = 10;
  return {
    left: Math.round(Math.min(Math.max(margin, left), Math.max(margin, window.innerWidth - 58 - margin))),
    top: Math.round(Math.min(Math.max(margin, top), Math.max(margin, window.innerHeight - 58 - margin))),
  };
}

function applyQuickChatPosition(dock) {
  const saved = quickChatPosition();
  if (!saved) return;
  const position = clampQuickChatPosition(saved.left, saved.top);
  dock.style.left = `${position.left}px`;
  dock.style.top = `${position.top}px`;
}

function bindQuickChatDrag(dock) {
  const trigger = dock.querySelector("[data-quick-chat-toggle]");
  if (!trigger) return;
  let drag = null;
  let suppressClick = false;

  trigger.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    const rect = dock.getBoundingClientRect();
    drag = { pointerId: event.pointerId, offsetX: event.clientX - rect.left, offsetY: event.clientY - rect.top, moved: false };
    trigger.setPointerCapture?.(event.pointerId);
  });
  trigger.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const position = clampQuickChatPosition(event.clientX - drag.offsetX, event.clientY - drag.offsetY);
    if (Math.abs(position.left - dock.getBoundingClientRect().left) > 3 || Math.abs(position.top - dock.getBoundingClientRect().top) > 3) drag.moved = true;
    dock.style.left = `${position.left}px`;
    dock.style.top = `${position.top}px`;
  });
  const finishDrag = (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    if (drag.moved) {
      const position = clampQuickChatPosition(dock.getBoundingClientRect().left, dock.getBoundingClientRect().top);
      try {
        localStorage.setItem(QUICK_CHAT_POSITION_KEY, JSON.stringify(position));
      } catch {
        // Kéo vẫn hoạt động trong trang hiện tại nếu trình duyệt chặn localStorage.
      }
      suppressClick = true;
    }
    trigger.releasePointerCapture?.(event.pointerId);
    drag = null;
  };
  trigger.addEventListener("pointerup", finishDrag);
  trigger.addEventListener("pointercancel", finishDrag);
  trigger.addEventListener("click", (event) => {
    if (!suppressClick) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    suppressClick = false;
  });
}

function nurseMessageCount(triageCase) {
  return triageCase?.conversation?.filter((message) => message.role === "nurse").length || 0;
}

function quickChatSeenCount(caseId) {
  try {
    return Number(sessionStorage.getItem(`${QUICK_CHAT_SEEN_PREFIX}${caseId}`) || 0);
  } catch {
    return 0;
  }
}

function markQuickChatRead(triageCase) {
  if (!triageCase?.case_id) return;
  try {
    sessionStorage.setItem(`${QUICK_CHAT_SEEN_PREFIX}${triageCase.case_id}`, String(nurseMessageCount(triageCase)));
  } catch {
    // Badge chỉ là tiện ích cục bộ; không được làm gián đoạn việc đọc ca nếu storage bị chặn.
  }
}

/** Chat nhanh chỉ dành cho lúc điều dưỡng đang hỏi trực tiếp (`needs_more_info`). Không dựng một
 * bản chat AI thứ hai ở trang tổng quan: ngoài gây nhiễu, nó có thể làm người bệnh hiểu nhầm câu
 * hỏi trực tiếp của nhân viên y tế là câu hỏi tự động của trợ lý. */
function bindQuickChatDock(root, { navigate }) {
  const dock = root.querySelector("#quick-chat-dock");
  if (!dock) return;

  const refresh = async () => {
    try {
      const cases = await api("/api/v1/patient/history");
      const activeCase = cases.find((item) => item.status === "needs_more_info");
      if (!activeCase) {
        dock.hidden = true;
        return;
      }
      if (quickChatOpen()) markQuickChatRead(activeCase);
      renderQuickChatDock(root, { navigate }, activeCase, refresh);
    } catch {
      dock.hidden = true;
    }
  };

  if (quickChatPolling) window.clearInterval(quickChatPolling);
  refresh();
  quickChatPolling = window.setInterval(refresh, 15000);
}

function renderQuickChatDock(root, { navigate }, triageCase, refresh) {
  const dock = root.querySelector("#quick-chat-dock");
  if (!dock) return;
  const open = quickChatOpen();
  const totalNurseMessages = nurseMessageCount(triageCase);
  const unread = Math.max(0, totalNurseMessages - quickChatSeenCount(triageCase.case_id));
  const messages = initialMessages(triageCase)
    .filter((message) => message.role === "nurse" || message.role === "patient")
    .slice(-4);

  dock.hidden = false;
  dock.classList.toggle("is-open", open);
  applyQuickChatPosition(dock);
  dock.innerHTML = `<button class="quick-chat-trigger" type="button" data-quick-chat-toggle aria-expanded="${open}" aria-label="${open ? "Thu gọn" : "Mở"} trao đổi với nhân viên y tế">
      <span class="quick-chat-robot-frame" aria-hidden="true"><img class="quick-chat-robot" src="/assets/triage-ai-doctor-looking-left.png" alt="" /></span>${unread ? `<b class="quick-chat-unread" aria-label="${unread} tin nhắn chưa đọc">${unread > 9 ? "9+" : unread}</b>` : ""}
    </button>
    ${open ? `<section class="quick-chat-panel" aria-label="Trao đổi nhanh">
      <header><span class="quick-chat-title"><i>${icon("user", 16)}</i><span><strong>${escapeHtml(triageCase.reviewed_by_name || "Nhân viên y tế")}</strong><small>Đang chờ bạn phản hồi</small></span></span><button type="button" class="quick-chat-collapse" data-quick-chat-toggle aria-label="Thu gọn trao đổi">${icon("chevronRight", 16)}</button></header>
      <div class="quick-chat-thread">${messages.length ? messages.map(messageMarkup).join("") : `<p>Nhân viên y tế sẽ nhắn tại đây khi cần thêm thông tin.</p>`}</div>
      <form class="quick-chat-composer" data-quick-chat-form>
        <label class="sr-only" for="quick-chat-message">Trả lời nhân viên y tế</label>
        <textarea id="quick-chat-message" name="message" rows="1" maxlength="5000" placeholder="Trả lời nhân viên y tế..."></textarea>
        <button type="submit" class="primary-button" aria-label="Gửi tin nhắn">${icon("send", 17)}</button>
      </form>
      <button class="quick-chat-open-case" type="button" data-quick-chat-open-case>Xem toàn bộ cuộc trao đổi ${icon("chevronRight", 15)}</button>
    </section>` : ""}`;

  bindQuickChatDrag(dock);
  dock.querySelectorAll("[data-quick-chat-toggle]").forEach((button) => button.addEventListener("click", () => {
    const nextOpen = !quickChatOpen();
    setQuickChatOpen(nextOpen);
    if (nextOpen) markQuickChatRead(triageCase);
    renderQuickChatDock(root, { navigate }, triageCase, refresh);
  }));
  dock.querySelector("[data-quick-chat-open-case]")?.addEventListener("click", () => {
    markQuickChatRead(triageCase);
    openPatientCase(triageCase.case_id, { navigate }, { fromCases: true });
  });
  dock.querySelector("[data-quick-chat-form]")?.addEventListener("submit", (event) => sendQuickChatMessage(event, root, { navigate }, triageCase, refresh));
}

async function sendQuickChatMessage(event, root, { navigate }, triageCase, refresh) {
  event.preventDefault();
  const form = event.currentTarget;
  const input = form.elements.message;
  const message = String(input.value || "").trim();
  if (!message) return;
  const submit = form.querySelector("button[type=submit]");
  submit.disabled = true;
  try {
    await api("/api/v1/chat", { method: "POST", body: JSON.stringify({ case_id: triageCase.case_id, message }) });
    input.value = "";
    await refresh();
  } catch (problem) {
    showToast(problem.message || "Không thể gửi tin nhắn lúc này.", true);
    submit.disabled = false;
  }
}

/** Hướng dẫn thao tác của người bệnh. Đây cố ý không lặp lại ba lưu ý bắt buộc ở màn disclaimer:
 * người dùng bấm nút này để biết dùng sản phẩm ra sao, còn disclaimer chỉ là xác nhận an toàn trước
 * khi mở một ca mới. */
function openPatientUsageGuide() {
  const dialog = document.createElement("div");
  dialog.className = "help-dialog patient-usage-guide";
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  dialog.setAttribute("aria-labelledby", "patient-usage-guide-title");
  dialog.innerHTML = `<button class="help-backdrop" type="button" aria-label="Đóng hướng dẫn" data-close-patient-guide></button><section class="help-modal patient-guide-modal"><div class="help-modal-heading"><div><p class="eyebrow">Dành cho bệnh nhân</p><h2 id="patient-usage-guide-title">Hướng dẫn sử dụng</h2></div><button class="help-close" type="button" aria-label="Đóng hướng dẫn" data-close-patient-guide>×</button></div><p class="help-intro">VMedTriage giúp bạn gửi thông tin triệu chứng để nhân viên y tế xem xét. Hệ thống không chẩn đoán hoặc tự gửi hướng dẫn xử trí.</p><div class="patient-guide-grid"><article><span class="patient-guide-icon is-blue">${icon("chat", 20)}</span><div><h3>Bắt đầu một ca mới</h3><p>Chọn “Khai báo triệu chứng”, đọc lưu ý an toàn rồi bắt đầu trao đổi.</p></div></article><article><span class="patient-guide-icon is-violet">${icon("ask", 20)}</span><div><h3>Mô tả theo điều bạn biết</h3><p>Nêu triệu chứng, thời điểm bắt đầu, diễn biến và điều khiến bạn lo lắng. Không chắc thì có thể nói không rõ.</p></div></article><article><span class="patient-guide-icon is-green">${icon("check", 20)}</span><div><h3>Kiểm tra phần tóm tắt</h3><p>Khi trợ lý hỏi xác nhận, chỉ xác nhận khi nội dung phản ánh đúng thông tin bạn đã cung cấp.</p></div></article><article><span class="patient-guide-icon is-amber">${icon("clock", 20)}</span><div><h3>Theo dõi kết quả của tôi</h3><p>Xem trạng thái ca trong “Kết quả của tôi”. Hướng dẫn chỉ xuất hiện sau khi nhân viên y tế duyệt.</p></div></article><article><span class="patient-guide-icon is-health">${icon("user", 20)}</span><div><h3>Bổ sung hồ sơ sức khỏe</h3><p>Thêm dị ứng, bệnh nền hoặc thuốc đang dùng để tiện tự kiểm tra khi cần.</p></div></article></div><aside class="patient-guide-safety">${icon("phone", 19)}<div><strong>Không chờ trong ứng dụng nếu có dấu hiệu cấp cứu</strong><span>Đau ngực dữ dội, khó thở cấp, ngất xỉu hoặc chấn thương nặng: gọi 115 ngay.</span></div></aside><div class="help-actions"><button class="primary-button" type="button" data-close-patient-guide>Đã hiểu</button></div></section>`;
  document.body.append(dialog);
  const close = () => {
    document.removeEventListener("keydown", onKeydown);
    dialog.remove();
  };
  const onKeydown = (event) => { if (event.key === "Escape") close(); };
  dialog.querySelectorAll("[data-close-patient-guide]").forEach((button) => button.addEventListener("click", close));
  document.addEventListener("keydown", onKeydown);
}

/** W-00 — trang chủ bệnh nhân. */
function renderPatientHomeLegacy(root, { navigate, logout }) {
  const current = state.currentPatientCase;
  const name = state.user?.full_name || "bạn";
  root.innerHTML = `<section class="app-shell">${patientHeader("home")}
    <main class="page">
      <div class="home-stack">
        <div class="home-top">
          <section class="home-hero">
            <div>
              <p class="home-hello">Chào ${escapeHtml(name)}</p>
              <h1>Bạn đang gặp vấn đề gì hôm nay?</h1>
            </div>
            <p>Mô tả triệu chứng bằng lời của bạn. Trợ lý sẽ hỏi thêm theo checklist y tế, sau đó nhân viên y tế xác nhận mức ưu tiên và gửi hướng dẫn xử trí cho bạn.</p>
            <div class="action-row">
              <button class="primary-button" type="button" data-start>${icon("chat", 18)}<span>Bắt đầu khai báo triệu chứng</span></button>
              <button class="secondary-button" type="button" data-guide>Xem hướng dẫn sử dụng</button>
            </div>
            <p class="fine-print">Thời gian trung bình để có hướng dẫn ban đầu: dưới 3 phút.</p>
          </section>

          <div class="home-aside">
            <div class="alert-card">
              <b>${icon("phone", 19)} Trường hợp khẩn cấp</b>
              <p>Đau ngực dữ dội, khó thở nặng, co giật, chảy máu không cầm — gọi <strong class="num">115</strong> ngay, không chờ trong ứng dụng.</p>
            </div>
            ${openCaseCard(current)}
          </div>
        </div>

        <div class="feature-row">
          <article><span class="feature-icon">${icon("clipboard", 21)}</span><h3>Khai báo triệu chứng</h3><p>5 nhóm triệu chứng: Sốt, Đau bụng, Đau ngực, Khó thở, Đau đầu / Chấn thương đầu nhẹ.</p></article>
          <article><span class="feature-icon is-green">${icon("shieldCheck", 21)}</span><h3>Kết quả đã duyệt</h3><p>Hướng dẫn xử trí chỉ hiển thị sau khi nhân viên y tế xác nhận.</p></article>
          <article><span class="feature-icon is-grey">${icon("user", 21)}</span><h3>Hồ sơ sức khoẻ</h3><p>Tiền sử bệnh, thuốc đang dùng và dị ứng — giúp phân loại chính xác hơn.</p></article>
        </div>

        <section class="history-card">
          <div class="head"><h2>Lịch sử phiên khai báo</h2></div>
          <div class="history-body" id="history-list"><p class="muted-copy">Đang tải lịch sử.</p></div>
        </section>

        <p class="fine-print">VMedTriage là công cụ hỗ trợ phân loại ưu tiên ban đầu, không phải chẩn đoán. Mọi hướng dẫn xử trí đều do nhân viên y tế xác nhận trước khi gửi.</p>
      </div>
    </main>
  </section>`;

  bindPatientNav(root, { navigate });
  root.querySelectorAll("[data-start]").forEach((button) => button.addEventListener("click", () => navigate("disclaimer")));
  root.querySelector("[data-guide]").addEventListener("click", openPatientUsageGuide);
  root.querySelector("[data-open-case]")?.addEventListener("click", () => navigate("patient-cases"));
  bindAccountMenu(root, { logout, onProfileSaved: () => renderPatientHome(root, { navigate, logout }) });
  loadPatientHistory(root, { navigate, logout });
}

/** Dashboard bệnh nhân: áp dụng bố cục hero + theo dõi ca, chỉ dùng trạng thái có trong hệ thống. */
export function renderPatientHome(root, { navigate, logout }) {
  const current = state.currentPatientCase;
  const name = state.user?.full_name || "bạn";
  root.innerHTML = patientDashboardShell("home", `
      <div class="patient-dashboard">
        <header class="patient-page-heading">
          <p class="eyebrow">Trang chủ</p>
          <h1>Chào ${escapeHtml(name)}</h1>
          <p>Theo dõi các ca đã gửi hoặc bắt đầu khai báo triệu chứng mới.</p>
        </header>
        <div class="patient-dashboard-top">
          <section class="patient-action-hero">
            <div class="patient-action-copy">
              <span class="patient-action-tag">${icon("chat", 15)} Trợ lý AI hỗ trợ sàng lọc triệu chứng</span>
              <h1>Bạn cảm thấy không khỏe ở đâu?</h1>
              <p>Mô tả triệu chứng bằng lời của bạn. Trợ lý sẽ hỏi thêm các thông tin cần thiết để nhân viên y tế đánh giá và gửi hướng dẫn phù hợp.</p>
              <div class="action-row">
                <button class="primary-button" type="button" data-start>${icon("chat", 18)}<span>Bắt đầu khai báo triệu chứng</span></button>
                <button class="secondary-button" type="button" data-guide>${icon("clipboard", 17)}<span>Hướng dẫn sử dụng</span></button>
              </div>
            </div>
            <div class="patient-action-footer">
              <p class="patient-action-note">${icon("shieldCheck", 16)} Mọi hướng dẫn xử trí đều được nhân viên y tế thẩm định trước khi gửi.</p>
              <span class="patient-action-availability"><i aria-hidden="true"></i>Tiếp nhận thông tin 24/7</span>
            </div>
          </section>
          <div id="open-case-slot">${openCaseCard(current)}</div>
        </div>

        <section class="history-card">
          <div class="head"><div><h2>Lịch sử phiên khai báo triệu chứng</h2><p>Danh sách các phiên sàng lọc trước đây của bạn.</p></div><button class="history-all-link" type="button" data-history-all>Xem tất cả lịch sử ${icon("chevronRight", 16)}</button></div>
          <div class="history-body" id="history-list"><p class="muted-copy">Đang tải lịch sử.</p></div>
        </section>
      </div>
  `);

  bindPatientNav(root, { navigate });
  bindPatientSidebar(root);
  bindPatientTheme(root);
  root.querySelectorAll("[data-start]").forEach((button) => button.addEventListener("click", () => navigate("disclaimer")));
  root.querySelector("[data-guide]").addEventListener("click", openPatientUsageGuide);
  root.querySelector("[data-open-case]")?.addEventListener("click", () => openCurrentCaseHistory(navigate));
  bindAccountMenu(root, { logout, onProfileSaved: () => renderPatientHome(root, { navigate, logout }) });
  bindQuickChatDock(root, { navigate });
  loadPatientHistory(root, { navigate, logout });
}

function openCaseCard(current) {
  if (!current) {
    return `<div class="open-case-card is-empty">
      <div class="head"><span class="section-label">Tiến trình hiện tại</span><span class="case-ready-status"><i aria-hidden="true"></i>Sẵn sàng</span></div>
      <div class="open-case-empty-state"><span class="open-case-illustration">${icon("clipboard", 25)}</span><strong>Chưa có ca đang chờ duyệt</strong><p>Khi gửi khai báo mới, tình trạng và phản hồi sẽ hiển thị tại đây.</p></div>
      <div id="recent-case-slot"></div>
      <div class="open-case-availability"><i aria-hidden="true"></i>Hệ thống tiếp nhận thông tin 24/7</div>
    </div>`;
  }
  const complaint = current.summary?.chief_complaint || symptomGroupLabels[current.structured_data?.symptom_group] || "Triệu chứng đang khai báo";
  const isEmergency = current.status === "escalated";
  const statusCopy = isEmergency
    ? "Tình trạng này cần được cấp cứu. Không chờ phản hồi trong ứng dụng."
    : current.status === "approved"
      ? "Phản hồi đã được nhân viên y tế gửi đến bạn."
      : current.status === "needs_more_info"
        ? "Nhân viên y tế đang chờ bạn phản hồi thêm thông tin."
        : current.status === "collecting_information"
          ? "Trợ lý đang thu thập thêm thông tin triệu chứng của bạn."
          : "Nhân viên y tế đang xem xét thông tin.";
  const reviewStarted = ["needs_nurse_review", "awaiting_approval"].includes(current.status);
  const handled = ["approved", "rejected"].includes(current.status);
  const progress = [
    ["Đã tiếp nhận", "is-done"],
    ["Trợ lý thu thập thông tin", reviewStarted || handled || isEmergency ? "is-done" : "is-active"],
    [isEmergency ? "Đã chuyển khẩn" : "Nhân viên y tế duyệt", handled || isEmergency ? "is-done" : reviewStarted ? "is-active" : ""],
  ];
  return `<div class="open-case-card">
    <div class="head"><span class="section-label">Tiến trình hiện tại</span><span class="status-badge ${statusClass(current.status)}">${statusLabels[current.status] || "Đang xử lý"}</span></div>
    <div class="title">${shortCaseId(current.case_id)} · ${escapeHtml(complaint)}</div>
    <p>Gửi lúc ${formatDate(current.created_at)} · ${statusCopy}</p>
    <ol class="open-case-progress" aria-label="Tiến trình xử lý ca">${progress.map(([label, state]) => `<li class="${state}"><i>${state === "is-done" ? icon("check", 12) : ""}</i><span>${label}</span></li>`).join("")}</ol>
    <div class="open-case-actions">${isEmergency ? `<a class="open-case-emergency-button" href="tel:115">${icon("phone", 16)} Gọi 115 ngay</a>` : ""}<button class="secondary-button open-case-detail-button" type="button" data-open-case>Xem chi tiết ca</button></div>
  </div>`;
}

async function loadPatientHistory(root, { navigate, logout }) {
  const list = root.querySelector("#history-list");
  try {
    const cases = await api("/api/v1/patient/history");
    const historyControl = root.querySelector("[data-history-all]");
    if (!cases.length) {
      historyControl.hidden = true;
      list.innerHTML = `<div class="patient-history-empty"><span>${icon("clipboard", 22)}</span><strong>Chưa có phiên khai báo</strong><p>Khi bạn gửi thông tin triệu chứng, lịch sử sàng lọc sẽ xuất hiện ở đây.</p></div>`;
      return;
    }
    const header = `<div class="history-head-row"><span class="col-label">Mã ca</span><span class="col-label">Ngày gửi</span><span class="col-label">Nhóm triệu chứng</span><span class="col-label">Mức ưu tiên</span><span class="col-label">Nhân viên duyệt</span><span class="col-label">Trạng thái</span><span aria-hidden="true"></span></div>`;
    let showingAll = false;
    const renderRows = () => {
      list.innerHTML = header + (showingAll ? cases : cases.slice(0, 5)).map(historyRow).join("");
      list.querySelectorAll("[data-history-case]").forEach((button) =>
        button.addEventListener("click", () => openPatientCase(button.dataset.historyCase, { navigate })),
      );
      list.querySelectorAll("[data-delete-case]").forEach((button) =>
        button.addEventListener("click", () => removePatientCase(button.dataset.deleteCase, button, () => renderPatientHome(root, { navigate, logout }))),
      );
    };
    // "Tiến trình hiện tại" phải là ca MỚI NHẤT, không phải ca cuối cùng người dùng bấm mở.
    // `state.currentPatientCase` giữ ca vừa xem (khôi phục cả từ `sessionStorage`), nên mở lại một ca
    // cũ trong lịch sử là trang chủ kẹt luôn ở ca đó. `/patient/history` đã sắp theo `updated_at`
    // giảm dần nên phần tử đầu chính là ca mới nhất.
    state.currentPatientCase = cases[0];
    const slot = root.querySelector("#open-case-slot");
    if (slot) {
      slot.innerHTML = openCaseCard(cases[0]);
      slot.querySelector("[data-open-case]")?.addEventListener("click", () => openPatientCase(cases[0].case_id, { navigate }));
    }
    historyControl.hidden = cases.length <= 5;
    historyControl.addEventListener("click", () => {
      showingAll = !showingAll;
      historyControl.innerHTML = `${showingAll ? "Thu gọn lịch sử" : "Xem tất cả lịch sử"} ${icon("chevronRight", 16)}`;
      renderRows();
    });
    renderRows();
    renderRecentCaseLink(root, cases[0], { navigate });
  } catch {
    list.innerHTML = `<p class="muted-copy">Không thể tải lịch sử phiên khai báo.</p>`;
  }
}

/** Mở một ca đã khai báo và sang màn chi tiết. Trước đây logic này bị chép ba lần (lịch sử trang
 *  chủ, link ca gần nhất, và giờ là màn "Kết quả của tôi") - ba bản chép là ba chỗ để quên
 *  `setActiveCase` hoặc quên khoá chỉ-đọc. */
async function openPatientCase(caseId, { navigate }, { fromCases = false } = {}) {
  try {
    state.currentPatientCase = await api(`/api/v1/cases/${caseId}`);
    setActiveCase(state.currentPatientCase.case_id);
    state.patientMessages = initialMessages(state.currentPatientCase);
    // Ca ĐANG MỞ (kể cả đang chat trực tiếp với điều dưỡng, "needs_more_info") vẫn phải gõ được -
    // chỉ khoá thành lịch sử chỉ-đọc khi ca đã thật sự kết thúc.
    state.viewingPatientHistory = completedStatuses.has(state.currentPatientCase.status);
    state.patientFromCases = fromCases;
    navigate("patient-chat");
  } catch (problem) {
    showToast(problem.message, true);
  }
}

function historyRow(item) {
  const priority = item.triage_proposal?.priority;
  const group = item.summary?.chief_complaint || symptomGroupLabels[item.structured_data?.symptom_group] || "Triệu chứng chung";
  const isEmergency = item.status === "escalated";
  const reviewer = isEmergency ? "Không chờ duyệt" : item.reviewed_by_name || (item.reviewed_at ? "Nhân viên y tế" : "Chờ duyệt");
  return `<div class="history-row">
    <span class="case-id">#${shortCaseId(item.case_id)}</span>
    <time class="case-date" datetime="${escapeHtml(item.created_at || "")}">${formatDate(item.created_at)}</time>
    <span class="group">${escapeHtml(group)}</span>
    <span class="priority-cell">${priority ? `<span class="priority-badge ${priorityClass(priority)}">${priorityLabels[priority] || priority}</span>` : `<span class="priority-badge is-routine">Chưa có</span>`}</span>
    <span class="reviewer ${isEmergency ? "is-emergency" : item.reviewed_by_name || item.reviewed_at ? "" : "is-pending"}">${escapeHtml(reviewer)}</span>
    <span class="status ${statusClass(item.status)}">${statusLabels[item.status] || item.status}</span>
    <span class="history-actions"><button class="history-detail" type="button" data-history-case="${item.case_id}">Chi tiết ${icon("chevronRight", 16)}</button><button class="history-delete" type="button" data-delete-case="${item.case_id}" aria-label="Xóa ca #${shortCaseId(item.case_id)} khỏi lịch sử" title="Xóa ca">${icon("trash", 17)}</button></span>
  </div>`;
}

async function removePatientCase(caseId, button, onRemoved) {
  const confirmed = window.confirm("Xóa ca này khỏi lịch sử của bạn? Bản ghi vẫn được lưu an toàn để nhân viên y tế đối chiếu khi cần.");
  if (!confirmed) return;
  button.disabled = true;
  try {
    await api(`/api/v1/cases/${caseId}`, { method: "DELETE" });
    showToast("Đã xóa ca khỏi lịch sử của bạn.");
    onRemoved();
  } catch (problem) {
    button.disabled = false;
    showToast(problem.message || "Không thể xóa ca lúc này.", true);
  }
}

function renderRecentCaseLink(root, item, { navigate }) {
  const slot = root.querySelector("#recent-case-slot");
  if (!slot || !item) return;
  const group = item.summary?.chief_complaint || symptomGroupLabels[item.structured_data?.symptom_group] || "Ca khai báo gần nhất";
  slot.innerHTML = `<button class="recent-case-link" type="button" data-recent-case="${item.case_id}"><span><small>Ca gần nhất</small><strong>#${shortCaseId(item.case_id)} · ${escapeHtml(group)}</strong></span><span>Chi tiết ${icon("chevronRight", 15)}</span></button>`;
  slot.querySelector("[data-recent-case]").addEventListener("click", () => openPatientCase(item.case_id, { navigate }));
}

/**
 * W-09 — "Kết quả của tôi": TOÀN BỘ ca người bệnh đã khai báo, gom về một chỗ.
 *
 * Ba trạng thái lọc bám đúng câu hỏi người bệnh thật sự hỏi ("ca của tôi xong chưa?"), chứ không
 * bám vocab `CaseStatus` của backend - `approved`/`rejected`/`withdrawn` với người bệnh đều là
 * "nhân viên y tế đã xem xong", còn `collecting_information` và `needs_nurse_review` đều là "chưa".
 */
const caseFilters = {
  all: { label: "Tất cả", includes: () => true, empty: "Bạn chưa khai báo ca nào." },
  settled: {
    label: "Đã được xác nhận",
    includes: (item) => completedStatuses.has(item.status),
    empty: "Chưa có ca nào được nhân viên y tế xác nhận xong.",
  },
  open: {
    label: "Chưa được xác nhận",
    includes: (item) => !completedStatuses.has(item.status),
    empty: "Không có ca nào đang khai báo hoặc đang chờ xác nhận.",
  },
};

export function renderPatientCases(root, { navigate, logout }) {
  root.innerHTML = patientDashboardShell("cases", `
      <div class="cases-page patient-cases-page">
        <div class="queue-head">
          <div>
            <h1>Kết quả của tôi</h1>
            <p>Toàn bộ ca bạn đã khai báo. Chọn một ca để xem lại hội thoại và kết quả phân loại.</p>
          </div>
          <button class="primary-button" type="button" data-start>${icon("chat", 17)}<span>Khai báo ca mới</span></button>
        </div>

        <div class="queue-toolbar">
          <div class="filter-chips" role="group" aria-label="Lọc theo trạng thái xác nhận">
            ${Object.entries(caseFilters)
              .map(([key, filter], index) => `<button class="filter-chip${index === 0 ? " is-active" : ""}" type="button" data-case-filter="${key}"><span>${filter.label}</span><b data-count="${key}">0</b></button>`)
              .join("")}
          </div>
        </div>

        <section class="history-card">
          <div class="history-body" id="cases-list"><p class="muted-copy">Đang tải danh sách ca.</p></div>
        </section>
      </div>
  `);

  bindPatientNav(root, { navigate });
  bindPatientSidebar(root);
  bindPatientTheme(root);
  bindAccountMenu(root, { logout, onProfileSaved: () => renderPatientCases(root, { navigate, logout }) });
  bindQuickChatDock(root, { navigate });
  root.querySelectorAll("[data-start]").forEach((button) => button.addEventListener("click", () => navigate("disclaimer")));
  root.dataset.caseFilter = "all";
  root.querySelectorAll("[data-case-filter]").forEach((button) =>
    button.addEventListener("click", () => {
      root.querySelectorAll("[data-case-filter]").forEach((item) => item.classList.toggle("is-active", item === button));
      root.dataset.caseFilter = button.dataset.caseFilter;
      paintPatientCases(root, { navigate, logout });
    }),
  );
  loadPatientCases(root, { navigate, logout });
}

const healthConditionOptions = [
  ["tim_mach", "Tim mạch"],
  ["ho_hap", "Hô hấp"],
  ["tieu_duong", "Tiểu đường"],
  ["than", "Thận"],
  ["gan", "Gan"],
  ["ung_thu", "Ung thư"],
  ["suy_giam_mien_dich", "Suy giảm miễn dịch"],
  ["khac", "Khác"],
];

const healthStatuses = {
  unknown: "Chưa xác nhận",
  none: "Không ghi nhận",
  yes: "Đã cập nhật",
};

function healthText(value) {
  const lines = String(value || "").split("\n").map((item) => item.trim()).filter(Boolean);
  return lines.length ? `<ul class="health-detail-list">${lines.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : "";
}

function healthInlineDetail(value) {
  const text = String(value || "").trim();
  return text ? `<em>${escapeHtml(text).replaceAll("\n", " · ")}</em>` : "";
}

function healthStatus(status) {
  const normalized = healthStatuses[status] ? status : "unknown";
  return `<span class="health-status is-${normalized}">${healthStatuses[normalized]}</span>`;
}

function healthProfileContent(profile) {
  const conditions = Array.isArray(profile.chronic_conditions) ? profile.chronic_conditions : [];
  const conditionLabels = conditions.map((value) => healthConditionOptions.find(([key]) => key === value)?.[1]).filter(Boolean);
  const allergyCopy = profile.allergy_status === "yes"
    ? healthText(profile.allergies) || `<p class="health-card-empty">Bạn có thể bổ sung chất gây dị ứng hoặc phản ứng đã từng gặp.</p>`
    : `<p class="health-card-empty">${profile.allergy_status === "none" ? "Bạn chưa ghi nhận dị ứng cần lưu ý." : "Chưa có thông tin dị ứng được xác nhận."}</p>`;
  const medicationCopy = healthText(profile.current_medications) || `<p class="health-card-empty">Chưa thêm thuốc đang dùng thường xuyên.</p>`;
  const lastConfirmed = profile.confirmed_at ? `Xác nhận gần nhất: ${formatDate(profile.confirmed_at)}` : "Chưa có lần xác nhận";
  return `<div class="health-profile-grid">
    <article class="health-profile-card">
      <div class="health-card-heading"><span class="feature-icon is-allergy">${icon("allergy", 22)}</span><div><h2>Dị ứng</h2>${healthStatus(profile.allergy_status)}</div></div>
      <div class="health-card-body">${allergyCopy}</div>
      <button class="secondary-button health-action-button" type="button" data-health-edit="allergies">${profile.allergy_status === "unknown" ? "Cập nhật" : "Chỉnh sửa"}</button>
    </article>
    <article class="health-profile-card">
      <div class="health-card-heading"><span class="feature-icon is-condition">${icon("stethoscope", 22)}</span><div><h2>Bệnh nền</h2>${healthStatus(conditionLabels.length ? "yes" : "unknown")}</div></div>
      <div class="health-card-body">${conditionLabels.length ? `<div class="health-chip-list">${conditionLabels.map((label) => `<span>${escapeHtml(label)}</span>`).join("")}</div>` : `<p class="health-card-empty">Chưa có bệnh nền được khai báo.</p>`}</div>
      ${profile.conditions_note ? `<p class="health-card-note">${healthInlineDetail(profile.conditions_note)}</p>` : ""}
      <button class="secondary-button health-action-button" type="button" data-health-edit="conditions">${conditionLabels.length ? "Chỉnh sửa" : "Cập nhật"}</button>
    </article>
    <article class="health-profile-card">
      <div class="health-card-heading"><span class="feature-icon is-medication">${icon("pill", 22)}</span><div><h2>Thuốc đang dùng</h2>${healthStatus(profile.current_medications ? "yes" : "unknown")}</div></div>
      <div class="health-card-body">${medicationCopy}</div>
      <button class="secondary-button health-action-button" type="button" data-health-edit="medications">${profile.current_medications ? "Chỉnh sửa" : "Thêm thuốc"}</button>
    </article>
    <article class="health-profile-card">
      <div class="health-card-heading"><span class="feature-icon is-recent">${icon("calendarCheck", 22)}</span><div><h2>Thông tin gần đây</h2>${healthStatus(profile.recent_care_status === "yes" || profile.pregnancy_status === "yes" ? "yes" : profile.recent_care_status === "none" && profile.pregnancy_status === "none" ? "none" : "unknown")}</div></div>
      <div class="health-recent-rows">
        <div class="health-recent-row"><span><strong>Nhập viện hoặc phẫu thuật</strong><small>Trong 30 ngày gần đây</small></span>${healthStatus(profile.recent_care_status)}</div>
        <div class="health-recent-row"><span><strong>Thai kỳ hoặc hậu sản</strong><small>Đang mang thai hoặc sinh trong 6 tuần qua</small></span>${healthStatus(profile.pregnancy_status)}</div>
      </div>
      ${profile.recent_note ? `<p class="health-recent-note">${healthInlineDetail(profile.recent_note)}</p>` : ""}
      <button class="secondary-button health-action-button" type="button" data-health-edit="recent">Cập nhật</button>
    </article>
  </div>
  <aside class="health-profile-trust">${icon("lock", 19)}<div><strong>Dữ liệu tự khai, chưa tự đưa vào ca sàng lọc</strong><span>Nhân viên y tế không xem được hồ sơ này trong bản hiện tại. Khi mở ca mới, hệ thống vẫn sẽ hỏi và cần bạn xác nhận thông tin liên quan.</span></div><small>${lastConfirmed}</small></aside>`;
}

const healthEditCopy = {
  allergies: { title: "Cập nhật dị ứng", heading: "Dị ứng" },
  conditions: { title: "Cập nhật bệnh nền", heading: "Bệnh nền đang điều trị" },
  medications: { title: "Cập nhật thuốc đang dùng", heading: "Thuốc đang dùng" },
  recent: { title: "Cập nhật thông tin gần đây", heading: "Thông tin gần đây" },
};

function healthFormSection(profile, section) {
  const checked = new Set(profile.chronic_conditions || []);
  const selected = (status, value) => status === value ? " selected" : "";
  if (section === "allergies") return `<section><h3>Dị ứng</h3><label>Bạn có dị ứng hoặc phản ứng cần lưu ý không?<select name="allergy_status"><option value="unknown"${selected(profile.allergy_status, "unknown")}>Không rõ / chưa xác nhận</option><option value="none"${selected(profile.allergy_status, "none")}>Không ghi nhận</option><option value="yes"${selected(profile.allergy_status, "yes")}>Có</option></select></label><label>Chất gây dị ứng hoặc phản ứng từng gặp <span>(nếu có)</span><textarea name="allergies" rows="3" maxlength="1000" placeholder="Ví dụ: thuốc hoặc thực phẩm, phản ứng từng gặp">${escapeHtml(profile.allergies || "")}</textarea></label></section>`;
  if (section === "conditions") return `<section><h3>Bệnh nền đang điều trị</h3><p>Chọn các nhóm phù hợp; đây là thông tin tự khai, không phải chẩn đoán của hệ thống.</p><div class="health-checkbox-grid">${healthConditionOptions.map(([value, label]) => `<label><input type="checkbox" name="chronic_conditions" value="${value}"${checked.has(value) ? " checked" : ""} />${label}</label>`).join("")}</div><label>Ghi chú bổ sung <span>(nếu có, nhất là khi chọn “Khác”)</span><textarea name="conditions_note" rows="2" maxlength="1000" placeholder="Ghi rõ tình trạng hoặc thông tin bạn muốn bổ sung">${escapeHtml(profile.conditions_note || "")}</textarea></label></section>`;
  if (section === "medications") return `<section><h3>Thuốc đang dùng</h3><label>Tên thuốc đang dùng thường xuyên <span>(nếu có)</span><textarea name="current_medications" rows="3" maxlength="1000" placeholder="Mỗi thuốc một dòng">${escapeHtml(profile.current_medications || "")}</textarea></label></section>`;
  return `<section><h3>Thông tin gần đây</h3><label>Nhập viện / phẫu thuật trong 30 ngày gần đây<select name="recent_care_status"><option value="unknown"${selected(profile.recent_care_status, "unknown")}>Không rõ / chưa xác nhận</option><option value="none"${selected(profile.recent_care_status, "none")}>Không có</option><option value="yes"${selected(profile.recent_care_status, "yes")}>Có</option></select></label><label>Thai kỳ / hậu sản<select name="pregnancy_status"><option value="unknown"${selected(profile.pregnancy_status, "unknown")}>Không rõ / chưa xác nhận</option><option value="none"${selected(profile.pregnancy_status, "none")}>Không áp dụng / không có</option><option value="yes"${selected(profile.pregnancy_status, "yes")}>Có</option></select></label><label>Ghi chú bổ sung <span>(nếu có, ví dụ: thời điểm phẫu thuật, lý do nhập viện hoặc tuần thai)</span><textarea name="recent_note" rows="3" maxlength="1000" placeholder="Ghi rõ thông tin bạn muốn bổ sung">${escapeHtml(profile.recent_note || "")}</textarea></label></section>`;
}

function healthProfilePayload(profile, section, formData) {
  const payload = {
    allergy_status: profile.allergy_status || "unknown",
    allergies: profile.allergies || null,
    chronic_conditions: Array.isArray(profile.chronic_conditions) ? profile.chronic_conditions : [],
    conditions_note: profile.conditions_note || null,
    current_medications: profile.current_medications || null,
    recent_care_status: profile.recent_care_status || "unknown",
    pregnancy_status: profile.pregnancy_status || "unknown",
    recent_note: profile.recent_note || null,
  };
  if (section === "allergies") {
    payload.allergy_status = formData.get("allergy_status");
    payload.allergies = formData.get("allergies");
  }
  if (section === "conditions") {
    payload.chronic_conditions = formData.getAll("chronic_conditions");
    payload.conditions_note = formData.get("conditions_note");
  }
  if (section === "medications") payload.current_medications = formData.get("current_medications");
  if (section === "recent") {
    payload.recent_care_status = formData.get("recent_care_status");
    payload.pregnancy_status = formData.get("pregnancy_status");
    payload.recent_note = formData.get("recent_note");
  }
  return payload;
}

function healthOverviewCard(title, value) {
  return `<article class="health-overview-card"><h3>${title}</h3><div>${value}</div></article>`;
}

function healthOverviewContent(profile) {
  const conditions = (profile.chronic_conditions || []).map((value) => healthConditionOptions.find(([key]) => key === value)?.[1]).filter(Boolean);
  const allergies = profile.allergy_status === "yes" ? healthText(profile.allergies) || "Có dị ứng, chưa ghi rõ chi tiết." : profile.allergy_status === "none" ? "Không ghi nhận dị ứng cần lưu ý." : "Chưa xác nhận.";
  const medications = healthText(profile.current_medications) || "Chưa ghi nhận thuốc đang dùng thường xuyên.";
  const conditionDetail = conditions.length ? `<div class="health-chip-list">${conditions.map((label) => `<span>${escapeHtml(label)}</span>`).join("")}</div>${profile.conditions_note ? `<p>${healthInlineDetail(profile.conditions_note)}</p>` : ""}` : profile.conditions_note ? `<p>${healthInlineDetail(profile.conditions_note)}</p>` : "Chưa có bệnh nền được khai báo.";
  const recentDetail = `<dl class="health-overview-list"><div><dt>Nhập viện hoặc phẫu thuật</dt><dd>${healthStatuses[profile.recent_care_status] || healthStatuses.unknown}</dd></div><div><dt>Thai kỳ hoặc hậu sản</dt><dd>${healthStatuses[profile.pregnancy_status] || healthStatuses.unknown}</dd></div></dl>${profile.recent_note ? `<p>${healthInlineDetail(profile.recent_note)}</p>` : ""}`;
  return `<div class="health-overview-grid">${healthOverviewCard("Dị ứng", allergies)}${healthOverviewCard("Bệnh nền", conditionDetail)}${healthOverviewCard("Thuốc đang dùng", medications)}${healthOverviewCard("Thông tin gần đây", recentDetail)}</div>`;
}

function openHealthProfileOverview(profile) {
  const dialog = document.createElement("div");
  dialog.className = "health-profile-dialog";
  dialog.innerHTML = `<div class="profile-backdrop" data-close-health></div><section class="health-profile-modal health-overview-modal" role="dialog" aria-modal="true" aria-labelledby="health-profile-title"><button class="profile-close" type="button" data-close-health aria-label="Đóng">×</button><p class="eyebrow">Hồ sơ sức khỏe</p><h2 id="health-profile-title">Hồ sơ sức khỏe tổng thể</h2><p>Đây là bản xem toàn bộ thông tin tự khai. Để thay đổi dữ liệu, hãy đóng cửa sổ này và chọn “Cập nhật” tại đúng phần cần sửa.</p>${healthOverviewContent(profile)}<div class="health-profile-actions"><button class="secondary-button" type="button" data-close-health>Đóng</button></div></section>`;
  document.body.append(dialog);
  dialog.querySelectorAll("[data-close-health]").forEach((button) => button.addEventListener("click", () => dialog.remove()));
}

function openHealthProfileDialog(profile, focusSection, { onSaved }) {
  const copy = healthEditCopy[focusSection] || healthEditCopy.allergies;
  const dialog = document.createElement("div");
  dialog.className = "health-profile-dialog";
  dialog.innerHTML = `<div class="profile-backdrop" data-close-health></div><section class="health-profile-modal" role="dialog" aria-modal="true" aria-labelledby="health-profile-title"><button class="profile-close" type="button" data-close-health aria-label="Đóng">×</button><p class="eyebrow">Hồ sơ sức khỏe</p><h2 id="health-profile-title">${copy.title}</h2><p>Bạn chỉ đang cập nhật mục “${copy.heading}”. Các phần còn lại của hồ sơ sẽ được giữ nguyên.</p><form class="health-profile-form">${healthFormSection(profile, focusSection)}<p class="form-error" role="alert"></p><div class="health-profile-actions"><button class="secondary-button" type="button" data-close-health>Hủy</button><button class="primary-button" type="submit">Lưu thông tin</button></div></form></section>`;
  document.body.append(dialog);
  const close = () => dialog.remove();
  dialog.querySelectorAll("[data-close-health]").forEach((button) => button.addEventListener("click", close));
  dialog.querySelector(".health-profile-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const error = form.querySelector(".form-error");
    const submit = form.querySelector("button[type=submit]");
    const formData = new FormData(form);
    const payload = healthProfilePayload(profile, focusSection, formData);
    error.textContent = "";
    submit.disabled = true;
    submit.textContent = "Đang lưu";
    try {
      const saved = await api("/api/v1/me/health-profile", { method: "PUT", body: JSON.stringify(payload) });
      close();
      showToast("Đã lưu hồ sơ sức khỏe.");
      onSaved(saved);
    } catch (problem) {
      error.textContent = problem.message || "Không thể lưu hồ sơ sức khỏe.";
      submit.disabled = false;
      submit.textContent = "Lưu thông tin";
    }
  });
}

export function renderPatientHealth(root, { navigate, logout }) {
  root.innerHTML = patientDashboardShell("health", `<div class="patient-health-page"><header class="patient-page-heading health-page-heading"><div><p class="eyebrow">Hồ sơ sức khỏe</p><h1>Thông tin sức khỏe của bạn</h1><p>Cập nhật các thông tin tự khai để bạn có thể kiểm tra và xác nhận lại khi cần.</p></div><button class="secondary-button health-overview-button" type="button" data-health-overview disabled>${icon("eye", 16)}<span>Xem hồ sơ tổng thể</span></button></header><div id="health-profile-content" class="health-profile-loading">Đang tải hồ sơ sức khỏe.</div></div>`);
  bindPatientNav(root, { navigate });
  bindPatientSidebar(root);
  bindPatientTheme(root);
  bindAccountMenu(root, { logout, onProfileSaved: () => renderPatientHealth(root, { navigate, logout }) });
  bindQuickChatDock(root, { navigate });
  const content = root.querySelector("#health-profile-content");
  api("/api/v1/me/health-profile")
    .then((profile) => {
      const renderProfile = (nextProfile) => {
        content.classList.remove("health-profile-loading");
        content.innerHTML = healthProfileContent(nextProfile);
        content.querySelectorAll("[data-health-edit]").forEach((button) => button.addEventListener("click", () => {
          openHealthProfileDialog(nextProfile, button.dataset.healthEdit, { onSaved: renderProfile });
        }));
        const overview = root.querySelector("[data-health-overview]");
        overview.disabled = false;
        overview.onclick = () => openHealthProfileOverview(nextProfile);
      };
      renderProfile(profile);
    })
    .catch(() => {
      content.innerHTML = `<div class="health-profile-error"><strong>Không thể tải hồ sơ sức khỏe.</strong><p>Hãy thử tải lại trang sau ít phút.</p></div>`;
    });
}

async function loadPatientCases(root, { navigate, logout }) {
  try {
    state.patientCases = await api("/api/v1/patient/history");
  } catch {
    root.querySelector("#cases-list").innerHTML = `<p class="muted-copy">Không thể tải danh sách ca.</p>`;
    return;
  }
  paintPatientCases(root, { navigate, logout });
}

function paintPatientCases(root, { navigate, logout }) {
  const cases = state.patientCases || [];
  for (const [key, filter] of Object.entries(caseFilters)) {
    root.querySelector(`[data-count="${key}"]`).textContent = cases.filter(filter.includes).length;
  }

  const filter = caseFilters[root.dataset.caseFilter] || caseFilters.all;
  const rows = cases.filter(filter.includes);
  const list = root.querySelector("#cases-list");

  if (!rows.length) {
    list.innerHTML = `<div class="patient-history-empty"><span>${icon("clipboard", 24)}</span><strong>${escapeHtml(filter.empty)}</strong><p>Ca bạn khai báo sẽ xuất hiện ở đây cùng kết quả phân loại.</p><button class="secondary-button" type="button" data-empty-start>Bắt đầu khai báo</button></div>`;
    list.querySelector("[data-empty-start]").addEventListener("click", () => navigate("disclaimer"));
    return;
  }

  const header = `<div class="history-head-row"><span class="col-label">Mã ca</span><span class="col-label">Ngày gửi</span><span class="col-label">Nhóm triệu chứng</span><span class="col-label">Mức ưu tiên</span><span class="col-label">Nhân viên duyệt</span><span class="col-label">Trạng thái</span><span aria-hidden="true"></span></div>`;
  list.innerHTML = header + rows.map(historyRow).join("");
  list.querySelectorAll("[data-history-case]").forEach((button) =>
    button.addEventListener("click", () => openPatientCase(button.dataset.historyCase, { navigate }, { fromCases: true })),
  );
  list.querySelectorAll("[data-delete-case]").forEach((button) =>
    button.addEventListener("click", () => removePatientCase(button.dataset.deleteCase, button, () => renderPatientCases(root, { navigate, logout }))),
  );
}

/** W-02 — disclaimer bắt buộc mỗi phiên khai báo mới, không có đường bỏ qua ngoài nút CTA. */
function openCurrentCaseHistory(navigate) {
  if (!state.currentPatientCase) return;
  state.patientMessages = initialMessages(state.currentPatientCase);
  state.viewingPatientHistory = completedStatuses.has(state.currentPatientCase.status);
  navigate("patient-chat");
}

export function renderDisclaimer(root, { navigate, onAccept, logout }) {
  root.innerHTML = patientDashboardShell("start", `
    <div class="patient-flow-page">
      <header class="patient-page-heading patient-flow-heading"><div><p class="eyebrow">Bước 1 / 3</p><h1>Trước khi khai báo</h1><p>Đọc các lưu ý an toàn trước khi bắt đầu trao đổi về triệu chứng.</p></div></header>
    <div class="disclaimer-wrap">
      <div class="disclaimer-card">
        <div class="disclaimer-head">
          <span class="disclaimer-icon">${icon("info", 28)}</span>
          <div><h1>Thông tin quan trọng</h1><p>Vui lòng đọc trước khi bắt đầu khai báo triệu chứng.</p></div>
        </div>
        <ol class="rule-list">
          <li><span class="rule-index">1</span><span>${AI_SCOPE_VI.replace("mức độ khẩn cấp", "<b>mức độ khẩn cấp</b>")}</span></li>
          <li><span class="rule-index">2</span><span>Mọi đề xuất đều được <b>nhân viên y tế xác nhận</b> trước khi gửi cho bạn.</span></li>
          <li><span class="rule-index">3</span><span>Trường hợp khẩn cấp, hãy <b>gọi 115 ngay</b> thay vì chờ trong ứng dụng.</span></li>
        </ol>
        <div class="action-row">
          <button class="primary-button" type="button" data-accept>Tôi đã hiểu, bắt đầu</button>
          <button class="secondary-button" type="button" data-back>Quay lại</button>
        </div>
      </div>
    </div>
    </div>
  `, { quickChat: false });
  bindPatientNav(root, { navigate });
  bindPatientSidebar(root);
  bindPatientTheme(root);
  bindAccountMenu(root, { logout, onProfileSaved: () => renderDisclaimer(root, { navigate, onAccept, logout }) });
  root.querySelector("[data-accept]").addEventListener("click", onAccept);
  root.querySelector("[data-back]").addEventListener("click", () => navigate("patient-home"));
}

export function startPatientCase(root, { navigate, logout, fresh = false }) {
  if (fresh) {
    setActiveCase(null);
    state.currentPatientCase = null;
    state.patientMessages = [];
    state.summaryConfirmed = false;
    state.patientForcedComplete = false;
    state.redFlagShownCaseId = null;
  }
  state.viewingPatientHistory = false;
  renderPatientChat(root, { navigate, logout });
}

/** W-03 — khai báo triệu chứng. Chat bên trái, cột phải là nhóm đã nhận diện + tiến độ checklist. */
export function renderPatientChat(root, { navigate, logout }) {
  const current = state.currentPatientCase;
  const messages = state.patientMessages.length ? state.patientMessages : initialMessages(current);
  const viewingHistory = state.viewingPatientHistory;
  // `state.patientBusy` phải đi vào markup chứ không chỉ chặn double-submit trong `submitMessage`:
  // nếu không, ô nhập và nút Gửi vẫn bấm được trong lúc chờ và người dùng gõ tiếp mà không hiểu vì
  // sao không có gì xảy ra. Một nguồn sự thật duy nhất cho trạng thái chờ.
  const busy = state.patientBusy ? " disabled" : "";
  const isNewConversation = !current && messages.length === 1 && messages[0]?.role === "agent";
  const starterPrompts = ["Tôi bắt đầu thấy khó chịu từ...", "Triệu chứng của tôi là...", "Điều khiến tôi lo nhất là..."];
  const chatTitle = viewingHistory || state.patientFromCases ? `Chi tiết ca${current ? ` · ${shortCaseId(current.case_id)}` : ""}` : "Khai báo triệu chứng";
  const chatIntro = viewingHistory || state.patientFromCases
    ? "Xem lại cuộc trao đổi và thông tin đã gửi trong ca này."
    : "Mô tả triệu chứng theo cách của bạn; trợ lý sẽ hỏi thêm những thông tin cần thiết.";
  const isCaseDetail = viewingHistory || state.patientFromCases;
  const caseDetailState = viewingHistory ? "Lịch sử đã lưu" : "Đang cần phản hồi";
  root.innerHTML = patientDashboardShell(viewingHistory || state.patientFromCases ? "cases" : "start", `
    <div class="patient-flow-page patient-chat-page">
      <header class="patient-page-heading patient-flow-heading">
        <div><p class="eyebrow">${viewingHistory || state.patientFromCases ? "Kết quả của tôi" : "Bước 2 / 3"}</p><h1>${chatTitle}</h1><p>${chatIntro}</p></div>
        ${state.patientFromCases ? `<button class="back-button" type="button" data-cases-back>${icon("chevronLeft", 15)}<span>Kết quả của tôi</span></button>` : ""}
      </header>
      <div class="chat-grid">
        <section class="chat-panel${isCaseDetail ? " is-case-detail" : ""}" aria-label="Hội thoại với trợ lý">
          <header class="chat-session-head"><span class="chat-session-icon">${icon("chat", 19)}</span><span class="chat-session-copy"><strong>Trao đổi về triệu chứng</strong><small>${isCaseDetail ? "Thông tin đã gửi trong ca này." : "Chia sẻ theo cách tự nhiên, trợ lý sẽ hỏi thêm khi cần."}</small></span>${isCaseDetail ? `<span class="chat-session-state${viewingHistory ? " is-readonly" : ""}">${icon(viewingHistory ? "lock" : "clock", 14)}${caseDetailState}</span>` : ""}</header>
          <div class="capability-strip">${icon("info", 15)}<span>${AI_SCOPE_VI}</span></div>
          <div class="chat-log${isNewConversation ? " is-welcome" : ""}" id="chat-log">${isNewConversation ? `<div class="chat-welcome"><span class="chat-welcome-icon">${icon("ask", 24)}</span><h2>Bạn đang cảm thấy thế nào?</h2><p>Hãy bắt đầu bằng điều khó chịu nhất bạn đang gặp. Bạn không cần dùng từ chuyên môn.</p><div class="chat-starter-list">${starterPrompts.map((prompt) => `<button type="button" data-chat-starter="${escapeHtml(prompt)}">${icon("chevronRight", 14)}<span>${escapeHtml(prompt)}</span></button>`).join("")}</div></div>` : messages.map(messageMarkup).join("")}</div>
          ${viewingHistory ? `<div class="chat-history-note">${icon("lock", 17)}<span>Đây là lịch sử trao đổi đã lưu của ca này. Bạn không thể gửi thêm tin nhắn tại đây.</span><button class="link-button" type="button" data-history-back>Quay lại Kết quả của tôi</button></div>`
          : state.patientForcedComplete ? `<div class="chat-history-note">${icon("lock", 17)}<span>Bạn đã xác nhận khai báo xong triệu chứng. Thông tin đã được chuyển cho nhân viên y tế, bạn không thể gửi thêm tin nhắn tại đây.</span></div>`
          : `<form id="chat-form" class="chat-composer">
            <label class="sr-only" for="patient-message">Mô tả triệu chứng</label>
            <button class="voice-input-button" type="button" data-speech-to-text aria-pressed="false" aria-label="Nhập bằng giọng nói" title="Nhập bằng giọng nói"${busy}><svg class="ico" width="19" height="19" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"><rect x="9" y="3" width="6" height="11" rx="3" stroke="currentColor" stroke-width="1.7"/><path d="M6.4 11.2a5.6 5.6 0 0 0 11.2 0M12 16.8v3.7M8.7 20.5h6.6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg></button>
            <textarea id="patient-message" name="message" rows="1" maxlength="5000" placeholder="Mô tả triệu chứng của bạn..." aria-describedby="voice-input-hint"${busy}></textarea>
            <button class="primary-button" type="submit"${busy}>${icon("send", 18)}<span>${state.patientBusy ? "Đang gửi…" : "Gửi"}</span></button>
            <span class="voice-input-hint" id="voice-input-hint" role="status" aria-live="polite">Bấm micro để nhập bằng giọng nói; hãy kiểm tra nội dung trước khi gửi.</span>
            <p class="form-error" id="chat-error" role="alert"></p>
          </form>
          <button class="secondary-button btn-sm" type="button" id="declare-done-button"${busy}>${icon("check", 16)}<span>Tôi đã khai báo hết triệu chứng, không còn bất thường nào khác</span></button>`}
        </section>

        <aside class="chat-side">
          <section class="side-card">
            <span class="section-label">Nhóm đã nhận diện</span>
            <div class="detected-group">${icon("check", 18)}<span>${escapeHtml(detectedGroup(current))}</span></div>
          </section>
          ${caseStatusCard(current)}
          <div class="note-card">${icon("lock", 18)}<span>Thông tin chỉ dùng để phân loại mức ưu tiên và được nhân viên y tế xem xét.</span></div>
        </aside>
      </div>
    </div>
  `, { quickChat: false });

  bindPatientNav(root, { navigate });
  bindPatientSidebar(root);
  bindPatientTheme(root);
  bindAccountMenu(root, { logout, onProfileSaved: () => renderPatientChat(root, { navigate, logout }) });
  root.querySelector("[data-history-back]")?.addEventListener("click", () => navigate("patient-cases"));
  root.querySelector("[data-cases-back]")?.addEventListener("click", () => navigate("patient-cases"));
  root.querySelectorAll("[data-chat-starter]").forEach((button) => button.addEventListener("click", () => {
    const input = root.querySelector("#patient-message");
    if (!input || input.disabled) return;
    input.value = button.dataset.chatStarter;
    input.focus();
  }));
  const form = root.querySelector("#chat-form");
  const stopSpeechToText = bindSpeechToText(form);
  form?.addEventListener("submit", (event) => {
    stopSpeechToText();
    submitMessage(event, root, { navigate, logout });
  });
  // Enter gửi, Shift+Enter xuống dòng — đúng hành vi bản thiết kế mô tả cho ô nhập.
  root.querySelector("#patient-message")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); }
  });
  root.querySelectorAll("[data-confirm]").forEach((button) => button.addEventListener("click", () => confirmSummary(root, { navigate, logout }, button.dataset.confirm === "yes")));
  root.querySelector("#declare-done-button")?.addEventListener("click", () => declareDone(root, { navigate, logout }));
  root.querySelector("[data-goto-result]")?.addEventListener("click", () => navigate("patient-result"));
  // Không focus khi đang khoá: focus vào ô disabled là no-op ở mọi trình duyệt, nhưng vẫn kéo màn
  // hình về composer trên mobile giữa lúc người dùng đang đọc câu trả lời.
  if (!state.patientBusy && !viewingHistory && !state.patientForcedComplete) root.querySelector("#patient-message")?.focus();
  scrollChat(root);
  if (!viewingHistory) startCasePolling(root, { navigate, logout }, renderPatientChat);
}

function detectedGroup(current) {
  const group = current?.structured_data?.symptom_group;
  if (group && group !== "general") return symptomGroupLabels[group] || group;
  return current?.summary?.chief_complaint || "Đang xác định";
}

/** SpeechRecognition chỉ tạo văn bản nháp trong ô chat; người bệnh vẫn phải tự kiểm tra rồi bấm
 * Gửi. Không thu hoặc lưu audio ở ứng dụng. */
function bindSpeechToText(form) {
  const button = form?.querySelector("[data-speech-to-text]");
  const input = form?.querySelector("#patient-message");
  const status = form?.querySelector("#voice-input-hint");
  if (!button || !input || !status) return () => {};

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    button.disabled = true;
    button.title = "Trình duyệt này chưa hỗ trợ nhập bằng giọng nói";
    status.textContent = "Trình duyệt này chưa hỗ trợ nhập bằng giọng nói. Bạn vẫn có thể gõ nội dung.";
    return () => {};
  }

  let recognition;
  let listening = false;
  let baseText = "";
  let receivedSpeech = false;

  const setListening = (isListening) => {
    listening = isListening;
    button.classList.toggle("is-listening", isListening);
    button.setAttribute("aria-pressed", String(isListening));
    button.setAttribute("aria-label", isListening ? "Dừng nhập bằng giọng nói" : "Nhập bằng giọng nói");
    button.title = isListening ? "Dừng ghi âm" : "Nhập bằng giọng nói";
  };

  const stop = () => {
    if (recognition && listening) recognition.stop();
  };

  button.addEventListener("click", () => {
    if (listening) {
      stop();
      return;
    }

    baseText = input.value.trim();
    receivedSpeech = false;
    recognition = new SpeechRecognition();
    recognition.lang = "vi-VN";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => {
      setListening(true);
      status.textContent = "Đang nghe… Bấm lại micro để dừng.";
    };
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0]?.transcript || "")
        .join(" ")
        .trim();
      receivedSpeech = Boolean(transcript);
      input.value = [baseText, transcript].filter(Boolean).join(" ");
      status.textContent = "Đang chuyển giọng nói thành văn bản…";
    };
    recognition.onerror = (event) => {
      const errorMessages = {
        "not-allowed": "Bạn chưa cho phép dùng micro. Hãy cấp quyền micro rồi thử lại.",
        "no-speech": "Không nghe thấy giọng nói. Vui lòng thử lại.",
        network: "Không thể kết nối dịch vụ nhận diện giọng nói. Vui lòng thử lại.",
      };
      status.textContent = errorMessages[event.error] || "Không thể nhận diện giọng nói. Vui lòng thử lại.";
    };
    recognition.onend = () => {
      setListening(false);
      if (receivedSpeech) status.textContent = "Đã chuyển thành văn bản. Hãy kiểm tra nội dung trước khi gửi.";
    };
    recognition.start();
  });

  return stop;
}

/**
 * Cột phải W-03 — TRẠNG THÁI CA, không phải checklist nội bộ.
 *
 * Trước 2026-08-19 chỗ này là thanh tiến độ "2/39" cộng phiếu tóm tắt liệt kê từng trường. Cả hai
 * đều phơi cấu trúc bên trong của hệ thống ra cho bệnh nhân: con số 39 là số field của protocol,
 * nó không có nghĩa gì với người đang đau và chỉ tạo cảm giác còn 37 câu hỏi nữa. Thay bằng ba
 * chặng mà bệnh nhân thật sự cần biết mình đang ở đâu.
 *
 * Thứ tự ưu tiên có chủ đích: nghi ngờ dấu hiệu nguy hiểm chen TRƯỚC bước xác nhận phiếu — không
 * bao giờ để một câu "chờ bạn xác nhận" đứng trên một ca đang cần chuyển gấp.
 */
function caseStatusCard(current) {
  const status = current?.status;
  if (status === "approved") return resultStatusCard(current);
  if (Boolean(current?.red_flags?.length) || status === "escalated") return suspectedRedFlagCard();
  if (status === "needs_more_info") return nurseFollowUpCard();
  if (current?.summary_ready && !state.summaryConfirmed) return confirmPendingCard();
  if (status === "needs_nurse_review" || status === "awaiting_approval" || state.summaryConfirmed) return waitingCard();
  return collectingCard();
}

function statusCard(tone, iconName, title, copy, extra = "") {
  return `<section class="side-card status-card${tone ? ` is-${tone}` : ""}">
    <span class="section-label">Tình trạng ca</span>
    <div class="status-head">${icon(iconName, 19)}<b>${escapeHtml(title)}</b></div>
    <p class="status-copy">${copy}</p>
    ${extra}
  </section>`;
}

function collectingCard() {
  return statusCard("active", "info", "Trợ lý đang thu thập thông tin",
    "Trợ lý đang hỏi để thu thập đủ thông tin cho nhân viên y tế. Bạn cứ trả lời theo những gì mình biết — không chắc thì nói không chắc cũng được.");
}

function nurseFollowUpCard() {
  return statusCard("active", "ask", "Nhân viên y tế cần bạn bổ sung",
    "Nhân viên y tế đang trao đổi trực tiếp với bạn. Hãy trả lời câu hỏi trong khung chat để họ có thêm thông tin xem xét ca.");
}

function confirmPendingCard() {
  return statusCard("active", "check", "Chờ bạn xác nhận",
    "Trợ lý đã ghi nhận đủ thông tin chính. Bạn xem lại phần tóm tắt trợ lý vừa nhắn trong hội thoại và xác nhận giúp.",
    `<div class="action-row" style="margin-top:14px">
      <button class="primary-button btn-sm" type="button" data-confirm="yes">Đúng rồi</button>
      <button class="secondary-button btn-sm" type="button" data-confirm="no">Chưa đúng</button>
    </div>`);
}

function waitingCard() {
  return statusCard("", "clock", "Đợi kết quả",
    "Thông tin của bạn đã chuyển tới nhân viên y tế. Hướng dẫn xử trí sẽ hiện ở đây sau khi được duyệt.",
    `<span class="pill" style="margin-top:12px">${icon("clock", 16)}<span>Ước tính <b>~5-10 phút</b></span></span>`);
}

/**
 * Ngôn ngữ ở đây theo quyết định 2026-08-19 (`_guidance/what_to_do_next.md` §4.12): hệ thống nêu
 * NGHI NGỜ và chuyển cho người, KHÔNG tự khẳng định "đây là cấp cứu". Câu thứ hai là lưới an toàn
 * phổ quát — nó đúng với mọi người bệnh trong mọi tình huống nên nói ra không phải là chẩn đoán.
 * Không nêu tên dấu hiệu và không nêu lý do lâm sàng: hệ thống không chẩn đoán, và một lời giải
 * thích sai ở đây đắt hơn nhiều so với việc không giải thích.
 */
function suspectedRedFlagCard() {
  return statusCard("alert", "warning", "Nghi ngờ dấu hiệu nguy hiểm",
    "Có một số thông tin bạn vừa mô tả cần nhân viên y tế xem trực tiếp. Ca của bạn đã được chuyển lên mức ưu tiên cao nhất và sẽ có người liên hệ trong ít phút.",
    `<p class="status-copy" style="margin-top:10px"><b>Trong lúc chờ, nếu bạn thấy tình trạng xấu đi hoặc thấy không ổn, hãy gọi 115 ngay</b> — đừng chờ phản hồi ở đây.</p>
     <span class="pill status-hotline" style="margin-top:12px">${icon("phone", 16)}<span>Cấp cứu <b class="num">115</b> · Trực 24/7</span></span>`);
}

/** Chặng 3 — dùng lại đúng khối kết quả của W-05 để hai màn không nói hai kiểu về cùng một ca. */
function resultStatusCard(current) {
  const priority = current.triage_proposal?.priority;
  return `<section class="side-card status-card">
    <span class="section-label">Kết quả phân loại</span>
    <span class="pill approved-chip">${icon("lock", 15)}<span>Đã duyệt bởi nhân viên y tế</span></span>
    <div class="final-card is-compact ${priorityClass(priority)}">
      <div class="final-priority">${priorityDot(priority)}<b>${priorityLabels[priority] || "Chưa xác định"}</b></div>
    </div>
    <button class="secondary-button btn-sm" type="button" data-goto-result style="margin-top:14px;width:100%">Xem hướng dẫn xử trí</button>
  </section>`;
}

function initialMessages(current) {
  if (current?.conversation?.length) {
    return current.conversation.map((item) => ({
      role: item.role === "system" ? "agent" : item.role,
      text: item.content,
      authorName: item.author_name || (item.role === "nurse" ? current.reviewed_by_name : null),
    }));
  }
  return [{ role: "agent", text: "Xin chào, bạn hãy mô tả tự do triệu chứng bạn đang gặp phải." }];
}

function messageMarkup(message) {
  // Bong bóng "đang xử lý" là thông báo trạng thái, không phải lời thoại: `role="status"` +
  // `aria-live` để trình đọc màn hình đọc lên, còn ba chấm là trang trí nên `aria-hidden`.
  if (message.role === "pending") {
    return `<div class="bubble is-pending" role="status" aria-live="polite"><span class="typing-dots" aria-hidden="true"><i></i><i></i><i></i></span><span>${escapeHtml(message.text)}</span></div>`;
  }
  if (message.role === "system") {
    return `<div class="bubble is-system">${icon("check", 14)}<span>${escapeHtml(message.text)}</span></div>`;
  }
  // tanh - sửa format output agent (2026-08-27).
  // Bong bóng đang stream đi qua ĐÚNG `paragraphs()` như bong bóng đã xong, chỉ thêm cờ `pending`.
  // Trước đây nó giữ văn bản thô rồi mới được `done` vẽ lại thành đoạn/gạch đầu dòng, nên người dùng
  // thấy cả câu trả lời nhảy một nhịp ngay lúc vừa đọc xong - format phải chạy CÙNG luồng chữ, không
  // phải sau nó. Con trỏ nhấp nháy theo `.is-typing` sang phần tử chữ cuối (xem `renderTextBlock`),
  // nên việc chèn `<p>` không còn đẩy nó xuống dòng riêng nữa.
  if (message.role === "streaming") {
    return `<div class="chat-message is-agent"><span class="chat-message-sender"><i class="chat-source-avatar">${icon("logo", 15)}</i><span>VMedTriage</span></span><div class="bubble is-streaming">${paragraphs(message.text, { pending: true })}</div></div>`;
  }
  const sender = message.role === "agent"
    ? "VMedTriage"
    : message.role === "nurse"
      ? message.authorName || "Nhân viên y tế"
      : "";
  if (sender) {
    const sourceIcon = message.role === "agent" ? icon("logo", 15) : icon("user", 15);
    return `<div class="chat-message is-${escapeHtml(message.role)}"><span class="chat-message-sender"><i class="chat-source-avatar">${sourceIcon}</i><span>${escapeHtml(sender)}</span></span><div class="bubble is-${escapeHtml(message.role)}">${paragraphs(message.text)}</div></div>`;
  }
  return `<div class="bubble is-${escapeHtml(message.role)}">${paragraphs(message.text)}</div>`;
}

// Danh sách "thông tin cần làm rõ" đã CHUYỂN sang màn hình điều dưỡng (`nurse.js`) ngày 2026-08-14:
// nó phơi ra checklist nội bộ mà bệnh nhân không cần thấy - họ chỉ cần trả lời câu trợ lý đang hỏi -
// trong khi điều dưỡng thì cần biết chính xác ca này còn thiếu gì trước khi duyệt.
//
// 2026-08-19 đi nốt bước còn lại: bỏ luôn THANH TIẾN ĐỘ. Mẫu số của nó là số field của protocol
// (39 với generic), một con số nội bộ mà bệnh nhân đọc thành "còn 37 câu hỏi nữa". Cột phải W-03
// nay là TRẠNG THÁI CA (`caseStatusCard`) - thứ bệnh nhân thật sự cần biết.

// Stage 6 CS: hết phiên hỏi-đáp, agent dựng phiếu tóm tắt và chờ bệnh nhân xác nhận ĐÚNG/CHƯA ĐÚNG
// trước khi bàn giao điều dưỡng. `case_id` chính là `session_id` của phiên agent nên gọi thẳng
// `/api/v1/fever/sessions/{id}/confirm` được, không cần endpoint mới.
//
// Danh sách trường của phiếu ĐÃ BỎ khỏi cột phải (2026-08-19) - bệnh nhân xác nhận theo phần tóm
// tắt trợ lý nhắn trong hội thoại, không theo một bảng field song song. Bước xác nhận vẫn còn:
// hai nút nay nằm trong `confirmPendingCard`, nên endpoint `/confirm` không mất đường gọi.
async function confirmSummary(root, context, isCorrect) {
  try {
    await api(`/api/v1/fever/sessions/${state.caseId}/confirm`, { method: "POST", body: JSON.stringify({ is_correct: isCorrect }) });
    state.summaryConfirmed = true;
    state.patientMessages.push({
      role: "system",
      text: isCorrect ? "Bạn đã xác nhận phiếu tóm tắt. Thông tin đang chờ nhân viên y tế duyệt." : "Đã ghi nhận. Bạn hãy nhắn lại phần chưa đúng để trợ lý sửa.",
    });
    renderPatientChat(root, context);
  } catch (problem) {
    showToast(problem.message || "Không gửi được xác nhận.", true);
  }
}

// Bệnh nhân tự chốt "không còn gì để khai báo thêm" — có thể bấm bất cứ lúc nào, kể cả khi agent
// chưa hỏi hết checklist. Đây là lối thoát chủ động của người dùng nên KHÔNG chờ agent xác nhận đủ
// thông tin (`summary_ready`); dừng hội thoại ngay và chuyển ca cho nhân viên y tế với dữ liệu hiện
// có — nhân viên y tế nhìn tag "Thiếu thông tin" trên phiếu tóm tắt để biết checklist chưa đầy đủ.
async function declareDone(root, context) {
  if (!window.confirm("Xác nhận bạn đã khai báo hết triệu chứng và không còn bất thường nào khác?")) return;
  try {
    // KHÔNG dùng `/api/v1/fever/sessions/{id}/confirm`: router đó là demo độc lập, không đụng tới
    // case_store nên nurse queue không bao giờ thấy ca, và AI đề xuất/nguồn đối chiếu/trace
    // Braintrust cũng không bao giờ sinh ra (xem docstring `force_complete_case` ở backend).
    const data = await api(`/api/v1/cases/${state.caseId}/force-complete`, { method: "POST" });
    state.currentPatientCase = await api(`/api/v1/cases/${data.case_id}`).catch(() => state.currentPatientCase);
    state.summaryConfirmed = true;
    state.patientForcedComplete = true;
    state.patientMessages.push({
      role: "system",
      text: "Bạn đã xác nhận khai báo xong triệu chứng. Thông tin hiện tại đã được chuyển cho nhân viên y tế duyệt.",
    });
    renderPatientChat(root, context);
  } catch (problem) {
    showToast(problem.message || "Không gửi được xác nhận.", true);
  }
}

/**
 * Chạy một lượt chat qua `/api/v1/chat/stream` và vẽ câu trả lời dần ra màn hình.
 *
 * Rơi về `POST /api/v1/chat` khi stream không dùng được (proxy chặn `text/event-stream`, trình duyệt
 * cũ không có `ReadableStream`). Đây là fallback THẬT chứ không phải phòng hờ: mất streaming chỉ là
 * mất một cải thiện cảm nhận, còn mất lượt chat là mất tính năng.
 */
async function streamChatTurn(message, root, context) {
  const body = JSON.stringify({ message, ...(state.caseId ? { case_id: state.caseId } : {}) });
  let done = null;
  let failed = null;
  let text = "";

  const paint = () => {
    // Thay bong bóng "đang xử lý" bằng phần văn bản đã nhận được - đây chính là điểm khác biệt người
    // dùng cảm nhận được: chữ hiện dần thay vì màn hình đứng im vài giây.
    state.patientMessages = state.patientMessages.filter((item) => item.role !== "pending" && item.role !== "streaming");
    state.patientMessages.push({ role: "streaming", text });
    // tanh - sửa format output agent (2026-08-27).
    // Mẩu chữ thứ hai trở đi chỉ vẽ lại BONG BÓNG, không dựng lại cả trang: `renderPatientChat` thay
    // `root.innerHTML`, gắn lại toàn bộ handler và mở lại vòng polling ca - làm việc đó vài chục lần
    // mỗi giây thì chính nó là thứ giật, và mỗi lần thay DOM lại khởi động lại animation con trỏ.
    // Lần đầu vẫn phải render đủ để bong bóng ra đời; `state` vẫn được cập nhật trước đó nên mọi lần
    // render đầy đủ sau này (`done`, lỗi, điều hướng) đều dựng lại đúng những gì đang thấy.
    const bubble = root.querySelector(".bubble.is-streaming");
    if (!bubble) { renderPatientChat(root, context); return; }
    bubble.innerHTML = paragraphs(text, { pending: true });
    scrollChat(root);
  };

  try {
    await apiStream("/api/v1/chat/stream", {
      body,
      onEvent: (event, data) => {
        if (event === "token") { text += data; paint(); }
        else if (event === "done") done = data;
        else if (event === "error") failed = data;
      },
    });
  } catch (problem) {
    if (problem.status === 401 || problem.status === 403) throw problem;
    return api("/api/v1/chat", { method: "POST", body });
  }

  if (failed) throw new ApiError(failed.detail || "Không xử lý được tin nhắn.", failed.status || 500);
  // Stream kết thúc mà không có `done`: kết nối đứt giữa chừng. Hỏi lại bằng đường thường thay vì
  // hiển thị nửa câu như thể đó là câu trả lời hoàn chỉnh.
  return done ?? api("/api/v1/chat", { method: "POST", body });
}

async function submitMessage(event, root, context) {
  event.preventDefault();
  if (state.patientBusy) return;
  const form = event.currentTarget;
  const input = form.querySelector("textarea");
  const error = form.querySelector("#chat-error");
  const message = input.value.trim();
  if (!message) { error.textContent = "Vui lòng nhập mô tả triệu chứng."; input.focus(); return; }
  error.textContent = "";
  state.patientMessages.push({ role: "patient", text: message }, { role: "pending", text: "Hệ thống đang kiểm tra thông tin bạn cung cấp." });
  input.value = "";
  state.patientBusy = true;
  renderPatientChat(root, context);
  try {
    const data = await streamChatTurn(message, root, context);
    setActiveCase(data.case_id);
    // `/chat` chỉ trả câu trả lời + trạng thái. Lấy thêm case đầy đủ để cột bên phải hiện đúng tiến
    // độ (`summary_fields`) - request này KHÔNG gọi LLM nên không làm chậm lượt chat đáng kể. Lỗi ở
    // đây không được làm hỏng lượt chat, nên fallback về chính response của `/chat`.
    state.currentPatientCase = await api(`/api/v1/cases/${data.case_id}`).catch(() => data);
    state.patientMessages = state.patientMessages.filter((item) => item.role !== "pending" && item.role !== "streaming");
    state.patientMessages.push({ role: "agent", text: data.response || "Thông tin đã được ghi nhận." });
  } catch (problem) {
    state.patientMessages = state.patientMessages.filter((item) => item.role !== "pending" && item.role !== "streaming");
    state.patientMessages.push({ role: "error", text: problem.message || "Không thể gửi thông tin. Vui lòng thử lại." });
  } finally {
    state.patientBusy = false;
    // W-04 chen vào NGAY khi phát hiện dấu hiệu cấp cứu, không chờ hết checklist và không chờ điều
    // dưỡng duyệt (CLAUDE.md nguyên tắc 4 - ngoại lệ có chủ đích của HITL). Chỉ chen MỘT LẦN cho
    // mỗi ca: xem ghi chú ở `state.redFlagShownCaseId`.
    if (needsRedFlagScreen()) {
      state.redFlagShownCaseId = state.caseId;
      context.navigate("red-flag");
      return;
    }
    renderPatientChat(root, context);
  }
}

function needsRedFlagScreen() {
  const current = state.currentPatientCase;
  if (!current) return false;
  if (state.redFlagShownCaseId === current.case_id) return false;
  return Boolean(current.red_flags?.length) || current.status === "escalated";
}

/**
 * W-04 — màn hình cảnh báo khẩn cấp, chiếm trọn khung.
 *
 * Đây là màn DUY NHẤT lấy đỏ làm màu chủ đạo. Không đặt nó thành một khối trong trang chat: người
 * bệnh phải dừng lại đọc, và một khối cuộn qua được thì không làm được việc đó.
 */
export function renderRedFlag(root, { navigate }) {
  const current = state.currentPatientCase;
  const reason = current?.red_flags?.[0]?.label || current?.triage_proposal?.reason || "dấu hiệu nguy hiểm được phát hiện";
  root.innerHTML = `<section class="redflag-shell">
    <div class="redflag-card">
      <div class="redflag-bar">${icon("warning", 19)}<b>Cảnh báo khẩn cấp</b><span>Ca ${shortCaseId(current?.case_id)} · ${formatDate(current?.updated_at || Date.now())}</span></div>
      <div class="redflag-body">
        <div class="redflag-inner">
          <div class="redflag-head">
            <span class="redflag-icon">${icon("warning", 44)}</span>
            <div>
              <h1>Dấu hiệu cần cấp cứu: ${escapeHtml(reason)}</h1>
              <p>Đây có thể là dấu hiệu của một tình trạng cấp cứu. Nếu triệu chứng xấu đi, hãy <b>gọi 115</b> hoặc đến cơ sở y tế gần nhất ngay.</p>
            </div>
          </div>
          <div class="redflag-cards">
            <div>${icon("check", 20)}<span>Ca của bạn đã được chuyển ngay tới nhân viên y tế trực với <strong>mức ưu tiên cao nhất</strong>.</span></div>
            <div class="hotline">${icon("phone", 20)}<span>Cấp cứu <strong class="num">115</strong> · Trực 24/7</span></div>
          </div>
          <button class="danger-button" type="button" data-continue>Tôi đã đọc, tiếp tục</button>
        </div>
      </div>
    </div>
  </section>`;
  // Quay lại đoạn chat đang dở thay vì màn kết quả riêng: đoạn hội thoại vẫn còn ý nghĩa (điều dưỡng
  // có thể chat trực tiếp tiếp theo), và trạng thái "đang chờ/đã chuyển cấp cứu" đã có sẵn ở cột phải
  // (`caseStatusCard` → `suspectedRedFlagCard`) nên không cần một màn hình riêng chỉ để chờ.
  root.querySelector("[data-continue]").addEventListener("click", () => navigate("patient-chat"));
}

/** W-05 — kết quả. Ba trạng thái: chờ duyệt / đã duyệt / lỗi tải. */
export function renderPatientResult(root, { navigate, logout }) {
  const current = state.currentPatientCase;
  const header = patientHeader("cases", {
    title: current ? `Hướng dẫn xử trí · <b>${shortCaseId(current.case_id)}</b>` : "Hướng dẫn xử trí",
    // Màn này là nhánh CUỐI của chuỗi Kết quả của tôi -> Chi tiết ca -> Hướng dẫn xử trí, nên nút
    // quay lại trỏ về chi tiết ca chứ không nhảy thẳng về danh sách.
    right: `<div class="header-right">${current ? `<button class="back-button" type="button" data-case-back>${icon("chevronLeft", 15)}<span>Chi tiết ca</span></button>` : ""}${accountMenu()}</div>`,
  });

  let body;
  if (!current) {
    body = `<div class="state-panel">
      <span class="state-icon is-neutral">${icon("broken", 38)}</span>
      <h2>Không thể tải kết quả</h2>
      <p>Chưa có ca nào đang mở trong phiên này. Kết quả của bạn vẫn được lưu.</p>
      <button class="secondary-button" type="button" data-retry>${icon("retry", 17)}<span>Thử lại</span></button>
    </div>`;
  } else if (current.status === "approved") {
    body = approvedMarkup(current);
  } else {
    body = `<div class="state-panel">
      <span class="state-icon">${icon("clock", 44)}</span>
      <h2>${current.status === "escalated" ? "Ca đã được chuyển cấp cứu" : "Đang chờ nhân viên y tế duyệt"}</h2>
      <p>${current.status === "escalated"
        ? "Không chờ phản hồi trực tuyến nếu triệu chứng đang diễn ra. Hãy gọi 115 ngay."
        : "Nhân viên y tế sẽ xem xét và gửi hướng dẫn xử trí sớm nhất có thể. Bạn có thể đóng trang này, chúng tôi sẽ thông báo khi có kết quả."}</p>
      <span class="pill">${icon("clock", 18)}<span>Thời gian chờ ước tính <b>~5-10 phút</b></span></span>
      <p class="state-hint">Ca Cấp cứu được xử lý nhanh hơn.</p>
      <div class="action-row" style="margin-top:22px">
        <button class="secondary-button" type="button" data-retry>${icon("retry", 17)}<span>Kiểm tra kết quả</span></button>
        <button class="link-button" type="button" data-new-case>Bắt đầu ca mới</button>
      </div>
    </div>`;
  }

  // Gợi ý bệnh viện gần nhất KHÔNG chờ điều dưỡng duyệt (ADR-010 - đây là thông tin logistics, khác
  // hướng xử trí lâm sàng ở trên), nên nút vào màn đó hiện ngay bất kể `current.status` là gì - chỉ
  // cần đã có case đang mở.
  const hospitalLink = current
    ? `<div class="hospital-suggestion-link"><button class="secondary-button" type="button" data-goto-hospital>${icon("mapPin", 16)}<span>Tìm bệnh viện gần nhất</span></button></div>`
    : "";

  root.innerHTML = `<section class="app-shell">${header}<main class="page">${hospitalLink}${body}</main>${quickChatDockMarkup()}</section>`;
  bindPatientNav(root, { navigate });
  bindAccountMenu(root, { logout, onProfileSaved: () => renderPatientResult(root, { navigate, logout }) });
  root.querySelector("[data-retry]")?.addEventListener("click", () => refreshResult(root, { navigate, logout }));
  root.querySelector("[data-new-case]")?.addEventListener("click", () => navigate("disclaimer"));
  root.querySelector("[data-home]")?.addEventListener("click", () => navigate("patient-home"));
  root.querySelector("[data-case-back]")?.addEventListener("click", () => navigate("patient-chat"));
  root.querySelector("[data-goto-hospital]")?.addEventListener("click", () => navigate("patient-hospital"));
  startCasePolling(root, { navigate, logout }, renderPatientResult);
  bindQuickChatDock(root, { navigate });
}

function approvedMarkup(current) {
  const priority = current.triage_proposal?.priority;
  const guidance = current.patient_visible_response || current.response || "";
  return `<div class="result-grid">
    <div class="result-main">
      <span class="pill approved-chip">${icon("lock", 16)}<span>Đã duyệt bởi nhân viên y tế</span></span>
      <div class="final-card ${priorityClass(priority)}">
        <span class="section-label">Mức ưu tiên cuối cùng</span>
        <div class="final-priority">${priorityDot(priority)}<b>${priorityLabels[priority] || "Chưa xác định"}</b></div>
        <hr />
        <h3>Hướng dẫn xử trí đã xác nhận</h3>
        <ol class="instruction-list">${guidanceSteps(guidance).map((step) => `<li><span>${escapeHtml(step)}</span></li>`).join("")}</ol>
      </div>
      <p class="fine-print">Đây không phải chẩn đoán, hãy gặp bác sĩ để được tư vấn đầy đủ.</p>
    </div>
    <div class="result-main">
      <div class="meta-card">
        <div><span>Nhóm triệu chứng</span><b>${escapeHtml(detectedGroup(current))}</b></div>
        <div><span>Người duyệt</span><b>${escapeHtml(current.reviewed_by_name || "Nhân viên y tế trực")}</b></div>
        <div><span>Thời điểm duyệt</span><b class="num">${formatDate(current.reviewed_at || current.updated_at)}</b></div>
      </div>
      ${priority === "Emergency" ? `<div class="alert-card"><b>Cần cấp cứu ngay</b><p>Nếu tình trạng xấu đi trên đường di chuyển, gọi <strong>115</strong>.</p></div>` : ""}
      <button class="secondary-button" type="button" data-home>Về trang chủ</button>
    </div>
  </div>`;
}

/** Thiết kế trình bày hướng dẫn thành danh sách đánh số. Phản hồi từ điều dưỡng là văn bản tự do,
 *  nên tách theo đánh số sẵn có hoặc theo câu — KHÔNG viết lại nội dung, chỉ ngắt dòng. */
function guidanceSteps(text) {
  const clean = String(text || "").trim();
  if (!clean) return ["Nhân viên y tế đã xem thông tin bạn cung cấp."];
  const numbered = clean.split(/\s*(?:\r?\n|^)\s*\d+[.)]\s+/).map((part) => part.trim()).filter(Boolean);
  if (numbered.length > 1) return numbered;
  const lines = clean.split(/\r?\n+/).map((line) => line.replace(/^[-•*]\s*/, "").trim()).filter(Boolean);
  if (lines.length > 1) return lines;
  return clean.split(/(?<=[.!?])\s+(?=[A-ZĐÀ-Ỹ])/).map((part) => part.trim()).filter(Boolean);
}

async function refreshResult(root, context) {
  if (!state.caseId) { showToast("Chưa có ca nào đang mở.", true); return; }
  try {
    state.currentPatientCase = await api(`/api/v1/cases/${state.caseId}`);
    renderPatientResult(root, context);
    showToast("Đã cập nhật trạng thái ca.");
  } catch (problem) {
    showToast(problem.message, true);
  }
}

// ── Gợi ý bệnh viện gần nhất ─────────────────────────────────────────────────────────────────
// PATIENT-ONLY, KHÔNG qua duyệt điều dưỡng - xem ADR-010 (docs/context/decisions.md). Danh sách là
// thông tin logistics (tên/địa chỉ/khoảng cách), không phải đề xuất xử trí lâm sàng, nên bệnh nhân
// thấy trực tiếp ngay khi backend trả kết quả - KHÔNG có màn "chờ duyệt" như W-05.
//
// GPS trình duyệt ưu tiên; từ chối quyền/không hỗ trợ/timeout đều rơi về form nhập địa chỉ tay - đây
// là fallback bắt buộc chốt với PM, không phải nhánh phụ.

export function renderHospitalSuggestion(root, { navigate, logout }) {
  const current = state.currentPatientCase;
  const header = patientHeader("cases", {
    title: "Bệnh viện gần nhất",
    right: `<div class="header-right"><button class="back-button" type="button" data-hospital-back>${icon("chevronLeft", 15)}<span>Quay lại</span></button>${accountMenu()}</div>`,
  });

  root.innerHTML = `<section class="app-shell">${header}<main class="page"><div id="hospital-body">${hospitalStatePanel("clock", "Đang tải…")}</div></main>${quickChatDockMarkup()}</section>`;
  bindPatientNav(root, { navigate });
  bindAccountMenu(root, { logout, onProfileSaved: () => renderHospitalSuggestion(root, { navigate, logout }) });
  root.querySelector("[data-hospital-back]").addEventListener("click", () => navigate(current ? "patient-result" : "patient-cases"));
  bindQuickChatDock(root, { navigate });

  loadHospitalSuggestion(root, { navigate, logout });
}

function hospitalStatePanel(iconName, title, description = "", actionsHtml = "") {
  return `<div class="state-panel">
    <span class="state-icon${iconName === "broken" ? " is-neutral" : ""}">${icon(iconName, 44)}</span>
    <h2>${escapeHtml(title)}</h2>
    ${description ? `<p>${escapeHtml(description)}</p>` : ""}
    ${actionsHtml}
  </div>`;
}

async function loadHospitalSuggestion(root, context) {
  const body = root.querySelector("#hospital-body");
  if (!state.caseId) {
    body.innerHTML = hospitalStatePanel(
      "broken",
      "Chưa có ca nào đang mở",
      "Hãy mở một ca đã khai báo trước khi tìm bệnh viện gần nhất.",
      `<button class="secondary-button" type="button" data-hospital-goto-cases>Xem danh sách ca</button>`,
    );
    body.querySelector("[data-hospital-goto-cases]").addEventListener("click", () => context.navigate("patient-cases"));
    return;
  }
  try {
    const result = await api(`/api/v1/cases/${state.caseId}/hospital-suggestions`);
    body.innerHTML = hospitalListMarkup(result);
    renderHospitalMap(result);
    bindHospitalListActions(root, context, result);
  } catch (problem) {
    if (problem.status === 404) {
      body.innerHTML = hospitalRequestMarkup();
      bindHospitalRequestActions(root, context);
      return;
    }
    body.innerHTML = hospitalStatePanel(
      "broken",
      "Không thể tải gợi ý bệnh viện",
      problem.message || "",
      `<button class="secondary-button" type="button" data-hospital-retry>${icon("retry", 17)}<span>Thử lại</span></button>`,
    );
    body.querySelector("[data-hospital-retry]").addEventListener("click", () => loadHospitalSuggestion(root, context));
  }
}

function hospitalRequestMarkup() {
  return `<div class="state-panel">
    <span class="state-icon">${icon("mapPin", 44)}</span>
    <h2>Tìm bệnh viện gần bạn</h2>
    <p>Cho phép truy cập vị trí để tìm cơ sở y tế gần nhất, hoặc nhập địa chỉ nếu bạn không muốn chia sẻ vị trí.</p>
    <div class="action-row" style="margin-top:18px">
      <button class="primary-button" type="button" data-use-gps>${icon("mapPin", 17)}<span>Dùng vị trí hiện tại</span></button>
      <button class="link-button" type="button" data-use-address>Nhập địa chỉ thay thế</button>
    </div>
    <form class="hospital-address-form" data-address-form hidden>
      <label class="field">Địa chỉ của bạn<input name="address_text" type="text" maxlength="500" required placeholder="Số nhà, đường, phường/xã, tỉnh/thành" /></label>
      <button class="primary-button" type="submit">Tìm bệnh viện</button>
    </form>
  </div>`;
}

function bindHospitalRequestActions(root, context) {
  const panel = root.querySelector("#hospital-body");
  const form = panel.querySelector("[data-address-form]");
  panel.querySelector("[data-use-gps]").addEventListener("click", () => requestHospitalsByGps(root, context, form));
  panel.querySelector("[data-use-address]").addEventListener("click", () => {
    form.hidden = false;
    form.querySelector("input").focus();
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const addressText = form.querySelector("input[name=address_text]").value.trim();
    if (!addressText) return;
    submitHospitalRequest(root, context, { address_text: addressText });
  });
}

function requestHospitalsByGps(root, context, addressForm) {
  if (!navigator.geolocation) {
    showToast("Trình duyệt của bạn không hỗ trợ định vị. Vui lòng nhập địa chỉ.", true);
    addressForm.hidden = false;
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (position) =>
      submitHospitalRequest(root, context, { latitude: position.coords.latitude, longitude: position.coords.longitude }),
    () => {
      showToast("Không lấy được vị trí (từ chối quyền hoặc hết thời gian chờ). Vui lòng nhập địa chỉ.", true);
      addressForm.hidden = false;
    },
    { enableHighAccuracy: false, timeout: 10000 },
  );
}

async function submitHospitalRequest(root, context, payload) {
  const body = root.querySelector("#hospital-body");
  body.innerHTML = hospitalStatePanel("clock", "Đang tìm bệnh viện gần bạn…");
  try {
    const result = await api(`/api/v1/cases/${state.caseId}/hospital-suggestions`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    body.innerHTML = hospitalListMarkup(result);
    renderHospitalMap(result);
    bindHospitalListActions(root, context, result);
  } catch (problem) {
    body.innerHTML = hospitalStatePanel(
      "broken",
      "Không tìm được bệnh viện",
      problem.message || "",
      `<button class="secondary-button" type="button" data-hospital-retry>${icon("retry", 17)}<span>Thử lại</span></button>`,
    );
    body.querySelector("[data-hospital-retry]").addEventListener("click", () => loadHospitalSuggestion(root, context));
  }
}

// Bản đồ trực quan (Leaflet + tile OpenStreetMap, miễn phí, không cần key - nhúng qua CDN ở
// index.html). Hai biến module-level vì Leaflet giữ listener trên `window`/`document`; đổi màn hình
// mà không gọi `.remove()`/xoá layer trước sẽ rò bộ nhớ và có thể vỡ lần khởi tạo tiếp theo trên
// cùng id DOM.
let hospitalMap = null;
let hospitalRouteLine = null;

export function destroyHospitalMap() {
  if (hospitalMap) hospitalMap.remove();
  hospitalMap = null;
  hospitalRouteLine = null; // layer đã bị xoá cùng map ở dòng trên, chỉ cần bỏ tham chiếu cũ
}

/** Link chỉ đường Google Maps - PHƯƠNG ÁN CHẮC ĂN, không phụ thuộc CORS/uptime của OSRM demo server.
 *  Luôn hiển thị cạnh mỗi bệnh viện, không chỉ khi vẽ route trên bản đồ thất bại. */
function directionsUrl(originLat, originLng, destLat, destLng) {
  return `https://www.google.com/maps/dir/?api=1&origin=${originLat},${originLng}&destination=${destLat},${destLng}&travelmode=driving`;
}

/** Vẽ marker vị trí bệnh nhân (xanh) + từng bệnh viện (đỏ), tự fit khung hình để thấy hết mọi điểm.
 *  Nếu CDN Leaflet chết (`window.L` không tồn tại) HOẶC response thiếu toạ độ hợp lệ thì bỏ qua lặng
 *  lẽ - danh sách text vẫn dùng được bình thường, bản đồ chỉ là phần bổ sung trực quan. Từng vỡ thật
 *  một lần vì backend quên trả `patient_lat/lng`; không để lỗi đó lan ra thành cả màn hình báo lỗi. */
function renderHospitalMap(result) {
  destroyHospitalMap();
  if (typeof window.L === "undefined" || !document.getElementById("hospital-map")) return;
  if (typeof result.patient_lat !== "number" || typeof result.patient_lng !== "number") {
    console.warn("renderHospitalMap: thiếu patient_lat/patient_lng hợp lệ trong response", result);
    return;
  }

  const patientPoint = [result.patient_lat, result.patient_lng];
  hospitalMap = window.L.map("hospital-map").setView(patientPoint, 14); // scrollWheelZoom mặc định BẬT
  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors",
    maxZoom: 19,
  }).addTo(hospitalMap);

  const points = [patientPoint];
  window.L.circleMarker(patientPoint, { radius: 9, color: "#2f78d5", fillColor: "#4a90e2", fillOpacity: 0.95, weight: 2 })
    .addTo(hospitalMap)
    .bindPopup("Vị trí của bạn");

  for (const hospital of result.hospitals || []) {
    if (typeof hospital.lat !== "number" || typeof hospital.lng !== "number") continue;
    const point = [hospital.lat, hospital.lng];
    points.push(point);
    window.L.circleMarker(point, { radius: 8, color: "#c0392b", fillColor: "#e74c3c", fillOpacity: 0.9, weight: 2 })
      .addTo(hospitalMap)
      .bindPopup(
        `<b>${escapeHtml(hospital.name || "(Chưa rõ tên)")}</b><br>${escapeHtml(hospital.address || "")}<br>${Number(hospital.distance_km).toFixed(1)} km<br>` +
          `<a href="${directionsUrl(result.patient_lat, result.patient_lng, hospital.lat, hospital.lng)}" target="_blank" rel="noopener">Chỉ đường trên Google Maps ↗</a>`,
      )
      // Bấm marker: thử vẽ route thật lên bản đồ (best-effort). Popup ở trên vẫn có link Google Maps
      // luôn sẵn sàng, không chờ kết quả gọi mạng này.
      .on("click", () => drawRouteTo(hospital, result));
  }
  if (points.length > 1) hospitalMap.fitBounds(points, { padding: [28, 28] });
}

/** Vẽ đường đi (lái xe) từ vị trí bệnh nhân tới 1 bệnh viện, gọi OSRM demo server (miễn phí, không
 *  cần key: router.project-osrm.org - Project OSRM tài trợ bởi FOSSGIS). server này KHÔNG đảm bảo
 *  CORS/uptime (dùng cho demo/thử nghiệm, không phải production quy mô lớn) - mọi lỗi (mạng, CORS,
 *  timeout, response bất thường) đều bị nuốt lặng lẽ, vì mỗi bệnh viện đã có sẵn link "Chỉ đường"
 *  mở Google Maps không phụ thuộc lời gọi này. KHÔNG raise, KHÔNG báo lỗi lên UI. */
async function drawRouteTo(hospital, result) {
  if (!hospitalMap) return;
  if (hospitalRouteLine) {
    hospitalMap.removeLayer(hospitalRouteLine);
    hospitalRouteLine = null;
  }
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 6000);
  try {
    const url = `https://router.project-osrm.org/route/v1/driving/${result.patient_lng},${result.patient_lat};${hospital.lng},${hospital.lat}?overview=full&geometries=geojson`;
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) return;
    const data = await response.json();
    const coordinates = data?.routes?.[0]?.geometry?.coordinates;
    if (!Array.isArray(coordinates) || !coordinates.length) return;
    const latLngs = coordinates.map(([lng, lat]) => [lat, lng]);
    hospitalRouteLine = window.L.polyline(latLngs, { color: "#2f78d5", weight: 5, opacity: 0.85 }).addTo(hospitalMap);
    hospitalMap.fitBounds(hospitalRouteLine.getBounds(), { padding: [28, 28] });
  } catch {
    // OSRM demo server sập/CORS/timeout - im lặng, người dùng vẫn dùng được link Google Maps.
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function hospitalListMarkup(result) {
  const hospitals = result.hospitals || [];
  if (!hospitals.length) {
    return hospitalStatePanel(
      "mapPin",
      "Không tìm thấy cơ sở y tế gần đây",
      "Thử lại với địa chỉ khác.",
      `<button class="secondary-button" type="button" data-hospital-retry-request>${icon("retry", 17)}<span>Tìm lại</span></button>`,
    );
  }
  const rows = hospitals
    .map(
      (item, index) => `<li class="hospital-row" data-hospital-index="${index}" tabindex="0" role="button" aria-label="Xem ${escapeHtml(item.name || "bệnh viện")} trên bản đồ">
        <div class="hospital-row-main"><b>${escapeHtml(item.name || "(Chưa rõ tên trên bản đồ)")}</b><span>${escapeHtml(item.address || "")}</span></div>
        <div class="hospital-row-meta">
          <span class="pill">${icon("mapPin", 14)}<span>${Number(item.distance_km).toFixed(1)} km</span></span>
          ${item.phone ? `<a class="link-button" href="tel:${escapeHtml(item.phone)}">${icon("phone", 14)}<span>${escapeHtml(item.phone)}</span></a>` : ""}
          <a class="link-button" href="${directionsUrl(result.patient_lat, result.patient_lng, item.lat, item.lng)}" target="_blank" rel="noopener">${icon("mapPin", 14)}<span>Chỉ đường ↗</span></a>
        </div>
      </li>`,
    )
    .join("");
  return `<div class="hospital-result">
    <p class="fine-print">Địa chỉ tra cứu: ${escapeHtml(result.address_text || "")} · Nguồn dữ liệu: ${escapeHtml(result.provider || "")}</p>
    <div id="hospital-map" class="hospital-map"></div>
    <ul class="hospital-list">${rows}</ul>
    <button class="link-button" type="button" data-hospital-retry-request>Tìm lại với vị trí khác</button>
  </div>`;
}

/** Bấm 1 dòng bệnh viện: lượn bản đồ tới đó + thử vẽ route (giống bấm marker). Bấm vào link "Gọi"/
 *  "Chỉ đường" bên trong dòng thì để trình duyệt tự xử lý bình thường, không chặn. */
function bindHospitalListActions(root, context, result) {
  root.querySelectorAll("[data-hospital-index]").forEach((row) => {
    const activate = (event) => {
      if (event.target.closest("a")) return; // đừng chặn link tel:/Google Maps bên trong dòng
      const hospital = result.hospitals[Number(row.dataset.hospitalIndex)];
      if (!hospital || !hospitalMap) return;
      hospitalMap.setView([hospital.lat, hospital.lng], 16);
      drawRouteTo(hospital, result);
    };
    row.addEventListener("click", activate);
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activate(event);
      }
    });
  });
  root.querySelector("[data-hospital-retry-request]")?.addEventListener("click", () => {
    destroyHospitalMap();
    root.querySelector("#hospital-body").innerHTML = hospitalRequestMarkup();
    bindHospitalRequestActions(root, context);
  });
}

function scrollChat(root) {
  const log = root.querySelector("#chat-log");
  if (log) log.scrollTop = log.scrollHeight;
}
