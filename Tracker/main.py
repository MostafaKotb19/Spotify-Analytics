import functions_framework
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pytz

# --- Configuration ---
CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
REDIRECT_URI = "https://example.org/callback"
REFRESH_TOKEN = "YOUR_REFRESH_TOKEN"

# Google Sheets setup
GOOGLE_SHEETS_CREDENTIALS_FILE = "sheets.json"
GOOGLE_SHEET_NAME = "Spotify Data"

# Define the required Spotify API scope
SCOPE = "user-read-currently-playing"

# Initialize last_state to track the last known state of playback
last_state = {"is_playing": None}

def get_spotify_client():
    """Authenticate and return a Spotify client using the refresh token."""
    auth_manager = SpotifyOAuth(client_id=CLIENT_ID,
                                client_secret=CLIENT_SECRET,
                                redirect_uri=REDIRECT_URI,
                                scope=SCOPE)
    auth_manager.refresh_access_token(REFRESH_TOKEN)
    return spotipy.Spotify(auth_manager=auth_manager)

# Initialize the Spotify client
sp = get_spotify_client()

def append_to_google_sheet(track_name, artist_name, album_name, duration_ms):
    """
    Append track information to Google Sheets.
    
    Args:
        track_name (str): Name of the track.
        artist_name (str): Name of the artist.
        album_name (str): Name of the album.
        duration_ms (int): Duration of the track in milliseconds.
    """
    try:
        # Set up Google Sheets API client
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        credentials = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS_FILE, scope)
        client = gspread.authorize(credentials)

        # Open the Google Sheet
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1

        # Convert duration from milliseconds to MM:SS format
        if duration_ms != "-":
            duration_seconds = duration_ms // 1000
            minutes = duration_seconds // 60
            seconds = duration_seconds % 60
            duration_formatted = f"{minutes:02}:{seconds:02}"
        else:
            duration_formatted = "-"

        # Append the track information with timestamp and duration
        tz = pytz.timezone('Africa/Cairo') 
        timestamp = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([timestamp, track_name, artist_name, album_name, duration_formatted])

        print("Track info appended to Google Sheet.")
    except Exception as e:
        print(f"An error occurred while updating Google Sheets: {e}")

@functions_framework.http
def spotify_to_google_sheets(request):
    """HTTP Cloud Function to check the currently playing track on Spotify and append it to Google Sheets."""
    try:
        # Fetch the currently playing track
        current_track = sp.current_user_playing_track()
        
        
        if current_track is None or current_track['item'] is None:
            print("No track is currently playing.")
        else:
            # Check if playback is active
            is_playing = current_track['is_playing']

            # Set up Google Sheets API client
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
                     "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
            credentials = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS_FILE, scope)
            client = gspread.authorize(credentials)

            # Open the Google Sheet
            sheet = client.open(GOOGLE_SHEET_NAME).sheet1

            # Get the last row of the sheet
            last_row = sheet.get_all_values()[-1] if sheet.row_count > 1 else None
            
            # Check if the last row is empty or contains only dashes
            if not is_playing:
                print("Playback is paused.")
                if last_row and last_row[1:] == ["-", "-", "-", "-"]:
                    print("Last entry indicates playback is already paused. Skipping appending.")
                else:
                    append_to_google_sheet("-", "-", "-", "-")
            else:
                # Extract relevant information
                track_name = current_track['item']['name']
                artist_name = ", ".join(artist['name'] for artist in current_track['item']['artists'])
                album_name = current_track['item']['album']['name']
                duration_ms = current_track['item']['duration_ms']  # Get duration in ms

                print(f"Currently playing: '{track_name}' by {artist_name} from the album '{album_name}' ({duration_ms} ms).")

                # Append to Google Sheet, including duration
                append_to_google_sheet(track_name, artist_name, album_name, duration_ms)
    except Exception as e:
        print(f"An error occurred: {e}")
    return "Success"