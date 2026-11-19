const pages = ["dashboard", "chat", "sources", "modules", "activity", "settings"];
const pageTitles = {
  dashboard: "Overview",
  chat: "Assistant",
  sources: "Data sources",
  modules: "Modules",
  activity: "Activity",
  settings: "Settings",
};
const chatMessages = [];
let currentPage = "dashboard";
let toastTimer;
let refreshTimer;

const byId = (id) => document.getElementById(id);
const make = (tag, className, text) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
};

async function api(path, options = {}) {
  const token = getApiToken();
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { "X-Homebrain-Token": token } : {}),
      ...options.headers,
    },
  });
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`The server returned an invalid response (${response.status}).`);
  }
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status}).`);
  return payload;
}

function getApiToken() {
  try {
    return localStorage.getItem("homebrain-api-token") || "";
  } catch {
    return "";
  }
}

function showToast(message, isError = false) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 3200);
}

function navigate(page, updateHash = true) {
  if (!pages.includes(page)) page = "dashboard";
  currentPage = page;
  document.querySelectorAll(".page-view").forEach((view) => {
    view.classList.toggle("hidden", view.id !== `page-${page}`);
  });
  document.querySelectorAll(".nav-link").forEach((link) => {
    const active = link.dataset.page === page;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  byId("page-title").textContent = pageTitles[page];
  if (updateHash && location.hash !== `#${page}`) history.replaceState(null, "", `#${page}`);
  if (page === "sources") loadSources();
  if (page === "modules") loadModules();
  if (page === "activity") loadActivity();
}

function renderModules(modules) {
  const list = byId("module-list");
  list.replaceChildren();
  if (!modules.length) {
    const empty = make("div", "empty-state");
    empty.append(make("span", "", "▦"), make("h3", "", "No modules are configured."));
    list.append(empty);
    return;
  }
  modules.forEach((module) => {
    const card = make("article", "panel module-card");
    const heading = make("div", "module-card-heading");
    const icon = make("span", "module-icon", module.kind === "ai" ? "✳" : module.kind === "media" ? "▻" : "⌘");
    const name = make("div");
    name.append(make("p", "eyebrow", module.kind.toUpperCase()), make("h2", "", module.name));
    heading.append(icon, name);
    card.append(heading, make("p", "module-description", module.description));

    const endpoint = new URL(module.public_path || "/", window.location.origin);
    if (module.public_port) endpoint.port = String(module.public_port);
    const link = make("a", "button button-secondary module-link", "Open module");
    link.href = endpoint.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.append(make("span", "", " ↗"));
    card.append(link);
    list.append(card);
  });
}

async function loadModules() {
  const list = byId("module-list");
  try {
    const data = await api("/api/v1/modules");
    renderModules(data.modules || []);
  } catch (error) {
    list.replaceChildren();
    const message = make("div", "empty-state");
    message.append(make("span", "", "!"), make("h3", "", "Modules couldn’t load."), make("p", "", error.message));
    list.append(message);
  }
}

function dateLabel(value) {
  if (!value) return "Not yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function renderDashboard(data) {
  byId("nav-source-count").textContent = String(data.source_count || 0);
  const run = data.latest_run;
  const result = data.dashboard;
  byId("dashboard-headline").textContent = result?.headline ||
    (data.source_count ? "Your next analysis will bring your signals together." : "Connect a data source to begin seeing the bigger picture.");
  byId("analysis-status").textContent = run ? run.status.toUpperCase() : "READY";
  byId("analysis-status").className = `banner-status ${run?.status || "empty"}`;
  byId("last-updated").textContent = run ? `Last checked ${dateLabel(run.completed_at)}` : "Waiting for first analysis";

  const metrics = byId("metrics-grid");
  metrics.replaceChildren();
  if (!result?.metrics?.length) {
    const card = make("article", "metric-card empty-metric");
    card.append(make("span", "metric-icon", "✳"));
    card.append(make("p", "", data.source_count
      ? "Your dashboard signals will appear after the first successful analysis."
      : "Dashboard insights will appear here after your first analysis."));
    metrics.append(card);
  } else {
    result.metrics.forEach((metric, index) => {
      const card = make("article", "metric-card");
      const top = make("div", "metric-top");
      top.append(make("span", "metric-label", metric.label));
      top.append(make("span", "metric-icon", ["◷", "⌂", "↗", "✧"][index % 4]));
      card.append(top);
      card.append(make("p", "metric-value", metric.value));
      if (metric.detail) card.append(make("p", "metric-detail", metric.detail));
      if (metric.trend) card.append(make("span", `metric-trend ${metric.trend}`, metric.trend === "up" ? "↗" : metric.trend === "down" ? "↘" : "→"));
      metrics.append(card);
    });
  }

  const insights = byId("insight-list");
  insights.replaceChildren();
  if (!result?.insights?.length) {
    const empty = make("div", "empty-state compact-empty");
    empty.append(make("span", "", "✧"), make("p", "", "Your findings will show up here."));
    insights.append(empty);
  } else {
    result.insights.forEach((insight) => {
      const row = make("article", "insight-item");
      row.append(make("span", `insight-priority ${insight.priority}`));
      const content = make("div");
      content.append(make("h3", "", insight.title), make("p", "", insight.body));
      row.append(content);
      insights.append(row);
    });
  }
  loadSources();
}

function sourceIcon(source) {
  if (source.type === "weather") return "☼";
  if (source.type === "gmail") return "✉";
  if (source.type === "github") return "⌘";
  if (source.type === "traffic") return "⇢";
  if (source.type === "stocks") return "↗";
  if (source.type === "news") return "▤";
  if (source.type === "events") return "✦";
  return source.type === "url" ? "↗" : "≡";
}

function sourceLocation(source) {
  if (source.type === "weather") return "Weather · Open-Meteo";
  if (source.type === "gmail" || source.type === "github") return source.location;
  if (source.type === "traffic") return `Traffic · ${source.location}`;
  if (source.type === "stocks") return `Markets · ${source.location}`;
  if (source.type === "news") return source.location;
  if (source.type === "events") return `Events · ${source.location}`;
  return source.type === "url" ? source.location : "Text note";
}

function renderSources(sources) {
  byId("nav-source-count").textContent = String(sources.length);
  byId("source-count").textContent = String(sources.length);

  const fullList = byId("source-list");
  fullList.replaceChildren();
  if (!sources.length) {
    const empty = make("div", "empty-state");
    empty.append(
      make("span", "", "⌘"),
      make("h3", "", "A clearer picture starts here."),
      make("p", "", "Add a note or connect a read-only text feed to get started."),
    );
    fullList.append(empty);
  } else {
    sources.forEach((source) => {
      const card = make("article", "source-card");
      card.append(make("span", "source-card-icon", sourceIcon(source)));
      const copy = make("div", "source-card-copy");
      copy.append(make("strong", "", source.name), make("small", "", `${sourceLocation(source)} · ${source.enabled ? "Included in analysis" : "Paused"}`));
      const actions = make("div", "source-actions");
      const toggle = make("button", `source-toggle ${source.enabled ? "enabled" : ""}`);
      toggle.type = "button";
      toggle.setAttribute("role", "switch");
      toggle.setAttribute("aria-checked", String(source.enabled));
      toggle.setAttribute("aria-label", `${source.enabled ? "Pause" : "Enable"} ${source.name}`);
      toggle.dataset.action = "toggle";
      toggle.dataset.id = source.id;
      const remove = make("button", "delete-source", "×");
      remove.type = "button";
      remove.setAttribute("aria-label", `Remove ${source.name}`);
      remove.dataset.action = "delete";
      remove.dataset.id = source.id;
      actions.append(toggle, remove);
      card.append(copy, actions);
      fullList.append(card);
    });
  }

  const miniList = byId("dashboard-sources");
  miniList.replaceChildren();
  const active = sources.filter((source) => source.enabled).slice(0, 4);
  if (!active.length) {
    const empty = make("div", "empty-state compact-empty");
    empty.append(make("span", "", "⌘"), make("p", "", "No active sources."));
    miniList.append(empty);
  } else {
    active.forEach((source) => {
      const row = make("div", "mini-source");
      row.append(make("span", "mini-source-icon", sourceIcon(source)));
      const details = make("div");
      details.append(make("strong", "", source.name), make("small", "", sourceLocation(source)));
      row.append(details, make("span", "source-state", "ACTIVE"));
      miniList.append(row);
    });
  }
}

async function loadSources() {
  try {
    const data = await api("/api/v1/sources");
    renderSources(data.sources || []);
  } catch (error) {
    if (currentPage === "sources") showToast(error.message, true);
  }
}

function renderActivity(runs) {
  const list = byId("activity-list");
  list.replaceChildren();
  if (!runs.length) {
    const empty = make("div", "empty-state");
    empty.append(make("span", "", "◷"), make("h3", "", "Your activity will appear here."), make("p", "", "Once Homebrain checks a source, you’ll find a record of it here."));
    list.append(empty);
    return;
  }
  runs.forEach((run) => {
    const row = make("article", "activity-item");
    row.append(make("span", `activity-icon ${run.status}`, run.status === "error" ? "!" : "✳"));
    const copy = make("div", "activity-copy");
    const title = run.headline || (run.status === "empty" ? "No sources were enabled" : run.status === "error" ? "Analysis needs attention" : "Home signals analyzed");
    const sourceError = run.errors?.length ? ` · ${run.errors.length} issue${run.errors.length === 1 ? "" : "s"}` : "";
    copy.append(make("strong", "", title), make("small", "", `${run.status[0].toUpperCase()}${run.status.slice(1)}${sourceError}`));
    row.append(copy, make("time", "activity-time", dateLabel(run.completed_at)));
    list.append(row);
  });
}

async function loadActivity() {
  try {
    const data = await api("/api/v1/agent/runs");
    renderActivity(data.runs || []);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function refreshDashboard() {
  try {
    const [dashboard, health, agentStatus] = await Promise.all([
      api("/api/v1/dashboard"),
      api("/api/v1/health"),
      api("/api/v1/agent/status"),
    ]);
    renderDashboard(dashboard);
    const active = health.status === "ok";
    byId("system-dot").classList.toggle("offline", !active);
    byId("system-status").textContent = active ? (agentStatus.running ? "Analyzing" : "Homebrain online") : "Disconnected";
    const buttons = ["run-analysis", "run-analysis-secondary", "run-analysis-activity"].map(byId).filter(Boolean);
    buttons.forEach((button) => {
      button.disabled = agentStatus.running;
      if (agentStatus.running) button.dataset.busy = "true";
      else delete button.dataset.busy;
    });
    buttons.forEach((button) => {
      if (button.dataset.busy) button.innerHTML = '<span class="button-spark">✳</span> Analyzing…';
      else if (button.id === "run-analysis-secondary") button.textContent = "Run now";
      else button.innerHTML = '<span class="button-spark">✳</span> Analyze now';
    });
    byId("schedule-copy").textContent = `Enabled sources are checked every ${formatInterval(agentStatus.interval_seconds)}. Run an analysis any time.`;
    if (currentPage === "activity") loadActivity();
  } catch {
    byId("system-dot").classList.add("offline");
    byId("system-status").textContent = "Disconnected";
  }
}

function formatInterval(seconds) {
  if (seconds % 3600 === 0) {
    const hours = seconds / 3600;
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }
  if (seconds % 60 === 0) {
    const minutes = seconds / 60;
    return `${minutes} minute${minutes === 1 ? "" : "s"}`;
  }
  return `${seconds} seconds`;
}

async function requestAnalysis() {
  try {
    await api("/api/v1/agent/run", { method: "POST", body: JSON.stringify({}) });
    showToast("Analysis queued. Your dashboard will refresh when it’s ready.");
    refreshDashboard();
  } catch (error) {
    showToast(error.message, true);
  }
}

function appendMessage(role, content, isError = false) {
  const row = make("div", `${role === "user" ? "user-message" : "assistant-message"} message-row`);
  if (isError) row.classList.add("message-error");
  row.append(make("span", "message-avatar", role === "user" ? "H" : "✳"));
  const bubble = make("div", "message-bubble");
  bubble.append(make("span", "message-author", role === "user" ? "You" : "Homebrain"));
  const contentNode = make("div");
  if (role === "assistant") renderAssistantText(contentNode, content);
  else contentNode.append(make("p", "", content));
  bubble.append(contentNode);
  row.append(bubble);
  byId("chat-messages").append(row);
  row.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function renderAssistantText(container, content) {
  const chunks = content.split(/```([^\n`]*)\n?([\s\S]*?)```/g);
  for (let index = 0; index < chunks.length; index += 3) {
    const text = chunks[index] || "";
    if (text.trim()) {
      text.split(/\n{2,}/).forEach((paragraph) => {
        const p = make("p");
        p.textContent = paragraph.trim();
        container.append(p);
      });
    }
    if (index + 2 < chunks.length) {
      const pre = make("pre");
      pre.append(make("code", "", chunks[index + 2].replace(/\n$/, "")));
      container.append(pre);
    }
  }
  if (!container.childNodes.length) container.append(make("p", "", content));
}

async function sendChat(text) {
  const clean = text.trim();
  if (!clean) return;
  chatMessages.push({ role: "user", content: clean });
  appendMessage("user", clean);
  const form = byId("chat-form");
  const send = byId("send-chat");
  send.disabled = true;
  const placeholder = make("div", "assistant-message message-row");
  placeholder.dataset.typing = "true";
  placeholder.append(make("span", "message-avatar", "✳"));
  const bubble = make("div", "message-bubble");
  bubble.append(make("span", "message-author", "Homebrain"));
  const typing = make("span", "typing-indicator");
  typing.append(make("span"), make("span"), make("span"));
  bubble.append(typing);
  placeholder.append(bubble);
  byId("chat-messages").append(placeholder);
  placeholder.scrollIntoView({ block: "nearest", behavior: "smooth" });
  try {
    const response = await api("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify({ messages: chatMessages }),
    });
    chatMessages.push(response);
    placeholder.remove();
    appendMessage("assistant", response.content);
  } catch (error) {
    placeholder.remove();
    appendMessage("assistant", error.message, true);
  } finally {
    send.disabled = false;
    byId("chat-input").focus();
    if (chatMessages.length > 20) chatMessages.splice(0, chatMessages.length - 20);
    form.dataset.busy = "false";
  }
}

document.querySelectorAll("[data-page]").forEach((button) => {
  button.addEventListener("click", () => navigate(button.dataset.page));
});

document.querySelectorAll("#run-analysis, #run-analysis-secondary, #run-analysis-activity").forEach((button) => {
  button.addEventListener("click", requestAnalysis);
});

byId("source-type").addEventListener("change", (event) => {
  const type = event.target.value;
  const valueField = byId("source-value");
  const isUrl = type === "url";
  const isGmail = type === "gmail";
  const isGitHub = type === "github";
  const fields = {
    text: ["Your note", "Anything you’d like Homebrain to keep an eye on…", "Add a note or observation. You can update or remove it any time."],
    url: ["Web address", "https://example.com/feed.json", "Public or local HTTP(S) text endpoints. GET only, without credentials or redirects."],
    gmail: ["Mailbox", "inbox", "Reads headers and labels for at most 20 recent inbox messages. Configure Google OAuth in the local .env file first; no message bodies are read."],
    github: ["Repositories", "owner/repo, owner/repo", "Enter up to five owner/repository names. Reads issue, pull-request, and release metadata only. Configure an optional fine-grained token in .env for private repos."],
    traffic: ["Traffic point", "home or 30.2672,-97.7431", "Samples one nearby road segment. Use home coordinates or latitude,longitude. Requires a TomTom API key in .env."],
    stocks: ["Stock symbols", "SPY, QQQ, DIA", "Enter up to eight symbols. Requires a Finnhub API key in .env; free-plan quotes may be delayed. Quotes are informational, not financial advice."],
    news: ["Location or search", "Austin, TX", "Searches recent headlines via Google News RSS; no API key required. Headlines are not independently verified."],
    events: ["Radius (miles)", "25", "Searches Ticketmaster events within 1–100 miles of your configured home coordinates. Requires a Ticketmaster API key in .env."]
  };
  const [label, placeholder, hint] = fields[type] || fields.text;
  byId("source-value-label").textContent = label;
  valueField.placeholder = placeholder;
  const defaults = { gmail: "inbox", traffic: "home", stocks: "SPY, QQQ, DIA", news: "Austin, TX", events: "25" };
  const previousDefault = valueField.dataset.defaultValue || "";
  if (type === "gmail") valueField.value = "inbox";
  else if (!valueField.value || valueField.value === previousDefault) valueField.value = defaults[type] || "";
  valueField.dataset.defaultValue = defaults[type] || "";
  valueField.rows = isUrl || isGmail || type === "traffic" || type === "stocks" || type === "news" || type === "events" ? 2 : 5;
  byId("source-hint").textContent = hint;
});

byId("source-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = byId("add-source");
  const errorNode = byId("source-error");
  errorNode.textContent = "";
  button.disabled = true;
  try {
    const data = Object.fromEntries(new FormData(form).entries());
    await api("/api/v1/sources", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    byId("source-type").dispatchEvent(new Event("change"));
    await loadSources();
    showToast("Your data source is connected.");
  } catch (error) {
    errorNode.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

byId("source-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const { action, id } = button.dataset;
  if (action === "delete" && !window.confirm("Remove this data source?")) return;
  button.disabled = true;
  try {
    if (action === "delete") {
      await api(`/api/v1/sources/${encodeURIComponent(id)}`, { method: "DELETE" });
      showToast("Data source removed.");
    } else {
      const enabled = button.getAttribute("aria-checked") !== "true";
      await api(`/api/v1/sources/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      });
      showToast(enabled ? "Data source enabled." : "Data source paused.");
    }
    await loadSources();
    refreshDashboard();
  } catch (error) {
    button.disabled = false;
    showToast(error.message, true);
  }
});

byId("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = byId("chat-input");
  const text = input.value;
  if (!text.trim() || byId("send-chat").disabled) return;
  input.value = "";
  sendChat(text);
});

byId("chat-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    byId("chat-form").requestSubmit();
  }
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    navigate("chat");
    sendChat(button.dataset.prompt);
  });
});

byId("clear-chat").addEventListener("click", () => {
  chatMessages.length = 0;
  const messages = byId("chat-messages");
  messages.replaceChildren();
  appendMessage("assistant", "A fresh start. What would you like to explore?");
});

byId("token-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const token = byId("api-token").value.trim();
  const feedback = byId("token-feedback");
  try {
    if (token) localStorage.setItem("homebrain-api-token", token);
    else localStorage.removeItem("homebrain-api-token");
    byId("api-token").value = "";
    feedback.textContent = token ? "Token saved in this browser." : "No token saved.";
    showToast(token ? "API token saved on this device." : "API token cleared.");
  } catch {
    feedback.textContent = "This browser could not save the token.";
    showToast("This browser could not save the token.", true);
  }
});

byId("clear-token").addEventListener("click", () => {
  try {
    localStorage.removeItem("homebrain-api-token");
    byId("token-feedback").textContent = "Saved token cleared.";
    showToast("API token cleared.");
  } catch {
    showToast("This browser could not clear the token.", true);
  }
});

window.addEventListener("hashchange", () => navigate(location.hash.slice(1), false));
const initialPage = location.hash.slice(1);
navigate(pages.includes(initialPage) ? initialPage : "dashboard", !pages.includes(initialPage));
refreshDashboard();
refreshTimer = window.setInterval(refreshDashboard, 20_000);
window.addEventListener("beforeunload", () => window.clearInterval(refreshTimer));
