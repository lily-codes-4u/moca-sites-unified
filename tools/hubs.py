"""Homepage, section hubs, directory and helper pages for the unified MOCA site."""
import html
import json
import os
import posixpath
import re
from collections import defaultdict

import templates as T

E = html.escape

GRANDMASTERS = [
    ("Alessandro Bavari", "bavari/bavari01.htm"), ("Peter Ciccariello", "ciccariello/ciccariello01.htm"),
    ("Andrew Cole", "open/cole/cole.htm"), ("Vincenzo Corrado", "autogallery2012/autogallery_corrado/"),
    ("Bjoern Daempfling", "daempfling/damp01.htm"), ("Thomas Demuth", "demuth/demuth01.htm"),
    ("Lisle Drake", "drake/drake01.htm"), ("Bernard Dumaine", "open/dumaine/dumaine.htm"),
    ("Werner Hornung", "hornung/hornung01.htm"), ("Dolores Glover Kaufman", "kaufman_new/kaufman01.htm"),
    ("Karin Kuhlmann", "kuhlmann1/kuhl01.htm"), ("Peter Mc Lane", "mclane/mclane01.htm"),
    ("Janet Parke", "parke/parke01.htm"), ("Helga Schmitt", "autogallery/autogallery_schmitt/"),
    ("Renata Spiazzi", "open/spiazzi/spiazzi01.htm"), ("Jay Wilson", "wilson/wilson01.htm"),
    ("Shige Yamada", "yamada/yamada01.htm"),
]
GALLERIES = [
    ("Photo-based", "newmoca/photo.asp"), ("Drawn & Painted", "newmoca/drawn.asp"), ("3D Rendered", "newmoca/3d.asp"),
    ("Algorithmic & Fractal", "newmoca/algorithmic.asp"), ("Mixed Technique", "newmoca/mixedtech.asp"),
    ("Surreal", "newmoca/surreal.htm"), ("Video & Audio", "newmoca/newmediamain.asp"), ("Projects", "newmoca/projects.htm"),
    ("Guest Gallery", "newmoca/guestgallery.htm"), ("Open Gallery", "open/opengallery.htm"),
]
POLICY = ["No charge to viewers.", "No charge to artists.", "No advertising.", "No Facebook or Meta.", "No Twitter or X."]


def build_all(results, files, media, media_url, write, site_url):
    by_path = {r["path"]: r for r in results}
    by_url = {r["url"]: r for r in results}
    ctx = dict(by_path=by_path, by_url=by_url, files=files, media=media, media_url=media_url, site_url=site_url)

    def url_of(p):
        if p.endswith("/"):
            return "/" + p
        r = by_path.get(p)
        return r["url"] if r else None

    def card(p, title=None, sub=None):
        r = by_path.get(p) or by_url.get("/" + p if p.endswith("/") else "")
        if not r:
            return ""
        img = r.get("first_img")
        if not img:  # index pages: borrow the first artwork from the pages they link to
            for kind, v in r.get("links", []):
                t = by_url.get(v.split("#")[0]) if kind == "page" else None
                if t and t.get("first_img"):
                    img = t["first_img"]
                    break
        pic = (T.img_tag(img, media, media_url, "", sizes="(max-width:640px) 50vw, 220px") if img else
               f'<span class="ph" aria-hidden="true">{E((title or r["title"])[:1])}</span>')
        if img:
            pic = pic.replace("<img ", '<img class="cimg" ', 1)
        return (f'<a class="card" href="{E(r["url"])}">{pic}<div><h3>{E(title or r["title"])}</h3>'
                f'<p>{E(sub or r["section"])}</p></div></a>')

    def hub(url, title, body, color="c1", desc="", active=None):
        page = T.page(title=title, url=url, section=("Home", color, "/"), body=body, desc=desc, site_url=site_url, active=active, crumb=False)
        write(url, page)

    # ---------------------------------------------------------- Donnie
    years = sorted({int(m.group(1)) for p in files for m in [re.match(r"donnie(\d{4})/", p)] if m}, reverse=True)
    dn_cards, dn_list = [], []
    for y in years:
        pages = sorted(r for r in by_path if r.startswith(f"donnie{y}/") and r.count("/") == 1)
        main = next((p for p in (f"donnie{y}/main.htm", f"donnie{y}/winners.htm", f"donnie{y}/winners{y}.htm", f"donnie{y}/exhibitpages/exhibitindex.htm", f"donnie{y}/catalog{y}.htm") if p in by_path), pages[0] if pages else None)
        if not main:
            continue
        dn_cards.append(card(main, f"The Donnie {y}", f"{sum(1 for r in by_path if r.startswith(f'donnie{y}/'))} pages"))
        links = "".join(f'<a href="{E(by_path[p]["url"])}">{E(by_path[p]["title"])}<span>{E(posixpath.basename(p))}</span></a>' for p in pages)
        ex = f"donnie{y}/exhibitpages/exhibitindex.htm"
        if ex in by_path and ex not in pages:
            links += f'<a href="{E(by_path[ex]["url"])}">Exhibit index<span>all entries</span></a>'
        dn_list.append(f'<div class="list" id="y{y}"><h2>{y}</h2>{links}</div>')
    body = (f'<div class="b prose"><p>The Donnie is MOCA\'s yearly digital art contest, running for more than a quarter century. '
            f'Every surviving exhibit, winners page and catalog from {years[-1]} to {years[0]} is here.</p>'
            f'<p><a href="/donniearchive.htm">Donnie archive</a> · <a href="/catalogs.htm">All catalogs</a></p></div>'
            f'<div class="cards">{"".join(dn_cards)}</div><h2 class="sec">Every Donnie page</h2><div class="cols">{"".join(dn_list)}</div>')
    hub("/donnie.html", "The Donnie", body, "c2", "Every Donnie digital art contest exhibit, winners list and catalog.", "/donnie.html")

    # ---------------------------------------------------------- AI art
    ai_groups = [
        ("AI collections", sorted(p for p in by_path if p.startswith("aicollections/"))),
        ("Portraits and places", sorted(p for p in by_path if p.startswith("ailoves/"))),
        ("Fabricated AI portraits", sorted(p for p in by_path if p.startswith("aifabfaces/"))),
        ("AI exhibits and slideshows", [p for p in ("aiexhibits.htm", "artforartssake.htm", "imageofthedayindexai.htm") if p in by_path]),
        ("Images of the Day (AI)", sorted(p for p in by_path if re.match(r"imagesoftheday\d+ai\.htm$", p))),
    ]
    other_ai = sorted(p for p in by_path if re.match(r"ai[a-z0-9]*/", p) and not p.startswith(("aicollections/", "ailoves/", "aifabfaces/")))
    ai_groups.append(("More AI galleries", other_ai))
    body = ('<div class="b prose"><p>Don Archer\'s art made with artificial intelligence, first shown on mocadigitalart.com: '
            'collections, portraits, the Doodles, images of the day and yearly exhibits.</p>'
            '<p><a href="/autogallery2023/autogallery_doodles/">Doodle slideshow</a> · <a href="/index.htm">The original mocadigitalart.com front page</a></p></div>')
    for name, ps in ai_groups:
        if ps:
            body += f'<h2 class="sec">{E(name)}</h2><div class="cards">{"".join(card(p) for p in ps)}</div>'
    hub("/ai.html", "AI Art", body, "c5", "Don Archer's AI art collections, portraits and exhibits.", "/ai.html")

    # ---------------------------------------------------------- Collection
    body = '<div class="cards">' + "".join(card(p, t, "Gallery") for t, p in GALLERIES) + "</div>"
    body += '<h2 class="sec">Grandmasters</h2><div class="cards">' + "".join(card(p if not p.endswith("/") else p, n, "Grandmaster") for n, p in GRANDMASTERS) + "</div>"
    body += ('<h2 class="sec">Also in the collection</h2><div class="cards">'
             + "".join(card(p) for p in ("autogalleryarchive.htm", "grandmasters.htm", "mocanet/mocalist.htm", "editorial/editorial.htm", "adon/abase.asp", "digivid/brown_valleys.htm") if p in by_path)
             + "</div>")
    hub("/collection.html", "The collection", body, "c1", "Browse MOCA's galleries: photo-based, drawn, 3D, fractal, mixed, surreal, video and more.", "/collection.html")

    # ---------------------------------------------------------- Artists (from the gallery index pages)
    artists = {}
    for _, gp in GALLERIES + [("", "grandmasters.htm"), ("", "autogalleryarchive.htm"), ("", "mocanet/mocalist.htm")]:
        r = by_path.get(gp)
        if not r:
            continue
        raw = open(os.path.join(os.environ.get("MOCA_MERGED", "/home/user/work/merged"), gp), "rb").read().decode("latin-1")
        for m in re.finditer(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', raw, re.S | re.I):
            label = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
            href = m.group(1)
            if not label or len(label) > 60 or href.startswith(("http", "mailto")) or re.search(r"home|index|gallery|archive|moca|submit|donate|^\W+$", label, re.I):
                continue
            from legacy import Ctx, norm_internal
            kind, val = norm_internal(href, Ctx(gp, lambda x: x in files, {p.rsplit("/", 1)[0] for p in files if p.endswith("/index.asp") and "autogallery" in p}))
            if kind == "page":
                artists.setdefault(label, val)
    names = sorted(artists, key=lambda n: (n.split()[-1].lower() if n.split() else n.lower()))
    groups = defaultdict(list)
    for n in names:
        key = (n.split()[-1][:1] if n.split() else n[:1]).upper()
        groups[key if key.isalpha() else "#"].append(n)
    az = "".join(f'<a href="#l-{k}">{k}</a>' for k in sorted(groups))
    lists = "".join(f'<div class="list" id="l-{k}"><h2>{k}</h2>' + "".join(f'<a href="{E(artists[n])}">{E(n)}</a>' for n in groups[k]) + "</div>" for k in sorted(groups))
    body = (f'<div class="b prose"><p>{len(names)} artists and exhibits linked from MOCA\'s gallery pages, sorted by last word of the name. '
            f'Use search (press /) to find anyone else, or browse the <a href="/directory/">complete directory of every page</a>.</p></div>'
            f'<nav class="az" aria-label="Jump to letter">{az}</nav><div class="cols">{lists}</div>')
    hub("/artists.html", "Artists", body, "c4", "Every artist exhibited at MOCA, A to Z.", "/artists.html")

    # ---------------------------------------------------------- Archive + directory
    tops = defaultdict(list)
    for r in results:
        top = r["path"].split("/")[0] if "/" in r["path"] else "(museum pages)"
        tops[top].append(r)
    dir_links = []
    for top in sorted(tops, key=str.lower):
        rs = sorted(tops[top], key=lambda r: r["path"])
        slug = re.sub(r"[^a-z0-9_\-]+", "-", top.lower()).strip("-") or "museum"
        items = "".join(f'<a href="{E(r["url"])}">{E(r["title"])}<span>{E(r["path"])}</span></a>' for r in rs)
        body = f'<div class="b prose"><p>All {len(rs)} pages in this part of the museum.</p></div><div class="list">{items}</div>'
        page = T.page(title=f"Directory: {top}", url=f"/directory/{slug}.html", section=("Directory", "c3", "/directory/"),
                      body=body, site_url=site_url, desc=f"Every page under {top}.")
        write(f"/directory/{slug}.html", page)
        dir_links.append(f'<a href="/directory/{slug}.html">{E(top)}<span>{len(rs)}</span></a>')
    third = (len(dir_links) + 2) // 3
    cols = "".join(f'<div class="list">{"".join(dir_links[i:i + third])}</div>' for i in range(0, len(dir_links), third))
    body = (f'<div class="b prose"><p>Every one of the {len(results):,} pages from moca.virtual.museum and mocadigitalart.com, grouped by the folder it lived in on the old sites. Files that no page showed are in <a href="/unlisted/">Unlisted files</a>.</p></div>'
            f'<div class="cols">{cols}</div>')
    write("/directory/", T.page(title="Directory of every page", url="/directory/", section=("Archive", "c3", "/archive.html"), body=body, site_url=site_url))

    arch = [p for p in ("autogalleryarchive.htm", "donniearchive.htm", "catalogs.htm", "imageofthedayindex.htm", "imageofthedayindexai.htm",
                        "editorial/editorial.htm", "mocanet/mocalist.htm", "grandmasters.htm", "aiexhibits.htm", "adon/abase.asp") if p in by_path]
    ag = sorted({r["url"] for r in results if r.get("autogallery")})
    ag_years = defaultdict(list)
    for r in results:
        if r.get("autogallery"):
            y = re.match(r"/autogallery(\d{4})?", r["url"]).group(1) or "classic"
            ag_years[y].append(r)
    ag_html = "".join(f'<div class="list"><h2>AutoGallery {y}</h2>' + "".join(f'<a href="{E(r["url"])}">{E(r["title"])}<span>{len(r["images"])} images</span></a>' for r in sorted(rs, key=lambda r: r["url"])) + "</div>"
                      for y, rs in sorted(ag_years.items(), reverse=True))
    legacy_homes = "".join(f'<a href="{u}">{t}</a>' for u, t in (("/index.htm", "mocadigitalart.com front page (2024)"), ("/legacy/moca-virtual-museum-home.html", "moca.virtual.museum front page (2024)")))
    body = (f'<div class="b prose"><p>Archives, indexes and catalogs from both former MOCA websites. For a list of absolutely every page, see the <a href="/directory/">directory</a>.</p>'
            f'<p class="links">{legacy_homes}<a href="/unlisted/">Unlisted files (shown on no page)</a></p></div>'
            f'<div class="cards">{"".join(card(p) for p in arch)}</div>'
            f'<h2 class="sec">AutoGallery, {len(ag)} galleries</h2><div class="cols">{ag_html}</div>')
    hub("/archive.html", "Archive", body, "c3", "MOCA archives: AutoGallery, the Donnie, catalogs, images of the day, editorial.", "/archive.html")

    # ---------------------------------------------------------- Submit (the ASP upload forms are retired)
    body = ('<div class="b prose"><h2>Show your art at MOCA</h2><p>MOCA has never charged artists or viewers. '
            'The old upload forms ran on the previous web server and are retired. To submit work for the AutoGallery, the Open Gallery or the Donnie, '
            'email up to 10 images (JPEG, longest side about 1600 pixels) with your name, titles and a short statement to '
            '<a href="mailto:don@moca.virtual.museum?subject=Art%20submission">don@moca.virtual.museum</a>.</p>'
            '<p><a href="/autogallerysubmit.html">The previous submission guidelines</a> are kept for reference.</p></div>')
    hub("/submit.html", "Submit your art", body, "c3", "How to show your digital art at MOCA, free.")

    # ---------------------------------------------------------- files no page shows
    extra = build_unlisted(results, media, media_url, write, site_url)
    # ---------------------------------------------------------- Home
    build_home(ctx, write, years, card)
    build_404(write, results, files, site_url)
    return extra


def build_unlisted(results, media, media_url, write, site_url):
    """Every image, video, Flash file and document that no page displays still gets a home,
    so nothing from the old servers is only reachable by guessing its URL."""
    shown = set()
    for r in results:
        shown.update(r.get("images", []))
        shown.update(v for k, v in r.get("links", []) if k == "media")
    groups = defaultdict(list)
    for p, m in media.items():
        if p in shown or m.get("type") in ("other", None) or m.get("error"):
            continue
        groups[p.split("/")[0] if "/" in p else "(top level)"].append(p)
    pages, links = [], []
    for top in sorted(groups, key=str.lower):
        ps = sorted(groups[top])
        slug = re.sub(r"[^a-z0-9_\-]+", "-", top.lower()).strip("-") or "top"
        tiles, others = [], []
        for p in ps:
            m = media[p]
            name = posixpath.basename(p)
            if m["type"] == "image":
                full = media_url(p, "1600") if (m.get("variants") or {}).get("1600") and not m.get("animated") else media_url(p)
                tiles.append(f'<figure class="art"><a class="zoom" href="{E(media_url(p))}" data-full="{E(full)}">'
                             + T.img_tag(p, media, media_url, name, sizes="(max-width: 640px) 50vw, 260px")
                             + f'</a><figcaption>{E(p)}</figcaption></figure>')
            else:
                kind = m["type"]
                b = {"t": "media", "src": p, "kind": "flash" if kind == "flash" else "video" if kind == "video" else "audio" if kind == "audio" else "other"}
                others.append(f'<div><p class="note">{E(p)}</p>{T.media_block(b, media_url, media)}</div>')
        body = (f'<div class="b prose"><p>{len(ps)} files from the <b>{E(top)}</b> folder of the old servers that no page displayed. '
                f'They are kept here so that every file from both sites can be seen.</p></div>'
                + (f'<div class="wall">{"".join(tiles)}</div>' if tiles else "") + "".join(others))
        url = f"/unlisted/{slug}.html"
        write(url, T.page(title=f"Unlisted files: {top}", url=url, section=("Archive", "c3", "/archive.html"), body=body,
                          site_url=site_url, desc=f"Files from {top} on the old MOCA servers that no page displayed."))
        pages.append({"path": f"unlisted/{slug}", "url": url, "title": f"Unlisted files: {top}", "section": "Archive",
                      "images": ps, "links": [], "dropped": [], "text_chars": 0, "words": [], "unlisted": True})
        links.append(f'<a href="{url}">{E(top)}<span>{len(ps)}</span></a>')
    third = (len(links) + 2) // 3 or 1
    cols = "".join(f'<div class="list">{"".join(links[i:i + third])}</div>' for i in range(0, len(links), third))
    total = sum(len(v) for v in groups.values())
    body = (f'<div class="b prose"><p>{total:,} images, videos and other files were stored on the old MOCA servers without any page showing them '
            f'(earlier versions, spare sizes, works that were taken down from a page). Here they are, by folder.</p></div><div class="cols">{cols}</div>')
    write("/unlisted/", T.page(title="Unlisted files", url="/unlisted/", section=("Archive", "c3", "/archive.html"), body=body, site_url=site_url))
    return pages


def build_home(ctx, write, years, card):
    by_path, media, media_url = ctx["by_path"], ctx["media"], ctx["media_url"]

    def img(p, sizes, eager=False):
        if not p or p not in ctx["files"]:
            return ""
        return T.img_tag(p, media, media_url, "", eager=eager, sizes=sizes)

    feat = by_path.get("polushkin/polushkin01.htm")
    feat_img = feat["first_img"] if feat else None
    doodles = sorted(p for p in ctx["files"] if p.startswith("autogallery2023/autogallery_doodles/") and p.endswith(".jpg"))
    ai_img = "aiartsake27/crucifixion 1.jpg"
    gm_names = ", ".join(n for n, _ in GRANDMASTERS[:7]) + "…"
    yrs = "".join(f'<a href="/donnie.html#y{y}">{y}</a>' for y in years[:8]) + f'<a href="/donnie.html">+{max(0, len(years) - 8)}</a>'
    pol = "".join(f"<span>{E(p)}</span>" for p in POLICY)
    n_pages = len(by_path)
    n_imgs = sum(1 for p in ctx["files"] if p.endswith((".jpg", ".jpeg", ".gif", ".png")))
    doodle_data = E(json.dumps([media_url(p, "480") for p in doodles[:120]]))
    hero = f"""
<div class="bento">
  <div class="b hero"><span class="k">Museum of Computer Art · est. 1993</span><div><h1>Digital art, all of it, in one place.</h1></div>
    <p>Photo-based, fractal, rendered, painted, surreal, video and AI. Thousands of artists, {n_pages:,} pages and {n_imgs:,} images. Free to view, free to exhibit.</p></div>
  <a class="b feat over" href="/polushkin/polushkin01.htm">{img(feat_img, "(max-width:1040px) 100vw, 50vw", True)}<span class="k">Featured exhibit</span><div><h2 style="font-size:30px">Andrew Polushkin</h2><p>Photo manipulation · St. Petersburg</p></div></a>
  <div class="b free"><b>$0</b><p>to view or exhibit. Ever.</p></div>
  <a class="b sub" href="/submit.html"><span class="k">Artists</span><h2 style="font-size:22px">Submit your art →</h2></a>
  <a class="b ai over" href="/ai.html">{img(ai_img, "(max-width:640px) 100vw, 33vw")}<span class="k">AI Art · Don Archer</span><div><h2 style="font-size:28px">15 AI collections</h2><p>From Pre-Columbian to Westward Ho!</p></div></a>
  <div class="b donnie"><span class="k">Yearly contest</span><div><h2 style="font-size:34px"><a href="/donnie.html">The Donnie</a></h2><p>Every exhibit and winners list, {years[-1]} to {years[0]}, and all 31 catalogs.</p></div><div class="yrs">{yrs}</div></div>
  <a class="b doodle" href="/autogallery2023/autogallery_doodles/" data-doodles="{doodle_data}">{img(doodles[0] if doodles else None, "(max-width:640px) 100vw, 33vw")}<div class="lbl"><span class="k">Doodles</span><span class="k">{len(doodles)} AI playthings</span></div><span class="btn go">Slideshow →</span></a>
  <a class="b gm" href="/grandmasters.htm"><span class="k">{len(GRANDMASTERS)} Grandmasters</span><div class="n">{E(gm_names)}</div><p>Artists MOCA celebrates →</p></a>
  <div class="b about"><div style="flex:1;min-width:0"><span class="k" style="color:var(--muted)">About</span><p style="margin-top:6px">A 501(c)(3) nonprofit founded by Don Archer and Bob Dodson, chartered by the NYS Department of Education.</p></div><a href="/about.htm" style="font-weight:700;white-space:nowrap">Our story →</a></div>
  <div class="b pol">{pol}</div>
</div>"""
    galleries = '<h2 class="sec" id="collection">Browse the collection</h2><div class="cards">' + "".join(card(p, t, "Gallery") for t, p in GALLERIES) + "</div>"
    dc = directors_choice(ctx)
    dc_html = ('<h2 class="sec">Director\'s choice</h2><div class="cards">' + "".join(dc) + "</div>") if dc else ""
    lists = ('<h2 class="sec">Contests, artists and archives</h2><div class="cols">'
             f'<div class="list"><h2>The Donnie</h2>' + "".join(f'<a href="/donnie.html#y{y}">Donnie {y}<span>exhibit</span></a>' for y in years[:6]) + '<a href="/catalogs.htm">All catalogs<span>Blurb</span></a></div>'
             '<div class="list"><h2>Grandmasters</h2>' + "".join(f'<a href="/{p if p.endswith("/") else by_path[p]["url"].lstrip("/") if p in by_path else p}">{E(n)}<span>Grandmaster</span></a>' for n, p in GRANDMASTERS[:7]) + '<a href="/grandmasters.htm">All grandmasters<span>17</span></a></div>'
             '<div class="list"><h2>Archives</h2><a href="/autogalleryarchive.htm">AutoGallery archive<span>2008–2024</span></a><a href="/donniearchive.htm">Donnie archive<span></span></a>'
             '<a href="/imageofthedayindex.htm">Images of the Day<span></span></a><a href="/editorial/editorial.htm">Reviews &amp; essays<span></span></a><a href="/mocanet/mocalist.htm">MOCAnet artist sites<span></span></a><a href="/directory/">Every page, A to Z<span></span></a></div></div>')
    body = hero + galleries + dc_html + lists
    html_ = T.head("MOCA · Museum of Computer Art", "/", "The Museum of Computer Art: digital fine art since 1993. Galleries, AI art, the Donnie contest and decades of archives, free to view.",
                   media_url(feat_img, "1600") if feat_img else None, ctx["site_url"]) + T.header("/") + f'\n<main id="main" class="wrap">{body}</main>\n' + T.FOOTER
    html_ = T.finalize(html_.replace("</body>", '<script>(function(){var t=document.querySelector(".doodle");if(!t||!window.IntersectionObserver||matchMedia("(prefers-reduced-motion: reduce)").matches)return;var l=JSON.parse(t.dataset.doodles||"[]"),i=0,im=t.querySelector("img"),vis=false,tm=null;if(!im||l.length<2)return;function tick(){if(!vis||document.hidden)return;i=(i+1)%l.length;var n=new Image();n.onload=function(){im.removeAttribute("srcset");im.src=n.src};n.src=l[i]}function sync(){clearInterval(tm);tm=(vis&&!document.hidden)?setInterval(tick,4000):null}new IntersectionObserver(function(e){vis=e[0].isIntersecting;sync()}).observe(t);document.addEventListener("visibilitychange",sync)})();</script>\n</body>'))
    write("/", html_)


def directors_choice(ctx):
    picks = ["prystrom/prystrom01.htm", "open/santos_t/santos_t03.htm", "open/baar/baar02.htm", "open/castellano/castellano08.htm",
             "open/broadfoot/broadfoot04.htm", "open/marini/marini03.htm", "open/ammel/ammel09.htm", "guest/bahreini/bahreini01.htm",
             "benshoshan/benshoshan01.htm", "open/lee/lee01.htm", "guest/mccoy/mccoy07.htm", "harvey/harvey01.htm",
             "kwakman/kwakman01.htm", "open/castile/castile01.htm", "yakovina/yakovina07.htm", "camlica/camlica01.htm",
             "caputo/caputo01.htm", "dicicco/dicicco00.htm", "mclane/mclane01.htm", "drake/drake01.htm", "melnichuk/melnichuk01.htm",
             "lamagni/lamagn00.htm", "open/lindsay/lindsay05.htm", "csuri/csuri01.htm", "open/locking/locking03.htm", "marchetti/marchetti01.htm"]
    out = []
    for p in picks:
        r = ctx["by_path"].get(p)
        if not r or not r.get("first_img"):
            continue
        out.append(f'<a class="card" href="{E(r["url"])}">' + T.img_tag(r["first_img"], ctx["media"], ctx["media_url"], r["title"], sizes="(max-width:640px) 50vw, 220px")
                   + f'<div><h3>{E(r["title"])}</h3><p>{E(r["section"])}</p></div></a>')
    return out


def build_404(write, results, files, site_url):
    """GitHub Pages serves 404.html for unknown paths. It redirects old URLs: mixed case,
    .asp links, old AutoGallery image links and the old domains' paths."""
    known = sorted({r["url"].split("#")[0] for r in results})
    body = ('<div class="b prose" id="nf"><h2>Looking for something from the old MOCA sites?</h2>'
            '<p>We could not find that page. Everything from moca.virtual.museum and mocadigitalart.com now lives here. '
            'Try the <a href="/directory/">directory of every page</a>, the <a href="/artists.html">artist list</a>, or search (press /).</p></div>')
    page = T.page(title="Page not found", url="/404.html", section=("Home", "c2", "/"), body=body, site_url=site_url, crumb=False)
    js = r"""<script>(function(){var p=location.pathname,q=location.search,h=location.hash;var l=decodeURIComponent(p).toLowerCase();
var m=l.match(/^(.*)\/index_q_mode-view-image-(\d+)-returnpage-\d+\.html?$/);if(m){location.replace(m[1]+"/#image-"+m[2]);return}
var c=[];if(l!==decodeURIComponent(p))c.push(l);
if(/\.aspx?$/.test(l))c.push(l.replace(/\.aspx?$/,".html"));
if(/\.html$/.test(l)){c.push(l.replace(/\.html$/,".htm"))}else if(/\.htm$/.test(l)){c.push(l.replace(/\.htm$/,".html"))}
if(/\/index\.(asp|html?)$/.test(l))c.push(l.replace(/index\.(asp|html?)$/,""));
if(!/\.[a-z0-9]{2,5}$/.test(l)&&!/\/$/.test(l))c.push(l+"/");
var known=null;function go(i){if(i>=c.length)return;var u=c[i];if(u===p)return go(i+1);
fetch(u,{method:"HEAD"}).then(function(r){if(r.ok)location.replace(u+(/image=(\d+)/i.test(q)?"#image-"+q.match(/image=(\d+)/i)[1]:h));else go(i+1)}).catch(function(){go(i+1)})}go(0)})();</script>"""
    write("/404.html", page.replace("</body>", js + "\n</body>"))
