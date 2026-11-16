#!/usr/bin/env python3
"""Remove the retired moca.virtual.museum name from the published site.

build.py runs clean() on every page it writes, so a rebuild stays clean. Run this file
on its own to clean an already built site/ folder in place (no backups needed):

    python3 tools/rebrand.py            # rewrite site/ and move the renamed folders
    python3 tools/rebrand.py --check    # only count what is left

What is kept on purpose: Internet Archive links (they only work with the old address),
media file URLs under media.museumofcomputerart.org (the R2 object keys still use the
old folder name), the PayPal account address in donate forms (changing it would
send donations to a different PayPal account), and <script> blocks, such as the 404.html code that redirects old addresses.
"""
import os
import re
import shutil
import sys

EMAIL = "hello@museumofcomputerart.org"
NEW_HOST = "museumofcomputerart.org"
OLD = r"(?:www\.)?moca\.virtual\.museum"

# Page folders and files whose own address contained the old name: old prefix -> new prefix.
MOVED = {
    "/imofday/moca.virtual.museum/": "/imofday/archive/",
    "/legacy/moca-virtual-museum-home-2022.html": "/legacy/moca-home-2022.html",
    "/legacy/moca-virtual-museum-home.html": "/legacy/moca-home.html",
}

_KEEP = re.compile(r"<script\b[^>]*>.*?</script>|name=\"business\" value=\"[^\"]*\"|https?://web\.archive\.org/[^\s\"'<>]*|https?://media\.museumofcomputerart\.org/[^\s\"'<>]*", re.I | re.S)

_RULES = [
    # email addresses, linked or not
    (re.compile(r"\b(?:don|admin|donarcher)@" + OLD, re.I), EMAIL),
    # the same person listed twice under two old addresses
    (re.compile(r'(<a href="mailto:' + re.escape(EMAIL) + r'">' + re.escape(EMAIL) + r'</a>)<br>\s*or<br>\s*\1'), r"\1"),
    # dead links that were missing a slash on the old site
    (re.compile(r"https?://" + OLD + r"newmoca/photo\.asp", re.I), "/newmoca/photo.html"),
    # a Google Translate link to the old About page
    (re.compile(r"https?://translate\.googleusercontent\.com/translate_c\?[^\"']*u=https?://" + OLD + r"/about\.htm[^\"']*", re.I), "/deutsch/about_d.htm"),
    # absolute links to the old domain become site-relative
    (re.compile(r"https?://" + OLD + r"(?=[/\"'?#])", re.I), ""),
    # the shared footer line
    (re.compile(r"\s*Formerly moca\.virtual\.museum and mocadigitalart\.com\."), ""),
    # history paragraphs about the old .museum domain
    (re.compile(r"MOCA was awarded \.?museum top-level domain \(TLD\) status by the Museum Domain Management Association \(MuseDoma\) in 2002\. "
                r"It is registered under ICANN authority and hosted on the Web as " + OLD + r"\. It can also be accessed as museumofcomputerart\.com(?: and as museumofcomputerart\.org)?\."),
     "MOCA is on the Web at museumofcomputerart.org."),
    (re.compile(r"MOCA was awarded \.?museum top-level domain \(TLD\) status by the Museum Domain Management Association \(MuseDoma\) in 2002\. "
                r"It is registered under ICANN authority and hosted on the Web as:(<br>\s*)<a href=\"/\">" + OLD + r"</a></p><p>It can also be accessed as:.*?museumofcomputerart\.org</a></p>"),
     r'MOCA is on the Web at:\1<a href="/">museumofcomputerart.org</a></p>'),
    (re.compile(r"It is registered under ICANN authority and hosted on the Web as:", re.I), "MOCA is on the Web at:"),
    (re.compile(r"This site is complementary to and cross-linked to " + OLD + r"\.", re.I), "This section complements the main MOCA collection."),
    (re.compile(r"A complementery site housed at and cross-linked to " + OLD + r" and focused on", re.I), "A companion collection at MOCA, focused on"),
    # titles of the two saved front pages
    (re.compile(OLD + r" front page", re.I), "Original MOCA front page"),
    (re.compile(r"\bfrom " + OLD + r" and mocadigitalart\.com", re.I), "from the old MOCA websites"),
    # the name written in capitals as a heading or caption
    (re.compile(r"MOCA\.VIRTUAL\.MUSEUM"), "MUSEUM OF COMPUTER ART"),
    # moved page folders, in links, og:url, sitemap and search index
    *[(re.compile(r"(?<![\w.-])" + re.escape(o)), n) for o, n in MOVED.items()],
    *[(re.compile(r"(?<=https://museumofcomputerart\.org)" + re.escape(o)), n) for o, n in MOVED.items()],
    *[(re.compile(r"(?<![\w./-])" + re.escape(o[1:])), n[1:]) for o, n in MOVED.items()],  # old paths shown as text
    # anything else: the name as text
    (re.compile(OLD, re.I), NEW_HOST),
]


def clean(text):
    """Return text with the old name replaced. Archive and media URLs are left alone."""
    kept = []

    def stash(m):
        kept.append(m.group(0))
        return f"\x00{len(kept) - 1}\x00"

    text = _KEEP.sub(stash, text)
    for pat, rep in _RULES:
        text = pat.sub(rep, text)
    return re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], text)


def moved_path(url):
    """New address for a page whose old address contained the retired name."""
    for o, n in MOVED.items():
        if url.startswith(o):
            return n + url[len(o):]
    return url


def _files(site):
    for d, _, names in os.walk(site):
        for n in names:
            if n.lower().endswith((".htm", ".html", ".xml", ".json", ".txt")):
                yield os.path.join(d, n)


def count(site):
    pat = re.compile(r"virtual\.museum", re.I)
    total, left = 0, {}
    for p in _files(site):
        with open(p, encoding="utf-8", errors="surrogateescape") as f:
            s = _KEEP.sub("", f.read())
        n = len(pat.findall(s))
        if n:
            total += n
            left[os.path.relpath(p, site)] = n
    return total, left


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    site = os.path.join(root, "site")
    if "--check" not in argv:
        for o, n in MOVED.items():
            src, dst = os.path.join(site, o.strip("/")), os.path.join(site, n.strip("/"))
            if os.path.exists(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, dst)
        changed = 0
        for p in _files(site):
            with open(p, encoding="utf-8", errors="surrogateescape") as f:
                s = f.read()
            t = clean(s)
            if t != s:
                with open(p, "w", encoding="utf-8", errors="surrogateescape") as f:
                    f.write(t)
                changed += 1
        print(f"rewrote {changed} files")
    total, left = count(site)
    print(f"{total} mentions left outside archive and media URLs")
    for p, n in sorted(left.items(), key=lambda x: -x[1])[:20]:
        print(f"  {n:4} {p}")


if __name__ == "__main__":
    main(sys.argv[1:])
