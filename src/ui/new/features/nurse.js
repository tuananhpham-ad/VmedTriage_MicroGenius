import { api } from "../api.js";
import { accountMenu, bindAccountMenu } from "./account.js?v=settings-full-20260813";
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
  list.innerHTML = items.map((item) => `<button class="queue-row ${priorityClass(priority(item))}" type="button" data-case="${item.case_id}" role="listitem"><div><span class="case-code">Ca ${shortCaseId(item.case_id)}</span><strong>${escapeHtml(complaint(item))}</strong></div><span class="priority-badge ${priorityClass(priority(item))}">${priorityLabels[priority(item)] || priority(item)}</span><span class="queue-meta">${statusLabels[item.status] || item.status}<small>Chờ ${waitingLabel(item.created_at)}</small>${slaBadge(item)}</span></button>`).join("");
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
  root.innerHTML = `<section class="app-shell nurse-shell"><header class="app-header"><a class="brand" href="/">${logo()}</a><nav aria-label="Điều hướng nhân viên y tế"><button class="nav-link" type="button" data-back>Hàng đợi ca</button><button class="nav-link is-active" type="button">Duyệt ca</button></nav>${accountMenu()}</header><main class="review-layout"><section class="case-record"><header class="record-header"><div><p class="eyebrow">Phiếu tóm tắt</p><h1>Ca ${shortCaseId(item.case_id)}</h1><p>${formatDate(item.created_at)}</p></div><div><span class="status-badge ${statusClass(item.status)}">${statusLabels[item.status] || item.status}</span><span class="priority-badge ${priorityClass(priority(item))}">${priorityLabels[priority(item)] || priority(item)}</span></div></header>${redFlagEditor(item, isDone)}${graphDecisionBlock(item)}<section class="record-section"><h2>Thông tin lâm sàng đã thu thập</h2><dl class="clinical-grid">${editableField("summary.chief_complaint", "Triệu chứng chính", summary.chief_complaint || symptomGroupLabels[structured.symptom_group] || "", isDone)}${editableField("summary.onset", "Khởi phát", summary.onset || "", isDone)}${editableField("summary.severity", "Mức độ", summary.severity ?? "", isDone)}${clinicalField("Độ tin cậy", Number.isFinite(structured.confidence) ? `${Math.round(structured.confidence * 100)}%` : "Chưa có")}</dl><div class="detail-group"><h3>Triệu chứng đi kèm</h3><div class="tag-list">${tags(summary.associated_symptoms, "Chưa ghi nhận")}</div></div>${intakeChecklistMarkup(item, missing)}</section><section class="record-section"><h2>Hội thoại</h2><div class="review-conversation">${conversation(item.conversation)}</div></section></section><aside class="review-actions"><p class="eyebrow">Xác nhận của nhân viên y tế</p><h2>Quyết định xử trí</h2><p>Phản hồi chỉ được gửi đến bệnh nhân sau khi bạn xác nhận.</p><form id="review-form" class="review-form"><label>Mức ưu tiên<select name="edited_priority" ${isDone ? "disabled" : ""}>${["Emergency", "Urgent", "Routine", "Self-care"].map((option) => `<option value="${option}" ${option === priority(item) ? "selected" : ""}>${priorityLabels[option]}</option>`).join("")}</select></label><label>Phản hồi gửi bệnh nhân<textarea name="approved_response" rows="7" required ${isDone ? "disabled" : ""}>${escapeHtml(item.patient_visible_response || defaultResponse(priority(item)))}</textarea></label><label>Ghi chú nội bộ <span>(không bắt buộc)</span><textarea name="nurse_notes" rows="3" ${isDone ? "disabled" : ""}></textarea></label><p id="review-error" class="form-error" role="alert">${isDone ? "Ca này đã được xử lý và không thể thay đổi." : ""}</p><div class="review-buttons"><button class="primary-button" type="submit" ${isDone ? "disabled" : ""}>Duyệt và gửi</button><button class="secondary-button" type="button" data-ask ${isDone ? "disabled" : ""}>Yêu cầu bổ sung</button><button class="danger-button" type="button" data-escalate ${isDone ? "disabled" : ""}>Chuyển cấp cứu</button></div></form></aside></main></section>`;
  root.querySelector("[data-back]").addEventListener("click", () => navigate("nurse-queue"));
  bindRedFlagEditor(root);
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
  const edits = collectFieldEdits(document.querySelector("#app"), item);
  if (edits.error) { error.textContent = edits.error; return; }
  const payload = { action, nurse_notes: String(values.get("nurse_notes") || "").trim() || null, field_edits: edits.list };
  if (action === "ask_more") payload.ask_more_question = response;
  else payload.approved_response = response;
  if (action === "edit") payload.edited_priority = editedPriority;
  try { await api(`/api/v1/cases/${item.case_id}/review`, { method: "POST", body: JSON.stringify(payload) }); state.selectedNurseCase = await api(`/api/v1/cases/${item.case_id}`); showToast(requested === "escalate" ? "Đã chuyển ca sang mức cấp cứu." : "Đã lưu quyết định."); renderNurseCase(document.querySelector("#app"), context); } catch (problem) { error.textContent = problem.message || "Không thể lưu quyết định."; }
}

// Chuyển từ `patient.js` (2026-08-14) - xem ghi chú ở đó. Bên bệnh nhân nó phơi checklist nội bộ ra
// cho người không cần đọc; bên điều dưỡng thì đây đúng là thứ cần trước khi bấm duyệt.
//
// Agent trả `summary_fields` với NHÃN tiếng Việt sẵn kèm cờ `is_missing` - dùng thẳng. Vẫn KHÔNG
// hiển thị giá trị thô (`alert`, `none_gt_6h`) ở đây: bảng "Thông tin lâm sàng đã thu thập" ngay
// phía trên đã là chỗ hiển thị giá trị, còn khối này chỉ trả lời một câu hỏi - "đã hỏi đủ chưa".
//
// Rơi về `missing_fields` (danh sách KEY thô) khi phiên chưa dựng được `summary_fields`: điều dưỡng
// đọc `urine_output` vẫn hiểu, khác hẳn bệnh nhân - nên nhánh dự phòng này giữ nguyên ở đây.
function intakeChecklistMarkup(item, fallbackMissing) {
  const rows = item?.summary_fields || [];
  if (rows.length) {
    const collected = rows.filter((row) => !row.is_missing);
    const missing = rows.filter((row) => row.is_missing);
    const heading = `<h3>Tiến độ thu thập <span>(${collected.length}/${rows.length})</span></h3>`;
    const list = [...missing, ...collected]
      .map((row) => `<div class="check-row"><span>${row.is_missing ? "○" : "✓"}</span>${escapeHtml(row.label)}</div>`)
      .join("");
    return `<div class="detail-group ${missing.length ? "is-missing" : ""}">${heading}${list}</div>`;
  }
  if (!fallbackMissing.length) return "";
  return `<div class="detail-group is-missing"><h3>Thông tin còn thiếu</h3><div class="tag-list">${tags(fallbackMissing)}</div></div>`;
}

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
  return `<section class="record-section advisory-block"><h2>Ý kiến tham khảo từ mô hình</h2><p class="advisory-note">Đây là ý kiến thứ hai, độc lập với đề xuất mức ưu tiên ở cột bên phải. Quyết định vẫn thuộc về bạn.</p><p class="advisory-label">Mức đề xuất: <strong>${escapeHtml(label)}</strong></p><p class="advisory-summary">${escapeHtml(decision.decision_summary || "")}</p>${review}<p class="advisory-disclaimer">${escapeHtml(decision.disclaimer || "")}</p></section>`;
}
function complaint(item) { return item.summary?.chief_complaint || symptomGroupLabels[item.structured_data?.symptom_group] || "Triệu chứng chung"; }
function compareCases(left, right) { const ranks = { Emergency: 0, Urgent: 1, "Manual review": 2, Routine: 3, "Self-care": 4 }; return (ranks[priority(left)] ?? 9) - (ranks[priority(right)] ?? 9) || new Date(left.created_at) - new Date(right.created_at); }
function clinicalField(label, value) { return `<div><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>`; }
function tags(values = [], empty = "") { return values.length ? values.map((value) => `<span>${escapeHtml(String(value).replaceAll("_", " "))}</span>`).join("") : `<span class="tag-empty">${empty}</span>`; }
function conversation(items = []) { return items.length ? items.map((item) => `<div class="review-message is-${escapeHtml(item.role)}"><strong>${item.role === "patient" ? "Bệnh nhân" : item.role === "nurse" ? "Nhân viên y tế" : "Hệ thống"}</strong><span>${escapeHtml(item.content)}</span></div>`).join("") : "<p class=\"muted-copy\">Chưa có lịch sử trao đổi.</p>"; }
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

function redFlagEditor(item, isDone) {
  const flags = item.red_flags || [];
  const notice = item.emergency_notice_sent
    ? `<p class="red-flag-notice">Thông điệp cấp cứu ĐÃ hiển thị cho bệnh nhân. Hạ cờ bây giờ chỉ đổi phiếu và luồng xử trí - không thu hồi được nội dung bệnh nhân đã đọc.</p>`
    : "";
  if (!flags.length) return "";
  const rows = flags.map((flag) => {
    const code = flag.code || "";
    const lowered = isLowered(item, code);
    return `<div class="red-flag-row" data-flag="${escapeHtml(code)}"><label><input type="checkbox" data-flag-active ${lowered ? "" : "checked"} ${isDone ? "disabled" : ""} /> ${escapeHtml(flag.label || code)}</label><input class="red-flag-reason" data-flag-reason placeholder="Lý do hạ dấu hiệu này (bắt buộc)" ${lowered ? "" : "hidden"} ${isDone ? "disabled" : ""} /></div>`;
  }).join("");
  return `<div class="red-flag-alert"><strong>Ca có dấu hiệu nguy hiểm</strong>${notice}${rows}</div>`;
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
  return `<div><dt>${label}</dt><dd><input class="clinical-input" data-edit-field="${path}" data-original="${escapeHtml(String(value))}" value="${escapeHtml(String(value))}" ${isDone ? "disabled" : ""} /></dd></div>`;
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
