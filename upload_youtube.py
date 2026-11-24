#!/usr/bin/env python3
"""Upload a video to your own YouTube channel.

Runs on your own computer. The sign-in token is saved outside this repository
(see TOKEN_PATH below) and is never committed.

Only the `youtube.upload` permission is requested: the script can upload
videos and set their thumbnails, but cannot delete or edit other videos.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

CONFIG_DIR = Path(
    os.environ.get("BANGLA_UPLOADER_HOME", Path.home() / ".config" / "bangla-uploader")
)
CLIENT_SECRET_PATH = Path(
    os.environ.get("BANGLA_UPLOADER_CLIENT_SECRET", CONFIG_DIR / "client_secret.json")
)
TOKEN_PATH = CONFIG_DIR / "youtube_token.json"

RETRIABLE_STATUS = {500, 502, 503, 504}
MAX_RETRIES = 8
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB


def get_credentials() -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            print("Saved sign-in was revoked or expired; signing in again.", file=sys.stderr)
            creds = None

    if not creds or not creds.valid:
        if not CLIENT_SECRET_PATH.exists():
            sys.exit(
                f"Missing OAuth client file: {CLIENT_SECRET_PATH}\n"
                "Download it from Google Cloud Console > APIs & Services > Credentials\n"
                "(OAuth client of type 'Desktop app') and save it at that path."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        pass  # e.g. Windows
    return creds


def read_text_arg(value: str | None) -> str | None:
    """Allow `@path/to/file.txt` to read text (handy for long Bangla descriptions)."""
    if value and value.startswith("@"):
        return Path(value[1:]).read_text(encoding="utf-8").strip()
    return value


def resumable_upload(request) -> dict:
    response = None
    retries = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"  uploaded {int(status.progress() * 100)}%", flush=True)
        except HttpError as e:
            if e.resp.status not in RETRIABLE_STATUS:
                raise
            retries += 1
        except (ConnectionError, TimeoutError, OSError):
            retries += 1
        else:
            continue
        if retries > MAX_RETRIES:
            sys.exit("Upload failed after repeated network errors.")
        wait = min(2**retries, 60)
        print(f"  network error, retrying in {wait}s ({retries}/{MAX_RETRIES})", flush=True)
        time.sleep(wait)
    return response


def main() -> None:
    p = argparse.ArgumentParser(description="Upload a video to your YouTube channel.")
    p.add_argument("video", type=Path, help="Video file (e.g. out/video.mp4)")
    p.add_argument("--title", required=True, help="Title (max 100 characters)")
    p.add_argument("--description", default="", help="Description, or @file.txt")
    p.add_argument("--tags", default="", help="Comma-separated tags")
    p.add_argument("--thumbnail", type=Path, help="Thumbnail image (JPG/PNG, < 2 MB)")
    p.add_argument(
        "--privacy",
        choices=["private", "unlisted", "public"],
        default="private",
        help="Default: private. Until the app passes YouTube's API audit, "
        "YouTube forces uploads to private anyway.",
    )
    p.add_argument("--category", default="27", help="Category ID (default 27 = Education)")
    p.add_argument("--language", default="bn", help="Video language (default bn)")
    p.add_argument(
        "--publish-at",
        help="Schedule public release, RFC 3339 UTC, e.g. 2026-12-01T13:00:00Z "
        "(video must be private)",
    )
    p.add_argument("--made-for-kids", action="store_true")
    args = p.parse_args()

    if not args.video.is_file():
        sys.exit(f"Video not found: {args.video}")
    if args.thumbnail and not args.thumbnail.is_file():
        sys.exit(f"Thumbnail not found: {args.thumbnail}")
    title = args.title.strip()
    if not title or len(title) > 100:
        sys.exit("Title must be 1-100 characters.")
    description = read_text_arg(args.description) or ""
    if len(description.encode("utf-8")) > 5000:
        sys.exit("Description is over YouTube's 5000-byte limit.")
    if args.publish_at and args.privacy != "private":
        sys.exit("--publish-at requires --privacy private.")

    youtube = build("youtube", "v3", credentials=get_credentials(), cache_discovery=False)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": [t.strip() for t in args.tags.split(",") if t.strip()],
            "categoryId": args.category,
            "defaultLanguage": args.language,
            "defaultAudioLanguage": args.language,
        },
        "status": {
            "privacyStatus": args.privacy,
            "selfDeclaredMadeForKids": args.made_for_kids,
        },
    }
    if args.publish_at:
        body["status"]["publishAt"] = args.publish_at

    print(f"Uploading {args.video.name} ...")
    media = MediaFileUpload(str(args.video), chunksize=CHUNK_SIZE, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    video = resumable_upload(request)
    video_id = video["id"]
    print(f"Uploaded: https://youtu.be/{video_id}  (status: {video['status']['privacyStatus']})")

    if args.thumbnail:
        try:
            youtube.thumbnails().set(
                videoId=video_id, media_body=MediaFileUpload(str(args.thumbnail))
            ).execute()
            print("Thumbnail set.")
        except HttpError as e:
            print(
                f"Thumbnail failed ({e.resp.status}). Custom thumbnails need a "
                "phone-verified channel: https://www.youtube.com/verify",
                file=sys.stderr,
            )

    if video["status"]["privacyStatus"] != args.privacy:
        print(
            "Note: YouTube set this video to private because the app has not passed "
            "the API audit yet. Change it to public in YouTube Studio.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
