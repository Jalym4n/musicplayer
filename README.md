# ♡ Pinkie Player

A cute, retro, pixel-style **desktop** music player for your **Spotify Premium** account.
Album covers, your playlists, Liked Songs, Recently Played, search, and a vinyl record that
spins while your song plays.

![Pinkie Player](docs/screenshot.png)

**Not a web app and not Chrome-based.** It's a native Qt app written in Python. It
installs only `PySide6-Essentials`, which doesn't include Qt's browser engine
(QtWebEngine/Chromium) at all. The only time a browser opens is the one-time Spotify login
page, because Spotify requires you to log in on their own site.

## Features

- Pink gingham "device" window with a custom frameless title bar, pixel fonts and pixel icons
- Sidebar with your playlists (with cover art), **Liked Songs** and **Recently Played**
- Song list with album thumbnails. Double-click a song (or press Enter) to play it
- Now-playing panel: polaroid album cover, spinning vinyl, scrolling title, heart-knob
  progress and volume sliders, shuffle, repeat (all / one), previous / next
- Speaker picker so you can play on your computer, phone, TV or smart speaker
- Search (Ctrl+F)
- Keyboard: **Space** play/pause · **Ctrl+→** next · **Ctrl+←** previous · **Ctrl+Q** quit
- `--demo` mode to preview the whole app with made-up music, no account needed

## How playback works (read this first)

Spotify doesn't let third-party apps stream audio themselves. There are two ways to hear music:

1. **Remote control (works out of the box).** Pinkie Player controls Spotify playing on any
   of your devices through Spotify Connect: the Spotify app on your phone or computer, a
   smart speaker, a TV. Open Spotify on one of them once, then choose it in Pinkie Player's
   speaker menu.
2. **Built-in speaker (optional, recommended).** Install
   [librespot](https://github.com/librespot-org/librespot), an open-source Spotify Connect
   player. Pinkie Player finds it and starts it in the background, so **the music comes out
   of this computer without the official Spotify app**. The first time, a browser tab asks you
   to log in once for it. librespot isn't an official Spotify product, so use a recent
   version.

## Setup (about 5 minutes)

### 1. Install Python
Get Python 3.10 or newer from [python.org](https://www.python.org/downloads/).
On Windows, tick **"Add Python to PATH"** during install.

### 2. Get the code and install
```bash
git clone https://github.com/Jalym4n/musicplayer.git
```
```bash
cd musicplayer
```
```bash
python -m pip install -r requirements.txt
```
(On macOS/Linux use `python3` if `python` isn't found.)

### 3. Try the demo (optional)
```bash
python -m pinkie --demo
```

### 4. Create your free Spotify developer app
Spotify requires every app to have a **Client ID**. Yours is free and takes 2 minutes:

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and log in
   with your **Premium** account.
2. Click **Create app**. Use any name and description, e.g. "Pinkie Player".
3. Under **Redirect URIs** add exactly:
   ```
   http://127.0.0.1:8898/callback
   ```
   Use `127.0.0.1`, not `localhost`. Spotify rejects `localhost`.
4. Under "Which API/SDKs are you planning to use?" tick **Web API**, accept the terms, **Save**.
5. Open the app's **Settings** and copy the **Client ID**. You don't need the client secret.

### 5. Run it
```bash
python -m pinkie
```
Paste your Client ID into the setup window and click **let's go!**. Your browser opens the
Spotify login. Approve it, close the tab, and your playlists appear. You stay logged in
next time.

### 6. (Optional) Make the computer the speaker with librespot
- **macOS:** `brew install librespot`
- **Windows / Linux:** download a release from the
  [librespot releases page](https://github.com/librespot-org/librespot/releases), or with Rust
  installed run `cargo install librespot`.

Restart Pinkie Player. It finds librespot automatically, or you can point to it under
**Settings (gear icon) → play through this computer**. Then pick **"Pinkie Player"** in the
speaker menu.

## Make it a real double-click app

```bash
python -m pip install -r requirements-dev.txt
```
```bash
python scripts/build.py
```

| OS      | Result                                           |
|---------|--------------------------------------------------|
| Windows | `dist/Pinkie Player/Pinkie Player.exe`           |
| macOS   | `dist/Pinkie Player.app` (drag to Applications)   |
| Linux   | `dist/Pinkie Player/Pinkie Player`               |

Build on the same OS you'll run it on. On macOS, the first launch of an unsigned app needs
**right-click → Open**.

## Spotify's rules for personal apps (2026)

Your Client ID runs in Spotify's **Development Mode**, which is meant for personal projects:

- The **app owner must have Premium**, and playback control only works with Premium.
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
| "Port 8898 is busy" | Close other copies of Pinkie Player and try again |
| "No speaker yet" | Open Spotify on your phone or computer (or install librespot), then pick it in the speaker menu |
| "Playback control needs Spotify Premium" | The logged-in account isn't Premium |
| "asking too often" | Spotify's rate limit. Wait a minute |
| A playlist says its songs are private | Spotify blocks listing songs of playlists you don't own. Press **play** anyway |
| Want to switch accounts | Settings (gear) → **log out**, then reopen the app |

Settings and your login token are stored only on your computer:
`%APPDATA%\Pinkie Player` (Windows), `~/Library/Application Support/Pinkie Player` (macOS),
`~/.config/pinkie-player` (Linux).

## Project layout

```
pinkie/
  app.py            entry point (python -m pinkie)
  main_window.py    window + logic tying the UI to Spotify
  auth.py           Spotify PKCE login (no client secret) + token refresh
  spotify.py        Web API client (2026 Development Mode endpoints)
  demo.py           offline fake Spotify for --demo
  librespot.py      optional built-in speaker
  images.py         album cover download + cache
  theme.py          palette, stylesheet, pixel icons
  widgets/          title bar, sidebar, track list, vinyl cover, sliders, dialogs
  assets/fonts/     Pixelify Sans + VT323 (SIL Open Font License)
tests/              python -m pytest
```

Fonts: [Pixelify Sans](https://github.com/eifetx/Pixelify-Sans) and VT323, both under the
SIL Open Font License (license files in `pinkie/assets/fonts`).
