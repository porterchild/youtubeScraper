const SERVER = "http://localhost:7823";

const $ = (id) => document.getElementById(id);

async function getCurrentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function extractVideoUrl(tabUrl) {
  try {
    const u = new URL(tabUrl);
    if (u.hostname.includes("youtube.com") && u.pathname === "/watch" && u.searchParams.get("v")) {
      return `https://www.youtube.com/watch?v=${u.searchParams.get("v")}`;
    }
  } catch {}
  return null;
}

function setStatus(msg, isError = false) {
  const el = $("status");
  el.textContent = msg;
  el.className = "status" + (isError ? " error" : "");
  el.classList.remove("hidden");
}

function clearStatus() {
  $("status").classList.add("hidden");
}

async function init() {
  const tab = await getCurrentTab();
  const videoUrl = extractVideoUrl(tab?.url || "");

  if (!videoUrl) {
    $("not-youtube").classList.remove("hidden");
    return;
  }

  $("main-view").classList.remove("hidden");
  $("video-title").textContent = tab.title?.replace(" - YouTube", "").trim() || videoUrl;

  // Restore saved checkbox preference
  const { saveDefault } = await chrome.storage.local.get("saveDefault");
  $("save-checkbox").checked = saveDefault ?? true;
  $("save-checkbox").addEventListener("change", () => {
    chrome.storage.local.set({ saveDefault: $("save-checkbox").checked });
  });

  $("summarize-btn").addEventListener("click", () => summarize(videoUrl));
}

async function summarize(videoUrl) {
  const btn = $("summarize-btn");
  const save = $("save-checkbox").checked;

  btn.disabled = true;
  btn.textContent = "Working...";
  clearStatus();
  $("result").classList.add("hidden");
  setStatus(save ? "Summarizing and saving to channels/..." : "Summarizing (not saving)...");

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
    $("video-title").textContent = data.title || $("video-title").textContent;
    $("cached-badge").classList.toggle("hidden", !data.cached);
    $("saved-badge").classList.toggle("hidden", !data.saved);
    $("summary-text").textContent = data.summary;
    $("result").classList.remove("hidden");
  } catch {
    setStatus(`Could not reach server at ${SERVER}. Is server.py running?`, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Summarize";
  }
}

init();
