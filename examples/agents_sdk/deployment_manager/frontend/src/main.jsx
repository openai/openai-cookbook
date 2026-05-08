import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AppWindow,
  Boxes,
  ChevronRight,
  Check,
  Copy,
  Download,
  ExternalLink,
  FileText,
  ListTree,
  Monitor,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Rocket,
  Sun,
  Trash2,
} from "lucide-react";
import openaiLogo from "./openai-logomark.svg";
import "./styles.css";

const views = ["apps", "traces", "logs", "system"];
const viewSet = new Set(views);
const viewIcons = {
  apps: Rocket,
  traces: Activity,
  logs: FileText,
  system: Boxes,
};
const appTabs = ["overview", "runs", "logs", "system"];
const traceRangeOptions = [
  { hours: "all", label: "All", param: "all" },
  { hours: 168, label: "7d", param: "7d" },
  { hours: 24, label: "1d", param: "1d" },
];
const sidebarCollapsedStorageKey = "deployment-manager.sidebar-collapsed";
const themePreferenceStorageKey = "deployment-manager.theme-preference";
const themePreferences = ["auto", "dark", "light"];
const detailPaneDefaultWidth = 460;
const detailPaneMinWidth = 320;
const detailPaneMaxWidth = 860;

function initialView() {
  return readUrlState().view;
}

function initialAppTab() {
  return readUrlState().appTab;
}

function normalizeView(view) {
  return viewSet.has(view) ? view : "apps";
}

function normalizeAppTab(tab) {
  if (tab === "traces" || tab === "runs") return "runs";
  return appTabs.includes(tab) ? tab : "list";
}

function tabUrlValue(tab) {
  return tab === "runs" ? "traces" : tab;
}

function rangeHoursFromParam(value) {
  const option = traceRangeOptions.find((item) => item.param === value);
  return option?.hours || 24;
}

function rangeParamFromHours(hours) {
  const option = traceRangeOptions.find((item) => item.hours === hours);
  return option?.param || "1d";
}

function readUrlState() {
  const url = new URL(window.location.href);
  const view = normalizeView(url.hash.replace("#", ""));
  const appId = url.searchParams.get("app_id") || "";
  const appTab = view === "apps" ? normalizeAppTab(url.searchParams.get("tab") || (appId ? "overview" : "")) : "list";
  return {
    view,
    appTab,
    appId,
    traceId: url.searchParams.get("trace_id") || "",
    sessionId: url.searchParams.get("session_id") || "",
    eventId: url.searchParams.get("event_id") || "",
    rangeHours: rangeHoursFromParam(url.searchParams.get("range") || "1d"),
  };
}

function writeUrlState(patch, { replace = false } = {}) {
  const url = new URL(window.location.href);
  if (patch.view) {
    url.hash = `#${normalizeView(patch.view)}`;
  }
  const paramPatch = {
    app_id: patch.appId,
    tab: Object.prototype.hasOwnProperty.call(patch, "appTab")
      ? patch.appTab
        ? tabUrlValue(patch.appTab)
        : null
      : patch.tab,
    trace_id: patch.traceId,
    session_id: patch.sessionId,
    event_id: patch.eventId,
    range: patch.rangeHours !== undefined ? rangeParamFromHours(patch.rangeHours) : patch.range,
  };
  for (const [key, value] of Object.entries(paramPatch)) {
    if (value === undefined) continue;
    if (value === null || value === "" || value === "list") {
      url.searchParams.delete(key);
    } else {
      url.searchParams.set(key, String(value));
    }
  }
  const nextUrl = `${url.pathname}${url.search}${url.hash}`;
  const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (nextUrl !== currentUrl) {
    window.history[replace ? "replaceState" : "pushState"](null, "", nextUrl);
  }
}

function initialSidebarCollapsed() {
  try {
    return window.localStorage.getItem(sidebarCollapsedStorageKey) === "true";
  } catch {
    return false;
  }
}

function initialThemePreference() {
  try {
    const stored = window.localStorage.getItem(themePreferenceStorageKey);
    return themePreferences.includes(stored) ? stored : "auto";
  } catch {
    return "auto";
  }
}

function systemTheme() {
  if (typeof window === "undefined" || !window.matchMedia) return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function resolveTheme(preference) {
  return preference === "auto" ? systemTheme() : preference;
}

function nextThemePreference(preference) {
  const currentIndex = themePreferences.indexOf(preference);
  return themePreferences[(currentIndex + 1) % themePreferences.length] || "auto";
}

async function writeClipboardText(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-1000px";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (copied) return true;

  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      return false;
    }
  }
  return false;
}

function sessionTraceId(session) {
  return session?.trace_id || session?.traceId || session?.metadata?.trace_id || session?.metadata?.traceId || "";
}

function findSessionByTraceId(sessions, traceId) {
  if (!traceId) return null;
  return sessions.find((session) => sessionTraceId(session) === traceId) || null;
}

function sessionUrlPatch(session) {
  if (!session) return { traceId: null, sessionId: null, eventId: null };
  const traceId = sessionTraceId(session);
  return {
    traceId: traceId || null,
    sessionId: traceId ? null : session.id || runId(session),
    eventId: null,
  };
}

function findSessionByUrlState(sessions, urlState) {
  if (urlState.traceId) {
    const session = findSessionByTraceId(sessions, urlState.traceId);
    if (session) return session;
  }
  if (!urlState.sessionId) return null;
  return sessions.find((session) => sessionMatchesId(session, urlState.sessionId)) || null;
}

function sessionMatchesId(session, value) {
  const id = String(value || "");
  if (!id) return false;
  return [session?.id, session?.expense_id, runId(session)].filter(Boolean).some((candidate) => String(candidate) === id);
}

function findDeploymentByAppId(deployments, appId) {
  if (!appId) return null;
  return deployments.find((item) => [item.id, item.name, item.project_id].filter(Boolean).includes(appId)) || null;
}

function findProjectByAppId(projects, appId) {
  if (!appId) return null;
  return projects.find((item) => [item.id, item.name].filter(Boolean).includes(appId)) || null;
}

function appIdForSelection(selected, row, fallbackDeployment, fallbackProject) {
  return selected?.deployment?.id
    || row?.deployment?.id
    || selected?.project?.id
    || row?.project?.id
    || fallbackDeployment?.id
    || fallbackProject?.id
    || "";
}

function eventUrlId(event, index) {
  return traceSpanId(event) || event?.id || eventKey(event, index);
}

function eventKeyFromUrlId(events, eventId) {
  if (!eventId) return null;
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    if ([eventUrlId(event, index), event?.id, traceSpanId(event)].filter(Boolean).includes(eventId)) {
      return eventKey(event, index);
    }
  }
  return null;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response.text();
}

function App() {
  const [project, setProject] = useState(null);
  const [projects, setProjects] = useState([]);
  const [deployment, setDeployment] = useState(null);
  const [deployments, setDeployments] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [selectedSessionId, setSelectedSessionId] = useState(null);
  const [timelineEvents, setTimelineEvents] = useState([]);
  const [containers, setContainers] = useState([]);
  const [containerCounts, setContainerCounts] = useState({});
  const [appDocs, setAppDocs] = useState(null);
  const [dockerfileText, setDockerfileText] = useState("");
  const [currentView, setCurrentView] = useState(initialView());
  const [currentAppTab, setCurrentAppTab] = useState(initialAppTab());
  const [runActivityRange, setRunActivityRange] = useState(() => readUrlState().rangeHours);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(initialSidebarCollapsed());
  const [themePreference, setThemePreference] = useState(initialThemePreference());
  const [resolvedTheme, setResolvedTheme] = useState(() => resolveTheme(initialThemePreference()));
  const [selectedEventKey, setSelectedEventKey] = useState(null);
  const [managerOnline, setManagerOnline] = useState(false);
  const [detailPaneWidth, setDetailPaneWidth] = useState(detailPaneDefaultWidth);
  const [detail, setDetail] = useState({ title: "App logs", text: "", format: "text" });
  const selectedSessionIdRef = useRef(null);
  const deploymentIdRef = useRef(null);
  const currentViewRef = useRef(currentView);
  const currentAppTabRef = useRef(currentAppTab);
  const detailPaneResizeRef = useRef(null);

  const deploymentSessions = useMemo(
    () => (deployment ? sessions.filter((session) => session.deployment_id === deployment.id) : sessions),
    [sessions, deployment?.id],
  );

  const visibleRunSessions = currentView === "traces" ? sessions : deploymentSessions;

  const selectedSession = useMemo(
    () => visibleRunSessions.find((session) => session.id === selectedSessionId) || visibleRunSessions[0] || null,
    [visibleRunSessions, selectedSessionId],
  );

  const runEvents = timelineEvents;

  const selectedEvent = useMemo(
    () => runEvents.find((event, index) => eventKey(event, index) === selectedEventKey) || runEvents[0] || null,
    [runEvents, selectedEventKey],
  );

  const agentRows = useMemo(
    () => buildAgentRows({ projects, deployments, sessions, containerCounts }),
    [projects, deployments, sessions, containerCounts],
  );

  useEffect(() => {
    const bodyView = currentView === "apps" && currentAppTab !== "list" ? `app-${currentAppTab}` : currentView;
    document.body.dataset.view = bodyView;
    document.body.dataset.appTab = currentAppTab;
    currentViewRef.current = currentView;
    currentAppTabRef.current = currentAppTab;
  }, [currentView, currentAppTab]);

  useEffect(() => {
    document.body.dataset.sidebar = sidebarCollapsed ? "collapsed" : "expanded";
    try {
      window.localStorage.setItem(sidebarCollapsedStorageKey, String(sidebarCollapsed));
    } catch {
      // Non-critical browser storage can fail in restricted contexts.
    }
  }, [sidebarCollapsed]);

  useEffect(() => {
    const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
    const applyTheme = () => {
      const nextTheme = themePreference === "auto" ? (media?.matches ? "dark" : "light") : themePreference;
      setResolvedTheme(nextTheme);
      document.documentElement.dataset.theme = nextTheme;
      document.documentElement.dataset.themePreference = themePreference;
      document.documentElement.style.colorScheme = nextTheme;
      document.body.dataset.theme = nextTheme;
      document.body.dataset.themePreference = themePreference;
    };
    applyTheme();
    try {
      window.localStorage.setItem(themePreferenceStorageKey, themePreference);
    } catch {
      // Non-critical browser storage can fail in restricted contexts.
    }
    if (themePreference !== "auto" || !media) return undefined;
    media.addEventListener?.("change", applyTheme);
    media.addListener?.(applyTheme);
    return () => {
      media.removeEventListener?.("change", applyTheme);
      media.removeListener?.(applyTheme);
    };
  }, [themePreference]);

  useEffect(() => () => document.body.classList.remove("resizing-detail-pane"), []);

  useEffect(() => {
    selectedSessionIdRef.current = selectedSessionId;
  }, [selectedSessionId]);

  useEffect(() => {
    deploymentIdRef.current = deployment?.id || null;
  }, [deployment?.id]);

  useEffect(() => {
    applyUrlState().catch((err) => showError("Startup error", err));
    const onUrlChange = () => {
      applyUrlState({ keepDetail: true }).catch((err) => showError("Navigation error", err));
    };
    window.addEventListener("popstate", onUrlChange);
    window.addEventListener("hashchange", onUrlChange);
    const timer = window.setInterval(() => {
      refreshAll({ keepDetail: true, urlState: readUrlState() }).catch(() => {});
    }, 4000);
    return () => {
      window.removeEventListener("popstate", onUrlChange);
      window.removeEventListener("hashchange", onUrlChange);
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (currentView === "apps" && ["overview", "system"].includes(currentAppTab)) {
      loadAppDocs().catch((err) => showError("App docs error", err));
    }
  }, [currentView, currentAppTab, project?.id]);

  useEffect(() => {
    if (currentView === "apps" && currentAppTab === "overview") {
      loadDockerfile().catch(() => {});
    }
  }, [currentView, currentAppTab, deployment?.id]);

  async function applyUrlState({ keepDetail = false } = {}) {
    const urlState = readUrlState();
    const nextView = urlState.view;
    const nextAppTab = nextView === "apps" ? urlState.appTab : "list";
    currentViewRef.current = nextView;
    currentAppTabRef.current = nextAppTab;
    setCurrentView(nextView);
    setCurrentAppTab(nextAppTab);
    setRunActivityRange(urlState.rangeHours);
    await refreshAll({ keepDetail, urlState });
  }

  async function refreshAll({ keepDetail = false, urlState = readUrlState() } = {}) {
    let latestDeployment = null;
    let latestProject = null;

    try {
      await api("/api/health");
      setManagerOnline(true);
    } catch {
      setManagerOnline(false);
    }

    const projectPayload = await api("/api/projects");
    setProjects(projectPayload.projects);

    const deploymentPayload = await api("/api/deployments");
    setDeployments(deploymentPayload.deployments);
    const containerCountEntries = await Promise.all(
      deploymentPayload.deployments.map(async (item) => {
        try {
          const payload = await api(`/api/deployments/${item.id}/containers`);
          return [item.id, payload.containers.filter((container) => container.role !== "orchestrator").length];
        } catch {
          return [item.id, null];
        }
      }),
    );
    setContainerCounts(Object.fromEntries(containerCountEntries));
    const urlDeployment = findDeploymentByAppId(deploymentPayload.deployments, urlState.appId);
    latestDeployment = urlState.appId
      ? urlDeployment
      : deploymentPayload.deployments.find((item) => item.id === deploymentIdRef.current)
        || deploymentPayload.deployments.at(-1)
        || null;
    if (latestDeployment) {
      const detailPayload = await api(`/api/deployments/${latestDeployment.id}`);
      latestDeployment = detailPayload.deployment;
      latestProject = detailPayload.project;
      deploymentIdRef.current = latestDeployment.id;
      setDeployment(latestDeployment);
      setProject(latestProject);
    } else {
      latestProject = findProjectByAppId(projectPayload.projects, urlState.appId) || projectPayload.projects[0] || null;
      deploymentIdRef.current = null;
      setDeployment(null);
      setProject(latestProject);
      setContainers([]);
    }

    if (latestDeployment) {
      const containerPayload = await api(`/api/deployments/${latestDeployment.id}/containers`);
      setContainers(containerPayload.containers);
    }

    const sessionsPayload = await api("/api/sessions");
    const nextSessions = sessionsPayload.sessions;
    setSessions(nextSessions);
    const wantsSpecificRun = Boolean(urlState.traceId || urlState.sessionId);
    const activeSessions = currentViewRef.current === "traces" || wantsSpecificRun
      ? nextSessions
      : latestDeployment
      ? nextSessions.filter((session) => session.deployment_id === latestDeployment.id)
      : nextSessions;
    const selectedByUrl = findSessionByUrlState(activeSessions, urlState);
    const nextSelected =
      selectedByUrl
      || activeSessions.find((session) => session.id === selectedSessionIdRef.current)
      || activeSessions[0]
      || null;
    updateSelectedSessionId(nextSelected?.id || null);
    if (nextSelected) {
      await loadTimeline(nextSelected, { eventId: urlState.eventId });
    } else {
      setTimelineEvents([]);
      setSelectedEventKey(null);
    }

    const showingLogs =
      currentViewRef.current === "logs"
      || (currentViewRef.current === "apps" && currentAppTabRef.current === "logs");
    if (showingLogs && !keepDetail) {
      await loadLogs(latestDeployment, latestProject);
    }
  }

  function updateSelectedSessionId(sessionId) {
    selectedSessionIdRef.current = sessionId;
    setSelectedSessionId(sessionId);
  }

  function showError(title, err) {
    setDetail({ title, text: err instanceof Error ? err.message : String(err), format: "text" });
  }

  function switchView(view, { appTab = "list", loadViewData = true, urlPatch = {}, replace = false } = {}) {
    const nextView = normalizeView(view);
    const nextAppTab = nextView === "apps" ? appTab : "list";
    const defaultRunPatch = nextView === "traces" && !urlPatch.traceId && !urlPatch.sessionId
      ? sessionUrlPatch(selectedSession)
      : {};
    currentViewRef.current = nextView;
    currentAppTabRef.current = nextAppTab;
    setCurrentView(nextView);
    setCurrentAppTab(nextAppTab);
    writeUrlState(
      {
        view: nextView,
        appTab: nextView === "apps" && nextAppTab !== "list" ? nextAppTab : null,
        ...(nextView === "apps" && nextAppTab === "list" ? { appId: null } : {}),
        ...(nextView === "apps" || nextView === "logs" ? {} : { appId: null }),
        ...(nextView === "traces" || (nextView === "apps" && nextAppTab === "runs")
          ? {}
          : { traceId: null, sessionId: null, eventId: null }),
        ...defaultRunPatch,
        ...urlPatch,
      },
      { replace },
    );
    if (loadViewData && nextView === "logs") {
      loadLogs().catch((err) => showError("Logs error", err));
    } else if (loadViewData && nextView === "apps" && nextAppTab === "logs") {
      loadLogs().catch((err) => showError("Logs error", err));
    } else if (loadViewData && nextView === "traces" && selectedSession) {
      loadTimeline(selectedSession).catch((err) => showError("Trace error", err));
    }
  }

  async function switchAppTab(tab) {
    if (!appTabs.includes(tab)) return;
    switchView("apps", {
      appTab: tab,
      loadViewData: false,
      urlPatch: {
        appId: deployment?.id || project?.id || "",
        ...(tab === "runs" ? sessionUrlPatch(selectedSession) : { traceId: null, sessionId: null, eventId: null }),
      },
    });
    if (tab === "logs") {
      await loadLogs();
    } else if (tab === "overview" || tab === "system") {
      await loadAppDocs();
      if (tab === "overview") {
        await loadDockerfile();
      }
    } else if (tab === "runs" && selectedSession) {
      await loadTimeline(selectedSession);
    }
  }

  async function selectDeploymentRow(row) {
    if (!row.deployment) {
      deploymentIdRef.current = null;
      setDeployment(null);
      setProject(row.project || null);
      setContainers([]);
      setDetail({ title: row.name, text: JSON.stringify(row.project || row, null, 2), format: "json" });
      return { deployment: null, project: row.project || null };
    }
    const detailPayload = await api(`/api/deployments/${row.deployment.id}`);
    deploymentIdRef.current = detailPayload.deployment.id;
    setDeployment(detailPayload.deployment);
    setProject(detailPayload.project);
    setDetail({
      title: displayDeploymentName(detailPayload.deployment, detailPayload.project),
      text: JSON.stringify(
        {
          deployment: detailPayload.deployment,
          project: detailPayload.project,
        },
        null,
        2,
      ),
      format: "json",
    });
    const containerPayload = await api(`/api/deployments/${row.deployment.id}/containers`);
    setContainers(containerPayload.containers);
    return detailPayload;
  }

  async function openRuns(row = null) {
    const selected = row ? await selectDeploymentRow(row) : { deployment, project };
    const activeDeploymentId = row
      ? selected?.deployment?.id || row?.deployment?.id || null
      : deployment?.id;
    const activeSessions = activeDeploymentId
      ? sessions.filter((session) => session.deployment_id === activeDeploymentId)
      : row
        ? []
        : sessions;
    const nextSession = row?.latestSession || activeSessions[0] || null;
    updateSelectedSessionId(nextSession?.id || null);
    setSelectedEventKey(null);
    if (nextSession) {
      await loadTimeline(nextSession);
    } else {
      setTimelineEvents([]);
    }
    switchView("apps", {
      appTab: "runs",
      urlPatch: {
        appId: appIdForSelection(selected, row, deployment, project),
        ...sessionUrlPatch(nextSession),
      },
    });
  }

  async function openLogs(row = null) {
    const selected = row ? await selectDeploymentRow(row) : { deployment, project };
    const activeDeployment = row ? selected?.deployment || row?.deployment || null : deployment;
    const activeProject = row ? selected?.project || row?.project || null : project;
    await loadLogs(activeDeployment, activeProject);
    switchView("apps", {
      appTab: "logs",
      loadViewData: false,
      urlPatch: {
        appId: appIdForSelection(selected, row, deployment, project),
        traceId: null,
        sessionId: null,
        eventId: null,
      },
    });
  }

  async function selectLogsApp(rowId) {
    const row = agentRows.find((item) => item.id === rowId);
    if (!row) return;
    const selected = await selectDeploymentRow(row);
    await loadLogs(selected?.deployment || row.deployment || null, selected?.project || row.project || null);
    writeUrlState({
      view: "logs",
      appId: appIdForSelection(selected, row, deployment, project),
      traceId: null,
      sessionId: null,
      eventId: null,
    });
  }

  async function openSystem(row = null) {
    const selected = row ? await selectDeploymentRow(row) : { deployment, project };
    await loadAppDocs(selected?.project || row?.project || project);
    switchView(row ? "apps" : "system", {
      appTab: row ? "system" : "list",
      urlPatch: row
        ? {
            appId: appIdForSelection(selected, row, deployment, project),
            traceId: null,
            sessionId: null,
            eventId: null,
          }
        : { traceId: null, sessionId: null, eventId: null },
    });
  }

  async function openOverview(row = null) {
    const selected = row ? await selectDeploymentRow(row) : { deployment, project };
    await loadAppDocs(selected?.project || row?.project || project);
    await loadDockerfile(selected?.deployment || row?.deployment || deployment);
    switchView("apps", {
      appTab: "overview",
      urlPatch: {
        appId: appIdForSelection(selected, row, deployment, project),
        traceId: null,
        sessionId: null,
        eventId: null,
      },
    });
  }

  async function removeDeployment(row) {
    if (!row?.deployment) return;
    const confirmed = window.confirm(
      `Remove app ${row.name}? This stops the app and deletes its local manager state.`,
    );
    if (!confirmed) return;
    await api(`/api/deployments/${row.deployment.id}`, { method: "DELETE" });
    if (deploymentIdRef.current === row.deployment.id) {
      deploymentIdRef.current = null;
      setDeployment(null);
      setProject(null);
      updateSelectedSessionId(null);
      setTimelineEvents([]);
      setContainers([]);
    }
    await refreshAll();
    switchView("apps");
  }

  async function openRunSession(session) {
    if (!session) return;
    updateSelectedSessionId(session.id);
    setSelectedEventKey(null);
    await loadTimeline(session);
    switchView("traces", { urlPatch: sessionUrlPatch(session) });
  }

  async function loadAppDocs(activeProject = project) {
    if (!activeProject?.id) {
      setAppDocs(null);
      return;
    }
    const docs = await api(`/api/projects/${activeProject.id}/docs`);
    setAppDocs(docs);
  }

  async function loadDockerfile(activeDeployment = deployment) {
    if (!activeDeployment?.id) {
      setDockerfileText("");
      return;
    }
    try {
      const dockerfile = await api(`/api/deployments/${activeDeployment.id}/dockerfile`);
      setDockerfileText(dockerfile || "Dockerfile is empty.");
    } catch (err) {
      setDockerfileText(`Unable to load Dockerfile: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  async function loadTimeline(session, { eventId = "" } = {}) {
    const activeSession = session || selectedSession;
    if (!activeSession) return;
    if (deployment?.id !== activeSession.deployment_id) {
      const detailPayload = await api(`/api/deployments/${activeSession.deployment_id}`);
      setDeployment(detailPayload.deployment);
      setProject(detailPayload.project);
      deploymentIdRef.current = detailPayload.deployment.id;
    }
    const timeline = await api(`/api/sessions/${activeSession.deployment_id}/${activeSession.expense_id}/timeline`);
    setTimelineEvents(timeline.events);
    setSelectedEventKey(eventKeyFromUrlId(timeline.events, eventId));
  }

  async function selectSession(sessionId) {
    const session = sessions.find((item) => item.id === sessionId);
    updateSelectedSessionId(sessionId);
    setSelectedEventKey(null);
    if (session) {
      await loadTimeline(session);
      writeUrlState({
        view: currentViewRef.current,
        appTab: currentViewRef.current === "apps" ? currentAppTabRef.current : null,
        ...sessionUrlPatch(session),
      });
    }
  }

  function selectTimelineEvent(event, index) {
    const key = eventKey(event, index);
    setSelectedEventKey(key);
    writeUrlState({ eventId: eventUrlId(event, index) });
  }

  function selectRunActivityRange(hours) {
    setRunActivityRange(hours);
    writeUrlState({ view: "apps", rangeHours: hours });
  }

  async function loadLogs(activeDeployment = deployment, activeProject = project) {
    if (!activeDeployment) {
      setDetail({
        title: "App logs",
        text: activeProject
          ? "This app is imported but is not currently managed as a deployment, so deployment logs are unavailable."
          : "Select an app to inspect deployment logs.",
        format: "text",
      });
      return;
    }
    const logs = await api(`/api/deployments/${activeDeployment.id}/logs`);
    setDetail({ title: "App logs", text: logs || "No logs yet.", format: "text" });
  }

  function clampDetailPaneWidth(width, maxWidth = detailPaneMaxWidth) {
    return Math.max(detailPaneMinWidth, Math.min(maxWidth, Math.round(width)));
  }

  function startDetailPaneResize(event) {
    const workspace = event.currentTarget.closest(".workspace");
    const workspaceWidth = workspace?.getBoundingClientRect().width || 0;
    const maxWidth = workspaceWidth
      ? Math.max(detailPaneMinWidth, Math.min(detailPaneMaxWidth, workspaceWidth - 520))
      : detailPaneMaxWidth;
    detailPaneResizeRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startWidth: detailPaneWidth,
      maxWidth,
    };
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    document.body.classList.add("resizing-detail-pane");
  }

  function moveDetailPaneResize(event) {
    const drag = detailPaneResizeRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    setDetailPaneWidth(clampDetailPaneWidth(drag.startWidth - (event.clientX - drag.startX), drag.maxWidth));
  }

  function endDetailPaneResize(event) {
    const drag = detailPaneResizeRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    detailPaneResizeRef.current = null;
    document.body.classList.remove("resizing-detail-pane");
  }

  function handleDetailPaneResizeKey(event) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const step = event.shiftKey ? 48 : 24;
    setDetailPaneWidth((width) => {
      if (event.key === "Home") return detailPaneDefaultWidth;
      if (event.key === "End") return detailPaneMaxWidth;
      return clampDetailPaneWidth(width + (event.key === "ArrowLeft" ? step : -step));
    });
  }

  const isAppDetail = currentView === "apps" && currentAppTab !== "list";
  const hasResizableDetailPane = currentView === "traces" || (currentView === "apps" && currentAppTab === "runs");
  const workspaceStyle = hasResizableDetailPane ? { "--detail-pane-width": `${detailPaneWidth}px` } : undefined;
  const detailResizeHandleProps = hasResizableDetailPane
    ? {
        onPointerDown: startDetailPaneResize,
        onPointerMove: moveDetailPaneResize,
        onPointerUp: endDetailPaneResize,
        onPointerCancel: endDetailPaneResize,
        onKeyDown: handleDetailPaneResizeKey,
        onDoubleClick: () => setDetailPaneWidth(detailPaneDefaultWidth),
        "aria-valuenow": Math.round(detailPaneWidth),
      }
    : null;
  const pageMeta = currentView === "apps"
    ? `${agentRows.length} apps / ${deployments.length} deployments / local manager`
    : currentView === "traces"
      ? `${sessions.length} runs / ${sessions.filter((session) => session.trace_id).length} traced`
      : currentView === "logs"
        ? deployment
          ? `${displayDeploymentName(deployment, project)} / ${deployment.id}`
          : "Select an app to inspect logs"
      : `${deployments.length} deployments / ${Object.values(containerCounts).filter((count) => count !== null).reduce((sum, count) => sum + count, 0)} containers`;
  const pageTitle = currentView === "apps"
    ? "Apps"
    : currentView === "traces"
      ? "Traces"
      : currentView === "logs"
        ? "Logs"
      : "System";
  const runtimeUrl = deployment?.app_url || project?.app_url;

  return (
    <div className={`shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <img src={openaiLogo} alt="" />
            <h1>
              Agents Deployment <span>Manager</span>
            </h1>
          </div>
          <button
            type="button"
            className="sidebar-toggle"
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!sidebarCollapsed}
            title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
          >
            {sidebarCollapsed ? (
              <PanelLeftOpen aria-hidden="true" size={21} strokeWidth={1.8} />
            ) : (
              <PanelLeftClose aria-hidden="true" size={21} strokeWidth={1.8} />
            )}
          </button>
        </div>
        <nav aria-label="Agent app manager views">
          {views.map((view) => (
            <NavItem key={view} view={view} active={view === currentView} onClick={() => switchView(view)} />
          ))}
        </nav>
        <div className="sidebar-footer" title={managerOnline ? "Manager online" : "Manager offline"}>
          <span className={`dot ${managerOnline ? "ok" : ""}`} />
          <span>{managerOnline ? "Manager online" : "Manager offline"}</span>
        </div>
      </aside>

      <main className="workspace" style={workspaceStyle}>
        <header className="topbar">
          <div>
            <h2>{pageTitle}</h2>
            <p className="crumb">{pageMeta}</p>
          </div>
          <div className="actions">
            <ThemeToggle
              preference={themePreference}
              resolvedTheme={resolvedTheme}
              onToggle={() => setThemePreference((preference) => nextThemePreference(preference))}
            />
          </div>
        </header>

        {currentView === "apps" && (
          <>
            <AgentsList
              rows={agentRows}
              selectedDeployment={isAppDetail ? deployment : null}
              selectedProject={isAppDetail ? project : null}
              activeTab={isAppDetail ? currentAppTab : "list"}
              onOpenOverview={(row) => {
                openOverview(row).catch((err) => showError("Overview error", err));
              }}
              onOpenRuns={(row) => {
                openRuns(row).catch((err) => showError("Runs error", err));
              }}
              onOpenLogs={(row) => {
                openLogs(row).catch((err) => showError("Logs error", err));
              }}
              onOpenSystem={(row) => {
                openSystem(row).catch((err) => showError("System error", err));
              }}
              onRemoveDeployment={(row) => {
                removeDeployment(row).catch((err) => showError("Remove error", err));
              }}
            />

            {isAppDetail ? (
              <>
                {currentAppTab === "overview" && (
                  <AppOverviewPanel
                    project={project}
                    deployment={deployment}
                    docs={appDocs}
                    dockerfile={dockerfileText}
                    sessions={deploymentSessions}
                    onOpenRun={(session) => openRunSession(session).catch((err) => showError("Run error", err))}
                  />
                )}

                {currentAppTab === "runs" && (
                  <>
                    <RunsPanel
                      selectedSession={selectedSession}
                      sessions={deploymentSessions}
                      events={runEvents}
                      allEvents={timelineEvents}
                      selectedEvent={selectedEvent}
                      onSelectEvent={selectTimelineEvent}
                      onSelectSession={(sessionId) => selectSession(sessionId).catch((err) => showError("Run error", err))}
                    />
                    <EventDetailPane event={selectedEvent} resizeHandleProps={detailResizeHandleProps} />
                  </>
                )}

                {currentAppTab === "logs" && (
                  <AppLogsPanel
                    detail={detail}
                    deployment={deployment}
                    project={project}
                    onRefresh={() => loadLogs().catch((err) => showError("Logs error", err))}
                  />
                )}

                {currentAppTab === "system" && (
                  <SystemPanel
                    project={project}
                    deployment={deployment}
                    containers={containers}
                    runtimeUrl={runtimeUrl}
                    managerOnline={managerOnline}
                  />
                )}
              </>
            ) : (
              <RecentRunsSummary
                appRows={agentRows}
                sessions={sessions}
                rangeHours={runActivityRange}
                onRangeChange={selectRunActivityRange}
                onOpenRun={(session) => openRunSession(session).catch((err) => showError("Run error", err))}
              />
            )}
          </>
        )}

        {currentView === "traces" && (
          <>
            <RunsPanel
              eyebrow="Traces"
              selectedSession={selectedSession}
              sessions={sessions}
              events={runEvents}
              allEvents={timelineEvents}
              selectedEvent={selectedEvent}
              onSelectEvent={selectTimelineEvent}
              onSelectSession={(sessionId) => selectSession(sessionId).catch((err) => showError("Run error", err))}
            />
            <EventDetailPane event={selectedEvent} resizeHandleProps={detailResizeHandleProps} />
          </>
        )}

        {currentView === "logs" && (
          <AppLogsPanel
            detail={detail}
            deployment={deployment}
            project={project}
            appRows={agentRows}
            selectedAppId={selectedAppRowId(agentRows, deployment, project)}
            onSelectApp={(rowId) => selectLogsApp(rowId).catch((err) => showError("Logs app error", err))}
            onRefresh={() => loadLogs().catch((err) => showError("Logs error", err))}
          />
        )}

        {currentView === "system" && (
          <ManagerSystemPanel
            managerOnline={managerOnline}
            projects={projects}
            deployments={deployments}
            sessions={sessions}
            containerCounts={containerCounts}
          />
        )}
      </main>
    </div>
  );
}

function ThemeToggle({ preference, resolvedTheme, onToggle }) {
  const Icon = preference === "auto" ? Monitor : resolvedTheme === "dark" ? Moon : Sun;
  const visibleLabel = preference === "auto" ? "Auto" : preference === "dark" ? "Dark" : "Light";
  const label = preference === "auto" ? `Auto theme (${resolvedTheme})` : `${visibleLabel} theme`;
  return (
    <button type="button" className="theme-toggle" title={label} aria-label={`${label}. Click to change theme.`} onClick={onToggle}>
      <Icon aria-hidden="true" size={18} strokeWidth={1.8} />
      <span>{visibleLabel}</span>
    </button>
  );
}

function NavItem({ view, active, onClick }) {
  const Icon = viewIcons[view] || FileText;
  return (
    <button
      type="button"
      className={`nav-item ${active ? "active" : ""}`}
      aria-current={active ? "page" : undefined}
      title={viewLabel(view)}
      onClick={onClick}
    >
      <Icon aria-hidden="true" size={20} strokeWidth={1.7} />
      <span>{viewLabel(view)}</span>
    </button>
  );
}

function viewLabel(view) {
  const labels = {
    apps: "Apps",
    traces: "Traces",
    logs: "Logs",
    system: "System",
  };
  return labels[view] || titleCase(view);
}

function navigateToRuntime(event, url) {
  event.preventDefault();
  event.stopPropagation();
  window.location.assign(url);
}

function openExternalUrl(event, url) {
  event.preventDefault();
  event.stopPropagation();
  window.open(url, "_blank", "noopener,noreferrer");
}

function exportRunTraceJson(selectedSession, events) {
  if (!selectedSession) return;
  const traceId = findTraceId(selectedSession, events);
  const traceEvents = traceEventsForExport(selectedSession, events);
  const spans = traceEvents
    .map((event) => traceEventToSpan(event, traceId))
    .sort(compareTraceSpans);
  const payload = {
    object: "run_trace_export",
    exported_at: new Date().toISOString(),
    trace_id: traceId || null,
    run: {
      id: selectedSession.id,
      run_id: runId(selectedSession),
      deployment_id: selectedSession.deployment_id,
      deployment_name: selectedSession.deployment_name,
      project_id: selectedSession.project_id,
      project_name: selectedSession.project_name,
      status: selectedSession.status,
      started_at: selectedSession.started_at,
      updated_at: selectedSession.updated_at,
      trace_id: selectedSession.trace_id || traceId || null,
      trace_url: selectedSession.trace_url || null,
    },
    span_count: spans.length,
    spans,
  };
  const appName = selectedSession.deployment_name || selectedSession.project_name || "run";
  downloadJsonFile(`${safeFilenamePart(appName)}-${safeFilenamePart(runId(selectedSession))}-trace.json`, payload);
}

function downloadJsonFile(fileName, payload) {
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function traceEventsForExport(selectedSession, events) {
  const traceId = findTraceId(selectedSession, events);
  return events.filter((event) => {
    const eventTraceId = event.trace_id || event.traceId || event.metadata?.trace_id || event.metadata?.traceId;
    const spanId = event.span_id || event.spanId || event.metadata?.span_id || event.metadata?.spanId || event.id;
    if (traceId) return eventTraceId === traceId;
    return Boolean(eventTraceId || String(spanId || "").startsWith("span_"));
  });
}

function traceEventToSpan(event, traceId) {
  const metadata = event.metadata || {};
  return {
    id: metadata.span_id || event.span_id || event.id || null,
    trace_id: metadata.trace_id || event.trace_id || traceId || null,
    parent_id: metadata.parent_id || event.parent_id || null,
    started_at: metadata.started_at || event.timestamp || null,
    ended_at: metadata.ended_at || null,
    duration_ms: metadata.duration_ms ?? null,
    span_data: metadata.span_data || null,
    source: event.source || null,
    type: event.type || null,
    message: event.message || null,
    level: event.level || null,
  };
}

function compareTraceSpans(left, right) {
  const leftTime = Date.parse(left.started_at || "");
  const rightTime = Date.parse(right.started_at || "");
  if (!Number.isNaN(leftTime) && !Number.isNaN(rightTime) && leftTime !== rightTime) {
    return leftTime - rightTime;
  }
  return String(left.id || "").localeCompare(String(right.id || ""));
}

function safeFilenamePart(value) {
  return String(value || "trace")
    .trim()
    .replace(/[^a-z0-9._-]+/gi, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || "trace";
}

function AppOverviewPanel({ project, deployment, docs, dockerfile, sessions, onOpenRun }) {
  const title = displayDeploymentName(deployment, project) || project?.name || "No app selected";
  const latestRun = sessions[0] || null;
  return (
    <section className="app-detail app-overview primary-section">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Overview</p>
          <h3>{title}</h3>
        </div>
      </div>
      <div className="app-summary">
        <div>
          <span>Status</span>
          <strong>{deployment?.status || "not deployed"}</strong>
        </div>
        <div>
          <span>Latest run</span>
          <strong>{latestRun ? `Run ID ${runId(latestRun)}` : "No runs"}</strong>
        </div>
        <div>
          <span>Runtime</span>
          <strong>{deployment ? `${deployment.target} · ${deployment.sandbox_backend}` : "-"}</strong>
        </div>
      </div>
      {latestRun && (
        <section className="overview-callout">
          <div>
            <p className="eyebrow">Latest run</p>
            <h3>{latestRun.status} · {latestRun.event_count} events</h3>
          </div>
          <button type="button" className="ghost" onClick={() => onOpenRun(latestRun)}>
            Open run
          </button>
        </section>
      )}
      <div className="app-doc-images">
        <DocImage title="Agent interactions" src={docs?.agent_interactions_url} />
        <DocImage title="Agent sequence" src={docs?.agent_sequence_url} />
      </div>
      <section className="prompt-doc">
        <div className="prompt-head">
          <p className="eyebrow">Prompt</p>
          <h3>{docs?.prompt_path || "docs/prompt.md"}</h3>
        </div>
        <MarkdownView className="markdown-body prompt-content" text={docs?.prompt || "No docs/prompt.md found for this app."} />
      </section>
      <section className="prompt-doc dockerfile-doc">
        <div className="prompt-head">
          <p className="eyebrow">Dockerfile</p>
          <h3>{deployment?.dockerfile_path || "Dockerfile"}</h3>
        </div>
        <pre className="logs dockerfile-content">{dockerfile || "No Dockerfile loaded for this app."}</pre>
      </section>
    </section>
  );
}

function AppLogsPanel({ detail, deployment, project, appRows = [], selectedAppId = "", onSelectApp, onRefresh }) {
  const logDetail = detail.title === "App logs" ? detail : { title: "App logs", text: "No logs loaded yet.", format: "text" };
  const title = displayDeploymentName(deployment, project) || project?.name;
  const canSelectApp = Boolean(onSelectApp && appRows.length);
  return (
    <section className="pane app-logs-panel primary-section">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Logs</p>
          {canSelectApp ? (
            <select
              className="app-title-select"
              aria-label="App logs"
              value={selectedAppId}
              onChange={(event) => onSelectApp(event.target.value)}
            >
              {appRows.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name} logs
                </option>
              ))}
            </select>
          ) : (
            <h3>{title ? `${title} logs` : "No app selected"}</h3>
          )}
        </div>
        <div className="logs-actions">
          <button type="button" className="ghost" onClick={onRefresh} disabled={!deployment}>
            Refresh logs
          </button>
        </div>
      </div>
      <DetailContent detail={logDetail} />
    </section>
  );
}

function SystemPanel({ project, deployment, containers, runtimeUrl, managerOnline }) {
  const title = displayDeploymentName(deployment, project) || project?.name || "No app selected";
  return (
    <section className="app-detail system-panel primary-section">
      <div className="panel-head">
        <div>
          <p className="eyebrow">System</p>
          <h3>{title}</h3>
        </div>
      </div>
      <section className="system-section">
        <div className="diagnostics-head">
          <div>
            <p className="eyebrow">Runtime</p>
            <h3>Local app runtime</h3>
          </div>
        </div>
        <div className="app-summary">
          <div>
            <span>Status</span>
            <strong>{deployment?.status || "-"}</strong>
          </div>
          <div>
            <span>Process</span>
            <strong>{deployment?.process_pid ? `pid ${deployment.process_pid}` : "-"}</strong>
          </div>
          <div>
            <span>Target</span>
            <strong>{deployment?.target || "-"}</strong>
          </div>
          <div>
            <span>URL</span>
            <strong>{runtimeUrl || "-"}</strong>
          </div>
        </div>
      </section>
      <section className="system-section">
        <div className="diagnostics-head">
          <div>
            <p className="eyebrow">Build</p>
            <h3>Entrypoints and sandbox</h3>
          </div>
        </div>
        <div className="app-summary">
          <div>
            <span>Project</span>
            <strong>{project?.name || "-"}</strong>
          </div>
          <div>
            <span>Orchestrator</span>
            <strong>{project?.orchestrator_entrypoint || "-"}</strong>
          </div>
          <div>
            <span>Executor</span>
            <strong>{project?.executor_entrypoint || "-"}</strong>
          </div>
          <div>
            <span>Sandbox</span>
            <strong>{deployment?.sandbox_backend || "-"}</strong>
          </div>
        </div>
      </section>
      <section className="system-section">
        <div className="diagnostics-head">
          <div>
            <p className="eyebrow">Health</p>
            <h3>Reachability</h3>
          </div>
        </div>
        <div className="app-summary">
          <div>
            <span>Manager</span>
            <strong>{managerOnline ? "online" : "offline"}</strong>
          </div>
          <div>
            <span>App</span>
            <strong>{deployment?.status === "running" ? "running" : deployment?.status || "-"}</strong>
          </div>
          <div>
            <span>Containers</span>
            <strong>{containers.length}</strong>
          </div>
          <div>
            <span>Project path</span>
            <strong>{project?.path || "-"}</strong>
          </div>
        </div>
      </section>
      <section className="system-section">
        <div className="diagnostics-head">
          <div>
            <p className="eyebrow">Containers</p>
            <h3>Observed Docker containers</h3>
          </div>
          <span className="panel-count">{containers.length} total</span>
        </div>
        <ContainerList containers={containers} appName={title} />
      </section>
    </section>
  );
}

function ManagerSystemPanel({ managerOnline, projects, deployments, sessions, containerCounts }) {
  const observedContainers = Object.values(containerCounts)
    .filter((count) => typeof count === "number")
    .reduce((sum, count) => sum + count, 0);
  return (
    <section className="app-detail system-panel primary-section">
      <div className="panel-head">
        <div>
          <p className="eyebrow">System</p>
          <h3>Local manager</h3>
        </div>
      </div>
      <div className="app-summary">
        <div>
          <span>Manager</span>
          <strong>{managerOnline ? "online" : "offline"}</strong>
        </div>
        <div>
          <span>Apps</span>
          <strong>{projects.length}</strong>
        </div>
        <div>
          <span>Active apps</span>
          <strong>{deployments.length}</strong>
        </div>
        <div>
          <span>Runs</span>
          <strong>{sessions.length}</strong>
        </div>
      </div>
      <section className="system-section">
        <div className="diagnostics-head">
          <div>
            <p className="eyebrow">Runtime</p>
            <h3>Local environment</h3>
          </div>
        </div>
        <div className="app-summary">
          <div>
            <span>Running apps</span>
            <strong>{deployments.filter((item) => item.status === "running").length}</strong>
          </div>
          <div>
            <span>Observed containers</span>
            <strong>{observedContainers}</strong>
          </div>
          <div>
            <span>Sandbox backends</span>
            <strong>{[...new Set(deployments.map((item) => item.sandbox_backend).filter(Boolean))].join(", ") || "-"}</strong>
          </div>
          <div>
            <span>Target</span>
            <strong>{[...new Set(deployments.map((item) => item.target).filter(Boolean))].join(", ") || "-"}</strong>
          </div>
        </div>
      </section>
      <section className="system-section">
        <div className="diagnostics-head">
          <div>
            <p className="eyebrow">Apps</p>
            <h3>Registered local apps</h3>
          </div>
        </div>
        <div className="system-app-list">
          {deployments.map((item) => (
            <div key={item.id}>
              <strong>{item.name}</strong>
              <span>{item.status} · {item.app_url || "no app url"}</span>
            </div>
          ))}
        </div>
      </section>
    </section>
  );
}

function DetailContent({ detail }) {
  if (detail.format === "json") {
    const parsed = parseJson(detail.text);
    if (isTimelineEvent(parsed)) {
      return <EventDetailContent event={parsed} />;
    }
    return <JsonView text={detail.text} />;
  }
  if (detail.format === "markdown") {
    return <MarkdownView className="markdown-body detail-content" text={detail.text} />;
  }
  return <pre className="logs">{detail.text}</pre>;
}

function EventDetailContent({ event }) {
  const [copied, setCopied] = useState(false);
  const stats = [
    ["Source", traceLabel(event.source)],
    ["Type", event.type || "-"],
    ["Time", formatTraceTime(event.timestamp) || "-"],
    ["Status", event.level === "error" ? "Error" : "Complete"],
  ];
  const summary = event.message || event.summary || event.error || "No summary recorded for this event.";
  const rawEventJson = JSON.stringify(event, null, 2);

  async function copyRawEvent() {
    const didCopy = await writeClipboardText(rawEventJson);
    if (!didCopy) return;
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  return (
    <div className="event-detail-content">
      <div className="event-detail-stats">
        {stats.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            {label === "Status" ? <strong className={`status-badge ${value.toLowerCase()}`}>{value}</strong> : <strong>{value}</strong>}
          </div>
        ))}
      </div>
      <section className="event-detail-summary">
        <span>Summary</span>
        <p>{summary}</p>
      </section>
      <section className="event-detail-accordion">
        <header>
          <span>Raw event</span>
          <button type="button" className="copy-button" onClick={copyRawEvent} aria-label="Copy raw event JSON">
            {copied ? <Check aria-hidden="true" size={14} strokeWidth={2} /> : <Copy aria-hidden="true" size={14} strokeWidth={2} />}
            <span>{copied ? "Copied" : "Copy"}</span>
          </button>
        </header>
        <div className="json-view" role="region" aria-label="Raw event JSON">
          <JsonNode value={event} />
        </div>
      </section>
    </div>
  );
}

function JsonView({ text }) {
  const parsed = parseJson(text);
  if (parsed === null) {
    return <pre className="logs">{text}</pre>;
  }
  return (
    <div className="json-view" role="region" aria-label="JSON detail">
      <JsonNode value={parsed} />
    </div>
  );
}

function JsonNode({ value }) {
  if (Array.isArray(value)) {
    if (!value.length) return <span className="json-token muted">[]</span>;
    return (
      <span className="json-node">
        <span className="json-token punctuation">[</span>
        <span className="json-children">
          {value.map((item, index) => (
            <span key={index} className="json-row">
              <JsonNode value={item} />
              {index < value.length - 1 && <span className="json-token punctuation">,</span>}
            </span>
          ))}
        </span>
        <span className="json-token punctuation">]</span>
      </span>
    );
  }

  if (value && typeof value === "object") {
    const entries = Object.entries(value);
    if (!entries.length) return <span className="json-token muted">{"{}"}</span>;
    return (
      <span className="json-node">
        <span className="json-token punctuation">{"{"}</span>
        <span className="json-children">
          {entries.map(([key, item], index) => (
            <span key={key} className="json-row">
              <span className="json-key">"{key}"</span>
              <span className="json-token punctuation">: </span>
              <JsonNode value={item} />
              {index < entries.length - 1 && <span className="json-token punctuation">,</span>}
            </span>
          ))}
        </span>
        <span className="json-token punctuation">{"}"}</span>
      </span>
    );
  }

  if (typeof value === "string") return <span className="json-string">"{value}"</span>;
  if (typeof value === "number") return <span className="json-number">{value}</span>;
  if (typeof value === "boolean") return <span className="json-boolean">{String(value)}</span>;
  return <span className="json-token muted">null</span>;
}

function MarkdownView({ text, className }) {
  const blocks = parseMarkdownBlocks(text);
  return (
    <div className={className}>
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          const Heading = `h${block.level}`;
          return <Heading key={index}>{renderInlineMarkdown(block.text)}</Heading>;
        }
        if (block.type === "list") {
          return (
            <ul key={index}>
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>{renderInlineMarkdown(item)}</li>
              ))}
            </ul>
          );
        }
        if (block.type === "code") {
          return (
            <pre key={index}>
              <code>{block.text}</code>
            </pre>
          );
        }
        if (block.type === "paragraph") {
          return <p key={index}>{renderInlineMarkdown(block.text)}</p>;
        }
        return <div key={index} className="markdown-spacer" />;
      })}
    </div>
  );
}

function parseMarkdownBlocks(text) {
  const lines = String(text || "").split(/\r?\n/);
  const blocks = [];
  let paragraph = [];
  let list = [];
  let code = [];
  let inCode = false;

  function flushParagraph() {
    if (paragraph.length) {
      blocks.push({ type: "paragraph", text: paragraph.join(" ") });
      paragraph = [];
    }
  }

  function flushList() {
    if (list.length) {
      blocks.push({ type: "list", items: list });
      list = [];
    }
  }

  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      if (inCode) {
        blocks.push({ type: "code", text: code.join("\n") });
        code = [];
        inCode = false;
      } else {
        flushParagraph();
        flushList();
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      code.push(line);
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      flushList();
      blocks.push({ type: "space" });
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ type: "heading", level: heading[1].length, text: heading[2] });
      continue;
    }

    const listItem = /^\s*(?:[-*]|\d+\.)\s+(.+)$/.exec(line);
    if (listItem) {
      flushParagraph();
      list.push(listItem[1]);
      continue;
    }

    flushList();
    paragraph.push(line.trim());
  }

  flushParagraph();
  flushList();
  if (inCode && code.length) {
    blocks.push({ type: "code", text: code.join("\n") });
  }
  return blocks.filter((block, index, items) => block.type !== "space" || items[index - 1]?.type !== "space");
}

function renderInlineMarkdown(text) {
  return String(text)
    .split(/(`[^`]+`)/g)
    .map((part, index) => {
      if (part.startsWith("`") && part.endsWith("`")) {
        return <code key={index}>{part.slice(1, -1)}</code>;
      }
      return part;
    });
}

function parseJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function DocImage({ title, src }) {
  return (
    <figure className="doc-image">
      <figcaption>{title}</figcaption>
      {src ? (
        <a href={src} target="_blank" rel="noreferrer" title={`Open ${title}`}>
          <img src={src} alt={title} />
        </a>
      ) : (
        <div>No image found</div>
      )}
    </figure>
  );
}

function AgentsList({
  rows,
  selectedDeployment,
  selectedProject,
  activeTab,
  onOpenOverview,
  onOpenRuns,
  onOpenLogs,
  onOpenSystem,
  onRemoveDeployment,
}) {
  return (
    <section className="agents-panel primary-section">
      <div className="panel-head agents-panel-head">
        <span className="panel-count">{rows.length} total</span>
      </div>
      <div className={`agent-list ${rows.length ? "" : "empty"}`} role="table" aria-label="Local apps">
        {rows.length ? (
          <>
            <div className="agent-table-head" role="row">
              <span />
              <span>App</span>
              <span>URL</span>
              <span>Status</span>
              <span>Actions</span>
            </div>
            {rows.map((row) => {
              const rowIsSelected = row.deployment?.id === selectedDeployment?.id
                || (!selectedDeployment && row.project?.id === selectedProject?.id);
              return (
                <div
                  key={row.id}
                  role="row"
                  tabIndex={0}
                  aria-selected={rowIsSelected}
                  className={`agent-row ${rowIsSelected ? "active" : ""}`}
                  onClick={() => onOpenOverview(row)}
                  onKeyDown={(event) => {
                    if (event.currentTarget !== event.target) return;
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onOpenOverview(row);
                    }
                  }}
                >
                  <span className={`agent-status ${row.status}`} aria-hidden="true" />
                  <span className="agent-main" role="cell">
                    <strong>{row.name}</strong>
                    <em>{projectFolderName(row.project)}</em>
                    <small>
                      {row.orchestrator || "main.py"} · {row.executor || "executor not detected"}
                    </small>
                  </span>
                  <span className="agent-url-cell" role="cell">
                    {row.appUrl ? (
                      <span className="agent-url-row">
                        <a
                          className="agent-url"
                          href={row.appUrl}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(event) => event.stopPropagation()}
                        >
                          {row.appUrl}
                        </a>
                        <button type="button" className="ghost agent-open-app" onClick={(event) => navigateToRuntime(event, row.appUrl)}>
                          <AppWindow aria-hidden="true" size={15} strokeWidth={1.8} />
                          Open app
                        </button>
                      </span>
                    ) : (
                      <span className="agent-url-row">
                        <span className="muted">-</span>
                        <span className="ghost disabled agent-open-app">
                          <AppWindow aria-hidden="true" size={15} strokeWidth={1.8} />
                          Open app
                        </span>
                      </span>
                    )}
                  </span>
                  <span role="cell">
                    <span className={`status-badge ${row.status}`}>{row.status}</span>
                  </span>
                  <span className="agent-actions" role="cell" onClick={(event) => event.stopPropagation()}>
                    <button
                      type="button"
                      className={`ghost ${rowIsSelected && activeTab === "runs" ? "active" : ""}`}
                      aria-pressed={rowIsSelected && activeTab === "runs"}
                      onClick={() => onOpenRuns(row)}
                    >
                      <ListTree aria-hidden="true" size={15} strokeWidth={1.8} />
                      Traces
                    </button>
                    <button
                      type="button"
                      className={`ghost ${rowIsSelected && activeTab === "logs" ? "active" : ""}`}
                      aria-pressed={rowIsSelected && activeTab === "logs"}
                      onClick={() => onOpenLogs(row)}
                    >
                      <FileText aria-hidden="true" size={15} strokeWidth={1.8} />
                      Logs
                    </button>
                    <button
                      type="button"
                      className={`ghost ${rowIsSelected && activeTab === "system" ? "active" : ""}`}
                      aria-pressed={rowIsSelected && activeTab === "system"}
                      onClick={() => onOpenSystem(row)}
                    >
                      <Boxes aria-hidden="true" size={15} strokeWidth={1.8} />
                      System
                    </button>
                    {row.deployment && (
                      <button type="button" className="ghost danger" onClick={() => onRemoveDeployment(row)}>
                        <Trash2 aria-hidden="true" size={15} strokeWidth={1.8} />
                        Remove
                      </button>
                    )}
                  </span>
                </div>
              );
            })}
          </>
        ) : (
          <div className="agent-empty">
            <strong>No apps deployed</strong>
            <span>Deploy an Agents SDK app to inspect traces, logs, and runtime state here.</span>
            <code>make deploy PROJECT_PATH=/path/to/agents-sdk-app</code>
          </div>
        )}
      </div>
    </section>
  );
}

function RecentRunsSummary({ appRows = [], sessions, rangeHours = 24, onRangeChange, onOpenRun }) {
  const [timelineZoom, setTimelineZoom] = useState(1);
  const gridRef = useRef(null);
  const dragRef = useRef(null);
  const activeRange = traceRangeOptions.find((option) => option.hours === rangeHours) || traceRangeOptions.at(-1);
  const timeline = buildTraceTimeline(sessions, rangeHours, appRows);
  const tracedCount = timeline.sessions.filter((item) => item.session.trace_id).length;
  const emptyLabel = activeRange.hours === "all" ? "all time" : activeRange.label.toLowerCase();
  const emptyMessage = appRows.length ? `No runs recorded in ${emptyLabel}.` : "Deploy an app to see run activity.";
  const timelineWidth = `${Math.round(1600 * timelineZoom)}px`;

  function resetTimelineView() {
    const grid = gridRef.current;
    dragRef.current = null;
    setTimelineZoom(1);
    if (!grid) return;
    grid.classList.remove("dragging");
    grid.scrollLeft = 0;
    grid.scrollTop = 0;
    window.requestAnimationFrame(() => {
      grid.scrollLeft = 0;
      grid.scrollTop = 0;
    });
  }

  function selectRange(hours) {
    resetTimelineView();
    onRangeChange?.(hours);
  }

  function handleTimelineWheel(event) {
    const grid = gridRef.current;
    if (!grid || !timeline.lanes.length) return;
    const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
    if (!delta) return;
    event.preventDefault();
    const rect = grid.getBoundingClientRect();
    const pointerX = event.clientX - rect.left;
    const anchor = (grid.scrollLeft + pointerX) / Math.max(1, grid.scrollWidth);
    setTimelineZoom((zoom) => {
      const scale = delta < 0 ? 1.15 : 1 / 1.15;
      const nextZoom = Math.max(1, Math.min(8, Math.round(zoom * scale * 100) / 100));
      if (nextZoom === zoom) return zoom;
      window.requestAnimationFrame(() => {
        const maxScroll = Math.max(0, grid.scrollWidth - grid.clientWidth);
        grid.scrollLeft = Math.max(0, Math.min(maxScroll, anchor * grid.scrollWidth - pointerX));
      });
      return nextZoom;
    });
  }

  function handleTimelinePointerDown(event) {
    const grid = gridRef.current;
    if (!grid || event.button !== 0 || event.target.closest?.("button,a")) return;
    if (grid.scrollWidth <= grid.clientWidth && grid.scrollHeight <= grid.clientHeight) return;
    dragRef.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      left: grid.scrollLeft,
      top: grid.scrollTop,
    };
    grid.setPointerCapture?.(event.pointerId);
    grid.classList.add("dragging");
  }

  function handleTimelinePointerMove(event) {
    const drag = dragRef.current;
    const grid = gridRef.current;
    if (!drag || !grid || drag.pointerId !== event.pointerId) return;
    grid.scrollLeft = drag.left - (event.clientX - drag.x);
    grid.scrollTop = drag.top - (event.clientY - drag.y);
  }

  function endTimelineDrag(event) {
    const drag = dragRef.current;
    const grid = gridRef.current;
    if (!drag || !grid || drag.pointerId !== event.pointerId) return;
    grid.releasePointerCapture?.(event.pointerId);
    grid.classList.remove("dragging");
    dragRef.current = null;
  }

  return (
    <section className="trace-summary primary-section">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Recent runs</p>
          <h3>Run activity</h3>
        </div>
        <div className="trace-summary-controls">
          <span className="panel-count">{tracedCount} traced</span>
          <div className="range-control" aria-label="Run time range">
            {traceRangeOptions.map((option) => (
              <button
                key={option.hours}
                type="button"
                className={option.hours === rangeHours ? "active" : ""}
                onClick={() => selectRange(option.hours)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div
        ref={gridRef}
        className={`trace-time-grid ${timeline.lanes.length ? "" : "empty"}`}
        tabIndex={0}
        aria-label="Zoomable run activity timeline"
        style={{ "--trace-time-width": timelineWidth }}
        onWheel={handleTimelineWheel}
        onPointerDown={handleTimelinePointerDown}
        onPointerMove={handleTimelinePointerMove}
        onPointerUp={endTimelineDrag}
        onPointerCancel={endTimelineDrag}
      >
        {timeline.lanes.length ? (
          <>
            <div className="trace-time-head">
              <span>App</span>
              <div>
                {timeline.ticks.map((tick) => (
                  <span key={tick.key} style={{ left: `${tick.position}%` }}>
                    {tick.label}
                  </span>
                ))}
              </div>
            </div>
            {timeline.lanes.map((lane) => (
              <div key={lane.key} className={`trace-time-row ${lane.hasTrace ? "has-trace" : ""}`}>
                <span className="trace-time-label">
                  <strong>{lane.appName}</strong>
                  <em>{lane.runs.length ? `${lane.runs.length} run${lane.runs.length === 1 ? "" : "s"}` : "No runs in range"}</em>
                </span>
                <div className="trace-time-track">
                  {timeline.ticks.map((tick) => (
                    <i key={`${lane.key}-${tick.key}`} style={{ left: `${tick.position}%` }} />
                  ))}
                  {lane.runs.map((item, index) => (
                    <button
                      key={item.session.id}
                      type="button"
                      className={`${item.session.trace_id ? "trace-time-run trace-platform" : "trace-time-run trace-session"} ${item.position > 82 ? "edge-end" : item.position < 18 ? "edge-start" : ""}`}
                      style={{ left: `${item.position}%`, top: `${runMarkerTop(index, lane.runs.length)}%` }}
                      onClick={() => onOpenRun(item.session)}
                    >
                      <span aria-hidden="true" />
                      <strong>{item.timeLabel}</strong>
                      <em>Run ID {runId(item.session)} · {item.session.event_count} events</em>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </>
        ) : (
          <div className="trace-summary-empty">{emptyMessage}</div>
        )}
      </div>
    </section>
  );
}

function RunsPanel({
  eyebrow = "Traces",
  selectedSession,
  sessions,
  events,
  allEvents,
  selectedEvent,
  onSelectEvent,
  onSelectSession,
}) {
  const [collapsedTraceNodes, setCollapsedTraceNodes] = useState(() => new Set());
  const traceId = findTraceId(selectedSession, allEvents);
  const traceUrl = traceId ? `https://platform.openai.com/traces/trace?trace_id=${encodeURIComponent(traceId)}` : "";
  const canExportTrace = Boolean(selectedSession && traceEventsForExport(selectedSession, allEvents).length);
  const traceTree = useMemo(() => buildTraceTree(events), [events]);
  const traceRows = useMemo(
    () => flattenTraceTree(traceTree, collapsedTraceNodes),
    [traceTree, collapsedTraceNodes],
  );
  const spanTimingByKey = useMemo(() => buildSpanTiming(events), [events]);
  const runStartedAt = allEvents[0]?.timestamp || selectedSession?.started_at;
  const runEndedAt = allEvents.at(-1)?.timestamp || selectedSession?.updated_at;
  const overviewItems = [
    ["Agent", selectedSession?.project_name || selectedSession?.deployment_name || "-"],
    ["Environment", selectedSession?.deployment_name || selectedSession?.deployment_id || "-"],
    ["Date", formatShortDate(runStartedAt)],
    ["Duration", formatDurationBetween(runStartedAt, runEndedAt)],
    ["Events", String(allEvents.length || selectedSession?.event_count || 0)],
    ["Status", selectedSession?.status || "-"],
    ["Trace ID", shortId(traceId || selectedSession?.id || "")],
  ];

  useEffect(() => {
    setCollapsedTraceNodes(new Set());
  }, [selectedSession?.id]);

  function toggleTraceNode(nodeId) {
    setCollapsedTraceNodes((collapsed) => {
      const next = new Set(collapsed);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  }

  return (
    <section className="trace-panel primary-section">
      <div className="panel-head">
        <div className="run-selector-block">
          <p className="eyebrow">{eyebrow}</p>
          <SessionSelect sessions={sessions} selectedSession={selectedSession} onSelectSession={onSelectSession} />
        </div>
        <div className="trace-head-actions">
          <button
            type="button"
            className="ghost trace-icon-button"
            disabled={!canExportTrace}
            title={canExportTrace ? "Export this run's trace spans as JSON." : "This run does not have trace spans to export."}
            onClick={() => exportRunTraceJson(selectedSession, allEvents)}
          >
            <Download aria-hidden="true" size={15} strokeWidth={1.8} />
            Export JSON
          </button>
          {traceUrl ? (
            <button type="button" className="ghost trace-icon-button" onClick={(event) => openExternalUrl(event, traceUrl)}>
              <ExternalLink aria-hidden="true" size={15} strokeWidth={1.8} />
              View on OpenAI platform
            </button>
          ) : (
            <span className="ghost disabled" title="This run does not have a platform trace id yet.">
              No platform trace
            </span>
          )}
        </div>
      </div>
      <SessionLanes sessions={sessions} selectedSession={selectedSession} onSelectSession={onSelectSession} />
      <dl className="run-overview">
        {overviewItems.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>
              {label === "Status" ? <span className={`status-badge ${String(value).toLowerCase()}`}>{value}</span> : value}
            </dd>
          </div>
        ))}
      </dl>
      <div className="trace-rail">
        {events.map((event, index) => (
          <button
            key={eventKey(event, index)}
            type="button"
            className={`trace-segment ${traceClass(event)} ${event === selectedEvent ? "active" : ""}`}
            title={`${traceLabel(event.source)} / ${event.type}`}
            onClick={() => onSelectEvent(event, index)}
          >
            <span>{formatTraceTime(event.timestamp) || index + 1}</span>
          </button>
        ))}
      </div>
      <div className="trace-events">
        {traceRows.length ? (
          traceRows.map((row) => {
            const key = eventKey(row.event, row.index);
            const title = spanRowTitle(row.event);
            const timing = spanTimingByKey.get(key) || defaultSpanTiming(row.event);
            return (
              <div
                key={key}
                role="button"
                tabIndex={0}
                data-trace-depth={row.depth}
                aria-label={`${title}, ${formatSpanDuration(timing.durationMs)}`}
                className={`trace-row ${traceClass(row.event)} ${row.event === selectedEvent ? "active" : ""} ${row.depth ? "nested" : ""} ${row.hasChildren ? "has-children" : ""}`}
                style={{ "--trace-depth": row.depth }}
                title={row.event.message || title}
                onClick={() => onSelectEvent(row.event, row.index)}
                onKeyDown={(event) => {
                  if (event.target !== event.currentTarget) return;
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectEvent(row.event, row.index);
                  }
                }}
              >
                <strong className="trace-span-name">
                  <span className="trace-tree-prefix">
                    {row.hasChildren ? (
                      <button
                        type="button"
                        className={`trace-row-toggle ${row.collapsed ? "collapsed" : ""}`}
                        aria-label={`${row.collapsed ? "Expand" : "Collapse"} ${title}`}
                        aria-expanded={!row.collapsed}
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          toggleTraceNode(row.nodeId);
                        }}
                      >
                        <ChevronRight aria-hidden="true" size={13} strokeWidth={2.2} />
                      </button>
                    ) : (
                      <span className="trace-row-toggle-spacer" aria-hidden="true" />
                    )}
                    <span className="trace-dot" aria-hidden="true" />
                  </span>
                  <span className="trace-title-text">{title}</span>
                </strong>
                <span className="trace-span-duration">{formatSpanDuration(timing.durationMs)}</span>
                <span className="trace-span-track" aria-hidden="true">
                  <span
                    className="trace-span-fill"
                    style={{
                      left: `${timing.left}%`,
                      width: `${timing.width}%`,
                    }}
                  />
                </span>
              </div>
            );
          })
        ) : (
          <div className="run-empty">No events recorded for this run.</div>
        )}
      </div>
    </section>
  );
}

function buildTraceTree(events) {
  const nodes = [];
  const nodesById = new Map();
  events.forEach((event, index) => {
    const baseId = traceSpanId(event) || eventKey(event, index);
    const id = nodesById.has(baseId) ? `${baseId}-${index}` : baseId;
    const node = {
      id,
      parentId: traceParentSpanId(event),
      event,
      index,
      depth: 0,
      sortTime: traceEventTimeMs(event),
      children: [],
    };
    nodes.push(node);
    nodesById.set(id, node);
  });

  const roots = [];
  nodes.forEach((node) => {
    const parent = node.parentId ? nodesById.get(node.parentId) : null;
    if (parent && parent.id !== node.id) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  });

  function sortAndDepth(items, depth) {
    items.sort(compareTraceNodes);
    items.forEach((node) => {
      node.depth = depth;
      sortAndDepth(node.children, depth + 1);
    });
  }

  sortAndDepth(roots, 0);
  return roots;
}

function flattenTraceTree(nodes, collapsedTraceNodes) {
  const rows = [];
  function visit(node) {
    const collapsed = collapsedTraceNodes.has(node.id);
    rows.push({
      event: node.event,
      index: node.index,
      depth: node.depth,
      hasChildren: node.children.length > 0,
      childCount: node.children.length,
      nodeId: node.id,
      collapsed,
    });
    if (!collapsed) {
      node.children.forEach(visit);
    }
  }
  nodes.forEach(visit);
  return rows;
}

function compareTraceNodes(left, right) {
  if (Number.isFinite(left.sortTime) && Number.isFinite(right.sortTime) && left.sortTime !== right.sortTime) {
    return left.sortTime - right.sortTime;
  }
  return left.index - right.index;
}

function traceSpanId(event) {
  const metadata = event?.metadata || {};
  return firstNonEmptyString([
    metadata.span_id,
    metadata.spanId,
    event?.span_id,
    event?.spanId,
    event?.id,
  ]);
}

function traceParentSpanId(event) {
  const metadata = event?.metadata || {};
  return firstNonEmptyString([
    metadata.parent_id,
    metadata.parentId,
    event?.parent_id,
    event?.parentId,
  ]);
}

function traceEventTimeMs(event) {
  const metadata = event?.metadata || {};
  for (const value of [metadata.started_at, event?.timestamp, metadata.ended_at]) {
    const parsed = Date.parse(value || "");
    if (Number.isFinite(parsed)) return parsed;
  }
  return Number.NaN;
}

function buildSpanTiming(events) {
  const spans = events.map((event, index) => {
    const started = traceEventTimeMs(event);
    const durationMs = traceDurationMs(event);
    const ended = Number.isFinite(started) ? started + Math.max(1, durationMs) : Number.NaN;
    return {
      key: eventKey(event, index),
      started,
      ended,
      durationMs,
    };
  });
  const timedSpans = spans.filter((span) => Number.isFinite(span.started));
  if (!timedSpans.length) {
    return new Map(spans.map((span) => [span.key, { left: 0, width: 1, durationMs: span.durationMs }]));
  }
  const start = Math.min(...timedSpans.map((span) => span.started));
  const end = Math.max(...timedSpans.map((span) => (Number.isFinite(span.ended) ? span.ended : span.started + 1)));
  const range = Math.max(1, end - start);
  return new Map(
    spans.map((span) => {
      if (!Number.isFinite(span.started)) {
        return [span.key, { left: 0, width: 1, durationMs: span.durationMs }];
      }
      const left = clamp(((span.started - start) / range) * 100, 0, 99.2);
      const width = clamp((Math.max(1, span.durationMs) / range) * 100, 0.8, 100 - left);
      return [span.key, { left, width, durationMs: span.durationMs }];
    }),
  );
}

function defaultSpanTiming(event) {
  return { left: 0, width: 1, durationMs: traceDurationMs(event) };
}

function traceDurationMs(event) {
  const metadata = event?.metadata || {};
  const explicitDuration = Number(metadata.duration_ms ?? metadata.durationMs ?? event?.duration_ms ?? event?.durationMs);
  if (Number.isFinite(explicitDuration)) return Math.max(0, explicitDuration);
  const started = Date.parse(metadata.started_at || event?.timestamp || "");
  const ended = Date.parse(metadata.ended_at || "");
  if (Number.isFinite(started) && Number.isFinite(ended)) return Math.max(0, ended - started);
  return 0;
}

function formatSpanDuration(durationMs) {
  const value = Number(durationMs);
  if (!Number.isFinite(value)) return "0 ms";
  const ms = Math.max(0, value);
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`;
  return `${Math.round(ms).toLocaleString()} ms`;
}

function spanRowTitle(event) {
  const spanData = event?.metadata?.span_data || {};
  const spanType = String(spanData.type || "").toLowerCase();
  if (spanType === "agent" && spanData.name) return spanData.name;
  if (spanType === "response") return event?.message || "response";
  if (spanType === "handoff" && spanData.to_agent) return `Handoff > ${spanData.to_agent}`;
  if (spanType === "function" && spanData.name) return spanData.name;
  if (spanData.name) return spanData.name;
  if (spanData.data?.sdk_span_type) return spanData.data.sdk_span_type;
  return eventTitle(event);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function firstNonEmptyString(values) {
  return values.find((value) => typeof value === "string" && value.trim()) || "";
}

function EventDetailPane({ event, resizeHandleProps = null }) {
  return (
    <aside className="pane detail-pane event-detail-pane">
      {resizeHandleProps && (
        <div
          className="detail-resizer"
          role="separator"
          aria-label="Resize details pane"
          aria-orientation="vertical"
          aria-valuemin={detailPaneMinWidth}
          aria-valuemax={detailPaneMaxWidth}
          tabIndex={0}
          {...resizeHandleProps}
        />
      )}
      <div className="panel-head">
        <div>
          <p className="eyebrow">Details</p>
          <h3>{event ? eventTitle(event) : "Select an event"}</h3>
        </div>
      </div>
      {event ? (
        <EventDetailContent event={event} />
      ) : (
        <div className="detail-empty">Select an event to inspect its payload.</div>
      )}
    </aside>
  );
}

function isTimelineEvent(value) {
  return Boolean(value && typeof value === "object" && ("source" in value || "type" in value || "timestamp" in value));
}

function eventKey(event, index) {
  return event?.id || `${event?.timestamp || "event"}-${event?.source || "source"}-${event?.type || "type"}-${index}`;
}

function eventTitle(event) {
  const source = traceLabel(event.source);
  const type = titleCase(String(event.type || "event").replaceAll("_", " "));
  if (!event.source) return type;
  if (!event.type) return source;
  return `${source}: ${type}`;
}

function findTraceId(selectedSession, traceEvents) {
  const candidates = [
    selectedSession?.trace_id,
    selectedSession?.traceId,
    selectedSession?.metadata?.trace_id,
    selectedSession?.metadata?.traceId,
  ];
  for (const event of traceEvents) {
    candidates.push(event.trace_id, event.traceId, event.metadata?.trace_id, event.metadata?.traceId);
  }
  return candidates.find((value) => typeof value === "string" && value.trim()) || "";
}

function SessionSelect({ sessions, selectedSession, onSelectSession }) {
  return (
    <select value={selectedSession?.id || ""} onChange={(event) => onSelectSession(event.target.value)}>
      {sessions.length ? (
        sessions.map((session) => (
          <option key={session.id} value={session.id}>
            {sessionTitle(session)} · {session.status}
          </option>
        ))
      ) : (
        <option>No runs</option>
      )}
    </select>
  );
}

function SessionLanes({ sessions, selectedSession, onSelectSession }) {
  return (
    <div className="session-lanes">
      {sessions.map((session) => (
        <button key={session.id} type="button" className={`session-lane ${session.id === selectedSession?.id ? "active" : ""}`} onClick={() => onSelectSession(session.id)}>
          <span>{session.deployment_name || session.deployment_id}</span>
          <strong>Run ID {runId(session)}</strong>
          <em>{session.project_name || session.project_id}</em>
          <small>{session.status} · {session.event_count} events</small>
        </button>
      ))}
    </div>
  );
}

function ContainerList({ containers, appName }) {
  if (!containers.length) {
    return <div className="container-list">No Docker containers observed.</div>;
  }
  return (
    <div className="container-list">
      {containers.map((container) => (
        <div key={container.id} className="container">
          <div>
            <strong>{displayContainerName(container, appName)}</strong>
            <small>{container.role === "orchestrator" ? "app container" : container.role}</small>
          </div>
          <div>
            <code>{container.id}</code>
            <small>{container.status}</small>
          </div>
          <small>{container.image}</small>
          {formatContainerLabels(container.labels) && <small>{formatContainerLabels(container.labels)}</small>}
        </div>
      ))}
    </div>
  );
}

function traceClass(event) {
  if (event.level === "error") return "trace-error";
  const eventType = String(event.type || "").toLowerCase();
  const eventMessage = String(event.message || "").toLowerCase();
  const spanType = String(event?.metadata?.span_data?.type || "").toLowerCase();
  if (spanType === "agent") return "trace-agent";
  if (spanType === "response") return "trace-platform";
  if (spanType === "function" || spanType === "handoff") return "trace-tool";
  if (spanType === "custom" || spanType === "task" || spanType === "turn") return "trace-orchestrator";
  if (event.source === "trace") return "trace-platform";
  if (event.source === "agent" && eventType === "response") return "trace-platform";
  if (event.source === "agent" && /search|browser|tool|exec|command|scrape|read|write/.test(`${eventType} ${eventMessage}`)) {
    return "trace-tool";
  }
  if (event.source === "agent") return "trace-agent";
  if (event.source === "tool") return "trace-tool";
  if (event.source === "approval") return "trace-platform";
  if (event.source === "sandbox") return "trace-sandbox";
  if (event.source === "orchestrator") return "trace-orchestrator";
  if (event.type === "decision") return "trace-decision";
  if (event.source === "session") return "trace-orchestrator";
  return "trace-orchestrator";
}

function traceLabel(source) {
  const labels = {
    trace: "Platform",
    agent: "Agent",
    tool: "Tool",
    approval: "Approval",
    sandbox: "Sandbox",
    orchestrator: "Runtime",
    session: "Session",
  };
  return labels[source] || titleCase(String(source || "event"));
}

function buildTraceTimeline(sessions, rangeHours = 24, appRows = []) {
  const now = Date.now();
  const appOrder = buildAppOrder(appRows);
  const lanes = buildAppTimelineLanes(appRows);
  const lanesByKey = new Map(lanes.map((lane) => [lane.key, lane]));
  const datedSessions = sessions
    .map((session) => {
      const date = parseSessionDate(session);
      return date ? { session, date } : null;
    })
    .filter(Boolean);
  const allTime = rangeHours === "all";
  const max = allTime && datedSessions.length ? Math.max(...datedSessions.map((item) => item.date.getTime()), now) : now;
  const min = allTime
    ? datedSessions.length
      ? Math.min(...datedSessions.map((item) => item.date.getTime()), now)
      : now - 24 * 60 * 60 * 1000
    : now - rangeHours * 60 * 60 * 1000;
  const range = Math.max(1, max - min);
  const items = datedSessions
    .filter((item) => allTime || (item.date.getTime() >= min && item.date.getTime() <= max))
    .sort((a, b) => {
      const appDelta = sessionAppOrder(a.session, appOrder) - sessionAppOrder(b.session, appOrder);
      if (appDelta) return appDelta;
      return b.date.getTime() - a.date.getTime();
    })
    .map((item) => ({
      ...item,
      appName: item.session.deployment_name || item.session.project_name || item.session.deployment_id,
      dateLabel: formatTraceDate(item.date),
      timeLabel: formatGridTime(item.date),
      position: Math.max(0, Math.min(100, ((item.date.getTime() - min) / range) * 100)),
    }));

  const ticks = Array.from({ length: 7 }, (_, index) => {
    const position = (index / 6) * 100;
    const date = new Date(min + (range * position) / 100);
    return {
      key: `${index}-${date.getTime()}`,
      label: formatGridTime(date),
      position,
    };
  });

  for (const item of items) {
    let laneKey = sessionAppLaneKey(item.session, lanes);
    if (!laneKey) {
      laneKey = `session-${item.session.deployment_id || item.session.project_id || item.appName}`;
      if (!lanesByKey.has(laneKey)) {
        const lane = {
          key: laneKey,
          appName: item.appName,
          runs: [],
          hasTrace: false,
          matchKeys: [],
        };
        lanes.push(lane);
        lanesByKey.set(laneKey, lane);
      }
    }
    const lane = lanesByKey.get(laneKey);
    lane.runs.push(item);
    lane.hasTrace = lane.hasTrace || Boolean(item.session.trace_id);
  }

  return {
    ticks,
    sessions: items,
    lanes: lanes
      .map((lane) => ({
        ...lane,
        runs: lane.runs.sort((a, b) => b.date.getTime() - a.date.getTime()),
      }))
      .filter((lane) => appRows.length || lane.runs.length),
  };
}

function buildAppTimelineLanes(appRows) {
  return appRows.map((row, index) => {
    const key = row.id || row.deployment?.id || row.project?.id || `app-${index}`;
    return {
      key,
      appName: row.name || row.deployment?.name || row.project?.name || key,
      runs: [],
      hasTrace: false,
      matchKeys: [
        row.id,
        row.name,
        row.deployment?.id,
        row.deployment?.name,
        row.project?.id,
        row.project?.name,
      ].filter(Boolean),
    };
  });
}

function sessionAppLaneKey(session, lanes) {
  const sessionKeys = [
    session.deployment_id,
    session.deployment_name,
    session.project_id,
    session.project_name,
  ].filter(Boolean);
  return lanes.find((lane) => lane.matchKeys.some((key) => sessionKeys.includes(key)))?.key || "";
}

function runMarkerTop(index, total) {
  if (total <= 1) return 50;
  const visibleIndex = index % 3;
  if (visibleIndex === 0) return 50;
  return visibleIndex === 1 ? 28 : 72;
}

function buildAppOrder(appRows) {
  const order = new Map();
  appRows.forEach((row, index) => {
    [
      row.id,
      row.name,
      row.deployment?.id,
      row.deployment?.name,
      row.project?.id,
      row.project?.name,
    ]
      .filter(Boolean)
      .forEach((key) => {
        if (!order.has(key)) order.set(key, index);
      });
  });
  return order;
}

function sessionAppOrder(session, appOrder) {
  for (const key of [
    session.deployment_id,
    session.deployment_name,
    session.project_id,
    session.project_name,
  ].filter(Boolean)) {
    if (appOrder.has(key)) return appOrder.get(key);
  }
  return Number.MAX_SAFE_INTEGER;
}

function parseSessionDate(session) {
  const timestamp = session?.updated_at || session?.started_at;
  if (!timestamp) return null;
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatTraceDate(date) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(date);
}

function formatGridTime(date) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function formatShortDate(timestamp) {
  if (!timestamp) return "-";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat(undefined, {
    month: "numeric",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function formatDurationBetween(startTimestamp, endTimestamp) {
  if (!startTimestamp || !endTimestamp) return "-";
  const started = new Date(startTimestamp);
  const ended = new Date(endTimestamp);
  if (Number.isNaN(started.getTime()) || Number.isNaN(ended.getTime())) return "-";
  const totalSeconds = Math.max(0, Math.round((ended.getTime() - started.getTime()) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function formatTraceTime(timestamp) {
  if (!timestamp) return "";
  const value = String(timestamp);
  const match = value.match(/T(\d{2}:\d{2}:\d{2})/);
  return match ? match[1] : value;
}

function shortId(value) {
  if (!value) return "-";
  const text = String(value);
  return text.length > 16 ? `${text.slice(0, 12)}...` : text;
}

function runId(session) {
  return session?.expense_id || session?.id || "-";
}

function titleCase(value) {
  return value.slice(0, 1).toUpperCase() + value.slice(1);
}

function sessionTitle(session) {
  return `${session.deployment_name || session.project_name || session.deployment_id} / Run ID ${runId(session)}`;
}

function projectFolderName(project) {
  const value = project?.path || project?.id;
  if (!value) return "No project folder";
  const normalized = String(value).replace(/\/+$/, "");
  return normalized.split("/").pop() || normalized;
}

function formatContainerLabels(labels = {}) {
  return ["agents-sdk.deployment-id", "agents-sdk.session-id"]
    .map((key) => labels[key] && `${key.replace("agents-sdk.", "")}=${labels[key]}`)
    .filter(Boolean)
    .join(" ");
}

function displayContainerName(container, appName) {
  return appName || container.name;
}

function buildAgentRows({ projects, deployments, sessions, containerCounts }) {
  const projectsById = new Map(projects.map((item) => [item.id, item]));
  const rows = deployments.map((deployment) => {
    const project = projectsById.get(deployment.project_id) || null;
    const deploymentSessions = sessions.filter((session) => session.deployment_id === deployment.id);
    return {
      id: deployment.id,
      name: displayDeploymentName(deployment, project) || deployment.id,
      deployment,
      project,
      status: deployment.status || "unknown",
      target: deployment.target || "local-process",
      sandbox: deployment.sandbox_backend || "-",
      port: deployment.port,
      appUrl: deployment.app_url || project?.app_url,
      sessionCount: deploymentSessions.length,
      containerCount: containerCounts[deployment.id],
      latestSession: deploymentSessions[0] || null,
      orchestrator: project?.orchestrator_entrypoint,
      executor: project?.executor_entrypoint,
    };
  });

  return rows;
}

function selectedAppRowId(rows, deployment, project) {
  const row = rows.find((item) => {
    if (deployment?.id && item.deployment?.id === deployment.id) return true;
    return project?.id && item.project?.id === project.id;
  });
  return row?.id || rows[0]?.id || "";
}

function displayDeploymentName(deployment, project) {
  if (!deployment) return project?.name || "";
  if (project?.name && deployment.name === `${project.name} local`) {
    return project.name;
  }
  return deployment.name || project?.name || deployment.id;
}

createRoot(document.getElementById("root")).render(<App />);
