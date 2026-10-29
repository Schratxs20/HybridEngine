# token-saver

Local prep steps that shrink what Claude has to read. Both scripts are plain `python3`, plus
`ffmpeg` where needed, and run the same way on a Mac or in a cloud session. Copies live in the
Made-from-effort repo under `scripts/`, and the journal scheduled tasks call them.

Install: nothing is needed in the cloud (python3 and ffmpeg are already there). Cloud network can't
reach YouTube, so there `transcript_prep.py` reads the Apify transcript JSON that the routine already
fetches. On a Mac, for URLs and audio: `brew install yt-dlp whisper-cpp ffmpeg`.

| Script | Replaces | Output Claude reads |
|---|---|---|
| `session_brief.py <repo>` | waking a 300k–700k-token session so it can "remember" the journal state | `/tmp/BRIEF.md`, about 150–300 words |
| `transcript_prep.py <url\|media\|vtt\|json>` | reading a full podcast transcript, or long slices of it | `/tmp/transcript-prep/<slug>/summary.md`, one page (kept outside the repo). Full text goes to `transcript.tsv` for grep. Add `--sheet` to also get `contact.jpg`, a 4×3 frame grid (video only) |

## Before/after (estimates from the Oct 2026 session audit)

| # | Task | Before (per run) | After |
|---|---|---|---|
| 1 | Scheduled journal/podcast firing into a long-lived session | ~470–560k cache write, then ~500k re-read on every turn (≈7–12M tokens read per firing) | Fresh session: ~50k system/tools + `BRIEF.md` ~0.4k, so about 1M read per firing |
| 2 | Podcast/YouTube transcript for the Sunday post | ~15–30k raw transcript, plus a subagent reading all of it, plus ~2–4k per printed slice. All of it is carried for the rest of the session | `summary.md` ~0.6k + one targeted quote slice ~1k |

## Routine prompt for fresh-session firings (draft)

> Run `python3 token-saver/session_brief.py .` and read only `BRIEF.md`. If today's slot is filled,
> stop. For a podcast post, run `transcript_prep.py <episode url>` and read `summary.md`. Use `awk` on
> `transcript.tsv` only for the exact lines you quote. Don't open other posts unless the brief says
> you need to.
