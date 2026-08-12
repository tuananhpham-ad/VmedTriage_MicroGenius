export const priorityLabels = {
  Emergency: "Cấp cứu",
  Urgent: "Khám sớm",
  Routine: "Khám thông thường",
  "Self-care": "Tự theo dõi",
  "Manual review": "Cần đánh giá thủ công",
};

export const statusLabels = {
  collecting_information: "Đang bổ sung thông tin",
  needs_more_info: "Cần bổ sung thông tin",
  needs_nurse_review: "Cần nhân viên y tế duyệt",
  awaiting_approval: "Đang chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Cần đánh giá lại",
  escalated: "Đã chuyển cấp cứu",
  withdrawn: "Đã đóng",
};

export const symptomGroupLabels = {
  fever: "Sốt",
  abdominal_pain: "Đau bụng",
  chest_pain: "Đau ngực",
  shortness_of_breath: "Khó thở",
  headache: "Đau đầu",
  head_injury: "Chấn thương đầu",
  general: "Triệu chứng chung",
};

export function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function shortCaseId(id) {
  return id ? id.slice(0, 8).toUpperCase() : "Chưa có";
}

export function humanize(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toLocaleUpperCase("vi-VN"));
}

export function priorityClass(priority) {
  if (priority === "Emergency") return "is-emergency";
  if (priority === "Urgent") return "is-urgent";
  if (priority === "Self-care") return "is-self-care";
  return "is-routine";
}

export function statusClass(status) {
  if (status === "approved") return "is-approved";
  if (status === "escalated") return "is-emergency";
  if (status === "rejected" || status === "withdrawn") return "is-muted";
  return "is-pending";
}

export function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Chưa xác định";
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function waitingLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "chưa xác định";
  const minutes = Math.max(0, Math.round((Date.now() - date.valueOf()) / 60000));
  if (minutes < 60) return `${minutes} phút`;
  return `${Math.floor(minutes / 60)} giờ ${minutes % 60} phút`;
}

export function showToast(message, isError = false) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.classList.toggle("is-error", isError);
  toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.hidden = true;
  }, 4200);
}

function pad(value) {
  return String(value).padStart(2, "0");
}

export function logo() {
  return `<span class="brand-mark" aria-hidden="true"><span class="pulse-mark"></span></span><span>VMed<span>Triage</span></span>`;
}
