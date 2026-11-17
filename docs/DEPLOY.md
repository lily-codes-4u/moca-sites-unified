# Deploying MOCA Sites Unified to museumofcomputerart.org

The site has two parts:

| Part | What | Where it is served from |
|---|---|---|
| Pages | ~13,400 HTML pages, CSS, JS, fonts, search index, sitemap (`site/`, about 150 MB) | GitHub Pages, from this repo, at `museumofcomputerart.org` |
| Media | every image, video, Flash file and original download, plus fast WebP/MP4 versions (about 6–7 GB) | Cloudflare R2 bucket `moca-media`, at `media.museumofcomputerart.org` |

GitHub Pages refuses sites over 1 GB, which is why the art lives in R2 (free tier: 10 GB storage, no bandwidth fees).
Both sit behind one free Cloudflare account, so everything is cached on Cloudflare's CDN.

## 1. GitHub Pages

1. Repo **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. Every push to `main` that changes `site/` runs `.github/workflows/pages.yml` and publishes `site/`.
3. On the same page, type `museumofcomputerart.org` under **Custom domain** and press **Save**. Sites deployed by GitHub Actions ignore the `site/CNAME` file, so this step is required.
4. After DNS (step 2) works and GitHub shows the DNS check as successful, tick **Enforce HTTPS**. The certificate can take up to an hour to appear.

## 2. Cloudflare DNS for museumofcomputerart.org

Add the domain to Cloudflare (free plan) and point the registrar's nameservers at Cloudflare. Then in **DNS**:

| Type | Name | Content | Proxy |
|---|---|---|---|
| A | `@` | 185.199.108.153 | Proxied |
| A | `@` | 185.199.109.153 | Proxied |
| A | `@` | 185.199.110.153 | Proxied |
| A | `@` | 185.199.111.153 | Proxied |
| CNAME | `www` | `lily-codes-4u.github.io` | Proxied |

Create the records as **DNS only** (grey cloud) first, so GitHub can check the domain and issue its certificate. Delete any old records for `@` or `www` left over from the previous host. Once **Enforce HTTPS** is ticked on GitHub, switch the records to **Proxied** and set SSL/TLS mode to **Full (strict)**.

## 3. Cloudflare R2 for media

1. **R2 → Create bucket** `moca-media`.
2. Bucket **Settings → Custom domains → Connect domain** `media.museumofcomputerart.org`.
3. Bucket **Settings → CORS**: allow `GET, HEAD` from `https://museumofcomputerart.org` (needed for the Flash player and fonts-style fetches).
4. **R2 → Manage API tokens → Create API token** with Object Read & Write on `moca-media`. Note the Account ID, Access Key ID and Secret Access Key.
5. On the Mac that holds the backups, upload everything (originals straight from the backups, plus the WebP/MP4 versions in `~/Code/moca-media-variants`). It is safe to stop and re-run:
   ```sh
   pip3 install boto3
   export R2_ACCOUNT_ID=...  R2_ACCESS_KEY_ID=...  R2_SECRET_ACCESS_KEY=...
   python3 tools/upload_r2.py --bucket moca-media \
       --map ~/Code/moca-sites-unified-transfer/media-map-originals.tsv \
       --variants ~/Code/moca-media-variants
   ```
   Object keys are the old site paths in lowercase (for example `autogallery2023/autogallery_doodles/doodle 01.jpg`), next to their generated `…w480.webp`, `…w1600.webp`, `….mp4` and `….poster.webp` versions.
6. Upload the files recovered after the backups were made (listed in `tools/recovered_media.json`, staged in the transfer folder as `recovered/`, `recovered-variants/` and `recovered-map.tsv`). Their map paths are relative to the transfer folder, hence `--home`:
   ```sh
   python3 tools/upload_r2.py --bucket moca-media \
       --map ~/Code/moca-sites-unified-transfer/recovered-map.tsv \
       --home ~/Code/moca-sites-unified-transfer \
       --variants ~/Code/moca-sites-unified-transfer/recovered-variants
   ```
   Pages only show these files from the commit that adds them to `tools/recovered_media.json` on, so upload before merging it.

## 4. Old domains and old links

Every old page keeps its path. Add both old domains to the same Cloudflare account and create these **Rules → Redirect Rules** (free plan allows 10):

1. `moca.virtual.museum` and `www.moca.virtual.museum`, all paths → `https://museumofcomputerart.org${path}` (301, keep query string). Dynamic expression: `concat("https://museumofcomputerart.org", http.request.uri.path)`.
2. Same for `mocadigitalart.com` and `www.mocadigitalart.com`.
3. Requests on `museumofcomputerart.org` for files ending in `.jpg .jpeg .gif .png .bmp .swf .mov .mp4 .flv .avi .wmv .mid .psd .pdf` → `https://media.museumofcomputerart.org` + `lower(http.request.uri.path)` (301). This keeps old image hotlinks working.

Everything else is handled in the browser by `site/404.html`: it lowercases mixed-case paths, maps `.asp` links to `.html`, maps `.htm`↔`.html`, and turns old AutoGallery image links (`index_q_mode-view-Image-13-ReturnPage-5.html` or `index.asp?Image=13`) into `/folder/#image-13`.

Optional Cloudflare speed settings: **Speed → Optimization**: Brotli on, Early Hints on, HTTP/3 on. **Caching → Browser Cache TTL**: respect existing headers.

## 5. Rebuilding

```sh
pip install beautifulsoup4 lxml pillow
MOCA_MERGED=/path/to/merged MOCA_MERGED_JSON=/path/to/merged.json \
MOCA_MEDIA_JSON=/path/to/media.json python3 tools/build.py
```
`MOCA_MEDIA_BASE` changes where media is loaded from (default `https://media.museumofcomputerart.org`).

## 6. The retired moca.virtual.museum name

`tools/rebrand.py` removes the old name from every published page: old email addresses become `hello@museumofcomputerart.org`, links to the old domain become site links, and the old name in text and headings is replaced. `build.py` runs it on every page, and `python3 tools/rebrand.py` cleans an already built `site/` in place (`--check` only counts what is left). Pages that lived under `/imofday/moca.virtual.museum/` are now under `/imofday/archive/`, and `/legacy/moca-virtual-museum-home*.html` are now `/legacy/moca-home*.html`; `404.html` redirects the old addresses.

Kept on purpose: the Cloudflare redirect rule above, the old domain in `OUR_HOSTS` in `tools/legacy.py`, Internet Archive links, the PayPal account address in donate forms, and media URLs. The R2 object keys under `imofday/moca.virtual.museum/` still use the old folder name; visitors never see them. Renaming them would mean changing the keys in `media-map-originals.tsv` and the variant folder, then running `upload_r2.py` again.
