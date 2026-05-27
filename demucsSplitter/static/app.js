const state = {
  videoId: null,
  autoRenderTimer: null,
  isRendering: false,
  needsRender: false,
  lastRenderedSignature: "",
};

const statusEl = document.getElementById("status");
const player = document.getElementById("videoPlayer");
const analysisBars = document.getElementById("analysisBars");
const analysisNote = document.getElementById("analysisNote");
const renderState = document.getElementById("renderState");
const mixNote = document.getElementById("mixNote");
const commentarySlider = document.getElementById("commentary");
const stadiumSlider = document.getElementById("stadium");
const commentaryVal = document.getElementById("commentaryVal");
const stadiumVal = document.getElementById("stadiumVal");
const applyMixBtn = document.getElementById("applyMixBtn");

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", Boolean(isError));
}

function sliderValues() {
  return {
    commentary: Number(commentarySlider?.value || 0),
    stadium: Number(stadiumSlider?.value || 0),
  };
}

function updateSliderLabels() {
  if (commentaryVal && commentarySlider) {
    commentaryVal.textContent = commentarySlider.value;
  }
  if (stadiumVal && stadiumSlider) {
    stadiumVal.textContent = stadiumSlider.value;
  }
}

function wireSliderEvents() {
  if (commentarySlider) {
    commentarySlider.addEventListener("input", () => {
      updateSliderLabels();
      updateRenderState("Changes pending");
    });
  }
  if (stadiumSlider) {
    stadiumSlider.addEventListener("input", () => {
      updateSliderLabels();
      updateRenderState("Changes pending");
    });
  }
}

function renderAnalysis(scores) {
  analysisBars.innerHTML = "";
  Object.entries(scores).forEach(([name, value]) => {
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `
      <span>${name}</span>
      <div class="track"><div class="fill" style="width:${value}%"></div></div>
      <strong>${value}%</strong>
    `;
    analysisBars.appendChild(row);
  });
}

function getRenderSignature() {
  return JSON.stringify(sliderValues());
}

function updateRenderState(text) {
  renderState.textContent = text;
}

function setControlsEnabled(enabled) {
  if (commentarySlider) commentarySlider.disabled = !enabled;
  if (stadiumSlider) stadiumSlider.disabled = !enabled;
  if (applyMixBtn) applyMixBtn.disabled = !enabled;
  document.querySelectorAll(".preset-btn").forEach((btn) => {
    btn.disabled = !enabled;
  });
}

const presetValues = {
  "commentary-reduce": { commentary: 55, stadium: 15 },
  "crowd-boost": { commentary: 25, stadium: 0 },
  balanced: { commentary: 35, stadium: 20 },
  "commentary-kill": { commentary: 100, stadium: 10 },
};

function applyPreset(key) {
  const preset = presetValues[key];
  if (!preset) return;
  if (commentarySlider) commentarySlider.value = preset.commentary;
  if (stadiumSlider) stadiumSlider.value = preset.stadium;
  updateSliderLabels();
  updateRenderState("Changes pending");
}

async function uploadVideo(file) {
  const form = new FormData();
  form.append("video", file);

  setStatus("Uploading and analyzing audio...");

  const response = await fetch("/upload", {
    method: "POST",
    body: form,
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Upload failed");
  }

  state.videoId = data.video_id;
  state.lastRenderedSignature = "";
  player.src = data.video_url;
  player.load();

  renderAnalysis(data.analysis.components || {});
  analysisNote.textContent = data.analysis.note || "";

  const recommendations = data.analysis.mix_recommendations || {};
  if (Number.isFinite(recommendations.commentary_reduction) && commentarySlider) {
    commentarySlider.value = recommendations.commentary_reduction;
  }
  if (Number.isFinite(recommendations.stadium_reduction) && stadiumSlider) {
    stadiumSlider.value = recommendations.stadium_reduction;
  }
  if (mixNote) {
    mixNote.textContent = recommendations.note || "";
  }

  updateSliderLabels();
  setControlsEnabled(true);

  setStatus(`Loaded ${data.filename}. Adjust sliders, then click Apply Mix.`);
  updateRenderState("Ready to apply");
}

async function renderProcessed() {
  if (!state.videoId) return;

  const signature = getRenderSignature();
  if (signature === state.lastRenderedSignature) {
    updateRenderState("No changes to apply");
    return;
  }

  if (state.isRendering) {
    state.needsRender = true;
    return;
  }

  state.isRendering = true;
  if (applyMixBtn) applyMixBtn.disabled = true;
  updateRenderState("Rendering stems and mixing...");
  setStatus("Rendering stem mix. First run may take a few minutes.", false);

  const wasPlaying = !player.paused;
  const currentTime = Number.isFinite(player.currentTime) ? player.currentTime : 0;

  try {
    const response = await fetch("/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        video_id: state.videoId,
        reductions: sliderValues(),
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      updateRenderState("Mix failed");
      throw new Error(data.details || data.error || "Mix failed");
    }

    const renderedUrl = `${data.output_url}?v=${Date.now()}`;
    player.src = renderedUrl;
    player.load();

    player.addEventListener(
      "loadedmetadata",
      () => {
        if (currentTime > 0 && Number.isFinite(player.duration)) {
          player.currentTime = Math.min(currentTime, Math.max(0, player.duration - 0.2));
        }
        if (wasPlaying) {
          player.play().catch(() => {
            // Browser autoplay may be blocked.
          });
        }
      },
      { once: true }
    );

    state.lastRenderedSignature = signature;
    updateRenderState("Mix applied");
    setStatus("Mix complete. Latest server-rendered audio synced.", false);
  } finally {
    state.isRendering = false;
    if (applyMixBtn) applyMixBtn.disabled = false;
  }

  if (state.needsRender) {
    state.needsRender = false;
    renderProcessed().catch((err) => {
      setStatus(err.message || "Mix failed", true);
    });
  }
}

document.getElementById("videoInput").addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;

  try {
    await uploadVideo(file);
  } catch (err) {
    setStatus(err.message || "Upload failed", true);
  }
});

document.querySelectorAll("[data-preset]").forEach((button) => {
  button.addEventListener("click", () => {
    applyPreset(button.dataset.preset);
  });
});

if (applyMixBtn) {
  applyMixBtn.addEventListener("click", () => {
    renderProcessed().catch((err) => {
      setStatus(err.message || "Mix failed", true);
      updateRenderState("Mix failed");
    });
  });
}

setControlsEnabled(false);
wireSliderEvents();
updateSliderLabels();
