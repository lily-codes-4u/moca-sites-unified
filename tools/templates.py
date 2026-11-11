"""HTML templates for the unified MOCA site (Bento design, prototype 3)."""
import hashlib
import html
import json
import os
import re
import shutil

E = html.escape
NAV = [("/collection.html", "Collection"), ("/ai.html", "AI Art"), ("/donnie.html", "The Donnie"),
       ("/artists.html", "Artists"), ("/archive.html", "Archive"), ("/about.htm", "About")]
NAV_TEXT = re.compile(r"^((back to |to )?top( of page)?|next( page| image)?|previous( page| image)?|prev|back|go back|home|moca home|main page|index|top|return( to.*)?|"
                      r"moca|museum of computer art|mocadigitalart|moca\.virtual\.museum|forward|>>|<<|>|<|\d{1,3})$", re.I)
ASSET_VER = {}


def asset(path):
    return path + ("?v=" + ASSET_VER[path] if path in ASSET_VER else "")


def head(title, url, desc, og_image, site_url, extra=""):
    canon = site_url + url.split("#")[0]
    full_title = title if title.startswith("MOCA") else f"{title} · MOCA"
    d = E((desc or "Museum of Computer Art: digital fine art since 1993.")[:300].strip())
    og = f'<meta property="og:image" content="{E(og_image)}">' if og_image else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{E(full_title)}</title>
<meta name="description" content="{d}">
<link rel="canonical" href="{E(canon)}">
<meta property="og:title" content="{E(full_title)}"><meta property="og:description" content="{d}"><meta property="og:url" content="{E(canon)}"><meta property="og:type" content="website">{og}
<meta name="theme-color" content="#3b5bfd">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="preload" href="/assets/fonts/bricolage.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/figtree.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{asset('/assets/site.css')}">
<link rel="preconnect" href="https://media.museumofcomputerart.org" crossorigin>
<script src="{asset('/assets/site.js')}" defer></script>{extra}
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
    <div><h2>Museum</h2><a href="/about.htm">About MOCA</a><a href="/submit.html">Submit your art</a><a href="/donate.htm">Donate</a><a href="mailto:don@moca.virtual.museum">don@moca.virtual.museum</a></div>
  </div>
  <p class="fine">© 1993–2026 Museum of Computer Art, a 501(c)(3) nonprofit. Images remain the property of the artists. Formerly moca.virtual.museum and mocadigitalart.com.</p>
</div></footer>
<dialog id="lb" aria-label="Image viewer"><button class="x" aria-label="Close">×</button><img alt=""><p class="cap"></p><a class="orig" href="#" target="_blank" rel="noopener">Open original file</a></dialog>
<dialog id="sd" aria-label="Search"><form method="dialog" class="sbox"><input id="q" type="search" placeholder="Search artists, exhibits, titles…" autocomplete="off" aria-label="Search"><button class="x" aria-label="Close">×</button></form><ol id="res"></ol></dialog>
</body>
</html>"""


def page(title, url, section, body, desc="", og_image=None, site_url="", scripts=(), active=None, crumb=True):
    sec_name, color, sec_url = section
    extra = "".join(f'\n<script src="{asset(s)}" defer></script>' for s in scripts)
    crumbs = (f'<nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a><span>/</span><a href="{E(sec_url)}">{E(sec_name)}</a></nav>'
              if crumb else "")
    return (head(title, url, desc, og_image, site_url, extra) + header(active) +
            f"""
<main id="main" class="wrap">
<div class="phead b {color}">{crumbs}<h1>{E(title)}</h1></div>
{body}
</main>
""" + FOOTER)


# ------------------------------------------------------------------ blocks
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


def short_para(b):
    return b and b["t"] == "p" and 0 < len(b["text"]) <= 160 and b["html"].count("<a ") <= 1 and not b.get("used")


def link_dense(b):
    n = b["html"].count("<a ")
    if n < 4:
        return False
    a_text = sum(len(re.sub(r"<[^>]+>", "", x)) for x in re.findall(r"<a [^>]*>(.*?)</a>", b["html"], re.S))
    return a_text >= 0.5 * max(1, len(b["text"]))


def fill_media(h, media_url):
    return re.sub(r"\{\{MEDIA:([^}]*)\}\}", lambda m: E(media_url(html.unescape(m.group(1)))), h)


def img_tag(path, media, media_url, alt, eager=False, sizes="(max-width: 700px) 100vw, 50vw", w=None, h=None):
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
        if "1600" in var:
            parts.append(f"{E(media_url(path, '1600'))} {min(1600, W or 1600)}w")
        srcset = f' srcset="{", ".join(parts)}" sizes="{sizes}"' if len(parts) > 1 else ""
    dims = f' width="{W}" height="{H}"' if W and H else ""
    load = ' fetchpriority="high"' if eager else ' loading="lazy"'
    return f'<img src="{E(src)}"{srcset}{dims}{load} decoding="async" alt="{E(alt)}">'


def link_href(link, media_url):
    kind, target = link
    if kind == "media":
        return media_url(target[1]), False
    if kind == "missing":
        return None, False
    return target, kind == "external"


def figure(b, media_url, media, caption="", eager=False, big=False):
    path = b.get("src")
    alt = b.get("alt") or re.sub(r"<[^>]+>", "", caption)[:120]
    if b.get("ext"):
        tag = f'<img src="{E(b["ext"])}" loading="lazy" decoding="async" alt="{E(alt)}"' + (f' width="{b["w"]}" height="{b["h"]}"' if b.get("w") and b.get("h") else "") + ">"
        inner = tag
        full = b["ext"]
    else:
        sizes = "(max-width: 900px) 100vw, 66vw" if big else "(max-width: 640px) 50vw, (max-width: 1040px) 33vw, 25vw"
        inner = img_tag(path, media, media_url, alt, eager=eager, sizes=sizes, w=b.get("w"), h=b.get("h"))
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
        m = media.get(path or "") or {}
        disp = media_url(path, "1600") if (m.get("variants") or {}).get("1600") and not m.get("animated") else full
        a = f'<a class="zoom" href="{E(full)}" data-full="{E(disp)}">{inner}</a>'
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    return f'<figure class="art">{a}{cap}</figure>'


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
            for m in re.finditer(r'<a href="([^"]*)"[^>]*>(.*?)</a>', b["html"], re.S):
                label = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
                if re.match(r"^(moca|museum of computer art|mocadigitalart|moca\.virtual\.museum|home|main page)$", label, re.I):
                    label = "MOCA home"
                if re.match(r"^(back to |to )?top( of page)?$", label, re.I):
                    continue
                pager.append((html.unescape(m.group(1)), label))
        else:
            content.append(b)
    imgs = [i for i, b in enumerate(content) if b["t"] == "img" and not b.get("missing")]
    first_img = next((content[i]["src"] for i in imgs if content[i].get("src")), None)
    # caption direction
    before = sum(1 for i in imgs if i > 0 and short_para(content[i - 1]))
    after = sum(1 for i in imgs if i + 1 < len(content) and short_para(content[i + 1]))
    direction = "before" if before > after else "after"
    caps = {}
    for i in imgs:
        j = i - 1 if direction == "before" else i + 1
        if 0 <= j < len(content) and short_para(content[j]) and j not in imgs:
            # don't steal a caption that sits between two images on the "wrong" side
            caps[i] = content[j]["html"]
            content[j]["used"] = True
    out = []
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
        out.append('<div class="artwork">' + figure(content[i], media_url, media, cap, eager=True, big=True).replace('class="art"', 'class="art b"', 1)
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
                cls = "wall one" if len(run) == 1 else "wall"
                out.append(f'<div class="{cls}">' + "".join(run) + "</div>")
                run.clear()

        for k, b in enumerate(content):
            if b.get("used"):
                continue
            if b["t"] == "img":
                if b.get("missing"):
                    continue
                close_prose()
                run.append(figure(b, media_url, media, caps.get(k, ""), eager=first, big=(n_imgs <= 2)))
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
            if (href, label) in seen or not href:
                continue
            seen.add((href, label))
            cls = " next" if label.lower().startswith(("next", "forward")) else ""
            items.append(f'<a class="pill{cls}" href="{E(fill_media(href, media_url) if "{{" in href else href)}">{E(label)}</a>')
        out.append('<nav class="pager" aria-label="Exhibit navigation">' + "".join(items) + "</nav>")
    return "\n".join(x for x in out if x), first_img


def render_text(b, media_url, media):
    t = b["t"]
    if t == "p":
        h = fill_media(b["html"], media_url)
        h = re.sub(r'<a href="([^"]*)" data-missing="1">(.*?)</a>', r'<span class="dead" title="This link pointed to a page that was not in the backups">\2</span>', h, flags=re.S)
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
                'Please email <a href="mailto:don@moca.virtual.museum">don@moca.virtual.museum</a> instead.</p>')
    if t == "img":
        return figure(b, media_url, media) if (b.get("src") or b.get("ext")) else ""
    if t in ("media", "embed"):
        return media_block(b, media_url, media)
    return ""


def render_autogallery(items, header_blocks, message_blocks, cfg, media_url, media):
    intro = []
    for b in message_blocks + header_blocks:
        if is_nav_para(b):
            continue
        r = render_text(b, media_url, media)
        if r:
            intro.append(r)
    timer = re.sub(r"\D", "", cfg.get("SlideShowTimer", "4")) or "4"
    tiles = []
    for it in items:
        m = media.get(it["src"]) or {}
        full = media_url(it["src"], "1600") if (m.get("variants") or {}).get("1600") and not m.get("animated") else media_url(it["src"])
        tiles.append(f'<figure class="art" id="image-{it["n"]}"><a class="zoom" href="{E(media_url(it["src"]))}" data-full="{E(full)}">'
                     + img_tag(it["src"], media, media_url, it["caption"], eager=it["n"] <= 4)
                     + f'</a><figcaption>{E(it["caption"])}</figcaption></figure>')
    controls = (f'<div class="b gbar"><span>{len(items)} images</span>'
                f'<button class="btn" id="play" data-timer="{timer}" type="button">▶ Play slideshow</button></div>' if items else "")
    return ((f'<div class="b prose">{"".join(intro)}</div>' if intro else "") + controls +
            f'<div class="wall" id="gallery">{"".join(tiles)}</div>')


# ------------------------------------------------------------------ assets
def write_assets(out, root):
    src = os.path.join(root, "assets")
    dst = os.path.join(out, "assets")
    shutil.copytree(src, dst, dirs_exist_ok=True)
    for name in ("site.css", "site.js", "gallery.js"):
        p = os.path.join(dst, name)
        if os.path.exists(p):
            ASSET_VER["/assets/" + name] = hashlib.md5(open(p, "rb").read()).hexdigest()[:8]
    for name in ("favicon.svg", "robots.txt", "CNAME", ".nojekyll"):
        sp = os.path.join(root, "static", name)
        if os.path.exists(sp):
            shutil.copy(sp, os.path.join(out, name))
    vendor = os.environ.get("MOCA_RUFFLE", "/home/user/work/out/vendor/ruffle")
    if os.path.isdir(vendor):
        shutil.copytree(vendor, os.path.join(out, "vendor", "ruffle"), dirs_exist_ok=True)


def write_meta(out, pages, site_url, write):
    # search index: title, url, section (loaded only when someone opens search)
    idx = [[p["title"], p["url"], p["section"]] for p in pages if p.get("title")]
    with open(os.path.join(out, "search.json"), "w") as f:
        json.dump(idx, f, separators=(",", ":"))
    urls = sorted({p["url"].split("#")[0] for p in pages})
    for i in range(0, len(urls), 40000):
        chunk = urls[i:i + 40000]
        with open(os.path.join(out, f"sitemap-{i // 40000 + 1}.xml"), "w") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
            f.write("".join(f"<url><loc>{E(site_url + u)}</loc></url>\n" for u in chunk))
            f.write("</urlset>\n")
    n = (len(urls) - 1) // 40000 + 1
    with open(os.path.join(out, "sitemap.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        f.write("".join(f"<sitemap><loc>{site_url}/sitemap-{i + 1}.xml</loc></sitemap>\n" for i in range(n)))
        f.write("</sitemapindex>\n")
