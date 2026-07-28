const YT_PATTERNS = [
  "*://www.youtube.com/watch?v=*",
  "*://www.youtube.com/watch*",
  "*://youtu.be/*",
];

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "summarize-link",
    title: "Summarize video",
    contexts: ["link"],
    targetUrlPatterns: YT_PATTERNS,
  });
  chrome.contextMenus.create({
    id: "summarize-link-save",
    title: "Summarize and save video",
    contexts: ["link"],
    targetUrlPatterns: YT_PATTERNS,
  });
});

chrome.contextMenus.onClicked.addListener((info) => {
  if (info.menuItemId === "summarize-link" || info.menuItemId === "summarize-link-save") {
    const save = info.menuItemId === "summarize-link-save";
    const url = chrome.runtime.getURL(
      `result.html?url=${encodeURIComponent(info.linkUrl)}&save=${save}`
    );
    chrome.tabs.create({ url, active: false });
  }
});
