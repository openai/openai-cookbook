(function () {
  "use strict";

  var data = JSON.parse(document.getElementById("viewer-data").textContent);
  var audio = document.getElementById("conversation-audio");
  var elements = {
    heading: document.getElementById("scenario-heading"),
    scenarioId: document.getElementById("scenario-id"),
    scenarioSelect: document.getElementById("scenario-select"),
    scenarioStatus: document.getElementById("scenario-status"),
    runState: document.getElementById("run-state"),
    play: document.getElementById("play-button"),
    speed: document.getElementById("speed-button"),
    currentTime: document.getElementById("current-time"),
    duration: document.getElementById("duration"),
    timeline: document.getElementById("timeline-stage"),
    ruler: document.getElementById("time-ruler"),
    caller: document.getElementById("caller-track"),
    assistant: document.getElementById("assistant-track"),
    events: document.getElementById("events-track"),
    playhead: document.getElementById("playhead"),
    caption: document.getElementById("timeline-caption"),
    tickCaption: document.getElementById("tick-caption"),
    transcript: document.getElementById("transcript-list"),
    turns: document.getElementById("turn-count"),
    interactionMode: document.getElementById("interaction-mode"),
    interactionExplanation: document.getElementById("interaction-explanation"),
    metrics: document.getElementById("metric-list"),
    tools: document.getElementById("tool-list"),
    outcome: document.getElementById("outcome-message")
  };
  var speeds = [1, 1.25, 1.5, 2, 0.75];
  var state = { scenario: data.scenarios[0], timeMs: 0, speedIndex: 0, frame: 0, selectedResponse: null, selectedBackend: null };

  function create(tag, className, text) {
    var element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function formatClock(milliseconds) {
    var total = Math.max(0, milliseconds || 0) / 1000;
    var minutes = Math.floor(total / 60);
    var seconds = Math.floor(total % 60);
    return String(minutes) + ":" + String(seconds).padStart(2, "0");
  }

  function formatPrecise(milliseconds) {
    return (Math.max(0, milliseconds || 0) / 1000).toFixed(1) + "s";
  }

  function formatLatency(milliseconds) {
    return (Math.max(0, milliseconds || 0) / 1000).toFixed(2) + " s";
  }

  function responseEvents() {
    return state.scenario.interactionEvents.filter(function (event) {
      return event.type === "response" && event.caller_end_ms != null && event.assistant_start_ms != null;
    });
  }

  function durationMs() {
    return Math.max(1, state.scenario.waveform.durationMs);
  }

  function percent(milliseconds) {
    return Math.max(0, Math.min(100, (milliseconds / durationMs()) * 100));
  }

  function setPlaying(playing) {
    elements.play.classList.toggle("is-playing", playing);
    elements.play.setAttribute("aria-label", playing ? "Pause conversation" : "Play conversation");
    elements.runState.textContent = playing ? "PLAYING" : state.scenario.status.toUpperCase();
    if (playing) animatePlayhead();
    else if (state.frame) {
      cancelAnimationFrame(state.frame);
      state.frame = 0;
    }
  }

  function animatePlayhead() {
    state.timeMs = audio.currentTime * 1000;
    updatePlayhead();
    highlightTurn();
    if (!audio.paused && !audio.ended) state.frame = requestAnimationFrame(animatePlayhead);
  }

  function updatePlayhead() {
    var canvas = elements.caller.getBoundingClientRect();
    var stage = elements.timeline.getBoundingClientRect();
    var left = canvas.left - stage.left + canvas.width * Math.min(1, state.timeMs / durationMs());
    elements.playhead.style.left = left + "px";
    elements.currentTime.textContent = formatClock(state.timeMs);
  }

  function makeRegion(item, role) {
    var region = create("div", "speech-region " + role);
    region.style.left = percent(item.startMs) + "%";
    region.style.width = Math.max(0.18, percent(item.endMs) - percent(item.startMs)) + "%";
    region.title = item.text || (role === "caller" ? "Caller speech" : "Agent speech");
    if (item.action) region.dataset.action = item.action;
    return region;
  }

  function makeOverlap(item) {
    var region = create("div", "overlap-region");
    region.style.left = percent(item.startMs) + "%";
    region.style.width = Math.max(0.16, percent(item.endMs) - percent(item.startMs)) + "%";
    region.title = "Overlapping speech · " + formatPrecise(item.endMs - item.startMs);
    return region;
  }

  function drawWaveform(container, role) {
    var samples = state.scenario.waveform[role] || [];
    var maximum = Math.max.apply(null, samples.concat([0.035]));
    var namespace = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(namespace, "svg");
    svg.setAttribute("class", "waveform " + role);
    svg.setAttribute("viewBox", "0 0 1000 100");
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("aria-hidden", "true");

    samples.forEach(function (sample, index) {
      var height = sample ? Math.max(4, (sample / maximum) * 67) : 1;
      var x = ((index + 0.5) / samples.length) * 1000;
      var line = document.createElementNS(namespace, "line");
      line.setAttribute("x1", x.toFixed(2));
      line.setAttribute("x2", x.toFixed(2));
      line.setAttribute("y1", ((100 - height) / 2).toFixed(2));
      line.setAttribute("y2", ((100 + height) / 2).toFixed(2));
      line.setAttribute("stroke", "currentColor");
      line.setAttribute("stroke-width", sample ? "1.1" : "0.7");
      line.setAttribute("stroke-opacity", sample ? "0.83" : "0.21");
      svg.appendChild(line);
    });
    container.appendChild(svg);
  }

  function renderTrack(container, role) {
    container.replaceChildren();
    state.scenario.tracks[role].forEach(function (item) {
      container.appendChild(makeRegion(item, role));
    });
    drawWaveform(container, role);
    state.scenario.overlaps.forEach(function (item) {
      container.appendChild(makeOverlap(item));
    });
  }

  function addEventMarker(item, label, className) {
    var kind = item.kind;
    var index = kind === "delegation" ? item.delegationIndex : item.toolIndex;
    var marker = create("button", "event-marker " + (className || ""));
    marker.type = "button";
    marker.dataset.activityId = activityId(kind, index);
    marker.classList.toggle("is-selected", marker.dataset.activityId === state.selectedBackend);
    marker.setAttribute("aria-label", "Show " + (kind === "delegation" ? "delegation " + String(index + 1) : "tool call " + label));
    marker.addEventListener("click", function (event) {
      event.stopPropagation();
      selectBackend(kind, index, true);
    });
    marker.style.left = percent(item.timeMs) + "%";
    marker.title = label + " · " + formatPrecise(item.timeMs);
    marker.dataset.timeMs = String(item.timeMs);
    marker.dataset.lane = String(item.lane || 0);
    marker.appendChild(create("span", "event-marker-label", label));
    elements.events.appendChild(marker);
  }

  function layoutEventMarkers() {
    var track = elements.events.getBoundingClientRect();
    var occupied = [];
    var highestLane = 0;
    var markers = Array.from(elements.events.querySelectorAll(".event-marker"));
    markers.sort(function (left, right) {
      return Number(left.dataset.timeMs) - Number(right.dataset.timeMs);
    });
    markers.forEach(function (marker) {
      var center = (Number(marker.dataset.timeMs) / durationMs()) * track.width;
      var width = marker.getBoundingClientRect().width;
      var left = center - 3.5 - 7;
      var right = center - 3.5 + width + 7;
      var lane = 0;
      while (occupied[lane] !== undefined && occupied[lane] > left) lane += 1;
      occupied[lane] = right;
      marker.dataset.lane = String(lane);
      marker.style.top = String(33 + lane * 20) + "px";
      highestLane = Math.max(highestLane, lane);
    });
    var minimum = window.matchMedia("(max-width: 720px)").matches ? 48 : 55;
    elements.events.parentElement.style.minHeight = String(Math.max(minimum, 38 + (highestLane + 1) * 20)) + "px";
  }

  function layoutLatencyLabels() {
    var track = elements.events.getBoundingClientRect();
    elements.events.querySelectorAll(".latency-span").forEach(function (span) {
      var label = span.querySelectorAll(".latency-span-label")[0];
      if (!label) return;
      var width = label.getBoundingClientRect().width;
      var start = Number.parseFloat(span.style.left) / 100 * track.width;
      var end = start + Number.parseFloat(span.style.width) / 100 * track.width;
      var center = Math.max(width / 2 + 3, Math.min(track.width - width / 2 - 3, (start + end) / 2));
      label.style.left = String(center - start) + "px";
    });
  }

  function renderEvents() {
    elements.events.replaceChildren();
    responseEvents().forEach(function (event, index) {
      var latency = event.latency_ms == null
        ? event.assistant_start_ms - event.caller_end_ms
        : event.latency_ms;
      var span = create("button", "latency-span");
      span.type = "button";
      span.style.left = percent(event.caller_end_ms) + "%";
      span.style.width = Math.max(0.16, percent(event.assistant_start_ms) - percent(event.caller_end_ms)) + "%";
      span.title = "Response " + String(index + 1) + " latency · " + formatLatency(latency);
      span.dataset.responseIndex = String(index);
      span.setAttribute("aria-label", span.title);
      span.appendChild(create("span", "latency-span-label", formatLatency(latency)));
      span.addEventListener("click", function (click) {
        click.stopPropagation();
        selectResponse(index, true);
      });
      elements.events.appendChild(span);
    });
    state.scenario.eventAnnotations.forEach(function (event) {
      var style = event.kind === "delegation"
        ? "is-delegation"
        : event.status === "completed" ? "is-completed" : "is-called";
      addEventMarker(event, event.label, style);
    });
    layoutEventMarkers();
    layoutLatencyLabels();
  }

  function renderRuler() {
    var count = Math.min(7, Math.max(4, Math.ceil(durationMs() / 7000)));
    elements.ruler.replaceChildren();
    for (var index = 0; index <= count; index += 1) {
      var mark = create("span", "ruler-mark", formatClock((index / count) * durationMs()));
      mark.style.left = ((index / count) * 100).toFixed(2) + "%";
      elements.ruler.appendChild(mark);
    }
  }

  function transcriptRow(turn, responseIndex) {
    var item = create("div", "transcript-row");
    var time = create("span", "transcript-time", formatClock(turn.startMs));
    var copy = create("div", "transcript-copy");
    var role = create("div", "transcript-role " + turn.role, turn.role === "caller" ? "CALLER" : "AGENT");
    if (turn.action && turn.action !== "OPENING" && turn.action !== "SPEAK") {
      role.appendChild(create("span", "turn-action", turn.action.toLowerCase()));
    }
    if (responseIndex != null) {
      role.appendChild(create("span", "turn-response-latency", formatLatency(turn.responseLatencyMs) + " response"));
      item.dataset.responseIndex = String(responseIndex);
    }
    copy.appendChild(role);
    copy.appendChild(create("p", "transcript-text", turn.text));
    item.appendChild(time);
    item.appendChild(copy);
    item.dataset.start = String(turn.startMs);
    item.dataset.end = String(turn.endMs);
    item.tabIndex = 0;
    item.setAttribute("role", "button");
    item.setAttribute(
      "aria-label",
      "Seek to " + (turn.role === "caller" ? "caller" : "agent") + " at " + formatClock(turn.startMs),
    );
    item.addEventListener("click", function () {
      seek(turn.startMs);
    });
    item.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        event.stopPropagation();
        seek(turn.startMs);
      }
    });
    return item;
  }

  function activityId(kind, index) {
    return "activity-" + kind + "-" + String(index);
  }

  function selectBackend(kind, index, reveal) {
    var activity = kind === "delegation"
      ? (state.scenario.delegations || [])[index]
      : (state.scenario.toolCalls || [])[index];
    if (!activity) return;
    state.selectedBackend = activityId(kind, index);
    [elements.transcript, elements.events].forEach(function (container) {
      container.querySelectorAll("[data-activity-id]").forEach(function (item) {
        item.classList.toggle("is-selected", item.dataset.activityId === state.selectedBackend);
      });
    });
    var row = document.getElementById(state.selectedBackend);
    if (reveal && row) {
      var details = row.querySelector("details");
      details.open = true;
      row.scrollIntoView({ block: "center", behavior: "auto" });
      details.querySelector("summary").focus({ preventScroll: true });
    }
    if (typeof activity.timeMs === "number") seek(activity.timeMs);
  }

  function backendRow(kind, activity, index) {
    var item = create("li", "backend-row " + kind);
    item.id = activityId(kind, index);
    item.dataset.activityId = item.id;
    var time = create("button", "transcript-time backend-seek",
      typeof activity.timeMs === "number" ? formatClock(activity.timeMs) : "—");
    time.type = "button";
    time.disabled = typeof activity.timeMs !== "number";
    time.setAttribute("aria-label", "Seek to " + (kind === "delegation" ? "delegation " + String(index + 1) : activity.name));
    time.addEventListener("click", function () { selectBackend(kind, index, false); });
    item.appendChild(time);
    var details = create("details", "backend-details");
    var summary = create("summary", "backend-summary");
    summary.appendChild(create("span", "backend-symbol", kind === "delegation" ? "◇" : "↳"));
    summary.appendChild(create("span", "backend-name", kind === "delegation"
      ? "Delegation " + String(index + 1) + " · " + activity.target : activity.name));
    summary.appendChild(create("span", "backend-status", activity.status));
    details.appendChild(summary);
    var content = create("div", "backend-content");
    if (kind === "delegation") {
      if (activity.responseCount != null) {
        content.appendChild(create("p", "backend-meta", String(activity.responseCount) + " backend response" +
          (activity.responseCount === 1 ? "" : "s")));
      }
      var responses = activity.responses || [];
      (responses.length ? responses : ["No final response text recorded."]).forEach(function (text) {
        content.appendChild(create("p", "backend-response", text));
      });
      var tools = activity.tools || [];
      if (!tools.length) {
        content.appendChild(create("p", "backend-meta", activity.toolCount == null
          ? "Tool association unavailable" : "No application tool calls recorded"));
      }
      tools.forEach(function (tool) {
        if (typeof tool.toolIndex === "number") {
          var link = create("button", "backend-link", tool.name + " · " + tool.status);
          link.type = "button";
          link.addEventListener("click", function () { selectBackend("tool", tool.toolIndex, true); });
          content.appendChild(link);
        } else content.appendChild(create("p", "backend-meta", tool.name + " · " + tool.status));
      });
    } else {
      if (typeof activity.delegationIndex === "number") {
        var owner = create("button", "backend-link", "Delegation " + String(activity.delegationIndex + 1));
        owner.type = "button";
        owner.addEventListener("click", function () { selectBackend("delegation", activity.delegationIndex, true); });
        content.appendChild(owner);
      }
      content.appendChild(create("p", "backend-meta", "Arguments"));
      content.appendChild(create(activity.arguments == null ? "p" : "pre", "backend-arguments",
        activity.arguments == null ? "Arguments not recorded." : JSON.stringify(activity.arguments, null, 2)));
    }
    details.appendChild(content);
    item.appendChild(details);
    return item;
  }

  function activityTurnIndex(timeMs) {
    if (!Number.isFinite(timeMs)) return null;
    var turns = state.scenario.turns;
    var active = null;
    var next = null;
    turns.forEach(function (turn, index) {
      if (turn.role !== "assistant") return;
      if (turn.startMs <= timeMs && timeMs < turn.endMs &&
          (active === null || turn.startMs > turns[active].startMs)) active = index;
      if (turn.startMs >= timeMs && (next === null || turn.startMs < turns[next].startMs)) next = index;
    });
    if (active !== null) return active;
    // A new caller turn between the event and the next response makes the
    // association ambiguous. Keep that activity visible but unassigned.
    if (next === null || turns.some(function (turn) {
      return turn.role === "caller" && turn.startMs > timeMs && turn.startMs < turns[next].startMs;
    })) return null;
    return next;
  }

  function appendActivityList(container, activities) {
    if (!activities.length) return;
    var list = create("ol", "turn-activity");
    list.setAttribute("aria-label", "Backend activity; actual event times");
    activities.sort(function (a, b) { return a.timeMs - b.timeMs || a.rank - b.rank; });
    activities.forEach(function (row) { list.appendChild(row.element); });
    container.appendChild(list);
  }

  function renderTranscript() {
    elements.transcript.replaceChildren();
    var responseIndex = 0;
    var rows = state.scenario.turns.map(function (turn, index) {
      var measuredResponse = turn.role === "assistant" && typeof turn.responseLatencyMs === "number";
      var group = create("li", "conversation-turn");
      group.dataset.turnIndex = String(index);
      group.appendChild(transcriptRow(turn, measuredResponse ? responseIndex : null));
      if (measuredResponse) responseIndex += 1;
      return { timeMs: turn.startMs, element: group, activities: [] };
    });
    var delegationOwners = (state.scenario.delegations || []).map(function (activity) {
      return activityTurnIndex(activity.timeMs);
    });
    var unassigned = [];
    ["delegation", "tool"].forEach(function (kind, rank) {
      var activities = kind === "delegation" ? state.scenario.delegations : state.scenario.toolCalls;
      (activities || []).forEach(function (activity, index) {
        var owner = kind === "delegation" ? delegationOwners[index] : activityTurnIndex(activity.timeMs);
        // Recorded tool/delegation identity takes precedence over timing,
        // including tools that finish after another speaker has started.
        if (kind === "tool" && Number.isInteger(activity.delegationIndex) &&
            activity.delegationIndex >= 0 && activity.delegationIndex < delegationOwners.length) {
          owner = delegationOwners[activity.delegationIndex];
        }
        var destination = owner === null ? unassigned : rows[owner].activities;
        destination.push({ timeMs: Number.isFinite(activity.timeMs) ? activity.timeMs : Infinity,
          rank: rank, element: backendRow(kind, activity, index) });
      });
    });
    rows.sort(function (a, b) { return a.timeMs - b.timeMs; });
    rows.forEach(function (row) {
      appendActivityList(row.element, row.activities);
      elements.transcript.appendChild(row.element);
    });
    if (unassigned.length) {
      var other = create("li", "unassigned-activity");
      other.appendChild(create("p", "activity-note", "Backend activity without a matching response"));
      appendActivityList(other, unassigned);
      elements.transcript.appendChild(other);
    }
    elements.turns.textContent = String(state.scenario.turns.length) + " turns";
  }

  function highlightTurn() {
    var rows = elements.transcript.querySelectorAll(".transcript-row");
    rows.forEach(function (row) {
      var start = Number(row.dataset.start);
      var end = Number(row.dataset.end);
      row.classList.toggle("is-active", state.timeMs >= start && state.timeMs <= end);
    });
  }

  function metricValue(value, kind, missingLabel) {
    if (value == null) return { text: missingLabel || "Not measured", empty: true };
    if (kind === "seconds") return { text: Number(value).toFixed(2) + " s", empty: false };
    if (kind === "milliseconds") return { text: Number(value).toLocaleString() + " ms", empty: false };
    if (kind === "percent") return { text: (Number(value) * 100).toLocaleString(undefined, { maximumFractionDigits: 2 }) + "%", empty: false };
    if (typeof value === "boolean") return { text: value ? "Yes" : "No", empty: false };
    if (typeof value === "number") return { text: value.toLocaleString(), empty: false };
    return { text: String(value), empty: false };
  }

  function countValue(key, eventTypes) {
    var counts = state.scenario.interactionCounts || {};
    if (typeof counts[key] === "number") return counts[key];
    return state.scenario.interactionEvents.filter(function (event) {
      return eventTypes.indexOf(event.type) !== -1;
    }).length;
  }

  function appendResponseBreakdown(events, container) {
    var longest = events.reduce(function (maximum, item) {
      var latency = item.latency_ms == null ? item.assistant_start_ms - item.caller_end_ms : item.latency_ms;
      return Math.max(maximum, latency);
    }, 1);
    events.forEach(function (event, index) {
      var latency = event.latency_ms == null
        ? event.assistant_start_ms - event.caller_end_ms
        : event.latency_ms;
      var row = create("div", "metric-row metric-response-detail");
      var name = create("dt");
      var button = create("button", "response-detail-button", "Response " + String(index + 1));
      button.type = "button";
      button.addEventListener("click", function () { selectResponse(index, true); });
      name.appendChild(button);
      row.appendChild(name);
      var value = create("dd", "response-detail-value");
      var bar = create("span", "response-detail-bar");
      var fill = create("i");
      fill.style.width = Math.max(8, Math.min(100, latency / longest * 100)) + "%";
      bar.appendChild(fill);
      value.appendChild(bar);
      value.appendChild(create("span", "response-detail-time", formatLatency(latency)));
      row.appendChild(value);
      row.dataset.responseIndex = String(index);
      container.appendChild(row);
    });
  }

  function metricLabel(key) {
    return key.replace(/_/g, " ").replace(/\bms\b/g, "duration").replace(/^./, function (letter) { return letter.toUpperCase(); });
  }

  function renderMetrics() {
    var finalMetrics = state.scenario.finalMetrics || { audio: state.scenario.metrics, task: state.scenario.task };
    var labels = {
      "audio.response_rate": "Response rate",
      "audio.response_latency_ms": "Average response latency",
      "audio.interruption_rate": "Interruptions",
      "audio.speaking_duration_ms.cumulative": "Cumulative speaking duration",
      "audio.speaking_duration_ms.maximum": "Maximum turn speaking duration",
      "audio.floor_hold_silence_ms.cumulative": "Cumulative floor-hold silence",
      "audio.floor_hold_silence_ms.maximum": "Maximum floor-hold silence",
      "task.task_completed": "Task completed",
      "task.tool_accuracy": "Tool accuracy",
      "task.delegation_accuracy": "Delegation accuracy",
      "task.semantic_quality.score": "Semantic quality",
      "task.tool_calls": "Tool calls",
      "task.delegations": "Delegations",
      "task.turns": "Turns"
    };
    var groups = { audio: "Audio", task: "Task", consumption: "Consumption" };
    elements.metrics.replaceChildren();

    function appendMetric(container, path, label, value, detail) {
      var key = path.join(".");
      var percentMetric = /(?:_rate|_accuracy)$/.test(key) || key.indexOf("task.semantic_quality") === 0;
      var kind = path.some(function (part) { return /_ms$/.test(part); }) ? "milliseconds" : percentMetric ? "percent" : "number";
      var display = metricValue(value, kind, key.indexOf("semantic_quality") !== -1 ? "Not assessed" : "Not measured");
      var row = create("div", "metric-row");
      row.dataset.metricPath = key;
      var name = create("dt", "", labels[key] || label);
      if (key === "audio.response_rate") {
        var total = countValue("response_total", ["response", "no_response"]);
        if (total) detail = String(countValue("response_count", ["response"])) + " of " + String(total) + " eligible requests";
      }
      if (key === "task.tool_accuracy") {
        var tools = state.scenario.tools || {};
        if (typeof tools.expected_count === "number") detail = tools.expected_count === 0 ? "No tools expected"
          : String(tools.matched_count == null ? "?" : tools.matched_count) + " of " + String(tools.expected_count) + " expected tools";
      }
      if (detail) name.appendChild(create("span", "metric-context", detail));
      row.appendChild(name);
      row.appendChild(create("dd", display.empty ? "is-empty" : "", display.text));
      container.appendChild(row);
      if (key === "audio.response_rate") appendResponseBreakdown(responseEvents(), container);
    }

    function walk(container, value, path, prefix) {
      var key = path.join(".");
      if (key === "audio.metrics_version") return;
      if (value && typeof value === "object" && !Array.isArray(value) &&
          Object.prototype.hasOwnProperty.call(value, "actual") && Object.prototype.hasOwnProperty.call(value, "expected")) {
        appendMetric(container, path, prefix, String(value.actual) + " / " + String(value.expected), "Actual / expected");
      } else if (value && typeof value === "object") {
        var keys = Object.keys(value);
        if (!keys.length) appendMetric(container, path, prefix, null);
        keys.forEach(function (child) {
          var childLabel = metricLabel(child);
          var nextLabel = prefix ? prefix + " · " + childLabel : childLabel;
          if (key === "task.semantic_quality.dimensions") nextLabel = childLabel;
          if (key === "task.semantic_quality" && child === "score") nextLabel = "Semantic quality";
          walk(container, value[child], path.concat(child), nextLabel);
        });
      } else appendMetric(container, path, prefix, value);
    }

    Object.keys(groups).concat(Object.keys(finalMetrics).filter(function (key) { return !groups[key]; })).forEach(function (group) {
      if (!Object.prototype.hasOwnProperty.call(finalMetrics, group)) return;
      var section = create("section", "metric-group");
      section.appendChild(create("h3", "metric-group-title", groups[group] || metricLabel(group)));
      var list = create("dl", "metric-list");
      walk(list, finalMetrics[group], [group], "");
      section.appendChild(list);
      elements.metrics.appendChild(section);
    });
  }

  function selectResponse(index, shouldSeek) {
    state.selectedResponse = index;
    elements.events.querySelectorAll(".latency-span").forEach(function (item) {
      item.classList.toggle("is-selected", Number(item.dataset.responseIndex) === index);
    });
    elements.transcript.querySelectorAll(".transcript-row").forEach(function (item) {
      item.classList.toggle("is-selected", item.dataset.responseIndex != null && Number(item.dataset.responseIndex) === index);
    });
    elements.metrics.querySelectorAll(".metric-response-detail").forEach(function (item) {
      item.classList.toggle("is-selected", Number(item.dataset.responseIndex) === index);
    });
    if (shouldSeek) {
      var response = responseEvents()[index];
      if (response) seek(response.assistant_start_ms);
    }
  }

  function renderTools() {
    var executed = state.scenario.toolCalls || [];
    elements.tools.replaceChildren();
    if (!executed.length) {
      elements.tools.appendChild(create("div", "tool-row", "No application tools"));
      return;
    }
    executed.forEach(function (tool, index) {
      var row = create("button", "tool-row tool-seek");
      row.type = "button";
      row.addEventListener("click", function () { selectBackend("tool", index, true); });
      row.appendChild(create("span", "", tool.name));
      row.appendChild(create("span", "", tool.status));
      elements.tools.appendChild(row);
    });
  }

  function renderEvidence() {
    var synthetic = data.run.audioProvenance === "synthetic_tone_fixture";
    elements.interactionMode.textContent = "Post-hoc inference";
    if (synthetic) {
      elements.interactionExplanation.textContent =
        "Offline verification fixture: both participants use synthetic tones, not real GPT Live speech.";
    } else {
      elements.interactionExplanation.textContent =
        "Both GPT Live participants speak continuously. Interaction signals are inferred from observed audio.";
    }
    elements.outcome.textContent = state.scenario.completion.rationale || "No outcome assessment was recorded.";
    renderMetrics();
    renderTools();
  }

  function renderHeader() {
    var scenario = state.scenario;
    var synthetic = data.run.audioProvenance === "synthetic_tone_fixture";
    elements.heading.textContent = scenario.title;
    elements.scenarioId.textContent = scenario.id;
    elements.scenarioStatus.textContent = scenario.status.toUpperCase();
    elements.scenarioStatus.classList.toggle("is-failed", scenario.status !== "passed");
    elements.runState.textContent = scenario.status.toUpperCase();
    elements.caption.textContent = synthetic
      ? "Synthetic test audio · no live model calls"
      : "Independent GPT Live caller + agent";
    elements.tickCaption.textContent = scenario.timelineProvenance === "reconstructed_audio"
      ? "Reconstructed from saved audio"
      : String(data.run.configuration.tick_ms || 200) + " ms resolution";
    elements.duration.textContent = formatClock(durationMs());
  }

  function renderScenario() {
    audio.pause();
    setPlaying(false);
    state.timeMs = 0;
    state.selectedResponse = null;
    state.selectedBackend = null;
    audio.src = state.scenario.audioData;
    audio.playbackRate = speeds[state.speedIndex];
    renderHeader();
    renderRuler();
    renderTrack(elements.caller, "caller");
    renderTrack(elements.assistant, "assistant");
    renderEvents();
    renderTranscript();
    renderEvidence();
    if (responseEvents().length) selectResponse(0, false);
    updatePlayhead();
  }

  function seek(milliseconds) {
    var limited = Math.max(0, Math.min(durationMs(), milliseconds));
    state.timeMs = limited;
    audio.currentTime = limited / 1000;
    updatePlayhead();
    highlightTurn();
  }

  function togglePlayback() {
    if (!audio.paused) {
      audio.pause();
      return;
    }
    var result = audio.play();
    if (result && result.catch) {
      result.catch(function () {
        setPlaying(false);
      });
    }
  }

  data.scenarios.forEach(function (scenario, index) {
    var option = create("option", "", scenario.id);
    option.value = String(index);
    elements.scenarioSelect.appendChild(option);
  });
  elements.scenarioSelect.disabled = data.scenarios.length < 2;
  elements.scenarioSelect.addEventListener("change", function () {
    state.scenario = data.scenarios[Number(elements.scenarioSelect.value)];
    renderScenario();
  });

  elements.play.addEventListener("click", togglePlayback);
  elements.speed.addEventListener("click", function () {
    state.speedIndex = (state.speedIndex + 1) % speeds.length;
    audio.playbackRate = speeds[state.speedIndex];
    elements.speed.textContent = String(speeds[state.speedIndex]) + "×";
  });
  elements.timeline.addEventListener("click", function (event) {
    if (event.target.closest(".track-label")) return;
    var bounds = elements.caller.getBoundingClientRect();
    var ratio = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
    seek(ratio * durationMs());
  });
  elements.timeline.addEventListener("keydown", function (event) {
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      seek(state.timeMs + (event.key === "ArrowRight" ? 5000 : -5000));
    }
  });
  document.addEventListener("keydown", function (event) {
    if (event.code !== "Space") return;
    if (event.target.closest("select, input, textarea, button, summary")) return;
    event.preventDefault();
    togglePlayback();
  });
  audio.addEventListener("play", function () {
    setPlaying(true);
  });
  audio.addEventListener("pause", function () {
    setPlaying(false);
  });
  audio.addEventListener("ended", function () {
    setPlaying(false);
  });
  audio.addEventListener("timeupdate", function () {
    state.timeMs = audio.currentTime * 1000;
    updatePlayhead();
    highlightTurn();
  });
  window.addEventListener("resize", function () {
    renderEvents();
    if (state.selectedResponse != null) selectResponse(state.selectedResponse, false);
    updatePlayhead();
  });
  renderScenario();
})();
