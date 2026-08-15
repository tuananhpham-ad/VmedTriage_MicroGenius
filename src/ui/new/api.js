import { clearSession, state } from "./state.js";

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (state.accessToken) headers.set("Authorization", `Bearer ${state.accessToken}`);

  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch {
    throw new ApiError("Không thể kết nối tới máy chủ.", 0);
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) clearSession();
    throw new ApiError(readError(payload) || "Yêu cầu không thành công.", response.status);
  }
  return payload;
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export function readError(payload) {
  if (!payload) return "";
  if (typeof payload.detail === "string") return friendlyMessage(payload.detail);
  if (Array.isArray(payload.detail)) {
    const messages = [...new Set(payload.detail.map((item) => friendlyMessage(item.msg, item.loc)).filter(Boolean))];
    return messages.length > 1 ? "Vui lòng kiểm tra và điền đầy đủ các thông tin bắt buộc." : (messages[0] || "");
  }
  return friendlyMessage(payload.message || "");
}

function friendlyMessage(message, location = []) {
  const clean = String(message).replace(/^value error,\s*/i, "");
  if (/^string should have at least 1 character$/i.test(clean)) return "Vui lòng điền đầy đủ thông tin bắt buộc.";
  if (/^value is not a valid email address/i.test(clean)) return "Vui lòng nhập địa chỉ email hợp lệ.";
  const minimumLength = clean.match(/^string should have at least (\d+) characters?$/i);
  if (minimumLength) {
    const field = Array.isArray(location) ? location.at(-1) : "";
    const labels = { full_name: "Họ và tên", phone_number: "Số điện thoại", password: "Mật khẩu", confirm_password: "Xác nhận mật khẩu" };
    const label = labels[field] || "Thông tin này";
    return `${label} cần có ít nhất ${minimumLength[1]} ký tự.`;
  }
  return clean;
}
