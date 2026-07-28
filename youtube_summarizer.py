import os
import time
import requests
import json
import re
import argparse
import re
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
import httpx
from openai import OpenAI


# Load environment variables
load_dotenv()

# Initialize OpenAI client for OpenRouter
http_client = httpx.Client()
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    http_client=http_client,
)

def get_latest_n_videos(channel_url, n=5):
    videos = []
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
    })

    def extract_videos_from_contents(contents):
        found = []
        continuation_token = None
        for item in contents:
            if 'richItemRenderer' in item:
                renderer = item['richItemRenderer'].get('content', {}).get('videoRenderer')
                if renderer:
                    video_id = renderer.get('videoId')
                    if video_id:
                        title_runs = renderer.get('title', {}).get('runs', [])
                        title = title_runs[0]['text'] if title_runs else video_id
                        found.append((video_id, title))
            elif 'continuationItemRenderer' in item:
                continuation_token = item['continuationItemRenderer']['continuationEndpoint']['continuationCommand']['token']
        return found, continuation_token

    try:
        print("Fetching channel page")
        response = session.get(channel_url)
        html = response.text

        match = re.search(r'var ytInitialData = ({.*?});', html, re.DOTALL)
        if not match:
            print("Could not find ytInitialData in HTML")
            return []

        data = json.loads(match.group(1))
        
        # Get API key and client context for continuations
        api_key = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)
        api_key = api_key.group(1) if api_key else None
        client_version = re.search(r'"INNERTUBE_CONTEXT_CLIENT_VERSION":"(.*?)"', html)
        client_version = client_version.group(1) if client_version else "2.20240101.01.00"

        # Initial videos
        try:
            tabs = data['contents']['twoColumnBrowseResultsRenderer']['tabs']
            videos_tab = next((t['tabRenderer']['content'] for t in tabs if 'tabRenderer' in t and t['tabRenderer'].get('title') == 'Videos'), None)
            if not videos_tab:
                videos_tab = tabs[1]['tabRenderer']['content']
            
            contents = videos_tab['richGridRenderer']['contents']
            new_videos, token = extract_videos_from_contents(contents)
            for v_id, v_title in new_videos:
                if len(videos) < n:
                    print(f"Found video ID: {v_id}, Title: {v_title}")
                    videos.append((v_id, v_title))
            
            # Pagination
            while len(videos) < n and token and api_key:
                time.sleep(2)  # Delay between pagination requests
                print(f"Fetching more videos (current count: {len(videos)})")
                browse_url = f"https://www.youtube.com/youtubei/v1/browse?key={api_key}"
                payload = {
                    "context": {
                        "client": {
                            "clientName": "WEB",
                            "clientVersion": client_version
                        }
                    },
                    "continuation": token
                }
                resp = session.post(browse_url, json=payload)
                if resp.status_code != 200:
                    break
                
                cont_data = resp.json()
                # Continuation response structure is different
                # onResponseReceivedActions -> appendContinuationItemsAction -> continuationItems
                actions = cont_data.get('onResponseReceivedActions', [])
                if not actions:
                    break
                
                cont_items = actions[0].get('appendContinuationItemsAction', {}).get('continuationItems', [])
                new_videos, token = extract_videos_from_contents(cont_items)
                for v_id, v_title in new_videos:
                    if len(videos) < n:
                        print(f"Found video ID: {v_id}, Title: {v_title}")
                        videos.append((v_id, v_title))
                    else:
                        break
                        
        except (KeyError, IndexError, StopIteration) as e:
            print(f"Error navigating channel JSON: {e}")
        
        return videos
    except Exception as e:
        print(f"Error fetching channel page: {e}")
        return []


def get_video_details(video_url):
    video_id = video_url.split('v=')[1].split('&')[0]
    title = 'Unknown'
    channel_name = 'Unknown'
    
    try:
        print("Fetching video metadata via oEmbed")
        oembed_url = f"https://www.youtube.com/oembed?url={video_url}&format=json"
        response = requests.get(oembed_url)
        if response.status_code == 200:
            data = response.json()
            title = data.get('title', title)
            channel_name = data.get('author_name', channel_name)
            # If it's a handle URL, try to extract the handle
            author_url = data.get('author_url', '')
            if '/@' in author_url:
                channel_name = author_url.split('/@')[-1]
            
            print(f"Video ID: {video_id}, Title: {title}, Channel: {channel_name}")
    except Exception as e:
        print(f"oEmbed failed: {e}")

    return video_id, title, channel_name

def get_transcript(video_id):
    try:
        ytt_api = YouTubeTranscriptApi()
        # Try English first
        fetched = ytt_api.fetch(video_id, languages=['en'])
        print("Fetched English transcript")
        transcript = " ".join([snippet.text for snippet in fetched])
        time.sleep(10)  # Rate limiting for YouTube API
        return transcript
    except:
        try:
            # Fall back to any available (auto-generated)
            fetched = ytt_api.fetch(video_id)
            print("Fetched transcript (auto-generated or other language)")
            transcript = " ".join([snippet.text for snippet in fetched])
            time.sleep(10)  # Rate limiting for YouTube API
            return transcript
        except Exception as e:
            print(f"Error fetching transcript: {e}")
            return None


def process_video(video_id, title, channel_name, no_save=False):
    if no_save:
        transcript = get_transcript(video_id)
        if transcript:
            summary = summarize_transcript(transcript)
            print(f"Video Summary for {title}:")
            print(summary)
        else:
            print(f"No transcript available for {title}")
        return
    
    # Sanitize title for folder name
    title_folder = re.sub(r'[<>:"/\\|?*]', '_', title)
    
    # Create directory structure with lowercase channel name
    video_dir = os.path.join('channels', channel_name.lower(), title_folder)
    os.makedirs(video_dir, exist_ok=True)
    
    summary_path = os.path.join(video_dir, 'summary.txt')
    transcript_path = os.path.join(video_dir, 'transcript.txt')
    
    if os.path.exists(summary_path):
        print(f"Already processed: {title}")
        return
    
    transcript = None
    if os.path.exists(transcript_path):
        with open(transcript_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if content != "No transcript available.":
                transcript = content
                print(f"Loaded existing transcript for {title}")
            else:
                print(f"No transcript available for {title}, skipping summary")
                return
    else:
        transcript = get_transcript(video_id)
        if transcript:
            with open(transcript_path, 'w', encoding='utf-8') as f:
                f.write(transcript)
            print(f"Saved transcript to {transcript_path}")
        else:
            # Save placeholder for no transcript
            placeholder = "No transcript available."
            with open(transcript_path, 'w', encoding='utf-8') as f:
                f.write(placeholder)
            print(f"Saved placeholder to {transcript_path}")
            print("No transcript available for the video.")
            return
    
    # Summarize and save
    summary = summarize_transcript(transcript)
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(summary)
    print(f"Saved summary to {summary_path}")
    print("Video Summary:\n")
    print(summary)

def summarize_transcript(transcript):
    if not transcript:
        return "No transcript available."
    
    content_types_prompt = """Recognize what kind of video it is, and tailor your reponse to fit it.
    Some of the common types are Descriptive (lays out a theory of some reality, or a worldview on a topic), Normative (says how something 'should' be), Predictive (predicts outcomes from assumptions and their interaction), Interpretive (casts data or events into a certain paradigm), Narrative (tells a story with plot points, imagery, emotions).
    So if it's Descriptive content, show the claims, their evidence and mechanisms, analogies, counterevidence, etc, to present the descriptive theory underlying the content.
        For example, a video on bureaucracy might look like this: 

        Video Type: Descriptive
        Central claims: Bureaucracy supresses innovation and creates totalitarianism

        CLAIM: Bureaucracy supresses innovation
            MECHANISM: Centralizes power and resists change to protect own interests
            MECHANISM: Creates regulations that favor stability over experimentation
            EVIDENCE: 19th-century China - regulated factories out of industrial dominance
            EVIDENCE: Islamic Golden Age - clergy/nobility suppressed merchant innovation
            EVIDENCE: Post-WWII Britain - state control over 2/3 of economy led to stagnation

        CLAIM: Bureaucracy creates totalitarianism
            MECHANISM: Needs to justify own power through expanded control
            MECHANISM: Converts governance into "false religion" of infinite progress
            EVIDENCE: French Revolution - bureaucratic uprising led to instability then Napoleon
            EVIDENCE: Soviet Union - managerial class created total state control
            EVIDENCE: Modern Britain - surveillance state, censorship, intimate life control
        
        ...ends with overall summary...
        
    In a similarly principled and structured way, for other video types:
    If it's Normative, lay out the values, prescriptions, justifications, and trade-offs.
    If it's Predictive, lay out the assumptions, their interactions, of course predictions, confidence, timeline, etc.
    If it's Interpretive, show the frame, patterns, analogies, implications, etc.
    If it's Narrative, tell a condensed version of the story and summarize the emphasis and experience.
    Etc.
    You aren't limited to these types of content. Whatever the type, represent its core ideas in a way that flows naturally for that type.
    """

    prompt = f"Summarize the video transcript. Ignore off-topic content like Patreon plugs, or sponsorships. Don't use markdown or tables.\n\n{content_types_prompt} \n\nHere is the transcript:\n\n{transcript}"
    
    max_retries = 10
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="deepseek/deepseek-v4-flash",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Rate limiting: wait 10 seconds after API request
            time.sleep(10)
            
            return response.choices[0].message.content
        except Exception as e:
            if "RateLimitError" in str(type(e)) or "429" in str(e):
                if attempt < max_retries - 1:
                    print(f"Rate limit hit, retrying in 5 seconds... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(5)
                    continue
                else:
                    print(f"Max retries reached for summary generation: {e}")
                    return "Summary generation failed after retries due to rate limit."
            else:
                print(f"Error generating summary: {e}")
                return "Summary generation failed due to API error."

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube Transcript Summarizer")
    parser.add_argument("url", help="Channel or video URL")
    parser.add_argument("-n", "--no-save", action="store_true", help="Print summary without saving files")
    parser.add_argument("--latest", type=int, default=5, help="Number of latest videos to process for channels (default: 5)")
    args = parser.parse_args()
    
    input_url = args.url
    no_save = args.no_save
    n_latest = args.latest
    
    if 'v=' in input_url:
        # Video URL
        print("Processing single video")
        video_id, title, channel_name = get_video_details(input_url)
        process_video(video_id, title, channel_name, no_save)
    else:
        # Channel URL
        if not input_url.endswith('/videos'):
            channel_url = input_url + '/videos'
        else:
            channel_url = input_url
        match = re.search(r'youtube\.com/(?:@)?([^/]+)', channel_url)
        if match:
            channel_name = match.group(1)
        else:
            print("Could not extract channel name from URL")
            sys.exit(1)
        print(f"Processing channel: {channel_name}")
        videos = get_latest_n_videos(channel_url, n=n_latest)
        if videos:
            print(f"Found {len(videos)} videos to process.")
            for i, (video_id, title) in enumerate(videos):
                print(f"\n--- Processing video {i+1}/{len(videos)}: {title} ---")
                process_video(video_id, title, channel_name, no_save)
        else:
            print("No videos found in channel.")
