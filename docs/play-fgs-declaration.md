# Play — декларація Foreground Service (`location`) для Streif

> **Статус:** чернетка v1.0 — 2026-07-20.
> **Куди:** Play Console → *Monitor and improve* → *App content* → **Foreground service permissions**.
> **Що вимагає Play:** для КОЖНОГО задекларованого типу FGS — (1) опис функціональності, (2) наслідки, якщо
> система відкладе/перерве задачу, (3) **посилання на відеодемонстрацію**, (4) вибір use case.
> Тексти нижче — **англійською**, як вимагає Play. Правити можна, зміст — ні.

---

## 1. Що саме декларуємо

Один тип: **`location`** (`AndroidManifest.xml:42` — `android:foregroundServiceType="location"`,
дозвіл `FOREGROUND_SERVICE_LOCATION` у рядку 11).

Інших FGS-типів у застосунку **немає** — у декларації відмічати тільки `location`.

> ✅ **Підтверджено на завантаженому бандлі (2026-07-29), а не лише за нашим вихідним маніфестом.**
> Перевіряти було що: WorkManager у нас використовується двічі (`BackupWorker`, `TelemetryWorker`), а
> свіжі версії тягнуть за собою `FOREGROUND_SERVICE_DATA_SYNC` і власну службу типу `dataSync`. Якби
> це сталося, декларація на самий лише `location` виявилась би неповною — і зʼясувалося б це аж на
> формі, після зйомки відео. В об'єднаному маніфесті release-варіанту:
> `foregroundServiceType="location"` — **один-єдиний**, а з FGS-дозволів лише `FOREGROUND_SERVICE`
> і `FOREGROUND_SERVICE_LOCATION`.
>
> Там же підтверджено ключове твердження §2 і `play-data-safety.md`: **`ACCESS_BACKGROUND_LOCATION`
> у бандлі немає**. Повний перелік — 12 дозволів, серед них жодного несподіваного (локація,
> активність, мережа, сповіщення, WAKE_LOCK, BOOT_COMPLETED).

### Вибір use case

Пресети Play для `location`: *user-initiated location sharing* · *navigation* · ~~*geofencing*~~
(прибрано з квітневих policy-оновлень 2026).

**Жоден не описує нас точно** — ми не шеримо локацію й не навігуємо. Play дозволяє **ввести власний
use case вручну** — робимо саме так:

```
User-initiated walk tracking: the user explicitly starts a walk, and the app records which
buildings and outdoor destinations they pass so the map can be progressively uncovered.
```

⛔ **ВИПРАВЛЕНО 2026-07-29, побачивши справжню форму.** Тут стояло «якщо форма змусить обрати з
переліку — найближчий за змістом **User-initiated location sharing**». **Так робити не можна.**
Цей пресет означає **передавання** геоданих — іншим користувачам або сервісу. Ми не передаємо нічого,
і в `play-data-safety.md` щойно задекларовано **Shared: No по всіх типах**. Рецензент кладе ці дві
форми поруч: в одній «ділимося геоданими», у другій «нічого не передаємо» — готова розбіжність, а
саме на розбіжностях між нашими ж документами нас уже ловили (§B.6 #2).

**Правильна відповідь — «Інше» у групі «Оновлення геоданих у фоновому режимі»** (у формі: *Location →
Для яких завдань потрібен FOREGROUND_SERVICE_LOCATION?*). Група саме та, бо служба отримує оновлення
позиції, коли екран згас і застосунок не на передньому плані. **Не** «Навігація» (маршрутів немає) і
**не** «Геозонування» (Geofencing API не використовуємо; proximity до POI рахується локально в
`TrackingRepository`). Після вибору «Інше» відкривається поле опису — туди текст із §2, і там же
поле для посилання на відео.

*(Історично: колишній варіант із переліку — )* **«User-initiated location sharing»**
(там серед прикладів Play фігурує *activity tracking*), але в текстовому полі все одно описати як вище.

---

## 2. Текст декларації (копіювати в Play Console)

### 2.1 Description of the functionality

> ⚠️ **Переписано 2026-07-27 (§B.6, розсинхрон документів).** Попередня редакція містила **три
> неправдиві твердження** — і два з них були рівно ті, які рецензент уже ловив у політиці приватності
> як BLOCKER:
> 1. *«It cannot access location unless the user has started a walk»* — **неправда**: застосунок читає
>    позицію на **кожному запуску** (`MapController.onMapReady` → `centerOnLastLocation`, `preloadArea`).
>    Саме це формулювання виправляли в політиці §2 і в disclosure — а тут воно лишалось;
> 2. *«Raw location data … never transmitted anywhere»* — трек справді не передається (D14), але
>    **координати покидають пристрій як ключі тайлів** (Kartverket, Cloudflare R2). Так і декларує
>    `play-data-safety.md` §2.1–2.2, тож заперечувати це в сусідньому документі не можна;
> 3. *«There is no account, no server sync, and no analytics»* — акаунт і синк **є** з 2026-07-21
>    (D36, Google Drive appdata), а телеметрія закритого тесту буде (D39).
>
> Рецензент Play кладе ці документи поруч. Розбіжність у декларації локації — типова причина
> відхилення, і саме на ній нас уже ловили.

```
Streif is a walking app that gradually uncovers a map of the user's own neighbourhood. When the
user taps "Start walk", the app starts a foreground service of type "location" and matches each
location update against the outlines of nearby buildings and outdoor destinations. Every building
the user physically walks past is permanently marked as uncovered and takes on colour on their
personal map.

The foreground service is started only by an explicit user action (the "Start walk" button) and
stops when the user taps "Stop walk" or the Stop action in the notification. A persistent, visible
notification ("Streif — walk / Uncovering buildings on your path") is shown for the entire duration
of the walk, so the user always knows that location is being used. The service is the only way the
app receives location while the screen is off.

The app does NOT request or use ACCESS_BACKGROUND_LOCATION. Outside a walk, the app reads location
only while it is open in the foreground: once to centre the map on the user, and to download the
map data for the area they are in. When no walk is running and the app is closed, it does not
receive location at all.

The user's route is never stored and never sent: location updates are processed in memory and only
the resulting list of uncovered building IDs is written to the app's local database. Map requests
to Kartverket and to our own Cloudflare storage do carry the coordinates of the tiles being
requested, as in any map application. The app offers an optional backup to the user's own Google
Drive, which the user turns on themselves; it copies the aggregated progress only — never the
route. During the closed test the app also sends anonymous aggregated diagnostics (matching
accuracy, battery and data-loading statistics), which the user is told about on first run and can
switch off in Settings at any time.
```

⚠️ **Останнє речення прибрати, коли телеметрію закритого тесту буде знято** (D39 передбачає її
видалення після тесту) — інакше документ знову почне описувати те, чого нема.

### 2.2 Why a foreground service is required (наслідки переривання)

```
A walk lasts from several minutes to a few hours, and it is used outdoors, in the user's pocket,
with the screen off. This is the normal and intended way to use the app: people do not walk with
the phone held in front of them.

Continuous location updates while the screen is off are therefore essential to the core function.
If the system defers or interrupts the task, the app misses location updates along the route and
silently fails to uncover the buildings the user actually walked past. From the user's point of
view the walk is simply lost — they did the physical work and the map did not change. Since a
building is uncovered only by being physically visited, there is no way to reconstruct the missed
part of the route afterwards.

No lighter-weight alternative is sufficient:
- WorkManager and periodic/deferred jobs cannot deliver the continuous, timely location stream
  needed to determine which side of a street the user passed on.
- The Geofence API does not apply: we do not monitor a small set of predefined areas. Buildings
  are matched dynamically against thousands of outlines loaded on demand around the user.
- Background location is deliberately not used, because the app must not be able to track the user
  when they have not started a walk themselves.
```

### 2.3 Video link

**YouTube, видимість «Unlisted»** — доступ за посиланням без логіну, не з'являється в пошуку,
посилання не протухає. Google Drive теж приймають, але легко забути відкрити доступ → отримаєш
відмову з формулюванням «reviewer could not access the video».

**Субтитри накладати НЕ треба** (рішення 2026-07-29). Вони були альтернативою озвучці — способом
пояснити те, чого не видно. Після перезйомки пояснювати нічого: інтерфейс і системні діалоги
англійською, а форма має велике текстове поле. Замість титрів — список кроків із таймкодами нижче:
той самий результат без редактора, експорту й ризику зсунути таймінги.

### 2.4 Опис відео з таймкодами (дописати в кінець тексту декларації)

```
The linked video is a single continuous screen recording, no edits, made on the same build that
testers receive.

0:06  The app is opened for the first time. The map is fully visible and every building is grey —
      nothing has been uncovered yet ("Revealed 0 · tap Start").
0:15  Before any location is read, the app shows its own explanation of what location is used for.
0:23  The user taps "Start walk". Only then does the system location prompt appear, and the user
      selects "While using the app" — the app never requests background location.
0:42  The notification shade is opened: an ongoing notification "Streif — walk · Uncovering
      buildings on your path" with a Stop action is visible for the whole walk.
0:50  The screen is switched off and the phone is carried normally, as during a real walk.
1:38  The screen is turned on again: buildings the user walked past are now coloured, and the
      counter has moved from 0 to 4 over 133 metres. This change is only possible because the
      foreground service kept receiving location updates while the screen was off.
2:06  The user taps "Stop walk".
2:10  The notification shade is opened again: the Streif notification is gone. Location access
      ends when the user ends the walk.
```

---

> ✅ **ВІДЕО ЗНЯТО 2026-07-29, другий дубль — перевірено покадрово (ffmpeg + розбір кадрів).**
> Знято на **versionCode 3**, тобто саме на збірці, яку отримають тестери. Мова системи — англійська,
> тож рецензент читає системні діалоги без перекладу. Усі шість кроків присутні:
>
> | Крок | Час | Що в кадрі |
> |---|---|---|
> | 1 | 0:06–0:18 | «Revealed 0 · tap Start» + onboarding + наше пояснення про локацію (обидва екрани) |
> | 2 | 0:23 | «Allow Streif to access this device's location?» → Precise → тап по **While using the app** (індикатор натискання видно) |
> | 3 | 0:42 | «Streif — walk · Uncovering buildings on your path» + дія **Stop** |
> | 4 | ~0:50–1:34 | згаслий екран під час реальної ходьби |
> | 5 | 1:38–2:02 | `Revealed 0 → 4`, 133 м, будинки кольорові |
> | 6 | 2:06–2:10 | «Revealed 4 · **tap Start**» і шторка **без нотифікації Streif** — доказ, що доступ припинився |
>
> ⚠️ Сам файл у git **не кладеться** (`.gitignore`: `*.mp4` тощо) — репозиторій публічний, а запис
> екрана містить екран блокування, шторку й реальний маршрут вулицями.

## 3. Сценарій відео — на один дубль

**Мета рецензента:** побачити, які кроки в застосунку **запускають** фічу, і що вона реально робить.
**Тривалість:** 50-70 секунд. **Без монтажу.** Знімати краще з екрана телефона (вбудований записувач),
а фінальний кадр — камерою (див. крок 5), або весь ролик камерою через плече.

**Головне, що мусить бути видно:** ① кнопка старту → ② системний запит дозволу → ③ **постійна нотифікація**
→ ④ **екран гасне, трекінг триває** → ⑤ карта змінилась → ⑥ явний стоп.

| # | Час | Що на екрані | Що написати субтитром / сказати |
|---|---|---|---|
| 1 | 0:00-0:07 | Головний екран, карта з сірими будинками. Не тапати нічого | «Streif — buildings are grey until you walk past them.» |
| 2 | 0:07-0:15 | Тап **«Start walk»**. З'являється системний діалог дозволу локації → обрати **«While using the app»** | «The walk starts only when the user taps Start walk.» ⚠️ Показати саме варіант *While using the app* — це доводить відсутність background-location |
| 3 | 0:15-0:25 | Потягнути шторку вниз — **велично показати нотифікацію** «Streif — walk · Uncovering buildings on your path» з кнопкою Stop. Затримати 3-4 с, щоб текст читався | «A persistent notification is shown for the whole walk.» |
| 4 | 0:25-0:33 | Закрити шторку, **натиснути кнопку живлення — екран гасне**. Тримати згаслим 5-6 с (у кадрі видно, що екран чорний) | «The service keeps running with the screen off — the phone is in the user's pocket.» |
| 5 | 0:33-0:50 | **Це головний кадр.** Пройти ~30-50 метрів повз кілька будинків із згаслим екраном, потім увімкнути екран. На карті **кілька будинків уже кольорові** | «After walking past them, the buildings are uncovered — this is the core feature.» |
| 6 | 0:50-1:00 | Тап **«Stop walk»** (або Stop у нотифікації). Нотифікація зникає | «The user stops the walk explicitly; location access ends.» |
| 7 | 1:00-1:05 | Статичний кадр карти з розкритими будинками | «No background location is used. Location never leaves the device.» |

### Налаштування телефона перед зйомкою (з'ясовано 2026-07-29)

| Що | Як | Чому |
|---|---|---|
| Звук пристрою | **вимкнути** | Застосунок беззвучний — записувати нічого |
| Мікрофон | **вимкнути** | Озвучка не обов'язкова; обмовка = зайвий перезнятий дубль. Пояснення йде **текстом у формі** (§2), ліміт там великий |
| **Показувати натискання** | **увімкнути** (Налаштування → Система → Для розробників) | Прямо працює на вимогу Google «показати кроки, які має виконати користувач». Без індикатора тап по «Start tur» невидимий — екран змінюється ніби сам, і рецензент не бачить, що дію ініціював користувач. А саме це доводить, що служба не стартує самовільно |
| Розташування вказівника | **НЕ вмикати** | Інша опція: малює перехрестя й смугу координат угорі. У кадрі читається як налагоджувальний режим |
| «Не турбувати» | увімкнути | У кадр не полетять чужі сповіщення (і особисте листування). ⚠️ На пробному записі перевірити, що нотифікація **самого Streif** лишається видимою — вона потрібна для кроку 3 |
| Мережа | **лишити ввімкненою** | Без неї зони не тягнуться й будинки не з'являться взагалі — крок 5 не зніметься |

⚠️ **Ідеальний момент для зйомки — одразу після встановлення з Play, ДО першого входу й ДО видачі
дозволу.** Тоді в кадрі природно з'являються всі три речі, які потім не відтворити дешево: системний
запит дозволу · наше пояснення про локацію (показується **один раз** і запам'ятовується) · сірі
будинки, бо розкриттів ще нуль. Відтворити цей стан потім можна лише через «Очистити сховище», а це
знову стирає прогрес.

### Чек-лист перед дублем (виріс із розбору першого запису, 2026-07-29)

Перший дубль вийшов технічно вдалим — і все одно пішов на перезйомку через дві речі, яких сценарій не
називав. Тому вони тепер тут, перед зйомкою, а не в переліку помилок після.

| # | Перевірити | Чому саме це |
|---|---|---|
| 1 | **Прибрати повідомлення власника з екрана блокування** | У першому дублі там читався номер телефона: «Fant du telefonen? Ring: …». Відео йде в Google і на YouTube |
| 2 | **Шторку тягнути ОДИН раз, не два** | Один рух — самі сповіщення (це все, що треба для кроку 3). Два — розгортаються швидкі налаштування, а там плитка «Гаманець» із останніми цифрами картки |
| 3 | **Мова телефона — англійська** (якщо не шкода часу) | Системні діалоги малюються мовою системи. У першому дублі рецензент побачив би «Коли додаток використовується» українською й не зрозумів, що це саме *While using the app* — тобто головний доказ відсутності background-локації. Альтернатива: описати кроки з таймкодами в текстовому полі форми |
| 4 | **«Очистити сховище» перед дублем** — ТУТ це доречно | Інакше не з'являться ні системний діалог, ні наше пояснення (воно показується один раз і запам'ятовується). ⚠️ Робити лише коли в застосунку нема чого втрачати: одразу після свіжого встановлення так і є. Прогрес живе в Drive-копії й повертається входом |
| 5 | **Дійти до кроку 6 і зупинити прогулянку** | Перший дубль обірвався на 2:58 із живою прогулянкою: показано, як служба вмикається, і не показано, як вимикається. А «користувач явно припиняє доступ до локації» — те, заради чого декларацію й читають |
| 6 | Не тримати згаслий екран довше ~10 с | У першому дублі вийшло ~40 с чорноти посеред відео — рецензент може прийняти це за збій запису |

### Практичні застереження

- **Крок 5 — не імітувати.** Потрібна справжня прогулянка, бо саме зміна карти доводить, навіщо FGS.
  Знімати вдень, щоб на екрані було видно різницю сірий→колір.
- ⚠️ **НЕ «Clear storage»** (тут раніше стояла саме ця порада — знято 2026-07-29). На телефоні тепер
  лежить **бойовий прогрес** — 494 розкриття, перенесені при зміні `applicationId` (§B.0). Стирання
  сховища знищить його; копії є, але платити ними за відео немає причини.
  **Натомість — знімати там, де ще не гуляв.** Ефект «до/після» потрібен саме локальний, і він
  безкоштовно є в будь-якому новому кварталі: у Volda розкрито 454 будинки, а, наприклад, в
  Ulsteinvik — **один**. Тобто досить від'їхати/відійти в незнайому частину, і навколо буде рівно
  той сірий фон, який потрібен кроку 5.
- **Знімати на debug-збірці, але не відкривати Settings.** Перехід на release виглядає правильніше,
  але коштує даних: release підписаний ІНШИМ ключем, тож `adb install -r` не пройде, а перевстановлення
  = стерта тека застосунку. У самому кадрі (мапа · «Start tur» · нотифікація · «Stopp») debug нічим не
  відрізняється — усі dev-секції (набір іконок, мова, режим оцінювання) живуть **усередині Settings**,
  куди за сценарієм заходити не треба.
  > ⚠️ **Застаріло 2026-07-29** — з'явилась збірка з треку. Знімати треба **на ній**: dev-секцій там
  > немає взагалі (вони під `BuildConfig.DEBUG`), тож Settings можна показувати спокійно, і рецензент
  > бачить рівно те, що отримає користувач. Абзац вище лишаю як історію рішення, а не як інструкцію.
- **Записувати ВЕСЬ екран, не «окремий додаток».** Три кроки сценарію відбуваються поза вікном
  застосунку: системний діалог дозволу (крок 2), шторка з нотифікацією (крок 3) і згаслий екран
  (крок 4). Режим «один додаток» знімає лише вікно Streif — тобто рівно ті кадри, які й доводять
  роботу foreground-служби, у запис не потраплять.
- **Без музики й без монтажних склейок.** Рецензент перевіряє достовірність; безперервний дубль читається
  краще за красивий кліп.
- Субтитри достатньо накласти текстом; **озвучка не обов'язкова**. Якщо озвучуєш — англійською.
- Якщо погода/час не дають зняти вулицю — **не підміняти емулятором з fake GPS**. Це помітно і псує довіру
  до всієї декларації. Краще зачекати день.

---

## 4. Пов'язане: prominent disclosure (окрема вимога, легко проґавити)

Політика Play вимагає **prominent in-app disclosure** ПЕРЕД системним запитом дозволу на локацію: окремий
екран/діалог, який пояснює, які дані збираються й навіщо, з кнопкою підтвердження.

⚠️ **Зараз цього немає.** `onboarding_message` (`strings.xml:6`) розповідає про механіку гри, але **не згадує
локацію взагалі**: *«This is your map… Every building you walk past lights up…»*.

Мінімальний фікс — дописати в онбординг-текст (перед першим запитом дозволу) щось на кшталт:

```
Streif needs your location while a walk is running, to detect which buildings you pass.
Location is used only after you tap "Start walk", it is never collected in the background,
and it never leaves your phone.
```

Це **не блокує закритий тест**, але майже напевно спливе при подачі на production. Дешевше зробити зараз —
рядок у `strings.xml` + nb/nn переклади. **Це зміна в Android-коді → задача Дениса / іншого агента, не моя.**

---

### Джерела (офіційні)

- [Understanding foreground service and full-screen intent requirements](https://support.google.com/googleplay/android-developer/answer/13392821) — склад декларації, вимога відео («a link to a video demonstrating each foreground service feature… the steps the user needs to take in your app in order to trigger the feature»), перелік дозволених use case для `location`
- [Foreground service types are required (Android 14+)](https://developer.android.com/about/versions/14/changes/fgs-types-required)
- [Minimum Scope: Foreground Location Access and the Location Button](https://support.google.com/googleplay/android-developer/answer/17033915) — ⚠️ стосується `targetSdk` **37+** (енфорсмент з кінця жовтня 2026). У нас `targetSdk = 36` → **поки не застосовне**, але врахувати при переході на Android 17
