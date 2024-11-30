import os
import random

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
scope = 'playlist-read-private user-read-private user-read-email user-library-read'

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

@app.route('/')
def home():
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)
    return redirect(url_for('get_playlists'))

@app.route('/callback')
def callback():
    sp_oauth.get_access_token(request.args['code'])
    return redirect('/')

#Will test this block of code when rendered html templates
@app.route('/search', methods=['GET', 'POST'])
def search():
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)
    
    results = None

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
                            'image': track['album']['images'][0]['url'] if track['album']['images'] else None
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
                            'image': track['album']['images'][0]['url'] if track['album']['images'] else None
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
    return render_template('search.html', results=results)

@app.route('/recommend', methods=['GET'])
def recommend():
    # Check if the token is valid
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)

    recommendations = None

    try:
        # Fetch user's top tracks and artists
        top_tracks = sp.current_user_top_tracks(limit=5, time_range='medium_term')['items']
        top_artists = sp.current_user_top_artists(limit=5, time_range='medium_term')['items']

        print("Top Tracks:", top_tracks)
        print("Top Artists:", top_artists)

        # Extract seeds (track IDs, artist IDs)
        seed_tracks = [track['id'] for track in top_tracks]
        seed_artists = [artist['id'] for artist in top_artists]

        # Debugging: Print top tracks and artists
        print("Top Tracks:", [track['name'] for track in top_tracks])
        print("Top Artists:", [artist['name'] for artist in top_artists])

        # Fetch audio features for top tracks
        audio_features = sp.audio_features(seed_tracks)

        # Calculate average song attributes
        avg_tempo = sum(f['tempo'] for f in audio_features if f) / len(audio_features)
        avg_energy = sum(f['energy'] for f in audio_features if f) / len(audio_features)
        avg_valence = sum(f['valence'] for f in audio_features if f) / len(audio_features)

        # Debugging: Print calculated averages
        print("Average Tempo:", avg_tempo)
        print("Average Energy:", avg_energy)
        print("Average Valence (Mood):", avg_valence)

        # Use calculated attributes to define recommendation parameters
        recommendation_results = sp.recommendations(
            seed_tracks=seed_tracks[:2],  # Use up to 2 track seeds
            seed_artists=seed_artists[:2],  # Use up to 2 artist seeds
            limit=10,
            min_tempo=max(avg_tempo - 10, 0),  # Adjust tempo range
            max_tempo=min(avg_tempo + 10, 300),
            min_energy=max(avg_energy - 0.2, 0),  # Adjust energy range
            max_energy=min(avg_energy + 0.2, 1),
            min_valence=max(avg_valence - 0.2, 0),  # Adjust mood range
            max_valence=min(avg_valence + 0.2, 1)
        )

        # Format the recommendations for rendering
        recommendations = [
            {
                'name': track['name'],
                'artist': ', '.join(artist['name'] for artist in track['artists']),
                'url': track['external_urls']['spotify']
            }
            for track in recommendation_results['tracks']
        ]

        # Debugging: Print formatted recommendations
        print("Formatted Recommendations:", recommendations)

    except Exception as e:
        return render_template('home.html', error=f"An error occurred: {str(e)}")

    return render_template('home.html', recommendations=recommendations)


@app.route('/top-charts', methods=['GET'])
def top_charts():
    # Ensure the user is authenticated
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)

    # Get the country code from the query parameter or default to "GLOBAL"
    country = request.args.get('country', 'GLOBAL').upper()

    try:
        # Retrieve the "Top 50" playlists for the specified country
        category_id = "charts"
        country_filter = "" if country == "GLOBAL" else f"_{country}"
        playlists = sp.category_playlists(category_id=category_id, country=None if country == "GLOBAL" else country, limit=10)

        # Find the specific "Top 50" playlist for the given country
        playlist_id = None
        for playlist in playlists['playlists']['items']:
            if f"Top 50{country_filter}" in playlist['name']:
                playlist_id = playlist['id']
                break

        if not playlist_id:
            return render_template('top_charts.html', error=f"No top charts found for {country}.", country=country)

        # Fetch playlist tracks
        playlist_tracks = sp.playlist_tracks(playlist_id, limit=50)
        tracks = [
            {
                'name': item['track']['name'],
                'artist': ', '.join(artist['name'] for artist in item['track']['artists']),
                'url': item['track']['external_urls']['spotify']
            }
            for item in playlist_tracks['items']
        ]
    except Exception as e:
        return render_template('top_charts.html', error=f"An error occurred: {str(e)}", country=country)

    # Render the top charts page with the tracks
    #return render_template('top_charts.html', country=country, tracks=tracks)

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

    return render_template('home.html', playlists=playlists_info)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(debug=True)