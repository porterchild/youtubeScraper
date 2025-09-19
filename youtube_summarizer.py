import os
import time
import requests
import json
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

CHANNEL_URL = "https://www.youtube.com/@PredictiveHistory/videos"

# Extract channel name from URL
CHANNEL_NAME = CHANNEL_URL.split('/@')[1].split('/')[0]

def get_latest_video_id(channel_url):
    try:
        if os.path.exists('channel_page.html'):
            print("Loading from local channel_page.html")
            with open('channel_page.html', 'r', encoding='utf-8') as f:
                html = f.read()
        else:
            print("Fetching channel page")
            response = requests.get(channel_url)
            html = response.text

            # Save HTML for debugging
            with open('channel_page.html', 'w', encoding='utf-8') as f:
                f.write(html)
            print("Saved HTML to channel_page.html for debugging")

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
            video_id = None
            title = None
            for i, item in enumerate(contents):
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
                                break
                            else:
                                print(f"Item {i} no videoId in videoRenderer")
                        else:
                            print(f"Item {i} no videoRenderer in renderer")
                    else:
                        print(f"Item {i} no content in rich_item")
            if video_id:
                print(f"Latest video ID: {video_id}")
                return video_id, title
            else:
                print("No video found in contents")
                return None
        else:
            print("Could not find ytInitialData in HTML")
            return None
    except Exception as e:
        print(f"Error fetching channel page: {e}")
        return None

def get_transcript(video_id):
    try:
        ytt_api = YouTubeTranscriptApi()
        # Try English first
        fetched = ytt_api.fetch(video_id, languages=['en'])
        print("Fetched English transcript")
        return " ".join([snippet.text for snippet in fetched])
    except:
        try:
            # Fall back to any available (auto-generated)
            fetched = ytt_api.fetch(video_id)
            print("Fetched transcript (auto-generated or other language)")
            return " ".join([snippet.text for snippet in fetched])
        except Exception as e:
            print(f"Error fetching transcript: {e}")
            return None

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
    result = get_latest_video_id(CHANNEL_URL)
    if result:
        video_id, title = result
        transcript = get_transcript(video_id)
        
        # Sanitize title for folder name
        title_folder = re.sub(r'[<>:"/\\|?*]', '_', title)
        
        # Create directory structure
        video_dir = os.path.join('channels', CHANNEL_NAME, title_folder)
        os.makedirs(video_dir, exist_ok=True)
        
        # Save transcript
        transcript_path = os.path.join(video_dir, 'transcript.txt')
        if transcript:
            with open(transcript_path, 'w', encoding='utf-8') as f:
                f.write(transcript)
            print(f"Saved transcript to {transcript_path}")
            
            # Summarize and save
            summary = summarize_transcript(transcript)
            summary_path = os.path.join(video_dir, 'summary.txt')
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(summary)
            print(f"Saved summary to {summary_path}")
            print("Video Summary:")
            print(summary)
        else:
            # Save placeholder for no transcript
            placeholder = "No transcript available."
            with open(transcript_path, 'w', encoding='utf-8') as f:
                f.write(placeholder)
            print(f"Saved placeholder to {transcript_path}")
            print("No transcript available for the latest video.")
    else:
        print("Could not fetch latest video ID from channel.")
