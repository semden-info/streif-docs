/**
 * D39 — локальні тести воркера. Запуск (нічого встановлювати не треба, `wrangler` теж не потрібен):
 *
 *     node spike/telemetry/worker/test.mjs
 *
 * Навіщо окремо від деплою: воркер — єдина частина телеметрії, яку не покриває Kotlin-тест, і
 * водночас саме він тримає межу «координати не потрапляють у відро». Перевіряти це вручну після
 * кожної правки не вийде, а помітити регрес постфактум — означає вже мати координати в R2.
 */
import worker from './src/index.js';

const puts = [];
const env = {
  TELEMETRY_KEY: 'secret',
  TELEMETRY_BUCKET: { put: async (k, v) => { puts.push([k, v]); } },
};

const post = (body, key = 'secret') =>
  new Request('https://x/', { method: 'POST', body, headers: key ? { 'x-streif-key': key } : {} });

const cases = [
  ['GET не приймаємо', new Request('https://x/'), 405],
  ['без спільного ключа', post('{"install":"a"}', ''), 403],
  ['не JSON', post('не json'), 400],
  ['без install — не наш пакет', post('{"v":1}'), 400],
  ['порожнє тіло', post(''), 413],
  // Головне, заради чого тест існує: дзеркало клієнтського гарда D14 з іншого кінця дроту.
  ['координата верхнього рівня', post('{"install":"a","walks":[{"lat":62.1}]}'), 422],
  ['координата у вкладеному об\'єкті', post('{"install":"a","x":{"y":{"geometry":1}}}'), 422],
  ['нормальний пакет', post('{"v":1,"install":"aaa","walks":[{"distM":10}]}'), 200],
];

let failed = 0;
for (const [name, req, want] of cases) {
  const res = await worker.fetch(req, env, {});
  const ok = res.status === want;
  if (!ok) failed++;
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${name} → ${res.status} (очікували ${want})`);
}

// Форма ключа — частина контракту з `analyze_telemetry.py` (він читає теку за днями).
if (puts.length !== 1) {
  console.log(`FAIL  у R2 мав лягти рівно 1 об'єкт, лягло ${puts.length}`);
  failed++;
} else {
  const [key, body] = puts[0];
  const keyOk = /^telemetry\/\d{4}-\d{2}-\d{2}\/[a-z0-9-]+-\d+\.json$/.test(key);
  console.log(`${keyOk ? 'ok  ' : 'FAIL'}  ключ має форму telemetry/<день>/<install>-<ts>.json → ${key}`);
  if (!keyOk) failed++;
  const stored = JSON.parse(body);
  const tsOk = typeof stored.receivedTs === 'number';
  console.log(`${tsOk ? 'ok  ' : 'FAIL'}  receivedTs дописано серверним часом`);
  if (!tsOk) failed++;
}

console.log(failed ? `\n${failed} провалено` : '\nусе зелене');
process.exit(failed ? 1 : 0);
