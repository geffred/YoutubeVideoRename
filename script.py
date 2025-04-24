import os
import time
import isodate
from datetime import datetime
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
MAX_RETRIES = 3
REQUEST_DELAY = 2  # seconds

def authenticate_youtube():
    creds = None
    token_file = "token.json"
    
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception as e:
            print(f"⚠️ Token load error: {e}")
            os.remove(token_file)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"⚠️ Refresh error: {e}")
                os.remove(token_file)
                return authenticate_youtube()
        else:
            try:
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                    "client_secrets.json", SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                print(f"⚠️ Authentication failed: {e}")
                raise

        with open(token_file, "w") as token:
            token.write(creds.to_json())

    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)

def is_long_video(duration_iso):
    """Check if a video is longer than 60 seconds using isodate."""
    try:
        duration = isodate.parse_duration(duration_iso)
        return duration.total_seconds() > 60
    except Exception as e:
        print(f"⚠️ Duration parsing error: {e}")
        return False

def get_my_videos(youtube):
    try:
        channel_response = youtube.channels().list(
            part="contentDetails",
            mine=True,
            fields="items/contentDetails/relatedPlaylists/uploads"
        ).execute()
        uploads_playlist = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

        long_videos = []
        next_page_token = None
        
        while True:
            playlist_response = youtube.playlistItems().list(
                part="snippet",
                playlistId=uploads_playlist,
                maxResults=50,
                pageToken=next_page_token,
                fields="nextPageToken,items/snippet(resourceId/videoId,title)"
            ).execute()
            
            video_batch = [(item['snippet']['resourceId']['videoId'], 
                            item['snippet']['title']) 
                           for item in playlist_response['items']]
            
            if video_batch:
                video_ids = [vid for vid, _ in video_batch]
                duration_response = youtube.videos().list(
                    part="contentDetails",
                    id=",".join(video_ids),
                    fields="items(id,contentDetails/duration)"
                ).execute()
                
                duration_map = {
                    item['id']: item['contentDetails']['duration'] 
                    for item in duration_response['items']
                }
                
                for video_id, title in video_batch:
                    if is_long_video(duration_map.get(video_id, 'PT60S')):
                        long_videos.append((video_id, title))
            
            next_page_token = playlist_response.get('nextPageToken')
            if not next_page_token or len(long_videos) >= 100:
                break
            time.sleep(REQUEST_DELAY)
            
        return long_videos
    except Exception as e:
        print(f"Error fetching videos: {e}")
        return []

def rename_video(youtube, video_id, old_title, retry_count=0):
    try:
        video_response = youtube.videos().list(
            part="snippet",
            id=video_id,
            fields="items(snippet(title,description,categoryId))"
        ).execute()
        
        snippet = video_response['items'][0]['snippet']
        
        today = datetime.now()
        months_fr = {
            1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 
            5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août", 
            9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
        }
        days_fr = [
            "Lundi", "Mardi", "Mercredi", "Jeudi", 
            "Vendredi", "Samedi", "Dimanche"
        ]
        
        day_name = days_fr[today.weekday()]
        month_name = months_fr[today.month]
        
        new_title = (
            f"Prière du {day_name} {today.day:02d} {month_name} {today.year} "
            "Psaume 91 🙏 | Prière du Matin Pour Bien Commencer la Journée"
        )
        
        if snippet['title'] == new_title:
            print(f"⏩ Video {video_id} already has correct title")
            return True
        
        youtube.videos().update(
            part="snippet",
            body={
                "id": video_id,
                "snippet": {
                    "title": new_title,
                    "categoryId": snippet.get('categoryId', '22'),
                    "description": snippet.get('description', '')
                }
            }
        ).execute()
        
        print(f"✅ Renamed: '{old_title}' → '{new_title}'")
        return True
        
    except HttpError as e:
        if e.resp.status == 403 and 'quotaExceeded' in str(e):
            print("❌ Quota exceeded - stopping process")
            raise
        elif retry_count < MAX_RETRIES:
            wait_time = (2 ** retry_count) * 5
            print(f"⚠️ Retry {retry_count+1} in {wait_time}s for {video_id}")
            time.sleep(wait_time)
            return rename_video(youtube, video_id, old_title, retry_count+1)
        else:
            print(f"❌ Failed after {MAX_RETRIES} tries for {video_id}: {e}")
            return False
    except Exception as e:
        print(f"❌ Error renaming {video_id}: {e}")
        return False

def auto_rename():
    title_base = [
        "Prière puissante Psaume 91| Prière du matin Pour Bien Commencer la Journée",
        "Prière Puissante de Protection ✨ Psaumes 23, 70, 91 | Prière du Matin pour une Journée Bénie 🙏",
        "Prière Puissante de Protection 🙏 | Prière du Matin pour Bien Commencer la Journée avec Dieu ✨",
        "Bénédictions et Protection Divine pour Vous 🙏 Prière du Matin Pour Bien Commencer la Journée",
        "La Prière qui va REVOLUTIONNER Votre Carême | Prière du matin Pour Bien Commencer la Journée",
        "Commencez votre Journée avec Bénédictions Psaume 91 | Prière du matin Pour Bien Commencer la Journée",
    ]
    
    try:
        youtube = authenticate_youtube()
        print("🔍 Fetching your videos...")
        
        videos = get_my_videos(youtube)
        if not videos:
            print("⚠️ No videos found or error fetching videos")
            return
        
        print(f"📹 Found {len(videos)} long videos to process")
        success_count = 0
        
        for idx, (video_id, old_title) in enumerate(videos, 1):
            if old_title in title_base:
                print(f"⏩ Skipping video with 'great title'")
                continue
                
            print(f"\n🔄 Processing video {idx}/{len(videos)}")
            if rename_video(youtube, video_id, old_title):
                success_count += 1
                
            if idx < len(videos):
                time.sleep(REQUEST_DELAY)
        
        print(f"\n🎉 Done! Successfully processed {success_count}/{len(videos)} videos")
        
    except HttpError as e:
        if 'quotaExceeded' in str(e):
            print("❌ Quota exceeded - try again tomorrow or request higher quota")
        else:
            print(f"❌ YouTube API error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    auto_rename()
