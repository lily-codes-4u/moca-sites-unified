"""Duplicate content: one page per piece of content.

The old servers held many copies of the same page: the /donnie(s)/ mirror of the Donnie
folders, x.htm next to x.html, Finder copies ("folder copy/", "folder 2/", "folder (1)/"),
folders copied inside other folders (/autogallery2013/autogallery2012/, /holloway/donnie2023/,
/imagesoftheday/imagesoftheday07.htm next to /imagesoftheday07.htm), "indexx" drafts, and the
same Images of the Day issue saved under two numbers. Once every page is written, find() groups
the pages whose content (visible text and the set of media they show, where two media files with
the same bytes count as one) is the same or nearly the same, and keeps one page per group: the
most complete one, then the one most linked to, then the cleanest address. apply() then
- adds to that page anything a copy showed that the page lacks (no content is lost),
- replaces every copy with a small redirect page at the same address (old links keep working),
- points links at the kept page, and takes the copies out of the hub cards, the directory and
  the search index (the sitemap leaves them out because they are noindex).

Judgment calls live in tools/duplicates.tsv (see the header of that file).
"""
import difflib
import html
import json
import os
import posixpath
import re
from collections import Counter, defaultdict
from urllib.parse import quote, unquote

E = html.escape
HERE = os.path.dirname(os.path.abspath(__file__))
OVERRIDES = os.path.join(HERE, "duplicates.tsv")
TWINS = os.path.join(HERE, "media_twins.tsv")
MEDIA_HOST = "https://media.museumofcomputerart.org/"
VARIANT = re.compile(r"(\.[A-Za-z0-9]{2,5})\.(w480\.webp|w800\.webp|w1600\.webp|poster\.webp|mp4)$")
# Pages made from the other pages (home, hubs, directory, unlisted files, error page).
GENERATED = re.compile(r"^/(index\.html|collection\.html|ai\.html|donnie\.html|artists\.html|archive\.html|submit\.html|404\.html|directory/|unlisted/)")
FINDER = re.compile(r"(.*?)(?: copy(?: \d+)?| \d| \(\d+\))(/.*)$")  # "folder copy/", "folder 2/", "folder (1)/"
COPY_SUFFIX = re.compile(r"^(.{3,}?)(x+|ok|-?orig(?:inal)?|old|a|\d)$")  # indexx, contestindexok, atelier2020-original, moss01a, reception1
URL_SAFE = "/~()&+,;=:@!$'*-._"
STUB = '<meta name="moca-duplicate-of"'
NAV_LINK = re.compile(r"^(back|next|previous|prev|return|go to|moca home|home|top|contest info|view all|catalog)\b|\b(index|home|logo)$|directors?( s)? choice|artist name|not (yet )?(been )?(fully )?populated")


def canonical_path(url):
    u = url.split("#")[0]
    if u.endswith("/index.html"):
        u = u[:-len("index.html")]
    return quote(unquote(u), safe=URL_SAFE)


def media_identity(path=TWINS):
    """Media key -> identity. media_twins.tsv lists the files stored more than once under different
    names (same byte size, and the same picture once fetched and compared; made by hand from
    media-map-originals.tsv): every copy maps to the first name."""
    twin = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or "\t" not in line:
                    continue
                k, rep = line.rstrip("\n").split("\t")[:2]
                twin[k] = rep
    except OSError:
        pass
    return lambda key: twin.get(key, key)


def main_of(doc):
    m = re.search(r'<main id="main".*?</main>', doc, re.S)
    return m.group(0) if m else ""


def content(doc):
    """The page's own content: <main> without the title bar, the exhibit pager and scripts."""
    body = re.sub(r'<div class="phead.*?</h1></div>', "", main_of(doc), count=1, flags=re.S)
    body = re.sub(r'<nav class="pager".*?</nav>', " ", body, flags=re.S)
    return re.sub(r"<(script|style)\b.*?</\1>", " ", body, flags=re.S)


def media_keys(body):
    keys = set()
    for u in re.findall(r'(?:src|href|data-full|data-swf)="(https://media\.museumofcomputerart\.org/[^"]+)"', body):
        keys.add(VARIANT.sub(r"\1", unquote(html.unescape(u[len(MEDIA_HOST):]))))
    for u in re.findall(r'<(?:iframe|embed|object|video|audio|source)\b[^>]*?(?:src|data)="([^"]+)"', body):
        if not u.startswith(MEDIA_HOST):
            keys.add("ext:" + html.unescape(u))
    return keys


def words_of(body):
    return re.findall(r"[a-z0-9]+", html.unescape(re.sub(r"<[^>]+>", " ", body)).lower())


def signature(doc, ident):
    body = content(doc)
    keys = media_keys(body)
    h1 = re.search(r"<h1>(.*?)</h1>", main_of(doc), re.S)
    # the page's own words: no link text (navigation) and no "not yet populated" notices
    own = re.sub(r"<a\b[^>]*>.*?</a>|<span class=\"dead\"[^>]*>.*?</span>", " ", body, flags=re.S)
    own = re.sub(r"this page (has )?not (yet )?(been )?(fully )?populated", " ", " ".join(words_of(own)))
    return {"words": words_of(body), "own": own.split(), "media": {ident(k) for k in keys},
            "title": html.unescape(h1.group(1)) if h1 else ""}


def stub_target(doc):
    m = re.search(STUB + r' content="([^"]*)"', doc)
    return html.unescape(m.group(1)) if m else None


def link_target(href):
    """An internal href -> the site path of the file it opens."""
    u = unquote(html.unescape(href.split("#")[0].split("?")[0]))
    if u.endswith("/"):
        u += "index.html"
    return u


def load_overrides(path=OVERRIDES):
    """duplicates.tsv: `copy<TAB>kept page` makes copy a duplicate of the kept page; `page<TAB>-`
    keeps a page that the rules would otherwise treat as a duplicate."""
    add, keep = {}, set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line.strip() or line.startswith("#"):
                    continue
                a, b = (line.split("\t") + ["", ""])[:2]
                if b.strip() == "-":
                    keep.add(a.strip())
                elif b.strip():
                    add[a.strip()] = b.strip()
    except OSError:
        pass
    return add, keep


def _thin(s):
    return len(s["words"]) < 20 and not s["media"]


def _series(a, b):
    """Two numbered pages of one sequence (bb13.htm and bb19.htm, bg08_10a.htm and bg08_19j.htm): the
    same picture shown twice in a slide sequence is left for a person to decide."""
    if posixpath.dirname(a) != posixpath.dirname(b):
        return False
    na, nb = (posixpath.splitext(posixpath.basename(x))[0] for x in (a, b))
    if re.sub(r"\d+", "#", na) == re.sub(r"\d+", "#", nb):
        return True
    tail = re.compile(r"\d[a-z]$")
    if tail.search(na) and tail.search(nb):
        return re.sub(r"\d+", "#", na)[:-1] == re.sub(r"\d+", "#", nb)[:-1]
    return False


def _stem(u):
    stem = posixpath.splitext(posixpath.basename(u))[0].lower()
    m = COPY_SUFFIX.match(stem)
    return m.group(1) if m and not stem[-2:].isdigit() else stem


def _ratio(a, b, at=0.9):
    """difflib's similarity of two word lists, or 0 when it is surely under `at`."""
    la, lb = len(a), len(b)
    if not la or not lb or 2 * min(la, lb) / (la + lb) < at:
        return 0.0
    ca, cb = Counter(a), Counter(b)
    if 2 * sum((ca & cb).values()) / (la + lb) < at:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def extra_words(dup, keep):
    """Words of dup that keep lacks (inserted or replaced), in order."""
    sm = difflib.SequenceMatcher(None, keep, dup, autojunk=False)
    return [w for op, _, _, b1, b2 in sm.get_opcodes() if op in ("insert", "replace") for w in dup[b1:b2]]


def find(docs, ident=None, overrides=None):
    """docs: {site path: html}. Returns ({copy: kept page}, notes) where notes lists the pairs left
    for a person (near copies whose differences would be lost, repeated pictures in a sequence)."""
    ident = ident or media_identity()
    add, keep = overrides if overrides is not None else load_overrides()
    dup_of, notes = {}, []
    for u, d in docs.items():
        t = stub_target(d)
        if t:
            dup_of[u] = t
    sig = {u: signature(d, ident) for u, d in docs.items() if u not in dup_of and not GENERATED.match(u)}
    inbound = Counter()
    for u, d in docs.items():
        if u in dup_of:
            continue
        for h in set(re.findall(r'<a [^>]*?href="(/[^"#?]*)', d)):
            inbound[link_target(h)] += 1

    def copy_like(u, group):
        """An address that looks like a copy: the mirror, Finder copies, a folder or file saved again
        inside another folder (/holloway/donnie2023/main.htm next to /donnie2023/main.htm), a draft
        name (indexx.html, reception1.htm next to reception.htm)."""
        name = posixpath.basename(u)
        stem = posixpath.splitext(name)[0].lower()
        return (u.startswith("/donnie(s)/") or bool(FINDER.match(u)) or stem.endswith("xx")
                or any(v != u and u.endswith(v) for v in group)
                or (_stem(u) != stem and any(posixpath.dirname(v) == posixpath.dirname(u) and _stem(v) == _stem(u)
                                             and posixpath.splitext(posixpath.basename(v))[0].lower() == _stem(u) for v in group)))

    edges = []

    def complete(a, b):
        """b holds everything a shows, give or take a few words."""
        return sig[a]["media"] <= sig[b]["media"] and len(extra_words(sig[a]["own"], sig[b]["own"])) <= 3

    # 1. copies by address: x.htm / x.html twins, Finder copy folders, the /donnie(s)/ mirror
    for u in sig:
        pair = None
        if u.endswith(".htm") and u + "l" in sig:
            pair = (u, u + "l")
        m = FINDER.match(u)
        if m and m.group(1) + m.group(2) in sig:
            pair = (u, m.group(1) + m.group(2))
        if u.startswith("/donnie(s)/") and "/" + u[len("/donnie(s)/"):] in sig:
            pair = (u, "/" + u[len("/donnie(s)/"):])
        if pair:
            a, b = pair
            same_media = sig[a]["media"] == sig[b]["media"] or sig[a]["media"] <= sig[b]["media"] or sig[b]["media"] <= sig[a]["media"]
            if same_media and (_ratio(sig[a]["words"], sig[b]["words"]) >= 0.9 or complete(a, b) or complete(b, a)):
                edges.append(pair)
            else:
                notes.append(("differs from its copy", a, b))
    # 1b. a folder or page saved again inside another folder (/holloway/donnie2023/x.htm, /rouse/rudavsky/x.htm,
    # /imagesoftheday/imagesoftheday07.htm next to /imagesoftheday07.htm) that shows nothing the original
    # lacks: a copy, even when it lost its pictures. A bare file name (/x/comments.htm and /comments.htm)
    # only counts when few folders use that name.
    names = Counter(posixpath.basename(u) for u in sig)
    for u in sig:
        parts = u.split("/")[1:]
        for i in range(1, len(parts)):
            v = "/" + "/".join(parts[i:])
            if v in sig and (len(parts) - i >= 2 or names[parts[-1]] <= 3):
                if complete(u, v):
                    edges.append((u, v))
                elif not complete(v, u) and sig[u]["media"] != sig[v]["media"] and _ratio(sig[u]["words"], sig[v]["words"]) >= 0.9:
                    notes.append(("copy in another folder shows other pictures", u, v))
                break
    # 2. the same content under two addresses
    exact = defaultdict(list)
    for u, s in sig.items():
        if not _thin(s):
            exact[(" ".join(s["words"]), tuple(sorted(s["media"])))].append(u)
    for us in exact.values():
        us.sort()
        for i, b in enumerate(us):
            partner = next((a for a in us if a != b and not _series(a, b)), None)
            if partner:
                edges.append((partner, b))
            elif i:
                notes.append(("same picture twice in a sequence", us[0], b))
    # 3. nearly the same content under the same file name (or a draft name of it)
    by_stem = defaultdict(list)
    for u, s in sig.items():
        if not _thin(s):
            by_stem[_stem(u)].append(u)
    for us in by_stem.values():
        us.sort()
        for i, a in enumerate(us):
            for b in us[i + 1:]:
                A, B = sig[a], sig[b]
                if A["media"] != B["media"] or (A["words"] == B["words"]) or _series(a, b):
                    continue
                if _ratio(A["words"], B["words"]) >= 0.9:
                    # a copy saved inside another folder, or a draft beside the page; near copies in
                    # unrelated folders (yearly versions of a page) are left for a person
                    if posixpath.dirname(a) == posixpath.dirname(b) or a.endswith(b) or b.endswith(a):
                        edges.append((a, b))
                    else:
                        notes.append(("near copy in another folder", a, b))
    for a, b in add.items():
        if a in sig and b in docs:
            edges.append((a, b))
    # groups, minus the pages a person decided to keep
    par = {}

    def root(x):
        while par.get(x, x) != x:
            par[x] = par.get(par[x], par[x])
            x = par[x]
        return x
    for a, b in edges:
        if a in keep or b in keep:
            continue
        ra, rb = root(a), root(b)
        if ra != rb:
            par[ra] = rb
    groups = defaultdict(list)
    for u in {x for e in edges for x in e}:
        if u not in keep:
            groups[root(u)].append(u)
    for us in groups.values():
        if len(us) < 2:
            continue
        forced = [b for a, b in add.items() if a in us and b in us and b not in add]
        allmedia = set().union(*(sig[u]["media"] for u in us))
        most = max(len(sig[u]["words"]) for u in us)

        def rank(u):
            s = sig[u]
            return (u in forced, not copy_like(u, us), s["media"] >= allmedia, len(s["words"]) >= 0.97 * most,
                    inbound[u], -u.count("/"), u.endswith(".htm"), -len(u))
        best = max(sorted(us), key=rank)
        for u in us:
            if u == best:
                continue
            dup_of[u] = best
    # chains (a copy of a copy) end at the page that is kept
    for u in list(dup_of):
        seen, t = {u}, dup_of[u]
        while t in dup_of and t not in seen:
            seen.add(t)
            t = dup_of[t]
        dup_of[u] = t
    return dup_of, notes


# ------------------------------------------------------------------ apply
def _blocks(body):
    """Top-level pieces of a page body: figures, paragraphs, headings, media, lists."""
    return re.findall(r'<figure\b.*?</figure>|<(p|h2|h3|li|blockquote)\b[^>]*>.*?</\1>|<div class="b media">.*?</div>', body, re.S)


def merge(keep_doc, dup_doc, ident):
    """Add to the kept page the pictures and passages of a copy that it does not show yet."""
    kbody = content(keep_doc)
    have_media = {ident(k) for k in media_keys(kbody)}
    have_words = set(words_of(kbody))
    extra = []
    dbody = content(dup_doc)
    for m in re.finditer(r'<figure\b.*?</figure>|<(p|h2|h3|blockquote)\b[^>]*>.*?</\1>|<div class="b media">.*?</div>', dbody, re.S):
        blk = m.group(0)
        ms = {ident(k) for k in media_keys(blk)}
        if ms:
            if not ms <= have_media:
                extra.append(blk)
                have_media |= ms
            continue
        ws = words_of(blk)
        linked = words_of(" ".join(x for t in re.findall(r'<a\b[^>]*>(.*?)</a>|<span class="dead"[^>]*>(.*?)</span>', blk, re.S) for x in t))
        if 'class="links"' in blk or len(linked) >= 0.6 * len(ws):
            # navigation and link lists: only entries the kept page lacks (an artist missing from
            # its copy of an index), never the copy's own navigation
            adds, linked_new = [], False
            for a in re.finditer(r'<a\b[^>]*?href="([^"]*)"[^>]*>(.*?)</a>|<span class="dead"[^>]*>(.*?)</span>', blk, re.S):
                aw = words_of(a.group(2) if a.group(1) is not None else a.group(3))
                if len(aw) >= 2 and not NAV_LINK.search(" ".join(aw)) and any(w not in have_words for w in aw) and (a.group(1) is None or f'href="{a.group(1)}"' not in kbody):
                    adds.append(a.group(0))
                    linked_new |= a.group(1) is not None
                    have_words |= set(aw)
            if linked_new:
                extra.append('<p class="links">' + "<br>".join(adds) + "</p>")
            continue
        if len([w for w in ws if w not in have_words]) >= 4 and not NAV_LINK.search(" ".join(ws)):  # more than a changed number or date; no notices
            extra.append(blk)
            have_words |= set(ws)
    if not extra:
        return keep_doc
    figs = "".join(b for b in extra if b.startswith(("<figure", "<div")))
    text = "".join(b for b in extra if not b.startswith(("<figure", "<div")))
    add = (f'<div class="b prose">{text}</div>' if text else "") + (f'<div class="wall">{figs}</div>' if figs else "")
    return keep_doc.replace("</main>", f'<section class="merged" aria-label="From another copy of this page">{add}</section>\n</main>', 1)


def stub(url, target, title, site_url, css):
    """The small page left at a copy's address: it sends visitors and search engines on."""
    canon = E(site_url + canonical_path(target))
    href = E(canonical_path(target))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="robots" content="noindex">
{STUB} content="{E(target)}">
<link rel="canonical" href="{canon}">
<meta http-equiv="refresh" content="0; url={href}">
<link rel="stylesheet" href="{E(css)}">
<script>location.replace({json.dumps(canonical_path(target))}+location.hash)</script>
</head>
<body>
<main id="main" class="wrap"><div class="b prose"><p>This page has moved to <a href="{href}">{E(title)}</a>.</p></div></main>
</body>
</html>
"""


def _title(doc):
    m = re.search(r"<title>(.*?)</title>", doc, re.S)
    t = html.unescape(m.group(1)).strip() if m else ""
    return re.sub(r"\s*·\s*MOCA$", "", t) or "Museum of Computer Art"


def apply(out, docs, dup_of, site_url, css="/assets/site.css", ident=None):
    """Write the merged pages, the redirect pages and the fixed links. docs is updated in place;
    returns (paths whose file changed, [(copy, kept page)] where the kept page took content from the copy)."""
    ident = ident or media_identity()
    changed, merged = set(), []
    # 1. merge: the kept page gets whatever a copy showed that it lacks
    for u in sorted(dup_of):
        t = dup_of[u]
        if t in docs and stub_target(docs[u]) is None:
            new = merge(docs[t], docs[u], ident)
            if new != docs[t]:
                docs[t] = new
                changed.add(t)
                merged.append((u, t))
    # 2. stubs
    for u in sorted(dup_of):
        t = dup_of[u]
        title = _title(docs[t]) if t in docs else "Museum of Computer Art"
        new = stub(u, t, title, site_url, css)
        if docs.get(u) != new:
            docs[u] = new
            changed.add(u)
    # 3. links on every other page; on the generated pages (hubs, directory) the copies' cards and lines go
    for u in sorted(docs):
        if u in dup_of:
            continue
        new = fix_links(docs[u], dup_of, GENERATED.match(u))
        if new != docs[u]:
            docs[u] = new
            changed.add(u)
    changed |= recount(docs, site_url, css)
    changed |= prune_unlisted(docs, ident, site_url, css)
    for u in sorted(changed):
        with open(os.path.join(out, u.lstrip("/")), "w", encoding="utf-8") as f:
            f.write(docs[u])
    return changed, merged


def fix_links(doc, dup_of, generated):
    if generated:
        def card(m):  # a copy's card on a hub that already has a card for the kept page: drop it
            t = dup_of.get(link_target(m.group(1)))
            if t and f'class="card" href="{E(canonical_path(t))}"' in doc:
                return ""
            return m.group(0)
        doc = re.sub(r'<a class="card" href="(/[^"]*)">.*?</a>', card, doc, flags=re.S)
        # directory and hub lists ("title<span>file</span>"): one line per page, so a copy's line goes
        doc = re.sub(r'<a href="(/[^"]*)">[^<]*<span>[^<]*</span></a>',
                     lambda m: "" if link_target(m.group(1)) in dup_of else m.group(0), doc)

    def href(m):
        h = m.group(2)
        t = dup_of.get(link_target(h))
        if not t:
            return m.group(0)
        frag = "#" + h.split("#", 1)[1] if "#" in h else ""
        return f'{m.group(1)}"{E(canonical_path(t))}{frag}"'
    return re.sub(r'(<a [^>]*?href=)"(/[^"]*)"', href, doc)


def recount(docs, site_url, css):
    """The directory's page counts once the copies have left its lists. A folder left with no page
    of its own (all copies) leaves the directory; its directory page sends visitors to the directory."""
    changed, counts = set(), {}
    for u in docs:
        m = re.fullmatch(r"/directory/([^/]+)\.html", u)
        if not m or u == "/directory/index.html":
            continue
        lst = re.search(r'<div class="list">(.*?)</div>', docs[u], re.S)
        n = len(re.findall(r"<a href=", lst.group(1))) if lst else 0
        counts["/directory/" + m.group(1) + ".html"] = n
        if n == 0:
            docs[u] = stub(u, "/directory/index.html", "Directory of every page", site_url, css)
            changed.add(u)
            continue
        new = re.sub(r"All \d[\d,]* pages in this part of the museum", f"All {n} pages in this part of the museum", docs[u])
        if new != docs[u]:
            docs[u] = new
            changed.add(u)
    idx = "/directory/index.html"
    if idx not in docs or not counts:
        return changed
    doc = docs[idx]
    old = re.search(r"Every one of the ([\d,]+) pages", doc)
    doc = re.sub(r'(<a href="(/directory/[^"]+\.html)">[^<]*<span>)\d+(</span></a>)',
                 lambda m: m.group(0) if m.group(2) not in counts else "" if not counts[m.group(2)] else m.group(1) + str(counts[m.group(2)]) + m.group(3), doc)
    total = sum(counts.values())
    if old:
        doc = doc.replace(f"{old.group(1)} pages", f"{total:,} pages")
        home = docs.get("/index.html")
        if home and f"{old.group(1)} pages" in home:
            docs["/index.html"] = home.replace(f"{old.group(1)} pages", f"{total:,} pages")
            changed.add("/index.html")
    if doc != docs[idx]:
        docs[idx] = doc
        changed.add(idx)
    return changed


UNLISTED_ITEM = re.compile(r'<figure\b.*?</figure>|<div><p class="note">[^<]*</p>(?:<div class="b media">.*?</div>|<figure\b.*?</figure>)</div>', re.S)


def prune_unlisted(docs, ident, site_url, css):
    """The Unlisted files pages show media that no page displays. A file stored again under another
    name (media_twins.tsv) is not unlisted when a page shows its twin, and is listed once only."""
    shown = set()
    for u, d in docs.items():
        if not u.startswith("/unlisted/") and STUB not in d:
            shown |= {ident(k) for k in media_keys(content(d))}
    changed, counts, seen = set(), {}, set()
    for u in sorted(docs):
        if not u.startswith("/unlisted/") or u == "/unlisted/index.html" or STUB in docs[u]:
            continue
        kept = []

        def item(m):
            ids = {ident(k) for k in media_keys(m.group(0))}
            if ids and (ids <= shown or ids <= seen):
                return ""
            seen.update(ids)
            kept.append(1)
            return m.group(0)
        new = UNLISTED_ITEM.sub(item, docs[u])
        counts[u] = len(kept)
        new = re.sub(r"<p>\d+ files from the <b>", f"<p>{len(kept)} files from the <b>", new, count=1)
        if not kept:
            new = stub(u, "/unlisted/index.html", "Unlisted files", site_url, css)
        if new != docs[u]:
            docs[u] = new
            changed.add(u)
    idx = "/unlisted/index.html"
    if idx in docs and changed:
        doc = re.sub(r'(<a href="(/unlisted/[^"]+\.html)">[^<]*<span>)\d+(</span></a>)',
                     lambda m: m.group(0) if m.group(2) not in counts else "" if not counts[m.group(2)] else m.group(1) + str(counts[m.group(2)]) + m.group(3), docs[idx])
        total = sum(int(n) for n in re.findall(r'<a href="/unlisted/[^"]+\.html">[^<]*<span>(\d+)</span></a>', doc))
        doc = re.sub(r"[\d,]+ images, videos and other files", f"{total:,} images, videos and other files", doc)
        if doc != docs[idx]:
            docs[idx] = doc
            changed.add(idx)
    return changed


def filter_search(out, dup_of, docs=None):
    """Search lists no redirect page (copies, and lists left empty once the copies went)."""
    stubs = set(dup_of) | {u for u, d in (docs or {}).items() if STUB in d}
    p = os.path.join(out, "search.json")
    try:
        with open(p) as f:
            idx = json.load(f)
    except (OSError, ValueError):
        return
    keep = [x for x in idx if link_target(x[1]) not in stubs]
    if len(keep) != len(idx):
        with open(p, "w") as f:
            json.dump(keep, f, separators=(",", ":"))
