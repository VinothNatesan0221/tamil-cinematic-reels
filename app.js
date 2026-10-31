/*
 * Tamil Cinematic Reels dashboard
 * Read-only Apps Script JSONP client.
 *
 * If your Apps Script deployment URL changes, update APPS_SCRIPT_URL below.
 * Never put Gemini keys, GitHub tokens, or other secrets in this file.
 */
const APPS_SCRIPT_URL =
  "https://script.google.com/macros/s/AKfycbzsX1-JhPay3TQSl4KMaRXaKjnl8QXHWJNgOMsKwyKPY8WfbF7tj4LIwiikuT87CoCa/exec";

const elements = {
  total: document.getElementById("totalDrafts"),
  approved: document.getElementById("approvedDrafts"),
  queued: document.getElementById("queuedRenders"),
  updated: document.getElementById("lastUpdated"),
  banner: document.getElementById("connectionBanner"),
  connection: document.getElementById("connectionState"),
  table: document.getElementById("draftTableBody"),
  filter: document.getElementById("statusFilter"),
  refresh: document.getElementById("refreshButton")
};

let allDrafts = [];
let requestTimer = null;

function showBanner(message, type) {
  elements.banner.textContent = message;
  elements.banner.className = `notice notice-${type}`;
  if (elements.connection) {
    const labels = { success: "Connected", error: "Disconnected", info: "Connecting…" };
    elements.connection.textContent = labels[type] || "Unknown";
    elements.connection.className = `live-indicator connection-${type || "info"}`;
  }
}

function formatDate(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit"
  });
}

function classifyStatus(status) {
  const value = String(status || "").trim().toUpperCase();
  if (value === "APPROVED") return "approved";
  if (value.includes("ERROR") || value.includes("FAILED") || value.includes("CANCELLED") || value === "FAILURE") return "error";
  if (["SUCCESS", "SUCCEEDED", "COMPLETED"].includes(value) || value.includes("SUCCESS")) return "approved";
  if (["IN_PROGRESS", "RUNNING", "QUEUED", "WAITING"].includes(value) ||
      value.includes("RUNNING") || value.includes("QUEUED") || value.includes("SUBMITTING")) return "working";
  if (value.includes("REVIEW") || value.includes("DRAFT")) return "review";
  return "other";
}

function safeGitHubUrl(value) {
  try {
    const url = new URL(String(value || ""));
    if (url.protocol !== "https:" || url.hostname !== "github.com") return "";
    return url.href;
  } catch (_) {
    return "";
  }
}

function statusPill(status, type) {
  const safe = escapeHtml(status || "Not set");
  return `<span class="status-pill ${type}">${safe}</span>`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;",
    '"': "&quot;", "'": "&#39;"
  })[char]);
}

function renderDrafts() {
  const filter = elements.filter.value;
  const filtered = allDrafts.filter(draft => {
    const approvalType = classifyStatus(draft.status);
    const render = String(draft.githubStatus || draft.renderStatus || "").toUpperCase();
    if (filter === "all") return true;
    if (filter === "approved") return approvalType === "approved" && draft.approvalVerified !== false;
    if (filter === "review") return approvalType === "review";
    if (filter === "error") return approvalType === "error" || classifyStatus(render) === "error";
    if (filter === "queued") return classifyStatus(render) === "working";
    return true;
  });

  if (!filtered.length) {
    elements.table.innerHTML =
      '<tr><td colspan="5" class="empty-state">No drafts match this filter.</td></tr>';
    return;
  }

  elements.table.innerHTML = filtered.map(draft => {
    const approvalType = classifyStatus(draft.status);
    const approvalText = String(draft.status || "Not set").toUpperCase() === "APPROVED" && draft.approvalVerified === false
      ? "APPROVED — NOT VERIFIED" : (draft.status || "Not set");
    const approvalDisplayType = approvalText.includes("NOT VERIFIED") ? "error" : approvalType;
    const renderText = String(draft.githubStatus || draft.renderStatus || "").trim();
    const renderType = classifyStatus(renderText);

    const title = draft.title || (approvalType === "error" ? "Story generation failed" : "Untitled draft");
    const hook = draft.hook ? `<small class="story-hook">${escapeHtml(draft.hook)}</small>` : "";
    const workflowUrl = safeGitHubUrl(draft.githubRunUrl || draft.workflowUrl);
    const artifactUrl = safeGitHubUrl(draft.artifactUrl);
    const workflow = workflowUrl
      ? `<a class="workflow-link" href="${escapeHtml(workflowUrl)}" target="_blank" rel="noopener noreferrer">Open run ↗</a>${artifactUrl ? ` <a class="workflow-link" href="${escapeHtml(artifactUrl)}" target="_blank" rel="noopener noreferrer">Artifact ↗</a>` : ""}`
      : '<span class="muted">Not synced</span>';

    return `<tr>
      <td><div class="story-cell"><strong>${escapeHtml(title)}</strong>${hook}<small class="row-number">Sheet row ${escapeHtml(draft.rowNumber)}</small></div></td>
      <td class="date-cell">${escapeHtml(formatDate(draft.createdAt))}</td>
      <td>${statusPill(approvalText, approvalDisplayType)}</td>
      <td>${statusPill(renderText || "Not started", renderType)}</td>
      <td>${workflow}</td>
    </tr>`;
  }).join("");
}

function handleDashboardData(data) {
  clearTimeout(requestTimer);

  if (!data || data.success !== true) {
    showBanner((data && data.error) || "The dashboard API returned an unexpected response.", "error");
    elements.table.innerHTML =
      '<tr><td colspan="5" class="empty-state">Could not load dashboard data.</td></tr>';
    return;
  }

  elements.total.textContent = Number(data.totalDrafts ?? 0);
  elements.approved.textContent = Number(data.approvedDrafts ?? 0);
  elements.queued.textContent = Number(data.queuedRenders ?? 0);
  elements.updated.textContent = formatDate(data.timestamp);
  allDrafts = Array.isArray(data.drafts) ? data.drafts : [];
  renderDrafts();
  showBanner("Connected — dashboard data loaded from your Google Sheet.", "success");
}

function loadDashboard() {
  showBanner("Refreshing dashboard data…", "info");
  elements.refresh.disabled = true;
  elements.refresh.textContent = "Loading…";

  // Apps Script supports JSONP through the callback parameter.
  // A unique callback avoids collisions between refresh attempts.
  const callbackName = `tcrDashboardCallback_${Date.now()}`;
  window[callbackName] = function (data) {
    handleDashboardData(data);
    delete window[callbackName];
    elements.refresh.disabled = false;
    elements.refresh.textContent = "↻ Refresh";
  };

  const oldScripts = document.querySelectorAll("script[data-dashboard-jsonp='true']");
  oldScripts.forEach(node => node.remove());

  const script = document.createElement("script");
  script.dataset.dashboardJsonp = "true";
  script.src = `${APPS_SCRIPT_URL}?action=dashboard&callback=${callbackName}&_=${Date.now()}`;
  script.onerror = function () {
    clearTimeout(requestTimer);
    showBanner("Connection failed. Check the Apps Script deployment URL and web app access settings.", "error");
    elements.table.innerHTML =
      '<tr><td colspan="5" class="empty-state">Dashboard API unavailable. Use Refresh to try again.</td></tr>';
    elements.refresh.disabled = false;
    elements.refresh.textContent = "↻ Refresh";
    delete window[callbackName];
  };

  requestTimer = setTimeout(() => {
    showBanner("The dashboard API did not respond in time. Check deployment access and try again.", "error");
    elements.refresh.disabled = false;
    elements.refresh.textContent = "↻ Refresh";
    delete window[callbackName];
    script.remove();
  }, 15000);

  document.body.appendChild(script);
}

elements.refresh.addEventListener("click", loadDashboard);
elements.filter.addEventListener("change", renderDrafts);
loadDashboard();
