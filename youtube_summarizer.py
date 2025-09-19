import os
import time
import requests
import json
import re
import sys
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
            # Channel name
            try:
                secondary_info = data['contents']['twoColumnWatchNextResults']['results']['results']['contents'][1]['videoSecondaryInfoRenderer']
                channel_runs = secondary_info['owner']['videoOwnerRenderer']['title']['runs']
                channel_name = channel_runs[0]['text'] if channel_runs else channel_name
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


def process_video(video_id, title, channel_name):
    # Sanitize title for folder name
    title_folder = re.sub(r'[<>:"/\\|?*]', '_', title)
    
    # Create directory structure
    video_dir = os.path.join('channels', channel_name, title_folder)
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
    print("Video Summary:")
    print(summary)

def summarize_transcript(transcript):
    if not transcript:
        return "No transcript available."
    
    prompt = f"Summarize the narrative, ideas and key points from this YouTube video transcript in a concise paragraph. Emphasize the more unituitive or novel bits:\n\n{transcript}"
    
    response = client.chat.completions.create(
        model="deepseek/deepseek-chat-v3.1:free",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    # Rate limiting: wait 10 seconds after API request
    time.sleep(10)
    
    return response.choices[0].message.content

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python youtube_summarizer.py <channel_url or video_url>")
        print("Example: python youtube_summarizer.py https://www.youtube.com/@PredictiveHistory")
        print("Or: python youtube_summarizer.py https://www.youtube.com/watch?v=-jF9gW2r_bk")
        sys.exit(1)
    
    input_url = sys.argv[1]
    
    if 'v=' in input_url:
        # Video URL
        print("Processing single video")
        video_id, title, channel_name = get_video_details(input_url)
        process_video(video_id, title, channel_name)
    else:
        # Channel URL
        if not input_url.endswith('/videos'):
            channel_url = input_url + '/videos'
        else:
            channel_url = input_url
        channel_name = channel_url.split('/@')[1].split('/')[0]
        print(f"Processing channel: {channel_name}")
        videos = get_latest_n_videos(channel_url, n=5)
        if videos:
            for video_id, title in videos:
                print(f"\n--- Processing video: {title} ---")
                process_video(video_id, title, channel_name)
        else:
            print("No videos found in channel.")
