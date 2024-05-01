import time
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import Flask, url_for, session, request, redirect, render_template


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
    token_info = sp_oauth.get_access_token(code, check_cache=False)
    session["token_info"] = token_info
    return redirect("/userinput")

@app.route('/stop')
def stop():
    return "placeholder until u can actually stop plist updates"

@app.route('/logout')
def logout():
    for key in list(session.keys()):
        session.pop(key)
    return "redirect('/')"

@app.route('/aboutme')
def aboutme():
    return render_template('aboutme.html')


@app.route('/userinput', methods = ['GET','POST'])
def userinput():
    if request.method == "POST":
        session["playlist_name"] = request.form.get('playlist_name')
        session["playlist_length"] = int(request.form.get('playlist_length'))
        return redirect(url_for('setPlaylist'))
    return render_template('input.html')


@app.route('/setPlaylist', methods = ['POST', 'GET'])
def setPlaylist():
    session['token_info'], authorized = get_token()
    session.modified = True
    if not authorized:
        return redirect('/')
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    tracklist = get_tracklist(sp)
    user_id = sp.me()["id"]
    playlists = sp.current_user_playlists()

    playlist_name = session["playlist_name"]

    # Checking if playlist exists 
    # then either creating or updating it
    playlist_uri = ""
    plist_exists = False
    plist_idx = -1
    for idx in range(len(playlists["items"])):
        if playlist_name == playlists["items"][idx]["name"]:
            plist_exists = True
            plist_idx = idx
    c_u = "?"
    if plist_exists:
        playlist = playlists["items"][plist_idx]
        playlist_uri = playlist["uri"]
        sp.playlist_replace_items(playlist_uri,tracklist)
        c_u = "updated"
    else:
        playlist = sp.user_playlist_create(user_id, playlist_name)
        playlist_uri = playlist["uri"]
        sp.playlist_add_items(playlist_uri,tracklist)
        c_u = "created"
    session["c_u"] = c_u
    return redirect('/success')

@app.route('/success', methods = ["GET", "POST"])
def success():
    #! get created or updated status from "set playlist"
    playlist_name = session["playlist_name"]
    c_u = session["c_u"]
    msg = f"Your playlist, {playlist_name}, has been {c_u}!"
    return render_template("success.html", msg = msg)
    


def get_tracklist(sp):
    tracklist = []
    playlist_length = session["playlist_length"]

    if (len(sp.current_user_saved_tracks(limit = 50)["items"])) < 50:
        playlist_length = (len(sp.current_user_saved_tracks(limit = 50)["items"]))
        tracklist += sp.current_user_saved_tracks(limit = playlist_length)["items"]
    else:
        divs = playlist_length//50
        extra = playlist_length % 50
        count = -1
        while count < divs:
            count += 1
            tracklist += sp.current_user_saved_tracks(limit = 50, offset = count*50)["items"]
        if extra != 0:
            return "panda1"
            tracklist += sp.current_user_saved_tracks(limit = extra, offset = count*50)["items"]
    return "panda2"
    for i in range(len(tracklist)):
        tracklist[i] = tracklist[i]["track"]["uri"]

    return tracklist

# Checks to see if token is valid and gets a new token if not
def get_token():
    token_valid = False
    token_info = session.get("token_info", {})

    # Checking if the session already has a token stored
    if not session.get('token_info', False):
        token_valid = False
        return token_info, token_valid

    # Checking if token has expired
    now = int(time.time())
    is_token_expired = session.get('token_info').get('expires_at') - now < 60

    # Refreshing token if it has expired
    if is_token_expired:
        sp_oauth = create_spotify_oauth()
        token_info = sp_oauth.refresh_access_token(session.get('token_info').get('refresh_token'))

    token_valid = True
    return token_info, token_valid

#! can u use this field to specify cache location?
#! but token info is already stored in the session??
def create_spotify_oauth():
    return SpotifyOAuth(
            client_id=os.getenv("CLIENT_ID"),
            client_secret=os.getenv("CLIENT_SECRET"),
            redirect_uri=url_for('authorize', _external=True),
            scope="user-library-read playlist-modify-public playlist-modify-private") 