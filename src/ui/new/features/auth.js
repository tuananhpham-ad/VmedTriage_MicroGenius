import { api } from "../api.js";
import { saveSession, state } from "../state.js";
import { escapeHtml, logo, showToast } from "../shared.js";

export function renderAccess(root, { navigate }) {
  root.innerHTML = `
    <section class="landing-shell" aria-labelledby="access-title">
      <header class="public-header"><a class="brand" href="/" aria-label="VMedTriage">${logo()}</a></header>
      <div class="access-layout">
        <div class="access-copy"><p class="eyebrow">Hỗ trợ phân luồng ban đầu</p><h1 id="access-title">Đồng hành cùng sức khỏe của bạn.</h1><p class="access-description">Phân luồng y tế thông minh, kết nối nhanh chóng.</p><figure class="ai-doctor-visual"><img src="/assets/triage-ai-doctor.png" alt="Robot AI mặc áo blouse hỗ trợ phân luồng y tế" /></figure><p class="emergency-note"><strong>Trường hợp khẩn cấp:</strong> gọi 115 hoặc đến cơ sở y tế gần nhất.</p></div>
        <div class="role-grid" aria-label="Chọn vai trò truy cập">
          <button class="role-card" type="button" data-role="patient"><span class="role-icon role-icon-patient" aria-hidden="true"><i></i></span><span><strong>Bệnh nhân</strong><small>Khai báo triệu chứng, theo dõi ca đang mở và nhận hướng dẫn đã duyệt.</small></span><b>Tiếp tục</b></button>
          <button class="role-card" type="button" data-role="nurse"><span class="role-icon role-icon-clinician" aria-hidden="true"><i></i></span><span><strong>Nhân viên y tế</strong><small>Xem hàng đợi, kiểm tra thông tin lâm sàng và duyệt phản hồi.</small></span><b>Tiếp tục</b></button>
        </div>
      </div>
    </section>`;
  root.querySelectorAll("[data-role]").forEach((button) => {
    button.addEventListener("click", () => navigate("auth", { role: button.dataset.role }));
  });
}

export function renderAuth(root, { navigate, role, onAuthenticated }) {
  let mode = "login";
  let selectedRole = role;

  const draw = () => {
    const isRegister = mode === "register";
    root.innerHTML = `
      <section class="auth-shell" aria-labelledby="auth-title">
        <button class="back-button" type="button" data-back>← Quay lại</button>
        <div class="auth-card">
          <div class="auth-intro"><a class="brand brand-large" href="/">${logo()}</a><p>Hỗ trợ phân loại mức độ khẩn cấp, có điều dưỡng xác nhận.</p><div class="auth-intro-copy"><h1>${isRegister ? "Bắt đầu cùng VMedTriage" : "Chào mừng trở lại"}</h1><p>${isRegister ? "Thông tin của bạn giúp đánh giá triệu chứng chính xác hơn và luôn được bảo mật." : selectedRole === "nurse" ? "Tiếp tục kiểm tra hàng đợi và các ca cần được duyệt." : "Xem lại triệu chứng đã khai báo và hướng dẫn xử trí đã được điều dưỡng duyệt."}</p></div></div>
          <div class="auth-panel">
            <div class="auth-tabs" role="tablist"><button type="button" class="${!isRegister ? "is-active" : ""}" data-mode="login">Đăng nhập</button><button type="button" class="${isRegister ? "is-active" : ""}" data-mode="register">Đăng ký</button></div>
            <form id="auth-form" class="auth-form" novalidate>
              <p class="form-error" id="auth-error" role="alert"></p>
              ${isRegister ? registrationFields(selectedRole) : loginFields()}
              <button class="primary-button" type="submit">${isRegister ? "Tạo tài khoản" : "Đăng nhập"}</button>
              ${!isRegister ? '<button class="link-button center" type="button" data-forgot>Quên mật khẩu?</button>' : ""}
              <p class="auth-switch">${isRegister ? 'Đã có tài khoản? <button type="button" data-mode="login">Đăng nhập</button>' : 'Chưa có tài khoản? <button type="button" data-mode="register">Đăng ký</button>'}</p>
            </form>
          </div>
        </div>
      </section>`;

    root.querySelector("[data-back]").addEventListener("click", () => navigate("access"));
    root.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => { mode = button.dataset.mode; draw(); }));
    root.querySelector("[data-forgot]")?.addEventListener("click", () => renderForgotPassword(root, { navigate, back: draw }));
    root.querySelector("#auth-form").addEventListener("submit", (event) => submitAuth(event, { isRegister, selectedRole, navigate, onAuthenticated }));
  };
  draw();
}

function loginFields() {
  return `<label>Email hoặc tên đăng nhập<input name="email" autocomplete="username" maxlength="320" required placeholder="ten@email.com" /></label><label>Mật khẩu<input name="password" type="password" autocomplete="current-password" maxlength="128" required placeholder="Nhập mật khẩu" /></label>`;
}

function registrationFields(role) {
  return `<div class="form-grid">
    <label>Họ và tên<input name="full_name" autocomplete="name" minlength="2" maxlength="120" required /></label>
    <label>Số điện thoại<input name="phone_number" type="tel" autocomplete="tel" maxlength="32" required /></label>
  </div>
  <label>Email<input name="email" type="email" autocomplete="email" maxlength="320" required /><small>Dùng để xác thực tài khoản và nhận thông tin quan trọng.</small></label>
  <div class="form-grid"><label>Mật khẩu<input name="password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required /></label><label>Xác nhận mật khẩu<input name="confirm_password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required /></label></div>
  ${role === "nurse" ? `<div class="nurse-fields"><h2>Thông tin xác minh nhân viên y tế</h2><label>Mã đăng ký nội bộ<input name="nurse_registration_code" type="password" maxlength="256" required /></label><div class="form-grid"><label>Giấy phép hoặc chứng chỉ<input name="professional_license" maxlength="160" required /></label><label>Nơi công tác<input name="workplace" maxlength="160" required /></label><label>Khoa hoặc phòng ban<input name="department" maxlength="160" required /></label></div><label>Tiểu sử chuyên môn<textarea name="bio" rows="3" maxlength="2000" required></textarea></label></div>` : ""}
  <label class="checkbox-field"><input name="terms_accepted" type="checkbox" required /> Tôi đã đọc và chấp nhận Điều khoản sử dụng cùng Chính sách quyền riêng tư.</label>`;
}

async function submitAuth(event, { isRegister, selectedRole, navigate, onAuthenticated }) {
  event.preventDefault();
  const form = event.currentTarget;
  const error = form.querySelector("#auth-error");
  const button = form.querySelector("button[type=submit]");
  error.textContent = "";
  button.disabled = true;
  button.textContent = isRegister ? "Đang tạo tài khoản" : "Đang đăng nhập";

  try {
    const values = new FormData(form);
    if (isRegister) {
      const payload = Object.fromEntries(values.entries());
      payload.terms_accepted = values.get("terms_accepted") === "on";
      payload.role = selectedRole;
      await api("/api/v1/register", { method: "POST", body: JSON.stringify(payload) });
      state.pendingVerificationEmail = payload.email;
      navigate("verify", { email: payload.email });
      return;
    }
    const session = await api("/api/v1/login", { method: "POST", body: JSON.stringify(Object.fromEntries(values.entries())) });
    saveSession(session.access_token, session.user);
    await onAuthenticated(session);
  } catch (problem) {
    error.textContent = problem.message || "Không thể hoàn tất xác thực.";
  } finally {
    button.disabled = false;
    button.textContent = isRegister ? "Tạo tài khoản" : "Đăng nhập";
  }
}

export function renderVerification(root, { navigate, email }) {
  root.innerHTML = `<section class="auth-shell"><div class="compact-card"><a class="brand brand-large" href="/">${logo()}</a><p class="eyebrow">Xác thực email</p><h1>Nhập mã xác thực</h1><p>Mã gồm 6 chữ số đã được gửi tới <strong>${escapeHtml(email)}</strong>.</p><form id="verify-form" class="auth-form"><label>Mã xác thực<input name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" required /></label><p class="form-error" role="alert"></p><button class="primary-button" type="submit">Xác thực email</button><button class="secondary-button" type="button" data-resend>Gửi lại mã</button><button class="link-button center" type="button" data-back>Quay lại đăng nhập</button></form></div></section>`;
  root.querySelector("[data-back]").addEventListener("click", () => navigate("auth"));
  root.querySelector("[data-resend]").addEventListener("click", async () => {
    try { await api("/api/v1/auth/email-verification/resend", { method: "POST", body: JSON.stringify({ email }) }); showToast("Đã gửi lại mã xác thực."); } catch (problem) { showToast(problem.message, true); }
  });
  root.querySelector("#verify-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const error = event.currentTarget.querySelector(".form-error"); error.textContent = "";
    try { await api("/api/v1/auth/email-verification/confirm", { method: "POST", body: JSON.stringify({ email, code: new FormData(event.currentTarget).get("code") }) }); showToast("Email đã được xác thực. Bạn có thể đăng nhập."); navigate("auth"); } catch (problem) { error.textContent = problem.message; }
  });
}

function renderForgotPassword(root, { navigate, back }) {
  root.innerHTML = `<section class="auth-shell"><div class="compact-card"><a class="brand brand-large" href="/">${logo()}</a><p class="eyebrow">Khôi phục tài khoản</p><h1>Đặt lại mật khẩu</h1><p>Nhập email để nhận liên kết đặt lại mật khẩu.</p><form id="forgot-form" class="auth-form"><label>Email<input name="email" type="email" autocomplete="email" required /></label><p class="form-error" role="alert"></p><button class="primary-button" type="submit">Gửi liên kết</button><button class="link-button center" type="button" data-back>Quay lại</button></form></div></section>`;
  root.querySelector("[data-back]").addEventListener("click", back);
  root.querySelector("#forgot-form").addEventListener("submit", async (event) => { event.preventDefault(); const error = event.currentTarget.querySelector(".form-error"); try { const result = await api("/api/v1/auth/password-reset/request", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) }); showToast(result.message); navigate("auth"); } catch (problem) { error.textContent = problem.message; } });
}

export function renderPasswordReset(root, { navigate, token }) {
  root.innerHTML = `<section class="auth-shell"><div class="compact-card"><a class="brand brand-large" href="/">${logo()}</a><p class="eyebrow">Khôi phục tài khoản</p><h1>Tạo mật khẩu mới</h1><form id="reset-form" class="auth-form"><label>Mật khẩu mới<input name="new_password" type="password" autocomplete="new-password" minlength="8" required /></label><label>Xác nhận mật khẩu mới<input name="confirm_new_password" type="password" autocomplete="new-password" minlength="8" required /></label><p class="form-error" role="alert"></p><button class="primary-button" type="submit">Lưu mật khẩu mới</button></form></div></section>`;
  root.querySelector("#reset-form").addEventListener("submit", async (event) => { event.preventDefault(); const error = event.currentTarget.querySelector(".form-error"); try { const values = Object.fromEntries(new FormData(event.currentTarget)); await api("/api/v1/auth/password-reset/confirm", { method: "POST", body: JSON.stringify({ token, ...values }) }); showToast("Đã đặt lại mật khẩu. Bạn có thể đăng nhập."); history.replaceState({}, "", "/"); navigate("auth"); } catch (problem) { error.textContent = problem.message; } });
}
