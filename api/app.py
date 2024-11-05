import time
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import Flask, url_for, session, request, redirect, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select, delete, String, ForeignKey, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session
from dotenv import load_dotenv
from datetime import datetime

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.secret_key = 'SOMETHING-RANDOM'
app.config['SESSION_COOKIE_NAME'] = 'spotify-login-session'

#init db model
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
db.init_app(app)

class Users(Base):
    __tablename__ = "users"
    userid: Mapped[str] = mapped_column(String(50), primary_key = True)
    playlist_name: Mapped[str] = mapped_column(String(50))
    playlist_length: Mapped[int] = mapped_column()

    def __repr__(self) -> str:
        return f"Users(userid={self.userid!r}, playlist_name={self.playlist_name!r}, playlist_length={self.playlist_length!r})"

class Tracks(Base):
    __tablename__ = "tracks"
    pkid: Mapped[int] = mapped_column(primary_key=True)
    trackid: Mapped[str] = mapped_column(String(50))
    userid: Mapped[str] = mapped_column(ForeignKey("users.userid"))
    isnew: Mapped[bool] = mapped_column(default = 1)

with app.app_context():
    db.create_all()

@app.route('/')
def login():
    sp_oauth = create_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
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

#!make accessible from template

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
        session['userid'] = sp.me()["id"]
        #!make sure user can only have one playlist
        #!if playlist name saved for user doesnt match new name, update entry
        stmt = select(Users).where(Users.userid == session['userid'])
        if not db.session.execute(stmt).first():
            user = Users(userid = session['userid'], playlist_name = session["playlist_name"], playlist_length = session["playlist_length"])
            db.session.add(user)
            db.session.commit()
        return redirect(url_for('setPlaylist1'))
    return render_template('input.html')



#need to get around spotify's 100 song id request limit
#thus, the following 4 routes
@app.route('/setPlaylist1', methods = ['POST', 'GET'])
def setPlaylist1():
    session['token_info'], authorized = get_token()
    session.modified = True
    if not authorized:
        return redirect('/')
    session['offset'] = 0
    session['extra'] = session['playlist_length']%50

    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))

    # stmt = (delete(Tracks).where(Tracks.userid == session['userid']))
    # db.session.execute(stmt)
    # db.session.commit()
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
    playlists = sp.current_user_playlists()
    playlist_name = session["playlist_name"]
    # Checking if playlist exists
    # then either creating or updating it
    plist_exists = False
    plist_idx = -1
    for idx in range(len(playlists["items"])):
        if playlist_name == playlists["items"][idx]["name"]:
            plist_exists = True
            plist_idx = idx
    if plist_exists:
        playlist = playlists["items"][plist_idx]
        tracklist = session['tracklist']
        sp.playlist_replace_items(playlist["uri"],[tracklist[1]])
        sp.playlist_remove_all_occurrences_of_items(playlist["uri"],[tracklist[1]])
    else:
        playlist = sp.user_playlist_create(session['userid'], playlist_name)
    session['playlist_uri'] = playlist["uri"]
    return redirect('/loadingplaylist2')


@app.route('/loadingplaylist2', methods = ["GET", "POST"])
def loadingplaylist2():
    session['token_info'], authorized = get_token()
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    tracklist = (session['tracklist'])
    ltracklist = []
    #! "if track old/new" goes here to create appropriate tracklist
    #! then, delete all tracks in sql marked old, which leaves only the new tracks
    #! update new tracks to be old

    stmt = update(Tracks).where(Tracks.userid == session['userid']).values(isnew = 0)
    db.session.execute(stmt)
    db.session.commit()

    for i in range(min(100, session['playlist_length'])):
            ltracklist.append(tracklist[i])
    sp.playlist_add_items(session['playlist_uri'],ltracklist)
    if session['playlist_length'] <= 100:
                return redirect('/success')
    session['playlist_length'] -= 100

    
    return redirect('/loadingplaylist2')


@app.route('/success', methods = ["GET", "POST"])
def success():
    #! get created or updated status from "set playlist"
    playlist_name = session["playlist_name"]
    msg = f"Your playlist, {playlist_name}, has been updated!"
    return render_template("success.html", msg = msg)

#gets up to 100 tracks
def get_tracklist(sp):
    extra = session['extra']
    tracklist = []
    #!! what if the length of the final tracklist is less than the playlist length??
    if (len(sp.current_user_saved_tracks(limit = 50,)["items"])) < 50:
        tracklist += sp.current_user_saved_tracks(limit = 50)["items"]
        session['offset'] = len(tracklist)
    elif (session['extra'] == (session['playlist_length'] - session['offset']) ):
        tracklist += sp.current_user_saved_tracks(limit = extra, offset = session['offset'])["items"]
        session['offset'] += session['playlist_length'] % 50
    else: 
        sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
        tracklist += sp.current_user_saved_tracks(limit = 50, offset = session['offset'])["items"]
        session['offset'] += 50
    for i in range(len(tracklist)):
        tracklist[i] = tracklist[i]["track"]["uri"]
        track = Tracks(userid = session['userid'], trackid = tracklist[i])
        db.session.add(track)
    db.session.commit()
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