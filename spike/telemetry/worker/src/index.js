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
 *    тут, ніж потім чистити bucket.
 *
 * Крім запису воркер уміє **читання** (`GET /list`, `GET /get`) — окремим адмін-секретом, див.
 * `adminAllowed`. Це замінило доступ до R2 напряму по S3-ключах: інакше `fetch_telemetry.py` вимагав
 * boto3 + три R2-креденшели на машині, тобто повний доступ до ВСІХ bucket-ів проєкту (включно з
 * продакшн-тайлами) заради читання кількох десятків JSON-ів.
 */

/** Стеля розміру тіла. Реальний пакет — одиниці кілобайт; усе більше або баг, або не наше. */
const MAX_BYTES = 256 * 1024;

const PREFIX = 'telemetry/';

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

/** Рівно та форма ключа, яку пише цей воркер. Служить і гардом на читанні — див. `getOne`. */
const KEY_RE = /^telemetry\/\d{4}-\d{2}-\d{2}\/[a-z0-9-]+-\d+\.json$/;

/**
 * Доступ на ЧИТАННЯ — окремим секретом `TELEMETRY_ADMIN_KEY`.
 *
 * ⚠️ **Чому не тим самим ключем, що в клієнта.** `TELEMETRY_KEY` лежить у APK і витягується
 * розпакуванням застосунку. Для запису це прийнятно (найгірше — сміття в bucket, яке видно й видаляється).
 * Якби ним відкривалось ще й читання, будь-хто, хто розпакував APK, прочитав би телеметрію ВСІХ
 * тестерів — тому ключі різні, а їхня рівність сама по собі є відмовою.
 *
 * ⚠️ **Fail CLOSED — свідомо навпаки до запису.** Перевірка на записі — `if (env.TELEMETRY_KEY && …)`,
 * тобто без секрету пропускає все; це компроміс, щоб можна було перевірити збірку до заведення
 * секрету (і на ньому 2026-07-29 приймач кілька хвилин постояв відкритим). Для читання така
 * поведінка неприпустима: ціна помилки не «сміття», а «злив даних тестерів». Немає секрету — немає доступу.
 */
function adminAllowed(request, env) {
  const k = env.TELEMETRY_ADMIN_KEY;
  if (!k) return false;
  if (k === env.TELEMETRY_KEY) return false;
  return request.headers.get('x-streif-admin') === k;
}

const json = (obj) =>
  new Response(JSON.stringify(obj), { headers: { 'content-type': 'application/json' } });

/**
 * `GET /list[?since=РРРР-ММ-ДД][&cursor=…]` → `{objects:[{key,size}], cursor}`.
 *
 * `since` фільтрує ПІСЛЯ вибірки з R2 (день лежить у самому ключі), тож сторінка може віддати
 * порожній `objects` із непорожнім `cursor` — клієнт мусить іти за курсором, а не спинятись на
 * першій порожній сторінці.
 */
async function list(url, env) {
  const since = url.searchParams.get('since') || '';
  const cursor = url.searchParams.get('cursor') || undefined;
  const page = await env.TELEMETRY_BUCKET.list({ prefix: PREFIX, cursor, limit: 1000 });
  const objects = page.objects
    .filter((o) => !since || (o.key.split('/')[1] || '') >= since)
    .map((o) => ({ key: o.key, size: o.size }));
  return json({ objects, cursor: page.truncated ? page.cursor : null });
}

/** `GET /get?key=telemetry/<день>/<install>-<ts>.json` → сам пакет. */
async function getOne(url, env) {
  const key = url.searchParams.get('key') || '';
  // Гард форми ключа: endpoint має віддавати НАШУ телеметрію, а не бути читалкою довільних об'єктів
  // bucket-а. Сьогодні bucket однопризначний, але покласти в нього щось інше — питання одного дня.
  if (!KEY_RE.test(key)) return new Response('bad key\n', { status: 400 });
  const obj = await env.TELEMETRY_BUCKET.get(key);
  if (!obj) return new Response('not found\n', { status: 404 });
  return new Response(obj.body, { headers: { 'content-type': 'application/json' } });
}

export default {
  async fetch(request, env, ctx) {
    // GET сюди приходить від сканерів і від самого Дениса «а чи живе воно». Відповідаємо коротко
    // й без подробиць: адреса приймача не має розповідати, що саме за нею стоїть. Цю ж відповідь
    // отримує читання без адмін-ключа — не 403, щоб самим фактом відмови не підтверджувати, що за
    // `/list` щось є.
    const notForYou = () => new Response('streif telemetry\n', { status: 405 });

    if (request.method !== 'POST') {
      if (request.method === 'GET') {
        const url = new URL(request.url);
        if (url.pathname === '/list' || url.pathname === '/get') {
          if (!adminAllowed(request, env)) return notForYou();
          return url.pathname === '/list' ? list(url, env) : getOne(url, env);
        }
      }
      return notForYou();
    }

    // Спільний секрет. Він лежить у APK і теоретично витягується — це не автентифікація, а фільтр
    // від випадкового трафіку: без нього будь-хто, хто побачив URL, може набити bucket сміттям.
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
      // метрик воркера, а не виявити координати в bucket через півроку.
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
