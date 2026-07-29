"""Забрати пакети телеметрії з R2 у локальну теку (далі — analyze_telemetry.py).

    python spike/telemetry/fetch_telemetry.py ./dump [--since=2026-08-01]

Читає НЕ R2 напряму, а read-endpoint того самого воркера, що приймає телеметрію:
`GET /list` і `GET /get?key=…` під заголовком `x-streif-admin`. Потрібні дві змінні середовища
(або `--url=` / `--key=` в аргументах):

    STREIF_TELEMETRY_URL         адреса воркера (та сама, що TELEMETRY_URL у telemetry.properties)
    STREIF_TELEMETRY_ADMIN_KEY   значення секрета TELEMETRY_ADMIN_KEY

⚠️ **Чому не S3-доступ до R2, як в `upload_r2.py`.** Спершу цей скрипт ходив у R2 через boto3 з
`R2_ACCOUNT_ID`/`R2_ACCESS_KEY`/`R2_SECRET_KEY`. Дві причини відмовитись: (1) сторонній пакет, якого
на машині не було — перша ж спроба впала на `ModuleNotFoundError`; (2) головніше — ті креденшели
дають доступ до ВСІХ bucket-ів проєкту, включно з продакшн-тайлами, тобто заради читання кількох
десятків JSON-ів на диску лежав ключ від усього. Адмін-секрет воркера відкриває рівно телеметрію.

⚠️ Раніше README радив `wrangler r2 object get … --prefix … --local-directory …` — таких прапорців
у wrangler 4.115 не існує, `r2 object get` бере РІВНО ОДИН об'єкт. Перевірено 2026-07-29.

⚠️ ТИМЧАСОВИЙ, як і вся тека: прибирається разом із телеметрією після закритого тесту.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# ⚠️ Windows: консоль за замовчуванням cp1252, і будь-який кириличний рядок валить скрипт
# `UnicodeEncodeError` ще до першої цифри — те саме, що в `analyze_telemetry.py`. Спіймано тут же
# при перевірці: у PowerShell Дениса вивід був цілий, а в bash-шелі агента той самий рядок падав.
# Тут, на відміну від сусіда, страхуємо ще й stderr: усі підказки «що саме не так» ідуть саме туди,
# і без цього виходять екрановані (`не ді…`) — нечитабельні рівно тоді, коли потрібні.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

PREFIX = "telemetry/"
UA = "streif-telemetry-fetch/1.0 (+https://semden.no)"


def api(base, path, admin, params=None):
    url = base + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"x-streif-admin": admin, "user-agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 405:
            # Воркер свідомо не відрізняє «немає ключа» від «ключ не той» і від «такого шляху немає» —
            # щоб відповідь не підтверджувала, що за /list узагалі щось стоїть. Тому підказку даємо тут.
            raise SystemExit(
                "405 від воркера. Найімовірніше STREIF_TELEMETRY_ADMIN_KEY не збігається з секретом\n"
                "воркера або секрет там ще не заведено:\n"
                "    wrangler secret put TELEMETRY_ADMIN_KEY   (у spike/telemetry/worker/)")
        raise SystemExit(f"{e.code} від воркера на {path}: {e.reason}")
    except urllib.error.URLError as e:
        raise SystemExit(f"не дістався воркера ({base}): {e.reason}")


def main():
    since = url = admin = ""
    rest = []
    for a in sys.argv[1:]:
        if a.startswith("--since="):
            since = a.split("=", 1)[1]
        elif a.startswith("--url="):
            url = a.split("=", 1)[1]
        elif a.startswith("--key="):
            admin = a.split("=", 1)[1]
        else:
            rest.append(a)
    outdir = rest[0] if rest else "./dump"

    url = url or os.environ.get("STREIF_TELEMETRY_URL", "")
    admin = admin or os.environ.get("STREIF_TELEMETRY_ADMIN_KEY", "")
    if not url or not admin:
        print("Потрібні STREIF_TELEMETRY_URL і STREIF_TELEMETRY_ADMIN_KEY. У PowerShell:\n"
              '    $env:STREIF_TELEMETRY_URL = "https://…workers.dev"\n'
              '    $env:STREIF_TELEMETRY_ADMIN_KEY = "…"\n'
              "або передати аргументами: --url=… --key=…")
        return 2
    base = url.rstrip("/")

    os.makedirs(outdir, exist_ok=True)
    got = skipped = 0
    cursor = None
    seen_cursors = set()
    while True:
        params = {}
        if since:
            params["since"] = since
        if cursor:
            params["cursor"] = cursor
        page = json.loads(api(base, "/list", admin, params))

        for obj in page.get("objects", []):
            key = obj["key"]
            # Пласко: analyze_telemetry.py читає теку, а не дерево. Ім'я лишається унікальним
            # (день + install + ts), тож колізій між днями не буде.
            dest = os.path.join(outdir, key[len(PREFIX):].replace("/", "_"))
            if os.path.exists(dest):
                skipped += 1
                continue
            with open(dest, "wb") as f:
                f.write(api(base, "/get", admin, {"key": key}))
            got += 1

        # ⚠️ Іти за курсором, навіть якщо `objects` порожній: `since` воркер застосовує ПІСЛЯ вибірки
        # з R2, тож сторінка цілком може відфільтруватись у нуль, а дані бути далі.
        cursor = page.get("cursor")
        if not cursor or cursor in seen_cursors:
            break
        seen_cursors.add(cursor)

    print(f"завантажено: {got}, пропущено (вже є): {skipped} → {outdir}")
    print(f"далі: python spike/telemetry/analyze_telemetry.py {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
