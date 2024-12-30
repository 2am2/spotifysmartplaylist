import time
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import Flask, url_for, session, request, redirect, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select, delete, String, ForeignKey, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session
from dotenv import load_dotenv
import re


app = Flask(__name__)
load_dotenv()

# fixing Vercel's postgres uri
uri = os.getenv('POSTGRES_URL')  
if uri and uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql+psycopg2://", 1)

#uri = 'sqlite:///users.db'

app.config['SQLALCHEMY_DATABASE_URI'] = uri
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
    playlist_uri: Mapped[str] = mapped_column(String(50))
    auto_update: Mapped[bool] = mapped_column(default = False)
    refresh_token: Mapped[str] = mapped_column(String(100))

    def __repr__(self) -> str:
        return f"Users(userid={self.userid!r}, playlist_name={self.playlist_name!r}, playlist_length={self.playlist_length!r})"

class Tracks(Base):
    __tablename__ = "tracks"
    pkid: Mapped[int] = mapped_column(primary_key=True)
    trackid: Mapped[str] = mapped_column(String(50))
    userid: Mapped[str] = mapped_column(ForeignKey("users.userid"))
    isnew: Mapped[bool] = mapped_column(default = True)

class ChangeTracks(Base):
    __tablename__ = "changetracks"
    pkid: Mapped[int] = mapped_column(primary_key=True)
    userid: Mapped[str] = mapped_column(ForeignKey("users.userid"))
    trackid: Mapped[str] = mapped_column(String(50))
    add_or_del: Mapped[bool] = mapped_column()

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
    #delete user from db
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
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    session['userid'] = sp.me()["id"]
    stmt = select(Users).where(Users.userid == session['userid'])
    user = db.session.execute(stmt).scalar_one_or_none()
    if request.method == "POST":
        session['playlist_name'] = request.form.get('playlist_name')
        session["playlist_length"] = int(request.form.get('playlist_length'))
        session['token_info'], authorized = get_token()
        session['auto_update'] = request.form.get("auto_update")
        if user:
            session['playlist_uri'] = user.playlist_uri
            session['playlist_uri'] = check_get_playlist_uri()
            if session['playlist_length'] != user.playlist_length:
                stmt = update(Users).where(Users.userid == session['userid']).values(playlist_length = session['playlist_length'])
                db.session.execute(stmt)
                db.session.commit()
            if session['auto_update']:
                session['auto_update'] = True
                stmt = update(Users).where(Users.userid == session['userid']).values(auto_update = session['auto_update'])
                db.session.execute(stmt)
                db.session.commit()
        else:
            session['playlist_uri'] = "nothing"
            session['playlist_uri'] = check_get_playlist_uri()
            if session['auto_update']:
                session['auto_update'] = True
            user = Users(userid = session['userid'], playlist_name = session["playlist_name"], 
            playlist_length = session["playlist_length"], playlist_uri = session['playlist_uri'], 
            auto_update = session['auto_update'],refresh_token = session['token_info'].get('refresh_token'))
            
            db.session.add(user)         
            db.session.commit()

        session['offset'] = 0
        session['extra'] = session['playlist_length']%50
        return redirect('/loadingplaylist')
    if user:
        name = user.playlist_name   
        length = user.playlist_length
    else:
        name = "RECENT LIKES :)"
        length = 100
    return render_template('input.html', name = name, length = length)


@app.route('/loadingplaylist', methods = ["GET", "POST"])
def loadingplaylist():
    get_tracklist()
    if session['offset'] == session['playlist_length']:
        return redirect('/loadingplaylist2')
    return redirect('/loadingplaylist')

@app.route('/loadingplaylist2', methods = ["GET", "POST"])
def loadingplaylist2():

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
            changetrack = ChangeTracks(userid = session['userid'], trackid = trackid, add_or_del = 1)
            db.session.add(changetrack)
            db.session.commit()
    for trackid in oldset:
        if trackid not in newset:
            changetrack = ChangeTracks(userid = session['userid'], trackid = trackid, add_or_del = 0)
            db.session.add(changetrack)
            db.session.commit()

    stmt = delete(Tracks).where(Tracks.isnew == False).where(Tracks.userid == session['userid'])
    db.session.execute(stmt)
    db.session.commit()

    stmt = update(Tracks).where(Tracks.userid == session['userid']).values(isnew = False)
    db.session.execute(stmt)
    db.session.commit()
    return redirect('/loadingplaylist3')

@app.route('/loadingplaylist3', methods = ["GET", "POST"])
def loadingplaylist3():

    session['token_info'], authorized = get_token()
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))

    addtracks = []
    deletetracks = []
    stmt = select(ChangeTracks).where(ChangeTracks.userid == session['userid'])
    db_result = db.session.execute(stmt).scalars()
    
    i = 0
    for track in db_result:
        if i == 100:
            break
        i += 1
        if track.add_or_del == 1:
            addtracks.append(track.trackid)
        else:
            deletetracks.append(track.trackid)
        stmt = delete(ChangeTracks).where(ChangeTracks.trackid == track.trackid).where(ChangeTracks.userid == session['userid'])
        db.session.execute(stmt)
    db.session.commit()
        

    if addtracks:
        sp.playlist_add_items(session['playlist_uri'], addtracks)
    if deletetracks:
        sp.playlist_remove_all_occurrences_of_items(session['playlist_uri'], deletetracks)


    stmt = select(ChangeTracks).where(ChangeTracks.userid == session['userid'])
    if not db.session.execute(stmt).first():
        return redirect('/success')
    return redirect('/loadingplaylist3')


@app.route('/success', methods = ["GET", "POST"])
def success():
    #! get created or updated status from "set playlist"
    msg = session["playlist_name"]
    return render_template("success.html", msg = msg)


# gets up to 100 tracks, limited due to Spotify API
def get_tracklist():
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    tracklist = []
    if (session['extra'] == (session['playlist_length'] - session['offset']) ):
        tracklist += sp.current_user_saved_tracks(limit = session['extra'], offset = session['offset'])["items"]
        session['offset'] += session['extra']
    elif (len(sp.current_user_saved_tracks(limit = 50, offset = session['offset'])["items"])) < 50:
        tracklist += sp.current_user_saved_tracks(limit = 50)["items"]
        session['offset'] = session['playlist_length']
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


def check_get_playlist_uri():
    sp = spotipy.Spotify(auth=user.refresh_token)
    playlists = sp.current_user_playlists()
    playlist_exists = 0
    for idx in range(len(playlists["items"])):
        if session["playlist_uri"] == playlists["items"][idx]["uri"]:
            playlist_uri = playlists["items"][idx]["uri"]
            playlist_exists = 1
            if session['playlist_name'] != playlists["items"][idx]["name"]:
                sp.playlist_change_details(playlist_uri, session['playlist_name'])
                stmt = update(Users).where(Users.userid == session['userid']).values(playlist_name = session['playlist_name'])
                db.session.execute(stmt)
                db.session.commit()
            break
    if not playlist_exists:
        playlist_uri = sp.user_playlist_create(session['userid'], session["playlist_name"])["uri"]
        stmt = update(Users).where(Users.userid == session['userid']).values(playlist_uri = playlist_uri)
        db.session.execute(stmt)
        db.session.commit()
    return playlist_uri



def create_spotify_oauth():
    load_dotenv()
    return SpotifyOAuth(
            client_id=os.getenv("CLIENT_ID"),
            client_secret=os.getenv("CLIENT_SECRET"),
            redirect_uri=url_for('authorize', _external=True),
            scope="user-library-read playlist-modify-public playlist-modify-private")

#Need these refactored versions of loading playlist functions
#to run cron job

def process_loadingplaylist():
    get_tracklist()
    if session['offset'] == session['playlist_length']:
        process_loadingplaylist2()

def process_loadingplaylist2():
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
            changetrack = ChangeTracks(userid = session['userid'], trackid = trackid, add_or_del = 1)
            db.session.add(changetrack)
            db.session.commit()
    for trackid in oldset:
        if trackid not in newset:
            changetrack = ChangeTracks(userid = session['userid'], trackid = trackid, add_or_del = 0)
            db.session.add(changetrack)
            db.session.commit()

    stmt = delete(Tracks).where(Tracks.isnew == False).where(Tracks.userid == session['userid'])
    db.session.execute(stmt)
    db.session.commit()

    stmt = update(Tracks).where(Tracks.userid == session['userid']).values(isnew = False)
    db.session.execute(stmt)
    db.session.commit()
    process_loadingplaylist3()

def process_loadingplaylist3():
    session['token_info'], authorized = get_token()
    sp = spotipy.Spotify(auth=user.refresh_token)

    addtracks = []
    deletetracks = []
    stmt = select(ChangeTracks).where(ChangeTracks.userid == session['userid'])
    db_result = db.session.execute(stmt).scalars()
    
    i = 0
    for track in db_result:
        if i == 100:
            break
        i += 1
        if track.add_or_del == 1:
            addtracks.append(track.trackid)
        else:
            deletetracks.append(track.trackid)
        stmt = delete(ChangeTracks).where(ChangeTracks.trackid == track.trackid).where(ChangeTracks.userid == session['userid'])
        db.session.execute(stmt)
    db.session.commit()
        
    if addtracks:
        sp.playlist_add_items(session['playlist_uri'], addtracks)
    if deletetracks:
        sp.playlist_remove_all_occurrences_of_items(session['playlist_uri'], deletetracks)

    stmt = select(ChangeTracks).where(ChangeTracks.userid == session['userid'])
    if not db.session.execute(stmt).first():
        print("Playlist update successful")

# Update the auto_update function to call these new functions
def auto_update():
    stmt = select(Users).where(Users.auto_update == True)
    users = db.session.execute(stmt).scalars()
    for user in users:
        sp = spotipy.Spotify(auth=user.refresh_token)
        session['userid'] = sp.me()["id"]
        session['playlist_name'] = user.playlist_name
        session["playlist_length"] = user.playlist_length
        session['playlist_uri'] = check_get_playlist_uri()
        session['offset'] = 0
        session['extra'] = session['playlist_length'] % 50
        process_loadingplaylist()