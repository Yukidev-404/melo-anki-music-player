# MELO

### Personal Music Player for Anki

**Version 1.0**  
**Copyright © 2026 Yuki**

MELO is a personal music player built for the Anki desktop environment. It combines local music playback with a compact retro-inspired interface, a vinyl-style visual display, playlists, favorites, visualizations, and customizable ambience.

---

## Features

- Local music playback
- Import individual audio files or entire folders
- Persistent music library
- LIST and DISC browsing modes
- Search
- Queue
- Custom playlists
- Recently played tracks
- Favorites
- Shuffle and repeat
- Clickable and draggable seek bar
- Audio-reactive LOW / HIGH visualizer
- Independent spinning vinyl display
- Custom selector background
- Personalized first-launch name
- Resizable and draggable player window
- Keyboard controls
- Persistent settings

---

## Installation

1. Download the latest `.ankiaddon` file from the [Releases](../../releases) page.
2. Open **Anki**.
3. Go to **Tools → Add-ons → Install from file**.
4. Select the MELO `.ankiaddon` file.
5. Restart Anki.
6. On first launch, MELO will ask:

   > What should I call you?

7. Enter the name you want MELO to use in its welcome message.

Your name is stored locally in Anki's addon configuration.

---

## First Launch

MELO does not ship with a personal name as the default.

On first launch, the addon asks:

> **What should I call you?**

The name you enter is saved locally and used for the personalized message:

```text
welcome back, [name]!
```

This allows the same MELO release to be shared without exposing the author's name as another user's default.

---

# Interface

## Header

### Search

The search field filters the visible music library.

Search can match:

- Track name
- File name
- Containing folder / artist folder

### `•••` Menu

The menu provides additional library and customization actions:

- **+ MUSIC** — import individual audio files
- **+ FOLDER** — recursively import supported audio files from a folder
- **+ PLAYLIST** — create a new playlist
- **ADD CURRENT TO PLAYLIST** — add the current track to a playlist
- **♡ ADD TO FAVORITES / REMOVE FROM FAVORITES** — toggle the current track as a favorite
- **CHANGE BACKGROUND...** — choose a custom music-selector background
- **RESET BACKGROUND** — remove the custom background

---

# Playback Controls

The left playback panel contains the current track, progress, and playback controls.

| Control | Function |
|---|---|
| `⇄` | Toggle Shuffle |
| `\|◀` | Previous track |
| `▶ / ⏸` | Play / Pause |
| `▶\|` | Next track |
| `↻` | Toggle Repeat |
| `♡ / ♥` | Add or remove the current track from Favorites |
| Progress bar | Click anywhere to seek; drag the handle to scrub |

### Previous Track Behavior

Pressing Previous normally moves to the previous track.

When the current track has played for more than a short period, pressing Previous first returns the current song to the beginning.

---

# Library

The music library is divided into five sections:

## LIST

Shows the complete music library in a normal scrollable list.

- Single-click a track to select it.
- Double-click a track to play it.

## QUEUE

Shows tracks currently included in the playback queue.

## PLAYLISTS

Shows your saved playlists.

Creating a playlist:

1. Open `•••`.
2. Select **+ PLAYLIST**.
3. Enter a playlist name.

Adding the current track:

1. Open `•••`.
2. Select **ADD CURRENT TO PLAYLIST**.
3. Choose a playlist.

Opening a playlist switches to its track list.

## RECENT

Shows recently played tracks.

MELO keeps a recent-history list so recently played music can be found quickly.

## FAVORITES

Shows tracks marked as favorites.

A track can be favorited using either:

- the `♡ / ♥` playback button, or
- the Favorites action in the `•••` menu.

---

# LIST Mode

LIST mode is the standard library view.

It is best for:

- browsing many songs
- searching
- working with playlists
- selecting a specific track directly

The list is vertically scrollable and supports pixel-based scrolling.

---

# DISC Mode

DISC mode provides MELO's vinyl-style browsing experience.

The selector presents several track titles around a central selected title and animates when the selection changes.

### DISC controls

- Use the keyboard navigation keys to move through tracks.
- Press **Enter** to play the selected track.
- The vinyl display rotates while music is playing.
- The vinyl texture is supplied by MELO and is not taken from MP3 embedded cover artwork.

The DISC selector also uses the configured music-selector background.

---

# Visualizer

The personal panel contains an audio-reactive visualizer divided into two sections:

```text
LOW | HIGH
```

- **LOW** bars occupy the left side.
- **HIGH** bars occupy the right side.
- All bars use the MELO pink accent.
- A central divider separates the two sections.
- The visualizer clears when playback stops.

---

# Vinyl Display

MELO uses a supplied vinyl texture for its main record display.

The record:

- is displayed independently from the rest of the player
- spins while music is playing
- stops when playback stops
- uses a fixed tonearm layer
- does not use MP3 embedded artwork as the vinyl texture

---

# Custom Background

MELO supports a custom image inside the music-selector area.

The outer player remains its normal light/off-white interface while the custom image is used behind the LIST / DISC selector area.

### Using the menu

Open:

```text
••• → CHANGE BACKGROUND...
```

Choose an image file.

To restore the default:

```text
••• → RESET BACKGROUND
```

### Supported image types

```text
PNG
JPG / JPEG
WEBP
BMP
GIF
```

### Configuration

The background path is stored as:

```json
"background_path": ""
```

A Windows path must escape backslashes in JSON, for example:

```json
"background_path": "C:\\Music\\background.jpg"
```

---

# Keyboard Controls

| Key | Function |
|---|---|
| `Space` | Play / Pause |
| `Left / Right` | Change track while using DISC mode |
| `Enter` | Play the selected DISC-mode track |

---

# Window Controls

MELO is designed as a compact desktop player inside Anki.

### Dragging

The player can be moved by dragging non-interactive areas of the window.

### Resizing

The player can be resized using its resize area.

MELO keeps the player inside the Anki window when moving or resizing it.

---

# Persistent Data

MELO stores its settings in Anki's addon configuration.

Stored data includes:

```text
tracks
volume
shuffle
repeat
mode
welcome_name
recent
favorites
playlists
background_path
```

This allows the library and preferences to remain available after restarting Anki.

---

# Supported Audio

MELO currently accepts:

```text
MP3
WAV
OGG
OGA
FLAC
M4A
AAC
OPUS
WMA
```

Folder imports search recursively for these supported formats.

---

# Source Code

The repository contains the source code used to build MELO as well as its bundled assets and release files.

Main entry point:

```text
__init__.py
```

Manifest:

```text
manifest.json
```

Configuration template:

```text
config.json
```

---

# Project Structure

A typical MELO source repository contains:

```text
melo-anki-music-player/
├── __init__.py
├── manifest.json
├── config.json
├── README.md
├── LICENSE.txt
├── NOTICE.txt
├── .gitignore
└── assets/
    ├── play_icon.png
    ├── pause_icon.png
    ├── disc_texture_centered.png
    └── arm_overlay_centered.png
```

The installable `.ankiaddon` package is provided through the project's GitHub Releases.

---

# Credits & Third-Party Materials

MELO is a custom project by **Yuki**.

Copyright © 2026 Yuki.

Third-party software, fonts, libraries, artwork, audio, and other materials remain the property of their respective owners and are subject to their respective licenses or permissions.

MELO does not claim ownership of user-provided music or other user-provided media.

---

# License

Copyright © 2026 Yuki.

See [`LICENSE.txt`](LICENSE.txt) for the applicable terms.

Unless explicitly permitted by the license or by the copyright holder, do not redistribute or repackage the original MELO project as your own.

---

# Release

## MELO v1.0

The first official MELO release.

See the [Releases](../../releases) page for the installable `.ankiaddon` package.

---

## Author

**Yuki**

Project: [MELO — Personal Music Player for Anki](https://github.com/Yukidev-404/melo-anki-music-player)
