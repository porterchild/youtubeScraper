# YouTube Summarizer

Fetch transcripts from YouTube videos and summarize them with AI (via OpenRouter).

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file with your OpenRouter API key:

```
OPENROUTER_API_KEY=sk-or-v1-...
```

## Usage

### 1. Start the server (required for everything)

```bash
python server.py
```

The server runs on port 7823 and provides the API that the extension and CLI both use.

### 2. Browser Extension (the main way to use this)

The extension lets you summarize any YouTube video in one click.

**Install it:**

1. Open Chrome/Edge/Brave and go to `chrome://extensions`
2. Enable **Developer mode** (toggle in top-right)
3. Click **Load unpacked** and select the `extension/` folder in this project
4. The YT Summarizer icon will appear in your toolbar

**Use it:**

- **Popup** — Click the extension icon while on any YouTube video page. You'll see the video title, a Summarize button, and a Save checkbox. Click Summarize and the summary appears right in the popup.
- **Save checkbox** — When checked, the transcript and summary get saved to `channels/<channel>/<title>/` on disk. The preference is remembered across sessions.
- **Cached badge** — If the video was already summarized and saved, the server returns the cached result (no extra API call).
- **Right-click** — On any YouTube video link, right-click and choose **"Summarize video"** or **"Summarize and save video"**. A new tab opens with the result.

**Extension files (in `extension/`):**

| File | Purpose |
|---|---|
| `manifest.json` | Chrome extension manifest v3 |
| `popup.html` / `popup.js` / `popup.css` | Popup UI shown when clicking the toolbar icon |
| `background.js` | Registers right-click context menu items on YouTube links |
| `result.html` / `result.js` / `result.css` | Full-page result view (opened via right-click) |

### 3. CLI (batch processing)

```bash
# Summarize a single video (saves to disk)
python youtube_summarizer.py "https://www.youtube.com/watch?v=..."

# Print summary without saving
python youtube_summarizer.py "https://www.youtube.com/watch?v=..." --no-save

# Summarize the latest N videos from a channel
python youtube_summarizer.py "https://www.youtube.com/@channelname" --latest 5
```

### API endpoints (for scripting)

| Method | Path | Body | Description |
|---|---|---|---|
| `POST` | `/summary` | `{"url": "...", "save": true/false}` | Summarize a video |
| `POST` | `/save` | `{"video_id": "..."}` | Flush a cached result to disk |

## Output structure

Videos saved to disk go here:

```
channels/
  └── <channel_name>/
      └── <video_title>/
          ├── transcript.txt
          └── summary.txt
```

## How it works

1. Fetches video metadata via YouTube's oEmbed API
2. Downloads the transcript via `youtube-transcript-api`
3. Sends the transcript to an LLM (DeepSeek V4 Flash on OpenRouter) with a content-aware prompt that tailors the summary structure to the video type (descriptive, normative, narrative, etc.)