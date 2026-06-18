const state = {
  config: null,
  stations: [],
  selected: {
    departure: null,
    arrival: null,
  },
  loading: false,
};

const $ = (selector) => document.querySelector(selector);

const elements = {
  form: $("#config-form"),
  alert: $("#global-alert"),
  diagnostics: $("#diagnostics"),
  logConsole: $("#log-console"),
  results: $("#results"),
  rawCandidateCount: $("#raw-candidate-count"),
  matchCount: $("#match-count"),
  latestMatch: $("#latest-match"),
  watcherDot: $("#watcher-dot"),
  watcherState: $("#watcher-state"),
  watcherLastCheck: $("#watcher-last-check"),
  watcherTotalChecks: $("#watcher-total-checks"),
  notificationResult: $("#notification-result"),
  routeDepartureSummary: $("#route-departure-summary"),
  routeArrivalSummary: $("#route-arrival-summary"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || payload.message || `${response.status} ${response.statusText}`);
  }
  return payload;
}

function formData() {
  const data = Object.fromEntries(new FormData(elements.form).entries());
  data.check_interval_seconds = Number(data.check_interval_seconds || 0);
  return data;
}

function setLoading(isLoading, label = "İşlem sürüyor...") {
  state.loading = isLoading;
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = isLoading;
  });
  if (isLoading) showAlert(label, "info");
}

function showAlert(message, level = "info") {
  elements.alert.hidden = false;
  elements.alert.textContent = message;
  elements.alert.dataset.level = level;
  if (level !== "error") {
    window.clearTimeout(showAlert.timer);
    showAlert.timer = window.setTimeout(() => {
      elements.alert.hidden = true;
    }, 3500);
  }
}

function setFormValues(config) {
  state.config = config;
  for (const [key, value] of Object.entries(config)) {
    const field = elements.form.elements.namedItem(key);
    if (field) field.value = value ?? "";
  }
  selectStation("departure", findStation(config.departure_station), config.departure_station || "");
  selectStation("arrival", findStation(config.arrival_station), config.arrival_station || "");
}

function findStation(name) {
  if (!name) return null;
  const key = normalize(name);
  return state.stations.find((station) => normalize(station.name) === key) || null;
}

function normalize(value) {
  return (value || "")
    .toLocaleLowerCase("tr-TR")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/ı/g, "i")
    .replace(/[^a-z0-9]+/g, "");
}

function selectStation(prefix, station, fallback = "") {
  const hiddenInput = document.getElementById(`${prefix}_station`);
  const searchInput = document.getElementById(`${prefix}-search`);
  state.selected[prefix] = station;
  hiddenInput.value = station ? station.name : fallback;
  searchInput.value = station ? station.label : fallback;
  updateRouteSummary();
}

function updateRouteSummary() {
  elements.routeDepartureSummary.textContent =
    state.selected.departure?.label || elements.form.elements.departure_station.value || "-";
  elements.routeArrivalSummary.textContent =
    state.selected.arrival?.label || elements.form.elements.arrival_station.value || "-";
}

function renderResults(matches = []) {
  elements.results.innerHTML = "";
  elements.matchCount.textContent = String(matches.length);
  elements.latestMatch.textContent = matches[0]?.departure_time || "-";

  if (!matches.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Uygun sefer bulunamadı.";
    elements.results.appendChild(empty);
    return;
  }

  for (const match of matches) {
    const card = document.createElement("article");
    card.className = "result-card";
    card.innerHTML = `
      <div class="result-time">${escapeHtml(match.departure_time || "-")}</div>
      <div class="result-main">
        <strong>${escapeHtml(match.train_name || "Bilinmeyen tren")}</strong>
        <span>${escapeHtml(match.class_name || "-")}</span>
        <small>${escapeHtml(match.reason || "")}</small>
      </div>
      <div class="availability">${escapeHtml(match.availability || "-")}</div>
    `;
    elements.results.appendChild(card);
  }
}

function renderDiagnostics(payload) {
  elements.rawCandidateCount.textContent = String(payload.raw_candidate_count ?? 0);
  elements.diagnostics.textContent = JSON.stringify(
    {
      filter_rejections: payload.filter_rejections,
      first_candidates: payload.first_candidates,
    },
    null,
    2,
  );
}

function renderLogs(logs = []) {
  if (!logs.length) {
    elements.logConsole.textContent = "Log bekleniyor.";
    return;
  }
  elements.logConsole.innerHTML = logs
    .map(
      (entry) => `
        <div class="log-line" data-level="${escapeHtml(entry.level || "info")}">
          <span>${escapeHtml(entry.time || "--:--:--")}</span>
          <strong>${escapeHtml(entry.level || "info")}</strong>
          <p>${escapeHtml(entry.message || "")}</p>
        </div>
      `,
    )
    .join("");
}

function updateWatcherStatus(status) {
  const running = Boolean(status.running);
  elements.watcherDot.dataset.running = running ? "true" : "false";
  elements.watcherState.textContent = running ? "Çalışıyor" : "Durduruldu";
  elements.watcherLastCheck.textContent = status.last_check_finished || status.last_check_started || "-";
  elements.watcherTotalChecks.textContent = String(status.total_checks || 0);

  if (status.last_error) showAlert(status.last_error, "error");
  if ((status.last_matches || []).length) renderResults(status.last_matches);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setupCombobox(prefix) {
  const wrapper = document.querySelector(`.combobox[data-target="${prefix}_station"]`);
  const searchInput = document.getElementById(`${prefix}-search`);
  const hiddenInput = document.getElementById(`${prefix}_station`);
  const dropdown = document.getElementById(`${prefix}-dropdown`);
  let activeIndex = -1;
  let options = [];

  function filterOptions(query = "") {
    const queryKey = normalize(query);
    return state.stations
      .filter((station) => !queryKey || normalize(station.label).includes(queryKey))
      .slice(0, 50);
  }

  function renderOptions(query = "") {
    options = filterOptions(query);
    activeIndex = options.length ? 0 : -1;
    dropdown.innerHTML = "";

    for (const [index, station] of options.entries()) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `dropdown-item${index === activeIndex ? " active" : ""}`;
      button.setAttribute("role", "option");
      button.innerHTML = `
        <strong>${escapeHtml(station.name)}</strong>
        <span>${escapeHtml(station.city || "TCDD")}</span>
      `;
      button.addEventListener("mousedown", (event) => event.preventDefault());
      button.addEventListener("click", () => {
        selectStation(prefix, station);
        closeDropdown();
      });
      dropdown.appendChild(button);
    }

    if (!options.length) {
      dropdown.innerHTML = `<div class="dropdown-empty">Sonuç yok</div>`;
    }
  }

  function openDropdown() {
    wrapper.classList.add("open");
    renderOptions(searchInput.value);
  }

  function closeDropdown() {
    wrapper.classList.remove("open");
  }

  function updateActive() {
    dropdown.querySelectorAll(".dropdown-item").forEach((item, index) => {
      item.classList.toggle("active", index === activeIndex);
    });
  }

  searchInput.addEventListener("focus", openDropdown);
  searchInput.addEventListener("input", () => {
    hiddenInput.value = searchInput.value;
    state.selected[prefix] = null;
    updateRouteSummary();
    openDropdown();
  });

  searchInput.addEventListener("keydown", (event) => {
    if (!wrapper.classList.contains("open") && ["ArrowDown", "ArrowUp"].includes(event.key)) {
      openDropdown();
      event.preventDefault();
      return;
    }
    if (event.key === "ArrowDown") {
      activeIndex = Math.min(activeIndex + 1, options.length - 1);
      updateActive();
      event.preventDefault();
    } else if (event.key === "ArrowUp") {
      activeIndex = Math.max(activeIndex - 1, 0);
      updateActive();
      event.preventDefault();
    } else if (event.key === "Enter" && activeIndex >= 0 && options[activeIndex]) {
      selectStation(prefix, options[activeIndex]);
      closeDropdown();
      event.preventDefault();
    } else if (event.key === "Escape") {
      closeDropdown();
    }
  });

  document.addEventListener("click", (event) => {
    if (!wrapper.contains(event.target)) closeDropdown();
  });
}

async function refreshWatcherStatus() {
  const payload = await api("/api/watcher/status");
  updateWatcherStatus(payload.status);
}

async function refreshLogs() {
  const payload = await api("/api/logs");
  renderLogs(payload.logs || []);
}

async function runAction(button, label, action) {
  try {
    setLoading(true, label);
    const payload = await action();
    showAlert(payload.message || "İşlem tamamlandı.", "success");
    return payload;
  } catch (error) {
    showAlert(error.message, "error");
    return null;
  } finally {
    setLoading(false);
    await refreshWatcherStatus().catch(() => {});
    await refreshLogs().catch(() => {});
  }
}

function localDateValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function setupQuickControls() {
  document.querySelectorAll("[data-date-offset]").forEach((button) => {
    button.addEventListener("click", () => {
      const date = new Date();
      date.setDate(date.getDate() + Number(button.dataset.dateOffset || 0));
      elements.form.elements.date.value = localDateValue(date);
    });
  });

  document.querySelector("[data-time-preset='evening']").addEventListener("click", () => {
    elements.form.elements.preferred_departure_time.value = "";
    elements.form.elements.departure_time_from.value = "18:00";
    elements.form.elements.departure_time_to.value = "21:00";
  });

  document.querySelector("[data-time-preset='all']").addEventListener("click", () => {
    elements.form.elements.preferred_departure_time.value = "";
    elements.form.elements.departure_time_from.value = "";
    elements.form.elements.departure_time_to.value = "";
  });
}

async function loadInitialData() {
  const [config, stations] = await Promise.all([api("/api/config"), api("/api/stations")]);
  state.stations = stations;
  setFormValues(config);
  renderResults([]);
}

$("#save-config").addEventListener("click", (event) =>
  runAction(event.currentTarget, "Config kaydediliyor...", async () =>
    api("/api/config", { method: "POST", body: JSON.stringify(formData()) }),
  ).then((payload) => {
    if (payload) setFormValues(payload.config);
  }),
);

$("#search-once").addEventListener("click", (event) =>
  runAction(event.currentTarget, "Arama yapılıyor...", async () =>
    api("/api/search", { method: "POST", body: JSON.stringify(formData()) }),
  ).then((payload) => {
    if (!payload) return;
    renderDiagnostics(payload);
    renderResults(payload.matches || []);
  }),
);

$("#start-watcher").addEventListener("click", (event) =>
  runAction(event.currentTarget, "Watcher başlatılıyor...", async () =>
    api("/api/watcher/start", { method: "POST", body: JSON.stringify(formData()) }),
  ),
);

$("#stop-watcher").addEventListener("click", (event) =>
  runAction(event.currentTarget, "Watcher durduruluyor...", async () =>
    api("/api/watcher/stop", { method: "POST", body: JSON.stringify({}) }),
  ),
);

$("#test-ntfy").addEventListener("click", (event) =>
  runAction(event.currentTarget, "ntfy test bildirimi gönderiliyor...", async () =>
    api("/api/ntfy/test", { method: "POST", body: JSON.stringify(formData()) }),
  ).then((payload) => {
    if (!payload) return;
    elements.notificationResult.textContent = payload.message || "Test bildirimi gönderildi.";
  }),
);

$("#clear-log").addEventListener("click", () => {
  elements.logConsole.textContent = "Log görünümü temizlendi. Yeni olaylar tekrar düşer.";
});

setupCombobox("departure");
setupCombobox("arrival");
setupQuickControls();
loadInitialData()
  .then(() => Promise.all([refreshWatcherStatus(), refreshLogs()]))
  .catch((error) => showAlert(error.message, "error"));

setInterval(() => {
  refreshWatcherStatus().catch(() => {});
  refreshLogs().catch(() => {});
}, 4000);
