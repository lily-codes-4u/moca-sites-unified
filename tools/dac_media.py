#!/usr/bin/env python3
"""Make the web versions of the Don Archer Collection media the site shows, and upload them to R2.

Pages built from the Don Archer Collection (the /studio/ archive and the old Don Archer
websites) show media under the R2 key prefix dac/: the collection path, lowercased, after
"dac/" (e.g. "1998/U-DRAW44/GIF/44FOO.GIF" -> "dac/1998/u-draw44/gif/44foo.gif"). Each lane
that built pages wrote an upload map, tools/dac-media-<lane>.tsv, with one row per original:
key <TAB> path relative to the Don Archer Collection folder <TAB> bytes.

For each row this script
  * images (jpg, gif, png, bmp, tif, tga, psd, pcx, webp): writes <key>.w480.webp always (never
    enlarged), <key>.w800.webp when the original is at least 800px wide and <key>.w1600.webp when
    it is at least 1600px wide (see variant_widths, which the page generator uses too);
  * video (mov, avi, mpg, wmv, flv, m4v, mp4): writes <key>.mp4 (H.264, needs ffmpeg) and
    <key>.poster.webp (a frame one second in);
  * anything else (MIDI, ...): nothing to make, the original is uploaded as it is;
then uploads every original and every web version to the bucket, skipping objects that are
already there with the same size (tools/upload_r2.py does the uploading).

It is safe to stop and run again: web versions already made (and newer than their original) are
kept, and uploaded objects are skipped.

Run on the Mac that holds the collection (python3 with Pillow; ffmpeg for the one video):

  pip3 install Pillow boto3
  export R2_ACCOUNT_ID=...  R2_ACCESS_KEY_ID=...  R2_SECRET_ACCESS_KEY=...
  python3 tools/dac_media.py --bucket moca-media \\
      --root "$HOME/Desktop/Don Archer Collection" \\
      --out "$HOME/Code/dac-media-variants" \\
      tools/dac-media-studio.tsv tools/dac-media-webarchive.tsv

Add --dry-run first to see what would be made and uploaded (nothing is written or uploaded,
no R2 credentials needed). --no-upload only makes the web versions; --no-variants only uploads.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor

VARIANT_WIDTHS = (480, 800, 1600)
IMAGE_EXT = (".jpg", ".jpeg", ".gif", ".png", ".bmp", ".tif", ".tiff", ".tga", ".psd", ".pcx", ".webp")
VIDEO_EXT = (".mov", ".avi", ".mpg", ".mpeg", ".wmv", ".flv", ".m4v", ".mp4")


def variant_widths(width):
    """The WebP widths made for an image `width` pixels wide: 480 always (at the original size
    when it is narrower), 800 and 1600 only when the original is at least that wide."""
    return [v for v in VARIANT_WIDTHS if v == VARIANT_WIDTHS[0] or (width or 0) >= v]


def outputs_for(key, width=None):
    """The web versions made for one original: [(suffix, kind)]."""
    ext = os.path.splitext(key)[1].lower()
    if ext in IMAGE_EXT:
        return [(f".w{v}.webp", v) for v in variant_widths(width if width is not None else 10 ** 6)]
    if ext in VIDEO_EXT:
        return [(".mp4", "mp4"), (".poster.webp", "poster")]
    return []


def read_maps(paths):
    rows, seen = [], set()
    for p in paths:
        for n, line in enumerate(open(p, encoding="utf-8"), 1):
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            key, rel, size = line.split("\t")
            if not key.startswith("dac/"):
                sys.exit(f"{p}:{n}: key does not start with dac/: {key}")
            if key in seen:
                continue
            seen.add(key)
            rows.append((key, rel, int(size)))
    return rows


def _fresh(out, src):
    return os.path.exists(out) and os.path.getsize(out) > 0 and os.path.getmtime(out) >= os.path.getmtime(src)


def _open_rgb(path):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(path)
    try:
        im.seek(0)  # first frame of an animated GIF
    except EOFError:
        pass
    alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
    if im.mode.startswith("I;16") or im.mode == "I":
        im = im.point(lambda x: x / 256).convert("L")
    return im.convert("RGBA" if alpha else "RGB")


def make_image(job):
    """job: (source path, output stem). Returns (made, error)."""
    src, stem = job
    from PIL import Image
    try:
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(src) as probe:  # reads the header only
            width = probe.width
        todo = [v for v in variant_widths(width) if not _fresh(f"{stem}.w{v}.webp", src)]
        if not todo:
            return 0, None
        im = _open_rgb(src)
        made = 0
        for v in todo:
            out = f"{stem}.w{v}.webp"
            w = min(v, im.width)
            h = max(1, round(im.height * w / im.width))
            small = im if w == im.width else im.resize((w, h), Image.LANCZOS)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            small.save(out + ".part", "WEBP", quality=82, method=4)
            os.replace(out + ".part", out)
            made += 1
        return made, None
    except Exception as e:  # keep going; the list of failures is printed at the end
        return 0, f"{type(e).__name__}: {e}"


def make_video(job):
    src, stem = job
    if not shutil.which("ffmpeg"):
        return 0, "ffmpeg not installed"
    made = 0
    try:
        mp4 = stem + ".mp4"
        if not _fresh(mp4, src):
            os.makedirs(os.path.dirname(mp4), exist_ok=True)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-vf", "scale='min(1280,iw)':-2", "-c:v", "libx264",
                            "-crf", "23", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                            "-c:a", "aac", "-b:a", "128k", "-f", "mp4", mp4 + ".part"], check=True)
            os.replace(mp4 + ".part", mp4)
            made += 1
        poster = stem + ".poster.webp"
        if not _fresh(poster, src):
            with tempfile.TemporaryDirectory() as td:
                png = os.path.join(td, "frame.png")
                for ss in ("1", "0"):
                    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", ss, "-i", src, "-frames:v", "1", png], check=False)
                    if os.path.exists(png):
                        break
                im = _open_rgb(png)
                if im.width > 1600:
                    from PIL import Image
                    im = im.resize((1600, round(im.height * 1600 / im.width)), Image.LANCZOS)
                im.save(poster + ".part", "WEBP", quality=82, method=4)
                os.replace(poster + ".part", poster)
                made += 1
        return made, None
    except Exception as e:
        return made, f"{type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("maps", nargs="+", help="tools/dac-media-<lane>.tsv files")
    ap.add_argument("--root", required=True, help="the Don Archer Collection folder")
    ap.add_argument("--out", required=True, help="folder for the web versions (same key layout)")
    ap.add_argument("--bucket", default="moca-media")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--dry-run", action="store_true", help="only report what would be made and uploaded")
    ap.add_argument("--no-variants", action="store_true", help="do not make web versions")
    ap.add_argument("--no-upload", action="store_true", help="do not upload")
    a = ap.parse_args()

    rows = read_maps(a.maps)
    missing, present = [], []
    for key, rel, size in rows:
        src = os.path.join(a.root, rel)
        (present if os.path.isfile(src) else missing).append((key, src, size))
    print(f"{len(rows)} originals in {len(a.maps)} map(s), {sum(r[2] for r in rows) / 1e9:.2f} GB; {len(missing)} not found under --root")
    for key, src, _ in missing[:20]:
        print("  MISSING", src)

    img_jobs = [(src, os.path.join(a.out, key)) for key, src, _ in present if key.lower().endswith(IMAGE_EXT)]
    vid_jobs = [(src, os.path.join(a.out, key)) for key, src, _ in present if key.lower().endswith(VIDEO_EXT)]
    print(f"web versions: {len(img_jobs)} images (up to {len(VARIANT_WIDTHS)} WebP sizes each), {len(vid_jobs)} videos (MP4 + poster)")
    if vid_jobs and not shutil.which("ffmpeg"):
        print("  ffmpeg is not installed: the video MP4 and poster will be skipped (brew install ffmpeg)")
    if a.dry_run:
        todo = sum(1 for src, stem in img_jobs if not _fresh(f"{stem}.w480.webp", src))
        print(f"dry run: {todo} images still need web versions; nothing was written or uploaded")
        return

    failed = []
    if not a.no_variants:
        with ProcessPoolExecutor(a.workers) as ex:
            done = 0
            for (src, _), (made, err) in zip(img_jobs, ex.map(make_image, img_jobs, chunksize=8)):
                done += 1
                if err:
                    failed.append((src, err))
                if done % 500 == 0:
                    print(f"  {done}/{len(img_jobs)} images", flush=True)
        for job in vid_jobs:
            made, err = make_video(job)
            if err:
                failed.append((job[0], err))
        print(f"web versions done, {len(failed)} originals could not be converted")
        for src, err in failed[:50]:
            print("  FAILED", src, err)

    if a.no_upload:
        return
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import upload_r2
    jobs = []
    for key, src, _ in present:
        jobs.append((key, src, os.path.getsize(src)))
        for suffix, _ in outputs_for(key):
            out = os.path.join(a.out, key + suffix)
            if os.path.isfile(out):
                jobs.append((key + suffix, out, os.path.getsize(out)))
    print(f"upload: {len(jobs)} files, {sum(j[2] for j in jobs) / 1e9:.2f} GB", flush=True)
    s3 = upload_r2.client(min(a.workers * 3, 32))
    bad = upload_r2.upload(s3, a.bucket, jobs, upload_r2.existing(s3, a.bucket, "dac/"), min(a.workers * 3, 32))
    sys.exit(1 if bad or failed or missing else 0)


if __name__ == "__main__":
    main()
