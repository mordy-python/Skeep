import json
from dotenv import load_dotenv
import os
from requests import post, get, delete
import random
from flask import Flask, flash, redirect, render_template, request, session, url_for
import urllib.parse
import base64
from flask_caching import Cache

load_dotenv(".env")

cache = Cache(config={"CACHE_TYPE": "SimpleCache"})
app = Flask(__name__)
cache.init_app(app)
app.config["SECRET_KEY"] = "d44f35e94e11bc0107d928b5bc8bf5b4"
redirect_uri = "http://localhost:5000/callback"

BASE_URL = "https://api.spotify.com/v1"
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
CLIENT_ID = os.getenv("CLIENT_ID")


def generate_random_string(length):
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(random.SystemRandom().choice(chars) for _ in range(length))


def get_access_token():
    if session["access_token"]:
        return session["access_token"]
    else:
        with open("token.json", "r") as token_file:
            session["access_token"] = token["access_token"]
            token = json.load(token_file)
        return session["access_token"]


@app.route("/profile_info")
def info():
    url = BASE_URL + "/me"
    token = get_access_token()

    print(token)

    headers = {
        "Authorization": f"Bearer {token}",
    }

    resp = get(url, headers=headers)

    res_json = resp.json()["id"]
    session["id"] = res_json

    return redirect(url_for("user", user_id=res_json))


@app.route("/")
def index():
    return render_template("home.html")


# @app.route("/top50")
# def top50():
#     url = BASE_URL + "/me/top/tracks"
#     token = get_access_token()

#     headers = {
#         "Authorization": f"Bearer {token}",
#     }

#     params = {"limit": 100, "offset": 0}

#     resp = get(url, headers=headers, params=params)

#     data = resp.json()["items"]

#     return render_template("top50.html", items=data, type="nottrack")


# @app.route("/recent")
# def recentlyPlayed():
#     url = BASE_URL + "/me/player/recently-played"
#     token = get_access_token()

#     headers = {
#         "Authorization": f"Bearer {token}",
#     }
#     params = {"limit": 100, "offset": 0}

#     resp = get(url, headers=headers, params=params)

#     data = resp.json()["items"]

#     return render_template("top50.html", items=data, type="track")


@app.route("/user/<user_id>")
def user(user_id):
    url = BASE_URL + f"/users/{user_id}"

    token = get_access_token()

    print(token)

    headers = {
        "Authorization": f"Bearer {token}",
    }

    resp = get(url, headers=headers)

    return str(resp.content)


def get_playlists():
    user_id = session["id"]
    token = get_access_token()

    url = BASE_URL + f"/users/{user_id}/playlists"
    headers = {
        "Authorization": f"Bearer {token}",
    }

    resp = get(url, headers=headers)

    data = resp.json()

    items = data["items"]
    return items


def get_tracks(playlist_id):
    url = BASE_URL + f"/playlists/{playlist_id}/tracks"

    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
    }

    resp = get(url, headers=headers)

    data = resp.json()

    items = data["items"]

    return items


def create_archive_playlist(with_url=False):
    user_id = session["id"]
    url = BASE_URL + f"/users/{user_id}/playlists"

    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = {"name": "Archive", "public": False, "description": "Songs you used to love"}

    response = post(url, headers=headers, data=json.dumps(data))
    playlist_id = response.json()["id"]

    if with_url:
        playlist_url = response.json()["external_urls"]["spotify"]
        return playlist_id, playlist_url
    else:
        return playlist_id


def add_tracks_to_playlist(playlist_id, tracks):
    url = BASE_URL + f"/playlists/{playlist_id}/tracks"

    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = {"uris": tracks}

    response = post(url, headers=headers, data=json.dumps(data))

    print(response)


def del_track_from_playlist(tracks):
    playlists = {}

    for track in tracks:
        playlist_id = track["fromPlaylist"]
        check_exists = playlists.get(playlist_id)
        if check_exists:
            playlists[playlist_id].append(track)
        else:
            playlists[playlist_id] = [track]

    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    for playlist_id, tracks in playlists.items():
        uris = get_track_uris(tracks)
        url = BASE_URL + f"/playlists/{playlist_id}/tracks"

        data = {"uris": uris}

        response = delete(url, headers=headers, data=json.dumps(data))


@cache.cached(timeout=3600, key_prefix="users_songs")
def get_user_songs():
    playlists = get_playlists()
    users_songs = []
    for playlist in playlists:
        tracks = get_tracks(playlist["id"])
        for track in tracks:
            track["skipCount"] = random.randint(0, 35)
            track["fromPlaylist"] = playlist["id"]
            users_songs.append(track)

    users_songs = list(filter(lambda song: song["skipCount"] > 5, users_songs))[:100]

    return users_songs


@app.route("/songs")
def songs():
    users_songs = get_user_songs()
    users_songs.sort(key=lambda x: x["skipCount"], reverse=True)

    return render_template("playlist.html", items=users_songs)


@app.route("/archive")
def archive():
    users_songs = get_user_songs()

    playlist_id, playlist_url = create_archive_playlist(with_url=True)
    uris = get_track_uris(users_songs)
    add_tracks_to_playlist(playlist_id, uris)
    del_track_from_playlist(users_songs)

    flash(
        f"Your songs have been archived. <a href='{playlist_url}' target='_blank'>View the playlist on Spotify</a>"
    )
    return redirect("/songs")


def get_track_uris(tracks):
    return [track["track"]["uri"] for track in tracks]


@app.route("/login")
def login():
    state = generate_random_string(16)
    scopes = "user-library-modify user-top-read user-read-recently-played playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private"

    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "scope": scopes,
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )

    return redirect(auth_url)


@app.route("/callback")
def callback():
    req = request

    code = req.args.get("code")
    state = req.args.get("state")

    authString = base64.b64encode(bytes(CLIENT_ID + ":" + CLIENT_SECRET, "utf-8"))
    authString = authString.decode("utf-8")

    if state is None:
        return redirect("/#" + "?error=state_mismatch")

    auth_options = {
        "url": "https://accounts.spotify.com/api/token",
        "data": {
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        "headers": {
            "Authorization": f"Basic {authString}",
        },
        "json": True,
    }

    response = post(**auth_options)

    session["access_token"] = response.json()["access_token"]

    if response.status_code != 200:
        return redirect("/#" + "?error={}".format(response.content.decode("utf-8")))

    with open("token.json", "w") as token_file:
        json.dump(response.json(), token_file)

    info()
    return redirect(url_for("songs"))


@app.route("/refresh_token")
def refresh_token():
    with open("token.json", "r") as token_file:
        file = json.load(token_file)
        refresh_tok = file["refresh_token"]

    authString = base64.b64encode(bytes(CLIENT_ID + ":" + CLIENT_SECRET, "utf-8"))
    authString = authString.decode("utf-8")

    auth_options = {
        "url": "https://accounts.spotify.com/api/token",
        "data": {
            "refresh_token": refresh_tok,
            "grant_type": "refresh_token",
        },
        "headers": {
            "Authorization": f"Basic {authString}",
        },
        "json": True,
    }

    response = post(**auth_options)
    access_token = response.json()["access_token"]
    session["access_token"] = access_token
    file["access_token"] = access_token

    with open("token.json", "w") as token_file:
        json.dump(file, token_file)

    return redirect(url_for("songs"))


if __name__ == "__main__":
    app.run(debug=True)
