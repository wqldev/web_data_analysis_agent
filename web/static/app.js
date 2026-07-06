const API = "/api";

const $ = (sel) => document.querySelector(sel);
const questionInput = $("#questionInput");
const submitBtn = $("#submitBtn");
const historyList = $("#historyList");
const progressPanel = $("#progressPanel");
const progressDetail = $("#progressDetail");
const reportPanel = $("#reportPanel");
const reportContent = $("#reportContent");
const reportTitle = $("#reportTitle");
const reportBadge = $("#reportBadge");
const emptyState = $("#emptyState");
const adminBtn = $("#adminBtn");
const adminDialog = $("#adminDialog");
const adminForm = $("#adminForm");
const adminMsg = $("#adminMsg");
const testConnBtn = $("#testConnBtn");
const testKeyBtn = $("#testKeyBtn");
const cancelAdmin = $("#cancelAdmin");
const refreshHistory = $("#refreshHistory");
const generalAnswer = $("#generalAnswer");
const generalAnswerContent = $("#generalAnswerContent");
const clearGeneralAnswer = $("#clearGeneralAnswer");
const completeDialog = $("#completeDialog");
const completeIcon = $("#completeIcon");
const completeTitle = $("#completeTitle");
const completeMessage = $("#completeMessage");
const completeOkBtn = $("#completeOkBtn");

let activeBoardId = null;
let pollTimer = null;

function formatTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
}

function setProgressPhase(phase) {
  const order = ["planning", "building", "verifying"];
  const idx = order.indexOf(phase);
  document.querySelectorAll(".step").forEach((el) => {
    const step = el.dataset.step;
    const stepIdx = order.indexOf(step);
    el.classList.remove("active", "done");
    if (stepIdx < idx) el.classList.add("done");
    else if (stepIdx === idx) el.classList.add("active");
  });
  document.querySelectorAll(".step-line").forEach((line, i) => {
    line.classList.toggle("done", i < idx);
  });
}

function showReport(requirement, report, passed = true) {
  generalAnswer.classList.add("hidden");
  emptyState.classList.add("hidden");
  reportPanel.classList.remove("hidden");
  reportTitle.textContent = requirement || "分析报告";
  reportBadge.textContent = passed ? "验收通过" : "验收未通过";
  reportBadge.classList.toggle("failed", !passed);
  reportContent.innerHTML = marked.parse(report || "_暂无报告内容_");
}

function showGeneralAnswer(text) {
  reportPanel.classList.add("hidden");
  progressPanel.classList.add("hidden");
  emptyState.classList.add("hidden");
  generalAnswerContent.innerHTML = marked.parse(text || "_无回答_");
  generalAnswer.classList.remove("hidden");
  clearInterval(pollTimer);
  pollTimer = null;
}

function showBlockedMessage(text) {
  reportPanel.classList.add("hidden");
  progressPanel.classList.add("hidden");
  emptyState.classList.add("hidden");
  generalAnswerContent.textContent =
    text || "这是禁止行为！！！修改数据库是不允许的，如有任何问题请联系数据库管理员";
  generalAnswer.classList.remove("hidden");
  clearInterval(pollTimer);
  pollTimer = null;
}

function showLoading() {
  emptyState.classList.add("hidden");
  generalAnswer.classList.add("hidden");
  reportPanel.classList.add("hidden");
  progressPanel.classList.remove("hidden");
  setProgressPhase("planning");
  progressDetail.textContent = "正在启动 Cursor Agent…";
}

function hideLoading() {
  progressPanel.classList.add("hidden");
  clearInterval(pollTimer);
  pollTimer = null;
}

function showCompleteDialog(passed, summary) {
  if (passed) {
    completeIcon.textContent = "✓";
    completeIcon.className = "complete-icon success";
    completeTitle.textContent = "分析完成";
    completeMessage.textContent = summary || "报告已生成，验收通过。";
  } else {
    completeIcon.textContent = "!";
    completeIcon.className = "complete-icon failed";
    completeTitle.textContent = "分析未通过";
    completeMessage.textContent = summary || "验收未通过，请查看报告或重新提问。";
  }
  completeDialog.showModal();
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function fetchHistory() {
  const res = await fetch(`${API}/history`);
  const data = await res.json();
  historyList.innerHTML = "";
  if (!data.items?.length) {
    historyList.innerHTML = '<li class="history-item" style="cursor:default;color:var(--muted)">暂无历史记录</li>';
    return;
  }
  data.items.forEach((item) => {
    const li = document.createElement("li");
    li.className = "history-item" + (item.board_id === activeBoardId ? " active" : "");
    li.dataset.boardId = item.board_id;
    li.innerHTML = `
      <div class="history-item-body" data-board-id="${item.board_id}">
        <div class="title">${escapeHtml(item.requirement)}</div>
        <div class="meta">${item.phase_label || item.status} · ${formatTime(item.updated_at)}</div>
      </div>
      <button class="btn-delete" data-board-id="${item.board_id}" title="删除此记录">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="3 6 5 6 21 6"></polyline>
          <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"></path>
          <line x1="10" y1="11" x2="10" y2="17"></line>
          <line x1="14" y1="11" x2="14" y2="17"></line>
        </svg>
      </button>
    `;
    li.querySelector(".history-item-body").addEventListener("click", () => loadReport(item.board_id));
    li.querySelector(".btn-delete").addEventListener("click", (e) => {
      e.stopPropagation();
      deleteHistory(item.board_id, li);
    });
    historyList.appendChild(li);
  });
}

async function deleteHistory(boardId, liEl) {
  if (!confirm("确定删除此分析记录？")) return;
  try {
    const res = await fetch(`${API}/analyze/${boardId}`, { method: "DELETE" });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || errData.message || `删除失败 (${res.status})`);
    }
    liEl.remove();
    if (activeBoardId === boardId) {
      activeBoardId = null;
      reportPanel.classList.add("hidden");
      emptyState.classList.remove("hidden");
    }
    if (!historyList.children.length) {
      historyList.innerHTML = '<li class="history-item" style="cursor:default;color:var(--muted)">暂无历史记录</li>';
    }
  } catch (err) {
    alert(err.message);
  }
}

async function loadReport(boardId) {
  activeBoardId = boardId;
  generalAnswer.classList.add("hidden");
  try {
    const res = await fetch(`${API}/analyze/${boardId}/report`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "报告未就绪");
    hideLoading();
    if (data.phase_label === "已回答") {
      showGeneralAnswer(data.report);
    } else if (data.phase_label === "禁止操作") {
      showBlockedMessage(data.report);
    } else {
      showReport(data.requirement, data.report, data.phase === "done");
    }
    await fetchHistory();
  } catch (err) {
    alert(err.message || "加载报告失败");
  }
}

function pollStatus(boardId, question) {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`${API}/analyze/${boardId}/status`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "状态查询失败");

      activeBoardId = data.board_id || boardId;

      if (data.phase && data.phase !== "done" && data.phase !== "failed") {
        setProgressPhase(data.phase);
      }
      progressDetail.textContent =
        data.detail || data.phase_label || data.verify_summary || "执行中…";

      if (data.status === "done" || data.status === "failed") {
        hideLoading();
        submitBtn.disabled = false;
        clearInterval(pollTimer);
        pollTimer = null;
        if (data.report) {
          const passed = data.passed !== false;
          showReport(question, data.report, passed);
          showCompleteDialog(
            passed,
            data.verify_summary || data.detail || (passed ? "报告已生成，验收通过。" : "验收未通过。")
          );
        } else if (data.error || data.detail) {
          alert(data.error || data.detail);
          emptyState.classList.remove("hidden");
        }
        await fetchHistory();
      } else if (data.phase === "done" && data.report) {
        hideLoading();
        submitBtn.disabled = false;
        clearInterval(pollTimer);
        pollTimer = null;
        const passed = data.passed !== false;
        showReport(question, data.report, passed);
        showCompleteDialog(
          passed,
          data.verify_summary || data.detail || (passed ? "报告已生成，验收通过。" : "验收未通过。")
        );
        await fetchHistory();
      }
    } catch (err) {
      hideLoading();
      submitBtn.disabled = false;
      alert(err.message || "轮询失败");
    }
  }, 2500);
}

async function submitQuestion() {
  const question = questionInput.value.trim();
  if (!question) return;

  submitBtn.disabled = true;
  showLoading();

  try {
    const res = await fetch(`${API}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.message || "分析启动失败");

    // DDL / 写操作：仅展示固定拒绝文案
    if (data.direct && data.blocked) {
      hideLoading();
      submitBtn.disabled = false;
      showBlockedMessage(data.report);
      await fetchHistory();
      return;
    }

    // 通用回答：展示在输入框下方
    if (data.direct && data.phase_label === "已回答") {
      hideLoading();
      submitBtn.disabled = false;
      showGeneralAnswer(data.report);
      await fetchHistory();
      return;
    }

    // 信息查询（表列表/表结构）：直接展示报告
    if (data.direct) {
      hideLoading();
      submitBtn.disabled = false;
      if (data.report) {
        showReport(question, data.report, data.passed !== false);
      } else {
        emptyState.classList.remove("hidden");
      }
      await fetchHistory();
      return;
    }

    pollStatus(data.board_id, question);
  } catch (err) {
    hideLoading();
    emptyState.classList.remove("hidden");
    submitBtn.disabled = false;
    alert(err.message || "请先在管理员配置中填写 Cursor API Key 和 MySQL 连接");
  }
}

async function loadAdminConfig() {
  const [mysqlRes, cursorRes] = await Promise.all([
    fetch(`${API}/admin/mysql-config`),
    fetch(`${API}/admin/cursor-config`),
  ]);
  const cfg = await mysqlRes.json();
  const cursor = await cursorRes.json();
  adminForm.host.value = cfg.host || "localhost";
  adminForm.port.value = cfg.port || 3306;
  adminForm.user.value = cfg.user || "root";
  adminForm.password.value = "";
  adminForm.database.value = cfg.database || "";
  adminForm.allow_writes.checked = !!cfg.allow_writes;
  adminForm.cursor_api_key.value = "";
  adminForm.cursor_model.value = cursor.model || "composer-2.5";
  const hints = [];
  if (cfg.password_set) hints.push("MySQL 密码已配置");
  if (cursor.api_key_set) hints.push("Cursor API Key 已配置");
  adminMsg.textContent = hints.join("；") || "请填写 MySQL 与 Cursor API Key";
  adminMsg.className = "admin-msg";
}

async function saveAdminConfig(e) {
  e.preventDefault();
  const mysqlPayload = {
    host: adminForm.host.value,
    port: Number(adminForm.port.value),
    user: adminForm.user.value,
    password: adminForm.password.value,
    database: adminForm.database.value,
    allow_writes: adminForm.allow_writes.checked,
  };
  const cursorPayload = {
    api_key: adminForm.cursor_api_key.value,
    model: adminForm.cursor_model.value || "composer-2.5",
  };
  const [mysqlRes, cursorRes] = await Promise.all([
    fetch(`${API}/admin/mysql-config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(mysqlPayload),
    }),
    fetch(`${API}/admin/cursor-config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cursorPayload),
    }),
  ]);
  if (!mysqlRes.ok || !cursorRes.ok) {
    adminMsg.textContent = "保存失败，请检查输入";
    adminMsg.className = "admin-msg err";
    return;
  }
  adminMsg.textContent = "配置已保存";
  adminMsg.className = "admin-msg ok";
  adminDialog.close();
}

async function testConnection() {
  const payload = {
    host: adminForm.host.value,
    port: Number(adminForm.port.value),
    user: adminForm.user.value,
    password: adminForm.password.value,
    database: adminForm.database.value,
    allow_writes: adminForm.allow_writes.checked,
  };
  adminMsg.textContent = "测试中…";
  adminMsg.className = "admin-msg";
  try {
    const res = await fetch(`${API}/admin/test-connection`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "连接失败");
    adminMsg.textContent = `${data.message}（${data.version} / ${data.current_database}）`;
    adminMsg.className = "admin-msg ok";
  } catch (err) {
    adminMsg.textContent = err.message;
    adminMsg.className = "admin-msg err";
  }
}

async function testCursorKey() {
  const payload = {
    api_key: adminForm.cursor_api_key.value || undefined,
    model: adminForm.cursor_model.value || "composer-2.5",
  };
  adminMsg.textContent = "测试中…";
  adminMsg.className = "admin-msg";
  try {
    const res = await fetch(`${API}/admin/test-cursor-key`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "验证失败");
    adminMsg.textContent = data.message;
    adminMsg.className = "admin-msg ok";
  } catch (err) {
    adminMsg.textContent = err.message;
    adminMsg.className = "admin-msg err";
  }
}

submitBtn.addEventListener("click", submitQuestion);
questionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") submitQuestion();
});
refreshHistory.addEventListener("click", fetchHistory);
adminBtn.addEventListener("click", async () => {
  await loadAdminConfig();
  adminDialog.showModal();
});
cancelAdmin.addEventListener("click", () => adminDialog.close());
adminForm.addEventListener("submit", saveAdminConfig);
testConnBtn.addEventListener("click", testConnection);
testKeyBtn.addEventListener("click", testCursorKey);
clearGeneralAnswer.addEventListener("click", () => {
  generalAnswer.classList.add("hidden");
});
completeOkBtn.addEventListener("click", () => completeDialog.close());

fetchHistory();
