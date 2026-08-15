import { api } from "../api.js";
import { state } from "../state.js";
import { escapeHtml, showToast } from "../shared.js";

export function accountMenu() {
  applyDisplaySettings(readSettings());
  const name = state.user?.full_name || "Tài khoản";
  const role = state.user?.role === "nurse" ? "Nhân viên y tế" : "Bệnh nhân";
  return `<div class="account-menu"><button class="account-avatar" type="button" data-account-toggle aria-expanded="false" aria-label="Mở menu tài khoản">${initials(name)}</button><div class="account-dropdown" data-account-dropdown hidden><div class="account-summary"><span class="account-summary-avatar" aria-hidden="true">${initials(name)}</span><div><div class="account-summary-name"><strong>${escapeHtml(name)}</strong><span class="role-badge">${role}</span></div><span>${escapeHtml(state.user?.email || "")}</span></div></div><div class="account-links"><button type="button" data-open-profile><span class="account-item-icon account-icon-profile" aria-hidden="true"></span>Hồ sơ</button><button type="button" data-account-info="settings"><span class="account-item-icon account-icon-settings" aria-hidden="true"></span>Cài đặt</button><button type="button" data-account-info="privacy"><span class="account-item-icon account-icon-privacy" aria-hidden="true"></span>Chính sách quyền riêng tư</button><button type="button" data-account-info="help"><span class="account-item-icon account-icon-help" aria-hidden="true"></span>Trợ giúp &amp; liên hệ</button></div><div class="account-logout"><button type="button" data-account-logout><span class="account-item-icon account-icon-logout" aria-hidden="true"></span>Đăng xuất</button></div></div></div>`;
}

export function bindAccountMenu(root, { logout, onProfileSaved }) {
  const toggle = root.querySelector("[data-account-toggle]");
  const dropdown = root.querySelector("[data-account-dropdown]");
  if (!toggle || !dropdown) return;
  toggle.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = dropdown.hidden;
    dropdown.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("click", (event) => {
    if (!root.contains(event.target)) return;
    if (!event.target.closest(".account-menu")) {
      dropdown.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
    }
  });
  root.querySelector("[data-open-profile]").addEventListener("click", () => openProfile(onProfileSaved));
  root.querySelectorAll("[data-account-info]").forEach((button) => button.addEventListener("click", () => openAccountInfo(button.dataset.accountInfo)));
  root.querySelector("[data-account-logout]").addEventListener("click", logout);
}

function openAccountInfo(kind) {
  if (kind === "settings") {
    openSettings();
    return;
  }
  const content = {
    privacy: { title: "Chính sách quyền riêng tư", text: "VMedTriage sử dụng thông tin tài khoản và nội dung khai báo để vận hành dịch vụ, bảo mật tài khoản và hỗ trợ phân luồng ban đầu. Quyền truy cập dữ liệu được giới hạn theo vai trò." },
    help: { title: "Trợ giúp & liên hệ", text: "Cần hỗ trợ? Liên hệ vitriage@gmail.com hoặc 0356 276 505. Chúng tôi hoạt động tại Hà Nội, Việt Nam." },
  }[kind];
  const dialog = document.createElement("div");
  dialog.className = "account-info-dialog";
  dialog.innerHTML = `<button class="profile-backdrop" type="button" aria-label="Đóng" data-close-info></button><section class="account-info-card" role="dialog" aria-modal="true" aria-labelledby="account-info-title"><button class="profile-close" type="button" aria-label="Đóng" data-close-info>×</button><p class="eyebrow">VMedTriage</p><h2 id="account-info-title">${content.title}</h2><p>${content.text}</p><button class="primary-button" type="button" data-close-info>Đã hiểu</button></section>`;
  document.body.append(dialog);
  dialog.querySelectorAll("[data-close-info]").forEach((button) => button.addEventListener("click", () => dialog.remove()));
}

function openSettings() {
  const preferences = readSettings();
  const dialog = document.createElement("div");
  dialog.className = "settings-dialog";
  dialog.innerHTML = `<button class="profile-backdrop" type="button" aria-label="Đóng" data-close-settings></button><section class="settings-card" role="dialog" aria-modal="true" aria-labelledby="settings-title"><button class="profile-close" type="button" aria-label="Đóng" data-close-settings>×</button><p class="eyebrow">Tài khoản của bạn</p><h2 id="settings-title">Cài đặt</h2><p class="settings-intro">Điều chỉnh thông báo, bảo mật, dữ liệu và cách hiển thị theo nhu cầu của bạn.</p><section class="settings-group"><h3>Thông báo</h3><label class="setting-row"><span class="setting-copy"><strong>Thông báo khi kết quả được duyệt</strong><small>Nhận email khi điều dưỡng đã duyệt phản hồi cho ca của bạn.</small></span><input class="setting-switch" type="checkbox" name="email_notifications" ${preferences.email_notifications ? "checked" : ""} /></label><label class="setting-row"><span class="setting-copy"><strong>Nhắc khi ca đang mở chờ quá lâu</strong><small>Giúp bạn theo dõi tiến trình và chủ động xem lại ca đang mở.</small></span><input class="setting-switch" type="checkbox" name="case_reminders" ${preferences.case_reminders ? "checked" : ""} /></label></section><section class="settings-group"><h3>Bảo mật</h3><div class="setting-row setting-row-action"><span class="setting-copy"><strong>Đổi mật khẩu</strong><small>Gửi liên kết đặt lại mật khẩu đến email đã xác thực.</small></span><button class="secondary-button" type="button" data-change-password>Gửi liên kết</button></div><div class="setting-row setting-row-action"><span class="setting-copy"><strong>Đổi email</strong><small>Yêu cầu xác minh bằng email hiện tại trước khi thay đổi địa chỉ liên hệ.</small></span><a class="link-button" href="mailto:vitriage@gmail.com?subject=Y%C3%AAu%20c%E1%BA%A7u%20%C4%91%E1%BB%95i%20email%20VMedTriage">Yêu cầu đổi</a></div><div class="setting-row"><span class="setting-copy"><strong>Quản lý phiên đăng nhập</strong><small>Đăng xuất các thiết bị khác để bảo vệ tài khoản dùng chung trong gia đình.</small></span><span class="setting-note">Sắp có</span></div></section><section class="settings-group"><h3>Dữ liệu &amp; quyền riêng tư</h3><div class="setting-row setting-row-action"><span class="setting-copy"><strong>Xem hoặc tải xuống dữ liệu cá nhân</strong><small>Tải bản sao hồ sơ và lịch sử khai báo thuộc tài khoản của bạn.</small></span><button class="link-button" type="button" data-download-data>Tải xuống</button></div><div class="setting-row setting-row-action"><span class="setting-copy"><strong>Yêu cầu xoá tài khoản &amp; dữ liệu</strong><small>Gửi yêu cầu để đội ngũ hỗ trợ xác minh và xử lý an toàn.</small></span><a class="link-button danger-link" href="mailto:vitriage@gmail.com?subject=Y%C3%AAu%20c%E1%BA%A7u%20xo%C3%A1%20t%C3%A0i%20kho%E1%BA%A3n%20VMedTriage">Gửi yêu cầu</a></div><div class="setting-row"><span class="setting-copy"><strong>Lịch sử truy cập hồ sơ</strong><small>Xem các lượt truy cập hồ sơ, bao gồm nhân viên y tế đã xem khi có nhật ký truy cập.</small></span><span class="setting-note">Đang hoàn thiện</span></div><div class="setting-row setting-row-action"><span class="setting-copy"><strong>Chính sách quyền riêng tư</strong><small>Xem cách VMedTriage sử dụng và bảo vệ dữ liệu của bạn.</small></span><button class="link-button" type="button" data-open-privacy>Xem</button></div></section><section class="settings-group"><h3>Khác</h3><label class="setting-row"><span class="setting-copy"><strong>Cỡ chữ dễ đọc hơn</strong><small>Tăng nhẹ cỡ chữ trên thiết bị này.</small></span><input class="setting-switch" type="checkbox" name="large_text" ${preferences.large_text ? "checked" : ""} /></label><label class="setting-row"><span class="setting-copy"><strong>Độ tương phản cao</strong><small>Làm rõ chữ và đường viền để dễ theo dõi.</small></span><input class="setting-switch" type="checkbox" name="high_contrast" ${preferences.high_contrast ? "checked" : ""} /></label></section><div class="settings-actions"><button class="primary-button" type="button" data-close-settings>Đã hiểu</button></div></section>`;
  document.body.append(dialog);

  const persist = () => {
    const next = {
      email_notifications: dialog.querySelector("[name=email_notifications]").checked,
      case_reminders: dialog.querySelector("[name=case_reminders]").checked,
      large_text: dialog.querySelector("[name=large_text]").checked,
      high_contrast: dialog.querySelector("[name=high_contrast]").checked,
    };
    localStorage.setItem("vmed_settings", JSON.stringify(next));
    applyDisplaySettings(next);
  };
  dialog.querySelectorAll(".setting-switch").forEach((control) => control.addEventListener("change", persist));
  const close = () => dialog.remove();
  dialog.querySelectorAll("[data-close-settings]").forEach((button) => button.addEventListener("click", close));
  dialog.querySelector("[data-open-privacy]").addEventListener("click", () => {
    close();
    openAccountInfo("privacy");
  });
  dialog.querySelector("[data-download-data]").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "Đang tạo";
    try {
      const [profile, history] = await Promise.all([api("/api/v1/me"), api("/api/v1/patient/history")]);
      const exportFile = new Blob([JSON.stringify({ exported_at: new Date().toISOString(), profile, triage_history: history }, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(exportFile);
      const link = document.createElement("a");
      link.href = url;
      link.download = "vmedtriage-du-lieu-ca-nhan.json";
      link.click();
      URL.revokeObjectURL(url);
      showToast("Đã tải xuống dữ liệu cá nhân.");
    } catch (problem) {
      showToast(problem.message || "Không thể tạo tệp dữ liệu.", true);
    } finally {
      button.disabled = false;
      button.textContent = "Tải xuống";
    }
  });
  dialog.querySelector("[data-change-password]").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "Đang gửi";
    try {
      const result = await api("/api/v1/auth/password-reset/request", { method: "POST", body: JSON.stringify({ email: state.user?.email }) });
      showToast(result.message || "Đã gửi liên kết đặt lại mật khẩu.");
    } catch (problem) {
      showToast(problem.message || "Không thể gửi liên kết đặt lại mật khẩu.", true);
    } finally {
      button.disabled = false;
      button.textContent = "Gửi liên kết";
    }
  });
}

function readSettings() {
  try {
    return { email_notifications: true, case_reminders: true, large_text: false, high_contrast: false, ...JSON.parse(localStorage.getItem("vmed_settings") || "{}") };
  } catch {
    return { email_notifications: true, case_reminders: true, large_text: false, high_contrast: false };
  }
}

function applyDisplaySettings(preferences) {
  document.body.classList.toggle("is-large-text", Boolean(preferences.large_text));
  document.body.classList.toggle("is-high-contrast", Boolean(preferences.high_contrast));
}

function openProfile(onProfileSaved) {
  const user = state.user || {};
  const dialog = document.createElement("div");
  dialog.className = "profile-dialog";
  dialog.innerHTML = `<div class="profile-backdrop" data-close-profile></div><section class="profile-card" role="dialog" aria-modal="true" aria-labelledby="profile-title"><button class="profile-close" type="button" data-close-profile aria-label="Đóng">×</button><p class="eyebrow">Hồ sơ cá nhân</p><h2 id="profile-title">Bổ sung hoặc chỉnh sửa hồ sơ</h2><p>Thông tin này giúp hệ thống và nhân viên y tế hiểu bối cảnh của bạn tốt hơn.</p><form class="profile-form" id="profile-form"><section class="profile-section"><h3>Thông tin cá nhân</h3><label>Họ và tên<input name="full_name" minlength="2" maxlength="120" autocomplete="name" value="${escapeHtml(user.full_name || "")}" required /></label><div class="form-grid"><label>Số điện thoại<input name="phone_number" minlength="9" maxlength="32" autocomplete="tel" value="${escapeHtml(user.phone_number || "")}" required /></label><label>Email<input value="${escapeHtml(user.email || "")}" readonly aria-readonly="true" /><small>Email đã xác thực không thể đổi tại đây.</small></label></div><div class="form-grid"><label>Ngày sinh<input name="date_of_birth" class="date-input" type="text" inputmode="numeric" autocomplete="bday" placeholder="DD/MM/YYYY" pattern="\\d{2}/\\d{2}/\\d{4}" value="${formatBirthDate(user.date_of_birth)}" required /><small>DD/MM/YYYY</small></label><label>Giới tính<select name="gender" required><option value="prefer_not_to_say">Không muốn nêu</option><option value="male">Nam</option><option value="female">Nữ</option><option value="other">Khác</option></select></label></div><div class="form-grid"><label>Tỉnh/thành phố<input name="province_city" maxlength="120" autocomplete="address-level1" value="${escapeHtml(user.province_city || "")}" /></label><label>Quận/huyện<input name="district" maxlength="120" autocomplete="address-level2" value="${escapeHtml(user.district || "")}" /></label></div></section><section class="profile-section profile-health-section"><h3>Thông tin cần lưu ý</h3><p>Không bắt buộc. Thông tin giúp phân luồng an toàn hơn.</p><label>Đang dùng thuốc chống đông máu hoặc ức chế miễn dịch<select name="high_risk_medication_status"><option value="">Chưa cập nhật</option><option value="yes">Có</option><option value="no">Không</option><option value="unknown">Không rõ</option></select></label><label>Tiền sử dị ứng nặng hoặc sốc phản vệ<select name="severe_allergy_status"><option value="">Chưa cập nhật</option><option value="yes">Có</option><option value="no">Không</option><option value="unknown">Không rõ</option></select></label><label>Phẫu thuật hoặc nhập viện gần đây <span>(không bắt buộc)</span><textarea name="recent_surgery_or_hospitalization" rows="3" maxlength="1000" placeholder="Ví dụ: nhập viện tháng trước do...">${escapeHtml(user.recent_surgery_or_hospitalization || "")}</textarea></label></section><section class="profile-section"><h3>Liên hệ khẩn cấp</h3><p>Cần khi hệ thống phát hiện dấu hiệu nguy hiểm.</p><label>Họ và tên người liên hệ<input name="emergency_contact_name" maxlength="120" autocomplete="name" value="${escapeHtml(user.emergency_contact_name || "")}" /></label><div class="form-grid"><label>Mối quan hệ<input name="emergency_contact_relationship" maxlength="80" placeholder="Ví dụ: Vợ, chồng, con" value="${escapeHtml(user.emergency_contact_relationship || "")}" /></label><label>Số điện thoại<input name="emergency_contact_phone" maxlength="32" autocomplete="tel" value="${escapeHtml(user.emergency_contact_phone || "")}" /></label></div></section><p class="form-error" role="alert"></p><button class="primary-button" type="submit">Lưu thay đổi</button></form></section>`;
  document.body.append(dialog);
  dialog.querySelector(".eyebrow").textContent = "Hồ sơ của bạn";
  dialog.querySelector("#profile-title").textContent = "Thông tin cá nhân & sức khỏe";
  dialog.querySelector("#profile-title + p").textContent = "Giúp VMedTriage hiểu rõ hơn về bạn để hỗ trợ tư vấn y tế kịp thời.";
  dialog.querySelector("button[type=submit]").textContent = "Lưu thông tin";
  dialog.querySelector(".profile-health-section")?.remove();
  const locationFields = dialog.querySelector('input[name="province_city"]')?.closest(".form-grid");
  if (locationFields) locationFields.outerHTML = `<label><span class="field-label">Nơi ở hiện tại <em>(không bắt buộc)</em></span><input name="address" maxlength="240" autocomplete="street-address" placeholder="Ví dụ: Cầu Giấy, Hà Nội" value="${escapeHtml(user.address || "")}" /></label>`;
  const gender = dialog.querySelector("select[name=gender]");
  gender.value = user.gender || "prefer_not_to_say";
  const close = () => dialog.remove();
  dialog.querySelectorAll("[data-close-profile]").forEach((button) => button.addEventListener("click", close));
  dialog.querySelector("#profile-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const error = form.querySelector(".form-error");
    const submit = form.querySelector("button[type=submit]");
    error.textContent = "";
    submit.disabled = true;
    submit.textContent = "Đang lưu";
    try {
      const payload = Object.fromEntries(new FormData(form).entries());
      delete payload.email;
      payload.date_of_birth = toIsoBirthDate(payload.date_of_birth);
      const updated = await api("/api/v1/me", { method: "PUT", body: JSON.stringify(payload) });
      state.user = updated;
      sessionStorage.setItem("vmed_user", JSON.stringify(updated));
      close();
      showToast("Đã lưu hồ sơ.");
      onProfileSaved?.();
    } catch (problem) {
      error.textContent = problem.message || "Không thể lưu hồ sơ.";
    } finally {
      submit.disabled = false;
      submit.textContent = "Lưu thông tin";
    }
  });
  dialog.querySelector("input[name=full_name]").focus();
}

function formatBirthDate(value) {
  const [year, month, day] = String(value || "").split("-");
  return year && month && day ? `${day}/${month}/${year}` : "";
}

function toIsoBirthDate(value) {
  const match = String(value || "").trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) throw new Error("Ngày sinh cần có định dạng dd/mm/yyyy.");
  const [, day, month, year] = match;
  const parsed = new Date(`${year}-${month}-${day}T00:00:00Z`);
  if (
    Number.isNaN(parsed.valueOf()) ||
    parsed.getUTCFullYear() !== Number(year) ||
    parsed.getUTCMonth() + 1 !== Number(month) ||
    parsed.getUTCDate() !== Number(day)
  ) {
    throw new Error("Ngày sinh không hợp lệ.");
  }
  return `${year}-${month}-${day}`;
}

function initials(name) {
  const parts = String(name).trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "VT";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts.at(-1)[0]}`.toUpperCase();
}
