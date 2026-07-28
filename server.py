import os
import re
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from youtube_summarizer import get_video_details, get_transcript, summarize_transcript

PORT = 7823


def resolve_video_id(video_url_or_id):
    """Extract video_id from a YouTube URL, or return bare ID as-is."""
    if not video_url_or_id:
        return None
    # If it looks like a full URL, extract v= parameter
    if "youtube.com" in video_url_or_id or "youtu.be" in video_url_or_id:
        match = re.search(r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})', video_url_or_id)
        if match:
            return match.group(1)
    # If it's an 11-char alphanumeric ID, use directly
    if re.match(r'^[a-zA-Z0-9_-]{11}$', video_url_or_id):
        return video_url_or_id
    return None

# In-memory cache keyed by video_id so /save can flush without re-fetching
_cache = {}  # video_id -> {title, channel_name, transcript, summary, video_dir, ...}


def video_dir_paths(channel_name, title):
    title_folder = re.sub(r'[<>:"/\\|?*]', '_', title)
    video_dir = os.path.join("channels", channel_name.lower(), title_folder)
    return video_dir, os.path.join(video_dir, "summary.txt"), os.path.join(video_dir, "transcript.txt")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[server] {format % args}")

    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self._serve_html("index.html")
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length))
        except Exception:
            self.send_json(400, {"error": "Invalid JSON"})
            return

        if path == "/summary":
            self._handle_summary(data)
        elif path == "/save":
            self._handle_save(data)
        else:
            self.send_json(404, {"error": "Not found"})

    def _serve_html(self, filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()
            body = content.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_json(404, {"error": "Page not found"})

    def _handle_summary(self, data):
        video_url = data.get("url")
        video_id = data.get("video_id")
        save = bool(data.get("save", False))

        # Accept either url or video_id
        raw = video_url or video_id
        if not raw:
            self.send_json(400, {"error": "Missing 'url' or 'video_id'"})
            return

        resolved_id = resolve_video_id(raw)
        if not resolved_id:
            self.send_json(400, {"error": "Could not parse video ID from input"})
            return

        try:
            # If a full URL was given, use it for metadata; otherwise build a URL from the ID
            if video_url and ("youtube.com" in video_url or "youtu.be" in video_url):
                fetch_url = video_url
            else:
                fetch_url = f"https://www.youtube.com/watch?v={resolved_id}"
            video_id, title, channel_name = get_video_details(fetch_url)
            video_dir, summary_path, transcript_path = video_dir_paths(channel_name, title)

            # Return cached summary if it exists on disk
            if save and os.path.exists(summary_path):
                with open(summary_path, "r", encoding="utf-8") as f:
                    summary = f.read()
                self.send_json(200, {"title": title, "channel": channel_name, "summary": summary, "cached": True, "saved": True})
                return

            transcript = get_transcript(video_id)
            if not transcript:
                self.send_json(200, {"title": title, "channel": channel_name, "summary": "No transcript available for this video.", "cached": False, "saved": False})
                return

            summary = summarize_transcript(transcript)

            # Always cache in memory so /save can flush later
            _cache[video_id] = {
                "title": title,
                "channel_name": channel_name,
                "transcript": transcript,
                "summary": summary,
                "video_dir": video_dir,
                "summary_path": summary_path,
                "transcript_path": transcript_path,
            }

            if save:
                os.makedirs(video_dir, exist_ok=True)
                with open(transcript_path, "w", encoding="utf-8") as f:
                    f.write(transcript)
                with open(summary_path, "w", encoding="utf-8") as f:
                    f.write(summary)

            self.send_json(200, {"video_id": video_id, "title": title, "channel": channel_name, "summary": summary, "cached": False, "saved": save})
        except Exception as e:
            self.send_json(500, {"error": str(e)})

    def _handle_save(self, data):
        video_id = data.get("video_id")
        if not video_id:
            self.send_json(400, {"error": "Missing 'video_id'"})
            return

        entry = _cache.get(video_id)
        if not entry:
            self.send_json(404, {"error": "No cached result for this video. Summarize it first."})
            return

        try:
            os.makedirs(entry["video_dir"], exist_ok=True)
            with open(entry["transcript_path"], "w", encoding="utf-8") as f:
                f.write(entry["transcript"])
            with open(entry["summary_path"], "w", encoding="utf-8") as f:
                f.write(entry["summary"])
            self.send_json(200, {"saved": True})
        except Exception as e:
            self.send_json(500, {"error": str(e)})


if __name__ == "__main__":
    print(f"Starting server on http://localhost:{PORT}")
    HTTPServer(("localhost", PORT), Handler).serve_forever()
