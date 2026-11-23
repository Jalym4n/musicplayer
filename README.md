# ✨ Aayusha's Music Player 🦦 ✨

A cute, retro, pixel-style **desktop** music player made for Aayusha, for her **Spotify
Premium** account. Lavender-and-pink holographic look, a spinning CD and cassette, her
playlists, an UP NEXT notebook, a heartbeat screen, a floating Mini-Player, and an otter
pal who says sweet things. **The music plays straight out of your computer's speakers or
headphones.** You don't need the Spotify app, a phone or a browser tab to play music.

![Aayusha's Music Player](docs/screenshot.png)

**Not a web app and not Chrome-based.** It's a native Qt app written in Python. It
installs only `PySide6-Essentials`, which doesn't include Qt's browser engine
(QtWebEngine/Chromium) at all.

## How it plays music

Spotify's public API doesn't hand audio to apps, so the app has a **built-in
speaker**: [librespot](https://github.com/librespot-org/librespot), an open-source Spotify
player that works with Premium. It ships inside the app. When the app opens, it
starts the speaker quietly in the background and plays every song through it.

- The speaker panel (bottom right) shows its status: a **mint light** means music
  comes out of your speakers.
- The speaker is private. It's hidden from other people on your Wi-Fi, so only your
  account can use it.
- If you start music on your phone, the panel says so. Tap it to **bring the music back**
  to the computer. Pressing play in the app always plays on the computer.

librespot isn't made by Spotify. It's a widely used open-source project, and using it
with your own Premium account is the same thing apps like `spotifyd` and `ncspot` do.

## Features

- **Made for Aayusha:** her name in the title, greetings, an otter pal 🦦 with little
  notes (tap it for hearts), and an otter that swims along the progress bar. The 🦦 is
  drawn with the computer's own emoji font, so on her Mac it's Apple's otter
- **Mini-Player** (title bar button or Ctrl+M): a tiny always-on-top window with the
  cover, title and controls
- **UP NEXT** notebook showing Spotify's queue (double-click to jump to a song)
- **Favorites:** right-click a playlist → "add to favorites" pins it in its own section

- Holographic "screen" with a spinning CD, the album cover and a cassette whose reels turn
- LCD marquee with ARTIST - TITLE (YEAR), a big glossy heart play button
- Sidebar: MY LIBRARY, DISCOVER, FAVORITES and PLAYLISTS with cover art
- Song list on notebook paper. Double-click a song (or press Enter) to play it
- 320 kbps playback with volume levelling
- Search (Ctrl+F)
- Keyboard: **Space** play/pause · **Ctrl+→** next · **Ctrl+←** previous ·
  **Ctrl+M** mini-player · **Ctrl+Q** quit
- `--demo` mode to preview the whole app with made-up music, no account needed

## Setup

### Step 1: Create your free Spotify developer app (2 minutes, everyone)
Spotify requires every app to have a **Client ID**:

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and log in
   with your **Premium** account.
2. Click **Create app**. Use any name and description, e.g. "Aayusha's Music Player".
3. Under **Redirect URIs** add exactly:
   ```
   http://127.0.0.1:8898/callback
   ```
   Use `127.0.0.1`, not `localhost`. Spotify rejects `localhost`.
4. Under "Which API/SDKs are you planning to use?" tick **Web API**, accept the terms, **Save**.
5. Open the app's **Settings** and copy the **Client ID**. You don't need the client secret.

### Step 2, option A: Download the ready-made app (easiest)
Every push to this repo builds the app for Windows, macOS and Linux with GitHub Actions,
with the speaker already inside:

1. Open the repo's **Actions** tab → **Build Aayusha's Music Player** → the latest green run.
2. Under **Artifacts**, download `AayushaMusicPlayer-Windows`, `AayushaMusicPlayer-macOS` or
   `AayushaMusicPlayer-Linux` and unzip it.
3. Open it:
   - **Windows:** run `Aayusha's Music Player.exe` inside the folder. If SmartScreen warns, click
     **More info → Run anyway**.
   - **macOS:** drag **Aayusha's Music Player.app** to Applications. The app isn't signed by Apple,
     so run this once in Terminal:
     ```bash
     xattr -dr com.apple.quarantine "/Applications/Aayusha's Music Player.app"
     ```
   - **Linux:** run `Aayusha's Music Player` inside the folder.

### Step 2, option B: Run from source
1. Install **Python 3.10+** ([python.org](https://www.python.org/downloads/); on Windows tick
   **"Add Python to PATH"**) and **Rust** ([rustup.rs](https://rustup.rs), for building the speaker).
   On Linux, also run `sudo apt install libasound2-dev pkg-config`.
2. Get the code and install:
   ```bash
   git clone https://github.com/Jalym4n/musicplayer.git
   ```
   ```bash
   cd musicplayer
   ```
   ```bash
   python -m pip install -r requirements.txt
   ```
3. Build the speaker once (takes a few minutes):
   ```bash
   python scripts/build_librespot.py
   ```
4. Start the app:
   ```bash
   python -m pinkie
   ```
   (On macOS/Linux use `python3` if `python` isn't found.)

To build your own double-click app instead, run
`python -m pip install -r requirements-dev.txt` and then `python scripts/build.py`. The
result goes in `dist/`.

### Step 3: First launch
1. Paste your **Client ID** into the setup window and click **let's go!**
2. Your browser opens the Spotify login. Approve it and close the tab.
3. A second Spotify tab opens **once** so the built-in speaker can sign in (Spotify
   requires its own login for it). Approve it and close the tab. The speaker panel turns
   **mint**.
4. Pick a playlist and press play ♡

You stay logged in after that, so later launches go straight to your music.

## Personalizing

- **Her name:** Settings (gear) → "who's this player for?". It updates the title, the
  greetings and the speaker's name in Spotify.
- **The otter's notes:** edit `NOTES` in `pinkie/personal.py`, then rebuild (or push, and
  GitHub builds new apps).

## Spotify's rules for personal apps (2026)

Your Client ID runs in Spotify's **Development Mode**, which is meant for personal projects:

- The **app owner must have Premium**, and playback only works with Premium.
- Up to **5 users** can be added to one app (Dashboard → your app → **User Management**).
  You're included automatically as the owner.
- Spotify only lets apps read the **song list of playlists you created or collaborate on**.
  Playlists you follow still show up with their cover and the **play** button works, but
  their songs aren't listed.
- Search returns 10 results per request, so the app fetches up to 3 pages.

## Troubleshooting

| Problem | Fix |
|---|---|
| "INVALID_CLIENT: Invalid redirect URI" in the browser | The redirect URI in the dashboard must be exactly `http://127.0.0.1:8898/callback` |
| "Port 8898 is busy" | Close other copies of the app and try again |
| Speaker panel says **speaker missing** | Running from source: run `python scripts/build_librespot.py`. Or use the downloaded app |
| Speaker panel says **no sound output found** | Plug in or switch on speakers/headphones, then tap the panel to restart the speaker |
| Speaker panel says **speaker login** | Finish the Spotify tab that opened. Tap the panel to open it again |
| Speaker panel shows **speaker trouble**, or keeps saying "warming up" / "restarting" | Settings (gear) → **reset speaker login**, then approve the Spotify tab. Still stuck? Settings → **open speaker log** and send the last 30 lines |
| macOS says the app or `librespot` "can't be opened" | Run the `xattr` command from Step 2A |
| "Playback control needs Spotify Premium" | The logged-in account isn't Premium |
| "asking too often" | Spotify's rate limit. Wait a minute |
| A playlist says its songs are private | Spotify blocks listing songs of playlists you don't own. Press **play** anyway |
| Want to switch accounts | Settings (gear) → **log out**, then reopen the app |

`python -m pinkie --check-speaker` prints where the app found its speaker.

Settings, your login token and the speaker's saved login are stored only on your computer:
`%APPDATA%\Pinkie Player` (Windows), `~/Library/Application Support/Pinkie Player` (macOS),
`~/.config/pinkie-player` (Linux).

## Project layout

```
pinkie/
  app.py            entry point (python -m pinkie)
  personal.py       her name + the otter's sweet notes
  main_window.py    window + logic tying the UI to Spotify
  speaker.py        built-in speaker: runs librespot, handles its login and restarts
  auth.py           Spotify PKCE login (no client secret) + token refresh
  spotify.py        Web API client (2026 Development Mode endpoints)
  demo.py           offline fake Spotify for --demo
  images.py         album cover download + cache
  theme.py          palette, stylesheet, pixel icons
  widgets/          deck (CD/cassette screen), sidebar, notebook, mini-player, dialogs
  assets/fonts/     Pixelify Sans + VT323 (SIL Open Font License)
scripts/
  build_librespot.py  compiles the speaker (librespot 0.8.0) into pinkie/bin/
  build.py            builds the double-click app with the speaker bundled
.github/workflows/build.yml   Windows/macOS/Linux builds on every push
tests/              python -m pytest
```

Fonts: [Pixelify Sans](https://github.com/eifetx/Pixelify-Sans) and VT323, both under the
SIL Open Font License (license files in `pinkie/assets/fonts`). librespot is MIT licensed.
