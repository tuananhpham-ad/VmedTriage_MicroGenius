/* Demo intake conversation - VMedTriage Feature #1 (thu thap trieu chung).
   Chi phuc vu demo: khong auth, khong day case sang dieu duong. */

const API = "/api/v1/intake";

const el = {
  mode: document.getElementById("mode"),
  disclaimer: document.getElementById("disclaimer"),
  redflag: document.getElementById("redflag"),
  redflagList: document.getElementById("redflagList"),
  chat: document.getElementById("chat"),
  composer: document.getElementById("composer"),
  input: document.getElementById("input"),
  send: document.getElementById("send"),
  pctText: document.getElementById("pctText"),
  pctSub: document.getElementById("pctSub"),
  barFill: document.getElementById("barFill"),
  fieldList: document.getElementById("fieldList"),
  summaryCard: document.getElementById("summaryCard"),
  summaryTable: document.getElementById("summaryTable"),
  confirmActions: document.getElementById("confirmActions"),
  btnYes: document.getElementById("btnYes"),
  btnNo: document.getElementById("btnNo"),
  correctionBox: document.getElementById("correctionBox"),
  correctionForm: document.getElementById("correctionForm"),
  correctionInput: document.getElementById("correctionInput"),
  doneMsg: document.getElementById("doneMsg"),
  llmProvider: document.getElementById("llmProvider"),
  llmModel: document.getElementById("llmModel"),
  llmModelList: document.getElementById("llmModelList"),
  llmKey: document.getElementById("llmKey"),
  toggleKey: document.getElementById("toggleKey"),
  testLlm: document.getElementById("testLlm"),
  applyLlm: document.getElementById("applyLlm"),
  clearLlm: document.getElementById("clearLlm"),
  llmStatus: document.getElementById("llmStatus"),
};

let sessionId = null;
let renderedTurns = 0;
let providerCatalog = [];

/* API key nguoi test tu nhap. Dung sessionStorage (mat khi dong tab), KHONG dung localStorage
   de key khong nam lai lau dai tren may dung chung. */
const KEY_STORE = "vmed_llm_credential";

function loadCredential() {
  try {
    return JSON.parse(sessionStorage.getItem(KEY_STORE) || "null");
  } catch {
    return null;
  }
}

function saveCredential(credential) {
  if (credential) sessionStorage.setItem(KEY_STORE, JSON.stringify(credential));
  else sessionStorage.removeItem(KEY_STORE);
}

function setLlmStatus(text, kind) {
  el.llmStatus.textContent = text;
  el.llmStatus.className = kind;
}

async function api(path, options) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Lỗi ${response.status}`);
  return body;
}

function addBubble(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  el.chat.appendChild(div);
  el.chat.scrollTop = el.chat.scrollHeight;
}

function renderConversation(conversation) {
  // Chi ve phan moi de khong nhap nhay va khong mat vi tri scroll.
  for (let i = renderedTurns; i < conversation.length; i += 1) {
    const turn = conversation[i];
    addBubble(turn.role === "user" ? "user" : "bot", turn.content);
  }
  renderedTurns = conversation.length;
}

function renderProgress(progress, summaryRows) {
  el.pctText.textContent = `${progress.percent}%`;
  el.pctSub.textContent = `${progress.filled_required}/${progress.total_required} trường bắt buộc`;
  el.barFill.style.width = `${progress.percent}%`;

  // Truoc khi co summary, backend khong tra summary_rows -> hien danh sach truong con thieu.
  el.fieldList.innerHTML = "";
  if (summaryRows && summaryRows.length) {
    summaryRows.forEach((row) => appendFieldRow(row.label, row.value, !row.is_missing));
  } else {
    progress.missing_required_labels.forEach((label) => appendFieldRow(label, "chưa có", false));
  }
}

function appendFieldRow(label, value, filled) {
  const li = document.createElement("li");
  li.className = filled ? "ok" : "no";
  li.innerHTML = `<span class="mark">${filled ? "✓" : "○"}</span>`;
  const labelSpan = document.createElement("span");
  labelSpan.className = "label";
  labelSpan.textContent = label;
  const valueSpan = document.createElement("span");
  valueSpan.className = "val";
  valueSpan.textContent = filled ? value : "chưa có";
  li.append(labelSpan, valueSpan);
  el.fieldList.appendChild(li);
}

function renderRedFlag(state) {
  el.redflag.classList.toggle("on", Boolean(state.red_flag));
  if (state.red_flag) el.redflagList.textContent = state.red_flag_labels.join(" · ");
}

function renderSummary(state) {
  const show = state.summary_ready;
  el.summaryCard.classList.toggle("on", show);
  if (!show) return;

  el.summaryTable.innerHTML = "";
  state.summary_rows.forEach((row) => {
    const tr = document.createElement("tr");
    const key = document.createElement("td");
    key.className = "k";
    key.textContent = row.label + (row.required ? "" : " (không bắt buộc)");
    const val = document.createElement("td");
    if (row.is_missing) {
      val.className = "missing";
      val.textContent = "Thiếu thông tin";
    } else {
      val.textContent = row.value;
    }
    tr.append(key, val);
    el.summaryTable.appendChild(tr);
  });

  const confirmed = state.state === "confirmed";
  el.confirmActions.hidden = confirmed;
  el.doneMsg.hidden = !confirmed;
  if (confirmed) el.correctionBox.classList.remove("on");
}

function applyState(state) {
  sessionId = state.session_id;
  renderConversation(state.conversation);
  renderProgress(state.progress, state.summary_rows);
  renderRedFlag(state);
  renderSummary(state);

  const collecting = state.state === "collecting";
  el.input.disabled = !collecting;
  el.send.disabled = !collecting;
  if (collecting) el.input.focus();

  el.mode.textContent = state.llm_used
    ? "chế độ: LLM sinh câu hỏi tự nhiên"
    : "chế độ: fallback mẫu cố định (LLM chưa sẵn sàng)";

  if (state.llm_source === "user") {
    setLlmStatus(
      `Đang dùng key của bạn · ${state.llm_provider} · ${state.llm_model || "model mặc định"} · ${state.llm_key_masked}`,
      "ok",
    );
  } else if (state.llm_used) {
    setLlmStatus(`Đang dùng key của server · ${state.llm_provider || "?"}`, "warn");
  } else {
    setLlmStatus("Chưa có LLM — đang chạy fallback mẫu cố định. Nhập API key để bật hỏi-đáp tự nhiên.", "warn");
  }
}

function renderModelOptions(providerName) {
  const entry = providerCatalog.find((item) => item.name === providerName);
  el.llmModelList.innerHTML = "";
  (entry?.suggested_models || []).forEach((model) => {
    const option = document.createElement("option");
    option.value = model;
    el.llmModelList.appendChild(option);
  });
  el.llmModel.placeholder = entry?.suggested_models?.[0] || "tên model";
}

async function loadProviders() {
  const data = await api(`${API}/providers`);
  providerCatalog = data.providers || [];
  el.llmProvider.innerHTML = "";
  providerCatalog.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.name;
    option.textContent = item.server_has_key ? `${item.name} (server có sẵn key)` : item.name;
    el.llmProvider.appendChild(option);
  });

  const saved = loadCredential();
  const initial = saved?.provider || data.server_default_provider || providerCatalog[0]?.name;
  if (initial) el.llmProvider.value = initial;
  renderModelOptions(el.llmProvider.value);
  if (saved) {
    el.llmModel.value = saved.model || "";
    el.llmKey.value = saved.api_key || "";
  }
}

/* Bat dau phien moi. Credential (neu co) gui kem khi tao phien va duoc server giu cho ca phien. */
async function startSession() {
  const saved = loadCredential();
  const body = saved && saved.api_key ? JSON.stringify(saved) : undefined;
  const state = await api(`${API}/sessions`, { method: "POST", body });
  el.disclaimer.textContent = state.disclaimer;

  // Reset khung chat khi tao phien moi, neu khong cac luot cu se dinh lai.
  el.chat.innerHTML = "";
  renderedTurns = 0;
  el.summaryCard.classList.remove("on");
  el.doneMsg.hidden = true;
  applyState(state);
}

async function boot() {
  try {
    await loadProviders();
  } catch (error) {
    setLlmStatus(`Không tải được danh sách provider: ${error.message}`, "err");
  }

  try {
    await startSession();
  } catch (error) {
    addBubble("sys", `Không khởi tạo được phiên: ${error.message}`);
    setLlmStatus(`Không khởi tạo được phiên: ${error.message}`, "err");
  }
}

el.composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = el.input.value.trim();
  if (!message || !sessionId) return;

  el.input.value = "";
  el.input.disabled = true;
  el.send.disabled = true;
  addBubble("sys", "đang xử lý…");
  const pending = el.chat.lastElementChild;

  try {
    const state = await api(`${API}/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ message }),
    });
    pending.remove();
    applyState(state);
  } catch (error) {
    pending.remove();
    addBubble("sys", `Lỗi: ${error.message}`);
    el.input.disabled = false;
    el.send.disabled = false;
  }
});

el.btnYes.addEventListener("click", async () => {
  try {
    applyState(await api(`${API}/sessions/${sessionId}/confirm`, {
      method: "POST",
      body: JSON.stringify({ is_correct: true }),
    }));
  } catch (error) {
    addBubble("sys", `Lỗi: ${error.message}`);
  }
});

el.btnNo.addEventListener("click", () => {
  el.correctionBox.classList.add("on");
  el.correctionInput.focus();
});

el.correctionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const correction = el.correctionInput.value.trim();
  if (!correction) return;
  el.correctionInput.value = "";
  el.correctionBox.classList.remove("on");

  try {
    applyState(await api(`${API}/sessions/${sessionId}/confirm`, {
      method: "POST",
      body: JSON.stringify({ is_correct: false, correction }),
    }));
  } catch (error) {
    addBubble("sys", `Lỗi: ${error.message}`);
  }
});

el.llmProvider.addEventListener("change", () => {
  renderModelOptions(el.llmProvider.value);
  el.llmModel.value = "";
});

el.toggleKey.addEventListener("click", () => {
  const hidden = el.llmKey.type === "password";
  el.llmKey.type = hidden ? "text" : "password";
  el.toggleKey.textContent = hidden ? "ẩn" : "hiện";
});

el.testLlm.addEventListener("click", async () => {
  const apiKey = el.llmKey.value.trim();
  if (!apiKey) {
    setLlmStatus("Nhập API key trước khi kiểm tra.", "warn");
    return;
  }
  el.testLlm.disabled = true;
  setLlmStatus("Đang gọi thử…", "warn");
  try {
    const result = await api(`${API}/providers/test`, {
      method: "POST",
      body: JSON.stringify({
        provider: el.llmProvider.value,
        api_key: apiKey,
        model: el.llmModel.value.trim() || null,
      }),
    });
    if (result.ok) {
      setLlmStatus(`Kết nối OK · ${result.provider} · ${result.model} · ${result.key_masked}`, "ok");
    } else {
      setLlmStatus(`Không gọi được: ${result.detail}`, "err");
    }
  } catch (error) {
    setLlmStatus(`Không gọi được: ${error.message}`, "err");
  } finally {
    el.testLlm.disabled = false;
  }
});

el.applyLlm.addEventListener("click", async () => {
  const apiKey = el.llmKey.value.trim();
  if (!apiKey) {
    setLlmStatus("Chưa nhập API key. Bỏ trống thì demo sẽ dùng key của server (nếu có).", "warn");
    saveCredential(null);
  } else {
    saveCredential({
      provider: el.llmProvider.value,
      api_key: apiKey,
      model: el.llmModel.value.trim() || null,
    });
  }

  el.applyLlm.disabled = true;
  try {
    await startSession();
  } catch (error) {
    setLlmStatus(`Không áp dụng được: ${error.message}`, "err");
  } finally {
    el.applyLlm.disabled = false;
  }
});

el.clearLlm.addEventListener("click", async () => {
  saveCredential(null);
  el.llmKey.value = "";
  el.llmModel.value = "";
  try {
    await startSession();
  } catch (error) {
    setLlmStatus(`Lỗi: ${error.message}`, "err");
  }
});

boot();
