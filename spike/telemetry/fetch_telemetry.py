"""Забрати пакети телеметрії з R2 у локальну теку (далі — analyze_telemetry.py).

    python spike/telemetry/fetch_telemetry.py ./dump [--since 2026-08-01]

⚠️ Навіщо окремий скрипт. README раніше радив
    wrangler r2 object get streif-telemetry --prefix telemetry/ --local-directory ./dump
але в wrangler 4.115 `r2 object get` бере РІВНО ОДИН об'єкт (`<bucket>/<key>`) — ні `--prefix`, ні
`--local-directory` не існує, і команда просто впаде. Перевірено 2026-07-29 на живому wrangler.

Автентифікація — ті самі змінні середовища, що в `spike/pipeline/upload_r2.py`, щоб не заводити
другий спосіб логінитись в R2:
    R2_ACCOUNT_ID · R2_ACCESS_KEY · R2_SECRET_KEY

⚠️ ТИМЧАСОВИЙ, як і вся тека: прибирається разом із телеметрією після закритого тесту.
"""
import os
import sys

import boto3
from botocore.config import Config

BUCKET = os.environ.get("R2_TELEMETRY_BUCKET", "streif-telemetry")
PREFIX = "telemetry/"


def main() -> int:
    args = [a for a in sys.argv[1:]]
    since = ""
    for a in list(args):
        if a.startswith("--since="):
            since = a[len("--since="):]
            args.remove(a)
    outdir = args[0] if args else "./dump"

    try:
        account = os.environ["R2_ACCOUNT_ID"]
        key_id = os.environ["R2_ACCESS_KEY"]
        secret = os.environ["R2_SECRET_KEY"]
    except KeyError as e:
        print(f"нема змінної середовища {e}. Потрібні R2_ACCOUNT_ID / R2_ACCESS_KEY / R2_SECRET_KEY "
              f"(ті самі, що для upload_r2.py).")
        return 2

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        config=Config(retries={"max_attempts": 5, "mode": "standard"},
                      s3={"addressing_style": "path"}),
        region_name="auto",
    )

    os.makedirs(outdir, exist_ok=True)
    got = skipped = 0
    # Ключі мають вигляд telemetry/<РРРР-ММ-ДД>/<install>-<ts>.json, тож `--since` — звичайне
    # порівняння рядків по даті в ключі: сортування ISO-дати збігається з хронологічним.
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if since:
                parts = key.split("/")
                if len(parts) < 3 or parts[1] < since:
                    skipped += 1
                    continue
            # Пласко: analyze_telemetry.py читає теку, а не дерево. Ім'я файла лишаємо унікальним
            # (день + install + ts), тож колізій між днями не буде.
            dest = os.path.join(outdir, key[len(PREFIX):].replace("/", "_"))
            if os.path.exists(dest):
                skipped += 1
                continue
            s3.download_file(BUCKET, key, dest)
            got += 1

    print(f"завантажено: {got}, пропущено (вже є або поза --since): {skipped} → {outdir}")
    print(f"далі: python spike/telemetry/analyze_telemetry.py {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
