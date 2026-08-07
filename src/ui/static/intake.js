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
};

let sessionId = null;
let renderedTurns = 0;

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
}

async function boot() {
  try {
    const health = await api(`${API}/health`);
    el.mode.textContent = health.llm_available
      ? "chế độ: LLM sinh câu hỏi tự nhiên"
      : "chế độ: fallback mẫu cố định (LLM chưa cấu hình)";
  } catch {
    el.mode.textContent = "không đọc được trạng thái LLM";
  }

  try {
    const state = await api(`${API}/sessions`, { method: "POST" });
    el.disclaimer.textContent = state.disclaimer;
    applyState(state);
  } catch (error) {
    addBubble("sys", `Không khởi tạo được phiên: ${error.message}`);
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

boot();
