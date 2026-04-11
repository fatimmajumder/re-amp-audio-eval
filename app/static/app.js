const state = {
  catalog: null,
  overview: null,
  runs: [],
  workspaces: [],
  activeRunId: null,
  compareResult: null
};

const elements = {
  benchmarkSelect: document.getElementById("benchmark-select"),
  modelSelect: document.getElementById("model-select"),
  workspaceSelect: document.getElementById("workspace-select"),
  publicDatasetSelect: document.getElementById("public-dataset-select"),
  datasetInput: document.getElementById("dataset-input"),
  seedInput: document.getElementById("seed-input"),
  notesInput: document.getElementById("notes-input"),
  scenarioGrid: document.getElementById("scenario-grid"),
  scenarioCount: document.getElementById("scenario-count"),
  runForm: document.getElementById("run-form"),
  formFeedback: document.getElementById("form-feedback"),
  workspaceForm: document.getElementById("workspace-form"),
  workspaceNameInput: document.getElementById("workspace-name-input"),
  workspaceOwnerInput: document.getElementById("workspace-owner-input"),
  workspaceDescriptionInput: document.getElementById("workspace-description-input"),
  workspaceFocusInput: document.getElementById("workspace-focus-input"),
  workspaceFeedback: document.getElementById("workspace-feedback"),
  compareLeft: document.getElementById("compare-left"),
  compareRight: document.getElementById("compare-right"),
  compareButton: document.getElementById("compare-button"),
  compareOutput: document.getElementById("compare-output"),
  runsList: document.getElementById("runs-list"),
  detailTitle: document.getElementById("detail-title"),
  detailStatus: document.getElementById("detail-status"),
  detailContent: document.getElementById("detail-content"),
  leaderboard: document.getElementById("leaderboard"),
  recentRuns: document.getElementById("recent-runs"),
  datasetsList: document.getElementById("datasets-list"),
  workspacesList: document.getElementById("workspaces-list"),
  heroRunCount: document.getElementById("hero-run-count"),
  heroWorkspaceCount: document.getElementById("hero-workspace-count"),
  heroDatasetCount: document.getElementById("hero-dataset-count"),
  metricAverageScore: document.getElementById("metric-average-score"),
  metricAverageLatency: document.getElementById("metric-average-latency"),
  metricBestModel: document.getElementById("metric-best-model"),
  metricActiveRuns: document.getElementById("metric-active-runs")
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch (error) {
      // Ignore parse errors and fall back to the status text.
    }
    throw new Error(detail);
  }

  return response.json();
}

function formatScore(value) {
  return Number(value || 0).toFixed(3);
}

function formatLatency(value) {
  return `${Math.round(Number(value || 0))} ms`;
}

function formatDate(value) {
  if (!value) {
    return "n/a";
  }

  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  });
}

function getSelectedScenarioNames() {
  return Array.from(
    elements.scenarioGrid.querySelectorAll('input[type="checkbox"]:checked')
  ).map((input) => input.value);
}

function syncScenarioCount() {
  const count = getSelectedScenarioNames().length;
  elements.scenarioCount.textContent = `${count} selected`;
}

function renderScenarioGrid(templateName) {
  if (!state.catalog) {
    return;
  }

  const template = state.catalog.benchmark_templates.find(
    (item) => item.benchmark_name === templateName
  );
  const defaults = new Set(template?.default_scenarios || []);

  if (!elements.publicDatasetSelect.value) {
    elements.datasetInput.value = template?.dataset_name || "";
  }

  elements.scenarioGrid.innerHTML = "";
  state.catalog.scenario_library.forEach((scenario) => {
    const card = document.createElement("label");
    card.className = "scenario-pill";
    card.innerHTML = `
      <input type="checkbox" value="${scenario.name}" ${defaults.has(scenario.name) ? "checked" : ""} />
      <div>
        <strong>${scenario.name.replaceAll("_", " ")}</strong>
        <small>${scenario.category} · ${scenario.difficulty}</small>
      </div>
      <p>${scenario.description}</p>
    `;

    const checkbox = card.querySelector("input");
    const toggleSelected = () => {
      card.classList.toggle("is-selected", checkbox.checked);
      syncScenarioCount();
    };

    checkbox.addEventListener("change", toggleSelected);
    toggleSelected();
    elements.scenarioGrid.appendChild(card);
  });
}

function renderCatalog() {
  if (!state.catalog) {
    return;
  }

  elements.benchmarkSelect.innerHTML = state.catalog.benchmark_templates
    .map(
      (template) =>
        `<option value="${template.benchmark_name}">${template.benchmark_name}</option>`
    )
    .join("");

  elements.modelSelect.innerHTML = state.catalog.models
    .map((model) => `<option value="${model.name}">${model.name}</option>`)
    .join("");

  elements.publicDatasetSelect.innerHTML = [
    `<option value="">Use template or custom dataset label</option>`,
    ...state.catalog.public_datasets.map(
      (dataset) => `<option value="${dataset.dataset_id}">${dataset.name}</option>`
    )
  ].join("");

  renderScenarioGrid(elements.benchmarkSelect.value);
  renderDatasets();
}

function renderWorkspaceSelect() {
  const previousValue = elements.workspaceSelect.value;
  elements.workspaceSelect.innerHTML = state.workspaces
    .map(
      (workspace) => `<option value="${workspace.workspace_id}">${workspace.name}</option>`
    )
    .join("");

  if (state.workspaces.some((workspace) => workspace.workspace_id === previousValue)) {
    elements.workspaceSelect.value = previousValue;
  }
}

function renderDatasets() {
  if (!state.catalog) {
    return;
  }

  elements.datasetsList.innerHTML = state.catalog.public_datasets
    .map((dataset) => {
      const availabilityClass =
        dataset.availability.status === "downloaded" ? "status-ready" : "status-remote";
      const availabilityCopy =
        dataset.availability.status === "downloaded"
          ? `${dataset.availability.audio_file_count} local files`
          : dataset.access_mode === "direct"
            ? "remote, ready to download"
            : dataset.access_mode === "request"
              ? "documented access flow"
              : "metadata-driven source";
      const sampleFiles =
        dataset.availability.sample_files.length > 0
          ? `<p class="dataset-samples">sample: ${dataset.availability.sample_files.join(", ")}</p>`
          : "";
      return `
        <article class="dataset-card">
          <div class="dataset-card-top">
            <div>
              <h4>${dataset.name}</h4>
              <p>${dataset.provider} · ${dataset.domain}</p>
            </div>
            <span class="status-chip ${availabilityClass}">${availabilityCopy}</span>
          </div>
          <p>${dataset.description}</p>
          <div class="dataset-meta">
            <span class="tag">${dataset.download_size}</span>
            <span class="tag">${dataset.license_name}</span>
            <span class="tag">${dataset.access_mode}</span>
          </div>
          <p class="dataset-notes">${dataset.notes.join(" ")}</p>
          ${sampleFiles}
          <div class="dataset-links">
            <a class="artifact-link" href="${dataset.source_url}" target="_blank" rel="noreferrer">Source</a>
            <a class="artifact-link" href="${dataset.download_url}" target="_blank" rel="noreferrer">Download</a>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderWorkspaces() {
  if (!state.workspaces.length) {
    elements.workspacesList.innerHTML =
      '<div class="empty-state">No workspaces yet. Create one to organize evaluation lanes.</div>';
    return;
  }

  elements.workspacesList.innerHTML = state.workspaces
    .map(
      (workspace) => `
        <article class="workspace-card">
          <div class="workspace-card-top">
            <div>
              <h4>${workspace.name}</h4>
              <p>${workspace.owner}</p>
            </div>
            <span class="tag">${workspace.run_count} runs</span>
          </div>
          <p>${workspace.description}</p>
          <div class="workspace-focuses">
            ${workspace.focus_areas.map((focus) => `<span class="tag">${focus}</span>`).join("")}
          </div>
          <div class="workspace-meta">
            <span>default benchmark: ${workspace.default_benchmark || "custom"}</span>
            <span>last run: ${formatDate(workspace.last_run_at)}</span>
          </div>
        </article>
      `
    )
    .join("");
}

function renderOverview() {
  const overview = state.overview;
  if (!overview) {
    return;
  }

  elements.heroRunCount.textContent = `${overview.total_runs} runs tracked`;
  elements.heroWorkspaceCount.textContent = `${overview.workspace_count} workspaces`;
  elements.heroDatasetCount.textContent = `${overview.public_dataset_count} datasets`;
  elements.metricAverageScore.textContent = formatScore(overview.average_score);
  elements.metricAverageLatency.textContent = formatLatency(overview.average_latency_ms);
  elements.metricBestModel.textContent = overview.best_model_name || "n/a";
  elements.metricActiveRuns.textContent = `${overview.active_runs}`;

  elements.leaderboard.innerHTML =
    overview.leaderboard.length === 0
      ? `<div class="empty-state">No completed runs yet.</div>`
      : overview.leaderboard
          .map((entry) => {
            const width = `${Math.max(8, entry.average_score * 100)}%`;
            return `
              <div class="leaderboard-row">
                <div>
                  <strong>${entry.model_name}</strong>
                  <span>${entry.benchmark_count} benchmark runs</span>
                </div>
                <div class="leaderboard-bar"><span style="width:${width}"></span></div>
                <div class="leaderboard-score">${formatScore(entry.average_score)} · ${formatLatency(entry.average_latency_ms)}</div>
              </div>
            `;
          })
          .join("");

  elements.recentRuns.innerHTML =
    overview.recent_runs.length === 0
      ? `<div class="empty-state">No recent activity.</div>`
      : overview.recent_runs
          .map(
            (run) => `
              <div class="recent-run">
                <div>
                  <strong>${run.model_name}</strong>
                  <p>${run.benchmark_name}</p>
                  <p>${run.workspace_name}</p>
                </div>
                <div>
                  <span>${run.aggregate_score ? formatScore(run.aggregate_score) : run.status}</span>
                  <p>${formatDate(run.created_at)}</p>
                </div>
              </div>
            `
          )
          .join("");
}

function renderRunList() {
  if (!state.runs.length) {
    elements.runsList.innerHTML =
      '<div class="empty-state">No runs yet. Use the composer to launch the first benchmark.</div>';
    return;
  }

  elements.runsList.innerHTML = state.runs
    .map((run) => {
      const score = run.summary ? formatScore(run.summary.aggregate_score) : "pending";
      const latency = run.summary
        ? formatLatency(run.summary.average_latency_ms)
        : run.status === "failed"
          ? "failed"
          : "queued";
      const progress = Math.max(6, Number(run.progress || 0));
      return `
        <article class="run-card ${state.activeRunId === run.run_id ? "is-active" : ""}" tabindex="0" data-run-id="${run.run_id}">
          <div class="run-card-top">
            <div>
              <h4>${run.model_name}</h4>
              <p class="eyebrow">${run.benchmark_name}</p>
            </div>
            <span class="status-badge" data-status="${run.status}">${run.status}</span>
          </div>
          <div class="run-card-meta">
            <span class="tag">${run.workspace_name}</span>
            <span class="tag">${run.dataset_name}</span>
            <span class="tag">seed ${run.seed}</span>
          </div>
          <div class="run-card-meta">
            <span>${run.scenarios.length} scenarios</span>
            <span>${run.public_dataset_id || "custom dataset"}</span>
          </div>
          <div class="run-card-meta">
            <span>score ${score}</span>
            <span>${latency}</span>
          </div>
          <div class="progress-bar"><span style="width:${progress}%"></span></div>
          <div class="run-card-meta">
            <span>${formatDate(run.created_at)}</span>
            <button class="ghost-button" type="button" data-replay-id="${run.run_id}">Replay</button>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderArtifactPreview(artifact) {
  if (artifact.artifact_type === "spectrogram" || artifact.artifact_type === "waveform") {
    return `
      <div class="artifact-preview">
        <img src="${artifact.download_url}" alt="${artifact.label}" loading="lazy" />
      </div>
    `;
  }

  if (artifact.artifact_type === "audio_preview") {
    return `
      <div class="artifact-preview">
        <audio controls preload="none" src="${artifact.download_url}"></audio>
      </div>
    `;
  }

  return "";
}

function renderRunDetail() {
  const run = state.runs.find((item) => item.run_id === state.activeRunId);
  if (!run) {
    elements.detailTitle.textContent = "Select a run";
    elements.detailStatus.textContent = "waiting";
    elements.detailContent.className = "detail-content empty-state";
    elements.detailContent.textContent =
      "Choose a run from the registry to inspect its scenario results, slice scores, and generated artifacts.";
    return;
  }

  elements.detailTitle.textContent = `${run.model_name} · ${run.benchmark_name}`;
  elements.detailStatus.textContent = run.status;
  elements.detailStatus.dataset.status = run.status;

  if (!run.summary) {
    elements.detailContent.className = "detail-content empty-state";
    elements.detailContent.textContent = run.error_message
      ? `This run failed during evaluation: ${run.error_message}`
      : "This run is still processing. The page auto-refreshes while background scoring completes.";
    return;
  }

  const summaryCards = [
    ["Aggregate score", formatScore(run.summary.aggregate_score)],
    ["Average latency", formatLatency(run.summary.average_latency_ms)],
    ["Similarity", formatScore(run.summary.average_similarity_score)],
    ["Artifact rate", formatScore(run.summary.average_artifact_rate)]
  ];

  const slices = run.slices
    .map(
      (slice) => `
        <div class="slice-row">
          <strong>${slice.slice_name}</strong>
          <span>${formatScore(slice.score)} score · ${formatScore(slice.failure_rate)} failure · ${slice.trend}</span>
        </div>
      `
    )
    .join("");

  const scenarios = run.results
    .map(
      (result) => `
        <div class="scenario-row">
          <strong>${result.scenario_name}</strong>
          <span>${formatScore(result.robustness_score)} robustness</span>
          <span>${formatLatency(result.latency_ms)}</span>
          <span>${formatScore(result.similarity_score)} similarity</span>
          <span>${result.notes.join(", ")}</span>
        </div>
      `
    )
    .join("");

  const artifacts = run.artifacts
    .map(
      (artifact) => `
        <li>
          <div>
            <strong>${artifact.label}</strong>
            <p>${artifact.description}</p>
            ${renderArtifactPreview(artifact)}
          </div>
          <div>
            <span class="artifact-kind">${artifact.artifact_type}</span>
            <p>${artifact.size_kb.toFixed(1)} KB</p>
            <a class="artifact-link" href="${artifact.download_url}" target="_blank" rel="noreferrer">Open artifact</a>
          </div>
        </li>
      `
    )
    .join("");

  elements.detailContent.className = "detail-content";
  elements.detailContent.innerHTML = `
    <div class="detail-card">
      <div class="detail-summary">
        <div>
          <p class="eyebrow">Headline</p>
          <h4>${run.summary.headline}</h4>
        </div>
        <div class="detail-metadata">
          <span>workspace ${run.workspace_name}</span>
          <span>created ${formatDate(run.created_at)}</span>
          <span>${run.scenarios.length} scenarios</span>
          ${run.public_dataset_id ? `<span>public dataset ${run.public_dataset_id}</span>` : ""}
          ${run.source_run_id ? `<span>replay of ${run.source_run_id.slice(0, 8)}</span>` : ""}
        </div>
      </div>
      <div class="summary-grid">
        ${summaryCards
          .map(
            ([label, value]) => `
              <div class="summary-item">
                <span>${label}</span>
                <strong>${value}</strong>
              </div>
            `
          )
          .join("")}
      </div>
      <div class="detail-metadata detail-links">
        <span>dataset label ${run.dataset_name}</span>
        ${run.dataset_source_url ? `<a class="artifact-link" href="${run.dataset_source_url}" target="_blank" rel="noreferrer">Source dataset</a>` : ""}
      </div>
      <div class="slice-grid">${slices}</div>
      <div class="scenario-table">${scenarios}</div>
      <ul class="artifact-list">${artifacts}</ul>
    </div>
  `;
}

function renderCompare() {
  const completedRuns = state.runs.filter((run) =>
    ["completed", "replayed"].includes(run.status)
  );
  const previousLeft = elements.compareLeft.value;
  const previousRight = elements.compareRight.value;

  const options = completedRuns
    .map(
      (run) =>
        `<option value="${run.run_id}">${run.model_name} · ${run.benchmark_name} · ${run.run_id.slice(0, 8)}</option>`
    )
    .join("");

  elements.compareLeft.innerHTML = options;
  elements.compareRight.innerHTML = options;

  if (completedRuns.length) {
    const defaultLeft = completedRuns[0]?.run_id || "";
    const defaultRight = completedRuns[1]?.run_id || completedRuns[0]?.run_id || "";
    elements.compareLeft.value = completedRuns.some((run) => run.run_id === previousLeft)
      ? previousLeft
      : defaultLeft;
    elements.compareRight.value = completedRuns.some((run) => run.run_id === previousRight)
      ? previousRight
      : defaultRight;
  }

  if (completedRuns.length < 2) {
    elements.compareOutput.className = "compare-output empty-state";
    elements.compareOutput.textContent =
      "Complete at least two runs to unlock scenario-level comparison.";
    return;
  }

  if (!state.compareResult) {
    elements.compareOutput.className = "compare-output empty-state";
    elements.compareOutput.textContent =
      "Select two completed runs to compute scenario-level deltas.";
    return;
  }

  const result = state.compareResult;
  elements.compareOutput.className = "compare-output";
  elements.compareOutput.innerHTML = `
    <div class="compare-card">
      <div class="compare-summary">
        <div>
          <p class="eyebrow">${result.left_label}</p>
          <strong>vs ${result.right_label}</strong>
        </div>
        <div>
          <span class="status-badge" data-status="${result.score_delta >= 0 ? "completed" : "queued"}">${result.verdict}</span>
          <p>${result.headline}</p>
        </div>
      </div>
      <div class="compare-deltas">
        ${result.scenario_deltas
          .map(
            (delta) => `
              <div class="delta-row">
                <strong>${delta.scenario_name}</strong>
                <span>${formatScore(delta.left_score)} → ${formatScore(delta.right_score)}</span>
                <span data-trend="${delta.trend}">${delta.delta >= 0 ? "+" : ""}${formatScore(delta.delta)}</span>
              </div>
            `
          )
          .join("")}
      </div>
    </div>
  `;
}

async function refreshDashboard() {
  const [overview, runs, workspaces] = await Promise.all([
    fetchJson("/api/overview"),
    fetchJson("/api/runs"),
    fetchJson("/api/workspaces")
  ]);

  state.overview = overview;
  state.runs = runs;
  state.workspaces = workspaces;

  if (!state.activeRunId && runs.length) {
    state.activeRunId = runs[0].run_id;
  } else if (state.activeRunId && !runs.some((run) => run.run_id === state.activeRunId)) {
    state.activeRunId = runs[0]?.run_id || null;
  }

  renderWorkspaceSelect();
  renderWorkspaces();
  renderOverview();
  renderRunList();
  renderRunDetail();
  renderCompare();
}

async function createRun(event) {
  event.preventDefault();

  const template = state.catalog.benchmark_templates.find(
    (item) => item.benchmark_name === elements.benchmarkSelect.value
  );
  const scenarioMap = new Map(
    state.catalog.scenario_library.map((scenario) => [scenario.name, scenario])
  );
  const scenarios = getSelectedScenarioNames()
    .map((name) => scenarioMap.get(name))
    .filter(Boolean);

  try {
    elements.formFeedback.textContent = "Queueing evaluation...";
    const run = await fetchJson("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        benchmark_name: elements.benchmarkSelect.value,
        model_name: elements.modelSelect.value,
        workspace_id: elements.workspaceSelect.value,
        public_dataset_id: elements.publicDatasetSelect.value || null,
        dataset_name: elements.datasetInput.value || template?.dataset_name || "",
        seed: Number(elements.seedInput.value),
        notes: elements.notesInput.value.trim(),
        scenarios
      })
    });

    state.activeRunId = run.run_id;
    state.compareResult = null;
    elements.formFeedback.textContent = `Queued ${run.run_id.slice(0, 8)}. Background scoring is running.`;
    await refreshDashboard();
  } catch (error) {
    elements.formFeedback.textContent = error.message;
  }
}

async function createWorkspace(event) {
  event.preventDefault();

  const focusAreas = elements.workspaceFocusInput.value
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);

  try {
    elements.workspaceFeedback.textContent = "Creating workspace...";
    await fetchJson("/api/workspaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: elements.workspaceNameInput.value.trim(),
        owner: elements.workspaceOwnerInput.value.trim() || "Fatim Majumder",
        description: elements.workspaceDescriptionInput.value.trim(),
        focus_areas: focusAreas
      })
    });

    elements.workspaceForm.reset();
    elements.workspaceOwnerInput.value = "Fatim Majumder";
    elements.workspaceFeedback.textContent = "Workspace saved.";
    await refreshDashboard();
  } catch (error) {
    elements.workspaceFeedback.textContent = error.message;
  }
}

async function replayRun(runId) {
  try {
    await fetchJson(`/api/runs/${runId}/replay`, { method: "POST" });
    state.compareResult = null;
    await refreshDashboard();
  } catch (error) {
    elements.formFeedback.textContent = `Replay failed: ${error.message}`;
  }
}

async function compareRuns() {
  if (!elements.compareLeft.value || !elements.compareRight.value) {
    return;
  }

  if (elements.compareLeft.value === elements.compareRight.value) {
    elements.compareOutput.className = "compare-output empty-state";
    elements.compareOutput.textContent = "Choose two different runs to compare.";
    return;
  }

  try {
    state.compareResult = await fetchJson("/api/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        left_run_id: elements.compareLeft.value,
        right_run_id: elements.compareRight.value
      })
    });
    renderCompare();
  } catch (error) {
    elements.compareOutput.className = "compare-output empty-state";
    elements.compareOutput.textContent = error.message;
  }
}

function syncPublicDatasetSelection() {
  const datasetId = elements.publicDatasetSelect.value;
  if (!datasetId || !state.catalog) {
    const template = state.catalog?.benchmark_templates.find(
      (item) => item.benchmark_name === elements.benchmarkSelect.value
    );
    elements.datasetInput.value = template?.dataset_name || "";
    return;
  }

  const dataset = state.catalog.public_datasets.find((item) => item.dataset_id === datasetId);
  if (dataset) {
    elements.datasetInput.value = dataset.name;
  }
}

function attachEventListeners() {
  elements.benchmarkSelect.addEventListener("change", (event) => {
    renderScenarioGrid(event.target.value);
    syncPublicDatasetSelection();
  });
  elements.publicDatasetSelect.addEventListener("change", syncPublicDatasetSelection);
  elements.runForm.addEventListener("submit", createRun);
  elements.workspaceForm.addEventListener("submit", createWorkspace);
  elements.compareButton.addEventListener("click", compareRuns);

  elements.runsList.addEventListener("click", async (event) => {
    const replayButton = event.target.closest("[data-replay-id]");
    if (replayButton) {
      event.stopPropagation();
      await replayRun(replayButton.dataset.replayId);
      return;
    }

    const runCard = event.target.closest("[data-run-id]");
    if (runCard) {
      state.activeRunId = runCard.dataset.runId;
      renderRunList();
      renderRunDetail();
    }
  });

  elements.runsList.addEventListener("keydown", (event) => {
    const runCard = event.target.closest("[data-run-id]");
    if (!runCard) {
      return;
    }

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      state.activeRunId = runCard.dataset.runId;
      renderRunList();
      renderRunDetail();
    }
  });
}

async function init() {
  try {
    state.catalog = await fetchJson("/api/catalog");
    renderCatalog();
    attachEventListeners();
    await refreshDashboard();
    window.setInterval(refreshDashboard, 3000);
  } catch (error) {
    elements.formFeedback.textContent = error.message;
  }
}

window.addEventListener("DOMContentLoaded", init);
