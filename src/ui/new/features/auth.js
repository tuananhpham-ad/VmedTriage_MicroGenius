import { api } from "../api.js";
import { saveSession, state } from "../state.js";
import { escapeHtml, icon, logo, showToast } from "../shared.js";

// TODO(ảnh thật): hai file này đang là ảnh chờ, lấy tạm từ `figures/` của repo. Cần thay bằng ảnh
// chụp thật trước khi lên production — hero: bệnh nhân trò chuyện với trợ lý / nhân viên y tế xem hồ
// sơ; band: nhân viên y tế đang duyệt ca trên hệ thống (xem mục "Assets" của handoff).
const HERO_PHOTO = "/assets/landing-hero.jpg";
const TEAM_PHOTO = "/assets/landing-team.jpg";

/**
 * W-00P — trang giới thiệu công khai, thứ người chưa đăng nhập thấy đầu tiên.
 *
 * Trang chọn vai trò cũ đã được gỡ (2026-08-19): bản thiết kế đưa việc chọn vai trò vào segmented
 * control ngay trên form W-01, nên giữ thêm một màn hình chỉ để chọn vai trò là bắt người dùng
 * quyết định cùng một việc hai lần. Mọi CTA ở đây đều dẫn tới W-01.
 */
export function renderAccess(root, { navigate }) {
  root.innerHTML = `
    <section class="landing-shell">
      <div class="landing">
        <nav class="landing-nav" aria-label="Điều hướng trang giới thiệu">
          <span class="brand">${logo(26)}</span>
          <div class="landing-nav-links">
            <button type="button" data-scroll="how">Cách hoạt động</button>
            <button type="button" data-scroll="about">Về chúng tôi</button>
          </div>
          <button class="secondary-button" type="button" data-login>Đăng nhập</button>
        </nav>

        <div class="landing-hero">
          <svg class="hero-rings" width="620" height="620" viewBox="0 0 620 620" aria-hidden="true" focusable="false"><circle cx="310" cy="310" r="300" fill="none" stroke="#CFE0F3" stroke-width="1"/><circle cx="310" cy="310" r="230" fill="none" stroke="#CFE0F3" stroke-width="1"/><circle cx="310" cy="310" r="160" fill="none" stroke="#CFE0F3" stroke-width="1"/></svg>
          <div class="hero-grid">
            <div class="hero-copy">
              <span class="hero-badge">Có nhân viên y tế xác nhận mọi ca</span>
              <h1>Phân loại mức độ khẩn cấp, an toàn, nhanh chóng</h1>
              <p class="hero-lead">Mô tả triệu chứng bằng lời của bạn. Trợ lý AI thu thập thông tin theo checklist y tế và đề xuất mức độ ưu tiên — nhân viên y tế luôn xem xét và xác nhận trước khi bạn nhận được hướng dẫn xử trí.</p>
              <div class="hero-actions">
                <button class="primary-button" type="button" data-login><span>Bắt đầu khai báo triệu chứng</span>${icon("chevronRight", 18)}</button>
                <button class="secondary-button" type="button" data-scroll="how">Tìm hiểu cách hoạt động</button>
              </div>
              <p class="hero-115">${icon("phone", 16)}<span>Trường hợp khẩn cấp, gọi ngay <b>115</b></span></p>
            </div>
            <div class="hero-figure">
              <img class="hero-photo" src="${HERO_PHOTO}" alt="Bệnh nhân trao đổi triệu chứng với trợ lý VMedTriage" />
              <svg class="hero-beat" width="120" height="46" viewBox="0 0 120 46" aria-hidden="true" focusable="false"><path d="M0 23h20l7-16 10 32 8-22 6 12h69" fill="none" stroke="#1A5EA8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
          </div>
        </div>

        <section class="landing-section" id="how">
          <div class="section-head">
            <p class="eyebrow">Cách hoạt động</p>
            <h2>Ba bước, nhanh chóng, an toàn</h2>
          </div>
          <div class="step-grid">
            <article class="step-card"><span class="step-num">01</span><span class="step-icon">${icon("clipboard", 22)}</span><h3>Khai báo triệu chứng</h3><p>Bạn mô tả bằng lời của mình. Trợ lý AI hỏi thêm theo checklist y tế để hiểu rõ tình trạng.</p></article>
            <article class="step-card"><span class="step-num">02</span><span class="step-icon">${icon("pulse", 22)}</span><h3>AI đề xuất mức ưu tiên</h3><p>Hệ thống chỉ đề xuất mức độ khẩn cấp và hiển thị rõ độ tin cậy — không tự chẩn đoán bệnh.</p></article>
            <article class="step-card"><span class="step-num">03</span><span class="step-icon">${icon("user", 22)}</span><h3>Nhân viên y tế xác nhận</h3><p>Mọi hướng dẫn xử trí chỉ được gửi tới bạn sau khi một nhân viên y tế thật đã xem và duyệt.</p></article>
          </div>
        </section>

        <section class="trust-band" id="about">
          <img class="trust-photo" src="${TEAM_PHOTO}" alt="Nhân viên y tế đang duyệt ca trên hệ thống VMedTriage" />
          <div class="trust-copy">
            <p class="eyebrow">Con người luôn quyết định</p>
            <h2>Công nghệ tiên tiến với các chuyên gia đầu ngành</h2>
            <p><strong>Bạn luôn có một nhân viên y tế đồng hành.</strong> Mỗi ca đều được xem xét và có thể được điều chỉnh hoặc trao đổi thêm để đảm bảo bạn nhận được sự hỗ trợ phù hợp.</p>
            <ul class="trust-list">
              <li>${icon("check", 18)}<span>Đối chiếu hướng dẫn Bộ Y tế Việt Nam và WHO</span></li>
              <li>${icon("check", 18)}<span>Ghi log đầy đủ mọi quyết định để truy vết</span></li>
            </ul>
          </div>
        </section>

        <div class="stat-row">
          <div><div class="stat-value">100%</div><p>Ca được nhân viên y tế xác nhận trước khi gửi</p></div>
          <div><div class="stat-value">&lt;5 phút</div><p>Thời gian trung bình để có hướng dẫn ban đầu</p></div>
          <div><div class="stat-value">24/7</div><p>Trực tiếp nhận và phân loại ca</p></div>
        </div>

        <div class="cta-band">
          <div><h2>Sẵn sàng khai báo triệu chứng?</h2><p>Chỉ mất vài phút, có nhân viên y tế xem xét mọi ca.</p></div>
          <button class="secondary-button" type="button" data-login>Đăng nhập / Đăng ký</button>
        </div>

        <footer class="landing-foot">
          <span>© 2026 VMedTriage</span>
          <span class="disclaimer">Không phải dịch vụ cấp cứu. Trường hợp khẩn cấp, gọi 115.</span>
        </footer>
      </div>
      ${guideDialog()}
    </section>`;

  root.querySelectorAll("[data-login]").forEach((button) => button.addEventListener("click", () => navigate("auth")));
  bindGuideDialog(root);
  // "Cách hoạt động" cuộn tới khối tương ứng trên trang; "Về chúng tôi" cũng vậy. Hộp thoại hướng
  // dẫn theo vai trò (có từ trước) treo vào nút "Tìm hiểu cách hoạt động" của hero.
  root.querySelectorAll("[data-scroll]").forEach((button) =>
    button.addEventListener("click", () => root.querySelector(`#${button.dataset.scroll}`)?.scrollIntoView({ behavior: "smooth", block: "start" })),
  );
  root.querySelector(".hero-actions [data-scroll]").addEventListener("click", () => openGuide(root));
}

// Hộp thoại "Cách thức hoạt động" theo vai trò — giữ nguyên nội dung đã có, chỉ đổi vỏ theo token
// mới. Bản thiết kế không vẽ màn này nhưng cũng không bỏ nội dung của nó đi đâu cả.
function guideDialog() {
  const steps = {
    patient: [
      ["Đăng nhập hoặc đăng ký", "Chọn vai trò Bệnh nhân trên màn hình đăng nhập để bắt đầu khai báo."],
      ["Khai báo triệu chứng", "Trả lời các câu hỏi theo tình trạng thực tế của người bệnh."],
      ["Nhận hướng dẫn xử trí", "Theo dõi phản hồi đã duyệt; gọi 115 ngay nếu có dấu hiệu khẩn cấp."],
    ],
    nurse: [
      ["Đăng nhập tài khoản chuyên môn", "Chọn vai trò Nhân viên y tế bằng tài khoản đã được cấp quyền."],
      ["Xem hàng đợi cần xử lý", "Kiểm tra thông tin khai báo, mức ưu tiên AI đề xuất và độ tin cậy của từng ca."],
      ["Đánh giá và duyệt phản hồi", "Chỉ định xử trí phù hợp hoặc điều phối cấp cứu khi cần."],
    ],
  };
  const panel = (role) =>
    `<ol class="guide-steps" id="guide-${role}" role="tabpanel" aria-labelledby="guide-tab-${role}" data-guide-panel="${role}"${role === "nurse" ? " hidden" : ""}>${steps[role]
      .map(([title, note]) => `<li><span><strong>${title}</strong><small>${note}</small></span></li>`)
      .join("")}</ol>`;
  return `<div class="help-dialog" role="dialog" aria-modal="true" aria-labelledby="usage-guide-title" hidden data-help-panel>
    <button class="help-backdrop" type="button" aria-label="Đóng hướng dẫn" data-help-close></button>
    <section class="help-modal">
      <div class="help-modal-heading"><div><p class="eyebrow">VMedTriage</p><h2 id="usage-guide-title">Cách thức hoạt động</h2></div><button class="help-close" type="button" aria-label="Đóng hướng dẫn" data-help-close>×</button></div>
      <p class="help-intro">Chọn vai trò để xem đúng luồng thao tác của bạn.</p>
      <div class="guide-tabs" role="tablist" aria-label="Vai trò sử dụng"><button type="button" role="tab" aria-selected="true" aria-controls="guide-patient" id="guide-tab-patient" data-guide-role="patient">Bệnh nhân/người nhà</button><button type="button" role="tab" aria-selected="false" aria-controls="guide-nurse" id="guide-tab-nurse" data-guide-role="nurse">Nhân viên y tế</button></div>
      ${panel("patient")}${panel("nurse")}
      <div class="help-actions"><button class="primary-button" type="button" data-help-close>Đã hiểu</button></div>
    </section>
  </div>`;
}

function openGuide(root) {
  root.querySelector("[data-help-panel]").hidden = false;
}

function bindGuideDialog(root) {
  const panel = root.querySelector("[data-help-panel]");
  const close = () => { panel.hidden = true; };
  root.querySelectorAll("[data-help-close]").forEach((button) => button.addEventListener("click", close));
  root.querySelectorAll("[data-guide-role]").forEach((button) =>
    button.addEventListener("click", () => {
      root.querySelectorAll("[data-guide-role]").forEach((tab) => tab.setAttribute("aria-selected", String(tab === button)));
      root.querySelectorAll("[data-guide-panel]").forEach((item) => { item.hidden = item.dataset.guidePanel !== button.dataset.guideRole; });
    }),
  );
  root.addEventListener("keydown", (event) => { if (event.key === "Escape") close(); });
}

/**
 * W-01 — đăng nhập / đăng ký, dùng chung cho cả hai vai trò.
 *
 * Vai trò nay là segmented control TRONG form (bản thiết kế), không còn là màn hình đứng trước.
 * Nút gửi bị khoá (xám đặc, `not-allowed`) tới khi email và mật khẩu đều có nội dung — chính vì thế
 * hai ô đó phải nghe `input` để vẽ lại đúng trạng thái nút.
 */
export function renderAuth(root, { navigate, role, onAuthenticated }) {
  let mode = "login";
  let selectedRole = role === "nurse" ? "nurse" : "patient";
  let showPassword = false;

  const draw = () => {
    const isRegister = mode === "register";
    root.innerHTML = `
      <section class="auth-shell">
        <div class="auth-card">
          <aside class="auth-aside">
            <span class="brand brand-lg">${logo(28)}</span>
            <div>
              <h1>Phân loại ưu tiên khám ban đầu, có nhân viên y tế xác nhận</h1>
              <p>Bệnh nhân mô tả triệu chứng bằng lời. Trợ lý thu thập theo checklist y tế và phát hiện dấu hiệu cần cấp cứu. Quyết định cuối cùng luôn thuộc về con người.</p>
            </div>
            <ul class="auth-trust">
              <li>${icon("check", 18)}<span>Không có hướng dẫn nào được gửi trước khi nhân viên y tế duyệt</span></li>
              <li>${icon("check", 18)}<span>Kết luận đối chiếu hướng dẫn của Bộ Y tế VN và WHO</span></li>
              <li>${icon("check", 18)}<span>Dữ liệu cá nhân được mã hoá và ghi log truy vết</span></li>
            </ul>
          </aside>

          <div class="auth-panel">
            <div class="auth-body">
              <div class="segmented auth-tabs" role="tablist" aria-label="Đăng nhập hoặc đăng ký">
                <button type="button" role="tab" aria-selected="${!isRegister}" class="${!isRegister ? "is-active" : ""}" data-mode="login">Đăng nhập</button>
                <button type="button" role="tab" aria-selected="${isRegister}" class="${isRegister ? "is-active" : ""}" data-mode="register">Đăng ký</button>
              </div>

              <h2>${isRegister ? "Tạo tài khoản mới" : "Chào mừng trở lại"}</h2>
              <p class="auth-note">${isRegister ? "Thông tin của bạn giúp đánh giá triệu chứng chính xác hơn và luôn được bảo mật." : "Đăng nhập để tiếp tục phiên khai báo hoặc xem kết quả đã duyệt."}</p>

              <form id="auth-form" class="auth-form" novalidate>
                <div class="banner is-error" id="auth-error" role="alert" hidden>${icon("alert", 19)}<span class="banner-text"></span></div>
                ${isRegister ? registrationFields(selectedRole) : loginFields(showPassword)}
                ${roleSelector(selectedRole)}
                <button class="primary-button" type="submit" disabled>${isRegister ? "Tạo tài khoản" : "Đăng nhập"}</button>
                <p class="auth-switch">${isRegister ? 'Đã có tài khoản? <button type="button" data-mode="login">Đăng nhập</button>' : 'Chưa có tài khoản? <button type="button" data-mode="register">Đăng ký</button>'}</p>
              </form>
            </div>
          </div>
        </div>
        ${legalDialog()}
      </section>`;

    const form = root.querySelector("#auth-form");
    const submit = form.querySelector("button[type=submit]");
    // Nguồn sự thật DUY NHẤT của trạng thái nút gửi. Trước đây nút luôn bật và lỗi "thiếu thông
    // tin" chỉ hiện sau khi bấm — bản thiết kế đảo lại: nút nói trước rằng chưa gửi được.
    const syncSubmit = () => {
      const email = form.querySelector("[name=email]")?.value.trim();
      const password = form.querySelector("[name=password]")?.value.trim();
      submit.disabled = !email || !password;
    };
    form.querySelectorAll("input").forEach((input) => input.addEventListener("input", syncSubmit));
    syncSubmit();

    root.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => { mode = button.dataset.mode; draw(); }));
    root.querySelectorAll("[data-role]").forEach((button) => button.addEventListener("click", () => { selectedRole = button.dataset.role; draw(); }));
    root.querySelector("[data-back]")?.addEventListener("click", () => navigate("access"));
    root.querySelector("[data-forgot]")?.addEventListener("click", () => renderForgotPassword(root, { navigate, back: draw }));
    root.querySelectorAll("[data-password-toggle]").forEach((button) =>
      button.addEventListener("click", () => {
        const input = button.parentElement.querySelector("input");
        const revealed = input.type === "text";
        input.type = revealed ? "password" : "text";
        button.innerHTML = revealed ? icon("eye", 20) : icon("eyeOff", 20);
        button.setAttribute("aria-label", revealed ? "Hiện mật khẩu" : "Ẩn mật khẩu");
        button.setAttribute("aria-pressed", String(!revealed));
        if (input.name === "password") showPassword = !revealed;
      }),
    );
    bindLegalDialog(root);
    form.addEventListener("submit", (event) => submitAuth(event, { isRegister, selectedRole, navigate, onAuthenticated }));
  };
  draw();
}

function roleSelector(selectedRole) {
  const option = (value, label) => `<button type="button" aria-pressed="${selectedRole === value}" data-role="${value}">${label}</button>`;
  return `<div class="field"><span>Vai trò</span><div class="segmented" role="group" aria-label="Vai trò truy cập">${option("patient", "Bệnh nhân")}${option("nurse", "Nhân viên y tế")}</div></div>`;
}

function loginFields(showPassword) {
  return `<label class="field">Email hoặc số điện thoại<input name="email" autocomplete="username" maxlength="320" required placeholder="ten@email.com" /></label>
  <label class="field">Mật khẩu${passwordInput({ name: "password", autocomplete: "current-password", placeholder: "Nhập mật khẩu", revealed: showPassword })}</label>
  <div class="auth-row">
    <label><input name="remember_me" type="checkbox" /> Ghi nhớ đăng nhập</label>
    <button class="link-button" type="button" data-forgot>Quên mật khẩu?</button>
  </div>`;
}

function passwordInput({ name, autocomplete, minLength = "", placeholder = "", revealed = false }) {
  return `<span class="password-field"><input name="${name}" type="${revealed ? "text" : "password"}" autocomplete="${autocomplete}"${minLength ? ` minlength="${minLength}"` : ""} maxlength="128" required${placeholder ? ` placeholder="${placeholder}"` : ""} /><button type="button" aria-label="${revealed ? "Ẩn" : "Hiện"} mật khẩu" aria-pressed="${revealed}" data-password-toggle>${revealed ? icon("eyeOff", 20) : icon("eye", 20)}</button></span>`;
}

function registrationFields(role) {
  return `<label class="field">Họ và tên<input name="full_name" autocomplete="name" minlength="2" maxlength="120" required placeholder="Nguyễn Văn A" /></label>
  <div class="form-grid">
    <label class="field">Số điện thoại<input name="phone_number" type="tel" autocomplete="tel" maxlength="32" required /></label>
    <label class="field">Email<input name="email" type="email" autocomplete="email" maxlength="320" required /></label>
  </div>
  <div class="form-grid">
    <label class="field">Mật khẩu${passwordInput({ name: "password", autocomplete: "new-password", minLength: 8 })}</label>
    <label class="field">Nhập lại mật khẩu${passwordInput({ name: "confirm_password", autocomplete: "new-password", minLength: 8, placeholder: "Nhập lại mật khẩu" })}</label>
  </div>
  <p class="password-requirements"><strong>Mật khẩu cần có:</strong> ít nhất 8 ký tự, gồm chữ hoa, chữ thường, số và ký tự đặc biệt.</p>
  ${role === "nurse" ? `<div class="nurse-fields"><h3>Thông tin xác minh nhân viên y tế</h3><label class="field">Mã đăng ký nội bộ<input name="nurse_registration_code" type="password" maxlength="256" required /></label><div class="form-grid"><label class="field">Giấy phép hoặc chứng chỉ<input name="professional_license" maxlength="160" required /></label><label class="field">Nơi công tác<input name="workplace" maxlength="160" required /></label></div><div class="form-grid"><label class="field">Khoa hoặc phòng ban<input name="department" maxlength="160" required /></label><label class="field">Tiểu sử chuyên môn<textarea name="bio" rows="3" maxlength="2000" required></textarea></label></div></div>` : ""}
  <label class="checkbox-field"><input name="terms_accepted" type="checkbox" required /><span>Tôi đã đọc và chấp nhận <button class="legal-link" type="button" data-legal-trigger="terms">Điều khoản sử dụng</button> cùng <button class="legal-link" type="button" data-legal-trigger="privacy">Chính sách quyền riêng tư</button>.</span></label>`;
}

function showAuthError(form, message) {
  const banner = form.querySelector("#auth-error");
  banner.querySelector(".banner-text").textContent = message;
  banner.hidden = !message;
}

async function submitAuth(event, { isRegister, selectedRole, navigate, onAuthenticated }) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  showAuthError(form, "");
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
    showAuthError(form, problem.message || "Email hoặc mật khẩu không đúng");
  } finally {
    button.disabled = false;
    button.textContent = isRegister ? "Tạo tài khoản" : "Đăng nhập";
  }
}

function legalDialog() {
  return `<div class="legal-dialog" role="dialog" aria-modal="true" aria-labelledby="legal-title" hidden data-legal-panel>
    <button class="legal-backdrop" type="button" aria-label="Đóng nội dung" data-legal-close></button>
    <section class="legal-modal">
      <div class="legal-modal-heading"><div><p class="eyebrow">VMedTriage</p><h2 id="legal-title">Điều khoản sử dụng</h2></div><button class="legal-close" type="button" aria-label="Đóng nội dung" data-legal-close>×</button></div>
      <div class="legal-content" data-legal-content="terms"><p>VMedTriage hỗ trợ ghi nhận triệu chứng và phân luồng ban đầu; không thay thế chẩn đoán, tư vấn hoặc điều trị trực tiếp từ nhân viên y tế.</p><h3>Sử dụng an toàn</h3><ul><li>Gọi 115 hoặc đến cơ sở y tế gần nhất nếu có dấu hiệu khẩn cấp.</li><li>Cung cấp thông tin trung thực, đầy đủ và bảo mật thông tin đăng nhập của bạn.</li><li>Không sử dụng dịch vụ để thay thế thăm khám hoặc trì hoãn cấp cứu.</li></ul><h3>Trách nhiệm tài khoản</h3><p>Nhân viên y tế chỉ sử dụng tài khoản chuyên môn được cấp quyền và chịu trách nhiệm về phản hồi đã duyệt.</p></div>
      <div class="legal-content" data-legal-content="privacy" hidden><p>Chính sách này tóm tắt cách VMedTriage xử lý dữ liệu bạn cung cấp khi tạo tài khoản và khai báo triệu chứng.</p><h3>Dữ liệu được sử dụng</h3><ul><li>Thông tin liên hệ, hồ sơ tài khoản và nội dung khai báo phục vụ phân luồng ban đầu.</li><li>Dữ liệu được dùng để vận hành dịch vụ, bảo mật tài khoản và gửi mã xác thực email.</li><li>Quyền truy cập được giới hạn theo vai trò người dùng và nhân viên y tế.</li></ul><h3>Quyền của bạn</h3><p>Bạn có thể yêu cầu cập nhật thông tin hồ sơ hoặc liên hệ hỗ trợ qua vitriage@gmail.com khi cần trợ giúp.</p></div>
      <div class="legal-actions"><button class="primary-button" type="button" data-legal-close>Đã hiểu</button></div>
    </section>
  </div>`;
}

function bindLegalDialog(root) {
  const panel = root.querySelector("[data-legal-panel]");
  if (!panel) return;
  const close = () => { panel.hidden = true; };
  root.querySelectorAll("[data-legal-trigger]").forEach((button) =>
    button.addEventListener("click", () => {
      const kind = button.dataset.legalTrigger;
      root.querySelectorAll("[data-legal-content]").forEach((content) => { content.hidden = content.dataset.legalContent !== kind; });
      root.querySelector("#legal-title").textContent = kind === "privacy" ? "Chính sách quyền riêng tư" : "Điều khoản sử dụng";
      panel.hidden = false;
    }),
  );
  root.querySelectorAll("[data-legal-close]").forEach((button) => button.addEventListener("click", close));
  root.addEventListener("keydown", (event) => { if (event.key === "Escape") close(); });
}

export function renderVerification(root, { navigate, email }) {
  root.innerHTML = `<section class="auth-shell"><div class="compact-card"><span class="brand brand-lg">${logo(28)}</span><p class="eyebrow">Xác thực email</p><h1>Nhập mã xác thực</h1><p>Mã gồm 6 chữ số đã được gửi tới <strong>${escapeHtml(email)}</strong>.</p><form id="verify-form" class="auth-form"><fieldset class="verification-fieldset"><legend>Mã xác thực gồm 6 chữ số</legend><div class="verification-code" role="group" aria-label="Mã xác thực">${Array.from({ length: 6 }, (_, index) => `<input data-code-digit aria-label="Chữ số ${index + 1}" inputmode="numeric" pattern="[0-9]" maxlength="1" autocomplete="${index === 0 ? "one-time-code" : "off"}" />`).join("")}</div></fieldset><p class="form-error" role="alert"></p><button class="primary-button" type="submit">Xác thực email</button><button class="secondary-button" type="button" data-resend>Gửi lại mã</button><button class="link-button center" type="button" data-back>Quay lại đăng nhập</button></form></div></section>`;
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
  root.innerHTML = `<section class="auth-shell"><div class="compact-card"><span class="brand brand-lg">${logo(28)}</span><p class="eyebrow">Khôi phục tài khoản</p><h1>Đặt lại mật khẩu</h1><p>Nhập email để nhận liên kết đặt lại mật khẩu.</p><form id="forgot-form" class="auth-form"><label class="field">Email<input name="email" type="email" autocomplete="email" required /></label><p class="form-error" role="alert"></p><button class="primary-button" type="submit">Gửi liên kết</button><button class="link-button center" type="button" data-back>Quay lại</button></form></div></section>`;
  root.querySelector("[data-back]").addEventListener("click", back);
  root.querySelector("#forgot-form").addEventListener("submit", async (event) => { event.preventDefault(); const error = event.currentTarget.querySelector(".form-error"); try { const result = await api("/api/v1/auth/password-reset/request", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) }); showToast(result.message); navigate("auth"); } catch (problem) { error.textContent = problem.message; } });
}

export function renderPasswordReset(root, { navigate, token }) {
  root.innerHTML = `<section class="auth-shell"><div class="compact-card"><span class="brand brand-lg">${logo(28)}</span><p class="eyebrow">Khôi phục tài khoản</p><h1>Tạo mật khẩu mới</h1><form id="reset-form" class="auth-form"><label class="field">Mật khẩu mới<input name="new_password" type="password" autocomplete="new-password" minlength="8" required /></label><label class="field">Xác nhận mật khẩu mới<input name="confirm_new_password" type="password" autocomplete="new-password" minlength="8" required /></label><p class="form-error" role="alert"></p><button class="primary-button" type="submit">Lưu mật khẩu mới</button></form></div></section>`;
  root.querySelector("#reset-form").addEventListener("submit", async (event) => { event.preventDefault(); const error = event.currentTarget.querySelector(".form-error"); try { const values = Object.fromEntries(new FormData(event.currentTarget)); await api("/api/v1/auth/password-reset/confirm", { method: "POST", body: JSON.stringify({ token, ...values }) }); showToast("Đã đặt lại mật khẩu. Bạn có thể đăng nhập."); history.replaceState({}, "", "/"); navigate("auth"); } catch (problem) { error.textContent = problem.message; } });
}
