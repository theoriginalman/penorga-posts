# Penorga posts

Automatic posting to Instagram (@penorga).

- `media/` holds the posters (.jpg/.png) and video posters (.mp4).
- `queue.json` lists what to post, with the caption and the time (India time). After a post goes out, its status changes to `posted`.
- Every 30 minutes GitHub checks the queue and publishes anything whose time has come.
- The Instagram token lives in the repo secret `IG_TOKEN` (Settings → Secrets and variables → Actions). It is never stored in these files.

A queue entry looks like:

```json
{ "file": "dickinson-nobody.mp4", "caption": "…", "post_at": "2026-11-20T19:30" }
```

If a post fails, its status becomes `failed` with the reason, and it is not retried until someone looks at it.
