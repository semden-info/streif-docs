# Польовий тест 2026-07-05 — CC-BY+Elveg, 2 телефони

Перша прогулянка на офіційних даних Kartverket (Matrikkelen via CDN + Elveg-eligibility). ~30 хв, Volda-центр.

- `samsung/` — Galaxy S24 FE, рука, екран-on → з ✓/✗-мітками (`marks.csv` = ground truth).
- `pixel/` — Pixel 9, кишеня, екран-off → батарея (Stage C) + автотрек (без міток).

Формати: `diag.csv` = `ts,lat,lon,acc,speed,f1,f2,note,batt%,charge` · `visited.txt` = `id,type,ts` · `marks.csv` = `ts,id,mark(correct|wrong|clear),lat,lon,wasRevealed`.
⚠️ У `diag.csv` перший запис — застарілий (тест-запуск), далі >60с розрив = реальний старт.

## Результати
- **Recall 100%** (обидва), **precision 87%** (7 хибних/52), крос-девайс Jaccard 89%.
- **Батарея Stage C:** Pixel екран-off ~6%/год (повний час) / ~8%/год (актив), Samsung екран-on ~14%/год. ✅
- **Ключове (P2):** хибні розкриття НЕ розділити порогом — стіна (TP до 17 м, FP 0.2-17.4 м) і accuracy (TP 3-5 м, FP 4-7 м) перекриваються. Precision 87% ≈ межа GPS-only. Пороги не міняємо; приріст = кращі сигнали post-MVP.

Аналіз-скрипти (scratchpad, сесія 2026-07-05): `analyze_walk.py`, `combined.py`, `wall_dist.py` — потребують CC-BY-тайлів (`tiles_region`) для геометрії.
