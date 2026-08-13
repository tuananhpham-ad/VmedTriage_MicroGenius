import { api } from "../api.js";
import { saveSession, state } from "../state.js";
import { escapeHtml, logo, showToast } from "../shared.js";

export function renderAccess(root, { navigate }) {
  root.innerHTML = `
    <section class="landing-shell" aria-labelledby="access-title">
      <header class="public-header"><a class="brand" href="/" aria-label="VMedTriage">${logo()}</a><div class="header-help"><button class="help-trigger" type="button" aria-expanded="false" aria-controls="usage-guide" data-help-toggle>Hướng dẫn sử dụng</button></div></header><div class="help-dialog" id="usage-guide" role="dialog" aria-modal="true" aria-labelledby="usage-guide-title" hidden data-help-panel><button class="help-backdrop" type="button" aria-label="Đóng hướng dẫn" data-help-close></button><section class="help-modal"><div class="help-modal-heading"><div><p class="eyebrow">VMedTriage</p><h2 id="usage-guide-title">Cách thức hoạt động</h2></div><button class="help-close" type="button" aria-label="Đóng hướng dẫn" data-help-close>×</button></div><p class="help-intro">Chọn vai trò để xem đúng luồng thao tác của bạn.</p><div class="guide-tabs" role="tablist" aria-label="Vai trò sử dụng"><button type="button" role="tab" aria-selected="true" aria-controls="guide-patient" id="guide-tab-patient" data-guide-role="patient">Bệnh nhân/người nhà</button><button type="button" role="tab" aria-selected="false" aria-controls="guide-nurse" id="guide-tab-nurse" data-guide-role="nurse">Nhân viên y tế</button></div><section class="guide-role-panel" id="guide-patient" role="tabpanel" aria-labelledby="guide-tab-patient" data-guide-panel="patient"><ol class="guide-steps"><li><span class="guide-icon guide-icon-role" aria-hidden="true"></span><span><strong>Chọn Bệnh nhân/người nhà</strong><small>Đăng nhập hoặc tạo tài khoản để bắt đầu khai báo.</small></span></li><li><span class="guide-icon guide-icon-form" aria-hidden="true"></span><span><strong>Khai báo triệu chứng</strong><small>Trả lời các câu hỏi theo tình trạng thực tế của người bệnh.</small></span></li><li><span class="guide-icon guide-icon-urgent" aria-hidden="true"></span><span><strong>Nhận hướng dẫn xử trí</strong><small>Theo dõi phản hồi đã duyệt; gọi 115 ngay nếu có dấu hiệu khẩn cấp.</small></span></li></ol></section><section class="guide-role-panel" id="guide-nurse" role="tabpanel" aria-labelledby="guide-tab-nurse" hidden data-guide-panel="nurse"><ol class="guide-steps"><li><span class="guide-icon guide-icon-role" aria-hidden="true"></span><span><strong>Chọn Nhân viên y tế</strong><small>Đăng nhập bằng tài khoản chuyên môn đã được cấp quyền.</small></span></li><li><span class="guide-icon guide-icon-form" aria-hidden="true"></span><span><strong>Xem hàng đợi cần xử lý</strong><small>Kiểm tra thông tin khai báo và mức độ ưu tiên của từng ca.</small></span></li><li><span class="guide-icon guide-icon-urgent" aria-hidden="true"></span><span><strong>Đánh giá và duyệt phản hồi</strong><small>Chỉ định xử trí phù hợp hoặc điều phối cấp cứu khi cần.</small></span></li></ol></section><div class="help-actions"><button class="primary-button" type="button" data-help-close>Đã hiểu</button></div></section></div>
      <div class="access-layout">
        <div class="access-copy"><p class="eyebrow">Hỗ trợ phân luồng ban đầu</p><h1 id="access-title"><span>Đồng hành cùng</span><span>sức khỏe của</span><span>mọi gia đình</span></h1><p class="access-description">Phân luồng y tế thông minh, kết nối nhanh chóng.</p><div class="care-flow" aria-hidden="true"><svg viewBox="0 0 1000 180" preserveAspectRatio="none"><path class="care-flow-track" pathLength="100" d="M8 92 H36 L48 80 L60 104 L72 92 H96 L108 75 L124 110 L140 92 H168 L180 79 L194 105 L208 92 H238 L252 76 L268 108 L284 92 H306 L320 130 L350 28 L382 152 L416 74 L444 103 H470 L482 78 L496 106 L510 92 H538 L550 75 L566 110 L582 92 H610 L622 80 L636 104 L650 92 H678 L692 76 L708 108 L724 92 H752 L766 79 L780 105 L794 92 H820 L834 74 L850 110 L866 92 H894 L908 78 L922 106 L936 92 H992" /><path class="care-flow-pulse care-flow-pulse-one" pathLength="100" d="M8 92 H36 L48 80 L60 104 L72 92 H96 L108 75 L124 110 L140 92 H168 L180 79 L194 105 L208 92 H238 L252 76 L268 108 L284 92 H306 L320 130 L350 28 L382 152 L416 74 L444 103 H470 L482 78 L496 106 L510 92 H538 L550 75 L566 110 L582 92 H610 L622 80 L636 104 L650 92 H678 L692 76 L708 108 L724 92 H752 L766 79 L780 105 L794 92 H820 L834 74 L850 110 L866 92 H894 L908 78 L922 106 L936 92 H992" /><path class="care-flow-pulse care-flow-pulse-two" pathLength="100" d="M8 92 H36 L48 80 L60 104 L72 92 H96 L108 75 L124 110 L140 92 H168 L180 79 L194 105 L208 92 H238 L252 76 L268 108 L284 92 H306 L320 130 L350 28 L382 152 L416 74 L444 103 H470 L482 78 L496 106 L510 92 H538 L550 75 L566 110 L582 92 H610 L622 80 L636 104 L650 92 H678 L692 76 L708 108 L724 92 H752 L766 79 L780 105 L794 92 H820 L834 74 L850 110 L866 92 H894 L908 78 L922 106 L936 92 H992" /></svg></div><p class="emergency-note"><strong>Trường hợp khẩn cấp:</strong> gọi 115 hoặc đến cơ sở y tế gần nhất.</p></div>
        <section class="role-board" aria-label="Chọn vai trò truy cập">
          <button class="role-card" type="button" data-role="patient"><span class="role-icon role-icon-patient" aria-hidden="true"><i></i></span><span><strong>Bệnh nhân/người nhà bệnh nhân</strong><small>Khai báo triệu chứng, theo dõi ca đang mở và nhận hướng dẫn đã duyệt.</small></span></button>
          <button class="role-card" type="button" data-role="nurse"><span class="role-icon role-icon-clinician" aria-hidden="true"><i></i></span><span><strong>Nhân viên y tế</strong><small>Xem hàng đợi, kiểm tra thông tin lâm sàng và duyệt phản hồi.</small></span></button>
        </section>
        <div class="hero-illustration"><figure class="ai-doctor-visual"><img src="/assets/triage-ai-doctor-looking-left.png" alt="Robot AI mặc áo blouse đang chỉ về bảng chọn vai trò" /></figure></div>
      </div><footer class="landing-contact" aria-label="Thông tin liên hệ"><p>Liên hệ hỗ trợ</p><div class="contact-list"><div><span class="contact-icon contact-icon-email" aria-hidden="true"></span><strong>Email:</strong><a href="mailto:vitriage@gmail.com">vitriage@gmail.com</a></div><div><span class="contact-icon contact-icon-phone" aria-hidden="true">☎</span><strong>Điện thoại:</strong><a href="tel:+84356276505">0356 276 505</a></div><div><span class="contact-icon contact-icon-location" aria-hidden="true"></span><strong>Vị trí:</strong><span>Hà Nội, Việt Nam</span></div></div></footer>
    </section>`;
  root.querySelectorAll("[data-role]").forEach((button) => {
    button.addEventListener("click", () => navigate("auth", { role: button.dataset.role }));
  });
  const helpToggle = root.querySelector("[data-help-toggle]");
  const helpPanel = root.querySelector("[data-help-panel]");
  const closeHelp = () => { helpPanel.hidden = true; helpToggle.setAttribute("aria-expanded", "false"); };
  helpToggle.addEventListener("click", () => { const isOpen = !helpPanel.hidden; helpPanel.hidden = isOpen; helpToggle.setAttribute("aria-expanded", String(!isOpen)); });
  root.querySelectorAll("[data-help-close]").forEach((button) => button.addEventListener("click", closeHelp));
  const setGuideRole = (role) => {
    root.querySelectorAll("[data-guide-role]").forEach((button) => button.setAttribute("aria-selected", String(button.dataset.guideRole === role)));
    root.querySelectorAll("[data-guide-panel]").forEach((panel) => { panel.hidden = panel.dataset.guidePanel !== role; });
  };
  root.querySelectorAll("[data-guide-role]").forEach((button) => button.addEventListener("click", () => setGuideRole(button.dataset.guideRole)));
  root.addEventListener("click", (event) => { if (!event.target.closest(".header-help, .help-modal")) closeHelp(); });
  root.addEventListener("keydown", (event) => { if (event.key === "Escape") closeHelp(); });
}

export function renderAuth(root, { navigate, role, onAuthenticated }) {
  let mode = "login";
  let selectedRole = role;

  const draw = () => {
    const isRegister = mode === "register";
    const roleLabel = selectedRole === "nurse" ? "Nhân viên y tế" : "Bệnh nhân/người nhà";
    root.innerHTML = `
      <section class="auth-shell" aria-labelledby="auth-title">
        <button class="back-button" type="button" data-back>← Về trang chủ</button>
        <div class="auth-card">
          <div class="auth-intro"><a class="brand brand-large" href="/">${logo()}</a><p>Hỗ trợ phân loại mức độ khẩn cấp, có điều dưỡng xác nhận.</p><ul class="auth-trust"><li>Thông tin được bảo mật</li><li>Phản hồi có nhân viên y tế duyệt</li><li>Dấu hiệu cấp cứu được ưu tiên</li></ul><div class="auth-intro-copy"><h1>${isRegister ? "Bắt đầu cùng VMedTriage" : "Chào mừng trở lại"}</h1><p>${isRegister ? "Thông tin của bạn giúp đánh giá triệu chứng chính xác hơn và luôn được bảo mật." : selectedRole === "nurse" ? "Tiếp tục kiểm tra hàng đợi và các ca cần được duyệt." : "Xem lại triệu chứng đã khai báo và hướng dẫn xử trí đã được điều dưỡng duyệt."}</p></div></div>
          <div class="auth-panel">
            <div class="auth-role-banner"><span>${isRegister ? "Đăng ký" : "Đăng nhập"} với vai trò: <strong>${roleLabel}</strong></span><button type="button" data-change-role>Đổi vai trò</button></div>
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
        <div class="legal-dialog" role="dialog" aria-modal="true" aria-labelledby="legal-title" hidden data-legal-panel><button class="legal-backdrop" type="button" aria-label="Đóng nội dung" data-legal-close></button><section class="legal-modal"><div class="legal-modal-heading"><div><p class="eyebrow">VMedTriage</p><h2 id="legal-title">Điều khoản sử dụng</h2></div><button class="legal-close" type="button" aria-label="Đóng nội dung" data-legal-close>×</button></div><div class="legal-content" data-legal-content="terms"><p>VMedTriage hỗ trợ ghi nhận triệu chứng và phân luồng ban đầu; không thay thế chẩn đoán, tư vấn hoặc điều trị trực tiếp từ nhân viên y tế.</p><h3>Sử dụng an toàn</h3><ul><li>Gọi 115 hoặc đến cơ sở y tế gần nhất nếu có dấu hiệu khẩn cấp.</li><li>Cung cấp thông tin trung thực, đầy đủ và bảo mật thông tin đăng nhập của bạn.</li><li>Không sử dụng dịch vụ để thay thế thăm khám hoặc trì hoãn cấp cứu.</li></ul><h3>Trách nhiệm tài khoản</h3><p>Nhân viên y tế chỉ sử dụng tài khoản chuyên môn được cấp quyền và chịu trách nhiệm về phản hồi đã duyệt.</p></div><div class="legal-content" data-legal-content="privacy" hidden><p>Chính sách này tóm tắt cách VMedTriage xử lý dữ liệu bạn cung cấp khi tạo tài khoản và khai báo triệu chứng.</p><h3>Dữ liệu được sử dụng</h3><ul><li>Thông tin liên hệ, hồ sơ tài khoản và nội dung khai báo phục vụ phân luồng ban đầu.</li><li>Dữ liệu được dùng để vận hành dịch vụ, bảo mật tài khoản và gửi mã xác thực email.</li><li>Quyền truy cập được giới hạn theo vai trò người dùng và nhân viên y tế.</li></ul><h3>Quyền của bạn</h3><p>Bạn có thể yêu cầu cập nhật thông tin hồ sơ hoặc liên hệ hỗ trợ qua vitriage@gmail.com khi cần trợ giúp.</p></div><div class="legal-actions"><button class="primary-button" type="button" data-legal-close>Đã hiểu</button></div></section></div>
      </section>`;

    root.querySelector("[data-back]").addEventListener("click", () => navigate("access"));
    root.querySelector("[data-change-role]").addEventListener("click", () => navigate("access"));
    root.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => { mode = button.dataset.mode; draw(); }));
    root.querySelector("[data-forgot]")?.addEventListener("click", () => renderForgotPassword(root, { navigate, back: draw }));
    root.querySelectorAll("[data-password-toggle]").forEach((button) => button.addEventListener("click", () => {
      const input = button.parentElement.querySelector("input");
      const revealed = input.type === "text";
      input.type = revealed ? "password" : "text";
      button.setAttribute("aria-label", revealed ? "Hiện mật khẩu" : "Ẩn mật khẩu");
      button.setAttribute("aria-pressed", String(!revealed));
    }));
    const legalPanel = root.querySelector("[data-legal-panel]");
    const openLegal = (kind) => {
      root.querySelectorAll("[data-legal-content]").forEach((content) => { content.hidden = content.dataset.legalContent !== kind; });
      root.querySelector("#legal-title").textContent = kind === "privacy" ? "Chính sách quyền riêng tư" : "Điều khoản sử dụng";
      legalPanel.hidden = false;
    };
    const closeLegal = () => { legalPanel.hidden = true; };
    root.querySelectorAll("[data-legal-trigger]").forEach((button) => button.addEventListener("click", () => openLegal(button.dataset.legalTrigger)));
    root.querySelectorAll("[data-legal-close]").forEach((button) => button.addEventListener("click", closeLegal));
    root.addEventListener("keydown", (event) => { if (event.key === "Escape") closeLegal(); });
    root.querySelector("#auth-form").addEventListener("submit", (event) => submitAuth(event, { isRegister, selectedRole, navigate, onAuthenticated }));
  };
  draw();
}

function loginFields() {
  return `<label>Email hoặc số điện thoại<input name="email" autocomplete="username" maxlength="320" required placeholder="ten@email.com hoặc 0356 276 505" /></label><label>Mật khẩu${passwordInput({ name: "password", autocomplete: "current-password", placeholder: "Nhập mật khẩu" })}</label><label class="remember-field"><input name="remember_me" type="checkbox" /> Ghi nhớ đăng nhập trên thiết bị này</label>`;
}

function passwordInput({ name, autocomplete, minLength = "", placeholder = "" }) {
  return `<span class="password-field"><input name="${name}" type="password" autocomplete="${autocomplete}"${minLength ? ` minlength="${minLength}"` : ""} maxlength="128" required${placeholder ? ` placeholder="${placeholder}"` : ""} /><button type="button" aria-label="Hiện mật khẩu" aria-pressed="false" data-password-toggle><span class="password-eye" aria-hidden="true"></span></button></span>`;
}

function registrationFields(role) {
  return `<div class="form-grid">
    <label>Họ và tên<input name="full_name" autocomplete="name" minlength="2" maxlength="120" required /></label>
    <label>Số điện thoại<input name="phone_number" type="tel" autocomplete="tel" maxlength="32" required /></label>
  </div>
  <label>Email<input name="email" type="email" autocomplete="email" maxlength="320" required /><small>Dùng để xác thực tài khoản và nhận thông tin quan trọng.</small></label>
  <div class="form-grid"><label>Mật khẩu${passwordInput({ name: "password", autocomplete: "new-password", minLength: 8 })}</label><label>Xác nhận mật khẩu${passwordInput({ name: "confirm_password", autocomplete: "new-password", minLength: 8 })}</label></div><p class="password-requirements"><strong>Mật khẩu cần có:</strong> ít nhất 8 ký tự, gồm chữ hoa, chữ thường, số và ký tự đặc biệt.</p>
  ${role === "nurse" ? `<div class="nurse-fields"><h2>Thông tin xác minh nhân viên y tế</h2><label>Mã đăng ký nội bộ<input name="nurse_registration_code" type="password" maxlength="256" required /></label><div class="form-grid"><label>Giấy phép hoặc chứng chỉ<input name="professional_license" maxlength="160" required /></label><label>Nơi công tác<input name="workplace" maxlength="160" required /></label><label>Khoa hoặc phòng ban<input name="department" maxlength="160" required /></label></div><label>Tiểu sử chuyên môn<textarea name="bio" rows="3" maxlength="2000" required></textarea></label></div>` : ""}
  <label class="checkbox-field"><input name="terms_accepted" type="checkbox" required /><span>Tôi đã đọc và chấp nhận <button class="legal-link" type="button" data-legal-trigger="terms">Điều khoản sử dụng</button> cùng <button class="legal-link" type="button" data-legal-trigger="privacy">Chính sách quyền riêng tư</button>.</span></label>`;
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
    const remember = values.get("remember_me") === "on";
    values.delete("remember_me");
    const session = await api("/api/v1/login", { method: "POST", body: JSON.stringify(Object.fromEntries(values.entries())) });
    saveSession(session.access_token, session.user, { remember });
    await onAuthenticated(session);
  } catch (problem) {
    error.textContent = problem.message || "Không thể hoàn tất xác thực.";
  } finally {
    button.disabled = false;
    button.textContent = isRegister ? "Tạo tài khoản" : "Đăng nhập";
  }
}

export function renderVerification(root, { navigate, email }) {
  root.innerHTML = `<section class="auth-shell"><div class="compact-card"><a class="brand brand-large" href="/">${logo()}</a><p class="eyebrow">Xác thực email</p><h1>Nhập mã xác thực</h1><p>Mã gồm 6 chữ số đã được gửi tới <strong>${escapeHtml(email)}</strong>.</p><form id="verify-form" class="auth-form"><fieldset class="verification-fieldset"><legend>Mã xác thực gồm 6 chữ số</legend><div class="verification-code" role="group" aria-label="Mã xác thực">${Array.from({ length: 6 }, (_, index) => `<input data-code-digit aria-label="Chữ số ${index + 1}" inputmode="numeric" pattern="[0-9]" maxlength="1" autocomplete="${index === 0 ? "one-time-code" : "off"}" />`).join("")}</div></fieldset><p class="form-error" role="alert"></p><button class="primary-button" type="submit">Xác thực email</button><button class="secondary-button" type="button" data-resend>Gửi lại mã</button><button class="link-button center" type="button" data-back>Quay lại đăng nhập</button></form></div></section>`;
  const codeInputs = [...root.querySelectorAll("[data-code-digit]")];
  const insertDigits = (value, startIndex) => {
    const digits = value.replace(/\D/g, "").slice(0, codeInputs.length - startIndex);
    if (!digits) return;
    [...digits].forEach((digit, offset) => { codeInputs[startIndex + offset].value = digit; });
    codeInputs[Math.min(startIndex + digits.length, codeInputs.length - 1)].focus();
  };
  codeInputs.forEach((input, index) => {
    input.addEventListener("input", () => {
      const value = input.value.replace(/\D/g, "");
      if (value.length > 1) { input.value = ""; insertDigits(value, index); return; }
      input.value = value;
      if (value && index < codeInputs.length - 1) codeInputs[index + 1].focus();
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Backspace" && !input.value && index > 0) { event.preventDefault(); codeInputs[index - 1].value = ""; codeInputs[index - 1].focus(); }
      if (event.key === "ArrowLeft" && index > 0) { event.preventDefault(); codeInputs[index - 1].focus(); }
      if (event.key === "ArrowRight" && index < codeInputs.length - 1) { event.preventDefault(); codeInputs[index + 1].focus(); }
    });
    input.addEventListener("paste", (event) => { event.preventDefault(); insertDigits(event.clipboardData.getData("text"), index); });
  });
  codeInputs[0].focus();
  root.querySelector("[data-back]").addEventListener("click", () => navigate("auth"));
  root.querySelector("[data-resend]").addEventListener("click", async () => {
    try { await api("/api/v1/auth/email-verification/resend", { method: "POST", body: JSON.stringify({ email }) }); showToast("Đã gửi lại mã xác thực."); } catch (problem) { showToast(problem.message, true); }
  });
  root.querySelector("#verify-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const error = event.currentTarget.querySelector(".form-error"); error.textContent = "";
    const code = codeInputs.map((input) => input.value).join("");
    if (code.length !== 6) { error.textContent = "Vui lòng nhập đủ 6 chữ số."; return; }
    try { await api("/api/v1/auth/email-verification/confirm", { method: "POST", body: JSON.stringify({ email, code }) }); showToast("Email đã được xác thực. Bạn có thể đăng nhập."); navigate("auth"); } catch (problem) { error.textContent = problem.message; }
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
