import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import Flask, url_for, session, request, redirect
import time
import os

app = Flask(__name__)

app.secret_key = 'SOMETHING-RANDOM'
app.config['SESSION_COOKIE_NAME'] = 'spotify-login-session'

@app.route('/')
def login():
    sp_oauth = create_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    print(auth_url)
    return redirect(auth_url)


@app.route('/authorize')
def authorize():
    sp_oauth = create_spotify_oauth()
    session.clear()
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session["token_info"] = token_info
    return redirect("/getTracks")

@app.route('/logout')
def logout():
    for key in list(session.keys()):
        session.pop(key)
    return redirect('/')

@app.route('/getTracks')
def get_all_tracks():
    session['token_info'], authorized = get_token()
    session.modified = True
    if not authorized:
        return redirect('/')
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))

    tracklist = []
    iter = 0

    while iter*50 < 100:
        tracklist += sp.current_user_saved_tracks(limit = 50, offset = iter*50)["items"]
        iter += 1

    tracklist = [tracklist[idx]["track"]["uri"] for idx in range(100)]
   
    user_id = sp.me()["id"]
    playlists = sp.current_user_playlists()
    x = 0
    playlist_uri = ""
    #checking if playlist exists, and getting uri
    for idx in range(len(playlists["items"])):
        if playlists["items"][idx]["name"] == "V1 RECENT LIKES":
            playlist = playlists["items"][idx]
            playlist_uri = playlist["uri"]
            sp.playlist_replace_items(playlist_uri,tracklist)
            x += 1
    if x == 0:
        playlist = sp.user_playlist_create(user_id, "V1 RECENT LIKES")
        playlist_uri = playlist["uri"]
        sp.playlist_add_items(playlist_uri,tracklist)

    #replace or update playlist for new likes??
    return [tracklist]
    # return playlists["items"][0]


# Checks to see if token is valid and gets a new token if not
def get_token():
    token_valid = False
    token_info = session.get("token_info", {})

    # Checking if the session already has a token stored
    if not (session.get('token_info', False)):
        token_valid = False
        return token_info, token_valid

    # Checking if token has expired
    now = int(time.time())
    is_token_expired = session.get('token_info').get('expires_at') - now < 60

    # Refreshing token if it has expired
    if (is_token_expired):
        sp_oauth = create_spotify_oauth()
        token_info = sp_oauth.refresh_access_token(session.get('token_info').get('refresh_token'))

    token_valid = True
    return token_info, token_valid


def create_spotify_oauth():
    return SpotifyOAuth(
            client_id=os.getenv("CLIENT_ID"),
            client_secret=os.getenv("CLIENT_SECRET"),
            redirect_uri=url_for('authorize', _external=True),
            scope="user-library-read playlist-modify-public playlist-modify-private") 