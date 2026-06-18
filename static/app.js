const state = {
  stations: [],
  config: null,
};

const form = document.getElementById("config-form");
const resultsEl = document.getElementById("results");
const diagnosticsEl = document.getElementById("diagnostics");
const rawCandidateCountEl = document.getElementById("raw-candidate-count");
const matchCountEl = document.getElementById("match-count");
const watcherStateEl = document.getElementById("watcher-state");
const watcherLastCheckEl = document.getElementById("watcher-last-check");
const watcherTotalChecksEl = document.getElementById("watcher-total-checks");
const watcherErrorEl = document.getElementById("watcher-error");
const watcherErrorRowEl = document.getElementById("watcher-error-row");

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

function formData() {
  const data = Object.fromEntries(new FormData(form).entries());
  data.check_interval_seconds = Number(data.check_interval_seconds || 0);
  return data;
}

function setFormValues(config) {
  state.config = config;
  for (const [key, value] of Object.entries(config)) {
    const element = form.elements.namedItem(key);
    if (element) {
      element.value = value ?? "";
    }
  }
  bindStationValue("departure", config.departure_station || "");
  bindStationValue("arrival", config.arrival_station || "");
}

function bindStationValue(prefix, value) {
  const searchInput = document.getElementById(`${prefix}-search`);
  const hiddenInput = document.getElementById(`${prefix}_station`);
  hiddenInput.value = value;
  searchInput.value = value;
}

function renderResults(matches) {
  resultsEl.innerHTML = "";
  if (!matches.length) {
    const empty = document.createElement("div");
    empty.className = "result-item";
    empty.textContent = "Uygun sefer bulunmadi.";
    resultsEl.appendChild(empty);
    return;
  }

  for (const match of matches) {
    const item = document.createElement("article");
    item.className = "result-item";
    item.innerHTML = `
      <div class="result-head">
        <div class="result-time">${match.departure_time || "-"}</div>
        <div>${match.availability || "-"}</div>
      </div>
      <div class="result-meta"><strong>${escapeHtml(match.train_name || "Bilinmiyor")}</strong></div>
      <div class="result-meta">${escapeHtml(match.class_name || "-")}</div>
    `;
    resultsEl.appendChild(item);
  }
}

function renderDiagnostics(payload) {
  rawCandidateCountEl.textContent = String(payload.raw_candidate_count ?? 0);
  matchCountEl.textContent = String((payload.matches || []).length);
  diagnosticsEl.textContent = JSON.stringify(
    {
      filter_rejections: payload.filter_rejections,
      first_candidates: payload.first_candidates,
    },
    null,
    2,
  );
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function updateWatcherStatus(status) {
  watcherStateEl.textContent = status.running ? "Calisiyor" : "Durduruldu";
  watcherLastCheckEl.textContent = status.last_check_finished || status.last_check_started || "-";
  watcherTotalChecksEl.textContent = String(status.total_checks || 0);
  if (status.last_error) {
    watcherErrorEl.textContent = status.last_error;
    watcherErrorRowEl.hidden = false;
  } else {
    watcherErrorEl.textContent = "-";
    watcherErrorRowEl.hidden = true;
  }
  if ((status.last_matches || []).length) {
    renderResults(status.last_matches);
    matchCountEl.textContent = String(status.last_matches.length);
  }
}

function setupCombobox(prefix) {
  const wrapper = document.querySelector(`.combobox[data-target="${prefix}_station"]`);
  const searchInput = document.getElementById(`${prefix}-search`);
  const hiddenInput = document.getElementById(`${prefix}_station`);
  const dropdown = document.getElementById(`${prefix}-dropdown`);

  function renderOptions(query = "") {
    const normalized = query.trim().toLocaleLowerCase("tr-TR");
    const options = state.stations
      .filter((station) => {
        if (!normalized) return true;
        return station.label.toLocaleLowerCase("tr-TR").includes(normalized);
      })
      .slice(0, 40);

    dropdown.innerHTML = "";
    for (const station of options) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "dropdown-item";
      button.textContent = station.label;
      button.addEventListener("click", () => {
        hiddenInput.value = station.name;
        searchInput.value = station.label;
        wrapper.classList.remove("open");
      });
      dropdown.appendChild(button);
    }
  }

  searchInput.addEventListener("focus", () => {
    wrapper.classList.add("open");
    renderOptions(searchInput.value);
  });

  searchInput.addEventListener("input", () => {
    wrapper.classList.add("open");
    renderOptions(searchInput.value);
    hiddenInput.value = searchInput.value;
  });

  document.addEventListener("click", (event) => {
    if (!wrapper.contains(event.target)) {
      wrapper.classList.remove("open");
    }
  });
}

async function loadInitialData() {
  const [config, stations] = await Promise.all([api("/api/config"), api("/api/stations")]);
  state.stations = stations;
  setFormValues(config);
}

async function refreshWatcherStatus() {
  try {
    const payload = await api("/api/watcher/status");
    updateWatcherStatus(payload.status);
  } catch (error) {
    watcherErrorEl.textContent = error.message;
    watcherErrorRowEl.hidden = false;
  }
}

document.getElementById("save-config").addEventListener("click", async () => {
  const payload = await api("/api/config", {
    method: "POST",
    body: JSON.stringify(formData()),
  });
  setFormValues(payload.config);
  diagnosticsEl.textContent = "Config kaydedildi.";
});

document.getElementById("search-once").addEventListener("click", async () => {
  diagnosticsEl.textContent = "Araniyor...";
  const payload = await api("/api/search", {
    method: "POST",
    body: JSON.stringify(formData()),
  });
  renderDiagnostics(payload);
  renderResults(payload.matches || []);
});

document.getElementById("start-watcher").addEventListener("click", async () => {
  const payload = await api("/api/watcher/start", {
    method: "POST",
    body: JSON.stringify(formData()),
  });
  updateWatcherStatus(payload.status);
  diagnosticsEl.textContent = "Watcher baslatildi.";
});

document.getElementById("stop-watcher").addEventListener("click", async () => {
  const payload = await api("/api/watcher/stop", {
    method: "POST",
    body: JSON.stringify({}),
  });
  updateWatcherStatus(payload.status);
  diagnosticsEl.textContent = "Watcher durduruldu.";
});

setupCombobox("departure");
setupCombobox("arrival");
loadInitialData().then(refreshWatcherStatus);
setInterval(refreshWatcherStatus, 4000);
