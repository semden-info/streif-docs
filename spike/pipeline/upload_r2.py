# -*- coding: utf-8 -*-
"""Upload gzipped Streif tiles to Cloudflare R2 via S3 API (boto3). Creds from env."""
import os, sys, glob, boto3
from botocore.config import Config

ACCOUNT = os.environ["R2_ACCOUNT_ID"]
AK = os.environ["R2_ACCESS_KEY"]
SK = os.environ["R2_SECRET_KEY"]
BUCKET = os.environ.get("R2_BUCKET", "streif-tiles")
TILES = sys.argv[1]

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{ACCOUNT}.r2.cloudflarestorage.com",
    aws_access_key_id=AK,
    aws_secret_access_key=SK,
    region_name="auto",
    config=Config(retries={"max_attempts": 5, "mode": "standard"}, s3={"addressing_style": "path"}),
)

files = sorted(glob.glob(os.path.join(TILES, "*.geojson")))
print(f"uploading {len(files)} tiles -> r2://{BUCKET}")
extra = {
    "ContentType": "application/json",          # тип РОЗПАКОВАНОГО вмісту
    "ContentEncoding": "gzip",                  # файли передстиснені
    "CacheControl": "public, max-age=3600, stale-while-revalidate=86400",
}
done = 0
for f in files:
    key = os.path.basename(f)                   # area_{la}_{lo}.geojson
    s3.upload_file(f, BUCKET, key, ExtraArgs=extra)
    done += 1
    if done % 50 == 0 or done == len(files):
        print(f"  {done}/{len(files)}")
print("DONE")

# P18: manifest.json — окремо, БЕЗ gzip (малий; свіжіший cache). Має лежати в тому ж каталозі TILES.
mf = os.path.join(TILES, "manifest.json")
if os.path.exists(mf):
    s3.upload_file(mf, BUCKET, "manifest.json", ExtraArgs={
        "ContentType": "application/json",
        "CacheControl": "public, max-age=300, stale-while-revalidate=3600",
    })
    print("uploaded manifest.json (uncompressed)")
else:
    print(f"WARN: {mf} не знайдено — скопіюй manifest.json (uncompressed) у {TILES} перед заливкою")

# verify: HEAD one object
head = s3.head_object(Bucket=BUCKET, Key="area_3107_304.geojson")
print(f"verify area_3107_304.geojson: {head['ContentLength']} bytes, "
      f"CT={head.get('ContentType')}, CE={head.get('ContentEncoding')}, CC={head.get('CacheControl')}")
