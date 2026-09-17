"""
Instagram Carousel MCP Server — remote (hosted) version
=========================================================
Same job as the local version: given a public Instagram post/reel/carousel
URL, fetch it and hand Claude the caption, author, and every image as real
image content, so vision analysis happens directly in the conversation —
no manual screenshotting.

The only difference from the local version is the transport: this runs as
a small always-on web server (streamable HTTP), so it can be hosted
somewhere reachable over the internet and added to Claude as a Connector
from any device — iPad and iPhone included, not just a Mac running Claude
Desktop.

Deployment: see README.md in this same folder. Written for Render's free
tier, but any host that can run `pip install -r requirements.txt` and then
`python server.py`, and gives you a public HTTPS URL, will work the same
way.
"""

import os
import re
from mcp.server.fastmcp import FastMCP, Image
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


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
