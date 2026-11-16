"""Parse a legacy MOCA page (1990s-2020s hand-written HTML/ASP) into a clean,
ordered list of content blocks that the Bento templates can render.

Nothing visible is thrown away silently: every image, link and run of text is
either emitted as a block or recorded in `dropped` with a reason, so the
verification step can account for it.
"""
import html
import os
import posixpath
import re
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

import rebrand

OUR_HOSTS = {
    "moca.virtual.museum", "www.moca.virtual.museum",
    "mocadigitalart.com", "www.mocadigitalart.com",
    "museumofcomputerart.org", "www.museumofcomputerart.org",
    "museumofcomputerart.com", "www.museumofcomputerart.com",
}
# Spam links planted in old pages (not on the live sites): dropped with their link text.
SPAM_HOSTS = {"francemaillotnba.com", "perfectreplica.to", "watchsourceguide.com"}
PAGE_EXT = (".htm", ".html", ".asp", ".aspx", ".shtml")
SERVER_SCRIPT_EXT = (".php", ".php3", ".cgi", ".pl", ".jsp")
MEDIA_VIDEO = (".mov", ".avi", ".flv", ".wmv", ".mpg", ".mpeg", ".rm", ".mp4", ".m4v")
MEDIA_AUDIO = (".mid", ".midi", ".wav", ".mp3", ".aif", ".aiff")
INLINE_KEEP = {"b": "b", "strong": "b", "i": "i", "em": "i", "u": "u", "sup": "sup", "sub": "sub"}
BLOCK = {"p", "div", "center", "blockquote", "table", "tr", "td", "th", "tbody", "thead",
         "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "dl", "dt", "dd",
         "form", "pre", "address", "section", "article", "header", "footer", "nav", "map"}
# Site chrome: old navigation buttons, footers and logos. Linked ones become text
# links; unlinked ones are recorded as dropped chrome.
CHROME_RE = re.compile(
    r"(^|/)(but_[^/]*|mfoot_[^/]*|mocafooter[^/]*|moca_?logo[^/]*|mocalogo[^/]*|home\d*\.(gif|jpg)|"
    r"spacer[^/]*|blank\.gif|dot\.gif|clear\.gif|arrow[^/]*|next\d*\.(gif|jpg)|prev[^/]*\.(gif|jpg)|"
    r"back\d*\.(gif|jpg)|forward[^/]*\.(gif|jpg)|top\d*\.(gif|jpg)|animated_favicon[^/]*|"
    r"creditcardlogos\.gif|paypal[^/]*\.(gif|jpg))$", re.I)
NAV_WORDS = {
    "next": "Next", "next page": "Next", "forward": "Next", ">>": "Next", ">": "Next",
    "previous": "Previous", "prev": "Previous", "back": "Back", "<<": "Previous", "<": "Previous",
    "home": "MOCA home", "moca home": "MOCA home", "index": "Index", "top": "Top",
}
CHROME_LABELS = [
    (r"home|moca(?!net)|musofcompart|logo", "MOCA home"), (r"next|forward", "Next"),
    (r"prev|back", "Previous"), (r"index", "Index"), (r"top", "Top"), (r"donate", "Donate"),
]


def decode(raw: bytes) -> str:
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace")


ASP_BLOCK = re.compile(r"<%.*?%>", re.S)
INCLUDE = re.compile(r"<!--\s*#include\s+(file|virtual)\s*=\s*\"([^\"]+)\"\s*-->", re.I)


def resolve_includes(text, page_path, read, depth=0):
    def sub(m):
        kind, target = m.group(1).lower(), m.group(2).replace("\\", "/")
        p = target.lstrip("/") if kind == "virtual" or target.startswith("/") else posixpath.join(posixpath.dirname(page_path), target)
        p = posixpath.normpath(p).lower()
        data = read(p)
        if data is None or depth > 3:
            return ""
        return resolve_includes(decode(data), p, read, depth + 1)
    return INCLUDE.sub(sub, text)


def clean_asp(text):
    # Keep the date ASP printed on the homepage out; strip all server code.
    return ASP_BLOCK.sub("", text)


class Ctx:
    def __init__(self, page_path, exists, autogalleries):
        self.page = page_path            # lowercase legacy path, e.g. donnie2024/exhibitpages/page001.htm
        self.dir = posixpath.dirname(page_path)
        self.exists = exists             # callable(lowercase path) -> bool
        self.autogalleries = autogalleries  # set of folder paths that are AutoGallery galleries
        self.dropped = []
        self.links_out = []
        self.images = []


LEGACY_HOMES = {"index.asp": "/legacy/moca-home.html", "index.html": "/legacy/moca-home-2022.html"}
AG_VIEW = re.compile(r"index_q_mode-view-image-(\d+)-returnpage-\d+\.html?$", re.I)


def norm_internal(target, ctx):
    """Map a legacy href/src to (kind, value).
    kind: 'page' (site path, new extension), 'media' (lowercase path), 'external', 'anchor', 'mailto', 'missing'."""
    if target is None:
        return ("none", "")
    t = target.strip().replace("\\", "/")
    t = re.sub(r"\s+", " ", t)
    if not t:
        return ("none", "")
    low = t.lower()
    if low.startswith("#"):
        return ("anchor", t)
    if low.startswith(("mailto:", "tel:")):
        return ("mailto", t)
    if re.fullmatch(r"[\w.+\-]+@[\w\-]+(\.[\w\-]+)+", t):
        return ("mailto", "mailto:" + t)
    if low.startswith(("javascript:", "vbscript:")):
        m = re.search(r"['\"]([^'\"]+\.(?:jpe?g|gif|png|htm|html|asp))['\"]", t, re.I)
        if not m:
            return ("none", "")
        t = m.group(1)
        low = t.lower()
    parts = urlsplit(t)
    if parts.scheme in ("http", "https", "ftp") or t.startswith("//"):
        host = (parts.hostname or "").lower()
        if host not in OUR_HOSTS:
            return ("external", t)
        path = parts.path or "/"
        query, frag = parts.query, parts.fragment
    elif parts.scheme:
        return ("external", t)
    else:
        path, query, frag = parts.path, parts.query, parts.fragment
    path = unquote(path)
    if not path.startswith("/"):
        path = posixpath.join("/" + ctx.dir, path)
    trailing = path.endswith("/")
    path = posixpath.normpath(path).lstrip("/").lower()
    if path == ".":
        path = ""
    m = AG_VIEW.search(path)
    if m:
        folder = posixpath.dirname(path)
        return ("page", f"/{folder}/#image-{m.group(1)}" if folder else "/")
    if path in ("", "index.asp", "index.htm", "index.html", "default.asp", "default.htm", "indexx.asp") or (
            re.search(r"(^|/)(index|default)\.(asp|html?)$", path) and not ctx.exists(path)):
        return ("page", "/" + (("#" + frag) if frag else ""))
    if path in ctx.autogalleries or (path.endswith("/index.asp") and posixpath.dirname(path) in ctx.autogalleries):
        folder = path if path in ctx.autogalleries else posixpath.dirname(path)
        img = re.search(r"image=(\d+)", query or "", re.I)
        return ("page", f"/{folder}/" + (f"#image-{img.group(1)}" if img else ""))
    if path.endswith(PAGE_EXT) or path.endswith(".htmxx"):
        out = page_url(path)
        if not ctx.exists(path):
            alt = [path[: -len(e)] + e2 for e in PAGE_EXT if path.endswith(e) for e2 in PAGE_EXT]
            hit = next((a for a in alt if ctx.exists(a)), None)
            if hit:
                out = page_url(hit)
            else:
                return ("missing", "/" + path)
        return ("page", out + (("#" + frag) if frag else ""))
    if path.endswith(SERVER_SCRIPT_EXT):
        return ("missing", "/" + path)  # a server script (comments, forms): nothing can run it on the static site
    # directory link: look for an index page
    if trailing or "." not in posixpath.basename(path):
        for idx in ("index.htm", "index.html", "index.asp", "default.htm", "default.asp", "main.htm"):
            cand = posixpath.join(path, idx)
            if ctx.exists(cand):
                return ("page", page_url(cand) if idx != "index.htm" else "/" + path + "/index.htm")
        if ctx.exists(path):
            return ("media", path)
        return ("missing", "/" + path + "/")
    if ctx.exists(path):
        return ("media", path)
    return ("missing", "/" + path)


def page_url(path):
    """Legacy page path -> URL on the new site (.asp/.aspx become .html; .htm/.html are kept)."""
    if path in LEGACY_HOMES:
        return LEGACY_HOMES[path]
    if path.endswith(".aspx"):
        path = path[:-5] + ".html"
    elif path.endswith(".asp"):
        path = path[:-4] + ".html"
    return rebrand.moved_path("/" + path)


def seq_label(cur, target):
    """'Next'/'Previous' from the page numbers in two file names (page014 -> page015)."""
    a = re.search(r"(\d+)\D*$", posixpath.basename(cur))
    b = re.search(r"(\d+)\D*$", posixpath.basename(target.split("#")[0]))
    if not a or not b or posixpath.dirname("/" + cur) != posixpath.dirname(target.split("#")[0]):
        return None
    x, y = int(a.group(1)), int(b.group(1))
    return "Next" if y > x else "Previous" if y < x else None


def int_attr(v):
    try:
        return int(re.match(r"\s*(\d+)", str(v)).group(1))
    except Exception:
        return None


def chrome_label(src, alt):
    if alt and alt.strip() and len(alt.strip()) < 40:
        return alt.strip()
    base = posixpath.basename(src.lower())
    base = re.sub(r"^(but_|mfoot_)", "", base)
    for pat, lab in CHROME_LABELS:
        if re.search(pat, base):
            return lab
    stem = re.sub(r"(_over)?\.(gif|jpe?g|png)$", "", base)
    stem = re.sub(r"[_\-]+", " ", stem).strip()
    return stem.title() or "Link"


class Parser:
    def __init__(self, ctx):
        self.ctx = ctx
        self.blocks = []
        self.buf = []          # inline html fragments of the current paragraph
        self.text_len = 0

    # ---- paragraph buffer
    def flush(self):
        h = "".join(self.buf).strip()
        h = re.sub(r"^(\s*<br>\s*)+|(\s*<br>\s*)+$", "", h)
        h = re.sub(r"(\s*<br>\s*){3,}", "<br><br>", h)
        plain = re.sub(r"<[^>]+>", "", h).replace("&nbsp;", " ")
        if plain.strip() or "<a " in h:
            self.blocks.append({"t": "p", "html": h, "text": html.unescape(re.sub(r"\s+", " ", plain)).strip()})
        self.buf = []

    def split_caption(self):
        """'Title<br><img>' on old pages: give the last line before an image its own paragraph."""
        joined = re.sub(r"(\s*<br>\s*)+$", "", "".join(self.buf).strip())
        if len(re.sub(r"<[^>]+>", "", joined)) <= 160:
            return
        parts = re.split(r"(?:\s*<br>\s*)+", joined)
        if len(parts) > 1 and re.sub(r"<[^>]+>", "", parts[-1]).strip():
            last = parts[-1]
            # keep tags balanced: only split when the tail has no unclosed inline tag
            if last.count("<b>") == last.count("</b>") and last.count("<i>") == last.count("</i>") and last.count("<a ") == last.count("</a>"):
                head = joined[: joined.rfind(last)]
                if head.count("<b>") == head.count("</b>") and head.count("<a ") == head.count("</a>"):
                    self.buf = [head]
                    self.flush()
                    self.buf = [last]

    def emit(self, block):
        if block.get("t") == "img":
            self.split_caption()
        self.flush()
        self.blocks.append(block)

    # ---- links
    def link_open(self, a):
        href = a.get("href")
        kind, val = norm_internal(href, self.ctx)
        if kind in ("none",):
            return None
        target = val
        if kind == "media":
            target = ("media", val)
        self.ctx.links_out.append((kind, val, href))
        return (kind, target)

    def a_tag(self, link):
        kind, target = link
        if kind == "media":
            return f'<a href="{{{{MEDIA:{html.escape(target[1])}}}}}">'
        if kind == "external":
            return f'<a href="{html.escape(target)}" rel="noopener">'
        if kind == "missing":
            return f'<a href="{html.escape(target)}" data-missing="1">'
        return f'<a href="{html.escape(target)}">'

    # ---- walk
    def walk(self, node, link=None):
        for ch in list(node.children):
            if isinstance(ch, Comment):
                continue
            if isinstance(ch, NavigableString):
                s = str(ch)
                if not s:
                    continue
                s = html.escape(re.sub(r"[ \t\r\n\f]+", " ", s), quote=False)
                if s.strip():
                    if link:
                        s = self.a_tag(link) + s + "</a>"
                    self.buf.append(s)
                elif self.buf and not self.buf[-1].endswith(" "):
                    self.buf.append(" ")
                continue
            if not isinstance(ch, Tag):
                continue
            name = ch.name.lower()
            if name in ("script", "style", "noscript", "head", "title", "meta", "link", "base", "bgsound", "xml", "o:p"):
                if name == "bgsound" and ch.get("src"):
                    self.media(ch.get("src"), "audio", ch)
                continue
            if name == "br":
                self.buf.append("<br>")
                continue
            if name == "img" or (name == "input" and (ch.get("type") or "").lower() == "image"):
                if name == "input":
                    continue  # form buttons are rendered with their form
                self.image(ch, link)
                continue
            if name == "a":
                host = (urlsplit((ch.get("href") or "").strip()).hostname or "").lower()
                if host.removeprefix("www.") in SPAM_HOSTS:
                    self.ctx.dropped.append(("spam-link", ch.get("href"), ch.get_text(" ", strip=True)[:80]))
                    continue
                lk = self.link_open(ch) if ch.get("href") else None
                if ch.get("name") and not ch.get_text(strip=True) and not ch.find("img"):
                    self.buf.append(f'<span id="{html.escape(ch.get("name").lower())}"></span>')
                self.walk(ch, lk or link)
                continue
            if name in ("embed", "object", "iframe", "video", "audio", "applet"):
                self.embed(ch)
                if name in ("object", "video", "audio"):
                    rest = BeautifulSoup(str(ch), "lxml")
                    for x in rest.find_all(["embed", "object", "param", "source", "video", "audio", "track"]):
                        x.unwrap() if x.name in ("object", "video", "audio") else x.decompose()
                    if rest.get_text(strip=True):
                        self.walk(rest.body or rest, link)
                continue
            if name == "map":
                self.image_map(ch)
                continue
            if name == "area":
                continue
            if name == "form":
                self.form(ch)
                continue
            if name in ("select", "textarea", "input", "button", "option"):
                continue
            if name in INLINE_KEEP:
                tag = INLINE_KEEP[name]
                start = len(self.buf)
                self.buf.append(f"<{tag}>")
                self.walk(ch, link)
                if len(self.buf) == start + 1:
                    self.buf.pop()
                else:
                    self.buf.append(f"</{tag}>")
                continue
            if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self.flush()
                self.walk(ch, link)
                h = "".join(self.buf).strip()
                self.buf = []
                txt = html.unescape(re.sub(r"<[^>]+>", "", h)).strip()
                if txt:
                    self.blocks.append({"t": "h", "html": h, "text": re.sub(r"\s+", " ", txt)})
                continue
            if name == "hr":
                self.emit({"t": "hr"})
                continue
            if name == "li":
                self.flush()
                self.buf.append("• ")
                self.walk(ch, link)
                self.flush()
                continue
            if name in BLOCK:
                self.flush()
                self.walk(ch, link)
                self.flush()
                continue
            # font, span, nobr, small, big, etc.: transparent
            self.walk(ch, link)

    def image(self, img, link):
        src = img.get("src") or img.get("data-src")
        if not src:
            return
        kind, val = norm_internal(src, self.ctx)
        alt = (img.get("alt") or "").strip()
        w, h = int_attr(img.get("width")), int_attr(img.get("height"))
        is_chrome = bool(CHROME_RE.search(src.split("?")[0])) or (w and h and w * h <= 1200 and (w < 160 and h < 40))
        if is_chrome:
            if link:
                label = chrome_label(src, alt)
                tgt = link[1] if isinstance(link[1], str) else link[1][1]
                if link[0] == "missing":
                    self.ctx.dropped.append(("chrome-linked-missing", src, tgt))
                    return
                if label in ("Next", "Previous", "Back") or (label == "MOCA home" and tgt not in ("/", "")):
                    label = seq_label(self.ctx.page, tgt) or (label if label != "MOCA home" else
                            re.sub(r"[_\-]+", " ", posixpath.splitext(posixpath.basename(tgt.split("#")[0].rstrip("/")))[0]).strip().title() or "Link")
                self.buf.append(self.a_tag(link) + html.escape(label) + "</a> ")
                self.ctx.dropped.append(("chrome-linked", src, label))
            else:
                self.ctx.dropped.append(("chrome", src, ""))
            return
        if kind == "external":
            self.emit({"t": "img", "ext": val, "alt": alt, "w": w, "h": h, "link": link})
            return
        if kind != "media":
            self.ctx.dropped.append(("missing-image", src, val))
            if link and link[0] != "missing":
                # keep the link the picture carried, as text
                label = alt or re.sub(r"[_\-]+", " ", posixpath.splitext(posixpath.basename(src.split("?")[0]))[0]).strip().title() or "Link"
                self.buf.append(self.a_tag(link) + html.escape(label) + "</a> ")
                return
            self.emit({"t": "img", "missing": val, "alt": alt, "w": w, "h": h, "link": link})
            return
        self.ctx.images.append(val)
        self.emit({"t": "img", "src": val, "alt": alt, "w": w, "h": h, "link": link})

    def image_map(self, m):
        self.flush()
        seen = set()
        for area in m.find_all("area"):
            href = area.get("href")
            if not href:
                continue
            lk = self.link_open(area)
            if not lk:
                continue
            label = (area.get("alt") or area.get("title") or "").strip()
            if not label:
                v = lk[1] if isinstance(lk[1], str) else lk[1][1]
                label = "MOCA home" if v in ("/", "") else (seq_label(self.ctx.page, v) or re.sub(r"[_\-]+", " ", posixpath.splitext(posixpath.basename(v.split("#")[0].rstrip("/")))[0]).strip().title() or "Link")
            key = (str(lk), label)
            if key in seen:
                continue
            seen.add(key)
            self.buf.append(self.a_tag(lk) + html.escape(label) + "</a> ")
        self.flush()

    def media(self, src, kind_hint, node):
        kind, val = norm_internal(src, self.ctx)
        if kind == "external":
            self.emit({"t": "embed", "ext": val, "kind": kind_hint})
        elif kind == "media":
            self.emit({"t": "media", "src": val, "kind": kind_hint,
                       "w": int_attr(node.get("width")), "h": int_attr(node.get("height"))})
        else:
            self.ctx.dropped.append(("missing-media", src, val))
            self.emit({"t": "media", "missing": val, "kind": kind_hint})

    def embed(self, node):
        name = node.name.lower()
        src = node.get("src") or node.get("data") or node.get("movie")
        if not src:
            for p in node.find_all("param"):
                if (p.get("name") or "").lower() in ("movie", "src", "filename", "url"):
                    src = p.get("value")
                    break
        if not src and name in ("video", "audio") and node.find("source"):
            src = node.find("source").get("src")
        if not src and node.find("embed"):
            return self.embed(node.find("embed"))
        if not src:
            if node.name == "applet":
                self.ctx.dropped.append(("applet", node.get("code", ""), ""))
            return
        low = src.lower().split("?")[0]
        if name == "iframe":
            kind, val = norm_internal(src, self.ctx)
            if kind in ("media", "missing") and low.endswith(MEDIA_VIDEO + MEDIA_AUDIO + (".swf",)):
                k = "flash" if low.endswith(".swf") else "video" if low.endswith(MEDIA_VIDEO) else "audio"
                return self.media(src, k, node)
            self.emit({"t": "embed", "ext": val if kind == "external" else ("/" + val if kind == "media" else val), "kind": "iframe",
                       "w": int_attr(node.get("width")), "h": int_attr(node.get("height"))})
            return
        k = "flash" if low.endswith(".swf") else "video" if low.endswith(MEDIA_VIDEO) else "audio" if low.endswith(MEDIA_AUDIO) else "other"
        self.media(src, k, node)

    def form(self, f):
        action = (f.get("action") or "").strip()
        self.flush()
        if "paypal.com" in action.lower():
            fields = []
            for inp in f.find_all("input"):
                t = (inp.get("type") or "text").lower()
                if t == "hidden":
                    fields.append(f'<input type="hidden" name="{html.escape(inp.get("name") or "")}" value="{html.escape(inp.get("value") or "")}">')
            # keep any visible text (e.g. amount options) as paragraphs
            for sel in f.find_all("select"):
                opts = "".join(f'<option value="{html.escape(o.get("value") or o.get_text())}">{html.escape(o.get_text(strip=True))}</option>' for o in sel.find_all("option"))
                fields.append(f'<label>{html.escape(sel.get("name") or "Option")}<select name="{html.escape(sel.get("name") or "")}">{opts}</select></label>')
            self.walk_text_only(f)
            self.emit({"t": "paypal", "action": "https://www.paypal.com/cgi-bin/webscr", "fields": "".join(fields)})
            return
        # server-side (ASP/CGI) forms cannot run on a static host; keep their text
        self.walk_text_only(f)
        self.emit({"t": "form-retired", "action": action})
        self.ctx.dropped.append(("server-form", action, ""))

    def walk_text_only(self, f):
        if re.search(r"search|freefind|google|picosearch|atomz", (f.get("action") or "") + " " + f.get_text(" "), re.I) and len(f.get_text(" ", strip=True)) < 120:
            return
        for x in f.find_all(["input", "select", "textarea", "button"]):
            x.decompose()
        self.walk(f)
        self.flush()


def parse(text, ctx):
    soup = BeautifulSoup(text, "lxml")
    title = ""
    if soup.title and soup.title.string:
        title = re.sub(r"\s+", " ", soup.title.get_text()).strip()
    desc = ""
    md = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if md and md.get("content"):
        desc = md["content"].strip()
    body = soup.body or soup
    # Background images on body/table cells are content on a few pages.
    bgs = []
    for t in body.find_all(attrs={"background": True}) + ([soup.body] if soup.body and soup.body.get("background") else []):
        bgs.append(t.get("background"))
    p = Parser(ctx)
    p.walk(body)
    p.flush()
    for b in bgs:
        kind, val = norm_internal(b, ctx)
        if kind == "media":
            dims = ctx.dims(val) if hasattr(ctx, "dims") else None
            if dims and dims[0] * dims[1] >= 250000:  # a real picture used as a page background
                ctx.images.append(val)
                p.blocks.insert(0, {"t": "img", "src": val, "alt": "", "w": dims[0], "h": dims[1], "link": None})
            else:
                ctx.dropped.append(("background", val, ""))
    return {"title": title, "desc": desc, "blocks": p.blocks}
