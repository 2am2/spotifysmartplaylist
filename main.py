import base64
from dotenv import load_dotenv
import os
from requests import post, get
import json

load_dotenv()

cID = os.getenv("CLIENT_ID")
cSecret = os.getenv("CLIENT_SECRET")

def get_token():
    auth_string = cID + ":" + cSecret
    auth_bytes = auth_string.encode("utf-8")
    auth_base64 = str(base64.urlsafe_b64encode(auth_bytes), "utf-8")

    url = "https://accounts.spotify.com/api/token"
    headers = {
        "Authorization": "Basic " + auth_base64,
        "Content-Type": "application/x-www-form-urlencoded "
    }
    data = {"grant_type":"client_credentials"}
    
    result = post(url, headers = headers, data = data)
    #result's post request gives us 'invalid client'

    json_result  = json.loads(result.content)
    
    token = json_result["access_token"]
    return token

def get_auth_header(token):
    return {"Authorization": "Bearer " + token}

def artist_search(token, artist):
    url = "https://api.spotify.com/v1/search"
    headers = get_auth_header(token)
    query = f"?q={artist}&type=artist&limit=1"
    qrl = url + query
    result = get(qrl, headers=headers)
    json_result  = json.loads(result.content)["artists"]["items"]
    if len(json_result) == 0:
        print("no one has ever had that name")
        return None 
    return json_result[0]

token = get_token()
result = artist_search(token, "gub")
print(result["name"])

