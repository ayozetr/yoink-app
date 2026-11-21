# Yoink CLI

`yoink-core` is both the backend server **and** a command-line downloader: with no
arguments it serves the API (how the desktop app launches it); with arguments it
runs the CLI. It drives the same engine (yt-dlp + ffmpeg) and shares the same
settings and history as the app.

Invoking it:

- **From source:** `scripts/yoink <url> …` (forwards to the built `yoink-core`).
- **Installed (.deb/.rpm):** `yoink-cli <url> …` (ships at `/usr/bin/yoink-cli`).

```bash
yoink https://youtu.be/… --audio -f flac -o ~/Music
```

## What it does

- **Single URL, batch and stdin** — pass several URLs, `-a/--batch-file FILE`
  (repeatable), or `-` to read URLs from stdin (only the http(s) links in the
  text are used, so a file with notes/comments works).
- **Video or audio** — `--audio`/`--video`, `-f/--format` (mp3/m4a/opus/flac/wav),
  `-c/--container` (mp4/mov/mkv/webm), `-q/--quality` (e.g. `1080`, `best`).
- **Playlists** — a playlist URL is expanded; pick with `--items 1,3-5`,
  `--filter TEXT`, `--skip-existing`, or just list it with `--list`.
- **Music-service imports** — a Spotify / Deezer / Apple Music / Tidal / Amazon
  URL is resolved to a tracklist, each track matched on YouTube and tagged with
  the exact source metadata (same as the app's import card).
- **Extras** — `--trim-start`/`--trim-end` (accept `90`, `1:30`, `1:02:03`),
  `--subs [LANG]`/`--no-subs`, `--chapters`/`--no-chapters`, `--vr`/`--vr-layout`,
  `--normalize`/`--normalize-lufs`, `--tag` (auto-tag audio from the catalogue),
  SponsorBlock, cookies, proxy and rate-limit overrides.
- **Inspect** — `--info` (metadata), `--list` (playlist/import entries),
  `--list-formats` (a single video's formats). Add `--json` for machine output.

Per-run flags like `-o/--output`, `--rate-limit`, `--proxy`, `--cookies-*`,
`--sponsorblock`, `--normalize*`, `--video-codec` and `--audio-bitrate` apply for
that invocation only; `yoink config set …` changes them persistently.

## Settings

```bash
yoink config                 # print all settings
yoink config get KEY         # print one
yoink config set KEY VALUE   # set + persist one (shared with the app)
```

## Examples

```bash
# Best-quality MP4 into a folder
yoink https://youtu.be/… -o ~/Videos

# A whole Spotify playlist as FLAC, tagged, skipping what you already have
yoink https://open.spotify.com/playlist/… -f flac --skip-existing

# Clip 1:00–1:30 of a video
yoink https://youtu.be/… --trim-start 1:00 --trim-end 1:30

# Batch from a text file (only the links are taken)
yoink -a urls.txt --audio -f mp3

# A 360° VR download, auto-detecting the layout
yoink https://youtu.be/… --vr
```

## Shell completion

```bash
yoink --print-completion bash > ~/.local/share/bash-completion/completions/yoink
yoink --print-completion zsh  > "${fpath[1]}/_yoink"
yoink --print-completion fish > ~/.config/fish/completions/yoink.fish
```

Run `yoink --help` for the full flag list.
