"""
Instagram Carousel MCP Server — remote (hosted) version
=========================================================
Given a public Instagram post/reel/carousel URL, fetch it and hand Claude
the caption, author, and every image as real image content, so vision
analysis happens directly in the conversation — no manual screenshotting.

Also exposes a second, more general tool: get_images. Any tool call that
only returns an image URL as a text string doesn't actually give Claude
vision — a URL sitting in a wall of text is just characters, not pixels.
get_images does the same trick get_instagram_post does (download the
bytes, hand them back as real embedded image content) for ANY list of
image URLs, not just Instagram's. This matters because this service runs
on a normal, unrestricted network — it can reach hosts a locked-down
sandbox environment can't (e.g. a marketing-email image CDN), so routing
a "here are some image URLs, show me what's on them" request through this
server is a general fix, not an Instagram-specific one.

The transport is streamable HTTP rather than stdio, so this runs as a
small always-on web server, hostable somewhere reachable over the
internet and addable to Claude as a Connector from any device — iPad and
iPhone included, not just a Mac running Claude Desktop.

Deployment: see README.md in this same folder. Written for Render's free
tier, but any host that can run `pip install -r requirements.txt` and then
`python server.py`, and gives you a public HTTPS URL, will work the same
way.
"""

import os
import re
import mimetypes
from mcp.server.fastmcp import FastMCP, Image
import httpx
import instaloader

mcp = FastMCP(
    "instagram-analyzer",
    stateless_http=True,
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8000)),
)

_context = instaloader.InstaloaderContext(
    sleep=True,
    quiet=True,
    user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
)

_SHORTCODE_RE = re.compile(r"instagram\.com/(?:[^/]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)")


def _extract_shortcode(url: str) -> str:
    match = _SHORTCODE_RE.search(url.strip())
    if not match:
        raise ValueError(
            f"Couldn't find an Instagram post/reel shortcode in '{url}'. "
            "Expecting something like https://www.instagram.com/p/ABC123xyz/ "
            "or https://www.instagram.com/reel/ABC123xyz/"
        )
    return match.group(1)


@mcp.tool()
def get_instagram_post(url: str) -> list:
    """Fetch a public Instagram post (single image, video, or carousel) and
    return its caption, author, and every image as real image content for
    vision analysis.

    Args:
        url: A public Instagram post URL, e.g.
             https://www.instagram.com/p/ABC123xyz/
             https://www.instagram.com/reel/ABC123xyz/

    Returns a text summary block followed by one image per slide. For a
    video post, only the video's cover thumbnail is returned (no frame
    extraction) — say so explicitly when that's the case.

    Only works on public posts. Private accounts, deleted posts, or a
    temporary Instagram rate-limit will raise a clear error instead of
    silently returning nothing.
    """
    try:
        shortcode = _extract_shortcode(url)
        post = instaloader.Post.from_shortcode(_context, shortcode)
    except ValueError:
        raise
    except instaloader.exceptions.ConnectionException as e:
        raise RuntimeError(
            f"Instagram blocked or rate-limited this anonymous request ({e}). "
            "This is common with logged-out scraping under heavy use — wait a "
            "few minutes and try again."
        ) from e
    except instaloader.exceptions.InstaloaderException as e:
        raise RuntimeError(
            f"Couldn't load that post ({type(e).__name__}: {e}). Double-check "
            "the URL is a public post — private accounts and deleted posts "
            "can't be fetched this way."
        ) from e

    is_carousel = post.typename == "GraphSidecar"
    slide_urls: list[str]
    if is_carousel:
        slide_urls = [node.display_url for node in post.get_sidecar_nodes()]
    else:
        slide_urls = [post.url]

    summary_lines = [
        f"Author: @{post.owner_username}",
        f"Post type: {'Carousel' if is_carousel else ('Video (thumbnail only)' if post.is_video else 'Single image')}",
        f"Slide count: {len(slide_urls)}",
        f"Likes: {post.likes}" if post.likes is not None else "",
        "",
        "Caption:",
        post.caption or "(no caption)",
    ]
    content: list = ["\n".join(line for line in summary_lines if line != "")]

    for i, img_url in enumerate(slide_urls, start=1):
        try:
            resp = _context.get_raw(img_url)
            content.append(f"--- Slide {i} of {len(slide_urls)} ---")
            content.append(Image(data=resp.content, format="jpeg"))
        except Exception as e:
            content.append(f"--- Slide {i} of {len(slide_urls)} failed to download: {e} ---")

    return content


_FORMAT_FROM_CONTENT_TYPE = {
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}

_MAX_IMAGES_PER_CALL = 30


def _guess_format(url: str, content_type: str | None) -> str:
    if content_type:
        fmt = _FORMAT_FROM_CONTENT_TYPE.get(content_type.split(";")[0].strip().lower())
        if fmt:
            return fmt
    guessed, _ = mimetypes.guess_type(url)
    if guessed:
        fmt = _FORMAT_FROM_CONTENT_TYPE.get(guessed)
        if fmt:
            return fmt
    return "png"


@mcp.tool()
def get_images(urls: list[str]) -> list:
    """Fetch any list of image URLs and return them as real image content
    for vision analysis — not Instagram-specific, works for any public,
    directly-loadable image URL (e.g. the images embedded in a marketing
    email, a CDN-hosted graphic, etc.).

    This exists because a tool that only returns an image URL as text
    doesn't give Claude actual vision on it — a URL is just characters
    until something downloads the real pixels and hands them back as
    embedded image content, which is what this does. It also runs on this
    server's own normal network, so it can reach hosts a locked-down
    client environment might not be able to fetch directly.

    Args:
        urls: A list of direct image URLs (e.g. ending in .png/.jpg, or
              any URL that actually serves image bytes when fetched).
              Up to 30 per call — split larger batches across multiple
              calls.

    Returns one image per URL, in the order given. If a URL fails (404,
    not actually an image, host unreachable), that one slot reports the
    error instead of silently vanishing — the rest of the batch still
    comes back.
    """
    if len(urls) > _MAX_IMAGES_PER_CALL:
        raise ValueError(
            f"Got {len(urls)} URLs, max {_MAX_IMAGES_PER_CALL} per call. "
            "Split this into multiple calls."
        )

    content: list = [f"Fetched {len(urls)} image(s):"]
    with httpx.Client(headers=_HTTP_HEADERS, timeout=30, follow_redirects=True) as client:
        for i, url in enumerate(urls, start=1):
            try:
                resp = client.get(url)
                resp.raise_for_status()
                fmt = _guess_format(url, resp.headers.get("content-type"))
                content.append(f"--- Image {i} of {len(urls)}: {url} ---")
                content.append(Image(data=resp.content, format=fmt))
            except Exception as e:
                content.append(f"--- Image {i} of {len(urls)} failed ({url}): {e} ---")

    return content


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
