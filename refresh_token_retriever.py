import spotipy
from spotipy.oauth2 import SpotifyOAuth

CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
REDIRECT_URI = "https://example.org/callback"
SCOPE = "user-read-currently-playing"

auth_manager = SpotifyOAuth(client_id=CLIENT_ID,
                            client_secret=CLIENT_SECRET,
                            redirect_uri=REDIRECT_URI,
                            scope=SCOPE)

print("Navigate to the following URL to authenticate:")
print(auth_manager.get_authorize_url())

# After authentication, paste the redirected URL here
response_url = input("Enter the full callback URL: ")
token_info = auth_manager.get_access_token(response_url)
print("Access Token:", token_info['access_token'])
print("Refresh Token:", token_info['refresh_token'])
