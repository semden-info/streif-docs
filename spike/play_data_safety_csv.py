"""Згенерувати CSV для імпорту в Play Console → Безпека даних.

Джерело правди — docs/play-data-safety.md §2.1-2.5. Кожне значення нижче має там обґрунтування;
якщо міняєш тут — міняй і там, інакше документ і форма розійдуться (а рецензент Play читає обидва).
"""
import csv
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

rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
changes = []

for row in rows:
    q, resp = row[Q], row[R]

    if (q, resp) in UNSELECT and row[V]:
        changes.append(f"ЗНЯТО   {resp}")
        row[V] = ""
        continue

    if not q.startswith("PSL_DATA_USAGE_RESPONSES:"):
        continue
    parts = q.split(":")
    if len(parts) < 3:
        continue
    dtype, key = parts[1], parts[2]
    if dtype not in USAGE:
        continue
    ephemeral, control, purposes = USAGE[dtype]

    if key == "PSL_DATA_USAGE_COLLECTION_AND_SHARING":
        # Тільки збираємо. Shared скрізь «ні»: дані йдуть на НАШ воркер і в НАШЕ приватне відро,
        # Cloudflare — обробник, не отримувач.
        new = "true" if resp == "PSL_DATA_USAGE_ONLY_COLLECTED" else ""
    elif key == "PSL_DATA_USAGE_EPHEMERAL":
        new = "true" if ephemeral else "false"
    elif key == "DATA_USAGE_USER_CONTROL":
        new = "true" if resp.endswith(control) else ""
    elif key == "DATA_USAGE_COLLECTION_PURPOSE":
        new = "true" if resp in purposes else ""
    elif key == "DATA_USAGE_SHARING_PURPOSE":
        new = ""          # нічого не передаємо → мета передавання порожня
    else:
        continue

    if new != row[V]:
        changes.append(f"{dtype:28} {key:38} {resp or '(значення)':34} → {new or '(порожньо)'}")
        row[V] = new

with open(DST, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

print(f"змін: {len(changes)}")
for c in changes:
    print("  ", c)
print(f"\nзаписано: {DST}")
