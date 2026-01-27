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
    try:
        print("Fetching channel page")
        response = requests.get(channel_url)
        html = response.text

        match = re.search(r'var ytInitialData = ({.*?});', html, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            print("Top level keys:", list(data.keys()))
            browse_results = data['contents']['twoColumnBrowseResultsRenderer']
            print("Browse results keys:", list(browse_results.keys()))
            tabs = browse_results['tabs']
            print("Number of tabs:", len(tabs))
            videos_tab = tabs[1]['tabRenderer']['content']
            print("Videos tab content keys:", list(videos_tab.keys()))
            rich_grid = videos_tab['richGridRenderer']
            print("Rich grid keys:", list(rich_grid.keys()))
            contents = rich_grid['contents']
            print("Number of contents:", len(contents))
            for i, item in enumerate(contents[:n]):
                print(f"Item {i} type: {list(item.keys())}")
                if 'richItemRenderer' in item:
                    rich_item = item['richItemRenderer']
                    print(f"Item {i} rich_item keys: {list(rich_item.keys())}")
                    if 'content' in rich_item:
                        renderer = rich_item['content']
                        print(f"Item {i} renderer keys: {list(renderer.keys())}")
                        if 'videoRenderer' in renderer:
                            video_renderer = renderer['videoRenderer']
                            video_id = video_renderer.get('videoId')
                            if video_id:
                                title_runs = video_renderer.get('title', {}).get('runs', [])
                                title = title_runs[0]['text'] if title_runs else video_id
                                print(f"Found video ID: {video_id}, Title: {title}")
                                videos.append((video_id, title))
                            else:
                                print(f"Item {i} no videoId in videoRenderer")
                        else:
                            print(f"Item {i} no videoRenderer in renderer")
                    else:
                        print(f"Item {i} no content in rich_item")
                else:
                    print(f"Item {i} is not richItemRenderer: {list(item.keys())}")
            return videos
        else:
            print("Could not find ytInitialData in HTML")
            return []
    except Exception as e:
        print(f"Error fetching channel page: {e}")
        return []


def get_video_details(video_url):
    video_id = video_url.split('v=')[1].split('&')[0]
    title = 'Unknown'
    channel_name = 'Unknown'
    try:
        print("Fetching video page")
        response = requests.get(video_url)
        html = response.text

        match = re.search(r'var ytInitialData = ({.*?});', html, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            # Title
            try:
                primary_info = data['contents']['twoColumnWatchNextResults']['results']['results']['contents'][0]['videoPrimaryInfoRenderer']
                title_runs = primary_info['title']['runs']
                title = title_runs[0]['text'] if title_runs else title
            except (KeyError, IndexError):
                print("Could not parse title from JSON")
            # Channel name - prefer handle from canonicalBaseUrl
            try:
                secondary_info = data['contents']['twoColumnWatchNextResults']['results']['results']['contents'][1]['videoSecondaryInfoRenderer']
                video_owner_renderer = secondary_info['owner']['videoOwnerRenderer']
                # Try to get handle
                try:
                    nav = video_owner_renderer['navigationEndpoint']['browseEndpoint']['canonicalBaseUrl']
                    channel_name = nav.lstrip('/@')
                except (KeyError, IndexError):
                    # Fallback to display name
                    channel_runs = video_owner_renderer['title']['runs']
                    channel_name = channel_runs[0]['text'] if channel_runs else 'Unknown'
            except (KeyError, IndexError):
                print("Could not parse channel name from JSON")
            print(f"Video ID: {video_id}, Title: {title}, Channel: {channel_name}")
        else:
            print("Could not find ytInitialData in HTML")
    except Exception as e:
        print(f"Error fetching video page: {e}")
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
                model="x-ai/grok-4.1-fast",
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
            for video_id, title in videos:
                print(f"\n--- Processing video: {title} ---")
                process_video(video_id, title, channel_name, no_save)
        else:
            print("No videos found in channel.")
