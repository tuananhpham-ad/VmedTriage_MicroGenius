import { api, ApiError, apiStream } from "../api.js";
import { accountMenu, bindAccountMenu } from "./account.js?v=design-20260819b";
import { setActiveCase, state } from "../state.js";
import {
  appHeader,
  escapeHtml,
  formatDate,
  icon,
  identityBlock,
  priorityClass,
  priorityDot,
  priorityLabels,
  shortCaseId,
  showToast,
  statusClass,
  statusLabels,
  symptomGroupLabels,
} from "../shared.js";

const commonSymptoms = [
  ["Sốt", "Tôi bị sốt."], ["Đau bụng", "Tôi bị đau bụng."], ["Đau ngực", "Tôi bị đau ngực."], ["Khó thở", "Tôi cảm thấy khó thở."], ["Đau đầu", "Tôi bị đau đầu."],
];

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

export function stopCasePolling() {
  if (casePolling) window.clearInterval(casePolling);
  casePolling = null;
}

/** Chỉ vẽ lại khi có thay đổi THẬT. Vẽ lại mỗi 10s vô điều kiện sẽ nháy màn hình và cuộn lại khung
 *  chat trong lúc người bệnh đang đọc. */
function statusSignature(item) {
  return [item?.status, item?.triage_proposal?.priority, item?.patient_visible_response, item?.red_flags?.length].join("|");
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

function patientNav(active) {
  return [
    { label: "Trang chủ", active: active === "home", action: "home" },
    { label: "Khai báo triệu chứng", active: active === "chat", action: "chat" },
    { label: "Kết quả của tôi", active: active === "result", action: "result" },
  ];
}

function bindPatientNav(root, { navigate }) {
  root.querySelectorAll("[data-nav]").forEach((button) =>
    button.addEventListener("click", () => {
      if (button.dataset.nav === "home") navigate("patient-home");
      if (button.dataset.nav === "chat") navigate(state.caseId ? "patient-chat" : "disclaimer");
      if (button.dataset.nav === "result") navigate("patient-result");
    }),
  );
}

function patientHeader(active) {
  return appHeader({
    nav: patientNav(active),
    right: `<div class="header-right">${identityBlock("Bệnh nhân")}${accountMenu()}</div>`,
  });
}

/** W-00 — trang chủ bệnh nhân. */
export function renderPatientHome(root, { navigate, logout }) {
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
  root.querySelector("[data-guide]").addEventListener("click", () => navigate("disclaimer"));
  root.querySelector("[data-open-case]")?.addEventListener("click", () => navigate("patient-result"));
  bindAccountMenu(root, { logout, onProfileSaved: () => renderPatientHome(root, { navigate, logout }) });
  loadPatientHistory(root, { navigate, logout });
}

function openCaseCard(current) {
  if (!current) {
    return `<div class="open-case-card"><div class="head"><span class="section-label">Ca đang mở</span></div><div class="empty-state"><strong>Chưa có ca nào đang mở</strong><span>Khi bắt đầu khai báo, tiến trình và kết quả đã duyệt sẽ xuất hiện tại đây.</span></div></div>`;
  }
  const complaint = current.summary?.chief_complaint || symptomGroupLabels[current.structured_data?.symptom_group] || "Triệu chứng đang khai báo";
  return `<div class="open-case-card">
    <div class="head"><span class="section-label">Ca đang mở</span><span class="status-badge ${statusClass(current.status)}">${statusLabels[current.status] || "Đang xử lý"}</span></div>
    <div class="title">${shortCaseId(current.case_id)} · ${escapeHtml(complaint)}</div>
    <p>Gửi lúc ${formatDate(current.created_at)}${current.status === "approved" ? "" : " · Ước tính còn ~5-10 phút"}</p>
    <button class="secondary-button" type="button" data-open-case>Xem trạng thái ca</button>
  </div>`;
}

async function loadPatientHistory(root, { navigate, logout }) {
  const list = root.querySelector("#history-list");
  try {
    const cases = await api("/api/v1/patient/history");
    if (!cases.length) { list.innerHTML = `<p class="muted-copy">Chưa có phiên khai báo nào.</p>`; return; }
    const header = `<div class="history-head-row"><span class="col-label">Ngày</span><span class="col-label">Nhóm triệu chứng</span><span class="col-label">Mức ưu tiên</span><span class="col-label">Trạng thái</span></div>`;
    list.innerHTML = header + cases.slice(0, 5).map(historyRow).join("");
    list.querySelectorAll("[data-history-case]").forEach((button) =>
      button.addEventListener("click", async () => {
        try {
          state.currentPatientCase = await api(`/api/v1/cases/${button.dataset.historyCase}`);
          setActiveCase(state.currentPatientCase.case_id);
          state.patientMessages = initialMessages(state.currentPatientCase);
          navigate("patient-result");
        } catch (problem) { showToast(problem.message, true); }
      }),
    );
  } catch {
    list.innerHTML = `<p class="muted-copy">Không thể tải lịch sử phiên khai báo.</p>`;
  }
}

function historyRow(item) {
  const priority = item.triage_proposal?.priority;
  const group = item.summary?.chief_complaint || symptomGroupLabels[item.structured_data?.symptom_group] || "Triệu chứng chung";
  return `<button class="history-row" type="button" data-history-case="${item.case_id}">
    <span class="date">${formatDate(item.created_at)}</span>
    <span class="group">${escapeHtml(group)}</span>
    <span>${priority ? `<span class="priority-badge ${priorityClass(priority)}">${priorityLabels[priority] || priority}</span>` : `<span class="muted-copy">Chưa có</span>`}</span>
    <span class="status ${statusClass(item.status)}">${statusLabels[item.status] || item.status}</span>
  </button>`;
}

/** W-02 — disclaimer bắt buộc mỗi phiên khai báo mới, không có đường bỏ qua ngoài nút CTA. */
export function renderDisclaimer(root, { navigate, onAccept, logout }) {
  root.innerHTML = `<section class="app-shell">
    ${appHeader({ title: "Bước 1 / 3 · Trước khi khai báo", right: `<div class="header-right">${accountMenu()}</div>` })}
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
  </section>`;
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
    state.redFlagShownCaseId = null;
  }
  renderPatientChat(root, { navigate, logout });
}

/** W-03 — khai báo triệu chứng. Chat bên trái, cột phải là nhóm đã nhận diện + tiến độ checklist. */
export function renderPatientChat(root, { navigate, logout }) {
  const current = state.currentPatientCase;
  const messages = state.patientMessages.length ? state.patientMessages : initialMessages(current);
  // `state.patientBusy` phải đi vào markup chứ không chỉ chặn double-submit trong `submitMessage`:
  // nếu không, ô nhập và nút Gửi vẫn bấm được trong lúc chờ và người dùng gõ tiếp mà không hiểu vì
  // sao không có gì xảy ra. Một nguồn sự thật duy nhất cho trạng thái chờ.
  const busy = state.patientBusy ? " disabled" : "";
  root.innerHTML = `<section class="app-shell">
    ${appHeader({
      nav: patientNav("chat"),
      meta: `<span class="live-chip">${state.patientBusy ? "Trợ lý đang xử lý" : "Trợ lý đang thu thập thông tin"}</span>`,
      right: `<div class="header-right">${accountMenu()}</div>`,
    })}
    <main class="page">
      <div class="chat-grid">
        <section class="chat-panel" aria-label="Hội thoại với trợ lý">
          <div class="capability-strip">${icon("info", 15)}<span>${AI_SCOPE_VI}</span></div>
          <div class="chat-log" id="chat-log">${messages.map(messageMarkup).join("")}</div>
          <div class="symptom-chips">${commonSymptoms.map(([label, value]) => `<button type="button" data-symptom="${escapeHtml(value)}">${label}</button>`).join("")}</div>
          <form id="chat-form" class="chat-composer">
            <label class="sr-only" for="patient-message">Mô tả triệu chứng</label>
            <textarea id="patient-message" name="message" rows="1" maxlength="5000" placeholder="Mô tả triệu chứng của bạn..."${busy}></textarea>
            <button class="primary-button" type="submit"${busy}>${icon("send", 18)}<span>${state.patientBusy ? "Đang gửi…" : "Gửi"}</span></button>
            <p class="form-error" id="chat-error" role="alert"></p>
          </form>
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
    </main>
  </section>`;

  bindPatientNav(root, { navigate });
  bindAccountMenu(root, { logout, onProfileSaved: () => renderPatientChat(root, { navigate, logout }) });
  root.querySelectorAll("[data-symptom]").forEach((button) =>
    button.addEventListener("click", () => {
      const input = root.querySelector("#patient-message");
      input.value = button.dataset.symptom;
      input.focus();
    }),
  );
  const form = root.querySelector("#chat-form");
  form.addEventListener("submit", (event) => submitMessage(event, root, { navigate, logout }));
  // Enter gửi, Shift+Enter xuống dòng — đúng hành vi bản thiết kế mô tả cho ô nhập.
  root.querySelector("#patient-message").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); }
  });
  root.querySelectorAll("[data-confirm]").forEach((button) => button.addEventListener("click", () => confirmSummary(root, { navigate, logout }, button.dataset.confirm === "yes")));
  root.querySelector("[data-goto-result]")?.addEventListener("click", () => navigate("patient-result"));
  // Không focus khi đang khoá: focus vào ô disabled là no-op ở mọi trình duyệt, nhưng vẫn kéo màn
  // hình về composer trên mobile giữa lúc người dùng đang đọc câu trả lời.
  if (!state.patientBusy) root.querySelector("#patient-message").focus();
  scrollChat(root);
  startCasePolling(root, { navigate, logout }, renderPatientChat);
}

function detectedGroup(current) {
  const group = current?.structured_data?.symptom_group;
  if (group && group !== "general") return symptomGroupLabels[group] || group;
  return current?.summary?.chief_complaint || "Đang xác định";
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
  return statusCard("active", "info", "Đang bổ sung thông tin",
    "Trợ lý đang hỏi để thu thập đủ thông tin cho nhân viên y tế. Bạn cứ trả lời theo những gì mình biết — không chắc thì nói không chắc cũng được.");
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
  if (current?.conversation?.length) return current.conversation.map((item) => ({ role: item.role === "nurse" ? "system" : item.role, text: item.content }));
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
  return `<div class="bubble is-${escapeHtml(message.role)}">${escapeHtml(message.text)}</div>`;
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
    renderPatientChat(root, context);
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
  root.querySelector("[data-continue]").addEventListener("click", () => navigate("patient-result"));
}

/** W-05 — kết quả. Ba trạng thái: chờ duyệt / đã duyệt / lỗi tải. */
export function renderPatientResult(root, { navigate, logout }) {
  const current = state.currentPatientCase;
  const header = appHeader({
    nav: patientNav("result"),
    title: current ? `Kết quả phân loại · <b>${shortCaseId(current.case_id)}</b>` : "Kết quả phân loại",
    right: `<div class="header-right">${accountMenu()}</div>`,
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

  root.innerHTML = `<section class="app-shell">${header}<main class="page">${body}</main></section>`;
  bindPatientNav(root, { navigate });
  bindAccountMenu(root, { logout, onProfileSaved: () => renderPatientResult(root, { navigate, logout }) });
  root.querySelector("[data-retry]")?.addEventListener("click", () => refreshResult(root, { navigate, logout }));
  root.querySelector("[data-new-case]")?.addEventListener("click", () => navigate("disclaimer"));
  root.querySelector("[data-home]")?.addEventListener("click", () => navigate("patient-home"));
  startCasePolling(root, { navigate, logout }, renderPatientResult);
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

function scrollChat(root) {
  const log = root.querySelector("#chat-log");
  if (log) log.scrollTop = log.scrollHeight;
}
