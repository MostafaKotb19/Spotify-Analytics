import functions_framework
import gspread
import pandas as pd
import datetime
from oauth2client.service_account import ServiceAccountCredentials
import pytz
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# --- Configuration ---
INPUT_SHEET_NAME = "Spotify Data"
OUTPUT_SHEET_NAME = "Spotify Processed Data"
CREDENTIALS_FILE = "sheets.json"

# Spotify API Credentials
CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
REDIRECT_URI = "https://example.org/callback"
REFRESH_TOKEN = "YOUR_REFRESH_TOKEN"

def get_spotify_client():
    """Authenticate and return a Spotify client using the refresh token."""
    auth_manager = SpotifyOAuth(client_id=CLIENT_ID,
                                client_secret=CLIENT_SECRET,
                                redirect_uri=REDIRECT_URI)
    auth_manager.refresh_access_token(REFRESH_TOKEN)
    return spotipy.Spotify(auth_manager=auth_manager)

def load_data_from_sheet(sheet_name):
    """
    Load data from a Google Sheet into a DataFrame.

    Args:
        sheet_name (str): The name of the Google Sheet to load data from.
    
    Returns:
        pd.DataFrame: A DataFrame containing the data from the Google Sheet.
    """
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(credentials)
    try:
        sheet = client.open(sheet_name).sheet1
        data = sheet.get_all_values()
        if not data:
            print(f"Error: No data found in {sheet_name}.")
            return pd.DataFrame()
        headers = data[0]
        data = data[1:]
        df = pd.DataFrame(data, columns=headers)
        return df
    except Exception as e:
         print(f"An error occurred while loading data from sheet '{sheet_name}': {e}")
         return pd.DataFrame()

def get_track_genre(artist, track_name):
    """
    Retrieves the genre of a track using the Spotify API.

    Args:
        artist (str): The name of the artist.
        track_name (str): The name of the track.

    Returns:
        str: The genre of the track, or None if not found or an error occurs.
    """
    try:
       
        sp = get_spotify_client()

        query = f'artist:"{artist}" track:"{track_name}"'
        results = sp.search(q=query, type='track', limit=1)

        if results and results['tracks']['items']:
            track = results['tracks']['items'][0]
            artist_id = track['artists'][0]['id']
            artist_info = sp.artist(artist_id)
            
            if artist_info['genres']:
              return ', '.join(artist_info['genres'])
            
    except Exception as e:
        print(f"Error retrieving genre for {track_name} by {artist}: {e}")
    return None

def transform_data(df, target_date):
    """
    Transform the input DataFrame to extract relevant information for the current date.

    Args:
        df (pd.DataFrame): The input DataFrame containing Spotify data.
        target_date (datetime.date): The date for which to filter the data.

    Returns:
        pd.DataFrame: A transformed DataFrame with relevant information.
    """
    # Check if the DataFrame is empty
    if df.empty:
        print("No data to transform.")
        return pd.DataFrame()
    
    # Filter out rows with '-' in the 'Track' column
    df = df[df['Track'] != '-'].copy()
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df['Date'] = df['Timestamp'].dt.date
    
    # Filter data for the current date
    df = df[df['Date'] == target_date].copy()
    
    if df.empty:
        print(f"No data for date: {target_date}")
        return pd.DataFrame()
    
    df['Duration'] = pd.to_timedelta('00:' + df['Duration'])
    df['Duration_seconds'] = df['Duration'].dt.total_seconds()

    # Group by day, track, artist, album and duration
    grouped = df.groupby(['Date', 'Track', 'Artist', 'Album', 'Duration_seconds']).agg(
        minutes_listened=('Track', 'count'),
    ).reset_index()

    # calculate the number of times this song was listened to
    grouped['times_listened'] = grouped['minutes_listened'] / (grouped['Duration_seconds'] / 60)
    grouped['times_listened'] = grouped['times_listened'].apply(lambda x: int(round(x, 0)))
    grouped['Duration_seconds'] = grouped['Duration_seconds'].apply(lambda x: str(datetime.timedelta(seconds=x))[:7])

    #Rename columns and transform duration to the format hh:mm:ss
    grouped.rename(columns={'Duration_seconds': 'duration'}, inplace=True)

    # calculate time listened to this song and transform it to the format hh:mm:ss
    grouped['time_listened'] = grouped['minutes_listened']
    
    # select just the coluns we need
    grouped = grouped[['Date', 'Track', 'Artist', 'Album', 'time_listened','times_listened', 'duration']]

    # Add genre column
    grouped['genre'] = grouped.apply(lambda row: get_track_genre(row['Artist'], row['Track']), axis=1)

    return grouped

def push_data_to_sheet(df, sheet_name):
    """
    Push data from a DataFrame to a Google Sheet.

    Args:
        df (pd.DataFrame): The DataFrame containing data to push.
        sheet_name (str): The name of the Google Sheet to push data to.
    """
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(credentials)

    try:
        sheet = client.open(sheet_name).sheet1

        #Get headers
        headers = list(df.columns)

        #Get rows with current date
        date_str = str(df['Date'].iloc[0])
        date_cells = sheet.findall(date_str)

        #Get the index of each row with the current date and clear only the rows with that specific date
        rows_to_clear = set()
        if date_cells:
           rows_to_clear = {cell.row for cell in date_cells}

        if rows_to_clear:
            sheet.delete_rows(min(rows_to_clear), max(rows_to_clear))
        
        #Append data and headers if sheet is empty
        existing_data = sheet.get_all_values()
        if not existing_data:
            sheet.append_row(headers)
        
        #Append rows
        data_list = df.values.tolist()
        data_list = [list(map(lambda x: str(x) if isinstance(x, datetime.date) else x, row)) for row in df.values.tolist()]
        sheet.append_rows(data_list)
        print("Data pushed to Google Sheet successfully.")

    except Exception as e:
        print(f"An error occurred while pushing data to sheet '{sheet_name}': {e}")

@functions_framework.http
def spotify_to_google_sheets(request):
    """HTTP Cloud Function to perform ETL process for Spotify data."""
    # Set Cairo timezone
    cairo_timezone = pytz.timezone('Africa/Cairo')
    
    # Get today's date in Cairo timezone
    today = datetime.datetime.now(cairo_timezone).date()

    # Load data from Google Sheet
    df_input = load_data_from_sheet(INPUT_SHEET_NAME)

    # Transform data for the current date
    df_output = transform_data(df_input, today)
    
    if not df_output.empty:
        print("ETL Process Completed")
        print(df_output.head())
        # Push data to Google Sheet
        push_data_to_sheet(df_output, OUTPUT_SHEET_NAME)

    print("ETL Process Complete")
    return "ETL Process Complete"
