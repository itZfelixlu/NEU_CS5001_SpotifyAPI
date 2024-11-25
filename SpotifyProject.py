import os
import requests
import urllib.parse

from flask import Flask, request, redirect, session, jsonify
from datetime import datetime, timedelta
from dotenv import load_dotenv





app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(64)
#load environment variables from .env file
load_dotenv()
client_id = os.getenv("SPOTIPY_CLIENT_ID")
client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI")

auth_url = "https://accounts.spotify.com/authorize"
token_url = "https://accounts.spotify.com/api/token"
api_base_url = "https://api.spotify.com/v1/"

@app.route('/')
def home():
    return "Welcome to m Spotify APP <a href='/login'>Login with Spotify</a>"

@app.route('/login')
def login():
    scope = 'user-read-private user-read-email'

    params = {
        'client_id': client_id,
        'response_type': 'code',
        'scope': scope,
        'redirect_uri': redirect_uri,
    }
    
    auth_url_with_params = f"{auth_url}?{urllib.parse.urlencode(params)}"

    return redirect(auth_url_with_params)

@app.route('/callback')
def callback():
    if 'error' in request.args:
        return jsonify({"error": request.args['error']})
    
    if 'code' in request.args:
        req_body = {
            'code': request.args['code'],
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
            'client_id': client_id,
            'client_secret': client_secret
        }

    response = requests.post(token_url, data=req_body)
    token_info = response.json()

    session['access_token'] = token_info['access_token']
    session['refresh_token'] = token_info['refresh_token']
    session['expires_at'] = datetime.now().timestamp() + token_info['expires_in']

    return redirect('/playlists')

@app.route('/playlists')
def get_playlists():
    if 'access_token' not in session:
        return redirect('/login')

    if datetime.now().timestamp() > session['expires_at']:
        return redirect('/refresh-token')
    
    headers = {
        'Authorization': f"Bearer {session['access_token']}"
    }

    response = requests.get(api_base_url + 'me/playlists', headers=headers)
    playlists = response.json()

    return jsonify(playlists)

@app.route('/refresh-token')
def refresh_token():
    if 'refresh_token' not in session:
        return redirect('/login')
    
    if datetime.now().timestamp() > session['expires_at']:
        req_body = {
            'grant_type': 'refresh_token',
            'refresh_token': session['refresh_token'],
            'client_id': client_id,
            'client_secret': client_secret
        }
    
    response = requests.post(token_url, data=req_body)
    new_token_info = response.jason()

    session['access_token'] = new_token_info['access_token']
    session['expires_in'] = datetime.now().timestamp() + new_token_info['expires_in']

    return redirect('/playlists')


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True) #flag used for when any adjustments made to code, when you save it, it will restart the server