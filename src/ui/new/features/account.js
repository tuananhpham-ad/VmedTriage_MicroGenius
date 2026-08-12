import { api } from "../api.js";
import { state } from "../state.js";
import { escapeHtml, showToast } from "../shared.js";

export function accountMenu() {
  const name = state.user?.full_name || "Tài khoản";
  return `<div class="account-menu"><button class="account-avatar" type="button" data-account-toggle aria-expanded="false" aria-label="Mở menu tài khoản">${initials(name)}</button><div class="account-dropdown" data-account-dropdown hidden><div class="account-summary"><strong>${escapeHtml(name)}</strong><span>${escapeHtml(state.user?.email || "")}</span></div><button type="button" data-open-profile>Hồ sơ</button><button type="button" data-account-logout>Đăng xuất</button></div></div>`;
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
  root.querySelector("[data-account-logout]").addEventListener("click", logout);
}

function openProfile(onProfileSaved) {
  const user = state.user || {};
  const dialog = document.createElement("div");
  dialog.className = "profile-dialog";
  dialog.innerHTML = `<div class="profile-backdrop" data-close-profile></div><section class="profile-card" role="dialog" aria-modal="true" aria-labelledby="profile-title"><button class="profile-close" type="button" data-close-profile aria-label="Đóng">×</button><p class="eyebrow">Hồ sơ cá nhân</p><h2 id="profile-title">Bổ sung hoặc chỉnh sửa hồ sơ</h2><p>Thông tin này giúp hệ thống và nhân viên y tế hiểu bối cảnh của bạn tốt hơn.</p><form class="profile-form" id="profile-form"><label>Họ và tên<input name="full_name" minlength="2" maxlength="120" autocomplete="name" value="${escapeHtml(user.full_name || "")}" required /></label><label>Số điện thoại<input name="phone_number" minlength="9" maxlength="32" autocomplete="tel" value="${escapeHtml(user.phone_number || "")}" required /></label><div class="form-grid"><label>Ngày sinh<input name="date_of_birth" class="date-input" type="text" inputmode="numeric" autocomplete="bday" placeholder="dd/mm/yyyy" pattern="\\d{2}/\\d{2}/\\d{4}" value="${formatBirthDate(user.date_of_birth)}" required /><small>Nhập theo định dạng ngày/tháng/năm.</small></label><label>Giới tính<select name="gender" required><option value="prefer_not_to_say">Không muốn nêu</option><option value="male">Nam</option><option value="female">Nữ</option><option value="other">Khác</option></select></label></div><p class="form-error" role="alert"></p><button class="primary-button" type="submit">Lưu thay đổi</button></form></section>`;
  document.body.append(dialog);
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
      submit.textContent = "Lưu thay đổi";
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
