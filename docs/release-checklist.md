# Streif — чек-лист закритого тесту в Google Play

> **Статус:** v1.0 — 2026-07-20. Складено під **закритий тест** (closed testing), не під production.
> **Вхідні умови:** акаунт Play — персональний, **уже верифікований**, з одним опублікованим застосунком.
> **Пов'язані документи:** `play-data-safety.md` · `play-fgs-declaration.md` · `privacy-policy/index.html`

---

## ЧАСТИНА A. Keystore (підпис застосунку)

### A.1 Що це і чому окремо

Play використовує **дворівневий підпис** (Play App Signing, обов'язковий для нових застосунків):

- **upload key** — твій ключ; ним ти підписуєш `.aab` перед завантаженням. Play перевіряє підпис і **знімає** його.
- **app signing key** — ключ, яким Play **сам** перепідписує APK для користувачів. Зберігає й захищає Google.

**Практичний наслідок:** ключ, який ти зараз створиш — це *upload key*. Він **відновлюваний** (див. A.5).
Це принципово інша ситуація, ніж «втратив ключ — втратив застосунок» зі старих часів.

### A.2 Команда генерації

`keytool` іде разом із JDK. Виконати **один раз**, у теці **поза репозиторієм** (напр. `C:\Users\mail\keys\`):

```bash
keytool -genkeypair -v \
  -keystore streif-upload.jks \
  -storetype PKCS12 \
  -alias streif-upload \
  -keyalg RSA -keysize 4096 \
  -validity 10000
```

У PowerShell — той самий рядок, але перенос рядка — backtick `` ` `` замість `\`, або просто одним рядком.

**Чому саме такі параметри:**

| Параметр | Значення | Чому |
|---|---|---|
| `-storetype PKCS12` | PKCS12 | Сучасний стандартний формат. Старий JKS keytool приймає, але щоразу лається попередженням |
| `-keysize 4096` | 4096 | Play вимагає ≥ 2048; 4096 — з запасом, на швидкість збірки не впливає |
| `-validity 10000` | ~27 років | Play вимагає, щоб ключ був чинний **щонайменше до 22 жовтня 2033**. 10000 днів від 2026 → ~2053 ✅ |
| `-alias` | `streif-upload` | Знадобиться в Gradle; назвати зрозуміло, бо забувається |

### A.3 Що відповідати на запити keytool

```
Enter keystore password:          ← ПРИДУМАТИ довгий пароль → одразу в менеджер паролів
Re-enter new password:            ← той самий
What is your first and last name?          [Unknown]:  Denis Semenyuk
What is the name of your organizational unit? [Unknown]:  Streif
What is the name of your organization?        [Unknown]:  Denis Semenyuk        (назва ENK)
What is the name of your City or Locality?    [Unknown]:  Orsta
What is the name of your State or Province?   [Unknown]:  More og Romsdal
What is the two-letter country code?          [Unknown]:  NO
Is CN=Denis Semenyuk, OU=Streif, ... correct?  [no]:  yes
Enter key password for <streif-upload>
        (RETURN if same as keystore password):  ← просто Enter (хай збігається — менше плутанини)
```

⚠️ **Про поля CN/OU/O:** вони йдуть у сертифікат і **не змінюються потім**, але користувачам **не показуються** —
Play показує лише твоє ім'я розробника з профілю акаунта. Тож писати реальні дані, без надмірної тривоги.
**Латиницею, без «ø» і «å»** — деякі інструменти підпису спотикаються на не-ASCII у DN.

### A.4 Де зберігати

- ✅ Сам файл `.jks` — **поза git-репозиторієм**, у теці, яка потрапляє в бекап (OneDrive підійде).
- ✅ **Друга копія** — на окремому носії (флешка/зовнішній диск), фізично окремо.
- ✅ Пароль — **у менеджері паролів**, не в текстовому файлі поруч із ключем.
- ❌ **Ніколи** не комітити `.jks` у git — навіть у приватне репо, навіть «тимчасово». Видалити з історії
  потім набагато важче, ніж не додати.
- 📌 Записати собі: шлях до файлу, `alias`, де лежить пароль. Через рік це забувається гарантовано.

### A.5 ⚠️ ЩО СТАЄТЬСЯ ПРИ ВТРАТІ (перевірено за офіційною документацією)

**Втрата upload key — НЕ катастрофа.** Офіційно: *«If you lose your upload key or suspect it was compromised,
you are not locked out of your app.»*

Процедура відновлення:

1. Згенерувати **новий** upload key (та сама команда з A.2, інша назва файлу).
2. Експортувати сертифікат у PEM:
   ```bash
   keytool -export -rfc -keystore streif-upload-new.jks -alias streif-upload -file upload_certificate.pem
   ```
3. Play Console → **Protected with Play** → *Play Store protection* → **Manage Play app signing** → запит на
   скидання upload key, вказати причину й прикріпити `.pem`.
4. Дочекатись підтвердження Google (не миттєво — зазвичай кілька робочих днів), далі підписувати новим ключем.

**А що НЕ відновлюється:** *app signing key*, **якщо** ти керуєш ним сам, поза Play App Signing —
офіційно *«This key cannot be reset if you manage it yourself… and lose it»*. Оскільки для нових застосунків
Play App Signing увімкнено (Google тримає цей ключ у себе), цей сценарій нас **не стосується** —
за умови, що при налаштуванні ти **не відмовляєшся** від Play App Signing.

> **Висновок:** втрата ключа коштує кількох днів очікування, а не застосунку. Але резервну копію все одно
> зробити — кілька днів простою посеред тесту теж неприємно.

### A.6 Як Gradle має читати ключ БЕЗ секретів у git

> ⚠️ Це **опис для Дениса / іншого агента**. Gradle-код я за умовою завдання не чіпав.

**Стан зараз:** у `app/build.gradle.kts` **немає жодного `signingConfigs`** — блок `release` містить лише
`optimization { enable = false }`. Тобто release-збірка зараз узагалі не підписується твоїм ключем.

**Рекомендований підхід — окремий `keystore.properties`** (не змішувати з `local.properties`, який
перезаписує Android Studio):

1. Створити `keystore.properties` у корені Android-проєкту:
   ```properties
   storeFile=C:/Users/mail/keys/streif-upload.jks
   storePassword=...
   keyAlias=streif-upload
   keyPassword=...
   ```
2. **Одразу** додати рядок `keystore.properties` у `.gitignore`.
   *(Перевірено: `local.properties` там уже є — і як `/local.properties`, і як `local.properties`.
   `keystore.properties` — ще ні, треба додати.)*
3. У `app/build.gradle.kts` — читати файл, якщо він існує, і застосовувати `signingConfig` до `release`.
   Обов'язково передбачити випадок, коли файлу **немає** (CI, чужа машина): тоді просто не підписувати,
   а не падати збіркою.
4. **Альтернатива для CI** — ті самі чотири значення через змінні середовища
   (`STREIF_STORE_FILE`, `STREIF_STORE_PASSWORD`, …), з фолбеком на файл. Для solo-dev поки надлишково.

**Швидка самоперевірка, що секрет не протік:**
```bash
git check-ignore -v keystore.properties     # має показати правило з .gitignore
git log --all --full-history -- "*.jks"     # має бути ПОРОЖНЬО
```

---

## ЧАСТИНА B. Чек-лист закритого тесту

Порядок — робочий: кожен наступний блок спирається на попередній.

### B.0 ⚠️ БЛОКЕР, який треба вирішити ПЕРШИМ

**`applicationId` зараз = `no.streif.spike`** (`app/build.gradle.kts:17`).

Package name **неможливо змінити після першого завантаження** — він назавжди прив'язаний до застосунку в Play.
Залишити `.spike` означає, що продакшн-Streif назавжди житиме під ідентифікатором «spike»
(видно в URL сторінки Play: `play.google.com/store/apps/details?id=no.streif.spike`).

→ **Змінити на `no.streif.app` (або просто `no.streif`) ДО першого завантаження `.aab`.**
Зачіпає `applicationId` + `namespace` + імпорти/маніфест. **Це Android-код → задача Дениса / іншого агента.**

*(Технічно `namespace` можна лишити старим, а змінити тільки `applicationId` — це менша правка.
Але тоді код і Play розходяться в назвах, що плутатиме потім. Вирішувати Денису.)*

---

### B.1 Моя частина — ✅ зроблено

| # | Що | Де |
|---|---|---|
| 1 | Privacy policy, nb + en, самодостатній HTML | `docs/privacy-policy/index.html` |
| 2 | Data safety — відповіді на кожне питання + обґрунтування | `docs/play-data-safety.md` |
| 3 | FGS-декларація: текст англійською + сценарій відео | `docs/play-fgs-declaration.md` |
| 4 | Keystore-інструкція + політика втрати ключа | цей файл, частина A |
| 5 | Аудит фактичних потоків даних по коду | `play-data-safety.md` §0 |

### B.2 Частина Дениса — код (перед першим `.aab`)

> **Статус оновлено 2026-07-21** після пакета A (`ba9028f`). ⚠️ «Збудовано» ≠ «працює чесно»:
> два пункти збудовані, але мають блокерні дефекти — див. **§B.6**.

| # | Що | Статус | Деталі |
|---|---|---|---|
| 1 | **Змінити `applicationId`** з `no.streif.spike` | 🔴 **НЕ зроблено** | B.0. Свідоме рішення власника — відкласти до першої публікації (нічого ще не опубліковано). Робити разом із keystore + додатковими OAuth-клієнтами |
| 2 | Створити keystore | 🔴 **НЕ зроблено** | Частина A. Твоя частина — я не можу створювати ключі й паролі |
| 3 | `signingConfigs` + `keystore.properties` у `.gitignore` | ✅ зроблено | Без файлу збірка лишається зеленою (release непідписаний). ⚠️ але **§B.6 #4** (`.gitignore` не покриває `*.jks`) і **#5** (`\` у шляху ламає Windows) |
| 4 | `versionCode`/`versionName` | ✅ `0.1.0` | `versionCode` лишився `1` — це правильно для першого завантаження, але мусить **зростати** з кожним наступним |
| 5 | Prominent disclosure про локацію | ⚠️ **збудовано, текст НЕПРАВДИВИЙ** | Екран є і показується перед системним запитом, але його твердження хибні → **§B.6 #2 (blocker)**. Також не показується тим, хто вже дав дозвіл (**#7**) |
| 6 | Release на debug-артефакти | ✅ перевірено | ✓/✗-мітки, перемикач мов, `diag.csv` — усе за `BuildConfig.DEBUG`, звірено грепом; `assembleRelease` + `lintVitalRelease` зелені |
| 7 | Кнопка «Delete all my data» | ⚠️ **збудовано, не видаляє остаточно** | Стирає локально, але наступний вхід у Google повертає все → **§B.6 #1 (blocker)**. Доки не полагоджено, відповідь у Data safety **ще не можна** міняти на «Yes» для локальних даних |
| 8 | Іконка застосунку | ✅ зроблено | Ілюстрація Дениса як adaptive-foreground, вписана в safe-зону 66/108. Оригінал 512 для лістингу → `docs/store-assets/play-icon-512.png` |
| 9 | **Руйнівний round-trip бекапу** (стерти → відновити) | 🟡 відкладено | Свідомо не робили на основному телефоні (там 383 розкриття + 151 мітка ground truth). Планово — на **другому телефоні** як чесний тест «переїзду на новий пристрій» |

### B.3 Частина Дениса — Play Console

Порядок саме такий: Play не пускає до треків, доки не заповнено *App content*.

| # | Крок | Нотатки |
|---|---|---|
| 1 | Створити застосунок | Default language: **English (United States)**; Type: App; Free |
| 2 | Викласти privacy policy на `semden.no` | Публічний URL, **не PDF**, без логіну. Напр. `https://semden.no/streif/privacy/` |
| 3 | *App content* → **Privacy policy** | вставити той URL |
| 4 | *App content* → **Data safety** | за `play-data-safety.md` |
| 5 | *App content* → **Foreground service permissions** | за `play-fgs-declaration.md`; **потрібне відео** → зняти заздалегідь (§3) |
| 6 | *App content* → решта декларацій | Ads: **No** · Content rating (анкета — Everyone) · Target audience: **не діти** · News app: No · Government app: No · Financial features: No · Data deletion: за §4 Data safety · Health apps: No |
| 7 | *Store listing* — англійська | Назва, коротким описом (80 симв.), повний опис, скріншоти (мін. 2, телефон), feature graphic 1024×500, іконка 512×512 |
| 8 | *Store listing* — **норвезька (bokmål)** | Додати локалізацію `no-NO`. У застосунку вже є `values-nb` + `values-nn` ✅ |
| 9 | Зібрати **`.aab`** (не `.apk`) | Для застосунків, створених після серпня 2021, APK більше не приймають |
| 10 | Створити трек **Closed testing** | Список тестерів — email'и або Google Group. Group зручніша: додавати людей без нового релізу |
| 11 | Завантажити `.aab`, вказати release notes | Перший реліз |
| 12 | Розіслати **opt-in URL** тестерам | Без переходу за цим посиланням тестер застосунку в Play **не побачить** |

### B.4 Про правило «12 тестерів / 14 днів»

**Не блокує закритий тест.** Перевірено офіційно, три уточнення:

1. Правило стосується **подачі на production access**, а не запуску closed test.
   Закритий тест можна стартувати одразу після заповнення *App content*.
2. Застосовується **лише до персональних акаунтів, створених після 13 листопада 2023**.
   → У тебе акаунт **уже верифікований і з опублікованим застосунком**. Якщо акаунт старший за цю дату —
   правило до тебе взагалі не застосовується; якщо ти вже маєш production access — питання закрите.
   **Перевірити в Play Console → Dashboard**, чи є взагалі блок «apply for production access».
3. Якщо правило все ж застосовне: 14 днів мають бути **безперервними**, тестерів — **12 одночасно
   опт-інутих**. Ті, хто вийшов раніше 14 днів, не зараховуються навіть якщо повернулись.
   → Практичний висновок: **не набирати тестерів по одному** — зібрати 12+ і завести всіх разом,
   інакше лічильник щоразу перезапускається.

### B.5 Технічні вимоги — статус

| Вимога | Статус | Джерело |
|---|---|---|
| `targetSdk` ≥ 36 (Android 16) для нових застосунків з 31.08.2026 | ✅ **36** (`build.gradle.kts:18`) | [target-sdk](https://developer.android.com/google/play/requirements/target-sdk) |
| App Bundle `.aab` замість APK | ⚠️ перевірити конфіг збірки | [app bundle](https://support.google.com/googleplay/android-developer/answer/9859152) |
| Play App Signing | ⚠️ увімкнути при створенні (не відмовлятись) | A.1 |
| FGS-тип у маніфесті + декларація | ✅ маніфест (`:42`) / ⚠️ декларація | `play-fgs-declaration.md` |
| Немає background location | ✅ перевірено по маніфесту | — |
| `minSdk 24` | ✅ обмежень Play немає | — |

---

### B.6 ⚠️ ВІДКРИТІ ДЕФЕКТИ пакета A (adversarial review, 2026-07-21) — НЕ виправлені

Код пакета A закомічено (`ba9028f`, збірки зелені, 239 тестів ✅), але review трьома незалежними
лінзами (втрата даних · відповідність політикам · збірка/реліз) знайшов реальні дефекти.
**Черга наступного заходу.** Порядок = пріоритет.

| # | Тяжкість | Що | Чому це важливо |
|---|---|---|---|
| 1 | 🔴 blocker | Після «Delete all my data» повторний вхід у Google **безумовно відновлює стерте** (union-merge), і застосунок сам штовхає на цю дію своїм toast'ом «sign in and try again». Те саме, якщо користувач свідомо лишив копію в Drive і потім знову ввімкнув бекап | Кнопка обіцяє більше, ніж робить. **Інваріант, який треба ввести:** після видалення жоден автоматичний шлях (вхід · щоденний Worker · «sync now») не має права повернути дані без явної, поінформованої дії користувача |
| 2 | 🔴 blocker (Play) | Текст disclosure стверджує, що локація вмикається «лише коли тиснеш Start walk» і «ніколи не покидає телефон». **Обидва твердження неправдиві:** застосунок центрується по локації на кожному запуску (`MapController.onMapReady` → `centerOnLastLocation` → `preloadArea`) і шле координати в R2/Kartverket за тайлами | Хибний prominent disclosure гірший за його відсутність: суперечить нашій же декларації Data safety (Location = Collected) і є самостійним порушенням політики |
| 3 | 🟠 major | `TrackingRepository.reset()` не чистить буфер `recentT/recentLat/recentLon` | Стирання **під час прогулянки** → наступний завантажений тайл переграє старі фікси й заново розкриває щойно стерті будинки. Плюс буфер сирих координат переживає «видалити все» (тертя з D14) |
| 4 | 🟠 major | `.gitignore` не покриває `*.jks` / `*.keystore` / `*.p12`, а коментар у `build.gradle.kts` запрошує покласти ключ у корінь проєкту | Один `git add -A` — і приватний ключ підпису в історії публічного репо. З історії його не прибрати; upload-key довелося б відкликати через Play |
| 5 | 🟠 major | `keystore.properties` на Windows: `\` — escape-символ у `java.util.Properties` | `storeFile=C:\Users\…` або тихо псується (падає лише на задачі підпису), або валить **конфігурацію всього проєкту** (`Malformed \uxxxx`). Треба нормалізувати шлях або задокументувати прямі слеші |
| 6 | 🟠 major | Android-OAuth-клієнт зареєстровано лише на **debug**-SHA-1 | У release-збірці із закритого треку (Play App Signing = третій сертифікат) вхід у Google впаде з `DEVELOPER_ERROR` → бекап мертвий саме в тій збірці, яку тестують. Треба додати клієнти зі SHA-1 upload-ключа **І** з Play Console → App signing |
| 7 | 🟡 minor | Disclosure показується лише в гілці «дозволу немає» | Хто вже дав дозвіл (усі наявні тестери) не побачить його ніколи. Потрібен одноразовий показ і для них |
| 8 | 🟡 minor | Видалення даних до `TrackingRepository.init` — тихий no-op, але toast рапортує успіх | Gear-FAB не гейтиться на `state.ready`: на холодному старті можна натиснути «видалити» й отримати хибне підтвердження при недоторканій базі |
| 9 | 🟡 minor | Гонка `deleteRemote()` ↔ `BackupWorker` | Вікно між мережевим видаленням і `backupEnabled=false`: Worker може відтворити файл у Drive із ще не стертих даних. Робити видалення+вимкнення+wipe під одним `SYNC_LOCK` |
| 10 | 🟡 minor | `cacheDir/share/streif-progress.png` не видаляється | Діалог обіцяє «everything Streif has saved on this phone», а PNG зі знімком прогресу лишається |

**Розсинхрон документів (виправити перед подачею — їх вставляють у Play дослівно):**
- `play-fgs-declaration.md` §2.1 каже «There is no account, no server sync, and no analytics» — після активації синку це **неправда**.
- `play-data-safety.md` §0/§4/§6 каже «немає in-app видалення» і радить відповідати **No** на «provide a way to request deletion» — після пакета A це теж неправда (тепер чесне **Yes**).

---

## Частина C — активація синхронізації з Google Drive (D26 / D14)

Синхронізацію прогресу в код **ЗБУДОВАНО** (пакет `backup/`: Sign in with Google → scope `drive.appdata`
→ двобічний merge → щоденний WorkManager при мережі+зарядці → «поділитись знімком» уже окремо в шторці
прогресу). Вона **вимкнена**, поки порожній ресурс `default_web_client_id` — тоді секції «Синк» у
Settings просто нема, ніщо не падає (гейт = порожній client-id, не окремий прапорець).

**Що тримає код (перевірено адверсивним review + 261 юніт-тест):**
- **D14** — у копію йдуть ЛИШЕ агрегати: розкриття / зібрані POI / закриті колекції / підсумки сесій
  (id·тип·час·tettsted·kommune·bygningstype·дистанція-скаляр). Сирого GPS-треку немає — `diag.csv`
  (debug-only) у бекап не потрапляє; у Room координат нема взагалі, тож витекти нема чому.
- **D30** — відновлення = **merge (union)**, ніколи не заміна: локальні розкриття переживають вхід на
  новому пристрої; ідемпотентно (щоденний цикл може перекритись сам із собою без шкоди).
- **D26** — вхід лише в Settings, після цінності; без входу все працює локально.
- **Мінімум прав** — тільки scope `drive.appdata` (прихована per-app тека акаунта), не весь Drive.

### C.1 Кроки в Google Cloud Console (частина Дениса)

1. **Проєкт** — новий у [console.cloud.google.com](https://console.cloud.google.com) (або наявний).
2. **APIs & Services → Enable APIs → Google Drive API → Enable.**
3. **OAuth consent screen:**
   - User type **External**; назва застосунку, email підтримки, лого (опц.).
   - **Scopes → додати `.../auth/drive.appdata`** («See, create, and delete its own configuration data»).
   - **Test users** → email'и тестерів (ті самі, що в Play closed test). Поки consent-екран у режимі
     *Testing*, увійти можуть лише вони — цього для закритого тесту достатньо, «verification» не потрібна.
   - ⚠️ **Але в статусі *Testing* refresh-токен спливає через 7 днів** (офіційно; виняток — лише scope
     name/email/profile, а в нас Drive). Практично: у тестерів фоновий бекап раз на тиждень тихо
     зупинятиметься до повторного входу в Settings. Код це переживає (Worker тихо відкладає, не падає).
     Прибирається переведенням consent-екрана в *In production* — а це для **non-sensitive** scope
     `drive.appdata` вимагає лише базової верифікації, без платної security-assessment.
4. **Credentials → Create credentials → OAuth client ID** — потрібні **ДВА** клієнти:
   - **Android** — `package name` = фінальний `applicationId`; `SHA-1` = відбиток ключа, яким
     **підписано встановлений застосунок**:
     - для локально встановленого APK у тесті — SHA-1 **upload-ключа**:
       `keytool -list -v -keystore streif-upload.jks -alias streif-upload` → рядок `SHA1`;
     - для роздачі через Play — додати ЩЕ SHA-1 з **Play Console → App signing** (Play перепідписує
       своїм ключем, і без його SHA-1 вхід у встановленої з Play версії впаде).
   - **Web** — окремий клієнт; його **Client ID** — це саме те, що йде в `default_web_client_id`
     (CredentialManager вимагає web-client-id як `serverClientId`, навіть коли нам потрібен лише Drive).
5. **Вписати web-client-id** у `app/src/main/res/values/strings.xml` → `default_web_client_id`. Він не
   секрет (публічний ідентифікатор), але тримати краще в не-VCS ресурсі; для тесту можна прямо в strings.
6. Зібрати → встановити → **Settings → «Синк і резервна копія»** з'явиться → «Резервна копія в Google
   Drive» → вибір акаунта → згода на App Data. Далі щоденний бекап планує WorkManager; «Синхронізувати
   зараз» — миттєвий двобічний merge.

### C.2 Поведінка й межі (для польової перевірки, коли ввімкнемо)

- Після **відновлення** (вхід на новому пристрої) розкриття лягають у Room і **жива мапа доповнюється
  одразу** (`TrackingRepository.refreshAfterRestore`, підключено після review) — без рестарту, без утрати
  локального (D30). Будинки, чиї тайли ще не завантажені, доллються на першому ж завантаженні зони.
- **Право на видалення:** Settings → «Видалити копію з Google Drive» прибирає файл із Drive і вимикає
  бекап (щоб наступний sync не відновив копію). Локальний прогрес не чіпається.
- **Конкурентність:** ручний «синхронізувати зараз» і фоновий Worker серіалізовані процес-локом — без
  дублікатів файлів у Drive чи подвоєних рядків сесій.
- Access-token живе ~1 год; фоновий Worker бере свіжий тихо. Якщо згоду відкликано — Worker тихо
  відкладає (не помилка), користувач повторно входить у Settings.
- **Device-verified НЕ тестувалось** (телефон відключено + потрібен OAuth-клієнт) — компіляція + 261
  юніт-тест + адверсивний review пройдено; реальний вхід/round-trip до Drive — за активацією.

> **`applicationId`.** Рішення власника: **поки лишаємо `no.streif.spike`** (нічого ще не публіковано під
> фінальним id). При першій публікації рекомендовано `app.streif` — точний reverse-DNS від домену
> `streif.app`, який планується купити; ним же закриваються privacy-policy URL (`streif.app/privacy`) і
> власний CDN-домен (`tiles.streif.app`). Той самий рядок піде в `package name` Android-OAuth-клієнта (C.1 §4).

---

### Джерела (офіційні)

- [Use Play App Signing](https://support.google.com/googleplay/android-developer/answer/9842756) — upload key відновлюваний; app signing key при самостійному керуванні — ні
- [Prepare and roll out a release / app bundles](https://support.google.com/googleplay/android-developer/answer/9859152) — APK лише для застосунків, створених до серпня 2021
- [Target API level requirements](https://developer.android.com/google/play/requirements/target-sdk) — API 36 для нових застосунків, дедлайн 31.08.2026 (продовження до 01.11.2026)
- [Testing requirements for personal developer accounts](https://support.google.com/googleplay/android-developer/answer/14151465) — 12/14 стосується акаунтів після 13.11.2023 і **подачі на production**
- [Foreground service requirements](https://support.google.com/googleplay/android-developer/answer/13392821)
- [Data safety section](https://support.google.com/googleplay/android-developer/answer/10787469)
