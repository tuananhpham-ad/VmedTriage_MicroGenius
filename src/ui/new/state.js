export const state = {
  view: "access",
  role: null,
  accessToken: readStoredValue("vmed_access_token"),
  user: readStoredUser(),
  caseId: sessionStorage.getItem("vmed_active_case_id"),
  currentPatientCase: null,
  patientMessages: [],
  patientBusy: false,
  // Bệnh nhân đã bấm xác nhận phiếu tóm tắt cuối phiên (Stage 6) chưa - chỉ để ẩn thẻ phiếu sau khi
  // bấm, trạng thái thật nằm ở phiên agent phía server.
  summaryConfirmed: false,
  selectedNurseCase: null,
  queue: [],
  nurseBusy: false,
  // W-07 trạng thái "lỗi lưu": header thay nút "Về hàng đợi" bằng chip khoá. Sống ở state chứ không
  // ở DOM vì `renderNurseCase` vẽ lại toàn bộ màn hình sau mỗi lần thử lưu.
  nurseSaveError: false,
  queueTimer: null,
  pendingVerificationEmail: "",
  // W-04 là màn hình chặn một lần cho MỖI CA, không phải mỗi lượt chat: một ca red-flag còn nhiều
  // lượt trao đổi phía sau, mà bắn lại màn cảnh báo sau mỗi lượt thì người bệnh học cách bấm qua nó
  // mà không đọc - đúng thứ màn hình này tồn tại để chống lại.
  redFlagShownCaseId: null,
};

export const pendingStatuses = new Set([
  "collecting_information",
  "needs_nurse_review",
  "awaiting_approval",
  "needs_more_info",
]);

export const completedStatuses = new Set(["approved", "rejected", "escalated", "withdrawn"]);

function readStoredUser() {
  try {
    return JSON.parse(readStoredValue("vmed_user") || "null");
  } catch {
    return null;
  }
}

function readStoredValue(key) {
  return sessionStorage.getItem(key) || localStorage.getItem(key);
}

export function saveSession(accessToken, user, { remember = false } = {}) {
  state.accessToken = accessToken;
  state.user = user;
  state.role = user.role;
  const storage = remember ? localStorage : sessionStorage;
  const otherStorage = remember ? sessionStorage : localStorage;
  storage.setItem("vmed_access_token", accessToken);
  storage.setItem("vmed_user", JSON.stringify(user));
  otherStorage.removeItem("vmed_access_token");
  otherStorage.removeItem("vmed_user");
}

export function clearSession() {
  state.accessToken = null;
  state.user = null;
  state.role = null;
  state.caseId = null;
  state.currentPatientCase = null;
  state.patientMessages = [];
  state.summaryConfirmed = false;
  state.selectedNurseCase = null;
  state.redFlagShownCaseId = null;
  sessionStorage.removeItem("vmed_access_token");
  sessionStorage.removeItem("vmed_user");
  sessionStorage.removeItem("vmed_active_case_id");
  sessionStorage.removeItem("vmed_active_nurse_case_id");
  localStorage.removeItem("vmed_access_token");
  localStorage.removeItem("vmed_user");
}

export function setActiveCase(caseId) {
  state.caseId = caseId;
  if (caseId) sessionStorage.setItem("vmed_active_case_id", caseId);
  else sessionStorage.removeItem("vmed_active_case_id");
}
