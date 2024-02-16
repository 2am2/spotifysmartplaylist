import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import Flask, url_for, session, request, redirect, render_template
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

@app.route('/success0')
def success0():
    return "Your playlist, 100 RECENT LIKES, has been updated!"

@app.route('/success1')
def success1():
    return "The playlist 100 RECENT LIKES has been created!"

@app.route('/authorize')
def authorize():
    sp_oauth = create_spotify_oauth()
    session.clear()
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code, check_cache=False)
    session["token_info"] = token_info
    return redirect("/setPlaylist")

@app.route('/logout')
def logout():
    for key in list(session.keys()):
        session.pop(key)
    return "redirect('/')"

@app.route('/userinput')
def userinput():
    return "God has failed us"

@app.route('/setPlaylist')
def setPlaylist():
    session['token_info'], authorized = get_token()
    session.modified = True
    if not authorized:
        return redirect('/')
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    tracklist = []
 
    #! take input here for playlist length TO DO
    playlist_length = 100
    if (len(sp.current_user_saved_tracks()["items"])) < playlist_length:
        playlist_length = (len(sp.current_user_saved_tracks()["items"]))
    # iter = playlist_length//50
    
    #! incorporate playlist length here to create a variable length playlist
   # count = 0
    #while count*50 < 100:
        #tracklist += sp.current_user_saved_tracks(limit = 50, offset = count*50)["items"]
     #   count += 1
    
    tracklist += sp.current_user_saved_tracks(limit = 10)["items"]

    tracklist = [tracklist[idx]["track"]["uri"] for idx in range(10)]
   # return tracklist

    user_id = sp.me()["id"]
    playlists = sp.current_user_playlists()
    
    #! take input here for playlist name  
    playlist_name = "100 RECENT LIKES"
     
    # Checking if playlist exists, and getting uri either way
    playlist_uri = ""
    return "10"
    for idx in range(len(playlists["items"])):
        if playlists["items"][idx]["name"] == playlist_name:
            playlist = playlists["items"][idx]
            playlist_uri = playlist["uri"]
            sp.playlist_replace_items(playlist_uri,tracklist)
            return redirect('/success0')
        else:
            playlist = sp.user_playlist_create(user_id, playlist_name)
            playlist_uri = playlist["uri"]
            sp.playlist_add_items(playlist_uri,tracklist)
            return redirect('/success1')
    


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

#! can u use this field to specify cache location?
#! but token info is already stored in the session??
def create_spotify_oauth():
    return SpotifyOAuth(
            client_id=os.getenv("CLIENT_ID"),
            client_secret=os.getenv("CLIENT_SECRET"),
            redirect_uri=url_for('authorize', _external=True),
            scope="user-library-read playlist-modify-public playlist-modify-private") 