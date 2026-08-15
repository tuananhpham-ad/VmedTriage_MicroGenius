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
  queueTimer: null,
  pendingVerificationEmail: "",
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
