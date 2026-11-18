#!/usr/bin/env python3
"""The Don Archer Studio Archive: /studio/, one gallery per year of Don Archer's studio folders
(1993-2015) plus his 3.5-inch disks, and a music and video page.

The pictures come from the Don Archer Collection (Don's own folders, 15 GB, kept off this
machine), not from the old websites. Only works the site did not show already are included.
Their media lives on R2 under dac/ (see dac_media.py, which makes the web versions and uploads
them from tools/dac-media-studio.tsv).

tools/studio_data.tsv is the committed input: one row per original, with the section (year)
and series it is shown under and a caption. It is made from the collection survey with

  python3 tools/studio.py prepare new-art.tsv new-other.tsv

which also writes tools/dac-media-studio.tsv (the upload map). The site build (hubs.py) calls
build() to write the pages; they need nothing else.

Privacy: U-DRAW fractals (and a few similar sets) were named after the people they were made
for. Captions, alt text, titles and search entries never use file names, only the series name
and a running image number; the only captions taken from Don's old pages are series titles such as
"Tongfire Series No. 10 (of 20)" and fractal numbers.
"""
import csv
import html
import os
import re
import sys
from collections import Counter, OrderedDict, defaultdict
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import templates as T  # noqa: E402
from dac_media import variant_widths  # noqa: E402

E = html.escape
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "studio_data.tsv")
MAP = os.path.join(HERE, "dac-media-studio.tsv")
MEDIA_BASE = os.environ.get("MOCA_MEDIA_BASE", "https://media.museumofcomputerart.org").rstrip("/")
PER_PAGE = 120
NAME = "Don Archer Studio Archive"
SECTION = (NAME, "c5", "/studio/")
COLS = ["section", "group", "label", "kind", "source", "width", "height", "bytes", "caption"]
SECTION_TEXT = {"disks": "3.5-inch disks, 1994", "backups": "studio backups"}
SECTION_SLUG = {"disks": "floppy-disks", "backups": "backups"}


def key_of(source):
    """R2 key of an original: dac/ + its path in the collection, lowercased."""
    return "dac/" + source.lower()


# ------------------------------------------------------------------ prepare (from the survey)
SKIP_DIR = [  # (path pattern, reason), checked in order
    (r"(^|/)website files archive/", "old website files: published from the website archive, not here"),
    (r"eudora|(^|/)netterm/", "e-mail and terminal program files (private)"),
    (r"^1995/(pm5|qpeg|chess)/", "software tutorial, sample and game images, not Don Archer's art"),
    (r"^1995/(moca|moca2)/|^1995/ims/cat\.gif$", "other artists' work from MOCA's 1995 exhibits"),
    (r"/disk 5/(sylvie|moca98|moca98a)/", "other artists' work from MOCA's 1998 web exhibits (Sylvie Gallet, Jaxun and others)"),
    (r"^1998/fractint 2/carr/", "renders of another fractal artist's (Bob Carr's) parameter files; authorship unclear"),
    (r"^2001/prizeimag/|^2009/donnie09/", "Donnie contest entries and award certificates (other artists)"),
    (r"^2004/da/", "MOCA logos and banners"),
]
NO_WEB = (".cdr", ".wmf", ".eps", ".lbm", ".rle", ".pce")
DROP_SEG = re.compile(r"^(1998 zip disk 1|v2|3\.5 inch floppies|gifs?|jpgs?|u-(gif|jpg)\d+)$")
UDRAW = re.compile(r"^(?:u-?dra?w|ud)(\d+)[a-z]?(?: v?\d+)?$")
# Series shown under a name of Don's; folders not named here and not U-DRAW are shown as
# "Untitled set A, B, ..." (some folders are named after the person a picture was made for).
LABELS = {
    "": "Unfiled works", "fract": "Fractals", "fract/darman": "Darman fractals", "fract/julia": "Julia sets",
    "fract/lyap": "Lyapunov fractals", "fract/sjmand": "SJ Mandelbrot fractals", "hp": "Exhibits from the 1995 home page",
    "hp1": "Fractal Camera and Fractal Zoo", "ims": "Fractals", "objscan": "Object scans", "objscan 2": "Object scans",
    "portrait": "Portraits", "bijou": "Bijou", "discon": "Discon", "misc": "Miscellaneous", "mutant": "Mutants",
    "pseudo": "Pseudo", "tante": "Tante", "archdon": "Archdon", "exper": "Experiments", "jul97": "July 1997",
    "misc00": "Miscellaneous", "misc01": "Miscellaneous", "fractint 2": "Fractint renders", "fractint 2/par": "Fractint renders",
    "bestdisk": "Miscellaneous", "bestgall": "Miscellaneous", "fault": "Faultline fractals", "new": "Miscellaneous",
    "flag": "Flags", "valley1": "Valley", "valley2": "Valley", "valley00": "Valley", "mhhcover": "Cover designs",
    "jan01": "January 2001", "feb01": "February 2001", "mar01": "March 2001", "apr01": "April 2001", "may01": "May 2001",
    "jpgvalhold": "Valley, held files", "jpgval01hold": "Valley, held files", "photoart": "Photo art",
    "144_nov03": "Set 144, November 2003", "145_dec03": "Set 145, December 2003", "146_jan04": "Set 146, January 2004",
    "147_feb04": "Set 147, February 2004", "148_mar04": "Set 148, March 2004", "atexture": "Textures",
    "beastie": "Beastie Series", "psd/tongfire": "Tongfire Series", "tongfire": "Tongfire Series", "renee": "Renee Series",
    "stout": "Stout Series", "trichon": "Trichon", "trichon 2": "Trichon", "136jpg": "Set 136", "137jpg": "Set 137",
    "jan05psd": "January 2005 files", "feb05psd": "February 2005 files", "mar05psd": "March 2005 files",
    "may05psd": "May 2005 files",
}
TOP_LABELS = {"1994": "3D Mandelbrot fractals", "2003": "Set 138"}  # pictures loose in a year folder
LABELS.update({"top " + k: v for k, v in TOP_LABELS.items()})


def real_caption(cap, source):
    """A caption from Don's old pages, only when it is clearly this picture's own: a series title,
    or a fractal number that is also in the file name. Never names of people."""
    if not cap.startswith("htm: "):
        return ""
    t = cap[5:]
    nums = re.findall(r"\d+", os.path.basename(source))
    m = re.match(r"([A-Z][a-z]+ Series No\. (\d+) \(of \d+\))", t)
    if m and m.group(2).lstrip("0") in [n.lstrip("0") for n in nums]:
        return m.group(1)
    m = re.match(r"Mutant #(\d+)(?= Mutant| Click|\s*<|\s*$)", t)
    if m and m.group(1) in nums:
        return f"Mutant #{m.group(1)}"
    m = re.match(r"#(\d{3,4})((?: [A-Za-z&][A-Za-z&'.]*)*?)(?= #\d| Click| This|\s*<|\s*$)", t)
    if m and m.group(1).lstrip("0") in [n.lstrip("0") for n in nums]:
        return f"#{m.group(1)}{m.group(2)}"
    return ""


def classify(path):
    """(section, series folder) for a collection path, or (None, reason)."""
    low = path.lower()
    for pat, why in SKIP_DIR:
        if re.search(pat, low):
            return None, why
    parts = low.split("/")
    top, segs = parts[0], [s for s in parts[1:-1] if not DROP_SEG.match(s)]
    if top == "3.5 inch disks 1994":
        m = re.match(r"disk (\d+)", segs[0]) if segs else None
        return "disks", (f"disk {int(m.group(1)):02d}" if m else "")
    if top == "don pics":
        return "don pics", "/".join(segs[1:])  # drop the dated backup folder
    if not segs and top in TOP_LABELS:
        return top, "top " + top
    return top, "/".join(segs)


def series(folder):
    """(group key, sort key, label, personal) for a series folder."""
    last = folder.split("/")[-1] if folder else ""
    if folder.startswith("disk "):
        n = int(folder[5:])
        return folder, (0, n, ""), f"Disk {n}", False
    m = UDRAW.match(last)
    if m:
        n = int(m.group(1))
        return f"udraw {n}", (2, n, ""), f"U-DRAW {n}", True
    if last in ("u-drawsr",):
        return "udraw sr", (2, -1, ""), "U-DRAW, selections", True
    if last in ("u-gif", "u-jpg"):
        return "udraw early", (2, -2, ""), "U-DRAW, first sets", True
    if last in ("bestgall", "bestdisk"):
        return "udraw best", (2, -4, ""), "U-DRAW, best of the year", True
    if folder.startswith("gifhold/"):
        return f"gifhold {last}", (2, -3, last), f"U-DRAW, held set {last}", True
    m = re.match(r"fract(\d+)(?: v2)?$", last)
    if m:
        n = int(m.group(1))
        return f"fract {n}", (1, n, ""), f"Fractals, set {n}", False
    if folder in LABELS:
        label = LABELS[folder]
        return "s " + label.lower(), (0, 0, label), label, False
    return "u " + folder, (1, 10 ** 6, folder), None, True  # named later: Untitled set A, B, ...


def prepare(new_art, new_other, data=DATA, map_path=MAP):
    rows = list(csv.DictReader(open(new_art, encoding="utf-8"), delimiter="\t"))
    skipped = Counter()
    keep = []
    for r in rows:
        src = r["best_copy"]
        w, h = int(r["width"] or 0), int(r["height"] or 0)
        sec, folder = classify(src)
        if sec is None:
            skipped[folder] += 1
            continue
        if src.lower().endswith(NO_WEB) or not w or not h:
            skipped["file format a browser or Pillow cannot show (CorelDraw, WMF, EPS, IFF, RLE)" if w else "unreadable or empty file"] += 1
            continue
        if "small/icon" in r["flags"] or max(w, h) < 200 or max(w, h) / min(w, h) > 3:
            skipped["icons, buttons and thumbnails"] += 1
            continue
        if "maybe-other-artist" in r["flags"]:
            skipped["possibly another artist's work (flagged in the survey)"] += 1
            continue
        if "camera-photo" in r["flags"] and re.search(r"/ud(raw)?20\d\d", src.lower()):
            skipped["camera photos of people in the U-DRAW folders"] += 1
            continue
        keep.append((sec, folder, r, w, h))
    # Don Pics are backups of the year folders: U-DRAW sets go to the year that holds the same
    # numbers (the nearest set number when that set has no folder of its own), other folders to
    # the year with a folder of the same name; anything else stays under "studio backups".
    udraw_year, folder_year = {}, {}
    for sec, folder, r, w, h in keep:
        if sec in ("don pics", "disks"):
            continue
        g = series(folder)
        if g[0].startswith("udraw ") and g[1][1] >= 0:
            udraw_year.setdefault(g[1][1], sec)
        folder_year.setdefault(folder.split("/")[-1], sec)
    placed = []
    for sec, folder, r, w, h in keep:
        if sec == "don pics":
            g = series(folder)
            if g[0].startswith("udraw ") and g[1][1] >= 0 and udraw_year:
                n = g[1][1]
                sec = udraw_year.get(n) or udraw_year[min(udraw_year, key=lambda k: (abs(k - n), k))]
            elif folder.split("/")[-1] in folder_year:
                folder = folder.split("/")[-1]
                sec = folder_year[folder]
            else:
                sec = "backups"
        placed.append((sec, folder, r, w, h))
    # untitled sets: letters in order of year and folder
    untitled = sorted({(sec, folder) for sec, folder, *_ in placed if series(folder)[2] is None})
    letters = {}
    for sec, folder in untitled:
        n = sum(1 for (s, _) in letters if s == sec)
        letters[(sec, folder)] = "Untitled set " + chr(ord("A") + n)
    out = []
    for sec, folder, r, w, h in placed:
        gkey, _, label, _ = series(folder)
        label = label or letters[(sec, folder)]
        out.append({"section": sec, "group": gkey, "label": label, "kind": "image", "source": r["best_copy"],
                    "width": w, "height": h, "bytes": r["bytes"], "caption": real_caption(r["title_or_caption"], r["best_copy"])})
    # music and video from Don's folders (the website archive's are published with those pages)
    others = list(csv.DictReader(open(new_other, encoding="utf-8"), delimiter="\t"))
    other_skip = Counter()
    for r in others:
        p = r["path"]
        if r["class"] in ("audio", "video") and not p.startswith("website files archive/"):
            out.append({"section": "media", "group": r["class"], "label": "Music" if r["class"] == "audio" else "Video",
                        "kind": r["class"], "source": p, "width": "", "height": "", "bytes": r["bytes"], "caption": ""})
        elif not p.startswith("website files archive/"):
            other_skip[r["class"]] += 1
    out.sort(key=lambda x: (x["section"], x["group"], x["source"].lower()))
    with open(data, "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, COLS, delimiter="\t", lineterminator="\n")
        wr.writeheader()
        wr.writerows(out)
    with open(map_path, "w", encoding="utf-8") as f:
        for x in out:
            f.write(f"{key_of(x['source'])}\t{x['source']}\t{x['bytes']}\n")
    print(f"{len(out)} items kept ({sum(1 for x in out if x['kind'] == 'image')} images), "
          f"{sum(int(x['bytes']) for x in out) / 1e9:.2f} GB")
    for why, n in skipped.most_common():
        print(f"  skipped {n:5d}  {why}")
    for cls, n in other_skip.most_common():
        print(f"  not published in this pass: {n} {cls} files")
    return out


# ------------------------------------------------------------------ pages
def load(data=DATA):
    with open(data, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    for r in rows:
        r["key"] = key_of(r["source"])
        r["w"] = int(r["width"] or 0)
        r["h"] = int(r["height"] or 0)
    return rows


def media_url(path, variant=None):
    suffix = {"mp4": ".mp4", "poster": ".poster.webp"}.get(variant, f".w{variant}.webp" if variant else "")
    return MEDIA_BASE + "/" + quote(path + suffix)


def media_info(r):
    if r["kind"] == "image":
        return {"w": r["w"], "h": r["h"], "type": "image",
                "variants": {str(v): f"{r['key']}.w{v}.webp" for v in variant_widths(r["w"])}}
    if r["kind"] == "video":
        return {"type": "video", "mp4": r["key"] + ".mp4", "poster": r["key"] + ".poster.webp"}
    return {"type": "audio"}


def section_title(sec):
    return {"disks": "3.5-inch disks", "backups": "Studio backups"}.get(sec, sec)


def section_url(sec, page=1):
    base = f"/studio/{SECTION_SLUG.get(sec, sec)}/"
    return base if page == 1 else f"{base}page-{page}.html"


def paginate(groups):
    """[(group, [rows])] -> pages of at most PER_PAGE pictures, each [(group, rows, continued)].
    A series starts on a new page rather than being cut, unless the page is still under two
    thirds full or the series is longer than a page."""
    pages, cur, n = [], [], 0
    for g, rows in groups:
        i = 0
        while i < len(rows):
            room = PER_PAGE - n
            rest = len(rows) - i
            if cur and (room <= 0 or (rest > room and rest <= PER_PAGE and n >= PER_PAGE * 2 // 3)):
                pages.append(cur)
                cur, n = [], 0
                continue
            take = min(room, rest)
            cur.append((g, rows[i:i + take], i > 0))
            n += take
            i += take
    if cur:
        pages.append(cur)
    return pages


def good_thumb(rows):
    """A card picture: a large landscape picture from a named (not personal) series, in a format
    that converts reliably; the middle one of those, for variety."""
    def ok(r, big):
        return (r["kind"] == "image" and not r["group"].startswith(("udraw", "gifhold", "u ")) and r["w"] >= big
                and 1.2 <= r["w"] / r["h"] <= 1.5 and r["source"].lower().endswith((".jpg", ".jpeg", ".gif", ".png")))
    for big in (1600, 1000, 600, 0):
        c = sorted((r for r in rows if ok(r, big)), key=lambda r: r["source"].lower())
        if c:
            return c[len(c) // 2]
    c = sorted((r for r in rows if r["kind"] == "image" and r["w"] >= 400), key=lambda r: r["source"].lower())
    return c[len(c) // 2] if c else None


def figure(r, n, sec, media):
    cap = r["caption"] or f"{r['label']}, image {r['no']}"
    where = SECTION_TEXT.get(sec, sec)
    alt = f"{'U-DRAW fractal, ' if r['group'].startswith(('udraw', 'gifhold')) else ''}{cap} ({where})"
    full = T.view_url(r["key"], media, media_url)
    return (f'<figure class="{T.fig_class({"src": r["key"]}, media)}" id="image-{n}"><a class="zoom" href="{E(media_url(r["key"]))}" data-full="{E(full)}">'
            + T.img_tag(r["key"], media, media_url, alt, sizes="(max-width: 640px) 50vw, 260px", tile=True)
            + f"</a><figcaption>{E(cap)}</figcaption></figure>")


def card_html(url, title, sub, r, media):
    if r:
        pic = T.img_tag(r["key"], media, media_url, "", sizes="(max-width:640px) 50vw, 220px").replace("<img ", '<img class="cimg" ', 1)
    else:
        pic = f'<span class="ph" aria-hidden="true">{E(title[:1])}</span>'
    return f'<a class="card" href="{E(url)}">{pic}<div><h3>{E(title)}</h3><p>{E(sub)}</p></div></a>'


def build(write, site_url, data=DATA):
    """Write every studio page. Returns {"pages": [page records for search], "card": the hub's
    card for other hubs, "count": pictures shown}."""
    rows = load(data)
    media = {r["key"]: media_info(r) for r in rows}
    by_sec = defaultdict(list)
    for r in rows:
        by_sec[r["section"]].append(r)
    order = sorted((s for s in by_sec if s.isdigit()), key=int) + [s for s in ("disks", "backups") if s in by_sec]
    pages_out, cards, sec_pages = [], [], {}
    # group and number the pictures of each section
    for sec in order:
        groups = OrderedDict()
        for r in sorted(by_sec[sec], key=lambda r: (series_sort(r), r["source"].lower())):
            groups.setdefault(r["group"], []).append(r)
        for g, rs in groups.items():
            for i, r in enumerate(rs, 1):
                r["no"] = i
        sec_pages[sec] = (list(groups.items()), paginate(list(groups.items())))
    for si, sec in enumerate(order):
        groups, pages = sec_pages[sec]
        sizes = dict(groups)
        total = sum(len(rs) for _, rs in groups)
        title0 = section_title(sec)
        where = SECTION_TEXT.get(sec, sec)
        first_page_of = {}
        for pi, pg in enumerate(pages, 1):
            for g, rs, cont in pg:
                first_page_of.setdefault(g, pi)
        jump = "<br>".join(f'<a href="{E(section_url(sec, first_page_of[g]))}#s-{slug(rs[0]["label"])}">{E(rs[0]["label"])}</a>' for g, rs in groups)
        nxt_sec = order[si + 1] if si + 1 < len(order) else None
        prv_sec = order[si - 1] if si else None
        thumb = good_thumb(by_sec[sec])
        for pi, pg in enumerate(pages, 1):
            url = section_url(sec, pi)
            title = f"Don Archer · {title0}" if pi == 1 else f"Don Archer · {title0} · page {pi}"
            n_here = sum(len(rs) for _, rs, _ in pg)
            intro = (f"{total:,} works from Don Archer's {E(where)} folders"
                     if sec.isdigit() else f"{total:,} works from Don Archer's {E(where)}")
            intro += f", in {len(groups)} series." if len(groups) > 1 else "."
            if len(pages) > 1:
                intro += f" Page {pi} of {len(pages)}."
            prose = (f'<div class="b prose"><p>{intro} Click a picture to see it large; the viewer links to the original file. '
                     f'<a href="/studio/">All years of the {NAME}</a>.</p>'
                     + (f"<details><summary>The {len(groups)} series of {E(title0)}</summary><p class=\"links\">{jump}</p></details>" if len(groups) > 1 else "") + "</div>")
            body_groups, n = [], 0
            for g, rs, cont in pg:
                figs = []
                for r in rs:
                    n += 1
                    figs.append(figure(r, n, sec, media))
                head = E(rs[0]["label"]) + (" (continued)" if cont else "")
                anchor = "" if cont else f' id="s-{slug(rs[0]["label"])}"'
                note = "" if cont else f'<p class="note">{len(sizes[g])} works</p>'
                cls = T.wall_class(len(rs), len(rs))
                body_groups.append(f'<h2 class="sec"{anchor}>{head}</h2>{note}<div class="{cls}">{"".join(figs)}</div>')
            pager = []
            if pi > 1:
                pager.append(f'<a class="pill" href="{E(section_url(sec, pi - 1))}">← Previous</a>')
            elif prv_sec:
                pager.append(f'<a class="pill" href="{E(section_url(prv_sec))}">← {E(section_title(prv_sec))}</a>')
            if len(pages) > 1:
                for k in range(1, len(pages) + 1):
                    pager.append(f'<span class="btn" aria-current="page">{k}</span>' if k == pi else
                                 f'<a class="pill" href="{E(section_url(sec, k))}">{k}</a>')
            if pi < len(pages):
                pager.append(f'<a class="pill next" href="{E(section_url(sec, pi + 1))}">Next</a>')
            elif nxt_sec:
                pager.append(f'<a class="pill next" href="{E(section_url(nxt_sec))}">{E(section_title(nxt_sec))}</a>')
            nav = f'<nav class="pager" aria-label="Pages of {E(title0)}">{"".join(pager)}</nav>'
            body = (prose + f'<div class="b gbar"><span>{n_here} works on this page</span>'
                    f'<button class="btn" id="play" data-timer="4" type="button">▶ Play slideshow</button></div>'
                    f'<div id="gallery">{"".join(body_groups)}</div>' + nav)
            first = pg[0][1][0]
            og = thumb if pi == 1 and thumb else first
            desc = (f"Don Archer's computer art from {where}: {total:,} works"
                    + (f" in {len(groups)} series" if len(groups) > 1 else "")
                    + f", from the studio folders he kept." + (f" Page {pi} of {len(pages)}." if len(pages) > 1 else ""))
            write(url, T.page(title=title, url=url, section=SECTION, body=body, desc=desc, site_url=site_url,
                              og_image=media_url(og["key"], max(media[og["key"]]["variants"], key=int)), scripts=["/assets/gallery.js"]))
            pages_out.append({"path": "studio" + url[len("/studio"):], "url": url, "title": title, "section": NAME, "images": [],
                              "links": [], "dropped": [], "text_chars": 0, "words": []})
        cards.append(card_html(section_url(sec), title0, f"{total:,} works" + (f" · {len(pages)} pages" if len(pages) > 1 else ""), thumb, media))

    # music and video
    av = sorted((r for r in rows if r["section"] == "media"), key=lambda r: (r["kind"] != "video", r["source"].lower()))
    if av:
        blocks = []
        vids = [r for r in av if r["kind"] == "video"]
        mids = [r for r in av if r["kind"] == "audio"]
        if mids:
            items = "".join(f'<div><p class="note">MIDI file {i} ({int(r["bytes"]) / 1024:.0f} KB)</p>'
                            + T.media_block({"t": "media", "src": r["key"], "kind": "audio"}, media_url, media) + "</div>"
                            for i, r in enumerate(mids, 1))
            blocks.append(f'<h2 class="sec">MIDI music</h2><div class="b prose"><p>{len(mids)} MIDI files from Don Archer\'s '
                          f'3.5-inch disks of the 1990s, when his web pages played background music. Who composed or sequenced each '
                          f'piece is not recorded with the files.</p></div>{items}')
        for r in vids:
            if "donnie" in r["source"].lower():
                blocks.append('<h2 class="sec">The Donnie 2009 slideshow</h2><div class="b prose"><p>A slideshow of the Donnie 2009 '
                              'contest found in Don Archer\'s 2009 folder. The works in it are by the contest\'s artists; see the '
                              '<a href="/donnie2009/winners.htm">Donnie 2009 winners</a>.</p></div>'
                              + T.media_block({"t": "media", "src": r["key"], "kind": "video"}, media_url, media))
            else:
                blocks.append(T.media_block({"t": "media", "src": r["key"], "kind": "video"}, media_url, media))
        url = "/studio/music.html"
        title = "Don Archer · Music and video"
        body = (f'<div class="b prose"><p>Music and video files kept with Don Archer\'s studio folders. '
                f'<a href="/studio/">All years of the {NAME}</a>.</p></div>' + "".join(blocks))
        poster = media_url(vids[0]["key"], "poster") if vids else None
        write(url, T.page(title=title, url=url, section=SECTION, body=body, site_url=site_url, og_image=poster,
                          desc=f"MIDI music and video from Don Archer's studio folders: {len(mids)} MIDI files and {len(vids)} video."))
        pages_out.append({"path": "studio/music.html", "url": url, "title": title, "section": NAME, "images": [], "links": [],
                          "dropped": [], "text_chars": 0, "words": []})
        sub = f"{len(mids)} MIDI files" + (f" · {len(vids)} video" if vids else "")
        av_card = (f'<a class="card" href="{url}">' + (f'<img class="cimg" src="{E(poster)}" loading="lazy" decoding="async" alt="">' if poster else
                   '<span class="ph" aria-hidden="true">M</span>') + f'<div><h3>Music and video</h3><p>{E(sub)}</p></div></a>')
    else:
        av_card = ""

    # the hub
    n_img = sum(1 for r in rows if r["kind"] == "image")
    years = [s for s in order if s.isdigit()]
    yr_cards = [c for s, c in zip(order, cards) if s.isdigit()]
    other_cards = [c for s, c in zip(order, cards) if not s.isdigit()] + ([av_card] if av_card else [])
    body = (f'<div class="b prose"><p>Don Archer, who founded the Museum of Computer Art in 1993, kept his work in a folder for each year. '
            f'This archive shows {n_img:,} pictures from those folders and from his 3.5-inch disks that the museum\'s web pages never showed: '
            f'early fractals, the Fractal Camera and Fractal Zoo, object scans, portraits, photo art and textures, and the numbered '
            f'series of his later years.</p>'
            f'<p>Most of the pictures from 1996 to 2001 are U-DRAW fractals. Visitors to Don Archer\'s website typed a few words into '
            f'his U-DRAW program, which drew a fractal from them; each picture was named for the person who made it, so here they are '
            f'shown by set and number only.</p>'
            f'<p>Works the museum already shows are not repeated here: see <a href="/adon/abase.html">Don Archer\'s collection</a> and '
            f'<a href="/ai.html">his AI art</a>.</p></div>'
            f'<h2 class="sec">By year</h2><div class="cards">{"".join(yr_cards)}</div>'
            + (f'<h2 class="sec">Disks, music and video</h2><div class="cards">{"".join(other_cards)}</div>' if other_cards else ""))
    hub_thumb = good_thumb([r for r in rows if r["section"] in years[:4]]) or good_thumb(rows)
    write("/studio/", T.page(title=NAME, url="/studio/", section=("Collection", "c1", "/collection.html"), body=body, site_url=site_url,
                             og_image=media_url(hub_thumb["key"], max(media[hub_thumb["key"]]["variants"], key=int)) if hub_thumb else None,
                             desc=f"{n_img:,} works by MOCA founder Don Archer from his studio folders, {years[0]} to {years[-1]}: "
                                  f"fractals, U-DRAW fractals, object scans, portraits and photo art, year by year."))
    pages_out.insert(0, {"path": "studio/", "url": "/studio/", "title": NAME, "section": NAME, "images": [], "links": [],
                         "dropped": [], "text_chars": 0, "words": []})
    card = card_html("/studio/", NAME, f"{n_img:,} works, {years[0]}–{years[-1]}", hub_thumb, media)
    return {"pages": pages_out, "card": card, "count": n_img, "years": f"{years[0]}–{years[-1]}"}


def series_sort(r):
    """Disks by number, then named series (alphabetically), numbered fractal sets, untitled sets,
    and the U-DRAW sets by number."""
    g = r["group"]
    if g.startswith("disk "):
        k = (0, int(g[5:]), "")
    elif g.startswith("s "):
        k = (1, 0, r["label"].lower())
    elif g.startswith("fract "):
        k = (2, int(g[6:]), "")
    elif g.startswith("u "):
        k = (3, 0, r["label"])
    elif g == "udraw early":
        k = (4, -2, "")
    elif g == "udraw sr":
        k = (4, -1, "")
    elif g == "udraw best":
        k = (4, -3, "")
    elif g.startswith("gifhold "):
        k = (4, 0, g)
    elif g.startswith("udraw "):
        k = (5, int(g[6:]), "")
    else:
        k = (6, 0, g)
    return k


def slug(g):
    return re.sub(r"[^a-z0-9]+", "-", g.lower()).strip("-")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "prepare":
        prepare(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
