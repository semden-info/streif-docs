/**
 * D39 — локальні тести воркера. Запуск (нічого встановлювати не треба, `wrangler` теж не потрібен):
 *
 *     node spike/telemetry/worker/test.mjs
 *
 * Навіщо окремо від деплою: воркер — єдина частина телеметрії, яку не покриває Kotlin-тест, і
 * водночас саме він тримає дві межі — «координати не потрапляють у bucket» і «читати може лише
 * адмін-секрет». Перевіряти це вручну після кожної правки не вийде, а помітити регрес постфактум
 * означає вже мати або координати в R2, або відкриту телеметрію тестерів.
 */
import worker from './src/index.js';

const puts = [];
const stored = new Map();

// Два готові об'єкти різних днів — щоб `/get` і `?since=` мали на чому спрацювати.
const SEED_OLD = 'telemetry/2026-07-01/aaa-1751328000000.json';
const SEED_NEW = 'telemetry/2026-08-02/bbb-1754092800000.json';
stored.set(SEED_OLD, '{"install":"aaa","receivedTs":1751328000000}');
stored.set(SEED_NEW, '{"install":"bbb","receivedTs":1754092800000}');

const env = {
  TELEMETRY_KEY: 'secret',
  TELEMETRY_ADMIN_KEY: 'admin-secret',
  TELEMETRY_BUCKET: {
    put: async (k, v) => { puts.push([k, v]); stored.set(k, v); },
    list: async ({ prefix }) => ({
      objects: [...stored.keys()].filter((k) => k.startsWith(prefix))
        .map((k) => ({ key: k, size: stored.get(k).length })),
      truncated: false,
    }),
    get: async (k) => (stored.has(k) ? { body: stored.get(k) } : null),
  },
};
// Обидва варіанти мусять ЗАКРИВАТИ читання: секрет не заведено / заведено такий самий, як клієнтський
// (а той лежить у APK, тож збіг звів би захист до нуля).
const envNoAdmin = { ...env, TELEMETRY_ADMIN_KEY: '' };
const envSameKey = { ...env, TELEMETRY_ADMIN_KEY: 'secret' };

const post = (body, key = 'secret') =>
  new Request('https://x/', { method: 'POST', body, headers: key ? { 'x-streif-key': key } : {} });
const get = (path, headers = {}) => new Request(`https://x${path}`, { headers });
const ADMIN = { 'x-streif-admin': 'admin-secret' };

const cases = [
  // --- запис ---
  ['GET на корінь не приймаємо', get('/'), 405],
  ['без спільного ключа', post('{"install":"a"}', ''), 403],
  ['не JSON', post('не json'), 400],
  ['без install — не наш пакет', post('{"v":1}'), 400],
  ['порожнє тіло', post(''), 413],
  // Головне, заради чого тест існує: дзеркало клієнтського гарда D14 з іншого кінця дроту.
  ['координата верхнього рівня', post('{"install":"a","walks":[{"lat":62.1}]}'), 422],
  ['координата у вкладеному об\'єкті', post('{"install":"a","x":{"y":{"geometry":1}}}'), 422],
  ['нормальний пакет', post('{"v":1,"install":"aaa","walks":[{"distM":10}]}'), 200],

  // --- читання ---
  ['/list без адмін-ключа', get('/list'), 405],
  ['/list клієнтським ключем не відкривається', get('/list', { 'x-streif-key': 'secret' }), 405],
  ['/list чужим адмін-ключем', get('/list', { 'x-streif-admin': 'wrong' }), 405],
  ['адмін-секрет не заведено → закрито', get('/list', ADMIN), 405, envNoAdmin],
  ['адмін-секрет = клієнтський → закрито', get('/list', { 'x-streif-admin': 'secret' }), 405, envSameKey],
  ['/list адмін-ключем', get('/list', ADMIN), 200],
  ['/get без key', get('/get', ADMIN), 400],
  ['/get не нашою формою ключа', get('/get?key=../wrangler.toml', ADMIN), 400],
  ['/get неіснуючого об\'єкта', get('/get?key=telemetry/2026-01-01/nope-1.json', ADMIN), 404],
  [`/get наявного об'єкта`, get(`/get?key=${SEED_NEW}`, ADMIN), 200],
  ['невідомий шлях — так само нічого', get('/admin', ADMIN), 405],
];

let failed = 0;
const check = (ok, msg) => {
  if (!ok) failed++;
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${msg}`);
};

for (const [name, req, want, e = env] of cases) {
  const res = await worker.fetch(req, e, {});
  check(res.status === want, `${name} → ${res.status} (очікували ${want})`);
}

// Форма ключа — частина контракту з `analyze_telemetry.py` (він читає теку за днями).
if (puts.length !== 1) {
  check(false, `у R2 мав лягти рівно 1 об'єкт, лягло ${puts.length}`);
} else {
  const [key, body] = puts[0];
  check(/^telemetry\/\d{4}-\d{2}-\d{2}\/[a-z0-9-]+-\d+\.json$/.test(key),
    `ключ має форму telemetry/<день>/<install>-<ts>.json → ${key}`);
  check(typeof JSON.parse(body).receivedTs === 'number', 'receivedTs дописано серверним часом');
}

// Вміст `/list`: те, що бачить `fetch_telemetry.py`.
const listed = await (await worker.fetch(get('/list', ADMIN), env, {})).json();
const keys = listed.objects.map((o) => o.key);
check(keys.includes(SEED_OLD) && keys.includes(SEED_NEW), `/list віддає обидва наявні ключі`);
check(listed.cursor === null, '/list без продовження віддає cursor: null');

const since = await (await worker.fetch(get('/list?since=2026-08-01', ADMIN), env, {})).json();
const sinceKeys = since.objects.map((o) => o.key);
check(sinceKeys.includes(SEED_NEW) && !sinceKeys.includes(SEED_OLD),
  `?since= відсіює давніші дні (лишилось ${sinceKeys.length})`);

const one = await worker.fetch(get(`/get?key=${SEED_OLD}`, ADMIN), env, {});
check((await one.text()) === stored.get(SEED_OLD), '/get віддає тіло об\'єкта незміненим');

console.log(failed ? `\n${failed} провалено` : '\nусе зелене');
process.exit(failed ? 1 : 0);
