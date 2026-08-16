import { api } from "./api.js";
import { clearSession, state } from "./state.js";
import { renderAccess, renderAuth, renderPasswordReset, renderVerification } from "./features/auth.js?v=login-example-20260813";
import { renderDisclaimer, renderPatientChat, renderPatientHome, startPatientCase } from "./features/patient.js?v=chat-loading-20260816";
import { renderNurseCase, renderNurseQueue, stopQueuePolling } from "./features/nurse.js?v=settings-full-20260813";

const app = document.querySelector("#app");

export function navigate(view, options = {}) {
  stopQueuePolling();
  state.view = view;
  if (view === "access") renderAccess(app, { navigate, logout });
  if (view === "auth") renderAuth(app, { navigate, role: options.role || state.role || "patient", onAuthenticated });
  if (view === "verify") renderVerification(app, { navigate, email: options.email || state.pendingVerificationEmail });
  if (view === "reset") renderPasswordReset(app, { navigate, token: options.token || new URLSearchParams(location.search).get("reset_token") });
  if (view === "patient-home") renderPatientHome(app, { navigate, logout });
  if (view === "disclaimer") renderDisclaimer(app, { navigate, logout, onAccept: () => startPatientCase(app, { navigate, logout, fresh: true }) });
  if (view === "patient-chat") renderPatientChat(app, { navigate, logout });
  if (view === "nurse-queue") renderNurseQueue(app, { navigate, logout });
  if (view === "nurse-case") renderNurseCase(app, { navigate, logout });
  app.focus();
}

async function onAuthenticated(session) {
  state.role = session.user.role;
  navigate(session.user.role === "nurse" ? "nurse-queue" : "patient-home");
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
      navigate(user.role === "nurse" ? "nurse-queue" : "patient-home");
      return;
    } catch {
      clearSession();
    }
  }
  navigate("access");
}

boot();
