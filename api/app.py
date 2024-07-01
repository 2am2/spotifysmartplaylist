import time
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import Flask, url_for, session, request, redirect, render_template
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///listeners.db'
app.secret_key = 'SOMETHING-RANDOM'
app.config['SESSION_COOKIE_NAME'] = 'spotify-login-session'

#init db
db = SQLAlchemy(app)
#init db model
class Listeners(db.Model):
    id = db.Column(db.Integer, primary_key = True)
    username = db.Column(db.String(50) )#unique = True)
    playlist_name = db.Column(db.String(50))
    playlist_length = db.Column(db.Integer)
    #date_added = db.Column(db.DateTime, default=datetime.datetime.now(datetime.UTC))

class Tracks(db.Model):
    username = db.Column(db.String(50))
    track_id = db.Column(db.String(100), unique = True, primary_key = True)



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
        session['token_info'], authorized = get_token()
        sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
        if not db.session.execute(db.select(Listeners).where(Listeners.username == sp.me()['id'])):
            listener = Listeners(username = sp.me()['id'], playlist_name = request.form.get('playlist_name'), playlist_length = int(request.form.get('playlist_length')))
            db.session.add(listener)
            db.session.commit()
        return redirect(url_for('setPlaylist1'))
    return render_template('input.html')


@app.route('/setPlaylist1', methods = ['POST', 'GET'])
def setPlaylist1():
    session['token_info'], authorized = get_token()
    session.modified = True
    if not authorized:
        return redirect('/')
    session['offset'] = 0
    session['div'] = session['playlist_length']//50
    session['extra'] = session['playlist_length']%50
    session['tracklist'] = []
    return redirect('/loadingplaylist')


@app.route('/loadingplaylist', methods = ["GET", "POST"])
def loadingplaylist():
    session['token_info'], authorized = get_token()
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    tracklist = get_tracklist(sp)
    
    session['tracklist'] += tracklist
    
    if session['offset'] == session['playlist_length']:
        return redirect('/setPlaylist2')
    return redirect('/loadingplaylist')


@app.route('/setPlaylist2', methods = ['POST', 'GET'])
def setPlaylist2():
    session['token_info'], authorized = get_token()   
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
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
        c_u = "updated"
    else:
        playlist = sp.user_playlist_create(user_id, playlist_name)
        c_u = "created"
    session['playlist_uri'] = playlist["uri"] 
    tracklist = session['tracklist']
    sp.playlist_replace_items(playlist["uri"],[tracklist[1]])
    sp.playlist_remove_all_occurrences_of_items(playlist["uri"],[tracklist[1]])
    print(sp.playlist_tracks(playlist["uri"],limit = 50))
    session["c_u"] = c_u
    return redirect('/loadingplaylist2')


@app.route('/loadingplaylist2', methods = ["GET", "POST"])
def loadingplaylist2():
    session['token_info'], authorized = get_token()
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    tracklist = (session['tracklist'])
    ltracklist = []
    
    if session['playlist_length'] <= 100:
        for i in range(session['playlist_length']):
            ltracklist.append(tracklist[i])
        sp.playlist_add_items(session['playlist_uri'],ltracklist)
        return redirect('/success')
    for i in range(100):
            ltracklist.append(tracklist[i])
    sp.playlist_add_items(session['playlist_uri'],ltracklist)
    session['playlist_length'] -= 100
    return redirect('/loadingplaylist2')


@app.route('/success', methods = ["GET", "POST"])
def success():
    #! get created or updated status from "set playlist"
    playlist_name = session["playlist_name"]
    c_u = session["c_u"]
    msg = f"Your playlist, {playlist_name}, has been {c_u}!"
    return render_template("success.html", msg = msg)
    

def get_tracklist(sp):
    loffset = session['offset']
    ldiv = session['div']
    extra = session['extra']
    tracklist = []
    #!! what if the length of the final tracklist is less than the playlist length??
    if (len(sp.current_user_saved_tracks(limit = 50,)["items"])) < 50:
        tracklist += sp.current_user_saved_tracks(limit = 50)["items"]
        loffset = len(tracklist)
    elif (session['extra'] == (session['playlist_length'] - session['offset']) ):
        tracklist += sp.current_user_saved_tracks(limit = extra, offset = loffset)["items"] 
        loffset += session['playlist_length'] % 50
    else: 
        for count in range(2):
            sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
            tracklist += sp.current_user_saved_tracks(limit = 50, offset = loffset)["items"] 
            loffset += 50 
    ldiv = ldiv - 2
    session['div'] = ldiv 
    session['offset'] = loffset
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

def create_spotify_oauth():
    load_dotenv()
    return SpotifyOAuth(
            client_id=os.getenv("CLIENT_ID"),
            client_secret=os.getenv("CLIENT_SECRET"),
            redirect_uri=url_for('authorize', _external=True),
            scope="user-library-read playlist-modify-public playlist-modify-private") 