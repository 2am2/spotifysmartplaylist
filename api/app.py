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
    isnew: Mapped[bool] = mapped_column(default = True)

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


@app.route('/logout')
#!make accessible from template
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
        sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
        session['userid'] = sp.me()["id"]
        session["playlist_name"] = request.form.get('playlist_name')
        session["playlist_length"] = int(request.form.get('playlist_length'))
        session['token_info'], authorized = get_token()
        
        
        #!make sure user can only have one playlist
        #!if playlist name saved for user doesnt match new name, update entry
        stmt = select(Users).where(Users.userid == session['userid'])
        if not db.session.execute(stmt).first():
            user = Users(userid = session['userid'], playlist_name = session["playlist_name"], playlist_length = session["playlist_length"])
            db.session.add(user)
            db.session.commit()

        session['offset'] = 0
        session['extra'] = session['playlist_length']%50
        get_playlist_uri()
        return redirect('/loadingplaylist')
    return render_template('input.html')


@app.route('/loadingplaylist', methods = ["GET", "POST"])
def loadingplaylist():
    get_tracklist()
    # have ^^ return additions to offset val to create exit condition
    # this will reduce data coupling
    if session['offset'] == session['playlist_length']:
        return redirect('/loadingplaylist2')
    return redirect('/loadingplaylist')


@app.route('/loadingplaylist2', methods = ["GET", "POST"])
def loadingplaylist2():

    session['token_info'], authorized = get_token()
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    
    #! build up ltracklist from sql, delete regular "tracklist"

    addtracks = []
    deletetracks = []
    
    #get only the first "plist length" number of tracks
    stmt = select(Tracks).where(Tracks.userid == session['userid']).where(Tracks.isnew == True)
    newtracks = db.session.execute(stmt).scalars()

    stmt = select(Tracks).where(Tracks.userid == session['userid']).where(Tracks.isnew == False)
    oldtracks = db.session.execute(stmt).scalars()

    newset = set()
    oldset = set()

    for track in oldtracks: 
        oldset.add(track.trackid)

    for track in newtracks: 
        newset.add(track.trackid)

    for trackid in newset:
        if trackid not in oldset:
            addtracks.append(trackid)

    for trackid in oldset:
        if trackid not in newset:
            deletetracks.append(trackid)
   
    if addtracks:
        sp.playlist_add_items(session['playlist_uri'], addtracks)
    if deletetracks:
        sp.playlist_remove_all_occurrences_of_items(session['playlist_uri'], deletetracks)

    
    stmt = delete(Tracks).where(Tracks.isnew == False).where(Tracks.userid == session['userid'])
    db.session.execute(stmt)
    db.session.commit()

    stmt = update(Tracks).where(Tracks.userid == session['userid']).values(isnew = False)
    db.session.execute(stmt)
    db.session.commit()

    return redirect('/success')


@app.route('/success', methods = ["GET", "POST"])
def success():
    #! get created or updated status from "set playlist"
    playlist_name = session["playlist_name"]
    msg = f"Your playlist, {playlist_name}, has been updated!"
    return render_template("success.html", msg = msg)





# gets up to 100 tracks
def get_tracklist():
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    tracklist = []
    #!! what if the length of the final tracklist is less than the playlist length??
    if (len(sp.current_user_saved_tracks(limit = 50, offset = session['offset'])["items"])) < 50:
        tracklist += sp.current_user_saved_tracks(limit = 50)["items"]
        session['offset'] = len(tracklist)
        return redirect('/loadingplaylist2')
    elif (session['extra'] == (session['playlist_length'] - session['offset']) ):
        tracklist += sp.current_user_saved_tracks(limit = session['extra'], offset = session['offset'])["items"]
        session['offset'] += session['extra']
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


def get_playlist_uri():
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    playlists = sp.current_user_playlists()
    plist_exists = False
    plist_idx = -1
    for idx in range(len(playlists["items"])):
        if session["playlist_name"] == playlists["items"][idx]["name"]:
            plist_exists = True
            plist_idx = idx
    if plist_exists:
        playlist = playlists["items"][plist_idx]
    else:
        playlist = sp.user_playlist_create(session['userid'], session["playlist_name"])
    session['playlist_uri'] = playlist["uri"]
    print(session['playlist_uri'])


def create_spotify_oauth():
    load_dotenv()
    return SpotifyOAuth(
            client_id=os.getenv("CLIENT_ID"),
            client_secret=os.getenv("CLIENT_SECRET"),
            redirect_uri=url_for('authorize', _external=True),
            scope="user-library-read playlist-modify-public playlist-modify-private")