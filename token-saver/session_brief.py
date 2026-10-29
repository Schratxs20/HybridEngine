#!/usr/bin/env python3
"""One-page state brief for a scheduled routine, so each run can start in a FRESH session
instead of waking a long-lived one and reloading 300k-700k tokens of old conversation.

Reads the repo, not the chat history:
  posts/*.md, posts/banked/*.md   front matter: title, date, issue, excerpt
  BRIEF_NOTES.md (optional)       standing rules you've told the routine ("don't flag other sessions' commits")
Writes BRIEF.md (default) — the routine's prompt says "read BRIEF.md first; don't read posts/ unless needed".

  python3 session_brief.py /path/to/Made-from-effort [--recent 12] [--out BRIEF.md]
"""
import argparse, datetime as dt, glob, os, re, subprocess

def front(path):
    m = re.match(r"---\n(.*?)\n---", open(path, encoding="utf-8").read(), re.S)
    d = {}
    for line in (m.group(1).splitlines() if m else []):
        k, _, v = line.partition(":")
        d[k.strip()] = v.strip().strip('"\'')
    d["file"] = path
    return d

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("repo"); ap.add_argument("--recent", type=int, default=12)
    ap.add_argument("--out"); ap.add_argument("--today", default=dt.date.today().isoformat())
    a = ap.parse_args()
    pub = [front(p) for p in glob.glob(os.path.join(a.repo, "posts", "*.md"))]
    bank = [front(p) for p in glob.glob(os.path.join(a.repo, "posts", "banked", "*.md"))]
    pub.sort(key=lambda d: d.get("date", ""), reverse=True)
    issues = [int(d["issue"]) for d in pub + bank if str(d.get("issue", "")).isdigit()]
    today = dt.date.fromisoformat(a.today)
    monday = today - dt.timedelta(days=today.weekday())
    week = [d for d in pub if d.get("date", "") >= monday.isoformat()]
    head = subprocess.run(["git", "-C", a.repo, "log", "-1", "--format=%h %cs %s"], capture_output=True, text=True).stdout.strip()
    L = [f"# Routine brief — {a.today} ({today.strftime('%A')})", "",
         f"- Repo HEAD: {head or 'n/a'}",
         f"- Next issue number: **{max(issues) + 1 if issues else 1}**",
         f"- Published: {len(pub)} · Banked: {len(bank)}",
         f"- Today's slot filled: **{'YES — ' + next(d['title'] for d in pub if d.get('date') == a.today) if any(d.get('date') == a.today for d in pub) else 'no'}**",
         "", "## This week", *([f"- {d.get('date')} #{d.get('issue','?')} {d.get('title')}" for d in week] or ["- (nothing yet)"]),
         "", f"## Last {a.recent} titles (don't repeat these angles)",
         *[f"- {d.get('date')} #{d.get('issue','?')} {d.get('title')}" for d in pub[:a.recent]],
         "", "## Banked drafts", *([f"- #{d.get('issue','?')} {d.get('title')} — `{os.path.relpath(d['file'], a.repo)}`" for d in bank] or ["- (none)"])]
    notes = os.path.join(a.repo, "BRIEF_NOTES.md")
    if os.path.exists(notes): L += ["", "## Standing notes", open(notes).read().strip()]
    out = a.out or os.path.join(a.repo, "BRIEF.md")
    open(out, "w").write("\n".join(L) + "\n")
    print(f"{out}  ({len(' '.join(L).split())} words)")

if __name__ == "__main__": main()
