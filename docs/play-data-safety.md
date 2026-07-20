# Play Data Safety — чернетка відповідей (Streif)

> **Статус:** чернетка v1.0 — 2026-07-20. Складено **за фактичним кодом** (не з пам'яті), джерела звірки в кожному рядку.
> **Заповнює:** Денис, у Play Console → *App content* → *Data safety*.
> ⚠️ **Це юридична декларація під відповідальність розробника.** Нижче — обґрунтована рекомендація; там,
> де питання неоднозначне (розділ 3), наведено ОБИДВА варіанти й чому обрано саме цей. Перечитай перед сабмітом.

---

## 0. Що встановлено по коду (база для всіх відповідей)

| Факт | Де перевірено |
|---|---|
| GPS-фікси обробляються в пам'яті, у БД лягає лише **результат** розкриття | `TrackingRepository.kt`, `MvpDatabase.kt` (`VisitEntity` = id/тип/час/tettsted/kommune/bygningstype — **без координат**) |
| Сирий трек `diag.csv` пишеться **тільки** в debug | `MapController.kt:592` — `if (BuildConfig.DEBUG) DiagnosticRecorder(...)`; `TrackingRepository.kt:92,532` |
| **Немає** background-location | `AndroidManifest.xml` — `ACCESS_BACKGROUND_LOCATION` відсутній; є лише `FOREGROUND_SERVICE_LOCATION` |
| **Немає** аналітики/крашлітики/реклами | `grep -riE "firebase\|analytics\|crashlytics\|admob\|sentry"` по `app/build.gradle.kts` + `libs.versions.toml` → **0 збігів** |
| Логін — **опційний** (D36), вимкнено гейтом за замовчуванням | `CredentialManager`+`AuthorizationClient` є (пакет `backup/`), але секція «Синк» з'являється лише коли заповнено `default_web_client_id` (порожній → фічі нема). Без входу — як 2.1–2.3. Деталі декларації → **2.4** |
| Мережа — рівно 3 адресати (+1 мертвий фолбек) | `style.json:6` + `MapBasemap.kt` (Kartverket) · `CdnGeoJsonAreaSource.kt` (R2) · `StreifApp.kt` + `PoiCard.kt:48` (Wikimedia) · `AreaSource.kt:29-31` (Overpass — недосяжний при `USE_CDN=true`, `build.gradle.kts:27`) |
| Усі endpoint'и — **HTTPS** | ті самі рядки; жодного `http://` |
| Немає in-app «видалити все» | `grep` по `SettingsSheet.kt`/`WalkViewModel.kt` → кнопки нема (`VisitDao.clear()` існує, але з UI не викликається) |

**Ключовий висновок:** точна локація **не покидає пристрій**, але **приблизна покидає** — у вигляді координат
тайла в URL. Саме на цьому тримається вся декларація нижче.

---

## 1. Стартове питання

> **Does your app collect or share any of the required user data types?**

**Відповідь: Yes.**

*Чому:* попри device-local архітектуру, Play визначає «collected» як **«transmitting data from your app off a
user's device»**. Запит тайла `area_{la}_{lo}.geojson` (`CdnGeoJsonAreaSource.kt:23`) і запит підложки
`.../{z}/{y}/{x}.png` (`style.json:6`) містять координати, похідні від позиції користувача → це передача
локації за межі пристрою. Відповісти «No» було б заниженням.

---

## 2. Data types — що декларуємо

### 2.1 Location → **Approximate location** — ✅ Collected

| Питання форми | Відповідь | Чому |
|---|---|---|
| Collected? | **Yes** | Координати тайла в URL до R2 і Kartverket |
| Shared? | **No** | див. розділ 3 |
| Processed ephemerally? | **Yes** | Сервери віддають статичний файл у реальному часі; ми нічого не пишемо й не профілюємо (`CdnGeoJsonAreaSource` — чистий GET, без сесій/куків/id) |
| Required or optional? | **Required** | Без карти застосунок не працює |
| Purpose | **App functionality** (єдина) | Немає ні реклами, ні аналітики, ні персоналізації |

### 2.2 Location → **Precise location** — ✅ Collected (перестраховка)

| Питання форми | Відповідь | Чому |
|---|---|---|
| Collected? | **Yes** | ⚠️ Формально сирий GPS **не передається** (гріди 0,02° ≈ 2,2 км — це «approximate»). АЛЕ підложка Kartverket тягне тайли на високому зумі: z18 ≈ 150 м, а Play рахує «precise» як точність **краще ніж 3 км²**. Тобто тайл-запит технічно потрапляє в «precise». **Декларуємо Yes** — рівно за принципом «краще перестрахуватись» |
| Shared? | **No** | див. розділ 3 |
| Processed ephemerally? | **Yes** | те саме, що вище |
| Required or optional? | **Required** | |
| Purpose | **App functionality** | |

> ### ✅ РІШЕННЯ УХВАЛЕНО (Денис, 2026-07-20): декларуємо **обидва** — Approximate **і** Precise.
>
> Розглядалась альтернатива «лише Approximate» (аргумент: сирі координати не покидають пристрій,
> передається тільки ID тайла) — вона теж захищається, але **відхилена свідомо**. Причина: різниця
> в картці Play мінімальна, а недодекларована локація — одна з найчастіших причин відхилення.
> Перестраховка тут коштує нічого, помилка — зняття застосунку.
>
> ⚠️ Це рішення **не переглядати** без нової перевірки коду: воно спирається на факт, що застосунок
> ходить до **трьох** зовнішніх адресатів (R2, `cache.kartverket.no`, Wikimedia), і саме підложка
> Kartverket на z18 (~150 м) заводить нас у визначення «precise» (краще ніж 3 км²).

### 2.3 Решта — ❌ NOT collected (окрім опційного бекапу — див. 2.4)

| Категорія | Відповідь | Чому |
|---|---|---|
| Personal info → **Email address** | **Yes — ЛИШЕ якщо ввімкнено бекап** (див. 2.4) | Опційний Google-вхід (D36) дає email обраного акаунта — лежить локально (`SettingsStore.backupEmail`), показує, куди йде копія. Без входу (дефолт) — **No** |
| Personal info (ім'я, адреса, тел., решта ID) | **No** | Не збираємо взагалі |
| Financial info | **No** | Немає платежів |
| Health and fitness | **No** | ⚠️ Health Connect **ще не підключено**. Дистанція сесії (`SessionEntity.distanceM`) лишається локально → «collected» не виникає. Перевірити наново, коли додаси Health Connect |
| Messages / Photos / Videos / Audio / Files | **No** | Застосунок нічого такого не читає й не шле |
| Calendar / Contacts | **No** | Дозволів нема в маніфесті |
| **App activity** (взаємодія, пошук, інстальовані апки) | **No** — без бекапу; **Yes** якщо ввімкнено (див. 2.4) | Без бекапу розкриття/сесії/POI/колекції лежать **лише** в Room. З бекапом їхній агрегат іде у **власний** Drive користувача (App functionality) |
| **App info and performance** (краші, діагностика, продуктивність) | **No** | Немає жодного crash/analytics SDK — перевірено grep'ом |
| **Device or other IDs** | **No** | Не читаємо AAID/ANDROID_ID; UA-рядок `Streif/0.4 (contact@semden.info)` — константа, не ідентифікатор (`CdnGeoJsonAreaSource.kt:27`, `StreifApp.kt:21`) |

> ℹ️ **IP-адреса** технічно видима серверам. Play **не має** окремого типу «IP address» і не вимагає його
> декларувати як ID, якщо ти його не збираєш і не використовуєш для ідентифікації. Ми — не збираємо.
> У політиці приватності IP згадано чесно (п. 4) — цього достатньо.

### 2.4 Опційний бекап у Google Drive (Sign-In, D36) — умовно collected

⚠️ **Ця секція актуальна ЛИШЕ коли `default_web_client_id` заповнено й користувач УВІМКНУВ бекап.** Дефолт —
вимкнено (deferred auth D26): без входу декларація зводиться до 2.1–2.3, і всі рядки нижче = **No**.

| Питання форми | Відповідь | Чому |
|---|---|---|
| Personal info → Email address — Collected? | **Yes** | Google-вхід (`CredentialManager`) дає email акаунта; лежить локально, показує, куди йде копія |
| Email address — Shared? | **No** | Email нікому не передаємо; він лише ідентифікує **власний** акаунт користувача для запису |
| App activity (розкриття/POI/колекції/сесії) — Collected? | **Yes** | Агрегат прогресу пишеться у **власний** Drive користувача (App Data Folder, scope `drive.appdata`) |
| App activity — Shared? | **No** | Це власне сховище користувача (Google як databehandler за його ж запитом), не передача третій стороні |
| Purpose (обидва типи) | **App functionality** (єдина) | Резервна копія / відновлення прогресу. Без реклами/аналітики/персоналізації |
| Optional? | **Yes** | Фіча вимкнена за замовчуванням, вмикається вручну в Settings |
| Processed ephemerally? | **No** | Копія зберігається в Drive до наступного циклу (не ефемерна, на відміну від тайлів) |

⚠️ **Чого тут НЕМА (незмінно, D14):** сирого GPS-треку. У Room координат не існує; `diag.csv` (debug) у
бекап не потрапляє. Страж-тести `BackupMergeTest.model_hasNoCoordinateFields` + whitelist ключів дроту
падають на будь-якому координатному полі. Тому «Location» у 2.1/2.2 бекап **не розширює**: він і далі про
тайли, а не про трек.

**Security → «request deletion»:** з бекапом є повний контроль — вимкнути синхронізацію в Settings
(перестає писати в Drive), а сама копія лежить у **власному** Google-акаунті користувача. Кнопку
**«Видалити копію з Google Drive»** виведено в Settings (`deleteBackup` → `BackupManager.deleteRemote()`
+ вимкнення бекапу, щоб наступний sync не відновив файл), тож «provide a way to request deletion» для
бекапу чесно **Yes**. *(In-app видалення ЛОКАЛЬНИХ даних — окреме питання, ще нема; див. 2.3/чек-лист.)*

---

## 3. Найтонше питання: Shared = Yes чи No?

**Рекомендація: No.** Обґрунтування по кожному адресату:

| Адресат | Кваліфікація | Аргумент |
|---|---|---|
| **Cloudflare R2** | ❌ не sharing | Наше власне сховище. Play прямо виводить з-під «sharing» передачу **«service provider that processes it on your behalf»** |
| **Kartverket** | ❌ не sharing | Не отримує «дані користувача, зібрані застосунком» — отримує запит на статичний тайл, ініційований дією користувача (він відкрив карту). Play виводить з-під sharing передачу «based on a specific user-initiated action». Кожен картографічний застосунок працює так само |
| **Wikimedia Commons** | ❌ не sharing | Запит фото відбувається **лише** коли користувач тапнув картку POI (`PoiCard.kt:48`) — user-initiated, і не містить локації взагалі, лише назву файлу |

⚠️ **Що врахувати:** «No» тут — обґрунтоване прочитання винятків Play, а не самоочевидний факт.
Якщо волієш нульовий ризик спору — можна поставити **Shared = Yes** для Location з purpose *App functionality*.
Ціна: у картці Play з'явиться «Data shared with third parties: location», що **менш точно описує реальність**
(ніхто не отримує від нас профіль користувача) і може відлякати частину аудиторії.
**Наша порада — No + збережений цей документ як письмове обґрунтування** на випадок питання від Play.

---

## 4. Security practices

> ⚠️ Тут напрямок ризику **протилежний**: занизити безпечно, **завищити — це вже недостовірна заява**.
> Не став галочку, якої не можеш підтвердити.

| Питання | Відповідь | Чому |
|---|---|---|
| **Is all of the user data collected by your app encrypted in transit?** | **Yes** | Усі три адресати — HTTPS: `style.json:6`, `MapBasemap.kt` (усі 4 стилі), `CdnGeoJsonAreaSource.kt:23,53`, Wikimedia через OkHttp/Coil. Жодного cleartext-URL у коді; `usesCleartextTraffic` не вмикали |
| **Do you provide a way for users to request that their data be deleted?** | **No** | ⚠️ Чесна відповідь. In-app кнопки видалення **нема** (перевірено), а серверних даних, які можна було б видалити на запит, **не існує взагалі**. Політика приватності (п. 7) прямо пояснює: «Clear storage» / видалення застосунку стирає все. Ставити «Yes» без реального механізму — недостовірна заява |
| **Independent security review** (опційне) | **No** | Незалежного аудиту не проходили. D23-review — архітектурний, не security-аудит |
| **Data deletion within 90 days** (якщо доступне) | не застосовне | Ми нічого не зберігаємо на своєму боці |

> 💡 **Швидкий апгрейд для наступної версії:** додати в Settings кнопку «Delete all my data»
> (`VisitDao.clear()` + `PoiVisitDao.clear()` + `CollectionClosureDao.clear()` + sessions — усі вже існують,
> лишилось під'єднати UI з підтвердженням). Тоді відповідь чесно стає **Yes** — і це прибирає єдиний
> «слабкий» пункт декларації. Це також перегукується з GDPR Art. 17 і з D30 (не втрачати прогрес випадково —
> тому обов'язково діалог підтвердження).

---

## 5. Privacy policy URL

Поле **Privacy policy** у Data safety + окремо в *Store listing*:

```
https://semden.no/streif/privacy/
```

Вимоги Play до цієї сторінки (усі виконані в `docs/privacy-policy/index.html`):
публічний URL без логіну · не PDF-файл · згадує застосунок за назвою · перелічує типи даних, мету,
поводження з ними · дає контакт розробника.

---

## 6. Перед сабмітом — звірка на актуальність

Перевір, чи не змінилось щось із моменту складання (2026-07-20):

- [ ] `USE_CDN` досі `true` — інакше оживає **Overpass** (`overpass-api.de` та дзеркала), і в політику треба
      додати 4-го адресата (`AreaSource.kt:29-31`)
- [ ] Не додано аналітику/Crashlytics — інакше вмикається «App info and performance»
- [x] Google Sign-In / Drive **збудовано (D36), але вимкнено гейтом** `default_web_client_id` (порожній →
      секції нема). Заповниш OAuth-клієнт і ввімкнеш бекап → декларуй **2.4**: «Personal info → Email address»
      (Collected, App functionality, optional) + «App activity» (Collected, у власний Drive). Політику вже
      приведено у відповідність (п. 10 — реалізовано, не «planned»)
- [ ] Health Connect не підключено — інакше «Health and fitness»
- [ ] Не з'явилось in-app видалення — якщо з'явилось, «request deletion» стає **Yes**

---

### Джерела (офіційні)

- [Provide information for Google Play's Data safety section](https://support.google.com/googleplay/android-developer/answer/10787469) — визначення «collected» («transmitting data from your app off a user's device»), «shared», винятки (service provider, user-initiated action), «ephemeral», питання безпеки
- [Understanding foreground service and full-screen intent requirements](https://support.google.com/googleplay/android-developer/answer/13392821)
