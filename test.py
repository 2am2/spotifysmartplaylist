import time
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import Flask, url_for, session, request, redirect, render_template
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv



def login():
    sp_oauth = create_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    print(auth_url)
    return authorize()

def authorize():
    sp_oauth = create_spotify_oauth()
    session.clear()
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code, check_cache=False)
    return token_info

def create_spotify_oauth():
    load_dotenv()
    return SpotifyOAuth(
            client_id=os.getenv("CLIENT_ID"),
            client_secret=os.getenv("CLIENT_SECRET"),
            scope="user-library-read playlist-modify-public playlist-modify-private")


def get_tracklist(sp):
    
    tracklist = []
    playlist_length = 101

    if (len(sp.current_user_saved_tracks(limit = 50)["items"])) < 50:
        playlist_length = (len(sp.current_user_saved_tracks(limit = 50)["items"]))
        tracklist += sp.current_user_saved_tracks(limit = playlist_length)["items"]
    else:
        divs = playlist_length//50
        extra = playlist_length % 50
        count = 0
        for count in range(divs):
            count += 1
            
            tracklist += sp.current_user_saved_tracks(limit = 50, offset = count*50)["items"]   
        if extra != 0:
            print("!!!!!!!!!")
            tracklist += sp.current_user_saved_tracks(limit = extra, offset = count*50)["items"]
    
    for i in range(len(tracklist)):
        tracklist[i] = tracklist[i]["track"]["uri"]

    return tracklist

token_info = login()
sp = spotipy.Spotify(auth=token_info)
sp.get_tracklist()