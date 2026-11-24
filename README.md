# Bangla Uploader

Personal tool that uploads my own Bangla videos to my own YouTube channel.
The website pages (`index.html`, `privacy.html`) are served by GitHub Pages.

## Security

- Runs on my own computer. The sign-in token is stored in
  `~/.config/bangla-uploader/youtube_token.json` (permissions `600`), **outside this repo**.
- Asks only for the `youtube.upload` permission: it can upload videos and set their thumbnails,
  but cannot delete or edit other videos.
- `.gitignore` blocks `client_secret*.json` and token files. This repo is public: never commit them.
- Revoke access any time at https://myaccount.google.com/permissions.

## One-time setup

1. In Google Cloud Console → APIs & Services:
   - Enable **YouTube Data API v3**.
   - Credentials → Create credentials → OAuth client ID → type **Desktop app**.
   - Download the JSON and save it as `~/.config/bangla-uploader/client_secret.json`.
2. Install:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. On the first upload a browser window opens: sign in with the channel's Google account.
   You'll see "Google hasn't verified this app" — click **Advanced → Go to Bangla Uploader**.
   That's expected for a personal app.

## Upload

```bash
python upload_youtube.py out/video.mp4 \
  --title "ভিডিওর শিরোনাম" \
  --description @out/description.txt \
  --tags "বাংলা,ইতিহাস" \
  --thumbnail out/cover.jpg \
  --privacy public
```

Options: `--privacy private|unlisted|public` (default `private`),
`--publish-at 2026-12-01T13:00:00Z` (scheduled release, with `--privacy private`),
`--category` (default `27` Education), `--language` (default `bn`), `--made-for-kids`.

## Known limits

- Until the app passes YouTube's [API compliance audit](https://support.google.com/youtube/contact/yt_api_form),
  YouTube forces API uploads to **private**. Switch them to public in YouTube Studio, or apply for the audit.
- Custom thumbnails need a phone-verified channel: https://www.youtube.com/verify
- Default API quota is 10,000 units/day; one upload costs about 1,600, so roughly 6 uploads per day.
