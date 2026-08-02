const state = {
  caseId: null,
  currentCase: null,
  activeTab: "summary",
};

const elements = {
  systemStatus: document.querySelector("#systemStatus"),
  messages: document.querySelector("#messages"),
  chatForm: document.querySelector("#chatForm"),
  messageInput: document.querySelector("#messageInput"),
  newCaseButton: document.querySelector("#newCaseButton"),
  caseId: document.querySelector("#caseId"),
  caseStatus: document.querySelector("#caseStatus"),
  casePriority: document.querySelector("#casePriority"),
  detailsView: document.querySelector("#detailsView"),
  queueList: document.querySelector("#queueList"),
  refreshQueueButton: document.querySelector("#refreshQueueButton"),
  approvedResponse: document.querySelector("#approvedResponse"),
  approveButton: document.querySelector("#approveButton"),
  escalateButton: document.querySelector("#escalateButton"),
  askMoreButton: document.querySelector("#askMoreButton"),
  tabs: document.querySelectorAll(".tab"),
};

elements.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = elements.messageInput.value.trim();
  if (!message) return;

  addMessage("patient", message);
  elements.messageInput.value = "";
  setStatus("Sending");

  const payload = { message };
  if (state.caseId) payload.case_id = state.caseId;

  const response = await fetchJson("/api/v1/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  state.caseId = response.case_id;
  state.currentCase = response;
  addMessage("system", response.response);
  renderCase(response);
  await refreshQueue();
  setStatus("Ready");
});

elements.newCaseButton.addEventListener("click", () => {
  state.caseId = null;
  state.currentCase = null;
  elements.messages.innerHTML = "";
  renderCase(null);
});

elements.refreshQueueButton.addEventListener("click", refreshQueue);

elements.approveButton.addEventListener("click", () => reviewCase("approve"));
elements.escalateButton.addEventListener("click", () => reviewCase("escalate"));
elements.askMoreButton.addEventListener("click", () => reviewCase("ask_more"));

elements.tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    state.activeTab = tab.dataset.tab;
    elements.tabs.forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    renderDetails();
  });
});

async function reviewCase(action) {
  if (!state.caseId) return;

  const approvedResponse = elements.approvedResponse.value.trim();
  const payload = { action };

  if (action === "ask_more") {
    payload.ask_more_question = approvedResponse || "Bạn vui lòng bổ sung thêm thông tin triệu chứng.";
  } else {
    payload.approved_response = approvedResponse;
  }

  setStatus("Reviewing");
  const response = await fetchJson(`/api/v1/cases/${state.caseId}/review`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

  addMessage("system", response.patient_visible_response || `Case ${response.status}`);
  const fullCase = await fetchJson(`/api/v1/cases/${state.caseId}`);
  state.currentCase = normalizeCaseResponse(fullCase);
  renderCase(state.currentCase);
  await refreshQueue();
  setStatus("Ready");
}

async function refreshQueue() {
  const cases = await fetchJson("/api/v1/nurse/queue");
  elements.queueList.innerHTML = "";

  cases.slice().reverse().forEach((item) => {
    const priority = item.triage_proposal?.priority || "-";
    const node = document.createElement("div");
    node.className = "queue-item";
    node.innerHTML = `
      <strong>${item.case_id}</strong>
      <span>${item.status} · <b class="priority-${priority}">${priority}</b></span>
    `;
    node.addEventListener("click", () => {
      state.caseId = item.case_id;
      state.currentCase = normalizeCaseResponse(item);
      renderCase(state.currentCase);
    });
    elements.queueList.appendChild(node);
  });
}

function renderCase(data) {
  if (!data) {
    elements.caseId.textContent = "No case";
    elements.caseStatus.textContent = "-";
    elements.casePriority.textContent = "-";
    elements.detailsView.textContent = "{}";
    return;
  }

  elements.caseId.textContent = data.case_id;
  elements.caseStatus.textContent = data.status || "-";
  elements.casePriority.textContent = data.triage_proposal?.priority || "-";
  renderDetails();
}

function renderDetails() {
  const data = state.currentCase;
  if (!data) {
    elements.detailsView.textContent = "{}";
    return;
  }

  const detailByTab = {
    summary: {
      summary: data.summary,
      red_flags: data.red_flags,
      triage_proposal: data.triage_proposal,
      validation: data.validation,
    },
    mapping: {
      structured_data: data.structured_data,
      analysis: data.analysis,
    },
    queue: {
      queue_item: data.queue_item,
      status: data.status,
      requires_human_approval: data.requires_human_approval ?? true,
    },
  };

  elements.detailsView.textContent = JSON.stringify(detailByTab[state.activeTab], null, 2);
}

function normalizeCaseResponse(data) {
  return {
    case_id: data.case_id,
    status: data.status,
    structured_data: data.structured_data,
    validation: data.validation,
    red_flags: data.red_flags,
    triage_proposal: data.triage_proposal,
    summary: data.summary,
    queue_item: data.queue_item,
    requires_human_approval: true,
  };
}

function addMessage(role, content) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.textContent = content;
  elements.messages.appendChild(node);
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const errorText = await response.text();
    setStatus("Error");
    throw new Error(errorText);
  }

  return response.json();
}

function setStatus(value) {
  elements.systemStatus.textContent = value;
}

refreshQueue().catch(() => setStatus("Queue error"));
