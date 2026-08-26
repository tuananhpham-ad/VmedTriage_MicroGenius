import { api } from "./api.js";
import { clearSession, state } from "./state.js";
import { renderAccess, renderAuth, renderPasswordReset, renderRoleSelect, renderVerification } from "./features/auth.js?v=design-20260824g";
import { destroyHospitalMap, renderDisclaimer, renderHospitalSuggestion, renderPatientCases, renderPatientChat, renderPatientHome, renderPatientResult, renderRedFlag, startPatientCase, stopCasePolling } from "./features/patient.js?v=design-20260824g";
import { renderNurseCase, renderNurseDone, renderNurseQueue, renderNurseShift, stopNurseChatPolling, stopQueuePolling } from "./features/nurse.js?v=design-20260824g";
import { renderNurseDashboard, stopDashboardPolling } from "./features/dashboard.js?v=design-20260824g";

const app = document.querySelector("#app");

// Các view không cần đăng nhập. Dùng để chặn trường hợp người dùng bấm Back về một màn hình nội bộ
// sau khi đã đăng xuất — lúc đó session đã bị xoá, render tiếp chỉ ra màn trắng.
const publicViews = new Set(["access", "role-select", "auth", "verify", "reset"]);

// Back/Forward của trình duyệt: mỗi lần `navigate` đẩy một entry vào history stack, nên Back trả về
// view trước đó thay vì thoát hẳn khỏi web. `restoring` để nhánh popstate không đẩy lại entry mới
// (sẽ tạo vòng lặp Back không bao giờ ra được).
let restoring = false;
let historyPrimed = false;

export function navigate(view, options = {}) {
  render(view, options);
  if (restoring) return;
  const entry = { vmedView: state.view, vmedOptions: options };
  const url = `${location.pathname}${location.search}#${state.view}`;
  // Lần đầu thì thay entry hiện tại chứ không đẩy thêm: nếu đẩy, entry gốc (chưa có state) vẫn nằm
  // dưới cùng và Back một nhát sẽ rơi vào đó, không render được gì.
  if (historyPrimed) history.pushState(entry, "", url);
  else history.replaceState(entry, "", url);
  historyPrimed = true;
}

function render(view, options = {}) {
  if (!publicViews.has(view) && !state.accessToken) view = "access";
  stopQueuePolling();
  stopDashboardPolling();
  stopNurseChatPolling();
  stopCasePolling();
  destroyHospitalMap();
  state.view = view;
  if (view === "access") renderAccess(app, { navigate, logout });
  // `onAuthenticated` vì màn chọn vai trò có khối "dùng thử" tạo tài khoản tạm rồi vào thẳng luồng -
  // cùng một đường với nút "Dùng thử" ở màn đăng nhập.
  if (view === "role-select") renderRoleSelect(app, { navigate, onAuthenticated, panel: options.panel });
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
  if (view === "patient-hospital") renderHospitalSuggestion(app, { navigate, logout });
  if (view === "nurse-queue") renderNurseQueue(app, { navigate, logout });
  if (view === "nurse-done") renderNurseDone(app, { navigate, logout });
  if (view === "nurse-dashboard") renderNurseDashboard(app, { navigate, logout });
  if (view === "nurse-shift") renderNurseShift(app, { navigate, logout });
  if (view === "nurse-case") renderNurseCase(app, { navigate, logout });
  app.focus();
}

window.addEventListener("popstate", (event) => {
  const entry = event.state;
  if (!entry || !entry.vmedView) return;
  restoring = true;
  try {
    render(entry.vmedView, entry.vmedOptions || {});
  } finally {
    restoring = false;
  }
});

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
