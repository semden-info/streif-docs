# -*- coding: utf-8 -*-
"""Upload gzipped Streif tiles to Cloudflare R2 via S3 API (boto3). Creds from env.

Паралельно (ThreadPoolExecutor) + ПРОПУСК НЕЗМІНЕНИХ (ETag == MD5 тіла, яке ми збираємось залити).
На масштабі фюльке (~3400 тайлів) послідовна заливка ≈ 20 хв; тут — хвилини, а повторний прогін
після дрібної правки заливає лише те, що справді змінилось.

Usage:
    R2_ACCOUNT_ID=… R2_ACCESS_KEY=… R2_SECRET_KEY=… \
    python upload_r2.py TILES_DIR [--workers=12] [--force] [--dry-run] [--verify=KEY]

    --workers=N  паралельні заливки (деф. 12; R2 тримає, але 32+ ловить SlowDown)
    --force      залити все, не звіряючи ETag
    --dry-run    нічого не заливати — лише показати, що змінилось (креденшли все одно потрібні:
                 читаємо перелік об'єктів у бакеті)
    --verify=KEY HEAD цього ключа наприкінці (деф. — перший area-тайл)

⚠️ Пропуск за ETag працює, лише якщо gzip ДЕТЕРМІНОВАНИЙ. Крок 4 README має стискати з mtime=0,
   інакше кожен тайл щоразу «новий» (заллється — не зламається, просто без економії).
"""
import os, sys, glob, gzip, io, json, time, hashlib, threading
from concurrent.futures import ThreadPoolExecutor
import boto3
from botocore.config import Config

ACCOUNT = os.environ["R2_ACCOUNT_ID"]
AK = os.environ["R2_ACCESS_KEY"]
SK = os.environ["R2_SECRET_KEY"]
BUCKET = os.environ.get("R2_BUCKET", "streif-tiles")

TILES = ""
workers, force, dry, verify_key = 12, False, False, ""
for a in sys.argv[1:]:
    if a.startswith("--workers="): workers = max(1, int(a[len("--workers="):]))
    elif a == "--force": force = True
    elif a == "--dry-run": dry = True
    elif a.startswith("--verify="): verify_key = a[len("--verify="):]
    else: TILES = a
assert TILES, __doc__

CFG = Config(retries={"max_attempts": 5, "mode": "standard"},
             s3={"addressing_style": "path"},
             max_pool_connections=workers + 4)     # інакше пул душить потоки

def new_client():
    return boto3.client("s3", endpoint_url=f"https://{ACCOUNT}.r2.cloudflarestorage.com",
                        aws_access_key_id=AK, aws_secret_access_key=SK,
                        region_name="auto", config=CFG)

# boto3-клієнт формально потокобезпечний, але офіційна рекомендація — свій клієнт на потік.
_tl = threading.local()
def client():
    c = getattr(_tl, "c", None)
    if c is None:
        c = _tl.c = new_client()
    return c

def gz(data):
    """Детермінований gzip (mtime=0) — інакше ETag «змінюється» на кожному прогоні."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as g:
        g.write(data)
    return buf.getvalue()

# ---------- що заливаємо ----------
# area_*.geojson — вже передстиснені (README крок 4), тож ідуть як є з Content-Encoding: gzip.
# tettsteder/poi.geojson тим кроком НЕ стискаються → gzip у коді (інакше віддали б нестиснений
# файл із заголовком gzip = битий на клієнті). manifest.json — без стиснення, свіжіший cache.
TILE_EXTRA = {"ContentType": "application/json", "ContentEncoding": "gzip",
              "CacheControl": "public, max-age=3600, stale-while-revalidate=86400"}
PLAIN_EXTRA = {"ContentType": "application/json",
               "CacheControl": "public, max-age=300, stale-while-revalidate=3600"}
GZ_EXTRA = {"ContentType": "application/json", "ContentEncoding": "gzip",
            "CacheControl": "public, max-age=300, stale-while-revalidate=86400"}

jobs = []   # (key, path, gzip_in_code, extra)
for f in sorted(glob.glob(os.path.join(TILES, "*.geojson"))):
    if os.path.basename(f) in ("tettsteder.geojson", "poi.geojson"): continue
    jobs.append((os.path.basename(f), f, False, TILE_EXTRA))
n_tiles = len(jobs)

mf = os.path.join(TILES, "manifest.json")
if os.path.exists(mf):
    jobs.append(("manifest.json", mf, False, PLAIN_EXTRA))
else:
    print(f"WARN: {mf} не знайдено — скопіюй manifest.json (uncompressed) у {TILES} перед заливкою")
for extra_name, why in (("tettsteder.geojson", "P20"), ("poi.geojson", "D34")):
    p = os.path.join(TILES, extra_name)
    if os.path.exists(p):
        jobs.append((extra_name, p, True, GZ_EXTRA))
    elif extra_name == "tettsteder.geojson":
        print(f"WARN: {p} не знайдено — скопіюй tettsteder.geojson у {TILES} перед заливкою ({why})")

print(f"{n_tiles} тайлів + {len(jobs)-n_tiles} службових -> r2://{BUCKET} "
      f"(workers={workers}{', FORCE' if force else ''}{', DRY-RUN' if dry else ''})")

# ---------- інвентар бакета: один прохід list_objects_v2 замість HEAD на кожен ключ ----------
remote = {}
if not force:
    t0 = time.perf_counter()
    pag = new_client().get_paginator("list_objects_v2")
    for page in pag.paginate(Bucket=BUCKET):
        for o in page.get("Contents", ()):
            remote[o["Key"]] = o["ETag"].strip('"')
    print(f"у бакеті вже {len(remote)} об'єктів (перелік за {time.perf_counter()-t0:.1f} с)")

# ---------- заливка ----------
lock = threading.Lock()
stat = {"put": 0, "skip": 0, "bytes": 0, "done": 0}

def work(job):
    key, path, do_gz, extra = job
    body = open(path, "rb").read()
    if do_gz: body = gz(body)
    md5 = hashlib.md5(body).hexdigest()
    et = remote.get(key)
    # ETag із дефісом = multipart (наші об'єкти не такі) → не звіряємо, заливаємо.
    hit = (not force) and et is not None and "-" not in et and et == md5
    if not hit and not dry:
        client().put_object(Bucket=BUCKET, Key=key, Body=body, **extra)
    with lock:
        stat["done"] += 1
        if hit: stat["skip"] += 1
        else:
            stat["put"] += 1; stat["bytes"] += len(body)
        if stat["done"] % 250 == 0 or stat["done"] == len(jobs):
            print(f"  {stat['done']}/{len(jobs)}  залито {stat['put']}  пропущено {stat['skip']}")

t0 = time.perf_counter()
with ThreadPoolExecutor(max_workers=workers) as ex:
    list(ex.map(work, jobs))         # map прокидає перше ж виключення назовні — тиха втрата тайла виключена
dt = time.perf_counter() - t0
print(f"DONE за {dt:.1f} с — залито {stat['put']} ({stat['bytes']/1024/1024:.1f} MB), "
      f"пропущено незмінених {stat['skip']}"
      + (f", {len(jobs)/max(dt,0.001):.0f} об'єктів/с" if not dry else " [DRY-RUN: нічого не залито]"))

# verify: HEAD одного об'єкта (деф. — перший area-тайл цього ж прогону)
vk = verify_key or (jobs[0][0] if jobs else "")
if vk and not dry:
    h = new_client().head_object(Bucket=BUCKET, Key=vk)
    print(f"verify {vk}: {h['ContentLength']} bytes, CT={h.get('ContentType')}, "
          f"CE={h.get('ContentEncoding')}, CC={h.get('CacheControl')}")
