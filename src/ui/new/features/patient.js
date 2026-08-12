import { api } from "../api.js";
import { accountMenu, bindAccountMenu } from "./account.js";
import { setActiveCase, state } from "../state.js";
import { escapeHtml, logo, shortCaseId, showToast, statusClass, statusLabels, symptomGroupLabels } from "../shared.js";

const commonSymptoms = [
  ["Sốt", "Tôi bị sốt."], ["Đau bụng", "Tôi bị đau bụng."], ["Đau ngực", "Tôi bị đau ngực."], ["Khó thở", "Tôi cảm thấy khó thở."], ["Đau đầu", "Tôi bị đau đầu."],
];

export function renderPatientHome(root, { navigate, logout }) {
  const current = state.currentPatientCase;
  root.innerHTML = `<section class="app-shell patient-home"><header class="app-header"><a class="brand" href="/">${logo()}</a><nav aria-label="Điều hướng bệnh nhân"><button class="nav-link is-active" type="button">Trang chủ</button><button class="nav-link" type="button" data-start>Phiên khai báo</button></nav>${accountMenu()}</header><main class="page-content" id="patient-main"><section class="home-hero"><div><p class="eyebrow">Không gian bệnh nhân</p><h1>Bắt đầu khai báo triệu chứng.</h1><p>Trợ lý sẽ ghi nhận thông tin ban đầu. Hướng dẫn xử trí chỉ được gửi sau khi nhân viên y tế xác nhận.</p><button class="primary-button hero-button" type="button" data-start>Bắt đầu khai báo</button></div><aside class="safety-card"><strong>Trong trường hợp khẩn cấp</strong><p>Đau ngực dữ dội, khó thở nặng, co giật hoặc chảy máu không cầm được: gọi 115 ngay.</p></aside></section><section class="case-overview"><div class="section-heading"><div><h2>Ca đang mở</h2><p>Theo dõi trạng thái phiên khai báo gần nhất.</p></div>${current ? `<span class="status-badge ${statusClass(current.status)}">${statusLabels[current.status] || "Đang xử lý"}</span>` : ""}</div>${current ? currentCaseCard(current) : `<div class="empty-state"><strong>Chưa có ca nào đang mở</strong><span>Khi bắt đầu khai báo, tiến trình và kết quả đã duyệt sẽ xuất hiện tại đây.</span></div>`}</section><section class="history-overview"><div class="section-heading"><div><h2>Lịch sử phiên khai báo</h2><p>Các ca thuộc tài khoản của bạn.</p></div></div><div id="history-list" class="history-list"><p class="muted-copy">Đang tải lịch sử.</p></div></section><section class="feature-row"><article><strong>Khai báo triệu chứng</strong><span>Mô tả tự do hoặc chọn nhóm triệu chứng phổ biến.</span></article><article><strong>Kết quả đã duyệt</strong><span>Không hiển thị hướng dẫn cho đến khi có xác nhận của nhân viên y tế.</span></article><article><strong>Hồ sơ bảo mật</strong><span>Thông tin của bạn chỉ dùng cho mục đích phân luồng ban đầu.</span></article></section></main></section>`;
  root.querySelectorAll("[data-start]").forEach((button) => button.addEventListener("click", () => navigate("disclaimer")));
  bindAccountMenu(root, { logout, onProfileSaved: () => renderPatientHome(root, { navigate, logout }) });
  root.querySelector("[data-open-case]")?.addEventListener("click", () => renderPatientChat(root, { navigate, logout }));
  loadPatientHistory(root, { navigate, logout });
}

async function loadPatientHistory(root, { navigate, logout }) {
  const list = root.querySelector("#history-list");
  try {
    const cases = await api("/api/v1/patient/history");
    if (!cases.length) { list.innerHTML = `<p class="muted-copy">Chưa có phiên khai báo nào.</p>`; return; }
    list.innerHTML = cases.slice(0, 5).map((item) => `<button class="history-row" type="button" data-history-case="${item.case_id}"><span>${escapeHtml(item.summary?.chief_complaint || symptomGroupLabels[item.structured_data?.symptom_group] || "Triệu chứng chung")}</span><span class="status-badge ${statusClass(item.status)}">${statusLabels[item.status] || item.status}</span><small>${shortCaseId(item.case_id)}</small></button>`).join("");
    list.querySelectorAll("[data-history-case]").forEach((button) => button.addEventListener("click", async () => {
      try { state.currentPatientCase = await api(`/api/v1/cases/${button.dataset.historyCase}`); setActiveCase(state.currentPatientCase.case_id); state.patientMessages = initialMessages(state.currentPatientCase); renderPatientChat(root, { navigate, logout }); } catch (problem) { showToast(problem.message, true); }
    }));
  } catch (problem) {
    list.innerHTML = `<p class="muted-copy">Không thể tải lịch sử phiên khai báo.</p>`;
  }
}

function currentCaseCard(current) {
  const complaint = current.summary?.chief_complaint || symptomGroupLabels[current.structured_data?.symptom_group] || "Triệu chứng đang khai báo";
  const body = current.status === "approved" ? current.patient_visible_response || current.response : patientStatusHelp(current.status);
  return `<div class="case-card"><div><small>Mã ca</small><strong>${shortCaseId(current.case_id)}</strong></div><div><small>Triệu chứng chính</small><strong>${escapeHtml(complaint)}</strong></div><div><small>Trạng thái</small><span>${escapeHtml(body)}</span></div><button class="secondary-button" type="button" data-open-case>Xem chi tiết</button></div>`;
}

export function renderDisclaimer(root, { navigate, onAccept, logout }) {
  root.innerHTML = `<section class="disclaimer-shell"><div class="disclaimer-card"><a class="brand brand-large" href="/">${logo()}</a><p class="eyebrow">Trước khi bắt đầu</p><h1>Thông tin an toàn quan trọng</h1><p>VMedTriage hỗ trợ ghi nhận triệu chứng ban đầu, không thay thế chẩn đoán, khám trực tiếp hoặc dịch vụ cấp cứu.</p><ol><li>Không chờ phản hồi trực tuyến nếu triệu chứng trở nặng hoặc xuất hiện dấu hiệu nguy hiểm.</li><li>Gọi 115 hoặc đến cơ sở y tế gần nhất khi cần cấp cứu.</li><li>Chỉ cung cấp thông tin cần thiết để hỗ trợ phân luồng.</li></ol><div class="action-row"><button class="primary-button" type="button" data-accept>Tôi đã hiểu, bắt đầu</button><button class="secondary-button" type="button" data-back>Quay lại</button></div></div></section>`;
  root.querySelector("[data-accept]").addEventListener("click", onAccept);
  root.querySelector("[data-back]").addEventListener("click", () => navigate("patient-home"));
}

export function startPatientCase(root, { navigate, logout, fresh = false }) {
  if (fresh) {
    setActiveCase(null);
    state.currentPatientCase = null;
    state.patientMessages = [];
  }
  renderPatientChat(root, { navigate, logout });
}

export function renderPatientChat(root, { navigate, logout }) {
  const current = state.currentPatientCase;
  const messages = state.patientMessages.length ? state.patientMessages : initialMessages(current);
  root.innerHTML = `<section class="app-shell patient-chat"><header class="app-header"><a class="brand" href="/">${logo()}</a><nav aria-label="Điều hướng bệnh nhân"><button class="nav-link" type="button" data-home>Trang chủ</button><button class="nav-link is-active" type="button">Phiên khai báo</button></nav>${accountMenu()}</header><main class="chat-layout"><section class="chat-panel" aria-labelledby="chat-title"><header class="chat-header"><div><p class="eyebrow">Phiên tư vấn</p><h1 id="chat-title">Trao đổi với trợ lý y tế</h1></div><span class="case-reference">${shortCaseId(state.caseId)}</span></header><div class="chat-log" id="chat-log">${messages.map(messageMarkup).join("")}</div><div class="symptom-chips">${commonSymptoms.map(([label, value]) => `<button type="button" data-symptom="${escapeHtml(value)}">${label}</button>`).join("")}</div><form id="chat-form" class="chat-composer"><label class="sr-only" for="patient-message">Mô tả triệu chứng</label><textarea id="patient-message" name="message" rows="2" maxlength="5000" placeholder="Mô tả triệu chứng bạn đang gặp phải"></textarea><p class="form-error" id="chat-error" role="alert"></p><button class="primary-button" type="submit">Gửi</button></form></section><aside class="chat-sidebar"><section class="case-state-card"><p>Ca đang mở</p><strong>${current ? shortCaseId(current.case_id) : "Chưa bắt đầu"}</strong><span class="status-badge ${statusClass(current?.status)}">${statusLabels[current?.status] || "Đang khai báo"}</span><small>${patientStatusHelp(current?.status)}</small></section><section class="checklist-card"><h2>Thông tin cần làm rõ</h2><div id="checklist">${checklistMarkup(current)}</div></section><section class="safety-mini"><strong>Cần cấp cứu?</strong><span>Gọi 115 ngay, không chờ phản hồi trong ứng dụng.</span></section></aside></main>${current && current.status !== "collecting_information" ? outcomeMarkup(current) : ""}</section>`;
  root.querySelector("[data-home]").addEventListener("click", () => navigate("patient-home"));
  bindAccountMenu(root, { logout, onProfileSaved: () => renderPatientChat(root, { navigate, logout }) });
  root.querySelectorAll("[data-symptom]").forEach((button) => button.addEventListener("click", () => { root.querySelector("#patient-message").value = button.dataset.symptom; root.querySelector("#patient-message").focus(); }));
  root.querySelector("#chat-form").addEventListener("submit", (event) => submitMessage(event, root, { navigate, logout }));
  root.querySelector("[data-check-result]")?.addEventListener("click", () => checkResult(root, { navigate, logout }));
  root.querySelector("[data-new-case]")?.addEventListener("click", () => navigate("disclaimer"));
  root.querySelector("#patient-message").focus();
  scrollChat(root);
}

function initialMessages(current) {
  if (current?.conversation?.length) return current.conversation.map((item) => ({ role: item.role === "nurse" ? "system" : item.role, text: item.content }));
  return [{ role: "agent", text: "Xin chào, bạn hãy mô tả tự do triệu chứng bạn đang gặp phải." }];
}

function messageMarkup(message) { return `<div class="chat-message is-${escapeHtml(message.role)}">${escapeHtml(message.text)}</div>`; }

function checklistMarkup(current) {
  const missing = current?.validation?.missing_fields || current?.structured_data?.missing_fields || [];
  if (!missing.length) return `<p class="muted-copy">Trợ lý sẽ ghi nhận thông tin cần thiết khi bạn trò chuyện.</p>`;
  return missing.map((item) => `<div class="check-row"><span>○</span>${escapeHtml(item.replaceAll("_", " "))}</div>`).join("");
}

function outcomeMarkup(current) {
  const status = current.status;
  const approved = status === "approved";
  const emergency = status === "escalated";
  const heading = approved ? "Phản hồi đã được nhân viên y tế duyệt" : emergency ? "Ca đã được chuyển cấp cứu" : "Thông tin đang chờ nhân viên y tế duyệt";
  const body = approved ? current.patient_visible_response || current.response : emergency ? "Không chờ phản hồi trực tuyến nếu triệu chứng đang diễn ra. Hãy gọi 115 ngay." : "Hướng dẫn xử trí sẽ chỉ hiển thị sau khi có xác nhận của nhân viên y tế.";
  return `<section class="patient-outcome ${emergency ? "is-emergency" : ""}"><div><p class="eyebrow">${statusLabels[status] || "Đang xử lý"}</p><h2>${heading}</h2><p>${escapeHtml(body)}</p></div><div class="action-row">${!approved && !emergency ? '<button class="secondary-button" type="button" data-check-result>Kiểm tra kết quả</button>' : ""}<button class="link-button" type="button" data-new-case>Bắt đầu ca mới</button></div></section>`;
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
    const data = await api("/api/v1/chat", { method: "POST", body: JSON.stringify({ message, ...(state.caseId ? { case_id: state.caseId } : {}) }) });
    setActiveCase(data.case_id);
    state.currentPatientCase = data;
    state.patientMessages = state.patientMessages.filter((item) => item.role !== "pending");
    state.patientMessages.push({ role: "agent", text: data.response || "Thông tin đã được ghi nhận." });
  } catch (problem) {
    state.patientMessages = state.patientMessages.filter((item) => item.role !== "pending");
    state.patientMessages.push({ role: "error", text: problem.message || "Không thể gửi thông tin. Vui lòng thử lại." });
  } finally {
    state.patientBusy = false;
    renderPatientChat(root, context);
  }
}

async function checkResult(root, context) {
  if (!state.caseId) return;
  try { state.currentPatientCase = await api(`/api/v1/cases/${state.caseId}`); renderPatientChat(root, context); showToast("Đã cập nhật trạng thái ca."); } catch (problem) { showToast(problem.message, true); }
}

function patientStatusHelp(status) {
  if (status === "approved") return "Phản hồi đã được xác nhận.";
  if (status === "escalated") return "Ưu tiên liên hệ dịch vụ cấp cứu.";
  if (status === "needs_nurse_review" || status === "awaiting_approval") return "Chưa có hướng dẫn nào được gửi trước khi duyệt.";
  if (status === "needs_more_info") return "Nhân viên y tế đã yêu cầu bổ sung thông tin.";
  return "Trợ lý có thể cần thêm một vài thông tin.";
}

function scrollChat(root) { const log = root.querySelector("#chat-log"); log.scrollTop = log.scrollHeight; }
