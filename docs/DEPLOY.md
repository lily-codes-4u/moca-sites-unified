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
3. `site/CNAME` already contains `museumofcomputerart.org`. After DNS (step 2) works, tick **Enforce HTTPS** on the Pages settings page.

## 2. Cloudflare DNS for museumofcomputerart.org

Add the domain to Cloudflare (free plan) and point the registrar's nameservers at Cloudflare. Then in **DNS**:

| Type | Name | Content | Proxy |
|---|---|---|---|
| A | `@` | 185.199.108.153 | Proxied |
| A | `@` | 185.199.109.153 | Proxied |
| A | `@` | 185.199.110.153 | Proxied |
| A | `@` | 185.199.111.153 | Proxied |
| CNAME | `www` | `lily-codes-4u.github.io` | Proxied |

SSL/TLS mode: **Full**. (While GitHub issues its certificate the first time, you may need to set the records to "DNS only" for a few minutes, then switch back to Proxied.)

## 3. Cloudflare R2 for media

1. **R2 → Create bucket** `moca-media`.
2. Bucket **Settings → Custom domains → Connect domain** `media.museumofcomputerart.org`.
3. Bucket **Settings → CORS**: allow `GET, HEAD` from `https://museumofcomputerart.org` (needed for the Flash player and fonts-style fetches).
4. Upload the contents of the media folder (`media/` on the build machine) with rclone:
   ```sh
   rclone config   # new remote "r2", type s3, provider Cloudflare, with an R2 API token
   rclone copy ./media r2:moca-media --transfers 32 --checkers 32 --progress \
     --header-upload "Cache-Control: public, max-age=31536000, immutable"
   ```
   Object keys are the old site paths in lowercase (for example `autogallery2023/autogallery_doodles/doodle 01.jpg`), next to their generated `…w480.webp`, `…w1600.webp`, `….mp4` and `….poster.webp` versions.

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
