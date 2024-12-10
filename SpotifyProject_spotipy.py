import os
import pandas as pd


from dotenv import load_dotenv
from flask import Flask, session, url_for, request, redirect, render_template
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import FlaskSessionCacheHandler



app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(64)
#load environment variables from .env file
load_dotenv()
client_id = os.getenv("SPOTIPY_CLIENT_ID")
client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI")
scope = 'playlist-read-private user-read-private user-read-email user-library-read user-top-read playlist-read-collaborative user-read-recently-played playlist-modify-public playlist-modify-private user-library-modify'

cache_handler = FlaskSessionCacheHandler(session)

sp_oauth = SpotifyOAuth(
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri=redirect_uri,
    scope=scope,
    cache_handler=cache_handler,
    show_dialog=True
)
sp = Spotify(auth_manager=sp_oauth)

#Load csv dataset
file_path = 'data/Songs_Dataset.csv'

if os.path.exists(file_path):
    song_df = pd.read_csv(file_path)
    print("Data loaded successfully")
else:
    print("Error: CSV file not found.")

#Song duration conversion
"""
    Convert duration in milliseconds to a human-readable format (minutes:seconds).
    :param duration_ms: Duration in milliseconds
    :return: Formatted string in minutes:seconds
    """
def format_duration(duration_ms):
    if not duration_ms:
        return "0:00"
    minutes, seconds = divmod(duration_ms // 1000, 60)
    return f"{minutes}:{seconds:02d}"

#Home page route
@app.route('/', methods=['GET', 'POST'])
def home():
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)
    
    playlists = get_playlists()
    recommendations = []
    top_50_metadata = {}
    try:
        # Handle form submission
        if request.method == 'POST':
            # Fetch user's liked songs
            liked_songs = sp.current_user_saved_tracks(limit=50)['items']

            # Extract artists and genres
            favorite_artists = list(set(track['track']['artists'][0]['name'] for track in liked_songs))
            favorite_genres = list(set(track['track']['album']['album_type'] for track in liked_songs))

            # Get form data
            min_tempo = int(request.form['min_tempo'])
            max_tempo = int(request.form['max_tempo'])
            min_danceability = float(request.form['min_danceability'])
            preferred_genres = request.form.getlist('preferred_genres')

            # Filter songs using CSV features + form data
            filtered_songs = song_df[
                (song_df['Tempo (BPM)'].between(min_tempo, max_tempo)) &
                (song_df['Danceability'] >= min_danceability) &
                ((song_df['Artist'].isin(favorite_artists)) |
                 (song_df['Genre'].isin(preferred_genres or favorite_genres)))
            ]

            # Generate top 10 recommendations
            recommendations = filtered_songs.head(10).to_dict(orient='records') if not filtered_songs.empty else []

    except Exception as e:
        print(f"Error generating recommendations: {e}")
        recommendations = []

    return render_template('home.html', playlists=playlists, recommendations=recommendations, top_50_metadata=top_50_metadata)

@app.route('/callback')
def callback():
    sp_oauth.get_access_token(request.args['code'])

    token_info = sp_oauth.get_cached_token()
    if not token_info:
        return "Error: Failed to retrieve access token.", 400

    print("Token Info Cached Successfully:", token_info)  # Debugging
    return redirect('/')

#Search page route
@app.route('/search', methods=['GET', 'POST'])
def search():
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)
    
    results = None
    user_playlists =[]

    try:
        playlists = sp.current_user_playlists()
        user_playlists = [
            {'id': playlist['id'], 'name': playlist['name']}
            for playlist in playlists['items']
        ]
    except Exception as e:
        user_playlists = []

    # Get the search query and type from the request
    if request.method == 'GET':
        query = request.args.get('query', '')
        search_type = request.args.get('type', 'artist')

    if request.method == 'POST':
        query = request.form.get('query', '')
        search_type = request.form.get('type', 'artist')
    
    if query:
        spotify_results = sp.search(q=query, type=search_type, limit=10)
    
        # Handle artist search
        if search_type == 'artist':
            if spotify_results['artists']['items']:
                artist = spotify_results['artists']['items'][0]
                artist_id = artist['id']
                artist_name = artist['name']
                artist_url = artist['external_urls']['spotify']
                artist_image = artist['images'][0]['url'] if artist['images'] else None
                top_tracks = sp.artist_top_tracks(artist_id)['tracks']
                albums_response = sp.artist_albums(artist_id, album_type='album', limit=10)
                albums = [
                    {
                        'name': album['name'],
                        'url': album['external_urls']['spotify'],
                        'release_date': album['release_date'],
                        'image': album['images'][0]['url'] if album['images'] else None
                    }
                    for album in albums_response['items']
                ]

                results = {
                    'type': 'artist',
                    'name': artist_name,
                    'url': artist_url,
                    'image': artist_image,
                    'top_tracks': [
                        {
                            'name': track['name'],
                            'url': track['external_urls']['spotify'],
                            'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                            'popularity': track['popularity'],  # Number of times listened (popularity)
                            'duration': format_duration(track['duration_ms']),  # Human-readable duration
                            'id': track['id']
                        }
                        for track in top_tracks
                    ],
                    'albums': albums
                }
            else:
                results = {'type': 'error', 'message': 'No artist found.'}

        # Handle track search
        elif search_type == 'track':
            tracks = spotify_results['tracks']['items']
            if tracks:  # Check if track results exist
                results = {
                    'type': 'track',
                    'tracks': [
                        {
                            'name': track['name'],
                            'artist': ', '.join(artist['name'] for artist in track['artists']),
                            'url': track['external_urls']['spotify'],
                            'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                            'id': track['id']
                        }
                        for track in tracks
                    ]
                }
            else:
                results = {'type': 'error', 'message': 'No tracks found.'}

        # Handle album search
        elif search_type == 'album':
            albums = spotify_results['albums']['items']
            if albums:  # Check if album results exist
                results = {
                    'type': 'album',
                    'albums': [
                        {
                            'name': album['name'],
                            'artist': ', '.join(artist['name'] for artist in album['artists']),
                            'url': album['external_urls']['spotify'],
                            'release_date': album['release_date'],
                            'image': album['images'][0]['url'] if album['images'] else None
                        }
                        for album in albums
                    ]
                }
            else:
                results = {'type': 'error', 'message': 'No albums found.'}

    # Render the search results page with the results
    return render_template('search.html', results=results, user_playlists=user_playlists)

@app.route('/like-track', methods=['POST'])
def like_track():
    track_id = request.form.get('track_id')
    if not track_id:
        return "Track ID is required", 400

    try:
        sp.current_user_saved_tracks_add([track_id])  # Add the track to Liked Songs
        return redirect(request.referrer or '/')  # Redirect back to the search page
    except Exception as e:
        return f"Error adding track to Liked Songs: {str(e)}", 500

@app.route('/add-to-playlist', methods=['POST'])
def add_to_playlist():
    track_id = request.form.get('track_id')
    playlist_id = request.form.get('playlist_id')

    if not track_id or not playlist_id:
        return "Track ID and Playlist ID are required", 400

    try:
        sp.playlist_add_items(playlist_id, [track_id])  # Add track to the selected playlist
        return redirect(request.referrer or '/')  # Redirect back to the search page
    except Exception as e:
        return f"Error adding track to playlist: {str(e)}", 500

'''
@app.route('/recommend', methods=['GET', 'POST'])
def recommend():
    # Check if the token is valid
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)

    try:
        # Fetch user's liked songs from Spotify
        liked_songs = sp.current_user_saved_tracks(limit=50)['items']

        # Extract artists and genres from liked songs
        favorite_artists = list(set(track['track']['artists'][0]['name'] for track in liked_songs))
        favorite_genres = list(set(track['track']['album']['album_type'] for track in liked_songs))

        # Get user preferences from form if POST request
        if request.method == 'POST':
            min_tempo = int(request.form['min_tempo'])
            max_tempo = int(request.form['max_tempo'])
            min_danceability = float(request.form['min_danceability'])
            preferred_genres = request.form.getlist('preferred_genres')

            # Filter songs using CSV features + user input
            filtered_songs = song_df[
                (song_df['Tempo (BPM)'].between(min_tempo, max_tempo)) &
                (song_df['Danceability'] >= min_danceability) &
                ((song_df['Artist'].isin(favorite_artists)) |
                 (song_df['Genre'].isin(preferred_genres or favorite_genres)))
            ]
        else:
            # Default filtering based on Spotify data only
            filtered_songs = song_df[
                (song_df['Artist'].isin(favorite_artists)) |
                (song_df['Genre'].isin(favorite_genres))
            ]

         # If no songs match the filter, return an empty list
        recommended_songs = filtered_songs.head(10).to_dict(orient='records') if not filtered_songs.empty else []


        return recommended_songs

    except Exception as e:
        print("Error generating recommendations:", e)
        return []
'''

'''
@app.route('/top-50', methods=['GET'])
def get_top_50_data():
    """
    Fetch metadata for all regional Top 50 playlists.
    """
    # Ensure the user is authenticated
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)

    region_playlists = {
    "GLOBAL": "37i9dQZEVXbMDoHDwVN2tF",
    "US": "37i9dQZEVXbLRQDuF5jeBp",
    "UK": "37i9dQZEVXbLnolsZ8PSNw",
    "CA": "37i9dQZEVXbKj23U1GF4IR",
    "DE": "37i9dQZEVXbJiZcmkrIHGU",
    "JP": "37i9dQZEVXbKXQ4mDTEBXq",
    "IN": "37i9dQZEVXbLZ52XmnySJg",
    "BR": "37i9dQZEVXbMXbN3EUUhlg"
    }
    # Initialize dictionary to store playlist metadata by region
    top_50_metadata = {}

    try:
        # Iterate through all regions in region_playlists
        for region, playlist_id in region_playlists.items():
            try:
                # Fetch playlist details from Spotify API
                playlist = sp.playlist(playlist_id)

                # Extract metadata with defensive checks
                name = playlist.get('name', 'Unknown Playlist')
                url = playlist['external_urls'].get('spotify') if playlist.get('external_urls') else None
                image = (
                    playlist['images'][0]['url']
                    if playlist.get('images') and len(playlist['images']) > 0
                    else None
                )

                # Handle missing URL or image gracefully
                if not url:
                    print(f"Warning: Playlist URL is missing for region '{region}'.")
                if not image:
                    print(f"Warning: No image found for playlist '{name}' (region: {region}).")

                # Add the playlist metadata to the dictionary
                top_50_metadata[region] = {
                    'name': name,
                    'url': url,
                    'image': image,
                }
            except Exception as e:
                print(f"Error fetching playlist for region '{region}': {e}")
                top_50_metadata[region] = {'error': f"Could not fetch data for region '{region}'."}

        # Return the metadata for all regions
        return top_50_metadata
    except Exception as e:
        print(f"Error fetching Top 50 data: {e}")
        return {'error': "An error occurred while fetching Top 50 data."}, 500
'''

@app.route('/get_playlists')
def get_playlists():
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)

    playlists = sp.current_user_playlists()
    #for debug purpose
    #print(playlists)
    playlists_info = []

    for playlist in playlists['items']:
        playlist_id = playlist['id']
        playlist_name = playlist['name']
        playlist_url = playlist['external_urls']['spotify']

        # Fetch the first track's album image
        tracks = sp.playlist_tracks(playlist_id, limit=1)
        if tracks['items']:
            first_track_image = tracks['items'][0]['track']['album']['images'][0]['url'] \
                if tracks['items'][0]['track']['album']['images'] else None
        else:
            first_track_image = None

        playlists_info.append({
            'name': playlist_name,
            'url': playlist_url,
            'image': first_track_image
        })
    
    try:
        liked_songs = sp.current_user_saved_tracks(limit=1)
        if liked_songs['items']:
            liked_songs_image = url_for('static', filename='images/liked-songs.png')
            playlists_info.append({
                'name': "Liked Songs",
                'url': "https://open.spotify.com/collection/tracks",  # Link to the Liked Songs page
                'image': liked_songs_image
            })
    except Exception as e:
        print("Error fetching liked songs:", e)

    #for debug purpose
    #print(playlists_info)

    return playlists_info
    #return render_template('home.html', playlists=playlists_info)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


if __name__ == '__main__':

    app.run(debug=True)