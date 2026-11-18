"""Publish due posts from queue.json to Instagram.

Run by GitHub Actions. Needs two environment variables:
  IG_TOKEN    - the Instagram access token (kept in the repo secret, never in files)
  IG_USER_ID  - the @penorga Instagram account id
Usage:
  python publish.py check   -> confirms the token works, posts nothing
  python publish.py run     -> publishes every queued post whose time has come
"""
import json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

API_VERSION = "v25.0"
IST = timezone(timedelta(hours=5, minutes=30))
QUEUE = "queue.json"
REPO = os.environ.get("GITHUB_REPOSITORY", "theoriginalman/penorga-posts")
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")

TOKEN = os.environ["IG_TOKEN"].strip()
USER_ID = os.environ["IG_USER_ID"].strip()
HOST = "https://graph.instagram.com" if TOKEN.startswith("IG") else "https://graph.facebook.com"


def call(method, path, params=None, data=None, headers=None, url=None):
    params = dict(params or {})
    url = url or f"{HOST}/{API_VERSION}/{path}"
    hdrs = {"Authorization": f"Bearer {TOKEN}"}
    hdrs.update(headers or {})
    body = None
    if method == "GET":
        if params:
            url += "?" + urllib.parse.urlencode(params)
    elif data is not None:
        body = data
    else:
        body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path or url} failed ({e.code}): {e.read().decode(errors='replace')}")


def wait_until_ready(container_id, label):
    for _ in range(60):  # up to ~10 minutes
        status = call("GET", container_id, {"fields": "status_code,status"})
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"{label}: Instagram could not process the media: {status}")
        time.sleep(10)
    raise RuntimeError(f"{label}: media still processing after 10 minutes")


def prepare(item):
    """Upload the media to Instagram and wait until it is ready. Returns the container id (nothing is posted yet)."""
    path = os.path.join("media", item["file"])
    caption = item.get("caption", "")
    if item["file"].lower().endswith((".mp4", ".mov")):
        # Videos go up as a Reel, uploaded straight from the repo (no public link needed).
        c = call("POST", f"{USER_ID}/media",
                 {"media_type": "REELS", "upload_type": "resumable", "caption": caption, "share_to_feed": "true"})
        cid = c["id"]
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            call("POST", None, data=f.read(),
                 url=f"https://rupload.facebook.com/ig-api-upload/{API_VERSION}/{cid}",
                 headers={"Authorization": f"OAuth {TOKEN}", "offset": "0", "file_size": str(size)})
    else:
        # Images must be fetched by Instagram from a public link: the raw file in this repo.
        image_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/media/{urllib.parse.quote(item['file'])}"
        c = call("POST", f"{USER_ID}/media", {"image_url": image_url, "caption": caption})
        cid = c["id"]
    wait_until_ready(cid, item["file"])
    return cid


def publish(item):
    cid = prepare(item)
    res = call("POST", f"{USER_ID}/media_publish", {"creation_id": cid})
    return res["id"]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "check":
        me = call("GET", USER_ID, {"fields": "username"})
        print(f"Token works. Connected to Instagram account: @{me.get('username')}")
        return
    if mode == "test":
        # Upload every queued file Instagram-side WITHOUT publishing, to catch problems early.
        with open(QUEUE) as f:
            queue = json.load(f)
        bad = 0
        for item in queue:
            if item.get("status") in ("posted", "failed"):
                continue
            try:
                prepare(item)
                print(f"OK   {item['file']}")
            except Exception as e:
                bad += 1
                print(f"FAIL {item['file']}: {e}")
        print("Nothing was published.")
        sys.exit(1 if bad else 0)

    with open(QUEUE) as f:
        queue = json.load(f)
    now = datetime.now(IST)
    changed, failed = False, False
    for item in queue:
        if item.get("status") in ("posted", "failed"):  # failed posts wait for a human to look
            continue
        when = datetime.fromisoformat(item["post_at"])
        if when.tzinfo is None:
            when = when.replace(tzinfo=IST)
        if when > now:
            continue
        try:
            media_id = publish(item)
            item["status"] = "posted"
            item["posted_at"] = now.isoformat(timespec="minutes")
            item["media_id"] = media_id
            item.pop("error", None)
            print(f"Posted {item['file']} (media id {media_id})")
        except Exception as e:
            item["status"] = "failed"
            item["error"] = str(e)[:500]
            failed = True
            print(f"FAILED {item['file']}: {e}")
        changed = True
    if changed:
        with open(QUEUE, "w") as f:
            json.dump(queue, f, indent=2, ensure_ascii=False)
            f.write("\n")
    else:
        print("Nothing due right now.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
