#!/usr/bin/env python3
"""Bring the new pages of the Don Archer Collection's "website files archive" onto the site.

Don Archer kept his own copies of the old MOCA websites. Most of their pages are already on the
site (from the 2024 server backups); this adds the ones that are not, the same way build.py
brought the legacy pages over (legacy.parse + the site templates), and nothing a visitor could
not tell apart from a page the site already has:

  contest website        the Donnie 2001 contest site            -> /donnie2001/
  moca website           old moca.virtual.museum pages           -> their own addresses
  Misc/MOCA99, moca98    the 1998-99 museum pages               -> their own addresses
  Misc/ARCHING, ARCHDOR  Don Archer's Fractal Art (1990s)        -> /adon/
  Misc/NETSCAPE          Don's browser cache: only Don/MOCA pages -> /adon/
  donarcher.com website  Don's own site: interview, music,       -> /adon/
                         front page, the U-DRAW e-postcards

A page is left out when everything it shows is already on the site: all its pictures are on the
media server under some page, and its own words (not navigation) add at most NEW_WORDS words to
what the site already says. Copies of one page in two archive folders count once (the folders are
read in the order above). Server scripts (.asp forms, guestbooks, counters, the postcard app),
Access databases and form submissions are never published. E-mail addresses of private people are
removed; MOCA's own become hello@museumofcomputerart.org.

Pictures: a file the media server already has (inventory.tsv site_key, or a file of the same
path on the server) is shown from there; any other is shown from dac/<collection path, lower case>
and listed in tools/dac-media-webarchive.tsv for tools/dac_media.py to upload.

Run after build.py (build.py calls apply() itself when MOCA_DAC is set), or on its own on an
already built site/; running it again changes nothing:

    python3 tools/webarchive.py --dac "<scratch>/don-collection" [--site site]

--dac is the folder holding webarchive/ (the extracted "website files archive"), inventory.tsv
and website-archive-pages.tsv.
"""
import argparse
import csv
import hashlib
import html
import json
import os
import posixpath
import re
import sys
import time
from collections import Counter, defaultdict
from urllib.parse import quote, unquote

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build  # noqa: E402  (helpers only: pick_title, section_for, generic)
import dedupe  # noqa: E402
import legacy  # noqa: E402
import rebrand  # noqa: E402
import templates as T  # noqa: E402

E = html.escape
SITE_URL = "https://museumofcomputerart.org"
MEDIA_BASE = "https://media.museumofcomputerart.org"
COLL = "website files archive/"
MAP_TSV = os.path.join(HERE, "dac-media-webarchive.tsv")
R2_ORIGINALS = "/mnt/project-files/transfer/media-map-originals.tsv"
NEW_WORDS = 15
FROM = '<meta name="moca-from" content="website files archive">'  # on every page this writes
MARK = "webarchive"  # id prefix of everything this adds to the hubs (makes a second run a no-op)

# (archive folder, path on the site): earlier folders win when two hold the same page.
SOURCES = [
    ("moca website", ""),
    ("Misc/MOCA99", ""),
    ("Misc/moca98", ""),
    ("Misc/ARCHING", "adon/"),
    ("Misc/ARCHDOR", "adon/"),
    ("donarcher.com website", "adon/"),
    ("contest website", "donnie2001/"),
    ("Misc/NETSCAPE/CACHE", "adon/"),
]
# Pages saved under a name the site uses for something else.
RENAME = {("donarcher.com website", "index.asp"): "adon/donarcher2003.asp",  # -> /adon/donarcher2003.html
          ("Misc/ARCHING", "INDEX.ING"): "adon/fractalart.htm",  # Don's 1990s home page (Ingress, then Dorsai)
          ("Misc/ARCHDOR", "INDEX.DOR"): "adon/fractalart.htm",
          # a later Fractal Camera page that links each picture to its full-resolution version
          ("Misc/NETSCAPE/CACHE", "M0Q6OPH5.HTM"): "adon/frccam-fullres.htm"}
# Never published: server scripts and their data, editor files, counters, form replies.
NEVER = re.compile(r"(^|/)(_vti_[^/]*|_notes|cgi-bin|guestbook[^/]*|comments\d*|statcountex|postcard[a-z]?|configs)(/|$)|"
                   r"\.(mdb|inc|asa|log|orig|old|virt|aspp)$|(^|/)(mthanks|thanks|count|ingcount|linktest|redirect|_vti_inf)\.html?$|"
                   r"(^|/)(uploadscript\d*|prepass|exfindyourpath|findphyspath|findinfo|okindex)\.asp$", re.I)
PAGE_RE = re.compile(r"\.(html?|asp)$", re.I)
MEDIA_EXT = (".jpg", ".jpeg", ".gif", ".png", ".bmp", ".mid", ".midi", ".wav", ".mp3", ".mov", ".avi", ".mpg", ".mpeg", ".swf", ".mp4", ".pdf")
IMAGE_EXT = (".jpg", ".jpeg", ".gif", ".png", ".bmp")
VIDEO_EXT = (".mov", ".avi", ".mpg", ".mpeg", ".mp4", ".wmv", ".flv")
# MOCA's and Don's own addresses (any old domain) become the museum's address; others are removed.
OWN_MAIL = re.compile(r"^(?:[\w.+-]+@(?:www\.)?(?:museumofcomputerart\.(?:com|org)|moca\.virtual\.museum|mocadigitalart\.com|donarcher\.com)|donarchr@[\w.-]+)$", re.I)
MAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def own_mail(addr):
    return bool(OWN_MAIL.match(addr))


def scrub_mail(text):
    """Private people's e-mail addresses out (mailto links keep their words, unless the words are the
    address); MOCA's own addresses become hello@museumofcomputerart.org."""
    def link(m):
        addr = unquote(m.group(2)).split("?")[0].strip()
        if own_mail(addr):
            return m.group(0)
        inner = m.group(3)
        return "" if MAIL.fullmatch(re.sub(r"<[^>]+>|\s", "", html.unescape(inner))) else inner
    text = re.sub(r"<a\s[^>]*?href\s*=\s*([\"']?)mailto:([^\"'\s>]+)\1[^>]*>(.*?)</a>", link, text, flags=re.I | re.S)
    return MAIL.sub(lambda m: rebrand.EMAIL if own_mail(m.group(0)) else "", text)


# ------------------------------------------------------------------ inputs
def load_inventory(path):
    inv, by_suffix, by_name = {}, defaultdict(list), defaultdict(list)
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            inv[r["path"]] = r
            if r["class"] in ("image", "video", "audio"):
                parts = r["path"].lower().split("/")
                by_name[parts[-1]].append(r)
                if r["class"] == "image":
                    by_name["stem:" + posixpath.splitext(parts[-1])[0]].append(r)
                if len(parts) >= 2:
                    by_suffix["/".join(parts[-2:])].append(r)
    return inv, by_suffix, by_name


def site_state(out):
    """What the built site already has: every page's content signature, the media it shows (with the
    variants and size each was published at) and, for dedupe, every run of five words it says."""
    ident = dedupe.media_identity()
    variants, dims, stubs, sigs, ours = defaultdict(set), {}, {}, {}, set()
    host = re.escape(MEDIA_BASE) + "/"
    for d, ds, fs in os.walk(out):
        ds.sort()
        for f in sorted(fs):
            if not f.endswith((".htm", ".html")):
                continue
            full = os.path.join(d, f)
            url = "/" + os.path.relpath(full, out).replace(os.sep, "/")
            doc = open(full, encoding="utf-8").read()
            if FROM in doc:
                ours.add(url)  # written by an earlier run: what the site had before is what counts
                continue
            doc = OUR_CARD.sub("", doc)
            t = dedupe.stub_target(doc)
            if t:
                stubs[url] = t
                continue
            for u in re.findall(host + r'([^"\s,<>]+)', doc):
                k = unquote(html.unescape(u))
                m = dedupe.VARIANT.search(k)
                if m:
                    variants[k[:m.start()] + m.group(1)].add(m.group(2))
                else:
                    variants[k]
            for tag in re.findall(r"<img [^>]*>", doc):
                s = re.search(r'src="' + host + r'([^"]+)"', tag)
                w, h = re.search(r' width="(\d+)"', tag), re.search(r' height="(\d+)"', tag)
                if s and w and h:
                    k = unquote(html.unescape(s.group(1)))
                    m = dedupe.VARIANT.search(k)
                    k = k[:m.start()] + m.group(1) if m else k
                    dims.setdefault(k, (int(w.group(1)), int(h.group(1))))
            if not dedupe.GENERATED.match(url):
                sigs[url] = dedupe.signature(doc, ident)
    return {"ident": ident, "variants": variants, "dims": dims, "stubs": stubs, "sigs": sigs, "ours": ours}


# the hub cards an earlier run added (left out when reading what the site already shows)
OUR_CARD = re.compile(r'<a class="card" href="/(?:donnie2001/|winners/|adon/about-don\.html|rediscovered\.html)[^"]*">.*?</a>', re.S)


def shingles(words, n=5):
    return {hash(tuple(words[i:i + n])) for i in range(max(0, len(words) - n + 1))}


def new_word_count(words, known, n=5):
    """Words of `words` that no already known run of n words covers."""
    if len(words) < n:
        return len(words)
    covered = [False] * len(words)
    for i in range(len(words) - n + 1):
        if hash(tuple(words[i:i + n])) in known:
            for j in range(i, i + n):
                covered[j] = True
    return covered.count(False)


# ------------------------------------------------------------------ media
class Media:
    """Legacy path (lower case, as the old pages asked for it) -> the file on the media server."""

    def __init__(self, inv, by_suffix, by_name, state, r2_keys):
        self.inv, self.by_suffix, self.by_name = inv, by_suffix, by_name
        self.state, self.r2 = state, r2_keys
        self.media = {}      # legacy path -> {w, h, variants, ...} as templates.render_blocks expects
        self.key = {}        # legacy path -> media server key
        self.src = {}        # dac/ key -> (collection path, bytes)
        self.on_site = {}    # legacy path -> True when the same picture is already on the site

    def add(self, val, row):
        """Map a legacy path to a collection file (an inventory row)."""
        cpath = row["path"]
        w, h = int(row["width"] or 0) or None, int(row["height"] or 0) or None
        sk, mt = row.get("site_key") or "", row.get("match_type") or ""
        use_site = bool(sk) and (mt.startswith(("md5", "name+size")) or (
            mt.startswith("visual") and (self.state["dims"].get(sk, (0, 0))[0] >= 0.8 * (w or 10 ** 6))))
        if use_site:
            key = sk
            m = self.site_entry(sk, w, h)
        else:
            key = "dac/" + cpath.lower()
            self.src[key] = (cpath, int(row["bytes"] or 0))
            m = {"w": w, "h": h, "variants": {}}
            low = key.lower()
            if low.endswith(VIDEO_EXT):
                m.update(type="video", mp4=key + ".mp4", poster=key + ".poster.webp")
            elif w and low.endswith(IMAGE_EXT) and not (low.endswith(".gif") and w < 480):
                # a GIF of 480px or more is a still fractal; smaller ones are often animations: shown as they are
                m["variants"] = {v: f"{key}.w{v}.webp" for v in ("480", "800", "1600") if w >= int(v)}
            elif low.endswith(".gif"):
                m["animated"] = True
        self.key[val], self.media[val] = key, m
        self.on_site[val] = bool(sk)
        return True

    def site_entry(self, key, w=None, h=None):
        seen = self.state["variants"].get(key, set())
        sw, sh = self.state["dims"].get(key, (w, h))
        m = {"w": sw or w, "h": sh or h,
             "variants": {v: f"{key}.w{v}.webp" for v in ("480", "800", "1600") if f"w{v}.webp" in seen}}
        if "mp4" in seen:
            m.update(type="video", mp4=key + ".mp4")
            if "poster.webp" in seen:
                m["poster"] = key + ".poster.webp"
        if not m["variants"] and key.lower().endswith(".gif"):
            m["animated"] = True
        return m

    def find(self, val, archive_files):
        """archive_files: legacy path -> collection path for the archive folders this page can see."""
        if val in self.key:
            return True
        cp = archive_files.get(val)
        if cp and cp in self.inv and self.inv[cp]["class"] in ("image", "video", "audio", "junk", "other", "document"):
            if not val.endswith(MEDIA_EXT):
                return False
            return self.add(val, self.inv[cp])
        if val in self.r2:
            self.key[val], self.media[val], self.on_site[val] = val, self.site_entry(val), True
            return True
        if not val.endswith(MEDIA_EXT):
            return False
        # the same file kept elsewhere in the collection (the 1990s pages' pictures are in the year folders)
        parts = val.split("/")
        rows = self.by_suffix.get("/".join(parts[-2:]), []) if len(parts) >= 2 else self.by_name.get(parts[-1], [])
        unique = len(parts) < 2
        if not rows and val.endswith(IMAGE_EXT):
            # saved in another format (u-drawn/x.jpg on the page, x.GIF in the year folder)
            rows, unique = self.by_name.get("stem:" + posixpath.splitext(parts[-1])[0], []), True
        if not rows:
            return False
        on = [r for r in rows if r.get("site_key")]
        if on:
            return self.add(val, on[0])
        md5s = Counter(r["md5"] for r in rows)
        if unique and len(md5s) > 1 and len({(r["width"], r["height"]) for r in rows}) > 1:
            return False  # a bare file name that means different pictures in different folders
        best = md5s.most_common(1)[0][0]
        row = min((r for r in rows if r["md5"] == best), key=lambda r: (r["path"].startswith(COLL) is False, len(r["path"])))
        return self.add(val, row)

    def url(self, val, variant=None):
        m = self.media.get(val) or {}
        target = self.key.get(val, val)
        if variant and (m.get("variants") or {}).get(variant):
            target = m["variants"][variant]
        elif variant == "mp4" and m.get("mp4"):
            target = m["mp4"]
        elif variant == "poster" and m.get("poster"):
            target = m["poster"]
        return MEDIA_BASE + "/" + quote(target)


# ------------------------------------------------------------------ pages
def candidates(dac):
    """(source folder, path in it, legacy path on the site) of every page to consider, in priority order."""
    status = {}
    with open(os.path.join(dac, "website-archive-pages.tsv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            status[(r["archive_site"], r["path_in_archive"])] = r["status"]
    root = os.path.join(dac, "webarchive")
    out = []
    for src, prefix in SOURCES:
        base = os.path.join(root, src)
        files = []
        for d, _, fs in os.walk(base):
            for f in fs:
                files.append(os.path.relpath(os.path.join(d, f), base).replace(os.sep, "/"))
        for rel in sorted(files):
            site_name = src.split("/CACHE")[0]
            key = (site_name, rel if site_name != "Misc/NETSCAPE" else "CACHE/" + rel)
            st = status.get(key, "")
            if src == "Misc/NETSCAPE/CACHE":
                if "." in rel and not PAGE_RE.search(rel):
                    continue
                raw = open(os.path.join(base, rel), "rb").read(4000)
                if not re.search(rb"<title>[^<]*(don archer|museum of computer art|\bmoca\b)", raw, re.I):
                    continue  # another site's page in Don's browser cache
                legacy_path = RENAME.get((src, rel)) or prefix + "netscape-" + posixpath.splitext(rel.lower())[0] + ".htm"
            else:
                if (src, rel) not in RENAME:
                    if not PAGE_RE.search(rel) or NEVER.search(rel):
                        continue
                    if not (st == "new" or st.startswith("donarcher.com") or src == "contest website"):
                        continue
                legacy_path = RENAME.get((src, rel)) or prefix + rel.lower()
            if (build.JUNK.search(legacy_path) or build.DRAFT_EXT.search(legacy_path)
                    or (legacy_path.endswith(".asp") and build.SERVER_SCRIPT.search(legacy_path))):
                continue
            out.append((src, rel, legacy_path))
    return out


def archive_files(dac):
    """legacy path -> collection path, per site prefix (all archive folders that share a prefix see each other's files)."""
    root = os.path.join(dac, "webarchive")
    files = defaultdict(dict)
    for src, prefix in SOURCES:
        base = os.path.join(root, src)
        for d, ds, fs in os.walk(base):
            ds.sort()
            for f in sorted(fs):
                rel = os.path.relpath(os.path.join(d, f), base).replace(os.sep, "/")
                files[prefix].setdefault(prefix + rel.lower(), COLL + src + "/" + rel)
    return files


# Site-generated titles for pages whose own title names nothing (or is an e-mail address).
TITLES = {
    "adon/donarcher2003.asp": "Don Archer digital art: donarcher.com front page (2003)",
    "adon/intervie.htm": "Interview with Don Archer (2003)",
    "adon/fractalart.htm": "Don Archer's Fractal Art: home page",
    "adon/frccam-fullres.htm": "The Fractal Camera, with full-resolution pictures",
    "personal.htm": "MOCA's curator and director",
    "swf.htm": "Flash animations",
    "thedonnie.htm": "The Donnie Awards 2001",
    "donnie2001/winners.htm": "The Donnie 2001 award winners",
    "donnie2001/allentry.htm": "The Donnie 2001: exhibit of all entries",
    "donnie2001/donprizes.htm": "The Donnie 2001 certificate awards",
    "donnie2001/don1.htm": "The Donnie 2001: Don Archer's first choices",
    "winners/winners02.htm": "The Donnie 2002 winners",
}
SECTIONS = {"winners/": ("The Donnie 2002", "c2", "/donnie.html"), "thedonnie.htm": ("The Donnie 2001", "c2", "/donnie.html")}
WINNER = re.compile(r"<b>((?:best in show<p>\s*)?[^<]*prize)</b><br>\s*([^<]*?)\s*<p>\s*<center>\s*(.*?)<br>\s*<b>(.*?)</b>", re.I | re.S)


def winners02_title(text, title):
    """A Donnie 2002 winner's page: 'Title, by Artist (2nd prize, Enhanced photography)'."""
    m = WINNER.search(text)
    if not m:
        return title
    t = lambda x: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", x))).strip()
    prize = re.sub(r"(?i)^best in show (1st prize)$", r"Best in Show and \1", t(m.group(1)))
    return f"{t(m.group(3))}, by {t(m.group(4))} ({prize}, {t(m.group(2))})"


ENTRY = re.compile(r"<b>Artist</b><br>\s*(.*?)<p>", re.I | re.S)


def contest_title(text, title):
    """A Donnie 2001 entry page: 'Title, by Artist' (every page was titled 'MOCA: ... Contest 2001')."""
    m = ENTRY.search(text)
    t = re.search(r"<hr[^>]*><p>\s*(.*?)\s*<table", text, re.I | re.S)
    if not m:
        return title
    artist = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip()
    work = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", t.group(1)))).strip() if t else ""
    return f"{work}, by {artist}" if work and len(work) < 80 else f"Entry by {artist}"


def render(dac, src, rel, lp, files, media):
    raw = open(os.path.join(dac, "webarchive", src, rel), "rb").read()
    text = legacy.decode(raw)
    prefix = dict(SOURCES)[src]
    seen = files[prefix]

    def read(p):
        cp = seen.get(p)
        return open(os.path.join(dac, "webarchive", cp[len(COLL):]), "rb").read() if cp else None
    text = legacy.resolve_includes(text, lp, read)
    text = scrub_mail(legacy.clean_asp(text))
    site_dir = render.site  # the built site this run adds to (set by apply)

    def exists(p):
        if p in seen and PAGE_RE.search(p):
            return True
        if PAGE_RE.search(p):
            return os.path.exists(os.path.join(site_dir, legacy.page_url(p).lstrip("/")))
        return media.find(p, seen)
    ctx = legacy.Ctx(lp, exists, set())
    ctx.dims = lambda v: (media.media[v]["w"], media.media[v]["h"]) if (media.media.get(v) or {}).get("w") and media.media[v].get("h") else None
    parsed = legacy.parse(text, ctx)
    p = lp
    title = build.pick_title(parsed, p)
    if src == "contest website":
        title = contest_title(text, title)
    elif p.startswith("winners/"):
        title = winners02_title(text, title)
    section = SECTIONS.get(p) or next((v for k, v in SECTIONS.items() if k.endswith("/") and p.startswith(k)), None) or build.section_for(p)
    url = legacy.page_url(p)
    body, first_img, lead = T.render_blocks(parsed["blocks"], media.url, media.media)
    if src != "contest website":
        if lead and 3 < len(lead) < 90 and lead.lower() not in title.lower() and not build.generic(lead):
            title = lead if title.lower() in lead.lower() else (f"{lead} · {title}" if len(title) < 40 else lead)
        elif lead and 90 <= len(lead) < 160 and title == build.stem_title(p) and not build.generic(lead):
            title = lead
    if lp in TITLES:
        title = TITLES[lp]
    elif title == "Don Archer's Fractal Art" or MAIL.search(title):
        heads = [b["text"] for b in parsed["blocks"] if b["t"] == "h" and b["text"] != title and not build.generic(b["text"])
                 and not re.search(r"museum of computer art", b["text"], re.I)]
        title = (heads[0][:1].upper() + heads[0][1:] + (" · Don Archer's Fractal Art" if title == "Don Archer's Fractal Art" else "")) if heads else build.stem_title(p)
    title = re.sub(r"\s*[—|-]+\s*MOCA: Museum of Computer Art\s*$", "", title).strip() or title
    title = T.shorten_title(T.tidy_title(title), artwork='<div class="artwork">' in body)
    body = T.drop_title_echo(body, title)
    body = T.name_alts(body, title)
    desc = parsed["desc"] or next((b["text"] for b in parsed["blocks"] if b["t"] == "p" and len(b["text"]) > 60), "")
    return {"src": src, "rel": rel, "path": p, "url": url, "title": title, "section": section, "body": body,
            "desc": desc, "first_img": first_img, "images": list(ctx.images), "links": [(k, v) for k, v, _ in ctx.links_out],
            "missing": sorted({d[1] for d in ctx.dropped if d[0] in ("missing-image", "missing-media")})}


render.site = "site"


def compose(r, media):
    return T.page(title=r["title"], url=r["url"], section=r["section"], body=r["body"], desc=r["desc"],
                  og_image=media.url(r["first_img"], "1600") if r.get("first_img") else None, site_url=SITE_URL,
                  scripts=r.get("scripts", ()))


def sig_media(sig):
    """The page's own media, by their server keys (embeds of other sites left out)."""
    return {k for k in sig["media"] if not k.startswith("ext:")}


def stem(key):
    return posixpath.splitext(posixpath.basename(key.lower()))[0]


def twin_page(sig, ms, stem_pages, sigs):
    """A page the site has with (nearly) the same words and pictures of the same names, perhaps saved in
    another format or size (4moby.jpg in Don's browser cache, 4moby.gif on the site)."""
    stems = {stem(k) for k in ms}
    if not stems:
        return None
    own = NOTICE.sub(" ", " ".join(sig["own"])).split()
    for u in sorted(set().union(*(stem_pages.get(x, set()) for x in stems))):
        other = sigs.get(u)
        if not other or len(stems & {stem(k) for k in other["media"]}) < 0.8 * len(stems):
            continue
        theirs = NOTICE.sub(" ", " ".join(other["own"])).split()
        # everything the site's page says, plus at most a heading, a line and the old "click here" links
        extra = len(dedupe.extra_words(own, theirs))
        if (len(dedupe.extra_words(theirs, own)) <= 5 and extra <= 2 * NEW_WORDS
                and len(own) - extra >= max(10, len(own) / 2)):
            return u
    return None


# words the templates add (the note under an old MIDI file), not the page's own
NOTICE = re.compile(r"\bbackground music \w+ browsers no longer play this format directly\b")


FRONT_DRAFT = re.compile(r"^(index[a-z_]+|okindex)\.asp$", re.I)


def skip_reason(src, rel, lp):
    if src == "moca website" and FRONT_DRAFT.match(rel):
        return "a draft of the old front page (the site keeps the front page itself under /legacy/)"
    if re.search(r"(^|/)(flash_)?test[^/]*\.html?$|_test\.html?$", rel, re.I):
        return "a test page"
    return SKIP_PAGES.get((src, rel))


SKIP_PAGES = {("Misc/NETSCAPE/CACHE", x): "a short notice that the U-draw form was closed for a week in 1997"
              for x in ("M0Q6N4L7.HTM", "M0Q6N4NA.HTM")}


# ------------------------------------------------------------------ hubs made here
def postcards(dac, files, media):
    """The 36 U-DRAW e-postcards of donarcher.com as a static gallery (the ASP postcard app cannot run here)."""
    base = os.path.join(dac, "webarchive", "donarcher.com website", "postcardd", "images")
    items = []
    for i, f in enumerate(sorted(x for x in os.listdir(base) if re.fullmatch(r"ud\d+\.jpg", x, re.I)), 1):
        val = "adon/postcardd/images/" + f.lower()
        media.find(val, files["adon/"])
        n = int(re.search(r"\d+", f).group(0))
        items.append({"n": i, "src": val, "caption": f"U-DRAW e-postcard no. {n}"})
    title = "U-DRAW fractal e-postcards"
    intro = [{"t": "p", "html": ("On donarcher.com Don Archer let visitors pick one of these U-DRAW fractals and send it to a friend "
                                 "as a digital postcard. The postcard service ran on the old web server and is retired; "
                                 f"the {len(items)} postcard pictures are shown here."), "text": "intro"},
             {"t": "p", "html": '<a href="/adon/about-don.html">About Don Archer</a> · <a href="/adon/abase.html">Don Archer\'s galleries</a>', "text": ""}]
    body = T.render_autogallery(items, [], intro, {"SlideShowTimer": "4"}, media.url, media.media, title)
    return {"path": "adon/postcards.html", "url": "/adon/postcards.html", "title": title,
            "section": ("Don Archer", "c5", "/adon/abase.html"), "body": body,
            "desc": f"The {len(items)} U-DRAW fractal e-postcards Don Archer offered on donarcher.com.",
            "first_img": items[0]["src"] if items else None, "images": [i["src"] for i in items], "links": [],
            "scripts": ["/assets/gallery.js"], "made": True}


def good_pic(r, media):
    m = media.media.get(r.get("first_img")) or {}
    return bool(m.get("w")) and min(m.get("w") or 0, m.get("h") or 0) >= 200


def card(r, media, sub):
    img = r.get("first_img")
    if img and (media.media.get(img) or {}).get("w"):
        pic = T.img_tag(img, media.media, media.url, "", sizes="(max-width:640px) 50vw, 220px").replace("<img ", '<img class="cimg" ', 1)
    else:
        pic = f'<span class="ph" aria-hidden="true">{E(r["title"][:1])}</span>'
    return f'<a class="card" href="{E(r["url"])}">{pic}<div><h3>{E(r["title"])}</h3><p>{E(sub)}</p></div></a>'


def link_list(rs):
    return "".join(f'<a href="{E(r["url"])}">{E(r["title"])}<span>{E(posixpath.basename(r["path"]))}</span></a>' for r in rs)


GROUPS = [  # rediscovered.html: (heading, test on the site path)
    ("Guest Gallery", lambda p: p.startswith("guest/")),
    ("Artist exhibits", lambda p: "/" in p and not p.startswith(("guest/", "adon/", "donnie2001/"))),
    ("Museum pages from 1998 to 2003", lambda p: "/" not in p),
]


def make_hubs(pages, media):
    """/adon/about-don.html (Don Archer and his own website) and /rediscovered.html (everything else
    found in the archive), as site pages like the others."""
    by = {r["path"]: r for r in pages}
    don = [r for r in pages if r["path"].startswith("adon/") and not r.get("made")]
    first = lambda paths: next((by[p] for p in paths if p in by), None)
    feature = [x for x in (first(["adon/intervie.htm"]), first(["adon/donarcher2003.asp"]), first(["adon/postcards.html"])) if x]
    body = ('<div class="b prose"><p>Don Archer founded the Museum of Computer Art and made fractal and computer art from 1993 on. '
            'These pages come from his own copies of his websites: an interview, his <a href="/adon/music.htm">fractal music</a>, the front page of donarcher.com and the U-DRAW fractals '
            'visitors could send as e-postcards. His galleries are in <a href="/adon/abase.html">Don Archer\'s collection</a>.</p></div>'
            f'<div class="cards">{"".join(card(r, media, "Don Archer") for r in feature)}</div>'
            '<h2 class="sec">More pages from Don\'s archive</h2>'
            f'<div class="list">{link_list(sorted((r for r in don if r not in feature), key=lambda r: r["path"]))}</div>')
    about = {"path": "adon/about-don.html", "url": "/adon/about-don.html", "title": "About Don Archer",
             "section": ("Don Archer", "c5", "/adon/abase.html"), "body": body, "made": True,
             "desc": "Don Archer, founder of the Museum of Computer Art: an interview, his fractal music, donarcher.com and his U-DRAW e-postcards.",
             "first_img": next((r["first_img"] for r in feature if good_pic(r, media)), None), "images": [], "links": []}
    rest = [r for r in pages if not r["path"].startswith(("adon/", "donnie2001/", "winners/")) and not r.get("made")]
    secs = []
    for name, test in GROUPS:
        rs = sorted((r for r in rest if test(r["path"])), key=lambda r: r["path"])
        if rs:
            secs.append(f'<div class="list"><h2>{E(name)}</h2>{link_list(rs)}</div>')
    n2001 = sum(1 for r in pages if r["path"].startswith("donnie2001/"))
    body = ('<div class="b prose"><p>Pages of the old MOCA websites that were not in the server backups the site was built from. '
            'They come from Don Archer\'s own copies of the websites, kept in his archive. '
            f'The Donnie 2001 contest site ({n2001} pages) and the Donnie 2002 winners are with <a href="/donnie.html#y2001">the other Donnie years</a>, '
            'and Don\'s own pages are under <a href="/adon/about-don.html">About Don Archer</a>.</p></div>'
            f'<div class="cols">{"".join(secs)}</div>')
    redis = {"path": "rediscovered.html", "url": "/rediscovered.html", "title": "Rediscovered pages",
             "section": ("Archive", "c3", "/archive.html"), "body": body, "made": True,
             "desc": "Pages of the old MOCA websites found in Don Archer's own archive: Guest Gallery artists, exhibits and museum pages from 1998 to 2003.",
             "first_img": next((r["first_img"] for r in sorted(rest, key=lambda r: r["path"]) if good_pic(r, media)), None), "images": [], "links": []}
    return [about, redis]


# ------------------------------------------------------------------ links between the new pages
def site_file(out, url):
    rel = unquote(url.split("#")[0].split("?")[0]).lstrip("/")
    if rel == "" or rel.endswith("/"):
        rel += "index.html"
    return os.path.join(out, rel)


def fix_links(body, out, new_urls, dup_to):
    """Links to archive pages that were left out (copies) go to the page they copy; links to pages
    neither the site nor the archive has become plain text, like build.py's dead links."""
    def sub(m):
        href = html.unescape(m.group(1))
        path = href.split("#")[0]
        if not path.startswith("/") or path.startswith("//"):
            return m.group(0)
        if path in new_urls or os.path.exists(site_file(out, path)) or path == "/":
            return m.group(0)
        if path in dup_to:
            return m.group(0).replace(f'href="{m.group(1)}"', f'href="{E(dup_to[path])}"', 1)
        return f'<span class="dead" title="This link pointed to a page that was not in the backups">{m.group(3)}</span>'
    return re.sub(r'<a href="([^"]*)"([^>]*)>(.*?)</a>', sub, body, flags=re.S)


# ------------------------------------------------------------------ apply to the built site
def write_page(out, url, doc):
    dest = site_file(out, url)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(rebrand.clean(doc.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n' + FROM, 1)))


def patch(path, fn):
    if not os.path.exists(path):
        return False
    doc = open(path, encoding="utf-8").read()
    new = fn(doc)
    if new != doc:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
        return True
    return False


def patch_hubs(out, pages, media):
    """Additions to the generated hubs, each as its own line before </main> (so they merge easily)."""
    dn = sorted((r for r in pages if r["path"].startswith("donnie2001/")), key=lambda r: r["path"])
    by = {r["path"]: r for r in pages}

    def year(prefix, main_path, index_path=None):
        """(card, list) for one Donnie year from the archive, like hubs.py makes them."""
        rs = sorted((r for r in pages if r["path"].startswith(prefix)), key=lambda r: r["path"])
        main = by.get(main_path)
        if not main:
            return "", ""
        linked = {v.split("#")[0] for k, v in main["links"] if k == "page"}
        pic = next((r for r in rs if r["url"] in linked and good_pic(r, media)), main)
        y = re.search(r"\d{4}", main["section"][0]).group(0)
        c = card({**main, "title": f"The Donnie {y}", "first_img": pic.get("first_img")}, media, f"{len(rs)} pages")
        entries = {v.split("#")[0] for k, v in by[index_path]["links"] if k == "page"} if index_path in by else set()
        links = link_list([r for r in rs if r["url"] not in entries])
        if index_path in by:
            links += f'<a href="{E(by[index_path]["url"])}">Exhibit index<span>all entries</span></a>'
        return c, f'<div class="list" id="y{y}">\n<h2>{y}</h2>{links}</div>'

    def donnie(doc):
        if 'id="y2001"' in doc:
            return doc
        cards, lists = zip(year("donnie2001/", "donnie2001/winners.htm", "donnie2001/allentry.htm"), year("winners/", "winners/winners02.htm"))
        cards = "".join(c for c in (cards[1], cards[0]) if c)
        lists = "".join(x for x in (lists[1], lists[0]) if x)
        # the new cards close the row of year cards, the new lists the "Every Donnie page" columns
        doc = doc.replace('</div><h2 class="sec">Every Donnie page</h2>', "\n" + cards + '\n</div><h2 class="sec">Every Donnie page</h2>', 1)
        doc = doc.replace("</div>\n</main>", "\n" + lists + "\n</div>\n</main>", 1)
        return re.sub(r"(Every surviving exhibit, winners page and catalog from )\d{4}( to )", r"\g<1>2001\2", doc)

    def home(doc):
        if "winners list, 2001 to" in doc:
            return doc
        doc = re.sub(r'(<a href="/donnie.html">\+)(\d+)(</a>)', lambda m: f"{m.group(1)}{int(m.group(2)) + 2}{m.group(3)}", doc, count=1)
        return re.sub(r"(Every exhibit and winners list, )\d{4}( to )", r"\g<1>2001\2", doc)

    def archive(doc):
        if f'id="{MARK}-archive"' in doc:
            return doc
        cs = [by[p] for p in ("adon/about-don.html", "rediscovered.html") if p in by]
        subs = {"adon/about-don.html": "Don Archer", "rediscovered.html": "Archive"}
        add = (f'<h2 class="sec" id="{MARK}-archive">From Don Archer\'s own archive</h2>'
               f'<div class="cards">{"".join(card(r, media, subs[r["path"]]) for r in cs)}</div>')
        return doc.replace("\n</main>", "\n" + add + "\n</main>", 1)
    changed = []
    if dn and patch(os.path.join(out, "donnie.html"), donnie):
        changed.append("/donnie.html")
    if dn and patch(os.path.join(out, "index.html"), home):
        changed.append("/index.html")
    if patch(os.path.join(out, "archive.html"), archive):
        changed.append("/archive.html")
    return changed


def patch_meta(out, pages):
    """search.json, the sitemap and build/lastmod.json, adding only what is not there yet."""
    sp = os.path.join(out, "search.json")
    idx = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else []
    have = {x[1] for x in idx}
    for r in pages:
        if r["url"] not in have:
            idx.append([rebrand.clean(r["title"]), r["url"], r["section"][0]])
    with open(sp, "w") as f:
        json.dump(idx, f, separators=(",", ":"))
    state_path = os.path.join(os.path.dirname(os.path.abspath(out)), "build", "lastmod.json")
    try:
        state = json.load(open(state_path))
    except (OSError, ValueError):
        state = {}
    today = time.strftime("%Y-%m-%d")
    maps = sorted((n for n in os.listdir(out) if re.fullmatch(r"sitemap-\d+\.xml", n)), key=lambda n: int(re.search(r"\d+", n).group(0)))
    if not maps:
        return
    allxml = "".join(open(os.path.join(out, n), encoding="utf-8").read() for n in maps)
    last = os.path.join(out, maps[-1])
    xml = open(last, encoding="utf-8").read()
    add = []
    for r in pages:
        doc = open(site_file(out, r["url"]), encoding="utf-8").read()
        hd = doc.split("</head>", 1)[0]
        m = re.search(r'<link rel="canonical" href="([^"]*)">', hd)
        if not m or 'name="robots" content="noindex' in hd:
            continue
        loc = html.unescape(m.group(1))
        t = re.search(r"<title>(.*?)</title>", hd, re.S)
        h = hashlib.md5(((t.group(1) if t else "") + T._main(doc)).encode("utf-8")).hexdigest()[:12]
        old = state.get(loc)
        state[loc] = [h, old[1] if old and old[0] == h else today]
        if f"<loc>{E(loc)}</loc>" not in allxml:
            add.append(f"<url><loc>{E(loc)}</loc><lastmod>{state[loc][1]}</lastmod></url>\n")
    if add:
        xml = xml.replace("</urlset>", "".join(add) + "</urlset>", 1)
        with open(last, "w") as f:
            f.write(xml)
        idxp = os.path.join(out, "sitemap.xml")
        patch(idxp, lambda d: re.sub(rf"(<loc>[^<]*/{re.escape(maps[-1])}</loc><lastmod>)[^<]*", rf"\g<1>{today}", d))
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w") as f:
        json.dump(state, f, indent=0, sort_keys=True)


def asset_versions(out):
    """New pages link the same ?v= asset versions as the pages already built."""
    if T.ASSET_VER:
        return
    try:
        doc = open(os.path.join(out, "index.html"), encoding="utf-8").read()
    except OSError:
        return
    for name, v in re.findall(r'(/assets/(?:site\.css|site\.js|gallery\.js))\?v=([0-9a-f]+)', doc):
        T.ASSET_VER[name] = v
    for d, _, fs in os.walk(out):
        for f in fs:
            if "/assets/gallery.js" in T.ASSET_VER:
                return
            if f.endswith((".htm", ".html")):
                m = re.search(r'/assets/gallery\.js\?v=([0-9a-f]+)', open(os.path.join(d, f), encoding="utf-8").read())
                if m:
                    T.ASSET_VER["/assets/gallery.js"] = m.group(1)


def apply(out, dac, r2_list=R2_ORIGINALS, map_tsv=MAP_TSV, report=None):
    asset_versions(out)
    render.site = out
    inv, by_suffix, by_name = load_inventory(os.path.join(dac, "inventory.tsv"))
    state = site_state(out)
    r2 = set(state["variants"])
    if r2_list and os.path.exists(r2_list):
        with open(r2_list, encoding="utf-8") as f:
            r2 |= {line.split("\t", 1)[0] for line in f if "\t" in line}
    r2 |= set(build.RECOVERED["files"])
    media = Media(inv, by_suffix, by_name, state, r2)
    files = archive_files(dac)
    ident = state["ident"]
    # pages an earlier run wrote: judged again as if they were not there yet
    ours = state["ours"]
    known = set()
    site_media = set()
    media_pages = defaultdict(list)
    for u, s in state["sigs"].items():
        if u in ours:
            continue
        known |= shingles(s["own"])
        site_media |= s["media"]
        for k in s["media"]:
            media_pages[k].append(u)
    stem_pages = defaultdict(set)
    for u, sg in state["sigs"].items():
        if u not in ours:
            for k in sg["media"]:
                stem_pages[stem(k)].add(u)
    sigs = {u: sg for u, sg in state["sigs"].items() if u not in ours}
    accepted, skipped, dup_to = [], [], {}
    seen_urls = set()
    for src, rel, lp in candidates(dac):
        url = legacy.page_url(lp)
        why = skip_reason(src, rel, lp)
        if why:
            skipped.append((src, rel, why))
            continue
        if url in seen_urls:
            skipped.append((src, rel, "same address as a page already taken from another archive folder"))
            continue
        if url not in ours and os.path.exists(site_file(out, url)):
            skipped.append((src, rel, "the site already has a page at this address"))
            continue
        try:
            r = render(dac, src, rel, lp, files, media)
        except Exception as e:  # never lose a page silently
            skipped.append((src, rel, f"error {type(e).__name__}: {e}"))
            continue
        doc = compose(r, media)
        sig = dedupe.signature(doc, ident)
        ms = sig_media(sig)
        new_media = {k for k in ms if k not in site_media}
        nw = new_word_count(sig["own"], known)
        # the page a copy stands for: the one showing its rarest picture, then the most of its pictures
        rare = sorted((k for k in ms if media_pages.get(k)), key=lambda k: (len(media_pages[k]), k))
        shared = Counter(u for k in ms for u in media_pages.get(k, []))
        best = [(min(media_pages[rare[0]], key=lambda u: (-shared[u], len(u), u)), 1)] if rare else []
        twin = twin_page(sig, ms, stem_pages, sigs)
        if not new_media and nw <= NEW_WORDS:
            why = f"already on the site ({'pictures and ' if ms else ''}{nw} new words)"
        elif twin:
            best, why = [(twin, 0)], "the same page as one the site has (same words, same pictures in another file format)"
        elif r["missing"] and not new_media and nw < 40:
            why = "its pictures are not in the archive or on the site, and it has little text of its own"
        else:
            why = None
        if why:
            if best and not why.startswith("its pictures"):
                dup_to[url] = best[0][0]
            skipped.append((src, rel, why + (f": {best[0][0]}" if best else "")))
            continue
        seen_urls.add(url)
        r["sig_new"] = (len(new_media), nw)
        accepted.append(r)
        known |= shingles(sig["own"])
        site_media |= ms
        sigs[url] = sig
        for k in ms:
            media_pages[k].append(url)
            stem_pages[stem(k)].add(url)
    pc = postcards(dac, files, media)
    pages = accepted + [pc]
    pages += make_hubs(pages, media)
    new_urls = {r["url"] for r in pages}
    for r in pages:
        r["body"] = fix_links(r["body"], out, new_urls, dup_to)
        write_page(out, r["url"], compose(r, media))
    hubs = patch_hubs(out, pages, media)
    patch_meta(out, pages)
    # the upload map: every dac/ original a published page shows
    used = set()
    for r in pages:
        doc = open(site_file(out, r["url"]), encoding="utf-8").read()
        for u in re.findall(re.escape(MEDIA_BASE) + r'/(dac/[^"\s,<>]+)', doc):
            k = unquote(html.unescape(u))
            m = dedupe.VARIANT.search(k)
            used.add(k[:m.start()] + m.group(1) if m else k)
    rows = sorted((k, *media.src[k]) for k in used if k in media.src)
    with open(map_tsv, "w", encoding="utf-8") as f:
        for k, s, b in rows:
            f.write(f"{k}\t{s}\t{b}\n")
    if report:
        with open(report, "w", encoding="utf-8") as f:
            json.dump({"published": [[r["url"], r["title"], (r.get("sig_new") or ("made",)), r.get("missing", [])] for r in pages],
                       "skipped": skipped, "hubs": hubs, "media_rows": len(rows), "media_bytes": sum(b for _, _, b in rows)}, f, indent=1)
    return pages, skipped, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dac", required=True, help="folder with webarchive/, inventory.tsv and website-archive-pages.tsv")
    ap.add_argument("--site", default=os.path.join(os.path.dirname(HERE), "site"))
    ap.add_argument("--r2", default=R2_ORIGINALS, help="media-map-originals.tsv (keys already on the media server)")
    ap.add_argument("--report", help="write a JSON report of what was published and left out")
    a = ap.parse_args()
    pages, skipped, rows = apply(a.site, a.dac, a.r2, report=a.report)
    print(f"{len(pages)} pages written, {len(skipped)} left out, {len(rows)} media rows ({sum(r[2] for r in rows):,} bytes)")


if __name__ == "__main__":
    main()
