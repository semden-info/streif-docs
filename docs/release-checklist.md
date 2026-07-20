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

| # | Що | Пріоритет | Деталі |
|---|---|---|---|
| 1 | **Змінити `applicationId`** з `no.streif.spike` | 🔴 блокер | B.0 — після першого завантаження вже не змінити |
| 2 | Створити keystore | 🔴 блокер | Частина A |
| 3 | Додати `signingConfigs` + `keystore.properties` у `.gitignore` | 🔴 блокер | A.6 |
| 4 | `versionCode`/`versionName` | 🟡 | Зараз `1` / `"1.0"`. Для тесту радше `versionName = "0.1.0"` — чесніше відображає стан. `versionCode` мусить **зростати** з кожним завантаженням |
| 5 | Prominent disclosure про локацію в онбордингу | 🟡 | `play-fgs-declaration.md` §4 — зараз локація не згадана взагалі. Для closed test не блокер, для production — майже напевно так |
| 6 | Перевірити release-збірку на debug-артефакти | 🟡 | ✓/✗-мітки, перемикач мов, `diag.csv` — усе під `BuildConfig.DEBUG` ✅, але зібрати release і **очима** перевірити |
| 7 | Кнопка «Delete all my data» у Settings | 🟢 бажано | Дає чесне «Yes» у Data safety; DAO-методи вже є (`play-data-safety.md` §4) |
| 8 | Іконка застосунку | 🟢 | Зараз дефолтна Android-іконка (`ic_launcher`) — для тестерів зійде, для сторінки Play виглядатиме неохайно |

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

### Джерела (офіційні)

- [Use Play App Signing](https://support.google.com/googleplay/android-developer/answer/9842756) — upload key відновлюваний; app signing key при самостійному керуванні — ні
- [Prepare and roll out a release / app bundles](https://support.google.com/googleplay/android-developer/answer/9859152) — APK лише для застосунків, створених до серпня 2021
- [Target API level requirements](https://developer.android.com/google/play/requirements/target-sdk) — API 36 для нових застосунків, дедлайн 31.08.2026 (продовження до 01.11.2026)
- [Testing requirements for personal developer accounts](https://support.google.com/googleplay/android-developer/answer/14151465) — 12/14 стосується акаунтів після 13.11.2023 і **подачі на production**
- [Foreground service requirements](https://support.google.com/googleplay/android-developer/answer/13392821)
- [Data safety section](https://support.google.com/googleplay/android-developer/answer/10787469)
