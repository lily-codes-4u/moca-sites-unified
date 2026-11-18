#!/usr/bin/env python3
"""Upload every MOCA media file to the Cloudflare R2 bucket.

Originals are read straight from the two server backups (no copies needed),
using media-map-originals.tsv (key <TAB> path-under-$HOME <TAB> size).
Generated WebP/MP4 versions are read from the variants folder.
Safe to re-run: objects already in the bucket with the same size are skipped.

  pip3 install boto3
  export R2_ACCOUNT_ID=...  R2_ACCESS_KEY_ID=...  R2_SECRET_ACCESS_KEY=...
  python3 upload_r2.py --bucket moca-media \
      --map ~/Code/moca-sites-unified-transfer/media-map-originals.tsv \
      --variants ~/Code/moca-media-variants
"""
import argparse
import mimetypes
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

TYPES = {".webp": "image/webp", ".mp4": "video/mp4", ".swf": "application/x-shockwave-flash", ".mid": "audio/midi",
         ".midi": "audio/midi", ".psd": "image/vnd.adobe.photoshop", ".mov": "video/quicktime", ".flv": "video/x-flv",
         ".rm": "application/vnd.rn-realmedia", ".wmv": "video/x-ms-wmv", ".avi": "video/x-msvideo", ".mpg": "video/mpeg",
         ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".png": "image/png", ".bmp": "image/bmp",
         ".tif": "image/tiff", ".tiff": "image/tiff", ".tga": "image/x-tga", ".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8"}


def ctype(key):
    ext = os.path.splitext(key)[1].lower().strip()
    return TYPES.get(ext) or mimetypes.guess_type(key)[0] or "application/octet-stream"


def client(workers=24):
    """An S3 client for the R2 account in the R2_* environment variables."""
    import boto3
    from botocore.config import Config
    return boto3.client("s3", endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
                        region_name="auto", config=Config(retries={"max_attempts": 8, "mode": "adaptive"}, max_pool_connections=workers * 2))


def existing(s3, bucket, prefix=""):
    """{key: size} of the objects already in the bucket (under prefix)."""
    out = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for o in page.get("Contents", []):
            out[o["Key"]] = o["Size"]
    return out


def upload(s3, bucket, jobs, have, workers=24):
    """Upload (key, local path, size) jobs, skipping keys already in `have` with the same size.
    Returns the list of (key, error) failures."""
    todo = [j for j in jobs if have.get(j[0]) != j[2]]
    print(f"{len(jobs) - len(todo)} already uploaded, {len(todo)} to go", flush=True)
    lock, done, failed = threading.Lock(), [0], []

    def put(job):
        key, path, size = job
        with open(path, "rb") as fh:
            s3.put_object(Bucket=bucket, Key=key, Body=fh, ContentType=ctype(key),
                          CacheControl="public, max-age=31536000, immutable")
        return key

    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(put, j): j for j in todo}
        for f in as_completed(futs):
            try:
                f.result()
            except Exception as e:
                failed.append((futs[f][0], str(e)))
            with lock:
                done[0] += 1
                if done[0] % 500 == 0:
                    print(f"{done[0]}/{len(todo)}", flush=True)
    print(f"finished: {len(todo) - len(failed)} uploaded, {len(failed)} failed", flush=True)
    for k, e in failed[:50]:
        print("FAILED", k, e)
    return failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default="moca-media")
    ap.add_argument("--map", required=True)
    ap.add_argument("--variants", required=True)
    ap.add_argument("--home", default=os.path.expanduser("~"))
    ap.add_argument("--workers", type=int, default=24)
    a = ap.parse_args()
    s3 = client(a.workers)
    jobs = []
    for line in open(a.map, encoding="utf-8"):
        key, rel, size = line.rstrip("\n").split("\t")
        jobs.append((key, os.path.join(a.home, rel), int(size)))
    for root, _, files in os.walk(a.variants):
        for f in files:
            if f.startswith("."):
                continue
            full = os.path.join(root, f)
            jobs.append((os.path.relpath(full, a.variants), full, os.path.getsize(full)))
    print(f"{len(jobs)} files, {sum(j[2] for j in jobs) / 1e9:.2f} GB", flush=True)
    failed = upload(s3, a.bucket, jobs, existing(s3, a.bucket), a.workers)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
