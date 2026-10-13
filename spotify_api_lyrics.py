"""
Floating Lyric Windows, synced to Spotify (lyrics from LRCLIB)

Setup:
    sudo apt install python3-tk -y
    pip install spotipy requests --break-system-packages

Usage:
    1. Fill in CLIENT_ID and CLIENT_SECRET below.
    2. Start playing a song in Spotify (pause it right before the part you want).
    3. Run: python3 lyric_float.py
    4. Start your screen recorder, click "Start", then press play in Spotify.
"""

import re
import time
import threading
import tkinter as tk
import random
import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# ====================== EDIT THIS SECTION ======================

CLIENT_ID = "INSERT CLIENT_ID"
CLIENT_SECRET = "INSERT CLIENT_SECRET"
REDIRECT_URI = "http://127.0.0.1:8888/callback"

TIME_OFFSET = 0.387      # seconds; raise if lyrics feel late, lower if early
TYPEWRITER_MS = 40       # ms per character

BOX_W, BOX_H = 300, 250
FONT = ("Georgia", 20, "bold italic")   # try: "Segoe UI", "Consolas", "Impact", "Comic Sans MS"
BG_COLOR = "#ffe4ec"                    # box background
FG_COLOR = "#7a1f3d"                    # text color

RISE_SPEED = 90           # pixels per second
BOTTOM_SPAWN_OFFSET = 150

PALETTE = [
    ("#ffe4ec", "#d60047"),   # red
    ("#e0f2ff", "#16405f"),   # blue
    ("#e8ffe0", "#1f5f2a"),   # green
    ("#fff6c9", "#5f4b16"),   # yellow
    ("#efe0ff", "#41205f"),   # purple
]

# ===============================================================

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope="user-read-playback-state user-read-currently-playing",
))

LRC_LINE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")


def parse_lrc(lrc_text):
    lyrics = []
    for line in lrc_text.splitlines():
        m = LRC_LINE.match(line)
        if m and m.group(3).strip():
            t = int(m.group(1)) * 60 + float(m.group(2))
            lyrics.append((t, m.group(3).strip()))
    return lyrics


def fetch_lyrics(track, artist, album, duration_s):
    headers = {"User-Agent": "lyric-float/1.0"}
    try:
        r = requests.get(
            "https://lrclib.net/api/get",
            params={"track_name": track, "artist_name": artist,
                    "album_name": album, "duration": int(duration_s)},
            headers=headers, timeout=10,
        )
        if r.status_code == 200 and r.json().get("syncedLyrics"):
            return parse_lrc(r.json()["syncedLyrics"])
    except requests.RequestException:
        pass
    try:
        r = requests.get(
            "https://lrclib.net/api/search",
            params={"q": f"{artist} {track}"},
            headers=headers, timeout=10,
        )
        for item in r.json():
            if item.get("syncedLyrics"):
                return parse_lrc(item["syncedLyrics"])
    except (requests.RequestException, ValueError):
        pass
    return []


class LyricBox:
    def __init__(self, master, text, x, y):
        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        bg, fg = random.choice(PALETTE)
        self.win.configure(bg=bg)
        self.win.geometry(f"{BOX_W}x{BOX_H}+{int(x)}+{int(y)}")
        self.win.resizable(False, False)

        bar = tk.Frame(self.win, bg="#111111", height=26)
        bar.pack(fill="x")
        tk.Label(bar, text="lyrics.exe", font=("Consolas", 10), bg="#111111", fg="#ffffff").pack(side="left", padx=8)
        tk.Label(bar, text="✕", font=("Consolas", 10), bg="#111111", fg="#ffffff").pack(side="right", padx=8)
        self.full_text = text
        self.label = tk.Label(
            self.win, text="", font=FONT, bg=bg, fg=fg,
            wraplength=BOX_W - 30, justify="center",
        )
        self.label.pack(expand=True, fill="both", padx=15, pady=15)

        self.idx = 0
        self.x = x
        self.y = float(y)
        self.typewriter()

    def rise(self, dy):
        self.y -= dy
        self.win.geometry(f"{BOX_W}x{BOX_H}+{int(self.x)}+{int(self.y)}")

    def is_offscreen(self):
        return self.y + BOX_H < -50

    def typewriter(self):
        if self.idx <= len(self.full_text):
            self.label.config(text=self.full_text[:self.idx])
            self.idx += 1
            self.win.after(TYPEWRITER_MS, self.typewriter)


class LyricFloatApp:
    def __init__(self, root):
        self.root = root
        root.title("Lyric Float Controller")
        root.geometry(f"{BOX_W}x{BOX_H}")
        root.configure(bg=BG_COLOR)
        root.resizable(False, False)

        self.start_btn = tk.Button(
            root, text="Start", font=FONT, bg=BG_COLOR, fg=FG_COLOR,
            relief="flat", command=self.start,
        )
        self.start_btn.pack(expand=True, fill="both", padx=15, pady=15)

        self.screen_w = root.winfo_screenwidth()
        self.screen_h = root.winfo_screenheight()

        self.lyrics = []
        self.next_lyric_idx = 0
        self.boxes = []
        self.current_side = "left"
        self.base_pos = 0.0
        self.base_time = time.time()
        self.last_sync = time.time()
        self.last_frame_time = time.time()
        self.playing = True

    def next_x(self):
        center_x = self.screen_w // 2
        left_x = center_x - (BOX_W + 60)
        right_x = center_x + 60
        if self.current_side == "left":
            self.current_side = "right"
            return left_x
        self.current_side = "left"
        return right_x

    def sync_spotify(self):
        try:
            pb = sp.current_playback()
            if pb and pb.get("item"):
                self.playing = pb["is_playing"]
                self.base_pos = pb["progress_ms"] / 1000
                self.base_time = time.time()
        except Exception as e:
            print("Spotify sync failed:", e)

    def start(self):
        pb = sp.current_playback()
        if not pb or not pb.get("item"):
            print("Play a song in Spotify first!")
            return

        item = pb["item"]
        track = item["name"]
        artist = item["artists"][0]["name"]
        album = item["album"]["name"]
        duration = item["duration_ms"] / 1000

        self.lyrics = fetch_lyrics(track, artist, album, duration)
        if not self.lyrics:
            print(f"No synced lyrics found for {artist} - {track}")
            return
        print(f"Loaded {len(self.lyrics)} lines for {artist} - {track}")

        self.start_btn.pack_forget()
        self.root.iconify()

        self.playing = pb["is_playing"]
        self.base_pos = pb["progress_ms"] / 1000
        self.base_time = time.time()
        self.last_frame_time = time.time()
        self.last_sync = time.time()

        self.next_lyric_idx = 0
        while (self.next_lyric_idx < len(self.lyrics) and self.lyrics[self.next_lyric_idx][0] < self.base_pos):
            self.next_lyric_idx += 1

        self.tick()

    def tick(self):
        now = time.time()
        dt = now - self.last_frame_time
        self.last_frame_time = now

        # Re-sync with Spotify every 3 seconds, off the main thread
        if now - self.last_sync > 3:
            self.last_sync = now
            threading.Thread(target=self.sync_spotify, daemon=True).start()

        if self.playing:
            elapsed = self.base_pos + (now - self.base_time) + TIME_OFFSET

            while (self.next_lyric_idx < len(self.lyrics) and self.lyrics[self.next_lyric_idx][0] <= elapsed):
                _, text = self.lyrics[self.next_lyric_idx]
                y = self.screen_h - BOX_H - BOTTOM_SPAWN_OFFSET
                self.boxes.append(LyricBox(self.root, text, self.next_x(), y))
                self.next_lyric_idx += 1

            dy = RISE_SPEED * dt
            for box in self.boxes:
                box.rise(dy)

        visible = []
        for box in self.boxes:
            if box.is_offscreen():
                try:
                    box.win.destroy()
                except tk.TclError:
                    pass
            else:
                visible.append(box)
        self.boxes = visible

        if self.next_lyric_idx < len(self.lyrics) or self.boxes:
            self.root.after(16, self.tick)


if __name__ == "__main__":
    root = tk.Tk()
    LyricFloatApp(root)
    root.mainloop()
