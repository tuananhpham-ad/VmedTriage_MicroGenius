import { api } from "../api.js";
import { accountMenu, bindAccountMenu } from "./account.js?v=design-20260819b";
import { completedStatuses, pendingStatuses, state } from "../state.js";
import {
  aiConfidence,
  appHeader,
  confidenceMarkup,
  escapeHtml,
  formatDate,
  icon,
  identityBlock,
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

function nurseHeader(active, { title = "", right = "" } = {}) {
  return appHeader({
    nav: active
      ? [
          { label: "Hàng đợi", active: active === "queue", action: "queue" },
          { label: "Ca đã duyệt", active: active === "done", action: "done" },
        ]
      : [],
    title,
    right: right || `<div class="header-right">${identityBlock("Nhân viên y tế")}${accountMenu()}</div>`,
  });
}

/** W-06 — hàng đợi ca chờ duyệt. Cột lọc bên trái, danh sách quét nhanh bên phải. */
export function renderNurseQueue(root, { navigate, logout }) {
  root.innerHTML = `<section class="app-shell">${nurseHeader("queue")}
    <main class="page">
      <div class="queue-grid">
        <aside class="queue-side">
          <div class="filter-card">
            <span class="section-label">Bộ lọc</span>
            <div class="filter-list">
              <button class="filter-button" type="button" data-filter="pending"><span>Ca cần xử lý</span><b id="pending-count">0</b></button>
              <button class="filter-button is-active" type="button" data-filter="all"><span>Tất cả</span><b id="all-count">0</b></button>
              <button class="filter-button" type="button" data-filter="Emergency"><span><span class="priority-dot is-emergency"></span>Cấp cứu</span><b id="emergency-count">0</b></button>
              <button class="filter-button" type="button" data-filter="Urgent"><span><span class="priority-dot is-urgent"></span>Khám sớm</span><b id="urgent-count">0</b></button>
              <button class="filter-button" type="button" data-filter="Self-care"><span><span class="priority-dot is-self-care"></span>Tự theo dõi</span><b id="selfcare-count">0</b></button>
            </div>
            <label class="field"><span class="section-label">Tìm ca</span><input id="queue-search" placeholder="Mã ca hoặc triệu chứng" /></label>
          </div>
          <div class="filter-card shift-card">
            <span class="section-label">Ca trực</span>
            <div>Đang trực<br /><small>Đã duyệt hôm nay: <b id="done-today">0</b> ca</small></div>
            <button class="secondary-button btn-sm wide" type="button" data-refresh style="margin-top:12px">${icon("retry", 15)}<span>Làm mới</span></button>
          </div>
        </aside>

        <section>
          <div class="queue-head">
            <div>
              <h1>Tất cả ca</h1>
              <p>Ca có red flag luôn được hiển thị trước để nhân viên y tế nắm tình huống.</p>
            </div>
            <span class="polling-chip">${icon("retry", 15)}<span id="queue-updated">Làm mới (polling tự động)</span></span>
          </div>
          <div class="banner is-warning" id="queue-message" hidden>${icon("warning", 19)}<span class="banner-text"></span><button class="secondary-button btn-sm" type="button" data-refresh>${icon("retry", 15)}<span>Thử lại</span></button></div>
          <div id="queue-list" class="queue-table"></div>
        </section>
      </div>
    </main>
  </section>`;

  bindAccountMenu(root, { logout, onProfileSaved: () => renderNurseQueue(root, { navigate, logout }) });
  root.querySelectorAll("[data-refresh]").forEach((button) => button.addEventListener("click", () => refreshQueue(root, { navigate, logout })));
  root.querySelector("#queue-search").addEventListener("input", () => paintQueue(root, { navigate, logout }));
  root.querySelectorAll("[data-filter]").forEach((button) =>
    button.addEventListener("click", () => {
      root.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("is-active", item === button));
      root.dataset.filter = button.dataset.filter;
      paintQueue(root, { navigate, logout });
    }),
  );
  root.dataset.filter = "all";
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
  const filter = root.dataset.filter || "pending";
  const query = root.querySelector("#queue-search").value.trim().toLocaleLowerCase("vi-VN");
  const counts = { pending: 0, Emergency: 0, Urgent: 0, "Self-care": 0, done: 0 };
  for (const item of state.queue) {
    if (needsNurseAttention(item)) counts.pending += 1;
    if (completedStatuses.has(item.status) && item.status !== "escalated") counts.done += 1;
    const level = priority(item);
    if (level in counts) counts[level] += 1;
  }
  root.querySelector("#pending-count").textContent = counts.pending;
  root.querySelector("#all-count").textContent = state.queue.length;
  root.querySelector("#emergency-count").textContent = counts.Emergency;
  root.querySelector("#urgent-count").textContent = counts.Urgent;
  root.querySelector("#selfcare-count").textContent = counts["Self-care"];
  root.querySelector("#done-today").textContent = counts.done;

  const items = state.queue
    .filter((item) => {
      if (filter === "pending" && !needsNurseAttention(item)) return false;
      if (filter !== "pending" && filter !== "all" && priority(item) !== filter) return false;
      if (!query) return true;
      return [item.case_id, complaint(item), priorityLabels[priority(item)], statusLabels[item.status], item.red_flags?.length ? "red flag" : ""].join(" ").toLocaleLowerCase("vi-VN").includes(query);
    })
    .sort(compareCases);

  const list = root.querySelector("#queue-list");
  if (!items.length) {
    list.innerHTML = `<div class="queue-empty"><span class="state-icon is-ok">${icon("check", 32)}</span><h2>Không có ca nào đang chờ duyệt 🎉</h2><p>Danh sách sẽ tự cập nhật khi có ca mới.</p></div>`;
    return;
  }
  const header = `<div class="queue-head-row"><span></span><span class="col-label">Mã bệnh nhân</span><span class="col-label">Nhóm triệu chứng</span><span class="col-label">Mức ưu tiên AI</span><span class="col-label align-right">Thời gian chờ</span><span></span></div>`;
  list.innerHTML = header + items.map(queueRow).join("");
  list.querySelectorAll("[data-case]").forEach((button) => button.addEventListener("click", () => loadCase(button.dataset.case, { navigate, logout })));
}

function queueRow(item) {
  const level = priority(item);
  const hasRedFlag = item.status === "escalated" || Boolean(item.red_flags?.length);
  const emergency = level === "Emergency" || hasRedFlag;
  return `<button class="queue-row ${emergency ? "is-emergency" : ""}" type="button" data-case="${item.case_id}">
    ${priorityDot(level)}
    <span class="case-code">${shortCaseId(item.case_id)}</span>
    <span class="group">${escapeHtml(complaint(item))}</span>
    <span class="signal">
      <span class="priority-badge ${priorityClass(emergency ? "Emergency" : level)}">${emergency ? icon("warning", 13) : ""}${priorityLabels[emergency ? "Emergency" : level] || level}</span>
      ${hasRedFlag ? `<span class="redflag-queue-tag">Red flag</span>` : ""}
      ${confidenceMarkup(item.triage_proposal?.confidence)}
    </span>
    <span class="wait">${waitingLabel(item.created_at)}${slaBadge(item)}</span>
    <span class="go">Duyệt ca →</span>
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
  if (!item) { navigate("nurse-queue"); return; }
  const summary = item.summary || {};
  const structured = item.structured_data || {};
  const validation = item.validation || {};
  const proposal = item.triage_proposal || {};
  const missing = summary.missing_information || validation.missing_fields || structured.missing_fields || [];
  const isDone = completedStatuses.has(item.status);
  const isChatting = item.status === "needs_more_info";
  const level = priority(item);
  const confidence = aiConfidence(proposal.confidence);

  // Trạng thái "lỗi lưu" của thiết kế thay nút "Về hàng đợi" bằng chip khoá — cố ý: khi chưa lưu
  // được quyết định thì rời màn hình là mất nó.
  const headerRight = state.nurseSaveError
    ? `<span class="header-meta"><span class="pill is-muted">${icon("lock", 15)}<span>Đang khoá — chưa lưu được quyết định</span></span></span>`
    : `<div class="header-right"><button class="back-button" type="button" data-back>${icon("chevronLeft", 15)}<span>Về hàng đợi</span></button>${accountMenu()}</div>`;

  root.innerHTML = `<section class="app-shell">
    ${nurseHeader("", { title: `Duyệt ca <b>${shortCaseId(item.case_id)}</b> · chờ ${waitingLabel(item.created_at)}`, right: headerRight })}
    <main class="page">
      <form id="review-form" class="review-grid">
        <div class="review-main">
          <section class="record-card" id="intake-summary">
            <div class="record-head"><b>Phiếu tóm tắt · Nhóm: ${escapeHtml(symptomGroupLabels[structured.symptom_group] || "Chưa xác định")}</b><span>Tạo lúc ${formatDate(item.created_at)}</span></div>
            <div class="record-body">
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
            <div class="record-head"><b>Phiếu bàn giao (ISBAR)</b></div>
            <div class="record-body"><p class="muted-copy">Đang tải…</p></div>
          </section>

          ${graphDecisionBlock(item)}
          ${sourceSupportCard(item)}

          <section class="record-card">
            <div class="record-head"><b>Hội thoại với trợ lý</b></div>
            <div class="transcript">${conversation(item.conversation)}</div>
          </section>
        </div>

        <div class="review-side">
          <div class="banner is-error" id="review-error" role="alert" hidden>${icon("alert", 19)}<span class="banner-text"></span></div>
          ${redFlagCallout(item, isDone)}

          <div class="ai-priority-card ${priorityClass(level)}">
            <div class="ai-priority-head">
              <span class="section-label">Mức ưu tiên AI đề xuất</span>
              ${confidence ? `<span class="conf-chip is-${confidence.key}"><span class="dot"></span>Độ tin cậy: ${confidence.label}</span>` : ""}
            </div>
            <div class="ai-priority-value">${priorityDot(level)}<b>${priorityLabels[level] || level}</b></div>
            <p>Quyết định cuối cùng thuộc về nhân viên y tế.</p>
          </div>

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

  root.querySelector("[data-back]")?.addEventListener("click", () => navigate("nurse-queue"));
  bindAccountMenu(root, { logout, onProfileSaved: () => renderNurseCase(root, { navigate, logout }) });
  bindRedFlagEditor(root);
  bindReviewActions(root, { navigate, logout, currentPriority: level });
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
function collectedFields(item, fallbackMissing) {
  const rows = item?.summary_fields || [];
  if (rows.length) {
    return rows
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

function needsNurseAttention(item) { return pendingStatuses.has(item.status) || item.status === "escalated"; }

function priority(item) { return item.triage_proposal?.priority || "Manual review"; }

// Nhãn của agent quyết định (src/graph_triage/) dùng bộ 3 mức riêng, KHÔNG phải TriagePriority của
// rule engine. Cố tình không ánh xạ sang TriagePriority: hai thang này không được lẫn vào nhau.
const graphLabels = { theo_doi_tai_nha: "Theo dõi tại nhà", kham_som: "Khám sớm", cap_cuu: "Cấp cứu" };

/** Ý kiến tham khảo THỨ HAI. Chỉ hiện kết luận cuối của LLM - không hiện xác suất từng model, không
 *  hiện evidence graph. Không được đưa giá trị này vào ô "Mức ưu tiên" của form duyệt. */
function graphDecisionBlock(item) {
  const decision = item.graph_decision;
  if (!decision) return "";
  const label = graphLabels[decision.triage_label] || decision.triage_label || "Không xác định";
  const review = decision.requires_human_review ? `<p class="advisory-review">Mô hình đề nghị bắt buộc có người xem lại.</p>` : "";
  return `<section class="advisory-card"><h3>Ý kiến tham khảo từ mô hình</h3><p class="advisory-note">Đây là ý kiến thứ hai, độc lập với đề xuất mức ưu tiên ở cột bên phải. Quyết định vẫn thuộc về bạn.</p><p class="advisory-label">Mức đề xuất: <strong>${escapeHtml(label)}</strong></p><p class="advisory-summary">${escapeHtml(decision.decision_summary || "")}</p>${review}<p class="advisory-disclaimer">${escapeHtml(decision.disclaimer || "")}</p></section>`;
}
/** Khối nguồn y văn ĐỌC-CHỈ của part 3 (src/source_support/), tách biệt khỏi ô nháp phản hồi bệnh
 *  nhân - trước đây trích dẫn chỉ lẫn vào text của `sourceSupportDraft()` nên điều dưỡng không có
 *  chỗ nào xem nguồn mà không đụng vào bản nháp có thể sửa. Card này KHÔNG được đưa vào form duyệt
 *  (không có `name=`), chỉ để đọc trước khi sửa ô phản hồi. */
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

/** Khối nguồn y văn của part 3 (src/source_support/), dựng lại đúng như `explanation_vi` +
 *  `explanation_citations` - `explanation_vi` chỉ mang marker [n], phần liệt kê URL do phía hiển thị
 *  tự ghép (prompt bước 7 cấm model tự viết URL vào đoạn văn). */
function sourceSupportDraft(item) {
  const support = item.graph_decision?.source_support;
  if (!support?.explanation_vi) return "";
  const sources = (support.explanation_citations || [])
    .map((cite) => {
      const quote = String(cite.quote || "").split(/\s+/).join(" ").trim();
      return `${cite.marker} ${cite.publisher || cite.title || "nguồn"} · ${cite.url}\n    "${quote}"`;
    })
    .join("\n");
  return sources ? `${support.explanation_vi}\n\nNguồn tham khảo:\n${sources}` : support.explanation_vi;
}

/** Nội dung mặc định của ô "Phản hồi gửi bệnh nhân". ĐÂY LÀ BẢN NHÁP, KHÔNG PHẢI ĐƯỜNG GỬI: part 3
 *  chỉ đổ vào ô soạn thảo để điều dưỡng đọc, sửa rồi bấm duyệt. Không có đường nào ghi thẳng vào
 *  `patient_visible_response` - làm vậy sẽ khiến ca ESCALATED gửi thẳng cho bệnh nhân không qua ai.
 *
 *  Part 3 nằm TRÊN, nội dung cũ nằm DƯỚI: với ca red-flag, `patient_visible_response` đang giữ
 *  EMERGENCY_MESSAGE cố định (triage_pipeline._build_patient_safe_response) và câu đó không được mất. */
function patientDraft(item, isDone) {
  const stored = item.patient_visible_response;
  if (isDone) return stored || "";
  const draft = sourceSupportDraft(item);
  const base = stored || defaultResponse(priority(item));
  return draft ? `${draft}\n\n${base}` : base;
}

function complaint(item) { return item.summary?.chief_complaint || symptomGroupLabels[item.structured_data?.symptom_group] || "Triệu chứng chung"; }
function compareCases(left, right) { const ranks = { Emergency: 0, Urgent: 1, "Manual review": 2, Routine: 3, "Self-care": 4 }; return (ranks[priority(left)] ?? 9) - (ranks[priority(right)] ?? 9) || new Date(left.created_at) - new Date(right.created_at); }

function conversation(items = []) {
  if (!items.length) return `<p class="muted-copy">Chưa có lịch sử trao đổi.</p>`;
  return items
    .map((item) => {
      const role = item.role === "patient" ? "patient" : item.role === "agent" ? "agent" : "system";
      return `<div class="bubble is-${role}">${escapeHtml(item.content)}</div>`;
    })
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
    ? `<div class="field-row is-block"><span class="label">Tóm tắt văn xuôi</span><span class="value">${escapeHtml(data.narrative)}</span></div>`
    : "";
  const denied = (fields.denied || []).length
    ? `<div class="field-row"><span class="label">Người bệnh phủ nhận</span><span class="value">${escapeHtml(fields.denied.join(", "))}</span></div>`
    : "";
  const unknown = (fields.unknown_safety || []).length
    ? `<div class="field-row is-missing"><span class="label">Chưa xác định được (dấu hiệu an toàn)</span><span class="value">${escapeHtml(fields.unknown_safety.join(", "))}</span></div>`
    : "";
  return `${narrative}${denied}${unknown}`;
}
