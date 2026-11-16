#!/usr/bin/env python3
"""Build the unified MOCA static site.

Inputs (see README):
  MOCA_MERGED   folder holding the merged legacy web root (lowercase paths)
  MOCA_MERGED_JSON  merged.json describing every file and where it came from
  MOCA_MEDIA_JSON   media.json from the media pipeline (sizes, variants)
  MOCA_MEDIA_BASE   URL prefix for media files (default https://media.museumofcomputerart.org)
Output:
  site/   ready to publish (GitHub Pages)
  build/  reports used by the verification checks
"""
import html
import json
import os
import posixpath
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(__file__))
import legacy  # noqa: E402
import rebrand  # noqa: E402
import templates as T  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MERGED = os.environ.get("MOCA_MERGED", "/home/user/work/merged")
MERGED_JSON = os.environ.get("MOCA_MERGED_JSON", "/home/user/work/merged.json")
MEDIA_JSON = os.environ.get("MOCA_MEDIA_JSON", "/home/user/work/out/media.json")
MEDIA_BASE = os.environ.get("MOCA_MEDIA_BASE", "https://media.museumofcomputerart.org").rstrip("/")
SITE_URL = "https://museumofcomputerart.org"
OUT = os.path.join(ROOT, "site")
REPORT = os.path.join(ROOT, "build")

SERVER_SCRIPT = re.compile(
    r"(upload|admin|guestbook|configure_|setup_email|check_user|delete_|add_comments|amend_|sign\.asp|"
    r"logindatabase|send_mail|test_ms|test_my|test_mail|/test/|payform|submitthanks\.asp|_vti_|hostinger/|hostgator/)", re.I)
JUNK = re.compile(r"(^|/)(_vti_cnf|_vti_pvt|_notes|smologin\d*|index (ionos|hostgator|hostinger|files)|donnie2006test)(/|$)|(^|/)[^/]* copy( \d+)?\.[a-z]+$|(^|/)[^/]* \d\.(asp|htm|html)$", re.I)
DRAFT_EXT = re.compile(r"\.(htmx+|htmlx+|aspxx+|htmxxxx|htmm|assp|aspng)$")

with open(MERGED_JSON) as f:
    FILES = json.load(f)
MEDIA = {}
if os.path.exists(MEDIA_JSON):
    with open(MEDIA_JSON) as f:
        MEDIA = json.load(f)


def exists(p):
    return p in FILES


def read(p):
    if p not in FILES:
        return None
    with open(os.path.join(MERGED, p), "rb") as f:
        return f.read()


def media_url(path, variant=None):
    m = MEDIA.get(path) or {}
    target = path
    if variant and m.get("variants", {}).get(variant):
        target = m["variants"][variant]
    elif variant == "mp4" and m.get("mp4"):
        target = m["mp4"]
    elif variant == "poster" and m.get("poster"):
        target = m["poster"]
    return MEDIA_BASE + "/" + quote(target)


# ---------------------------------------------------------------- inventory
def find_autogalleries():
    ags = {}
    for p in FILES:
        if p.endswith("/index.asp") and "autogallery" in p:
            raw = read(p)
            if raw and b"DO NOT EDIT BELOW THIS LINE" in raw:
                ags[posixpath.dirname(p)] = p
    return ags


def classify_pages(ags):
    pages, skipped = [], []
    ag_index = set(ags.values())
    for p, v in FILES.items():
        low = p
        if p in ag_index:
            continue
        if JUNK.search(low):
            skipped.append((p, "editor/backup/test file, not a published page (FrontPage _vti_cnf, 'copy' files, login system, test folders)"))
            continue
        if DRAFT_EXT.search(low):
            skipped.append((p, "unpublished draft copy (file name ends in xx/x)"))
            continue
        if not low.endswith(legacy.PAGE_EXT):
            continue
        if posixpath.basename(low).startswith("."):
            skipped.append((p, "iCloud placeholder"))
            continue
        if low.endswith((".asp", ".aspx")) and SERVER_SCRIPT.search(low):
            skipped.append((p, "server-side script (uploads, admin, guestbook, mail); cannot run on a static host"))
            continue
        pages.append(p)
    return sorted(pages), skipped


SECTION_RULES = [
    (r"^donnie(\d{4})", lambda m: ("The Donnie " + m.group(1), "c2", "/donnie.html")),
    (r"^donnie", lambda m: ("The Donnie", "c2", "/donnie.html")),
    (r"^(ai[a-z]*|imagesoftheday\d*ai|imageofthedayindexai|aiexhibits|artforartssake)", lambda m: ("AI Art", "c5", "/ai.html")),
    (r"^autogallery(\d{4})?", lambda m: ("AutoGallery " + (m.group(1) or "classic"), "c4", "/archive.html")),
    (r"^adon/", lambda m: ("Don Archer", "c5", "/adon/abase.html")),
    (r"^newmoca/", lambda m: ("Galleries", "c1", "/collection.html")),
    (r"^open/", lambda m: ("Open Gallery", "c4", "/open/opengallery.htm")),
    (r"^guest/", lambda m: ("Guest Gallery", "c4", "/newmoca/guestgallery.htm")),
    (r"^editorial/", lambda m: ("Editorial", "c3", "/editorial/editorial.htm")),
    (r"^mocanet/", lambda m: ("MOCAnet", "c3", "/mocanet/mocalist.htm")),
    (r"^(digivid|newmedia)/", lambda m: ("Video & new media", "c2", "/newmoca/newmediamain.html")),
    (r"^(imagesoftheday|imageoftheday|imofday)", lambda m: ("Images of the Day", "c3", "/archive.html")),
    (r"^(da\d|blurb|catalog)", lambda m: ("Catalogs", "c3", "/catalogs.htm")),
    (r"^[^/]+\.(htm|html|asp)$", lambda m: ("Museum", "c1", "/")),
]


def section_for(p):
    for pat, fn in SECTION_RULES:
        m = re.match(pat, p)
        if m:
            return fn(m)
    top = p.split("/")[0]
    return ("Artist exhibit", "c1", "/artists.html")


LEGACY_TITLES = {"index.htm": "mocadigitalart.com front page (as of 2024)",
                 "index.asp": "Original MOCA front page (as of 2024)",
                 "index.html": "Original MOCA front page (2022)"}
GENERIC_TITLE = re.compile(r"^(moca[:\s-]*)?(the )?(museum of computer art|moca|mocadigitalart|moca\.virtual\.museum|untitled( document)?|new page \d*|index|"
                           r"don archer digital art|digital art|computer art|home|\d{1,3}|this artist|enter your search terms.*|click (here|image).*|this page has not been fully populated)$", re.I)


def pick_title(parsed, p):
    t = parsed["title"].strip()
    t = re.sub(r"^(MOCA|mocadigitalart)\s*[:|\-]\s*", "", t, flags=re.I).strip()
    if t and not GENERIC_TITLE.match(t) and len(t) < 120:
        return t
    for b in parsed["blocks"]:
        if b["t"] == "h" and 2 < len(b["text"]) < 100:
            return b["text"]
    for b in parsed["blocks"]:
        if b["t"] == "p" and b["text"] and not b["html"].count("<a "):
            lines = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", x))).strip() for x in re.split(r"<br>", b["html"])]
            lines = [x for x in lines if x and not GENERIC_TITLE.match(x)]
            if lines and all(len(x) < 70 for x in lines[:3]):
                t = " · ".join(lines[:3])
                if len(t) < 110:
                    return t
    for b in parsed["blocks"]:
        if b["t"] == "p" and 2 < len(b["text"]) < 90 and not GENERIC_TITLE.match(b["text"]) and "home" not in b["text"].lower():
            return b["text"]
    stem = posixpath.splitext(posixpath.basename(p))[0]
    return re.sub(r"[_\-]+", " ", stem).strip().title() or "MOCA"


# ---------------------------------------------------------------- page build
def build_page(p, ags):
    raw = read(p)
    text = legacy.decode(raw)
    text = legacy.resolve_includes(text, p, read)
    text = legacy.clean_asp(text)
    ctx = legacy.Ctx(p, exists, set(ags))
    ctx.dims = lambda v: (MEDIA[v]["w"], MEDIA[v]["h"]) if (MEDIA.get(v) or {}).get("w") and (MEDIA.get(v) or {}).get("h") else None
    parsed = legacy.parse(text, ctx)
    for im in ctx.images:
        if (MEDIA.get(im) or {}).get("error"):
            ctx.dropped.append(("undecodable-or-empty-source", im, MEDIA[im]["error"][:120]))
    title = pick_title(parsed, p)
    section = section_for(p)
    url = legacy.page_url(p)
    body, first_img, lead = T.render_blocks(parsed["blocks"], media_url, MEDIA)
    if lead and 3 < len(lead) < 90 and lead.lower() not in title.lower() and not GENERIC_TITLE.match(lead):
        title = lead if title.lower() in lead.lower() else (f"{lead} · {title}" if len(title) < 40 else lead)
    title = LEGACY_TITLES.get(p, title)
    title = re.sub(r"\s*[\u2014|-]+\s*MOCA: Museum of Computer Art\s*$", "", title).strip() or title
    if len(title) > 90:
        title = title[:87].rsplit(" ", 1)[0].rstrip(" ·,:;-") + "…"
    body = body.replace('alt=""', f'alt="{html.escape(title)}"')
    desc = parsed["desc"] or next((b["text"] for b in parsed["blocks"] if b["t"] == "p" and len(b["text"]) > 60), "")
    page_html = T.page(title=title, url=url, section=section, body=body, desc=desc,
                       og_image=media_url(first_img, "1600") if first_img else None, site_url=SITE_URL)
    write(url, page_html)
    texts = [b["text"] for b in parsed["blocks"] if b.get("text")]
    return {
        "path": p, "url": url, "title": title, "section": section[0], "first_img": first_img,
        "images": ctx.images, "links": [(k, v) for k, v, _ in ctx.links_out],
        "dropped": ctx.dropped, "text_chars": sum(len(t) for t in texts),
        "words": sorted(set(re.findall(r"[a-z0-9]{4,}", " ".join(texts).lower())))[:4000],
    }


def write(url, content):
    rel = url.split("#")[0].lstrip("/")
    if rel == "" or rel.endswith("/"):
        rel += "index.html"
    dest = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if dest.endswith((".htm", ".html")):
        content = rebrand.clean(content)  # no moca.virtual.museum name or addresses on the new site
    with open(dest, "w", encoding="utf-8") as f:
        f.write(content)


AG_VAR = re.compile(r'^\s*(\w+)\s*=\s*"((?:[^"]|"")*)"', re.M)
IMG_EXT = (".jpg", ".jpeg", ".gif", ".png", ".bmp", ".webp")


def build_autogallery(folder, index_path):
    text = legacy.decode(read(index_path))
    cfg = {k: v.replace('""', '"') for k, v in AG_VAR.findall(text.split("DO NOT EDIT BELOW")[0])}
    imgs = sorted([p for p in FILES if posixpath.dirname(p) == folder and p.endswith(IMG_EXT)
                   and not re.search(r"_thumbnail\.", p)], key=lambda x: posixpath.basename(x))
    # The ASP gallery listed files in folder order; keep original-case names for captions.
    items = []
    for i, p in enumerate(imgs, 1):
        stem = posixpath.splitext(posixpath.basename(FILES[p]["orig"]))[0]
        items.append({"n": i, "src": p, "caption": stem.replace("_", " ")})
    ctx = legacy.Ctx(index_path, exists, set())
    header = legacy.parse("<body>" + cfg.get("PageHeader", "") + "</body>", ctx)
    message = legacy.parse("<body>" + cfg.get("PageMessage", "") + "</body>", ctx)
    title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cfg.get("PageTitle", "")))).strip()
    if not title or GENERIC_TITLE.match(title) or len(title) < 3:
        hb = next((b["text"] for b in message["blocks"] + header["blocks"] if b.get("text") and not GENERIC_TITLE.match(b["text"].split(" · ")[0])
                   and not re.search(r"moca|autogallery|submit|home", b["text"], re.I)), "")
        title = (hb.split("  ")[0][:80] if hb else "") or folder.split("/")[-1].replace("autogallery_", "").replace("_", " ").title()
    section = section_for(folder + "/")
    url = "/" + folder + "/"
    body = T.render_autogallery(items, header["blocks"], message["blocks"], cfg, media_url, MEDIA)
    page_html = T.page(title=title, url=url, section=section, body=body,
                       desc=f"{title}: {len(items)} images in the MOCA AutoGallery.",
                       og_image=media_url(items[0]["src"], "1600") if items else None, site_url=SITE_URL,
                       scripts=["/assets/gallery.js"])
    write(url, page_html)
    return {"path": index_path, "url": url, "title": title, "section": section[0],
            "first_img": items[0]["src"] if items else None, "images": [i["src"] for i in items],
            "links": [], "dropped": [], "text_chars": 0, "words": [], "autogallery": True,
            "slideshow": cfg.get("TurnOnSlideshow", "").upper() == "YES", "timer": cfg.get("SlideShowTimer", "4")}


def _job(args):
    kind, p, ags = args
    try:
        if kind == "ag":
            return build_autogallery(p, ags[p])
        return build_page(p, ags)
    except Exception as e:  # never lose a page silently
        import traceback
        return {"path": p, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-800:]}


def main():
    t0 = time.time()
    if os.path.isdir(OUT):
        for name in os.listdir(OUT):
            if name in ("CNAME",):
                continue
            full = os.path.join(OUT, name)
            shutil.rmtree(full) if os.path.isdir(full) else os.remove(full)
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(REPORT, exist_ok=True)
    ags = find_autogalleries()
    pages, skipped = classify_pages(ags)
    only = os.environ.get("MOCA_ONLY")
    if only:
        pages = [p for p in pages if re.search(only, p)]
    T.write_assets(OUT, ROOT)  # before rendering, so every page gets the ?v= hashes
    jobs = [("ag", f, ags) for f in sorted(ags)] + [("page", p, ags) for p in pages]
    results = []
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        for r in ex.map(_job, jobs, chunksize=64):
            results.append(r)
    errors = [r for r in results if "error" in r]
    ok = [r for r in results if "error" not in r]
    import hubs
    extra = hubs.build_all(ok, FILES, MEDIA, media_url, write, SITE_URL)
    ok += extra
    T.write_assets(OUT, ROOT)
    T.write_meta(OUT, ok, SITE_URL, write)
    with open(os.path.join(REPORT, "pages.json"), "w") as f:
        json.dump(ok, f)
    with open(os.path.join(REPORT, "skipped.json"), "w") as f:
        json.dump({"skipped": skipped, "errors": errors}, f, indent=1)
    print(f"built {len(ok)} pages ({len(ags)} autogalleries), {len(errors)} errors, {len(skipped)} skipped in {time.time()-t0:.0f}s")
    for e in errors[:10]:
        print("ERR", e["path"], e["error"])


if __name__ == "__main__":
    main()
