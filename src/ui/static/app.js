const state = {
  role: null,
  selectedRole: null,
  authMode: "login",
  pendingVerificationEmail: "",
  accessToken: sessionStorage.getItem("vmed_access_token"),
  user: readStoredUser(),
  caseId: null,
  currentPatientCase: null,
  selectedNurseCase: null,
  queue: [],
  patientBusy: false,
  nurseBusy: false,
  queueTimer: null,
  toastTimer: null,
};

const pendingStatuses = new Set([
  "collecting_information",
  "needs_nurse_review",
  "awaiting_approval",
]);

const completedStatuses = new Set(["approved", "rejected", "escalated"]);

const priorityLabels = {
  Emergency: "Cấp cứu",
  Urgent: "Khám sớm",
  Routine: "Khám thông thường",
  "Self-care": "Tự theo dõi",
  "Manual review": "Cần đánh giá thủ công",
};

const priorityRanks = {
  Emergency: 0,
  Urgent: 1,
  "Manual review": 2,
  Routine: 3,
  "Self-care": 4,
};

const statusLabels = {
  collecting_information: "Đang bổ sung thông tin",
  needs_nurse_review: "Cần duyệt ưu tiên",
  awaiting_approval: "Đang chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Đã từ chối",
  escalated: "Đã chuyển cấp cứu",
};

const symptomGroupLabels = {
  fever: "Sốt",
  abdominal_pain: "Đau bụng",
  chest_pain: "Đau ngực",
  shortness_of_breath: "Khó thở",
  headache: "Đau đầu",
  head_injury: "Chấn thương đầu",
  general: "Triệu chứng chung",
};

const clinicalLabels = {
  chest_pain: "Đau ngực",
  abdominal_pain: "Đau bụng",
  shortness_of_breath: "Khó thở",
  headache: "Đau đầu",
  head_injury: "Chấn thương đầu",
  fever: "Sốt",
  this_morning: "Từ sáng nay",
  today: "Hôm nay",
  pain_severity: "Mức độ đau",
  pain_radiation: "Đau lan",
  onset: "Thời điểm khởi phát",
  duration: "Thời gian kéo dài",
  associated_symptoms: "Triệu chứng đi kèm",
  risk_factors: "Yếu tố nguy cơ",
};

const elements = {
  views: document.querySelectorAll(".view"),
  accessView: document.querySelector("#accessView"),
  disclaimerView: document.querySelector("#disclaimerView"),
  patientView: document.querySelector("#patientView"),
  nurseView: document.querySelector("#nurseView"),
  homeButton: document.querySelector("#homeButton"),
  switchRoleButton: document.querySelector("#switchRoleButton"),
  changePasswordButton: document.querySelector("#changePasswordButton"),
  systemStatus: document.querySelector("#systemStatus"),
  roleChoices: document.querySelector("#roleChoices"),
  roleButtons: document.querySelectorAll("[data-role]"),
  authPanel: document.querySelector("#authPanel"),
  authRoleLabel: document.querySelector("#authRoleLabel"),
  authTitle: document.querySelector("#authTitle"),
  authHelp: document.querySelector("#authHelp"),
  authModeButtons: document.querySelectorAll("[data-auth-mode]"),
  authForm: document.querySelector("#authForm"),
  fullNameField: document.querySelector("#fullNameField"),
  authFullName: document.querySelector("#authFullName"),
  usernameField: document.querySelector("#usernameField"),
  authUsername: document.querySelector("#authUsername"),
  authEmail: document.querySelector("#authEmail"),
  phoneField: document.querySelector("#phoneField"),
  authPhone: document.querySelector("#authPhone"),
  birthDateField: document.querySelector("#birthDateField"),
  authBirthDate: document.querySelector("#authBirthDate"),
  genderField: document.querySelector("#genderField"),
  authGender: document.querySelector("#authGender"),
  avatarField: document.querySelector("#avatarField"),
  authAvatar: document.querySelector("#authAvatar"),
  authPassword: document.querySelector("#authPassword"),
  confirmPasswordField: document.querySelector("#confirmPasswordField"),
  authConfirmPassword: document.querySelector("#authConfirmPassword"),
  nurseCodeField: document.querySelector("#nurseCodeField"),
  nurseRegistrationCode: document.querySelector("#nurseRegistrationCode"),
  authError: document.querySelector("#authError"),
  authSubmitButton: document.querySelector("#authSubmitButton"),
  authBackButton: document.querySelector("#authBackButton"),
  nurseDetails: document.querySelector("#nurseDetails"),
  professionalLicense: document.querySelector("#professionalLicense"),
  workplace: document.querySelector("#workplace"),
  department: document.querySelector("#department"),
  nurseBio: document.querySelector("#nurseBio"),
  termsField: document.querySelector("#termsField"),
  termsAccepted: document.querySelector("#termsAccepted"),
  forgotPasswordButton: document.querySelector("#forgotPasswordButton"),
  emailVerificationPanel: document.querySelector("#emailVerificationPanel"),
  emailVerificationForm: document.querySelector("#emailVerificationForm"),
  verificationCode: document.querySelector("#verificationCode"),
  emailVerificationError: document.querySelector("#emailVerificationError"),
  resendVerificationButton: document.querySelector("#resendVerificationButton"),
  forgotPasswordPanel: document.querySelector("#forgotPasswordPanel"),
  forgotPasswordForm: document.querySelector("#forgotPasswordForm"),
  forgotPasswordEmail: document.querySelector("#forgotPasswordEmail"),
  forgotPasswordError: document.querySelector("#forgotPasswordError"),
  forgotPasswordBackButton: document.querySelector("#forgotPasswordBackButton"),
  resetPasswordPanel: document.querySelector("#resetPasswordPanel"),
  resetPasswordForm: document.querySelector("#resetPasswordForm"),
  newPassword: document.querySelector("#newPassword"),
  confirmPassword: document.querySelector("#confirmPassword"),
  resetPasswordError: document.querySelector("#resetPasswordError"),
  resetPasswordBackButton: document.querySelector("#resetPasswordBackButton"),
  changePasswordPanel: document.querySelector("#changePasswordPanel"),
  changePasswordForm: document.querySelector("#changePasswordForm"),
  currentPassword: document.querySelector("#currentPassword"),
  changeNewPassword: document.querySelector("#changeNewPassword"),
  changeConfirmPassword: document.querySelector("#changeConfirmPassword"),
  changePasswordError: document.querySelector("#changePasswordError"),
  changePasswordCancelButton: document.querySelector("#changePasswordCancelButton"),
  acceptDisclaimerButton: document.querySelector("#acceptDisclaimerButton"),
  backToRolesButton: document.querySelector("#backToRolesButton"),
  emergencyBanner: document.querySelector("#emergencyBanner"),
  acknowledgeEmergencyButton: document.querySelector("#acknowledgeEmergencyButton"),
  patientStateValue: document.querySelector("#patientStateValue"),
  patientStateHelp: document.querySelector("#patientStateHelp"),
  patientCaseId: document.querySelector("#patientCaseId"),
  messages: document.querySelector("#messages"),
  welcomeMessage: document.querySelector("#welcomeMessage"),
  symptomChoices: document.querySelector("#symptomChoices"),
  chatForm: document.querySelector("#chatForm"),
  messageInput: document.querySelector("#messageInput"),
  messageError: document.querySelector("#messageError"),
  sendButton: document.querySelector("#sendButton"),
  patientOutcome: document.querySelector("#patientOutcome"),
  patientOutcomeLabel: document.querySelector("#patientOutcomeLabel"),
  patientOutcomeTitle: document.querySelector("#patientOutcomeTitle"),
  patientOutcomeBody: document.querySelector("#patientOutcomeBody"),
  checkResultButton: document.querySelector("#checkResultButton"),
  newCaseButton: document.querySelector("#newCaseButton"),
  pendingCaseCount: document.querySelector("#pendingCaseCount"),
  queueUpdatedAt: document.querySelector("#queueUpdatedAt"),
  refreshQueueButton: document.querySelector("#refreshQueueButton"),
  queueFilter: document.querySelector("#queueFilter"),
  queueMessage: document.querySelector("#queueMessage"),
  queueList: document.querySelector("#queueList"),
  caseEmptyState: document.querySelector("#caseEmptyState"),
  caseDetail: document.querySelector("#caseDetail"),
  selectedCaseId: document.querySelector("#selectedCaseId"),
  selectedCaseStatus: document.querySelector("#selectedCaseStatus"),
  selectedCasePriority: document.querySelector("#selectedCasePriority"),
  caseAlert: document.querySelector("#caseAlert"),
  summaryComplaint: document.querySelector("#summaryComplaint"),
  summaryOnset: document.querySelector("#summaryOnset"),
  summarySeverity: document.querySelector("#summarySeverity"),
  summaryConfidence: document.querySelector("#summaryConfidence"),
  associatedSymptoms: document.querySelector("#associatedSymptoms"),
  missingBlock: document.querySelector("#missingBlock"),
  missingInformation: document.querySelector("#missingInformation"),
  proposalPriority: document.querySelector("#proposalPriority"),
  proposalReason: document.querySelector("#proposalReason"),
  redFlagSection: document.querySelector("#redFlagSection"),
  redFlagList: document.querySelector("#redFlagList"),
  conversationHistory: document.querySelector("#conversationHistory"),
  editedPriority: document.querySelector("#editedPriority"),
  approvedResponse: document.querySelector("#approvedResponse"),
  nurseNotes: document.querySelector("#nurseNotes"),
  reviewError: document.querySelector("#reviewError"),
  approveButton: document.querySelector("#approveButton"),
  askMoreButton: document.querySelector("#askMoreButton"),
  escalateButton: document.querySelector("#escalateButton"),
  toast: document.querySelector("#toast"),
};

elements.roleButtons.forEach((button) => {
  button.addEventListener("click", () => selectRole(button.dataset.role));
});
elements.authModeButtons.forEach((button) => {
  button.addEventListener("click", () => setAuthMode(button.dataset.authMode));
});

elements.homeButton.addEventListener("click", returnToRoleSelection);
elements.switchRoleButton.addEventListener("click", logout);
elements.changePasswordButton.addEventListener("click", openChangePasswordForm);
elements.authBackButton.addEventListener("click", returnToRoleSelection);
elements.authForm.addEventListener("submit", submitAuthForm);
elements.forgotPasswordButton.addEventListener("click", openForgotPasswordForm);
elements.emailVerificationForm.addEventListener("submit", submitEmailVerification);
elements.resendVerificationButton.addEventListener("click", resendVerificationCode);
elements.forgotPasswordForm.addEventListener("submit", submitForgotPasswordForm);
elements.forgotPasswordBackButton.addEventListener("click", returnToLogin);
elements.resetPasswordForm.addEventListener("submit", submitResetPasswordForm);
elements.resetPasswordBackButton.addEventListener("click", returnToLogin);
elements.changePasswordForm.addEventListener("submit", submitChangePasswordForm);
elements.changePasswordCancelButton.addEventListener("click", closeChangePasswordForm);
elements.backToRolesButton.addEventListener("click", returnToRoleSelection);
elements.acceptDisclaimerButton.addEventListener("click", openPatientWorkspace);
elements.chatForm.addEventListener("submit", submitPatientMessage);
elements.newCaseButton.addEventListener("click", startNewCase);
elements.checkResultButton.addEventListener("click", checkPatientResult);
elements.acknowledgeEmergencyButton.addEventListener("click", acknowledgeEmergency);
elements.refreshQueueButton.addEventListener("click", () => refreshQueue());
elements.queueFilter.addEventListener("change", renderQueue);
elements.approveButton.addEventListener("click", () => reviewCase("approve"));
elements.askMoreButton.addEventListener("click", () => reviewCase("ask_more"));
elements.escalateButton.addEventListener("click", () => reviewCase("escalate"));

elements.symptomChoices.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-symptom]");
  if (!button) return;
  elements.messageInput.value = button.dataset.symptom;
  elements.messageError.textContent = "";
  elements.messageInput.focus();
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && state.role === "nurse") {
    refreshQueue({ silent: true });
  }
});

function selectRole(role) {
  state.selectedRole = role;
  if (state.accessToken && state.user?.role === role) {
    enterRole(role);
    return;
  }

  showAuthForRole(role);
}

function enterRole(role) {
  stopQueuePolling();
  state.role = role;
  elements.switchRoleButton.hidden = false;
  elements.changePasswordButton.hidden = false;

  if (role === "patient") {
    showView(elements.disclaimerView);
    elements.acceptDisclaimerButton.focus();
    return;
  }

  showView(elements.nurseView);
  startQueuePolling();
  elements.refreshQueueButton.focus();
}

function returnToRoleSelection() {
  stopQueuePolling();
  state.role = null;
  state.selectedRole = null;
  elements.roleChoices.hidden = false;
  elements.authPanel.hidden = true;
  elements.emailVerificationPanel.hidden = true;
  elements.forgotPasswordPanel.hidden = true;
  elements.resetPasswordPanel.hidden = true;
  elements.authError.textContent = "";
  elements.switchRoleButton.hidden = !state.accessToken;
  elements.changePasswordButton.hidden = !state.accessToken;
  showView(elements.accessView);
  document.querySelector('[data-role="patient"]').focus();
}

function showAuthForRole(role) {
  state.role = null;
  elements.roleChoices.hidden = true;
  elements.authPanel.hidden = false;
  elements.emailVerificationPanel.hidden = true;
  elements.forgotPasswordPanel.hidden = true;
  elements.resetPasswordPanel.hidden = true;
  elements.authRoleLabel.textContent = role === "nurse" ? "Không gian điều dưỡng" : "Khu vực bệnh nhân";
  elements.authHelp.textContent =
    role === "nurse"
      ? "Đăng nhập bằng tài khoản điều dưỡng. Tạo mới cần mã riêng từ quản trị viên."
      : "Đăng nhập hoặc tạo tài khoản bệnh nhân để tiếp tục khai báo.";
  setAuthMode("login");
  elements.authEmail.focus();
}

function setAuthMode(mode) {
  state.authMode = mode;
  const isRegister = mode === "register";
  const needsNurseDetails = isRegister && state.selectedRole === "nurse";
  elements.authModeButtons.forEach((button) => {
    const isActive = button.dataset.authMode === mode;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
  elements.authTitle.textContent = isRegister ? "Tạo tài khoản mới" : "Đăng nhập để tiếp tục";
  elements.fullNameField.hidden = !isRegister;
  elements.authFullName.required = isRegister;
  elements.usernameField.hidden = !isRegister;
  elements.authUsername.required = isRegister;
  elements.phoneField.hidden = !isRegister;
  elements.authPhone.required = isRegister;
  elements.birthDateField.hidden = !isRegister;
  elements.authBirthDate.required = isRegister;
  elements.genderField.hidden = !isRegister;
  elements.authGender.required = isRegister;
  elements.avatarField.hidden = !isRegister;
  elements.authAvatar.required = isRegister;
  elements.confirmPasswordField.hidden = !isRegister;
  elements.authConfirmPassword.required = isRegister;
  elements.termsField.hidden = !isRegister;
  elements.termsAccepted.required = isRegister;
  elements.nurseCodeField.hidden = !needsNurseDetails;
  elements.nurseRegistrationCode.required = needsNurseDetails;
  elements.nurseDetails.hidden = !needsNurseDetails;
  [elements.professionalLicense, elements.workplace, elements.department, elements.nurseBio].forEach((field) => {
    field.required = needsNurseDetails;
  });
  elements.authPassword.autocomplete = isRegister ? "new-password" : "current-password";
  elements.forgotPasswordButton.hidden = isRegister;
  elements.authSubmitButton.textContent = isRegister ? "Tạo tài khoản và tiếp tục" : "Đăng nhập";
  elements.authError.textContent = "";
}

async function submitAuthForm(event) {
  event.preventDefault();
  if (!state.selectedRole || !elements.authForm.reportValidity()) return;

  const email = elements.authEmail.value.trim();
  const password = elements.authPassword.value;
  elements.authError.textContent = "";
  elements.authSubmitButton.disabled = true;
  elements.authSubmitButton.textContent = state.authMode === "register" ? "Đang tạo tài khoản" : "Đang đăng nhập";

  try {
    if (state.authMode === "register") {
      const avatarDataUrl = await readAvatarDataUrl();
      const registerPayload = {
        email,
        password,
        full_name: elements.authFullName.value.trim(),
        username: elements.authUsername.value.trim(),
        phone_number: elements.authPhone.value.trim(),
        date_of_birth: elements.authBirthDate.value,
        gender: elements.authGender.value,
        avatar_data_url: avatarDataUrl,
        confirm_password: elements.authConfirmPassword.value,
        terms_accepted: elements.termsAccepted.checked,
        role: state.selectedRole,
      };
      if (state.selectedRole === "nurse") {
        registerPayload.nurse_registration_code = elements.nurseRegistrationCode.value;
        registerPayload.professional_license = elements.professionalLicense.value.trim();
        registerPayload.workplace = elements.workplace.value.trim();
        registerPayload.department = elements.department.value.trim();
        registerPayload.bio = elements.nurseBio.value.trim();
      }
      await fetchJson("/api/v1/register", {
        method: "POST",
        body: JSON.stringify(registerPayload),
      });
      openEmailVerificationForm(email);
      return;
    }

    const session = await fetchJson("/api/v1/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    if (session.user.role !== state.selectedRole) {
      throw new Error(
        `Tài khoản này thuộc vai trò ${session.user.role === "nurse" ? "điều dưỡng" : "bệnh nhân"}.`,
      );
    }

    saveSession(session.access_token, session.user);
    enterRole(session.user.role);
  } catch (error) {
    if (error?.message?.includes("chưa được xác thực")) openEmailVerificationForm(email);
    elements.authError.textContent = readableError(error, "Không thể xác thực tài khoản.");
  } finally {
    elements.authSubmitButton.disabled = false;
    elements.authSubmitButton.textContent = state.authMode === "register" ? "Tạo tài khoản và tiếp tục" : "Đăng nhập";
  }
}

function openEmailVerificationForm(email) {
  state.pendingVerificationEmail = email;
  elements.authPanel.hidden = true;
  elements.emailVerificationPanel.hidden = false;
  elements.emailVerificationError.textContent = "";
  elements.verificationCode.value = "";
  elements.verificationCode.focus();
}

async function submitEmailVerification(event) {
  event.preventDefault();
  if (!state.pendingVerificationEmail || !elements.emailVerificationForm.reportValidity()) return;
  try {
    const result = await fetchJson("/api/v1/auth/email-verification/confirm", {
      method: "POST",
      body: JSON.stringify({ email: state.pendingVerificationEmail, code: elements.verificationCode.value.trim() }),
    });
    showToast(result.message);
    elements.authEmail.value = state.pendingVerificationEmail;
    returnToLogin();
  } catch (error) {
    elements.emailVerificationError.textContent = readableError(error, "Không thể xác thực email.");
  }
}

async function resendVerificationCode() {
  if (!state.pendingVerificationEmail) return;
  try {
    const result = await fetchJson("/api/v1/auth/email-verification/resend", {
      method: "POST",
      body: JSON.stringify({ email: state.pendingVerificationEmail }),
    });
    elements.emailVerificationError.textContent = result.message;
  } catch (error) {
    elements.emailVerificationError.textContent = readableError(error, "Không thể gửi lại mã.");
  }
}

function openForgotPasswordForm() {
  elements.authPanel.hidden = true;
  elements.forgotPasswordPanel.hidden = false;
  elements.forgotPasswordEmail.value = elements.authEmail.value.trim();
  elements.forgotPasswordError.textContent = "";
  elements.forgotPasswordEmail.focus();
}

function returnToLogin() {
  history.replaceState({}, "", window.location.pathname);
  elements.emailVerificationPanel.hidden = true;
  elements.forgotPasswordPanel.hidden = true;
  elements.resetPasswordPanel.hidden = true;
  if (!state.selectedRole) {
    returnToRoleSelection();
    return;
  }
  elements.authPanel.hidden = false;
  setAuthMode("login");
  elements.authEmail.focus();
}

async function submitForgotPasswordForm(event) {
  event.preventDefault();
  if (!elements.forgotPasswordForm.reportValidity()) return;
  try {
    const result = await fetchJson("/api/v1/auth/password-reset/request", {
      method: "POST",
      body: JSON.stringify({ email: elements.forgotPasswordEmail.value.trim() }),
    });
    elements.forgotPasswordError.textContent = result.message;
  } catch (error) {
    elements.forgotPasswordError.textContent = readableError(error, "Không thể gửi yêu cầu.");
  }
}

async function submitResetPasswordForm(event) {
  event.preventDefault();
  if (!elements.resetPasswordForm.reportValidity()) return;
  try {
    const result = await fetchJson("/api/v1/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify({
        token: elements.resetPasswordPanel.dataset.token,
        new_password: elements.newPassword.value,
        confirm_new_password: elements.confirmPassword.value,
      }),
    });
    showToast(result.message);
    returnToLogin();
  } catch (error) {
    elements.resetPasswordError.textContent = readableError(error, "Không thể đặt lại mật khẩu.");
  }
}

function openChangePasswordForm() {
  elements.changePasswordPanel.hidden = false;
  elements.changePasswordError.textContent = "";
  elements.changePasswordForm.reset();
  elements.currentPassword.focus();
}

function closeChangePasswordForm() {
  elements.changePasswordPanel.hidden = true;
}

async function submitChangePasswordForm(event) {
  event.preventDefault();
  if (!elements.changePasswordForm.reportValidity()) return;
  try {
    const result = await fetchJson("/api/v1/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: elements.currentPassword.value,
        new_password: elements.changeNewPassword.value,
        confirm_new_password: elements.changeConfirmPassword.value,
      }),
    });
    closeChangePasswordForm();
    logout();
    showToast(result.message);
  } catch (error) {
    elements.changePasswordError.textContent = readableError(error, "Không thể đổi mật khẩu.");
  }
}

function readAvatarDataUrl() {
  const file = elements.authAvatar.files?.[0];
  if (!file) return Promise.reject(new Error("Vui lòng chọn ảnh đại diện."));
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 1_000_000) {
    return Promise.reject(new Error("Ảnh đại diện phải là PNG, JPEG hoặc WebP và không quá 1 MB."));
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Không thể đọc ảnh đại diện."));
    reader.readAsDataURL(file);
  });
}

function saveSession(accessToken, user) {
  state.accessToken = accessToken;
  state.user = user;
  sessionStorage.setItem("vmed_access_token", accessToken);
  sessionStorage.setItem("vmed_user", JSON.stringify(user));
  elements.switchRoleButton.hidden = false;
  elements.changePasswordButton.hidden = false;
}

function clearSession() {
  state.accessToken = null;
  state.user = null;
  sessionStorage.removeItem("vmed_access_token");
  sessionStorage.removeItem("vmed_user");
  elements.changePasswordButton.hidden = true;
}

function logout() {
  clearSession();
  returnToRoleSelection();
  showToast("Đã đăng xuất khỏi tài khoản.");
}

function readStoredUser() {
  try {
    return JSON.parse(sessionStorage.getItem("vmed_user")) || null;
  } catch {
    sessionStorage.removeItem("vmed_user");
    return null;
  }
}

async function restoreSession() {
  if (!state.accessToken) return;
  try {
    const user = await fetchJson("/api/v1/me");
    saveSession(state.accessToken, user);
  } catch {
    clearSession();
    elements.switchRoleButton.hidden = true;
  }
}

function showView(activeView) {
  elements.views.forEach((view) => {
    view.hidden = view !== activeView;
  });
  document.querySelector("#mainContent").focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: "auto" });
}

function openPatientWorkspace() {
  state.role = "patient";
  showView(elements.patientView);
  renderPatientCase(state.currentPatientCase);
  elements.messageInput.focus();
}

async function submitPatientMessage(event) {
  event.preventDefault();
  if (state.patientBusy) return;

  const message = elements.messageInput.value.trim();
  if (!message) {
    elements.messageError.textContent = "Vui lòng nhập mô tả triệu chứng.";
    elements.messageInput.focus();
    return;
  }

  elements.messageError.textContent = "";
  elements.welcomeMessage?.remove();
  addChatMessage("patient", message);
  elements.messageInput.value = "";
  const pendingMessage = addChatMessage("pending", "Hệ thống đang kiểm tra thông tin bạn cung cấp.");
  setPatientBusy(true);

  const payload = { message };
  if (state.caseId) payload.case_id = state.caseId;

  try {
    const response = await fetchJson("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    pendingMessage.remove();
    state.caseId = response.case_id;
    state.currentPatientCase = response;
    addChatMessage("system", response.response || "Thông tin đã được ghi nhận.");
    renderPatientCase(response);
  } catch (error) {
    pendingMessage.remove();
    elements.messageInput.value = message;
    addChatMessage("error", readableError(error, "Không thể gửi thông tin. Vui lòng thử lại."));
    elements.messageError.textContent = "Tin nhắn chưa được gửi.";
  } finally {
    setPatientBusy(false);
    elements.messageInput.focus();
  }
}

function addChatMessage(role, content) {
  const node = document.createElement("div");
  const normalizedRole = role === "pending" || role === "error" ? `system ${role}` : role;
  node.className = `message ${normalizedRole}`;
  node.textContent = content;
  elements.messages.appendChild(node);
  elements.messages.scrollTop = elements.messages.scrollHeight;
  return node;
}

function setPatientBusy(isBusy) {
  state.patientBusy = isBusy;
  elements.messageInput.disabled = isBusy;
  elements.sendButton.disabled = isBusy;
  elements.sendButton.textContent = isBusy ? "Đang gửi" : "Gửi";
  elements.symptomChoices.querySelectorAll("button").forEach((button) => {
    button.disabled = isBusy;
  });
}

function renderPatientCase(data) {
  if (!data) {
    elements.patientCaseId.textContent = "Chưa có";
    elements.patientStateValue.textContent = "Chưa bắt đầu";
    elements.patientStateHelp.textContent = "Chọn một nhóm triệu chứng hoặc nhập mô tả để bắt đầu.";
    elements.patientOutcome.hidden = true;
    elements.emergencyBanner.hidden = true;
    return;
  }

  const status = data.status || "collecting_information";
  const hasRedFlags = Array.isArray(data.red_flags) && data.red_flags.length > 0;

  elements.patientCaseId.textContent = shortCaseId(data.case_id);
  elements.patientStateValue.textContent = statusLabels[status] || "Đang xử lý";
  elements.patientStateHelp.textContent = patientStatusHelp(status, hasRedFlags);
  renderEmergencyState(hasRedFlags || status === "escalated");
  renderPatientOutcome(data);
}

function patientStatusHelp(status, hasRedFlags) {
  if (hasRedFlags) return "Ca đã được đưa vào hàng đợi ưu tiên để nhân viên y tế xem xét.";
  if (status === "collecting_information") return "Hệ thống có thể cần bạn trả lời thêm một số câu hỏi.";
  if (status === "awaiting_approval" || status === "needs_nurse_review") return "Chưa có hướng dẫn nào được gửi trước khi nhân viên y tế duyệt.";
  if (status === "approved") return "Phản hồi đã được nhân viên y tế xác nhận.";
  if (status === "escalated") return "Ca đã được chuyển sang mức cấp cứu.";
  return "Ca đang được xử lý.";
}

function renderEmergencyState(isEmergency) {
  elements.emergencyBanner.hidden = !isEmergency;
  if (isEmergency) {
    elements.acknowledgeEmergencyButton.disabled = false;
    elements.acknowledgeEmergencyButton.textContent = "Tôi đã đọc";
  }
}

function acknowledgeEmergency() {
  elements.acknowledgeEmergencyButton.disabled = true;
  elements.acknowledgeEmergencyButton.textContent = "Đã xác nhận";
  elements.patientOutcome.scrollIntoView({ block: "nearest" });
}

function renderPatientOutcome(data) {
  const status = data.status;
  elements.patientOutcome.classList.remove("is-approved", "is-emergency");

  if (status === "collecting_information") {
    elements.patientOutcome.hidden = true;
    return;
  }

  elements.patientOutcome.hidden = false;
  elements.checkResultButton.hidden = false;

  if (status === "approved") {
    elements.patientOutcome.classList.add("is-approved");
    elements.patientOutcomeLabel.textContent = "Đã được nhân viên y tế duyệt";
    elements.patientOutcomeTitle.textContent = "Phản hồi dành cho bạn";
    elements.patientOutcomeBody.textContent =
      data.patient_visible_response || data.response || "Phản hồi đã được xác nhận.";
    elements.checkResultButton.hidden = true;
    return;
  }

  if (status === "escalated" || (data.red_flags || []).length > 0) {
    elements.patientOutcome.classList.add("is-emergency");
    elements.patientOutcomeLabel.textContent = "Đang được ưu tiên xử lý";
    elements.patientOutcomeTitle.textContent = "Ca đã được chuyển tới nhân viên y tế";
    elements.patientOutcomeBody.textContent = "Không chờ phản hồi trực tuyến nếu triệu chứng đang nặng lên. Hãy gọi 115 ngay.";
    return;
  }

  if (status === "rejected") {
    elements.patientOutcomeLabel.textContent = "Cần đánh giá lại";
    elements.patientOutcomeTitle.textContent = "Chưa có phản hồi được duyệt";
    elements.patientOutcomeBody.textContent = "Vui lòng liên hệ trực tiếp với cơ sở y tế nếu bạn cần hỗ trợ.";
    elements.checkResultButton.hidden = true;
    return;
  }

  elements.patientOutcomeLabel.textContent = "Đang chờ duyệt";
  elements.patientOutcomeTitle.textContent = "Thông tin đã được chuyển tới nhân viên y tế";
  elements.patientOutcomeBody.textContent = "Bạn có thể kiểm tra lại kết quả trong ít phút. Nếu triệu chứng nặng lên, hãy gọi 115.";
}

async function checkPatientResult() {
  if (!state.caseId || state.patientBusy) return;
  elements.checkResultButton.disabled = true;
  elements.checkResultButton.textContent = "Đang kiểm tra";

  try {
    const data = await fetchJson(`/api/v1/cases/${state.caseId}`);
    const previousResponse = state.currentPatientCase?.patient_visible_response;
    state.currentPatientCase = data;
    renderPatientCase(data);

    if (data.patient_visible_response && data.patient_visible_response !== previousResponse) {
      addChatMessage(data.status === "collecting_information" ? "nurse" : "system", data.patient_visible_response);
    }
    showToast("Đã cập nhật trạng thái ca.");
  } catch (error) {
    showToast(readableError(error, "Không thể kiểm tra kết quả."), true);
  } finally {
    elements.checkResultButton.disabled = false;
    elements.checkResultButton.textContent = "Kiểm tra kết quả";
  }
}

function startNewCase() {
  state.caseId = null;
  state.currentPatientCase = null;
  elements.messages.replaceChildren();

  const welcome = document.createElement("div");
  welcome.className = "welcome-message";
  welcome.id = "welcomeMessage";
  const title = document.createElement("strong");
  title.textContent = "Bạn đang gặp triệu chứng gì?";
  const body = document.createElement("p");
  body.textContent = "Chọn một nhóm bên dưới hoặc mô tả bằng lời của bạn.";
  welcome.append(title, body);
  elements.messages.appendChild(welcome);
  elements.welcomeMessage = welcome;

  renderPatientCase(null);
  showView(elements.disclaimerView);
  elements.acceptDisclaimerButton.focus();
}

function startQueuePolling() {
  stopQueuePolling();
  refreshQueue();
  state.queueTimer = window.setInterval(() => refreshQueue({ silent: true }), 15000);
}

function stopQueuePolling() {
  if (state.queueTimer) {
    window.clearInterval(state.queueTimer);
    state.queueTimer = null;
  }
}

async function refreshQueue({ silent = false, force = false } = {}) {
  if (state.nurseBusy && !force) return;

  if (!silent && state.queue.length === 0) {
    setQueueMessage("Đang tải hàng đợi", "Vui lòng chờ trong giây lát.");
  }
  elements.refreshQueueButton.disabled = true;
  elements.refreshQueueButton.textContent = "Đang tải";

  try {
    const cases = await fetchJson("/api/v1/nurse/queue");
    state.queue = Array.isArray(cases) ? cases : [];
    elements.pendingCaseCount.textContent = String(state.queue.filter((item) => pendingStatuses.has(item.status)).length);
    elements.queueUpdatedAt.textContent = `Cập nhật lúc ${new Date().toLocaleTimeString("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
    })}`;
    renderQueue();
  } catch (error) {
    if (state.queue.length > 0) {
      setQueueMessage("Không tải được dữ liệu mới", "Danh sách gần nhất vẫn được giữ lại.", true);
      renderQueue({ keepMessage: true });
    } else {
      setQueueMessage("Không thể tải hàng đợi", "Kiểm tra kết nối và thử lại.", true);
    }
  } finally {
    elements.refreshQueueButton.disabled = false;
    elements.refreshQueueButton.textContent = "Làm mới";
  }
}

function renderQueue({ keepMessage = false } = {}) {
  const filtered = filterQueue(state.queue, elements.queueFilter.value).sort(compareCases);
  elements.queueList.replaceChildren();

  if (filtered.length === 0) {
    setQueueMessage(
      elements.queueFilter.value === "pending" ? "Không có ca nào đang chờ duyệt" : "Không có ca phù hợp",
      "Danh sách sẽ tự động cập nhật mỗi 15 giây.",
    );
    return;
  }

  if (!keepMessage) elements.queueMessage.hidden = true;

  filtered.forEach((item) => {
    const priority = item.triage_proposal?.priority || "Manual review";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "queue-item";
    if (priority === "Emergency") button.classList.add("is-emergency");
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(item.case_id === state.selectedNurseCase?.case_id));
    button.setAttribute("aria-label", `${shortCaseId(item.case_id)}, ${priorityLabels[priority]}, ${statusLabels[item.status]}`);

    const top = document.createElement("span");
    top.className = "queue-item-top";
    const caseName = document.createElement("strong");
    caseName.textContent = `Ca ${shortCaseId(item.case_id)}`;
    const priorityText = document.createElement("span");
    priorityText.textContent = priorityLabels[priority] || priority;
    top.append(caseName, priorityText);

    const bottom = document.createElement("span");
    bottom.className = "queue-item-bottom";
    const symptom = document.createElement("span");
    symptom.textContent = symptomGroupLabel(item.structured_data?.symptom_group);
    const status = document.createElement("span");
    status.textContent = statusLabels[item.status] || item.status;
    bottom.append(symptom, status);

    button.append(top, bottom);
    button.addEventListener("click", () => loadNurseCase(item.case_id));
    elements.queueList.appendChild(button);
  });
}

function filterQueue(cases, filter) {
  if (filter === "all") return cases.slice();
  if (filter === "emergency") {
    return cases.filter((item) => item.triage_proposal?.priority === "Emergency");
  }
  if (filter === "completed") {
    return cases.filter((item) => completedStatuses.has(item.status));
  }
  return cases.filter((item) => pendingStatuses.has(item.status));
}

function compareCases(left, right) {
  const leftCompleted = completedStatuses.has(left.status) ? 1 : 0;
  const rightCompleted = completedStatuses.has(right.status) ? 1 : 0;
  if (leftCompleted !== rightCompleted) return leftCompleted - rightCompleted;

  const leftPriority = priorityRanks[left.triage_proposal?.priority] ?? 99;
  const rightPriority = priorityRanks[right.triage_proposal?.priority] ?? 99;
  return leftPriority - rightPriority;
}

function setQueueMessage(title, body, isError = false) {
  elements.queueMessage.replaceChildren();
  const strong = document.createElement("strong");
  strong.textContent = title;
  const span = document.createElement("span");
  span.textContent = body;
  elements.queueMessage.append(strong, span);
  elements.queueMessage.classList.toggle("is-error", isError);
  elements.queueMessage.hidden = false;
}

async function loadNurseCase(caseId) {
  setNurseBusy(true);
  elements.reviewError.textContent = "";

  try {
    const data = await fetchJson(`/api/v1/cases/${caseId}`);
    state.selectedNurseCase = data;
    renderNurseCase(data);
    renderQueue();
  } catch (error) {
    showToast(readableError(error, "Không thể tải chi tiết ca."), true);
  } finally {
    setNurseBusy(false);
  }
}

function renderNurseCase(data) {
  elements.caseEmptyState.hidden = true;
  elements.caseDetail.hidden = false;

  const priority = data.triage_proposal?.priority || "Manual review";
  const summary = data.summary || {};
  const structuredData = data.structured_data || {};
  const validation = data.validation || {};
  const redFlags = Array.isArray(data.red_flags) ? data.red_flags : [];
  const missing = summary.missing_information || validation.missing_fields || structuredData.missing_fields || [];

  elements.selectedCaseId.textContent = `Ca ${shortCaseId(data.case_id)}`;
  elements.selectedCaseStatus.textContent = statusLabels[data.status] || data.status;
  elements.selectedCaseStatus.className = `status-badge ${statusClass(data.status)}`;
  elements.selectedCasePriority.textContent = priorityLabels[priority] || priority;
  elements.selectedCasePriority.className = `priority-badge ${priorityClass(priority)}`;

  elements.summaryComplaint.textContent = summary.chief_complaint
    ? humanize(summary.chief_complaint)
    : symptomGroupLabel(structuredData.symptom_group);
  elements.summaryOnset.textContent = summary.onset ? humanize(summary.onset) : "Thiếu thông tin";
  elements.summarySeverity.textContent = displayValue(summary.severity, "Thiếu thông tin");
  elements.summaryConfidence.textContent = Number.isFinite(structuredData.confidence)
    ? `${Math.round(structuredData.confidence * 100)}%`
    : "Chưa có";

  renderTags(elements.associatedSymptoms, summary.associated_symptoms || [], "Chưa ghi nhận", false);
  renderTags(elements.missingInformation, missing, "Không còn trường bắt buộc bị thiếu", true);
  elements.missingBlock.hidden = missing.length === 0;

  elements.proposalPriority.textContent = priorityLabels[priority] || priority;
  elements.proposalReason.textContent = localizeProposalReason(
    data.triage_proposal?.reason || summary.protocol_reason || "Chưa có lý do phân loại.",
  );
  elements.editedPriority.value = priority;

  renderRedFlags(redFlags);
  renderCaseAlert(redFlags, missing);
  renderConversation(data.conversation || []);

  const existingResponse = completedStatuses.has(data.status) ? data.patient_visible_response : null;
  elements.approvedResponse.value = existingResponse || defaultPatientResponse(priority);
  elements.nurseNotes.value = "";
  elements.reviewError.textContent = "";
  updateReviewAvailability();
}

function renderTags(container, values, emptyText, isMissing) {
  container.replaceChildren();
  if (!values.length) {
    const empty = document.createElement("span");
    empty.className = "tag is-empty";
    empty.textContent = emptyText;
    container.appendChild(empty);
    return;
  }

  values.forEach((value) => {
    const tag = document.createElement("span");
    tag.className = `tag${isMissing ? " is-missing" : ""}`;
    tag.textContent = humanize(value);
    container.appendChild(tag);
  });
}

function renderRedFlags(redFlags) {
  elements.redFlagList.replaceChildren();
  elements.redFlagSection.hidden = redFlags.length === 0;

  redFlags.forEach((finding) => {
    const item = document.createElement("div");
    item.className = "red-flag-item";
    item.textContent = finding.label || humanize(finding.code) || "Dấu hiệu nguy hiểm";
    elements.redFlagList.appendChild(item);
  });
}

function renderCaseAlert(redFlags, missing) {
  if (redFlags.length > 0) {
    elements.caseAlert.hidden = false;
    elements.caseAlert.textContent = "Ca có red flag. Ưu tiên đánh giá ngay và không trì hoãn hành động cấp cứu cần thiết.";
    return;
  }

  if (missing.length > 0) {
    elements.caseAlert.hidden = false;
    elements.caseAlert.textContent = `Còn ${missing.length} trường thông tin cần được kiểm tra trước khi duyệt.`;
    return;
  }

  elements.caseAlert.hidden = true;
  elements.caseAlert.textContent = "";
}

function renderConversation(conversation) {
  elements.conversationHistory.replaceChildren();

  if (!conversation.length) {
    const empty = document.createElement("p");
    empty.textContent = "Chưa có lịch sử trao đổi.";
    elements.conversationHistory.appendChild(empty);
    return;
  }

  conversation.forEach((message) => {
    const item = document.createElement("div");
    item.className = `history-message${message.role === "patient" ? " is-patient" : ""}`;
    const role = document.createElement("strong");
    role.textContent = roleLabel(message.role);
    const content = document.createElement("span");
    content.textContent = message.content;
    item.append(role, content);
    elements.conversationHistory.appendChild(item);
  });
}

function updateReviewAvailability() {
  const completed = completedStatuses.has(state.selectedNurseCase?.status);
  [elements.approveButton, elements.askMoreButton, elements.escalateButton].forEach((button) => {
    button.disabled = state.nurseBusy || completed;
  });
  elements.editedPriority.disabled = state.nurseBusy || completed;
  elements.approvedResponse.disabled = state.nurseBusy || completed;
  elements.nurseNotes.disabled = state.nurseBusy || completed;

  if (completed) {
    elements.reviewError.textContent = "Ca này đã được xử lý. Các hành động duyệt đã được khóa trong bản demo.";
  }
}

async function reviewCase(requestedAction) {
  const currentCase = state.selectedNurseCase;
  if (!currentCase || state.nurseBusy || completedStatuses.has(currentCase.status)) return;

  const responseText = elements.approvedResponse.value.trim();
  if (!responseText) {
    elements.reviewError.textContent =
      requestedAction === "ask_more"
        ? "Nhập câu hỏi cần bệnh nhân bổ sung."
        : "Nhập nội dung đã được nhân viên y tế xác nhận.";
    elements.approvedResponse.focus();
    return;
  }

  const originalPriority = currentCase.triage_proposal?.priority;
  let selectedPriority = elements.editedPriority.value;
  let action = requestedAction;
  if (action === "escalate") {
    action = "edit";
    selectedPriority = "Emergency";
  } else if (action === "approve" && selectedPriority !== originalPriority) {
    action = "edit";
  }

  const payload = {
    action,
    nurse_notes: elements.nurseNotes.value.trim() || null,
  };

  if (action === "ask_more") {
    payload.ask_more_question = responseText;
  } else {
    payload.approved_response = responseText;
  }

  if (action === "edit") payload.edited_priority = selectedPriority;

  setNurseBusy(true);
  elements.reviewError.textContent = "";

  try {
    const result = await fetchJson(`/api/v1/cases/${currentCase.case_id}/review`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const updatedCase = await fetchJson(`/api/v1/cases/${currentCase.case_id}`);
    state.selectedNurseCase = updatedCase;
    renderNurseCase(updatedCase);

    if (state.caseId === updatedCase.case_id) {
      state.currentPatientCase = updatedCase;
    }

    await refreshQueue({ silent: true, force: true });
    showToast(requestedAction === "escalate" ? "Đã chuyển ca sang mức cấp cứu." : reviewSuccessMessage(result.status));
  } catch (error) {
    elements.reviewError.textContent = readableError(error, "Không thể lưu quyết định. Vui lòng thử lại.");
  } finally {
    setNurseBusy(false);
    updateReviewAvailability();
  }
}

function setNurseBusy(isBusy) {
  state.nurseBusy = isBusy;
  if (!state.selectedNurseCase) return;

  const completed = completedStatuses.has(state.selectedNurseCase.status);

  [elements.approveButton, elements.askMoreButton, elements.escalateButton].forEach((button) => {
    button.disabled = isBusy || completed;
  });
  elements.editedPriority.disabled = isBusy || completed;
  elements.approvedResponse.disabled = isBusy || completed;
  elements.nurseNotes.disabled = isBusy || completed;

  elements.approveButton.textContent = isBusy ? "Đang lưu" : "Duyệt và gửi";
}

function defaultPatientResponse(priority) {
  if (priority === "Emergency") {
    return "Nhân viên y tế đã xem thông tin bạn cung cấp. Hãy gọi 115 hoặc đến cơ sở y tế gần nhất ngay nếu triệu chứng đang diễn ra.";
  }
  if (priority === "Urgent") {
    return "Nhân viên y tế đã xem thông tin bạn cung cấp và khuyến nghị bạn được khám sớm. Nếu triệu chứng nặng lên, hãy gọi 115.";
  }
  if (priority === "Self-care" || priority === "Routine") {
    return "Nhân viên y tế đã xem thông tin bạn cung cấp. Hãy tiếp tục theo dõi và liên hệ cơ sở y tế nếu triệu chứng nặng hơn hoặc xuất hiện dấu hiệu bất thường.";
  }
  return "Nhân viên y tế đã xem thông tin bạn cung cấp và sẽ liên hệ theo mức ưu tiên phù hợp.";
}

function reviewSuccessMessage(status) {
  if (status === "approved") return "Đã duyệt và lưu phản hồi cho bệnh nhân.";
  if (status === "escalated") return "Đã chuyển ca sang mức cấp cứu.";
  if (status === "collecting_information") return "Đã gửi yêu cầu bổ sung thông tin.";
  return "Đã lưu quyết định.";
}

function statusClass(status) {
  if (status === "approved") return "status-approved";
  if (status === "escalated") return "status-escalated";
  if (pendingStatuses.has(status)) return "status-pending";
  return "";
}

function priorityClass(priority) {
  if (priority === "Emergency") return "priority-emergency";
  if (priority === "Urgent" || priority === "Manual review") return "priority-urgent";
  if (priority === "Self-care" || priority === "Routine") return "priority-self-care";
  return "";
}

function shortCaseId(caseId) {
  if (!caseId) return "Chưa có";
  const value = String(caseId);
  return value.length > 10 ? value.slice(0, 8).toUpperCase() : value.toUpperCase();
}

function symptomGroupLabel(value) {
  if (!value) return "Chưa xác định nhóm";
  return symptomGroupLabels[value] || humanize(value);
}

function humanize(value) {
  if (value === null || value === undefined || value === "") return "Chưa có";
  const normalized = String(value).trim().toLowerCase().replaceAll(" ", "_");
  if (clinicalLabels[normalized]) return clinicalLabels[normalized];
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function displayValue(value, fallback) {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function localizeProposalReason(value) {
  return String(value)
    .replace(/^Red-flag safety layer matched:\s*/i, "Khớp quy tắc red flag: ")
    .replace(/^Manual review required:?\s*/i, "Cần nhân viên y tế đánh giá: ");
}

function roleLabel(role) {
  if (role === "patient") return "Bệnh nhân";
  if (role === "nurse") return "Nhân viên y tế";
  return "Hệ thống";
}

async function fetchJson(url, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (state.accessToken) headers.Authorization = `Bearer ${state.accessToken}`;
  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let message = `Yêu cầu thất bại (${response.status}).`;
    try {
      const payload = await response.json();
      if (Array.isArray(payload.detail)) {
        message = payload.detail.map((item) => item.msg).join("; ") || message;
      } else {
        message = payload.detail || message;
      }
    } catch {
      const text = await response.text();
      if (text) message = text;
    }
    throw new Error(message);
  }

  return response.json();
}

function readableError(error, fallback) {
  if (!error) return fallback;
  if (typeof error.message === "string" && error.message.trim()) return error.message;
  return fallback;
}

function showToast(message, isError = false) {
  window.clearTimeout(state.toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.toggle("is-error", isError);
  elements.toast.hidden = false;
  state.toastTimer = window.setTimeout(() => {
    elements.toast.hidden = true;
  }, 4000);
}

async function checkSystemStatus() {
  setSystemStatus("Đang kết nối", "loading");
  try {
    await fetchJson("/health");
    setSystemStatus("Hệ thống sẵn sàng", "ready");
  } catch {
    setSystemStatus("Mất kết nối", "error");
  }
}

function setSystemStatus(label, variant) {
  const text = elements.systemStatus.querySelector("span:last-child");
  text.textContent = label;
  elements.systemStatus.classList.toggle("is-ready", variant === "ready");
  elements.systemStatus.classList.toggle("is-error", variant === "error");
}

checkSystemStatus();
restoreSession();

const resetToken = new URLSearchParams(window.location.search).get("reset_token");
if (resetToken) {
  elements.roleChoices.hidden = true;
  elements.authPanel.hidden = true;
  elements.resetPasswordPanel.hidden = false;
  elements.resetPasswordPanel.dataset.token = resetToken;
  elements.newPassword.focus();
}
