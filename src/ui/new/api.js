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
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) return payload.detail.map((item) => item.msg).filter(Boolean).join(" ");
  return payload.message || "";
}
