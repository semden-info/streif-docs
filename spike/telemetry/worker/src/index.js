/**
 * D39 — приймач телеметрії закритого тесту: Cloudflare Worker → R2.
 *
 * Свідомо примітивний. Це не «аналітичний бекенд», а труба: прийняти рядок, перевірити, покласти
 * об'єкт у R2. Жодної БД, жодного стану, жодних агрегацій на льоту — усе рахує Python-скрипт поруч
 * (`analyze_telemetry.py`), бо саме там уже живе аналіз польових даних.
 *
 * **Один запит = один об'єкт у R2.** R2 не вміє append, а городити читання-злиття-запис заради
 * дописування рядка означало б гонки на рівному місці. Об'єктів буде мало: кілька тестерів × раз на
 * добу — це десятки на місяць, і `list` по них дешевий.
 *
 * ⚠️ **Чого цей воркер НЕ пише в R2 — і це головне:**
 *  • **IP-адреси.** `cf-connecting-ip` є в кожному запиті й це персональні дані за GDPR. Записати
 *    його означало б перетворити «знеособлену статистику» на прив'язану до людини — тобто збрехати
 *    в тексті згоди. Не читаємо взагалі;
 *  • **нічого, що схоже на координати** — див. `looksLikeLocation`. Клієнт це вже гарантує тестом,
 *    але клієнт може відкотитись, а стара збірка лишитись у когось на телефоні. Дешевше відмовити
 *    тут, ніж потім чистити відро.
 */

/** Стеля розміру тіла. Реальний пакет — одиниці кілобайт; усе більше або баг, або не наше. */
const MAX_BYTES = 256 * 1024;

/**
 * Ключі, яких у пакеті бути не може. Дзеркалить `TelemetryTest.noModelFieldCanCarryACoordinate`
 * на боці клієнта — та сама перевірка з іншого кінця дроту.
 */
const BANNED = ['lat', 'lon', 'lng', 'coord', 'point', 'geometry', 'track', 'path', 'route'];

function looksLikeLocation(obj, depth = 0) {
  if (depth > 6 || obj === null || typeof obj !== 'object') return false;
  for (const [k, v] of Object.entries(obj)) {
    const key = k.toLowerCase();
    if (BANNED.some((b) => key.includes(b))) return true;
    if (typeof v === 'object' && looksLikeLocation(v, depth + 1)) return true;
  }
  return false;
}

/** `2026-07-27` — префікс дня, щоб `list` і вибірка за період були тривіальні. */
function dayKey(ms) {
  return new Date(ms).toISOString().slice(0, 10);
}

/** Тільки [a-z0-9-], обрізано: id приходить ззовні й лізе в ключ об'єкта. */
function safeId(s) {
  return String(s || 'unknown').toLowerCase().replace(/[^a-z0-9-]/g, '').slice(0, 40) || 'unknown';
}

export default {
  async fetch(request, env, ctx) {
    if (request.method !== 'POST') {
      // GET сюди приходить від сканерів і від самого Дениса «а чи живе воно». Відповідаємо коротко
      // й без подробиць: адреса приймача не має розповідати, що саме за нею стоїть.
      return new Response('streif telemetry\n', { status: 405 });
    }

    // Спільний секрет. Він лежить у APK і теоретично витягується — це не автентифікація, а фільтр
    // від випадкового трафіку: без нього будь-хто, хто побачив URL, може набити відро сміттям.
    if (env.TELEMETRY_KEY && request.headers.get('x-streif-key') !== env.TELEMETRY_KEY) {
      return new Response('nope\n', { status: 403 });
    }

    const body = await request.text();
    if (body.length === 0 || body.length > MAX_BYTES) {
      return new Response('bad size\n', { status: 413 });
    }

    let payload;
    try {
      payload = JSON.parse(body);
    } catch (e) {
      return new Response('bad json\n', { status: 400 });
    }
    if (typeof payload !== 'object' || payload === null || !payload.install) {
      return new Response('bad payload\n', { status: 400 });
    }
    if (looksLikeLocation(payload)) {
      // Свідомо 422, а не тихе прийняття: якщо це колись спрацює, ми маємо про це дізнатись із
      // метрик воркера, а не виявити координати у відрі через півроку.
      return new Response('rejected: payload looks like location data\n', { status: 422 });
    }

    // Час беремо СВІЙ, а не з пакета: годинник на телефоні буває який завгодно, а розкладати об'єкти
    // по днях треба детерміновано. Клієнтський `ts` лишається всередині — розбіжність сама по собі
    // діагностична.
    const receivedTs = Date.now();
    const key = `telemetry/${dayKey(receivedTs)}/${safeId(payload.install)}-${receivedTs}.json`;

    // `receivedTs` дописуємо збоку, не чіпаючи присланого об'єкта.
    const stored = JSON.stringify({ ...payload, receivedTs });
    await env.TELEMETRY_BUCKET.put(key, stored, {
      httpMetadata: { contentType: 'application/json' },
    });

    return new Response('ok\n', { status: 200 });
  },
};
