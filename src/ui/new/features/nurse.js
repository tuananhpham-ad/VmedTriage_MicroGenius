import { api } from "../api.js";
import { accountMenu, bindAccountMenu } from "./account.js";
import { completedStatuses, pendingStatuses, state } from "../state.js";
import { escapeHtml, formatDate, logo, priorityClass, priorityLabels, shortCaseId, showToast, statusClass, statusLabels, symptomGroupLabels, waitingLabel } from "../shared.js";

let polling = null;

export function stopQueuePolling() {
  if (polling) window.clearInterval(polling);
  polling = null;
}

export function renderNurseQueue(root, { navigate, logout }) {
  root.innerHTML = `<section class="app-shell nurse-shell"><header class="app-header"><a class="brand" href="/">${logo()}</a><nav aria-label="Điều hướng nhân viên y tế"><button class="nav-link is-active" type="button">Hàng đợi ca</button></nav>${accountMenu()}</header><main class="nurse-layout"><aside class="queue-filter"><p class="eyebrow">Điều hướng</p><h1>Ca cần xử lý</h1><button class="filter-button is-active" type="button" data-filter="pending">Đang chờ duyệt <b id="pending-count">0</b></button><button class="filter-button" type="button" data-filter="all">Tất cả ca <b id="all-count">0</b></button><button class="filter-button" type="button" data-filter="emergency">Cấp cứu <b id="emergency-count">0</b></button><label>Tìm ca<input id="queue-search" placeholder="Mã ca hoặc triệu chứng" /></label><button class="secondary-button wide" type="button" data-refresh>Làm mới</button></aside><section class="queue-content"><header class="queue-heading"><div><p class="eyebrow">Hàng đợi triage</p><h2>Danh sách ca chờ duyệt</h2><p id="queue-updated">Đang tải dữ liệu</p></div></header><div id="queue-message" class="queue-message" hidden></div><div id="queue-list" class="queue-list" role="list"></div></section></main></section>`;
  bindAccountMenu(root, { logout, onProfileSaved: () => renderNurseQueue(root, { navigate, logout }) });
  root.querySelector("[data-refresh]").addEventListener("click", () => refreshQueue(root, { navigate, logout }));
  root.querySelector("#queue-search").addEventListener("input", () => paintQueue(root, { navigate, logout }));
  root.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => { root.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("is-active", item === button)); root.dataset.filter = button.dataset.filter; paintQueue(root, { navigate, logout }); }));
  root.dataset.filter = "pending";
  refreshQueue(root, { navigate, logout });
  polling = window.setInterval(() => refreshQueue(root, { navigate, logout, silent: true }), 15000);
}

export async function refreshQueue(root, context) {
  const refresh = root.querySelector("[data-refresh]");
  if (!context.silent) { refresh.disabled = true; refresh.textContent = "Đang tải"; }
  try {
    state.queue = await api("/api/v1/nurse/queue");
    root.querySelector("#queue-updated").textContent = `Cập nhật lúc ${formatDate(new Date())}`;
    paintQueue(root, context);
  } catch (problem) {
    const message = root.querySelector("#queue-message");
    message.hidden = false; message.className = "queue-message is-error"; message.textContent = problem.message || "Không thể tải hàng đợi.";
  } finally {
    if (!context.silent) { refresh.disabled = false; refresh.textContent = "Làm mới"; }
  }
}

function paintQueue(root, { navigate, logout }) {
  const filter = root.dataset.filter || "pending";
  const query = root.querySelector("#queue-search").value.trim().toLocaleLowerCase("vi-VN");
  const pending = state.queue.filter((item) => pendingStatuses.has(item.status));
  root.querySelector("#pending-count").textContent = pending.length;
  root.querySelector("#all-count").textContent = state.queue.length;
  root.querySelector("#emergency-count").textContent = state.queue.filter((item) => priority(item) === "Emergency").length;
  const items = state.queue.filter((item) => {
    if (filter === "pending" && !pendingStatuses.has(item.status)) return false;
    if (filter === "emergency" && priority(item) !== "Emergency") return false;
    if (!query) return true;
    return [item.case_id, complaint(item), priorityLabels[priority(item)], statusLabels[item.status]].join(" ").toLocaleLowerCase("vi-VN").includes(query);
  }).sort(compareCases);
  const list = root.querySelector("#queue-list");
  const message = root.querySelector("#queue-message");
  if (!items.length) { message.hidden = false; message.className = "queue-message"; message.innerHTML = "<strong>Không có ca phù hợp</strong><span>Danh sách sẽ được cập nhật tự động.</span>"; list.replaceChildren(); return; }
  message.hidden = true;
  list.innerHTML = items.map((item) => `<button class="queue-row ${priorityClass(priority(item))}" type="button" data-case="${item.case_id}" role="listitem"><div><span class="case-code">Ca ${shortCaseId(item.case_id)}</span><strong>${escapeHtml(complaint(item))}</strong></div><span class="priority-badge ${priorityClass(priority(item))}">${priorityLabels[priority(item)] || priority(item)}</span><span class="queue-meta">${statusLabels[item.status] || item.status}<small>Chờ ${waitingLabel(item.created_at)}</small></span></button>`).join("");
  list.querySelectorAll("[data-case]").forEach((button) => button.addEventListener("click", () => loadCase(button.dataset.case, { navigate, logout })));
}

async function loadCase(caseId, { navigate, logout }) {
  try { state.selectedNurseCase = await api(`/api/v1/cases/${caseId}`); sessionStorage.setItem("vmed_active_nurse_case_id", caseId); navigate("nurse-case"); } catch (problem) { showToast(problem.message, true); }
}

export function renderNurseCase(root, { navigate, logout }) {
  const item = state.selectedNurseCase;
  if (!item) { navigate("nurse-queue"); return; }
  const summary = item.summary || {};
  const structured = item.structured_data || {};
  const validation = item.validation || {};
  const proposal = item.triage_proposal || {};
  const missing = summary.missing_information || validation.missing_fields || structured.missing_fields || [];
  const isDone = completedStatuses.has(item.status);
  root.innerHTML = `<section class="app-shell nurse-shell"><header class="app-header"><a class="brand" href="/">${logo()}</a><nav aria-label="Điều hướng nhân viên y tế"><button class="nav-link" type="button" data-back>Hàng đợi ca</button><button class="nav-link is-active" type="button">Duyệt ca</button></nav>${accountMenu()}</header><main class="review-layout"><section class="case-record"><header class="record-header"><div><p class="eyebrow">Phiếu tóm tắt</p><h1>Ca ${shortCaseId(item.case_id)}</h1><p>${formatDate(item.created_at)}</p></div><div><span class="status-badge ${statusClass(item.status)}">${statusLabels[item.status] || item.status}</span><span class="priority-badge ${priorityClass(priority(item))}">${priorityLabels[priority(item)] || priority(item)}</span></div></header>${item.red_flags?.length ? `<div class="red-flag-alert">Ca có dấu hiệu nguy hiểm: ${item.red_flags.map((flag) => escapeHtml(flag.label || flag.code)).join(", ")}</div>` : ""}<section class="record-section"><h2>Thông tin lâm sàng đã thu thập</h2><dl class="clinical-grid">${clinicalField("Triệu chứng chính", summary.chief_complaint || symptomGroupLabels[structured.symptom_group] || "Chưa ghi nhận")}${clinicalField("Khởi phát", summary.onset || "Thiếu thông tin")}${clinicalField("Mức độ", summary.severity || "Thiếu thông tin")}${clinicalField("Độ tin cậy", Number.isFinite(structured.confidence) ? `${Math.round(structured.confidence * 100)}%` : "Chưa có")}</dl><div class="detail-group"><h3>Triệu chứng đi kèm</h3><div class="tag-list">${tags(summary.associated_symptoms, "Chưa ghi nhận")}</div></div>${missing.length ? `<div class="detail-group is-missing"><h3>Thông tin còn thiếu</h3><div class="tag-list">${tags(missing)}</div></div>` : ""}</section><section class="record-section"><h2>Hội thoại</h2><div class="review-conversation">${conversation(item.conversation)}</div></section></section><aside class="review-actions"><p class="eyebrow">Xác nhận của nhân viên y tế</p><h2>Quyết định xử trí</h2><p>Phản hồi chỉ được gửi đến bệnh nhân sau khi bạn xác nhận.</p><form id="review-form" class="review-form"><label>Mức ưu tiên<select name="edited_priority" ${isDone ? "disabled" : ""}>${["Emergency", "Urgent", "Routine", "Self-care"].map((option) => `<option value="${option}" ${option === priority(item) ? "selected" : ""}>${priorityLabels[option]}</option>`).join("")}</select></label><label>Phản hồi gửi bệnh nhân<textarea name="approved_response" rows="7" required ${isDone ? "disabled" : ""}>${escapeHtml(item.patient_visible_response || defaultResponse(priority(item)))}</textarea></label><label>Ghi chú nội bộ <span>(không bắt buộc)</span><textarea name="nurse_notes" rows="3" ${isDone ? "disabled" : ""}></textarea></label><p id="review-error" class="form-error" role="alert">${isDone ? "Ca này đã được xử lý và không thể thay đổi." : ""}</p><div class="review-buttons"><button class="primary-button" type="submit" ${isDone ? "disabled" : ""}>Duyệt và gửi</button><button class="secondary-button" type="button" data-ask ${isDone ? "disabled" : ""}>Yêu cầu bổ sung</button><button class="danger-button" type="button" data-escalate ${isDone ? "disabled" : ""}>Chuyển cấp cứu</button></div></form></aside></main></section>`;
  root.querySelector("[data-back]").addEventListener("click", () => navigate("nurse-queue"));
  bindAccountMenu(root, { logout, onProfileSaved: () => renderNurseCase(root, { navigate, logout }) });
  root.querySelector("#review-form").addEventListener("submit", (event) => review(event, "approve", { navigate, logout }));
  root.querySelector("[data-ask]").addEventListener("click", () => review(root.querySelector("#review-form"), "ask_more", { navigate, logout }));
  root.querySelector("[data-escalate]").addEventListener("click", () => review(root.querySelector("#review-form"), "escalate", { navigate, logout }));
}

async function review(eventOrForm, requested, context) {
  eventOrForm.preventDefault?.();
  const form = eventOrForm.currentTarget || eventOrForm;
  const item = state.selectedNurseCase;
  const values = new FormData(form);
  const error = form.querySelector("#review-error");
  const response = String(values.get("approved_response") || "").trim();
  if (!response) { error.textContent = "Vui lòng nhập phản hồi dành cho bệnh nhân."; return; }
  let action = requested;
  let editedPriority = values.get("edited_priority");
  if (requested === "approve" && editedPriority !== priority(item)) action = "edit";
  if (requested === "escalate") { action = "edit"; editedPriority = "Emergency"; }
  const payload = { action, nurse_notes: String(values.get("nurse_notes") || "").trim() || null };
  if (action === "ask_more") payload.ask_more_question = response;
  else payload.approved_response = response;
  if (action === "edit") payload.edited_priority = editedPriority;
  try { await api(`/api/v1/cases/${item.case_id}/review`, { method: "POST", body: JSON.stringify(payload) }); state.selectedNurseCase = await api(`/api/v1/cases/${item.case_id}`); showToast(requested === "escalate" ? "Đã chuyển ca sang mức cấp cứu." : "Đã lưu quyết định."); renderNurseCase(document.querySelector("#app"), context); } catch (problem) { error.textContent = problem.message || "Không thể lưu quyết định."; }
}

function priority(item) { return item.triage_proposal?.priority || "Manual review"; }
function complaint(item) { return item.summary?.chief_complaint || symptomGroupLabels[item.structured_data?.symptom_group] || "Triệu chứng chung"; }
function compareCases(left, right) { const ranks = { Emergency: 0, Urgent: 1, "Manual review": 2, Routine: 3, "Self-care": 4 }; return (ranks[priority(left)] ?? 9) - (ranks[priority(right)] ?? 9) || new Date(left.created_at) - new Date(right.created_at); }
function clinicalField(label, value) { return `<div><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>`; }
function tags(values = [], empty = "") { return values.length ? values.map((value) => `<span>${escapeHtml(String(value).replaceAll("_", " "))}</span>`).join("") : `<span class="tag-empty">${empty}</span>`; }
function conversation(items = []) { return items.length ? items.map((item) => `<div class="review-message is-${escapeHtml(item.role)}"><strong>${item.role === "patient" ? "Bệnh nhân" : item.role === "nurse" ? "Nhân viên y tế" : "Hệ thống"}</strong><span>${escapeHtml(item.content)}</span></div>`).join("") : "<p class=\"muted-copy\">Chưa có lịch sử trao đổi.</p>"; }
function defaultResponse(priorityValue) { if (priorityValue === "Emergency") return "Nhân viên y tế đã xem thông tin. Hãy gọi 115 hoặc đến cơ sở y tế gần nhất ngay nếu triệu chứng đang diễn ra."; if (priorityValue === "Urgent") return "Nhân viên y tế khuyến nghị bạn được khám sớm. Hãy gọi 115 nếu triệu chứng nặng lên."; return "Nhân viên y tế đã xem thông tin bạn cung cấp. Hãy tiếp tục theo dõi và liên hệ cơ sở y tế nếu triệu chứng nặng hơn."; }
