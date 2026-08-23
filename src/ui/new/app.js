import { api } from "./api.js";
import { clearSession, state } from "./state.js";
import { renderAccess, renderAuth, renderPasswordReset, renderRoleSelect, renderVerification } from "./features/auth.js?v=design-20260823r";
import { renderDisclaimer, renderPatientCases, renderPatientChat, renderPatientHome, renderPatientResult, renderRedFlag, startPatientCase, stopCasePolling } from "./features/patient.js?v=design-20260823r";
import { renderNurseCase, renderNurseDone, renderNurseQueue, renderNurseShift, stopNurseChatPolling, stopQueuePolling } from "./features/nurse.js?v=design-20260823r";
import { renderNurseDashboard, stopDashboardPolling } from "./features/dashboard.js?v=design-20260823r";

const app = document.querySelector("#app");

export function navigate(view, options = {}) {
  stopQueuePolling();
  stopDashboardPolling();
  stopNurseChatPolling();
  stopCasePolling();
  state.view = view;
  if (view === "access") renderAccess(app, { navigate, logout });
  if (view === "role-select") renderRoleSelect(app, { navigate });
  if (view === "auth") renderAuth(app, { navigate, role: options.role || state.role || "patient", onAuthenticated });
  if (view === "verify") renderVerification(app, { navigate, email: options.email || state.pendingVerificationEmail });
  if (view === "reset") renderPasswordReset(app, { navigate, token: options.token || new URLSearchParams(location.search).get("reset_token") });
  if (view === "patient-home") renderPatientHome(app, { navigate, logout });
  if (view === "disclaimer") renderDisclaimer(app, { navigate, logout, onAccept: () => startPatientCase(app, { navigate, logout, fresh: true }) });
  if (view === "patient-chat") renderPatientChat(app, { navigate, logout });
  // W-04: màn hình chiếm trọn khung, không phải một khối trong trang chat. Đó là lý do nó là một
  // view riêng chứ không phải một nhánh markup của `patient-chat`.
  if (view === "red-flag") renderRedFlag(app, { navigate, logout });
  if (view === "patient-cases") renderPatientCases(app, { navigate, logout });
  if (view === "patient-result") renderPatientResult(app, { navigate, logout });
  if (view === "nurse-queue") renderNurseQueue(app, { navigate, logout });
  if (view === "nurse-done") renderNurseDone(app, { navigate, logout });
  if (view === "nurse-dashboard") renderNurseDashboard(app, { navigate, logout });
  if (view === "nurse-shift") renderNurseShift(app, { navigate, logout });
  if (view === "nurse-case") renderNurseCase(app, { navigate, logout });
  app.focus();
}

// Màn đầu tiên sau khi đăng nhập, theo vai trò. Nhân viên y tế vào thẳng bảng điều khiển; hàng đợi
// nằm ngay mục kế bên trên thanh điều hướng trái.
const homeView = { nurse: "nurse-dashboard", patient: "patient-home" };

async function onAuthenticated(session) {
  state.role = session.user.role;
  navigate(homeView[session.user.role] || "patient-home");
}

function logout() {
  clearSession();
  navigate("access");
}

async function boot() {
  const token = new URLSearchParams(location.search).get("reset_token");
  if (token) {
    navigate("reset", { token });
    return;
  }

  if (state.accessToken) {
    try {
      const user = await api("/api/v1/me");
      state.user = user;
      state.role = user.role;
      navigate(homeView[user.role] || "patient-home");
      return;
    } catch {
      clearSession();
    }
  }
  navigate("access");
}

boot();
