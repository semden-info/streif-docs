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

### Вибір use case

Пресети Play для `location`: *user-initiated location sharing* · *navigation* · ~~*geofencing*~~
(прибрано з квітневих policy-оновлень 2026).

**Жоден не описує нас точно** — ми не шеримо локацію й не навігуємо. Play дозволяє **ввести власний
use case вручну** — робимо саме так:

```
User-initiated walk tracking: the user explicitly starts a walk, and the app records which
buildings and outdoor destinations they pass so the map can be progressively uncovered.
```

Якщо форма змусить обрати з переліку — найближчий за змістом **«User-initiated location sharing»**
(там серед прикладів Play фігурує *activity tracking*), але в текстовому полі все одно описати як вище.

---

## 2. Текст декларації (копіювати в Play Console)

### 2.1 Description of the functionality

```
Streif is a walking app that gradually uncovers a map of the user's own neighbourhood. When the
user taps "Start walk", the app starts a foreground service of type "location" and matches each
location update against the outlines of nearby buildings and outdoor destinations. Every building
the user physically walks past is permanently marked as uncovered and takes on colour on their
personal map.

The foreground service is started only by an explicit user action (the "Start walk" button) and
stops when the user taps "Stop walk" or the Stop action in the notification. A persistent, visible
notification ("Streif — walk / Uncovering buildings on your path") is shown for the entire duration
of the walk, so the user always knows that location is being used.

The app does NOT request or use ACCESS_BACKGROUND_LOCATION. It cannot access location unless the
user has started a walk in the app. Raw location data is processed in memory on the device and is
never transmitted anywhere; only the resulting list of uncovered building IDs is stored, locally,
in the app's own database. There is no account, no server sync, and no analytics.
```

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

Заповнити після зйомки (див. §3). Порада: **YouTube, видимість «Unlisted»** — доступ за посиланням без
логіну, не з'являється в пошуку, посилання не протухає. Google Drive теж приймають, але легко забути
відкрити доступ → отримаєш відмову з формулюванням «reviewer could not access the video».

---

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

### Практичні застереження

- **Крок 5 — не імітувати.** Потрібна справжня прогулянка, бо саме зміна карти доводить, навіщо FGS.
  Знімати вдень, щоб на екрані було видно різницю сірий→колір.
- **Перед зйомкою скинути стан**, інакше будинки навколо вже розкриті й «до/після» не видно:
  Settings → Apps → Streif → Storage → *Clear storage*. (Потім доведеться заново дати дозвіл — це навіть
  плюс, крок 2 вийде природним.)
- **Знімати на release-збірці або принаймні без debug-оверлеїв** — ✓/✗-мітки й перемикач мов у debug
  (`MapController.kt:964`, `WalkScreen.kt:144`) виглядають як «недороблений застосунок».
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
