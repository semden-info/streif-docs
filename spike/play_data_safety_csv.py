"""Згенерувати CSV для імпорту в Play Console → Безпека даних.

    python spike/play_data_safety_csv.py <експорт із консолі> <файл для імпорту>

Джерело правди — `docs/play-data-safety.md` §2.1-2.5. Кожне значення нижче має там обґрунтування;
якщо міняєш тут — міняй і там, інакше документ і форма розійдуться (а рецензент Play читає обидва).

⚠️ **Формат критичний, не лише зміст.** Перша версія робила `DictReader` → `DictWriter`, і Play
відхилив файл із «Не вдалося завантажити»: `utf-8-sig` дописував BOM (в експорті його немає), а
writer додавав перенос у кінці (в експорті його теж немає). Тому тут файл обробляється **порядково**
й переписуються ЛИШЕ ті рядки, що справді змінились — решта віддається байт-у-байт.
"""
import csv
import io
import sys

SRC, DST = sys.argv[1], sys.argv[2]

# ── типи, які ми декларуємо (решта — не збираємо) ────────────────────────────────────────────────
# ephemeral · user control · purposes
USAGE = {
    # §2.1 — тайли ефемерні, АЛЕ телеметрія зберігає tettsted прогулянки в R2 до кінця тесту,
    # тож «уся категорія ефемерна» = ні. Analytics — саме через цей tettsted.
    "PSL_APPROX_LOCATION": (False, "REQUIRED", ["PSL_APP_FUNCTIONALITY", "PSL_ANALYTICS"]),
    # §2.2 — у «precise» нас заводять ЛИШЕ запити тайлів; точних координат телеметрія не несе
    # (гард noModelFieldCanCarryACoordinate), зберігати нема чого.
    "PSL_PRECISE_LOCATION": (True, "REQUIRED", ["PSL_APP_FUNCTIONALITY"]),
    # §2.4 — email приходить лише з Google-входу, а він вимкнений за замовчуванням (D26).
    "PSL_EMAIL": (False, "OPTIONAL", ["PSL_APP_FUNCTIONALITY"]),
    # §2.4 + §2.5 — прогрес у власний Drive (функціональність) + підсумки прогулянок до нас (аналітика).
    "PSL_USER_INTERACTION": (False, "OPTIONAL", ["PSL_APP_FUNCTIONALITY", "PSL_ANALYTICS"]),
    # §2.5 — лічильники невдач завантаження зон і синку. Жодного crash/analytics SDK у застосунку немає.
    "PSL_PERFORMANCE_DIAGNOSTICS": (False, "OPTIONAL", ["PSL_APP_FUNCTIONALITY", "PSL_ANALYTICS"]),
    # §2.5 — випадковий UUID на встановлення (Play прямо називає прикладом «Firebase installation ID»).
    "PSL_DEVICE_ID": (False, "OPTIONAL", ["PSL_APP_FUNCTIONALITY", "PSL_ANALYTICS"]),
}

# ⚠️ Знімаємо: crash-логів ми НЕ збираємо. Жодного crash-SDK немає; телеметрія шле лічильники, а це
# «diagnostics», не «crash logs». Play Vitals збирає падіння сам — це збір Google, не наш.
UNSELECT = {("PSL_DATA_TYPES_APP_PERFORMANCE", "PSL_CRASH_LOGS")}

Q, R, V = "Question ID (machine readable)", "Response ID (machine readable)", "Response value"


def encode(fields):
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(fields)
    return buf.getvalue()


def wanted(q, resp, old):
    """Яке значення має бути в цьому рядку; None = не чіпати."""
    if (q, resp) in UNSELECT:
        return "" if old else None
    if not q.startswith("PSL_DATA_USAGE_RESPONSES:"):
        return None
    parts = q.split(":")
    if len(parts) < 3 or parts[1] not in USAGE:
        return None
    ephemeral, control, purposes = USAGE[parts[1]]
    key = parts[2]
    if key == "PSL_DATA_USAGE_COLLECTION_AND_SHARING":
        # Тільки збираємо. Shared скрізь «ні»: дані йдуть на НАШ воркер і в НАШЕ приватне відро,
        # Cloudflare — обробник, не отримувач.
        return "true" if resp == "PSL_DATA_USAGE_ONLY_COLLECTED" else ""
    if key == "PSL_DATA_USAGE_EPHEMERAL":
        return "true" if ephemeral else "false"
    if key == "DATA_USAGE_USER_CONTROL":
        return "true" if resp.endswith(control) else ""
    if key == "DATA_USAGE_COLLECTION_PURPOSE":
        return "true" if resp in purposes else ""
    if key == "DATA_USAGE_SHARING_PURPOSE":
        return ""          # нічого не передаємо → мета передавання порожня
    return None


raw = open(SRC, encoding="utf-8", newline="").read()
lines = raw.split("\r\n")
header = next(csv.reader([lines[0]]))
iq, ir, iv = header.index(Q), header.index(R), header.index(V)

out = [lines[0]]
changes = []
for line in lines[1:]:
    if not line:
        out.append(line)
        continue
    fields = next(csv.reader([line]))
    new = wanted(fields[iq], fields[ir], fields[iv])
    if new is None or new == fields[iv]:
        out.append(line)                       # незмінене — віддаємо ОРИГІНАЛЬНИЙ текст
        continue
    changes.append("%-28s %-38s %-34s → %s" % (
        fields[iq].split(":")[1] if ":" in fields[iq] else fields[iq],
        fields[iq].split(":")[2] if fields[iq].count(":") >= 2 else "",
        fields[ir] or "(значення)", new or "(порожньо)"))
    fields[iv] = new
    out.append(encode(fields))

# Без BOM і без переносу в кінці — точно як в експорті.
with open(DST, "w", encoding="utf-8", newline="") as f:
    f.write("\r\n".join(out))

print(f"змін: {len(changes)}")
for c in changes:
    print("  ", c)
print(f"\nзаписано: {DST}")
