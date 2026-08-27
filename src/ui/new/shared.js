import { state } from "./state.js";

const APP_THEME_KEY = "vmed_theme";
const LEGACY_PATIENT_THEME_KEY = "vmed_patient_theme";

/** Chủ đề là tuỳ chọn chung của cùng một người dùng, dù họ đang ở khu vực bệnh nhân hay nhân viên
 * y tế. Đọc key cũ một lần để các phiên trước khi đổi tên key không bị trả về giao diện sáng. */
export function readAppTheme() {
  try {
    const saved = localStorage.getItem(APP_THEME_KEY) ?? localStorage.getItem(LEGACY_PATIENT_THEME_KEY);
    return saved === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function applyAppTheme(theme) {
  document.documentElement.dataset.theme = theme;
}

export function saveAppTheme(theme) {
  try {
    localStorage.setItem(APP_THEME_KEY, theme);
  } catch {
    // Vẫn đổi trong phiên hiện tại nếu trình duyệt chặn localStorage.
  }
  applyAppTheme(theme);
}

export function resetAppTheme() {
  try {
    localStorage.removeItem(APP_THEME_KEY);
    localStorage.removeItem(LEGACY_PATIENT_THEME_KEY);
  } catch {
    // Vẫn trả về sáng nếu trình duyệt chặn localStorage.
  }
  applyAppTheme("light");
}

export const priorityLabels = {
  Emergency: "Cấp cứu",
  Urgent: "Khám sớm",
  Routine: "Khám thông thường",
  "Self-care": "Tự theo dõi",
  "Manual review": "Cần đánh giá thủ công",
};

export const statusLabels = {
  collecting_information: "Trợ lý đang thu thập thông tin",
  needs_more_info: "Nhân viên y tế cần bạn bổ sung",
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

/**
 * Chuyển một đoạn văn thô thành HTML đọc được: đoạn, tiêu đề "…:" và gạch đầu dòng.
 *
 * Tồn tại vì hai nguồn văn bản của hệ thống đều trả về CHUỖI THÔ, không phải HTML: văn xuôi của
 * phiếu tóm tắt (một khối 6-8 câu liền mạch) và lời thoại của trợ lý. Đổ thẳng chuỗi đó vào một
 * `<span>` thì được đúng thứ đang thấy trên màn duyệt ca - một bức tường chữ không có chỗ nghỉ mắt,
 * mà điều dưỡng lại phải dò trong đó xem field nào có, field nào chưa hỏi.
 *
 * Câu dài mới bị cắt thành nhiều đoạn (`minLengthToSplit`): một câu trả lời hai chữ của người bệnh
 * không cần chia đoạn, và chia thì bong bóng chat trông rời rạc.
 *
 * Escape nằm BÊN TRONG hàm này - gọi `paragraphs(escapeHtml(text))` là sai (dấu `&` sẽ bị escape
 * hai lần), luôn truyền chuỗi thô vào.
 */
export function paragraphs(text = "", { groupSize = 2, minLengthToSplit = 200 } = {}) {
  const source = String(text).replace(/\r\n/g, "\n").trim();
  if (!source) return "";
  return source
    .split(/\n{2,}/)
    .map((block) => renderTextBlock(block, groupSize, minLengthToSplit))
    .join("");
}

function renderTextBlock(block, groupSize, minLengthToSplit) {
  const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
  const parts = [];
  let bullets = [];
  const flushBullets = () => {
    if (!bullets.length) return;
    parts.push(`<ul class="prose-list">${bullets.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`);
    bullets = [];
  };
  for (const line of lines) {
    const bullet = /^[-*•+]\s+(.+)$/.exec(line);
    if (bullet) { bullets.push(bullet[1]); continue; }
    flushBullets();
    // "Triệu chứng ghi nhận:" là NHÃN của danh sách bên dưới, không phải một câu - để nó lẫn vào
    // đoạn văn thì mất luôn ranh giới giữa "người bệnh có" và "người bệnh phủ nhận".
    if (line.endsWith(":")) parts.push(`<p class="prose-heading">${escapeHtml(line)}</p>`);
    else parts.push(...splitIntoParagraphs(line, groupSize, minLengthToSplit).map((item) => `<p>${escapeHtml(item)}</p>`));
  }
  flushBullets();
  return parts.join("");
}

function splitIntoParagraphs(line, groupSize, minLengthToSplit) {
  if (line.length <= minLengthToSplit) return [line];
  const sentences = line.match(/[^.!?…]+(?:[.!?…]+|$)/g) || [line];
  const chunks = [];
  for (let index = 0; index < sentences.length; index += groupSize) {
    const chunk = sentences.slice(index, index + groupSize).join("").trim();
    if (chunk) chunks.push(chunk);
  }
  return chunks.length ? chunks : [line];
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

export function formatChatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "";
  const now = new Date();
  const isToday =
    date.getDate() === now.getDate() &&
    date.getMonth() === now.getMonth() &&
    date.getFullYear() === now.getFullYear();

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const isYesterday =
    date.getDate() === yesterday.getDate() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getFullYear() === yesterday.getFullYear();

  const timePart = `${pad(date.getHours())}:${pad(date.getMinutes())}`;
  if (isToday) return timePart;
  if (isYesterday) return `Hôm qua ${timePart}`;
  if (date.getFullYear() === now.getFullYear()) return `${pad(date.getDate())}/${pad(date.getMonth() + 1)} ${timePart}`;
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${timePart}`;
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


// --- lớp primitive của bản thiết kế 2026-08-19 (docs/design_handoff_vmedtriage) -----------------
//
// Thiết kế dùng icon nét 1.5-2px, KHÔNG tô nền. Gom vào một chỗ thay vì rải inline SVG khắp các
// feature: cùng một cái warning-triangle xuất hiện ở W-04, banner stale của W-06 và red-flag của
// W-07 - ba bản chép tay lệch nhau vài pixel là cách nhanh nhất để giao diện chỉ còn "gần giống".
const icons = {
  logo: `<rect x="2.2" y="2.2" width="19.6" height="19.6" rx="5.6" stroke="currentColor" stroke-width="1.5"/><path d="M5.6 12.2h2.9l1.4-3.1 2.1 6 1.7-4.1 1.1 1.2h3.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>`,
  check: `<path d="m4.5 12.5 4.5 4.5L19.5 6.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`,
  warning: `<path d="M12 3.4 21 19H3l9-15.6Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M12 9.6v4M12 16.2v.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>`,
  info: `<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.6"/><path d="M12 11v5M12 7.6v.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>`,
  alert: `<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.6"/><path d="M12 7.8v5.4M12 16.4v.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>`,
  phone: `<path d="M7.2 3.6h3l1.6 4-2 1.4a10.6 10.6 0 0 0 5.2 5.2l1.4-2 4 1.6v3a1.8 1.8 0 0 1-2 1.8A16.4 16.4 0 0 1 5.4 5.6a1.8 1.8 0 0 1 1.8-2Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>`,
  chat: `<path d="M20.5 12c0 4.1-3.8 7.4-8.5 7.4-1 0-2-.15-2.9-.43L4 20.8l1.7-3.7A7 7 0 0 1 3.5 12C3.5 7.9 7.3 4.6 12 4.6s8.5 3.3 8.5 7.4Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>`,
  ask: `<path d="M20.5 12.2c0 4-3.8 7.2-8.5 7.2-1 0-2-.15-2.9-.42L4 20.5l1.7-3.6A6.9 6.9 0 0 1 3.5 12.2C3.5 8.2 7.3 5 12 5s8.5 3.2 8.5 7.2Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M10 10.2a2.1 2.1 0 1 1 3.1 1.9c-.7.4-1.1.9-1.1 1.6M12 15.9v.2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  send: `<path d="M4.5 12 20 4.5l-4 15.5-4.4-5.6-7.1-2.4Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>`,
  clock: `<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5"/><path d="M12 7.4V12l3.2 2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  retry: `<path d="M20 12a8 8 0 1 1-2.6-5.9M20 4.5V10h-5.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  lock: `<rect x="5" y="10.5" width="14" height="9.5" rx="2.2" stroke="currentColor" stroke-width="1.6"/><path d="M8.4 10.5V8a3.6 3.6 0 0 1 7.2 0v2.5" stroke="currentColor" stroke-width="1.6"/>`,
  user: `<circle cx="12" cy="8.4" r="3.4" stroke="currentColor" stroke-width="1.6"/><path d="M5.6 19.4a6.4 6.4 0 0 1 12.8 0" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>`,
  allergy: `<path d="M12 4.1s-5.2 5.7-5.2 9.3a5.2 5.2 0 1 0 10.4 0C17.2 9.8 12 4.1 12 4.1Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M11 15.9c.8.5 1.8.5 2.6 0M18.6 4.5v3M17.1 6h3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>`,
  stethoscope: `<path d="M6.3 4.5v4.2a5.7 5.7 0 0 0 11.4 0V4.5M6.3 7.1H4.8M17.7 7.1h1.5M17.7 13.4v1.9a2.7 2.7 0 0 1-2.7 2.7h-1.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="11.3" cy="18" r="2.2" stroke="currentColor" stroke-width="1.6"/>`,
  pill: `<rect x="4.4" y="8.2" width="15.2" height="7.6" rx="3.8" transform="rotate(-45 12 12)" stroke="currentColor" stroke-width="1.6"/><path d="m9.3 14.7 5.4-5.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>`,
  calendarCheck: `<rect x="4.5" y="5.6" width="15" height="14.1" rx="2.4" stroke="currentColor" stroke-width="1.6"/><path d="M8 3.7v3.8M16 3.7v3.8M4.5 10.1h15M8.7 14.1l2 2 4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>`,
  clipboard: `<path d="M6.5 3.5h11v17l-5.5-3-5.5 3v-17Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>`,
  pulse: `<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.6"/><path d="M8.5 12.5h2.2l1.1-2.4 1.6 4.6 1.3-3.1.9.9h2.4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>`,
  shieldCheck: `<rect x="4.5" y="3.5" width="15" height="17" rx="2.6" stroke="currentColor" stroke-width="1.6"/><path d="m8.6 12.4 2.2 2.2 4.6-4.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  chevronDown: `<path d="m6 9.5 6 6 6-6" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>`,
  chevronLeft: `<path d="M14 6l-6 6 6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  chevronRight: `<path d="M9 5l7 7-7 7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  sidebarCollapse: `<rect x="3.5" y="4.5" width="17" height="15" rx="3" stroke="currentColor" stroke-width="1.55"/><path d="M9 4.8v14.4M15.2 9.1 12.1 12l3.1 2.9" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"/>`,
  sidebarExpand: `<rect x="3.5" y="4.5" width="17" height="15" rx="3" stroke="currentColor" stroke-width="1.55"/><path d="M9 4.8v14.4m3.8 1.1 3.1-2.9-3.1-2.9" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"/>`,
  eye: `<path d="M3 12s3.6-6 9-6 9 6 9 6-3.6 6-9 6-9-6-9-6Z" stroke="currentColor" stroke-width="1.5"/><circle cx="12" cy="12" r="2.6" stroke="currentColor" stroke-width="1.5"/>`,
  eyeOff: `<path d="M3 12s3.6-6 9-6 9 6 9 6-3.6 6-9 6-9-6-9-6Z" stroke="currentColor" stroke-width="1.5"/><circle cx="12" cy="12" r="2.6" stroke="currentColor" stroke-width="1.5"/><path d="M4 20 20 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>`,
  sun: `<circle cx="12" cy="12" r="3.5" stroke="currentColor" stroke-width="1.6"/><path d="M12 2.8v2M12 19.2v2M2.8 12h2M19.2 12h2M5.5 5.5l1.4 1.4M17.1 17.1l1.4 1.4M18.5 5.5l-1.4 1.4M6.9 17.1l-1.4 1.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>`,
  moon: `<path d="M19.4 15.4A8.2 8.2 0 0 1 8.6 4.6 8.3 8.3 0 1 0 19.4 15.4Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>`,
  offline: `<path d="M2.5 8.5a14 14 0 0 1 19 0M6 12.6a9 9 0 0 1 12 0M12 20.2v.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M4 20 20 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>`,
  broken: `<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.4"/><path d="M9.2 9.2l5.6 5.6M14.8 9.2l-5.6 5.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>`,
  trash: `<path d="M4.8 7.2h14.4M9.2 7.2V4.6h5.6v2.6M7.2 7.2l.8 12.2h8l.8-12.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M10.2 10.5v5.6M13.8 10.5v5.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>`,
  settings: `<circle cx="12" cy="12" r="3.1" stroke="currentColor" stroke-width="1.6"/><path d="M19.1 13.8a1.7 1.7 0 0 0 .34 1.88l.06.06-2.25 2.25-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56v.1h-3.18v-.1a1.7 1.7 0 0 0-1.03-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06-2.25-2.25.06-.06a1.7 1.7 0 0 0 .34-1.88 1.7 1.7 0 0 0-1.56-1.03h-.1V9.67h.1a1.7 1.7 0 0 0 1.56-1.03 1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.25-2.25.06.06a1.7 1.7 0 0 0 1.88.34 1.7 1.7 0 0 0 1.03-1.56v-.1h3.18v.1a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.25 2.25-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.03h.1v3.18h-.1a1.7 1.7 0 0 0-1.56 1.03Z" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/>`,
  flag: `<path d="M6 3.5v17M6 4.6h9.5l-1.4 3.4 1.4 3.4H6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>`,
  mapPin: `<path d="M12 21s7-7.6 7-12.4A7 7 0 1 0 5 8.6C5 13.4 12 21 12 21Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><circle cx="12" cy="8.6" r="2.4" stroke="currentColor" stroke-width="1.6"/>`,
  mic: `<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3M8 22h8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>`,
  paperclip: `<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l7.88-7.87" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>`,
  volume: `<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07M19.07 4.93a10 10 0 0 1 0 14.14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>`,
};

/** Icon nét theo bộ của bản thiết kế. Màu luôn thừa kế qua `currentColor` - đừng truyền stroke cứng
 *  vào đây, mọi biến thể màu đã nằm ở lớp CSS bao ngoài. */
export function icon(name, size = 18, extraClass = "") {
  const body = icons[name];
  if (!body) return "";
  return `<svg class="ico ${extraClass}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">${body}</svg>`;
}

// --- G2 "make capability limits explicit" (docs/design_handoff_vmedtriage/README.md) -------------
//
// Thang riêng, CỐ Ý không dùng đỏ/hổ phách/xanh của thang mức ưu tiên. Điều dưỡng đọc lướt một dòng
// hàng đợi thấy hai tín hiệu màu cạnh nhau; nếu "độ tin cậy Thấp" tô đỏ thì nó bị đọc thành "Cấp
// cứu", tức là chỉ báo dựng ra để giúp cân nhắc lại trở thành nguồn nhầm lẫn.
const confidenceScale = [
  { min: 0.75, key: "high", label: "Cao" },
  { min: 0.45, key: "medium", label: "Trung bình" },
  { min: 0, key: "low", label: "Thấp" },
];

/** `null` khi backend chưa có số - KHÔNG suy ra "Thấp". "Chưa đo được độ tin cậy" và "độ tin cậy
 *  thấp" là hai điều khác nhau; gộp lại thì điều dưỡng mất đúng thông tin cần để hoài nghi. */
export function aiConfidence(value) {
  if (!Number.isFinite(value)) return null;
  return confidenceScale.find((level) => value >= level.min) ?? confidenceScale.at(-1);
}

/** G2 buộc mọi chỗ điều dưỡng thấy mức ưu tiên AI đề xuất đều thấy kèm độ tin cậy. Dùng hàm này ở
 *  CẢ hai chỗ (dòng hàng đợi W-06 và thẻ đề xuất W-07) để hai nơi không thể lệch nhau. */
export function confidenceMarkup(value, prefix = "Độ tin cậy AI") {
  const level = aiConfidence(value);
  if (!level) return "";
  return `<span class="ai-confidence">${prefix}: <b class="is-${level.key}">${level.label}</b></span>`;
}

/** Chấm màu của mức ưu tiên. `Routine`/`Manual review` của rule engine không có ô riêng trong bảng
 *  màu 3 mức của thiết kế nên rơi về trung tính - không được mượn màu của một mức khác. */
export function priorityDot(priority) {
  return `<span class="priority-dot ${priorityClass(priority)}" aria-hidden="true"></span>`;
}

export function logo(size = 25) {
  return `<svg class="ico logo-mark" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">${icons.logo}</svg><span class="brand-word">VMed<span>Triage</span></span>`;
}

/** Thanh header dùng chung của mọi màn hình đã đăng nhập (W-00, W-02..W-07). Thiết kế đặt logo,
 *  gạch dọc, nav rồi khối bên phải theo đúng thứ tự này ở cả 6 màn - dựng một lần ở đây thay vì
 *  chép lại sáu lần. */
export function appHeader({ nav = [], title = "", meta = "", right = "" } = {}) {
  const links = nav
    .map((item) => `<button class="nav-link${item.active ? " is-active" : ""}" type="button"${item.action ? ` data-nav="${item.action}"` : ""}>${escapeHtml(item.label)}</button>`)
    .join("");
  const divider = links || title ? `<span class="header-divider" aria-hidden="true"></span>` : "";
  return `<header class="app-header"><a class="brand" href="/" aria-label="VMedTriage">${logo()}</a>${divider}${links ? `<nav aria-label="Điều hướng">${links}</nav>` : ""}${title ? `<span class="header-title">${title}</span>` : ""}${meta ? `<span class="header-meta">${meta}</span>` : ""}${right}</header>`;
}

/** Khối nhận dạng người đang đăng nhập ở góc phải header (W-00 "Bệnh nhân · ID", W-06 "Trực ca
 *  chiều"). Thiết kế luôn ghép nó với menu tài khoản sẵn có. */
export function identityBlock(subtitle = "") {
  const name = state.user?.full_name || "Tài khoản";
  return `<span class="header-identity"><b>${escapeHtml(name)}</b>${subtitle ? `<small>${escapeHtml(subtitle)}</small>` : ""}</span>`;
}
