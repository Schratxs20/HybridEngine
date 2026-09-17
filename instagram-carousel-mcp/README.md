# Instagram Carousel Analyzer — Hosted Version

This is the fully-automatic version: paste an Instagram URL into Claude,
Claude fetches it and actually sees the images — no Mac, no Terminal, no
screenshotting. Everything below is done through Safari on your iPad or
iPhone, tapping buttons on websites, exactly like signing up for any app.

The code lives in this repo already (in this `instagram-carousel-mcp/`
folder) — you're not writing or editing any code. You're just telling a
free hosting service to run it, then telling Claude where to find it.

---

## Step 1 — Create a free Render account

1. In Safari, go to **render.com**
2. Tap **Get Started**, then **Sign up with GitHub** (simplest — this also
   connects your GitHub account in the same step)
3. Approve the GitHub login prompt if asked

You should not be asked for a credit card for this. If a payment screen
comes up before you've deployed anything, stop and tell me — don't enter
card details.

## Step 2 — Create the web service

1. On Render's dashboard, tap **New +** → **Web Service**
2. It'll ask to connect a GitHub repository — find and select
   **Schratxs20/HybridEngine** (grant Render access to it if asked)
3. Fill in these exact fields:

| Field | Value |
|---|---|
| Name | `instagram-carousel-mcp` (or anything you want) |
| Root Directory | `instagram-carousel-mcp` |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python server.py` |
| Instance Type | **Free** |

4. Tap **Deploy Web Service**

It'll take 2-3 minutes on the first build — you'll see a log scrolling by,
that's normal. When it's done, Render shows a URL at the top of the page
that looks like:

```
https://instagram-carousel-mcp.onrender.com
```

That's your server's address. Keep this page open or copy the URL
somewhere — you need it for the next step.

## Step 3 — Add it to Claude

1. Open Claude (the app or claude.ai) → **Settings** → **Connectors**
2. Tap **Add custom connector** (may also be called "Add more")
3. Paste your URL from Step 2 with `/mcp` added on the end, e.g.:
   ```
   https://instagram-carousel-mcp.onrender.com/mcp
   ```
4. Save/Add it

## Step 4 — Test it

Start a new chat and paste a real public Instagram post URL, asking Claude
to analyze it. First request might take 30-60 seconds to respond — that's
the free server "waking up" after being idle, not an error. Every request
after that in the same session is fast.

If it works, Claude should describe what's actually in the images, not
just repeat the caption back to you.

---

## Things worth knowing

- **The free tier sleeps.** Render's free web services spin down after 15
  minutes of no use and take about 30-60 seconds to wake back up on the
  next request. Fine for occasional personal use like this; just expect
  that first-of-the-day delay.
- **Public posts only**, same as before — no Instagram login involved, so
  private accounts and deleted posts won't work.
- **If it stops working** after Instagram changes something on their end,
  the fix is bumping the `instaloader` version. Tell me and I'll push an
  update to this repo — Render automatically redeploys whenever the repo
  changes, so you won't need to touch anything.
- **Video posts** return only the cover thumbnail, not frame-by-frame
  video — same limitation as before.
