const SERVER = "http://localhost:7823";

const $ = (id) => document.getElementById(id);

const params = new URLSearchParams(location.search);
const videoUrl = params.get("url");
const save = params.get("save") === "true";

function setStatus(msg, isError = false) {
  const el = $("status");
  el.textContent = msg;
  el.className = "status" + (isError ? " error" : "");
  el.classList.remove("hidden");
}

function clearStatus() {
  $("status").classList.add("hidden");
}

async function summarize() {
  const btn = $("summarize-btn");
  btn.disabled = true;
  btn.textContent = "Working...";
  clearStatus();
  $("result").classList.add("hidden");
  setStatus(save ? "Summarizing and saving to channels/..." : "Summarizing...");

  try {
    const res = await fetch(`${SERVER}/summary`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: videoUrl, save }),
    });

    const data = await res.json();

    if (!res.ok) {
      setStatus(data.error || "Server error", true);
      return;
    }

    clearStatus();
    document.title = data.title ? `${data.title} — YT Summarizer` : "YT Summarizer";
    $("video-title").textContent = data.title || "";
    $("video-title").classList.toggle("hidden", !data.title);
    $("cached-badge").classList.toggle("hidden", !data.cached);
    $("saved-badge").classList.toggle("hidden", !data.saved);
    $("summary-text").textContent = data.summary;
    $("result").classList.remove("hidden");

    if (!save && data.video_id) {
      const saveBtn = $("save-now-btn");
      saveBtn.classList.remove("hidden");
      saveBtn.onclick = () => saveNow(data.video_id, saveBtn);
    }
  } catch {
    setStatus(`Could not reach server at ${SERVER}. Is server.py running?`, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Summarize";
  }
}

async function saveNow(videoId, saveBtn) {
  saveBtn.disabled = true;
  saveBtn.textContent = "Saving...";

  try {
    const res = await fetch(`${SERVER}/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_id: videoId }),
    });

    const data = await res.json();

    if (!res.ok) {
      saveBtn.textContent = data.error || "Save failed";
      saveBtn.disabled = false;
      return;
    }

    saveBtn.textContent = "Saved to channels/";
    $("saved-badge").classList.remove("hidden");
  } catch {
    saveBtn.textContent = "Save failed — is server.py running?";
    saveBtn.disabled = false;
  }
}

function init() {
  if (!videoUrl) {
    setStatus("No video URL provided.", true);
    return;
  }

  $("video-url").textContent = videoUrl;
  $("summarize-btn").addEventListener("click", summarize);
  summarize();
}

init();
