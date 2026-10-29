#!/usr/bin/env python3
"""Turn a long podcast/video transcript into a one-page brief Claude reads instead.

Input (first match wins):
  - a .vtt/.srt/.txt/.json transcript, incl. an Apify get-dataset-items result saved to tool-results/
    (cloud sessions: this is the path to use, their network cannot reach YouTube directly)
  - a YouTube URL       -> yt-dlp auto-captions (no Whisper needed when captions exist)
  - an audio/video file -> whisper.cpp (`whisper-cli`) or openai-whisper (`whisper`)
Output in --out (default /tmp/transcript-prep/<slug>/, outside the repo on purpose):
  summary.md      one page: sections with timestamps, key lines, keywords
  transcript.tsv  full text, "seconds<TAB>line" — grep it, never Read it whole
  contact.jpg     optional, video only: one 4x3 frame grid (--sheet)
"""
import argparse, collections, json, math, os, re, shutil, subprocess, sys, tempfile

STOP = set("""a about after again all also am an and any are as at be because been before being but by can could did do
does doing don't down even every for from get got had has have he her here him his how i i'm if in into is it it's its
just know like little lot make me more most my no not now of off oh okay on one only or other our out over really right
said say so some something than that that's the their them then there these they thing things think this those to too um
uh up us very want was way we well were what when where which who why will with would yeah you your you're gonna kind
actually going mean people because""".split())

def ts(sec): sec = int(sec); return f"{sec//3600:d}:{sec//60%60:02d}:{sec%60:02d}" if sec >= 3600 else f"{sec//60:d}:{sec%60:02d}"

def parse_time(s):
    p = [float(x) for x in s.replace(",", ".").split(":")]
    return sum(v * 60 ** i for i, v in enumerate(reversed(p)))

def read_captions(path):
    """Return [(seconds, text)] from vtt/srt/txt/json."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    if path.endswith(".json"):
        d = json.loads(raw)
        item = (d.get("items") or [d])[0] if isinstance(d, dict) else d[0]
        rows = next((item[k] for k in ("timestamped", "transcript", "captions", "segments", "text", "raw") if item.get(k)), None)
        if isinstance(rows, list):
            out = []
            for r in rows:
                if isinstance(r, dict):
                    t = r.get("start", r.get("offset", r.get("time", 0)))
                    out.append((parse_time(str(t)) if ":" in str(t) else float(t or 0), r.get("text", "")))
                elif isinstance(r, (list, tuple)):
                    t = str(r[0]); out.append((parse_time(t) if ":" in t else float(t), str(r[1])))
            return out
        text = re.sub(r"<[^>]+>", " ", str(rows or ""))
        return [(0, s) for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    out, t, seen = [], 0.0, set()
    for line in raw.splitlines():
        m = re.match(r"\s*(\d[\d:.,]*)\s*-->", line)
        if m: t = parse_time(m.group(1)); continue
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line or line.isdigit() or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")): continue
        if line in seen: continue          # auto-captions repeat each line 2-3 times
        seen.add(line); out.append((t, line))
    return out

def fetch(src, work):
    if os.path.exists(src) and src.rsplit(".", 1)[-1].lower() in ("vtt", "srt", "txt", "json"):
        return src, None
    if re.match(r"https?://", src):
        if not shutil.which("yt-dlp"): sys.exit("yt-dlp not installed (brew install yt-dlp)")
        subprocess.run(["yt-dlp", "--skip-download", "--write-auto-subs", "--write-subs", "--sub-langs", "en.*",
                        "--sub-format", "vtt", "-o", f"{work}/%(id)s.%(ext)s", src], check=True, capture_output=True)
        subs = [f for f in os.listdir(work) if f.endswith(".vtt")]
        if subs: return os.path.join(work, subs[0]), None
        subprocess.run(["yt-dlp", "-x", "--audio-format", "wav", "-o", f"{work}/audio.%(ext)s", src], check=True, capture_output=True)
        src = os.path.join(work, "audio.wav")
    # local media -> whisper
    wav = os.path.join(work, "a16k.wav")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-ar", "16000", "-ac", "1", wav], check=True)
    if shutil.which("whisper-cli"):
        model = os.environ.get("WHISPER_MODEL", os.path.expanduser("~/.cache/whisper/ggml-base.en.bin"))
        subprocess.run(["whisper-cli", "-m", model, "-f", wav, "-ovtt", "-of", f"{work}/w"], check=True, capture_output=True)
    elif shutil.which("whisper"):
        subprocess.run(["whisper", wav, "--model", "base.en", "--output_format", "vtt", "--output_dir", work], check=True, capture_output=True)
        os.rename(os.path.join(work, "a16k.vtt"), os.path.join(work, "w.vtt"))
    else:
        sys.exit("no captions and no Whisper: brew install whisper-cpp (or pip install openai-whisper)")
    return os.path.join(work, "w.vtt"), src

def sentences(rows):
    """Merge caption fragments into (start_sec, sentence)."""
    out, buf, start = [], [], None
    for t, txt in rows:
        if start is None: start = t
        buf.append(txt)
        joined = " ".join(buf)
        if re.search(r"[.!?]$", txt) or len(joined) > 240:
            out.append((start, joined)); buf, start = [], None
    if buf: out.append((start, " ".join(buf)))
    return out

def words(s): return [w for w in re.findall(r"[a-z][a-z']+", s.lower()) if w not in STOP and len(w) > 2]

def summarize(sents, section_sec, per_section):
    sw = [set(words(s)) for _, s in sents]
    sdf = collections.Counter(w for ws in sw for w in ws)
    idf = {w: math.log(len(sents) / c) for w, c in sdf.items()}   # filler said in every other line scores ~0
    secs = collections.defaultdict(list)
    for (t, s), ws in zip(sents, sw): secs[int(t // section_sec)].append((t, s, ws))
    out = []
    for k in sorted(secs):
        v = secs[k]
        local = collections.Counter(w for *_, ws in v for w in ws)
        topic = [w for w, _ in sorted(local.items(), key=lambda x: -x[1] * idf[x[0]])[:4]]
        def score(r):
            t, s, ws = r
            if not 6 <= len(s.split()) <= 45: return 0
            return sum(idf[w] * (3 if w in topic else 1) for w in ws) / (len(s.split()) + 6)
        picked, used = [], set()
        for r in sorted(v, key=score, reverse=True):
            if r[1] in used: continue
            picked.append(r); used.add(r[1])
            if len(picked) == per_section: break
        out.append((v[0][0], topic, sorted((t, s) for t, s, _ in picked)))
    tot = collections.Counter(w for ws in sw for w in ws)
    kw = sorted(tot, key=lambda w: -tot[w] * idf[w])[:15]
    return out, kw

def contact_sheet(video, dest):
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                               capture_output=True, text=True).stdout or 0)
    if not dur: return
    fps = 12 / dur
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", video, "-vf", f"fps={fps},scale=320:-2,tile=4x3",
                    "-frames:v", "1", "-q:v", "4", dest], check=True)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source"); ap.add_argument("--title", default="")
    ap.add_argument("--out"); ap.add_argument("--section-min", type=float, default=0)
    ap.add_argument("--per-section", type=int, default=2); ap.add_argument("--sheet", action="store_true")
    a = ap.parse_args()
    work = tempfile.mkdtemp(prefix="tprep-")
    cap, media = fetch(a.source, work)
    rows = read_captions(cap)
    sents = sentences(rows)
    if sents and all(t == 0 for t, _ in sents):      # untimed text: estimate at ~150 spoken words/min
        n, est = 0, []
        for _, x in sents: est.append((n * 0.4, x)); n += len(x.split())
        sents, rows = est, est
    dur = rows[-1][0] if rows else 0
    section = a.section_min * 60 or max(120, dur / 10)        # ~10 sections keeps it to one page
    secs, kw = summarize(sents, section, a.per_section)
    slug = re.sub(r"[^a-z0-9]+", "-", (a.title or os.path.basename(a.source)).lower()).strip("-")[:50] or "transcript"
    out = a.out or os.path.join(tempfile.gettempdir(), "transcript-prep", slug); os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "transcript.tsv"), "w") as f:
        for t, s in sents: f.write(f"{int(t)}\t{s}\n")
    nwords = sum(len(s.split()) for _, s in sents)
    md = [f"# {a.title or slug}", "",
          f"Length {ts(dur)} · {nwords:,} words (~{int(nwords*1.33):,} tokens raw) · full text: `transcript.tsv` (grep it; columns: seconds, line)", "",
          "**Keywords:** " + ", ".join(kw), "", "## Sections"]
    for start, topic, best in secs:
        md.append(f"\n**{ts(start)}** — {', '.join(topic)}")
        md += [f"- [{ts(t)}] {s}" for t, s in best]
    md += ["", "_To quote exactly: `awk -F'\\t' '$1>=START && $1<=END' transcript.tsv | cut -f2`_"]
    open(os.path.join(out, "summary.md"), "w").write("\n".join(md) + "\n")
    if a.sheet and media and shutil.which("ffprobe"): contact_sheet(media, os.path.join(out, "contact.jpg"))
    print(f"{out}/summary.md  ({len(' '.join(md).split())} words, from {nwords} words)")

if __name__ == "__main__": main()
