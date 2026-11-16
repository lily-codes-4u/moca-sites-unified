"""HTML templates for the unified MOCA site (Bento design, prototype 3)."""
import difflib
import hashlib
import html
import json
import os
import re
import shutil
import time
from collections import Counter
from urllib.parse import quote, unquote

E = html.escape
NAV = [("/collection.html", "Collection"), ("/ai.html", "AI Art"), ("/donnie.html", "The Donnie"),
       ("/artists.html", "Artists"), ("/archive.html", "Archive"), ("/about.htm", "About")]
NAV_TEXT = re.compile(r"^(index of .*|first|last|first page|last page|view (all|contest) .*|(back to |to )?top( of page)?|next( page| image)?|previous( page| image)?|prev|back|go back|home|moca home|main page|index|top|return( to.*)?|"
                      r"moca|museum of computer art|mocadigitalart|moca\.virtual\.museum|forward|>>|<<|>|<|\d{1,3})$", re.I)
ASSET_VER = {}
DEFAULT_DESC = "Museum of Computer Art: digital fine art since 1993."

# ------------------------------------------------------------------ titles
# Text the old pages put where a title belongs but which names nothing: a hit-counter widget,
# leftover markup or arrows, script placeholders, "(3 of 8)" counters and notes to the reader.
JUNK_TITLE = re.compile(r"^(.*visitors online( now)?|[,\s]*ET,.*|add bad words|var \w+|<?/?(html|head|body)>?|\[gallery\]|\(?\d+ of \d+\)?|"
                        r"\(?(please )?see (the )?note below\)?|this page has not (yet )?been fully populated|no comments available on this artist\.?|"
                        r"\(debug path:.*\)|_+|visitors \w{3} [\d/]+)$", re.I)
TITLE_TYPOS = [(re.compile(r"\bSubmision\b"), "Submission"), (re.compile(r"\bsubmision\b"), "submission")]
SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}
ABBREV = {"bros", "ave", "inc", "ltd", "etc", "vol", "dept", "assn", "corp", "univ", "mrs"}
KEEP_CAPS = {"AI", "MOCA", "MOCANET", "NY", "NYC", "NYS", "USA", "UK", "II", "III", "IV", "TV", "3D", "JD", "MD", "DNA", "CD", "DVD"}


def junk_title(t):
    t = re.sub(r"\s+", " ", t or "").strip()
    return not re.search(r"\w", t) or bool(JUNK_TITLE.match(t))


def _unshout(part):
    """'ALL THE SHIPS AT SEA' -> 'All the Ships at Sea'; acronyms and tokens with digits stay."""
    words = part.split(" ")
    out = []
    for i, w in enumerate(words):
        core = re.sub(r"^\W+|\W+$", "", w)
        if core == "PAYPAL":
            out.append(w.replace(core, "PayPal"))
            continue
        if not core or core in KEEP_CAPS or re.search(r"\d", core):
            out.append(w)
            continue
        low = w.lower()
        if i and core.lower() in SMALL_WORDS:
            out.append(low)
        else:
            j = len(w) - len(w.lstrip("\"'(["))
            out.append(low[:j] + low[j:j + 1].upper() + low[j + 1:])
    return " ".join(out)


def tidy_title(t):
    """General clean-ups of a page title made from the old pages' own words."""
    orig = t = re.sub(r"\s+", " ", t or "").strip()
    for pat, rep in TITLE_TYPOS:
        t = pat.sub(rep, t)
    # "the Museum of Computer Art Donations" -> "Donations"; "Mary's Page at MOCA: the Museum of Computer Art" -> "Mary's Page at MOCA"
    t = re.sub(r"^the Museum of Computer Art\s*[:|\-–—]?\s+(?=\w)", "", t)
    t = re.sub(r"(?<=\w)\s*(:|[–—|-]+)\s*(the )?Museum of Computer Art\s*$", "", t, flags=re.I)
    # stray arrows and backslashes from old navigation ("<Originals", "Three Graces · <")
    parts = [re.sub(r"^[<>\\]+\s*|\s*[<>\\]+$", "", p.strip()) for p in t.split(" · ")]
    parts = [p for p in parts if p]
    kept = []
    for i, p in enumerate(parts):
        low = p.lower()
        # a part repeated word for word, or "Museum of Computer Art Donnie 2009" after "Donnie 2009"
        rest = re.sub(r"^(the )?museum of computer art\b\W*", "", low).strip(" .")
        others = [q.lower() for j, q in enumerate(parts) if j != i]
        if low in [k.lower() for k in kept] or (rest != low and (not rest or any(rest in q for q in others))):
            continue
        if not kept:  # the leading part: a page or section heading, not an artwork's own title
            # one sentence-ending period ("Includes AI Art."), never "...", "Jr.", "Bros." or "Q.E.D."
            last = p.rsplit(" ", 1)[-1]
            if re.fullmatch(r"[\"'(]*[A-Za-z]{3,}\.", last) and last.strip("\"'(.").lower() not in ABBREV:
                p = p[:-1]
            # set in capitals, two or more words
            if not re.search(r"[a-z]", p) and len(re.findall(r"\b[A-Z][A-Z']{2,}\b", p)) >= 2:
                p = _unshout(p)
        kept.append(p)
    t = " · ".join(kept) or t
    # a lowercase sentence start ("the Kremlin", "click to view or order ..."), not handles like "jjblack" or "fa2k"
    if re.match(r"the\s", t) or (re.match(r"[a-z]+\s", t) and len(t.split()) >= 3):
        t = t[0].upper() + t[1:]
    return t.strip() or orig


def shorten_title(t, artwork=False, limit=90):
    """Over-long titles lose whole ' · ' parts instead of stopping mid-phrase. On a single-artwork
    page ("Exhibit · Artist · Artwork title") the exhibit name goes first, so the artwork's own
    title stays; elsewhere the trailing parts go."""
    parts = t.split(" · ")
    while artwork and len(" · ".join(parts)) > limit and len(parts) > 1:
        parts.pop(0)
    t = " · ".join(parts)
    if len(t) > limit:
        t = t[:limit - 3].rsplit(" ", 1)[0].rstrip(" ·,:;-") + "…"
    if t.endswith("…") and " · " in t:
        t = t.rsplit(" · ", 1)[0]
    return t


def drop_title_echo(body, title):
    """Leave out a first heading or bold line that only repeats the page title shown just above it."""
    m = re.match(r'(<div class="b prose[^"]*">)(<hr>)?(<p>|<h2>)(.*?)(</p>|</h2>)', body)
    if not m:
        return body
    txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(4)))).strip()
    if not txt or txt.lower().strip(" .:!") != title.lower().strip(" .:!"):
        return body
    rest = body[m.end():]
    if rest.startswith("</div>"):
        return rest[len("</div>"):].lstrip("\n")
    return m.group(1) + rest


def asset(path):
    return path + ("?v=" + ASSET_VER[path] if path in ASSET_VER else "")


SITE_NAME = "Museum of Computer Art"
OG_DEFAULT = "/og-image.png"
# Pages that stay reachable but are kept out of search results: the error page, snapshots of
# the old front pages, and the "files no page showed" listings.
NOINDEX = re.compile(r"^/(404\.html|index\.htm|legacy/|unlisted/)")
URL_SAFE = "/~()&+,;=:@!$'*-._"


def canonical_path(url):
    """Site path -> the one URL a page is known by: no fragment, folder index pages as the folder,
    unsafe characters (spaces) percent-encoded."""
    u = url.split("#")[0]
    if u.endswith("/index.html"):
        u = u[:-len("index.html")]
    return quote(unquote(u), safe=URL_SAFE)


def _plain(h):
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h or ""))).strip()
    return re.sub(r" ([,.;:!?)])", r"\1", t)


def _norm(t):
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def _boilerplate(t, title):
    low, n = t.lower().strip(" ."), _norm(t)
    if len(n) < 4 or n in _norm(title) or n in ("museumofcomputerart", "mocamuseumofcomputerart") or low.startswith(DEFAULT_DESC.lower().rstrip(".")) or low.endswith(DEFAULT_DESC.lower().rstrip(".")):
        return True
    if re.search(r"(computer|digital) art museum,\s+works by", low):
        return True
    if re.fullmatch(r"(moca\W*)?(museum of computer art\W*)?(the )?donnie( \d{4})?\W*", low):
        return True
    if "{{" in t or re.search(r"https?://|www\.|\bclick\b|\.(jpe?g|gif|png)\b|^(next|previous|prev|back|return|go to|visit|see)\b|moca home", low):
        return True
    segs = [s for s in t.split(",") if s.strip()]
    return (len(segs) >= 4 and not re.search(r"[.:]| and ", t.rstrip(".")) and sum(map(len, segs)) / len(segs) < 25)  # keyword list


def _clip(t, n=160):
    if len(t) <= n:
        return t
    return t[:n - 2].rsplit(" ", 1)[0].rstrip(" ,;:·-–—(") + "…"


def describe(title, given, body, section=""):
    """Meta description from the page's own words (70-160 characters): its old description if
    that was real text, else its first paragraph. Pages without that much text of their own keep
    the short description they were given, or "<title> · Museum of Computer Art: ...", with the
    old site-wide boilerplate descriptions replaced by the latter."""
    title = _plain(title)
    raw = _plain(given)
    given = "" if _boilerplate(raw, title) else raw
    texts = []
    for m in re.finditer(r'<(p|figcaption)( class="[^"]*")?>(.*?)</\1>', body or "", re.S):
        if m.group(2) and re.search(r"links|note|fine|cap", m.group(2)):
            continue
        t = re.sub(r"^(THE )?MUSEUM OF COMPUTER ART\b[\s:·|-]*|^MOCA\s*[:·|-]+\s*", "", _plain(m.group(3)))  # old page headers
        if len(t) >= 20 and not _boilerplate(t, title):
            texts.append(t)
    for t in [given] + texts:
        if len(t) >= 70:
            return _clip(t)
    if raw and _boilerplate(raw, "") is False:
        return _clip(raw)
    return _clip(f"{title} · {DEFAULT_DESC}")


def ld_script(data):
    j = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/ld+json">{j}</script>'


def org_ld(site_url):
    return {"@context": "https://schema.org", "@type": ["Museum", "NGO"], "@id": site_url + "/#museum",
            "name": SITE_NAME, "alternateName": "MOCA", "url": site_url + "/", "logo": site_url + "/logo.png",
            "image": site_url + OG_DEFAULT, "foundingDate": "1993", "email": "hello@museumofcomputerart.org",
            "founder": [{"@type": "Person", "name": "Don Archer"}, {"@type": "Person", "name": "Bob Dodson"}],
            "nonprofitStatus": "https://schema.org/Nonprofit501c3",
            "description": "A nonprofit museum of digital fine art, online since 1993. Free to view, free to exhibit, no advertising."}


def website_ld(site_url):
    return {"@context": "https://schema.org", "@type": "WebSite", "@id": site_url + "/#website", "name": SITE_NAME,
            "alternateName": "MOCA", "url": site_url + "/", "inLanguage": "en", "publisher": {"@id": site_url + "/#museum"}}


def breadcrumb_ld(trail, site_url):
    """trail: [(name, path or None)], the visible breadcrumbs followed by the page itself."""
    items = []
    for i, (name, path) in enumerate(trail, 1):
        it = {"@type": "ListItem", "position": i, "name": name}
        if path:
            it["item"] = site_url + canonical_path(path)
        items.append(it)
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items}


def head(title, url, desc, og_image, site_url, extra="", ld=()):
    canon = site_url + canonical_path(url)
    full_title = title if title.startswith("MOCA") else f"{title} · MOCA"
    d = E(_clip(_plain(desc) or f"{title} · {DEFAULT_DESC}"))
    robots = '\n<meta name="robots" content="noindex, follow">' if NOINDEX.match(url) else ""
    canon_tag = f'\n<link rel="canonical" href="{E(canon)}">' if url != "/404.html" else ""
    og_url = f'<meta property="og:url" content="{E(canon)}">' if url != "/404.html" else ""
    img = og_image or site_url + OG_DEFAULT
    ld_html = "".join("\n" + ld_script(x) for x in ld)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{E(full_title)}</title>
<meta name="description" content="{d}">{robots}{canon_tag}
<meta property="og:site_name" content="{SITE_NAME}"><meta property="og:title" content="{E(full_title)}"><meta property="og:description" content="{d}">{og_url}<meta property="og:type" content="website"><meta property="og:image" content="{E(img)}"><meta property="og:image:alt" content="{E(title if og_image else SITE_NAME)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#3b5bfd">
<link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="icon" href="/favicon.ico" sizes="32x32"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><link rel="manifest" href="/site.webmanifest">
<link rel="preload" href="/assets/fonts/bricolage.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/figtree.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{asset('/assets/site.css')}">
<!--PRECONNECT--><script src="{asset('/assets/site.js')}" defer></script>{extra}{ld_html}
</head>"""


def header(active=None):
    links = "".join(f'<a href="{h}"{" aria-current=page" if h == active else ""}>{t}</a>' for h, t in NAV)
    return f"""<body>
<a class="skip" href="#main">Skip to content</a>
<header class="top"><div class="wrap">
  <a class="logo" href="/"><i aria-hidden="true"></i>MOCA</a>
  <nav aria-label="Main" id="nav">{links}<a class="donate" href="/donate.htm">Donate</a></nav>
  <button class="icon" id="searchbtn" aria-label="Search the museum" title="Search (/)"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="m20 20-4-4" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg></button>
  <button class="icon menu" id="menubtn" aria-label="Menu" aria-expanded="false" aria-controls="nav"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg></button>
</div></header>"""


FOOTER = """<footer class="foot"><div class="wrap">
  <div class="fcols">
    <div><a class="logo" href="/"><i aria-hidden="true"></i>MOCA</a><p>Museum of Computer Art. Digital fine art since 1993. No charge to viewers or artists, no advertising.</p></div>
    <div><h2>Visit</h2><a href="/collection.html">Collection</a><a href="/ai.html">AI Art</a><a href="/donnie.html">The Donnie</a><a href="/artists.html">Artists</a><a href="/grandmasters.htm">Grandmasters</a></div>
    <div><h2>Archive</h2><a href="/archive.html">Everything archived</a><a href="/catalogs.htm">All catalogs</a><a href="/autogalleryarchive.htm">AutoGallery archive</a><a href="/editorial/editorial.htm">Reviews &amp; essays</a></div>
    <div><h2>Museum</h2><a href="/about.htm">About MOCA</a><a href="/submit.html">Submit your art</a><a href="/donate.htm">Donate</a><a href="mailto:hello@museumofcomputerart.org">hello@museumofcomputerart.org</a></div>
  </div>
  <p class="fine">© 1993–2026 Museum of Computer Art, a 501(c)(3) nonprofit. Images remain the property of the artists.</p>
</div></footer>
<dialog id="lb" aria-label="Image viewer"><button class="x" aria-label="Close">×</button><img alt=""><p class="cap"></p><a class="orig" href="#" target="_blank" rel="noopener">Open original file</a></dialog>
<dialog id="sd" aria-label="Search"><form method="dialog" class="sbox"><input id="q" type="search" placeholder="Search artists, exhibits, titles…" autocomplete="off" aria-label="Search"><button class="x" aria-label="Close">×</button></form><ol id="res"></ol></dialog>
</body>
</html>"""


INDEX_LINK = re.compile(r'(<a [^>]*?href="/(?:[^"#?]*/)?)index\.html"')


def finalize_links(doc):
    """Link folder index pages by their canonical folder URL (/x/ rather than /x/index.html)."""
    return INDEX_LINK.sub(r'\1"', doc)


def finalize(doc):
    """Speed touches applied to every page: preconnect to the media host only when the page
    shows media; the first images are fetched eagerly, the very first at high priority.
    Only <img> tags are touched: embedded players (iframes) stay lazy, and old http:// images
    on third-party hosts never get the preconnect or the high priority."""
    after = doc.split("<main", 1)[-1]
    m = re.search(r'<img [^>]*?src="(https://[^/"]+)/', after) or re.search(r'src="(https://[^/"]+)/', after)
    pre = f'<link rel="preconnect" href="{m.group(1)}">\n' if m else ""
    doc = doc.replace("<!--PRECONNECT-->", pre, 1)
    doc = finalize_links(doc)
    head_, sep, main = doc.partition('<main id="main"')
    state = {"high": 'fetchpriority="high"' in main, "eager": 5}  # the next few images on screen: no lazy delay

    def speed(mt):
        tag = mt.group(0)
        if ' loading="lazy"' not in tag:
            return tag
        if not state["high"] and ' src="https://' in tag:
            state["high"] = True
            return tag.replace(' loading="lazy"', ' fetchpriority="high"', 1)
        if state["eager"] > 0:
            state["eager"] -= 1
            return tag.replace(' loading="lazy"', "", 1)
        return tag
    main = re.sub(r"<img [^>]*>", speed, main)
    return head_ + sep + main


# The breadcrumb names the page it links to: exhibit pages sit under the Artists hub.
CRUMB_LABEL = {"/artists.html": "Artists"}


def crumb_link(name, sec_url, url):
    label = E(CRUMB_LABEL.get(sec_url, name))
    if sec_url == url.split("#")[0]:  # the section's own index page: no link to itself
        return f'<span aria-current="page">{label}</span>'
    return f'<a href="{E(sec_url)}">{label}</a>'


def page(title, url, section, body, desc="", og_image=None, site_url="", scripts=(), active=None, crumb=True):
    sec_name, color, sec_url = section
    extra = "".join(f'\n<script src="{asset(s)}" defer></script>' for s in scripts)
    crumbs = (f'<nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a><span>/</span>{crumb_link(sec_name, sec_url, url)}</nav>'
              if crumb else "")
    ld = ()
    if crumb:
        label = CRUMB_LABEL.get(sec_url, sec_name)  # same words as the visible breadcrumbs
        if sec_url == url.split("#")[0]:
            trail = [("Home", "/"), (label, None)]
        elif sec_url != "/" and canonical_path(sec_url) != canonical_path(url):
            trail = [("Home", "/"), (label, sec_url), (title, None)]
        else:
            trail = [("Home", "/"), (title, None)]
        ld = (breadcrumb_ld(trail, site_url),)
    desc = describe(title, desc, body, sec_name)
    return finalize(head(title, url, desc, og_image, site_url, extra, ld) + header(active) + f"""
<main id="main" class="wrap">
<div class="phead b {color}">{crumbs}<h1>{E(title)}</h1></div>
{body}
</main>
""" + FOOTER)


# ------------------------------------------------------------------ blocks
def LOGOISH(path, media):
    m = media.get(path) or {}
    return deco(path, m.get("w"), m.get("h"))


def deco(path, w, h):
    """Banners, logos, buttons and strips: not artwork to crop into a square tile."""
    w, h = w or 0, h or 0
    if w and h and (w / h > 3 or h / w > 3 or (w < 120 and h < 120)):
        return True
    # narrow strips at most 100px across (the 280x100 MOCA logo, 150x50 buttons) are site graphics too
    if w and h and max(w, h) / min(w, h) >= 2.3 and min(w, h) <= 100:
        return True
    # "untitled" is a common artwork name, not a title graphic
    return bool(re.search(r"(logo|head|banner|(?<!un)title|top\d|header|button|footer)[^/]*$", path or ""))


# Image walls: one picture (plus banners) is shown alone and large; two to four share a row at full
# size, never cropped; five or more become a grid of square tiles that open in the viewer.
SIZES_BIG = "(max-width: 900px) 100vw, 66vw"
SIZES_TILE = "(max-width: 640px) 50vw, (max-width: 1040px) 33vw, 260px"


def wall_class(n_art, n_all):
    if not n_art:  # only small or strip-shaped pictures (e.g. a page of thumbnails): count them all
        n_art = n_all
    return "wall one" if n_art <= 1 else "wall few" if n_art <= 4 else "wall"


def is_nav_para(b):
    if b["t"] != "p" or "<a " not in b["html"]:
        return False
    anchors = re.findall(r"<a [^>]*>(.*?)</a>", b["html"], re.S)
    if not anchors:
        return False
    outside = re.sub(r"<a [^>]*>.*?</a>", "", b["html"], flags=re.S)
    outside = re.sub(r"<[^>]+>|&nbsp;|[\s|•·\-–—:/\[\]()]+", "", outside)
    if outside:
        return False
    return all(NAV_TEXT.match(html.unescape(re.sub(r"<[^>]+>", "", a)).strip()) for a in anchors)


def link_only(b):
    return bool(re.fullmatch(r"\s*(<[biu]>\s*)*<a [^>]*>.*?</a>\s*(</[biu]>\s*)*", b["html"], re.S))


def short_para(b):
    return (b and b["t"] == "p" and 0 < len(b["text"]) <= 160 and b["html"].count("<a ") <= 1 and not b.get("used")
            and not link_only(b) and not is_nav_para(b))


def link_dense(b):
    n = b["html"].count("<a ")
    if n < 4:
        return False
    a_text = sum(len(re.sub(r"<[^>]+>", "", x)) for x in re.findall(r"<a [^>]*>(.*?)</a>", b["html"], re.S))
    return a_text >= 0.5 * max(1, len(b["text"]))


def dead_links(h):
    return re.sub(r'<a href="([^"]*)" data-missing="1">(.*?)</a>', r'<span class="dead" title="This link pointed to a page that was not in the backups">\2</span>', h, flags=re.S)


def fill_media(h, media_url):
    return re.sub(r"\{\{MEDIA:([^}]*)\}\}", lambda m: E(media_url(html.unescape(m.group(1)))), h)


WEB_IMAGE = (".jpg", ".jpeg", ".gif", ".png", ".bmp", ".webp", ".svg", ".avif", ".ico")


def view_url(path, media, media_url):
    """The file the image viewer (lightbox, slideshow) shows: the 1600px WebP when there is one,
    the original when it is animated or a format browsers display, else the largest WebP made
    from it (Photoshop, TIFF and misnamed files cannot be shown by a browser)."""
    m = media.get(path) or {}
    var = m.get("variants") or {}
    if var.get("1600") and not m.get("animated"):
        return media_url(path, "1600")
    if m.get("animated") or path.lower().endswith(WEB_IMAGE):
        return media_url(path)
    for v in ("800", "480"):
        if var.get(v):
            return media_url(path, v)
    return media_url(path)


def img_tag(path, media, media_url, alt, eager=False, sizes="(max-width: 700px) 100vw, 50vw", w=None, h=None, tile=False):
    m = media.get(path) or {}
    W, H = m.get("w") or w, m.get("h") or h
    var = m.get("variants") or {}
    if m.get("animated") or not var:
        src, srcset = media_url(path), ""
    else:
        src = media_url(path, "1600" if "1600" in var else "480")
        parts = []
        if "480" in var:
            parts.append(f"{E(media_url(path, '480'))} {min(480, W or 480)}w")
        if "800" in var:
            parts.append(f"{E(media_url(path, '800'))} 800w")
        if "1600" in var:
            parts.append(f"{E(media_url(path, '1600'))} {min(1600, W or 1600)}w")
        srcset = f' srcset="{", ".join(parts)}" sizes="{sizes}"' if len(parts) > 1 else ""
    dims = f' width="{W}" height="{H}"' if W and H else ""
    if tile and W and H and min(W, H) < 400:
        dims += f' style="--s:{min(W, H)}px"'  # a square tile never grows past the picture's short side
    load = ' fetchpriority="high"' if eager == "high" or eager is True else "" if eager else ' loading="lazy"'
    return f'<img src="{E(src)}"{srcset}{dims}{load} decoding="async" alt="{E(alt)}">'


def link_href(link, media_url):
    kind, target = link
    if kind == "media":
        return media_url(target[1]), False
    if kind == "missing":
        return None, False
    return target, kind == "external"


def figure(b, media_url, media, caption="", eager=False, big=False, sizes=None):
    path = b.get("src")
    alt = b.get("alt") or html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", caption))).strip()[:140]
    caption = dead_links(fill_media(caption, media_url)) if caption else caption
    if b.get("ext"):
        tag = f'<img src="{E(b["ext"])}" loading="lazy" decoding="async" alt="{E(alt)}"' + (f' width="{b["w"]}" height="{b["h"]}"' if b.get("w") and b.get("h") else "") + ">"
        inner = tag
        full = b["ext"]
    else:
        sizes = sizes or (SIZES_BIG if big else SIZES_TILE)
        inner = img_tag(path, media, media_url, alt, eager=eager, sizes=sizes, w=b.get("w"), h=b.get("h"), tile=True)
        full = media_url(path)
    link = b.get("link")
    if link and link[0] != "missing":
        href, ext = link_href(link, media_url)
        is_img_link = href and re.search(r"\.(jpe?g|gif|png|bmp)$", href.split("?")[0], re.I)
        if is_img_link:
            a = f'<a class="zoom" href="{E(href)}" data-full="{E(href)}">{inner}</a>'
        else:
            a = f'<a href="{E(href)}"{" rel=noopener" if ext else ""}>{inner}</a>'
    else:
        disp = view_url(path, media, media_url) if path else full
        a = f'<a class="zoom" href="{E(full)}" data-full="{E(disp)}">{inner}</a>'
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    return f'<figure class="{fig_class(b, media)}">{a}{cap}</figure>'


def is_deco(b, media):
    if b.get("ext") or not b.get("src"):
        return False
    m = media.get(b["src"]) or {}
    return deco(b["src"], m.get("w") or b.get("w"), m.get("h") or b.get("h"))


def fig_class(b, media):
    return "art deco" if is_deco(b, media) else "art"


def media_block(b, media_url, media):
    if b.get("missing"):
        return ""
    kind = b.get("kind")
    if b.get("ext"):
        src = b["ext"]
        if kind == "iframe":
            if src.startswith("http"):
                src = re.sub(r"^http://", "https://", src)
            return f'<div class="b media"><iframe src="{E(src)}" loading="lazy" allowfullscreen title="Embedded media"></iframe></div>'
        return f'<div class="b media"><a href="{E(src)}" rel="noopener">Open external media</a></div>'
    path = b["src"]
    m = media.get(path) or {}
    ext = os.path.splitext(path)[1].lstrip(".").upper()
    orig = media_url(path)
    if kind == "video" or m.get("type") == "video":
        if m.get("mp4") or path.endswith(".mp4"):
            poster = f' poster="{E(media_url(path, "poster"))}"' if m.get("poster") else ""
            return (f'<figure class="b media"><video controls preload="none" playsinline{poster}'
                    f'{" width=%d height=%d" % (m["w"], m["h"]) if m.get("w") and m.get("h") else ""}>'
                    f'<source src="{E(media_url(path, "mp4"))}" type="video/mp4"></video>'
                    f'<figcaption><a href="{E(orig)}" download>Download original ({ext})</a></figcaption></figure>')
        return f'<div class="b media"><p>Video file ({ext}).</p><a class="btn" href="{E(orig)}" download>Download video</a></div>'
    if kind == "flash" or path.endswith(".swf"):
        w, h = b.get("w") or 640, b.get("h") or 480
        return (f'<figure class="b media flash"><div class="swf" data-swf="{E(orig)}" style="aspect-ratio:{w}/{h}">'
                f'<button class="btn play" type="button">▶ Play Flash animation</button></div>'
                f'<figcaption>Flash, played with the Ruffle emulator. <a href="{E(orig)}" download>Download .swf</a></figcaption></figure>')
    if kind == "audio" or m.get("type") == "audio":
        if path.endswith((".mp3", ".wav")):
            return f'<div class="b media"><audio controls preload="none" src="{E(orig)}"></audio></div>'
        return f'<div class="b media"><p>Background music ({ext}). Browsers no longer play this format directly.</p><a class="btn" href="{E(orig)}" download>Download {ext} file</a></div>'
    return f'<div class="b media"><a class="btn" href="{E(orig)}">Open {ext} file</a></div>'


def render_blocks(blocks, media_url, media):
    """Return (html, first_image_path)."""
    blocks = [dict(b) for b in blocks]
    pager = []
    content = []
    for b in blocks:
        if is_nav_para(b):
            for m in re.finditer(r'<a href="([^"]*)"([^>]*)>(.*?)</a>', b["html"], re.S):
                if "data-missing" in m.group(2):
                    lbl = html.unescape(re.sub(r"<[^>]+>", "", m.group(3))).strip()
                    if lbl and lbl.lower() not in ("next", "previous", "prev", "back", "home", "moca home", ">", "<", ">>", "<<"):
                        pager.append((None, lbl))
                    continue
                label = html.unescape(re.sub(r"<[^>]+>", "", m.group(3))).strip()
                if re.match(r"^(moca|museum of computer art|mocadigitalart|moca\.virtual\.museum|home|main page)$", label, re.I):
                    label = "MOCA home"
                if re.match(r"^(back to |to )?top( of page)?$", label, re.I):
                    continue
                pager.append((html.unescape(m.group(1)), label))
        else:
            content.append(b)
    imgs = [i for i, b in enumerate(content) if b["t"] == "img" and not b.get("missing") and not (media.get(b.get("src") or "") or {}).get("error")]
    first_img = next((content[i]["src"] for i in imgs if content[i].get("src") and not LOGOISH(content[i]["src"], media)), None)
    # caption direction
    before = sum(1 for i in imgs if i > 0 and short_para(content[i - 1]))
    after = sum(1 for i in imgs if i + 1 < len(content) and short_para(content[i + 1]))
    if before == after and imgs:
        first_has = imgs[0] > 0 and short_para(content[imgs[0] - 1])
        direction = "before" if first_has else "after"
    else:
        direction = "before" if before > after else "after"
    caps = {}
    for i in imgs:
        j = i - 1 if direction == "before" else i + 1
        if 0 <= j < len(content) and short_para(content[j]) and j not in imgs:
            # don't steal a caption that sits between two images on the "wrong" side
            caps[i] = content[j]["html"]
            content[j]["used"] = True
    out = []
    lead = ""
    n_imgs = len(imgs)
    text_chars = sum(len(b.get("text", "")) for b in content if b["t"] in ("p", "h") and not b.get("used"))
    if n_imgs == 1 and text_chars < 2500:
        i = imgs[0]
        info = []
        for k, b in enumerate(content):
            if k == i or b.get("used"):
                continue
            info.append(render_text(b, media_url, media))
        cap = caps.get(i, "")
        lead = html.unescape(re.sub(r"\s+", " ", re.sub(r"<br>", " · ", re.sub(r"<(?!br)[^>]+>", "", cap)))).strip(" ·")
        out.append('<div class="artwork">' + figure(content[i], media_url, media, cap, eager=True, big=True).replace('<figure class="art', '<figure class="art b', 1)
                   + ('<div class="b info">' + "".join(x for x in info if x) + "</div>" if any(info) else "") + "</div>")
    else:
        run, prose = [], []
        first = True

        def close_prose():
            if prose:
                out.append('<div class="b prose">' + "".join(prose) + "</div>")
                prose.clear()

        def close_run():
            nonlocal first
            if run:
                cls = wall_class(sum(1 for r in run if not is_deco(r[0], media)), len(run))
                sizes = SIZES_TILE if cls == "wall" else SIZES_BIG
                out.append(f'<div class="{cls}">' + "".join(figure(r[0], media_url, media, r[1], eager=r[2], sizes=sizes) for r in run) + "</div>")
                run.clear()

        for k, b in enumerate(content):
            if b.get("used"):
                continue
            if b["t"] == "img":
                if b.get("missing") or (media.get(b.get("src") or "") or {}).get("error"):
                    continue
                close_prose()
                run.append((b, caps.get(k, ""), first))
                first = False
            elif b["t"] in ("media", "embed"):
                close_prose(); close_run()
                out.append(media_block(b, media_url, media))
            elif b["t"] in ("paypal", "form-retired"):
                close_prose(); close_run()
                out.append(render_text(b, media_url, media))
            else:
                close_run()
                r = render_text(b, media_url, media)
                if r:
                    prose.append(r)
        close_prose(); close_run()
    if pager:
        seen, items = set(), []
        for href, label in pager:
            if href is None:
                if ("", label) not in seen:
                    seen.add(("", label))
                    items.append(f'<span class="pill dead" title="This page was not in the backups">{E(label)}</span>')
                continue
            if (href, label) in seen or not href or href.startswith("/") is False and not href.startswith(("http", "#", "mailto")):
                continue
            seen.add((href, label))
            cls = " next" if label.lower().startswith(("next", "forward")) else ""
            items.append(f'<a class="pill{cls}" href="{E(fill_media(href, media_url) if "{{" in href else href)}">{E(label)}</a>')
        out.append('<nav class="pager" aria-label="Exhibit navigation">' + "".join(items) + "</nav>")
    return "\n".join(x for x in out if x), first_img, lead


def render_text(b, media_url, media):
    t = b["t"]
    if t == "p":
        h = fill_media(b["html"], media_url)
        h = dead_links(h)
        cls = ' class="links"' if link_dense(b) else ""
        return f"<p{cls}>{h}</p>"
    if t == "h":
        return f"<h2>{fill_media(b['html'], media_url)}</h2>"
    if t == "hr":
        return "<hr>"
    if t == "paypal":
        return (f'<form class="b paypal" action="{E(b["action"])}" method="post" target="_top">{b["fields"]}'
                f'<button class="btn" type="submit">Donate with PayPal</button></form>')
    if t == "form-retired":
        return ('<p class="note">This page once had an online form that ran on the old server. '
                'Please email <a href="mailto:hello@museumofcomputerart.org">hello@museumofcomputerart.org</a> instead.</p>')
    if t == "img":
        return figure(b, media_url, media) if ((b.get("src") and not (media.get(b["src"]) or {}).get("error")) or b.get("ext")) else ""
    if t in ("media", "embed"):
        return media_block(b, media_url, media)
    return ""


# Alt text that is only a file name ("image002", "154", "onlineonwall405787", "thanks.gif") says nothing.
FILE_STEM = re.compile(r"(?:img|image|dsc|dscn|pic|photo|p)?[_\- ]?\d+[a-z]?|\S*\d{5,}\S*|\S+\.(?:jpe?g|gif|png|bmp)", re.I)
ALT_ATTR = re.compile(r'(<img [^>]*?)alt="([^"]*)"')


def name_alts(body, title):
    """Artwork images with no alt text, or a file name as alt text, are described by the page title."""
    def fix(m):
        alt = html.unescape(m.group(2)).strip()
        return m.group(1) + (f'alt="{E(title)}"' if not alt or FILE_STEM.fullmatch(alt) else m.group(0)[len(m.group(1)):])
    return ALT_ATTR.sub(fix, body)


def render_autogallery(items, header_blocks, message_blocks, cfg, media_url, media, title=""):
    intro = []
    for b in message_blocks + header_blocks:
        if is_nav_para(b):
            continue
        r = render_text(b, media_url, media)
        if r:
            intro.append(r)
    timer = re.sub(r"\D", "", cfg.get("SlideShowTimer", "4")) or "4"
    tiles = []
    cls = wall_class(sum(1 for it in items if not is_deco({"src": it["src"]}, media)), len(items))
    sizes = "(max-width: 640px) 50vw, 260px" if cls == "wall" else SIZES_BIG
    for it in items:
        full = view_url(it["src"], media, media_url)
        alt = f'{title}, image {it["n"]}' if title and FILE_STEM.fullmatch(it["caption"].strip()) else it["caption"]
        tiles.append(f'<figure class="{fig_class({"src": it["src"]}, media)}" id="image-{it["n"]}"><a class="zoom" href="{E(media_url(it["src"]))}" data-full="{E(full)}">'
                     + img_tag(it["src"], media, media_url, alt, eager="high" if it["n"] == 1 else it["n"] <= 4 and "eager", sizes=sizes, tile=True)
                     + f'</a><figcaption>{E(it["caption"])}</figcaption></figure>')
    controls = (f'<div class="b gbar"><span>{len(items)} images</span>'
                f'<button class="btn" id="play" data-timer="{timer}" type="button">▶ Play slideshow</button></div>' if items else "")
    return ((f'<div class="b prose">{"".join(intro)}</div>' if intro else "") + controls +
            f'<div class="{cls}" id="gallery">{"".join(tiles)}</div>')


# ------------------------------------------------------------------ assets
def write_assets(out, root):
    src = os.path.join(root, "assets")
    dst = os.path.join(out, "assets")
    shutil.copytree(src, dst, dirs_exist_ok=True)
    for name in ("site.css", "site.js", "gallery.js"):
        p = os.path.join(dst, name)
        if os.path.exists(p):
            ASSET_VER["/assets/" + name] = hashlib.md5(open(p, "rb").read()).hexdigest()[:8]
    for name in ("favicon.svg", "favicon.ico", "apple-touch-icon.png", "icon-192.png", "icon-512.png", "logo.png", "og-image.png",
                 "site.webmanifest", "robots.txt", "CNAME", ".nojekyll"):
        sp = os.path.join(root, "static", name)
        if os.path.exists(sp):
            shutil.copy(sp, os.path.join(out, name))
    vendor = os.environ.get("MOCA_RUFFLE", "/home/user/work/out/vendor/ruffle")
    if os.path.isdir(vendor):
        shutil.copytree(vendor, os.path.join(out, "vendor", "ruffle"), dirs_exist_ok=True)


def write_meta(out, pages, site_url, write):
    # search index: title, url, section (loaded only when someone opens search)
    dup = lambda p: p["url"].startswith("/donnie(s)/")  # mirror of the /donnieYYYY/ folders
    import rebrand
    idx = [[rebrand.clean(p["title"]), p["url"], p["section"]] for p in pages if p.get("title") and not dup(p)]
    with open(os.path.join(out, "search.json"), "w") as f:
        json.dump(idx, f, separators=(",", ":"))
    seo_finish(out, site_url, os.path.join(os.path.dirname(os.path.abspath(out)), "build", "lastmod.json"))


def _main(doc):
    m = re.search(r'<main id="main".*?</main>', doc, re.S)
    return m.group(0) if m else ""


def seo_finish(out, site_url, state_path, today=None):
    """Run once every page is written. Pages that duplicate another page (x.htm next to an
    identical x.html, the /donnie(s)/ mirror, "folder copy/" folders) get a rel=canonical
    pointing at the original. Then the sitemap lists every indexable page by its canonical URL,
    with a lastmod date that only changes when the page's content changes (kept in state_path)."""
    today = today or time.strftime("%Y-%m-%d")
    paths = {}
    for d, _, fs in os.walk(out):
        for f in fs:
            if f.endswith((".htm", ".html")):
                full = os.path.join(d, f)
                paths["/" + os.path.relpath(full, out).replace(os.sep, "/")] = full
    docs = {u: open(p, encoding="utf-8").read() for u, p in paths.items()}
    inbound = Counter(html.unescape(h) for doc in docs.values() for h in re.findall(r'<a [^>]*?href="(/[^"#?]*)', doc))

    def similar(a, b):
        wa, wb = (re.sub(r"<[^>]+>", " ", _main(docs[x])).split() for x in (a, b))
        return difflib.SequenceMatcher(None, wa, wb, autojunk=False).ratio() >= 0.9

    dup_of = {}
    for u in sorted(docs):
        if NOINDEX.match(u):
            continue
        if u.endswith(".htm") and u + "l" in docs and similar(u, u + "l"):
            a, b = u, u + "l"
            keep = max((a, b), key=lambda x: (inbound[x], x.endswith(".htm")))
            dup_of[b if keep == a else a] = keep
        m = re.match(r"(.*?)(?: copy(?: \d+)?| \d| \(\d+\))(/.*)$", u)  # "folder copy/", "folder 2/", "folder (1)/" (Finder duplicates)
        if m and m.group(1) + m.group(2) in docs and similar(u, m.group(1) + m.group(2)):
            dup_of[u] = m.group(1) + m.group(2)
        if u.startswith("/donnie(s)/") and "/" + u[len("/donnie(s)/"):] in docs:
            dup_of[u] = "/" + u[len("/donnie(s)/"):]

    def final(u):
        seen = set()
        while u in dup_of and u not in seen:
            seen.add(u)
            u = dup_of[u]
        return u

    for u in dup_of:
        canon = E(site_url + canonical_path(final(u)))
        doc = re.sub(r'<link rel="canonical" href="[^"]*">', f'<link rel="canonical" href="{canon}">', docs[u], count=1)
        doc = re.sub(r'<meta property="og:url" content="[^"]*">', f'<meta property="og:url" content="{canon}">', doc, count=1)
        if doc != docs[u]:
            docs[u] = doc
            with open(paths[u], "w", encoding="utf-8") as f:
                f.write(doc)

    try:
        with open(state_path) as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}
    entries = {}
    for u in sorted(docs):
        doc = docs[u]
        hd = doc.split("</head>", 1)[0]
        m = re.search(r'<link rel="canonical" href="([^"]*)">', hd)
        if not m or 'name="robots" content="noindex' in hd:
            continue
        loc = html.unescape(m.group(1))
        if loc != site_url + canonical_path(u):
            continue
        t = re.search(r"<title>(.*?)</title>", hd, re.S)
        h = hashlib.md5(((t.group(1) if t else "") + _main(doc)).encode("utf-8")).hexdigest()[:12]
        old = state.get(loc)
        entries[loc] = [h, old[1] if old and old[0] == h else today]
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w") as f:
        json.dump(entries, f, indent=0, sort_keys=True)
    locs = sorted(entries)
    for name in os.listdir(out):
        if re.fullmatch(r"sitemap-\d+\.xml", name):
            os.remove(os.path.join(out, name))
    chunks = [locs[i:i + 40000] for i in range(0, len(locs), 40000)]  # the limit is 50,000 per file
    for i, chunk in enumerate(chunks, 1):
        with open(os.path.join(out, f"sitemap-{i}.xml"), "w") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
            f.write("".join(f"<url><loc>{E(u)}</loc><lastmod>{entries[u][1]}</lastmod></url>\n" for u in chunk))
            f.write("</urlset>\n")
    with open(os.path.join(out, "sitemap.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        f.write("".join(f"<sitemap><loc>{site_url}/sitemap-{i}.xml</loc><lastmod>{max(entries[u][1] for u in c)}</lastmod></sitemap>\n"
                        for i, c in enumerate(chunks, 1)))
        f.write("</sitemapindex>\n")
    return dup_of
