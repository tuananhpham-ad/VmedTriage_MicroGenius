export const state = {
  view: "access",
  role: null,
  accessToken: sessionStorage.getItem("vmed_access_token"),
  user: readStoredUser(),
  caseId: sessionStorage.getItem("vmed_active_case_id"),
  currentPatientCase: null,
  patientMessages: [],
  patientBusy: false,
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
    return JSON.parse(sessionStorage.getItem("vmed_user") || "null");
  } catch {
    return null;
  }
}

export function saveSession(accessToken, user) {
  state.accessToken = accessToken;
  state.user = user;
  state.role = user.role;
  sessionStorage.setItem("vmed_access_token", accessToken);
  sessionStorage.setItem("vmed_user", JSON.stringify(user));
}

export function clearSession() {
  state.accessToken = null;
  state.user = null;
  state.role = null;
  state.caseId = null;
  state.currentPatientCase = null;
  state.patientMessages = [];
  state.selectedNurseCase = null;
  sessionStorage.removeItem("vmed_access_token");
  sessionStorage.removeItem("vmed_user");
  sessionStorage.removeItem("vmed_active_case_id");
  sessionStorage.removeItem("vmed_active_nurse_case_id");
}

export function setActiveCase(caseId) {
  state.caseId = caseId;
  if (caseId) sessionStorage.setItem("vmed_active_case_id", caseId);
  else sessionStorage.removeItem("vmed_active_case_id");
}
