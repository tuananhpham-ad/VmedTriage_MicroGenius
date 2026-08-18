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

/**
 * Gọi một endpoint SSE và gọi lại `onEvent(tên, dữ liệu)` cho từng sự kiện.
 *
 * Dùng `fetch` + `ReadableStream` chứ KHÔNG dùng `EventSource`: `EventSource` không đặt được header
 * tuỳ ý, mà mọi route ở đây đòi `Authorization: Bearer`. Đổi lại phải tự tách khung SSE - đó là lý
 * do có hàm này thay vì gọi thẳng trong `patient.js`.
 */
export async function apiStream(path, { body, onEvent } = {}) {
  const headers = new Headers({ Accept: "text/event-stream", "Content-Type": "application/json" });
  if (state.accessToken) headers.set("Authorization", `Bearer ${state.accessToken}`);

  let response;
  try {
    response = await fetch(path, { method: "POST", headers, body });
  } catch {
    throw new ApiError("Không thể kết nối tới máy chủ.", 0);
  }
  if (!response.ok || !response.body) {
    if (response.status === 401) clearSession();
    const payload = await response.json().catch(() => null);
    throw new ApiError(readError(payload) || "Yêu cầu không thành công.", response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Sự kiện SSE ngăn cách bằng một dòng trống. Phần dư sau lần tách cuối là khung CHƯA đủ - giữ
    // lại trong buffer, không được parse vội (mẩu tiếng Việt hay bị cắt giữa chừng ký tự).
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = /^event:\s*(.+)$/m.exec(frame)?.[1]?.trim();
      const raw = /^data:\s*([\s\S]*)$/m.exec(frame)?.[1];
      if (!event || raw === undefined) continue;
      let data = null;
      try { data = JSON.parse(raw); } catch { continue; }
      onEvent?.(event, data);
    }
  }
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
