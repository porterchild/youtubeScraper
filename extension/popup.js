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

function summarize(videoUrl) {
  const save = $("save-checkbox").checked;
  const url = chrome.runtime.getURL(
    `result.html?url=${encodeURIComponent(videoUrl)}&save=${save}`
  );
  chrome.tabs.create({ url, active: false });
  window.close();
}

init();
