# Сторінка Google Play — тексти (чернетка)

> **Статус:** чернетка v0.1, 2026-07-29. Голос узято з `docs/outreach/streif-brev-bokmal.txt` і
> `01-product-vision.md` — не вигадувався наново. **Норвезьку вичитати Денисові** перед вставкою.
> Куди вставляти: `release-checklist` §B.3 кроки 7 (англійська) і 8 (bokmål).
>
> ⚠️ **Головне правило цього файла.** Рецензент Play кладе опис поруч із `play-data-safety.md` і
> політикою приватності. Розбіжність у твердженнях про локацію — типова причина відхилення, і саме на
> ній нас уже ловили (§B.6 #2: «локація не покидає телефон» суперечило власній декларації
> Location=Collected). Тому тут **не** сказано «нічого не покидає пристрій»: сказано, що НЕ
> зберігається й не надсилається **маршрут**, і окремо — що позиція доходить до картосерверів, бо
> тайли тягнуться навколо тебе. Це збігається з `play-data-safety.md` §2.1–2.2 і п. 2-3 політики.

---

## Ліміти Play

| Поле | Ліміт | Наш текст |
|---|---|---|
| App name | 30 символів | 6 (`Streif`) |
| Short description | 80 символів | en **71** · nb **61** |
| Full description | 4000 символів | en **1998** · nb **1904** |
| Release notes | 500 символів **на мову** | en **457** · nb **463** (перша версія була 535 — не вміщалась) |

*(Числа зміряні, не на око — якщо правитимеш тексти, переміряй: Play ріже мовчки.)*

---

## English (default language: English (United States))

### App name

```
Streif
```

*(Альтернатива, якщо захочеш пояснювальну назву — 24 символи: `Streif: uncover your map`. Рекомендую
голе `Streif`: бренд коротший і не прив'язує назву до однієї механіки.)*

### Short description (80)

```
Walk your neighbourhood and watch it light up on an open Norwegian map.
```

### Full description

```
Streif turns your everyday walks into a map you uncover yourself.

Every building you walk past lights up in colour by what it is — homes, outbuildings, public buildings, churches. Everything else stays visible in grey. Over time you can see how much of your own town you have actually seen, and where you have never been.

A VISIBLE MAP, ALWAYS
Streif never hides the terrain. There is no fog of war. Paths, contours and hazards are visible everywhere, including where you have not walked yet. That is a safety decision, not a design one — you should be able to plan where to go.

BUILT ON NORWAY'S OPEN MAP DATA
Buildings come from Kartverket's open data and OpenStreetMap, the base map is Kartverket's own, and settlement boundaries come from SSB. Nothing here is scraped from anyone else's service.

CALM BY DEFAULT
No streaks. No daily pressure. No score to chase. You see how much you have covered and how varied it is, in plain numbers. Take a week off and nothing is lost or reset.

YOUR DATA
Your progress is stored on your phone. Streif does not record or send your route — no GPS track leaves the device, and none is kept after a walk. Like any map app, the area around you is fetched while you walk, so your approximate position does reach the map servers.

You can turn on backup to your own Google Drive if you want your progress to survive a new phone. That copy holds only what you have uncovered — never a route. No account is needed to use Streif.

While Streif is in closed testing, the app also sends anonymous statistics so that problems on phones other than the developer's can be found and fixed. You are asked about this at first launch and can switch it off at any time.

LANGUAGES
English, bokmål and nynorsk.

Streif is a non-commercial, public-benefit project made in Ørsta/Volda. It is meant to complement local offerings such as StikkUT!, not to compete with them: where StikkUT! highlights destinations, Streif is about the everyday exploring close to where you live.
```

---

## Norsk bokmål (локалізація `no-NO`)

### App name

```
Streif
```

### Short description (80)

```
Gå tur i nabolaget og se det lyse opp på et åpent norsk kart.
```

### Full description

```
Streif gjør de daglige turene dine om til et kart du avdekker selv.

Hver bygning du går forbi lyser opp i farge etter hva den er — boliger, uthus, offentlige bygg, kirker. Resten av kartet blir stående synlig i grått. Etter hvert ser du hvor mye av ditt eget sted du faktisk har sett, og hvor du aldri har vært.

ET SYNLIG KART, ALLTID
Streif skjuler aldri terrenget. Det finnes ingen tåke. Stier, høydekurver og farer er synlige overalt, også der du ikke har gått. Det er et sikkerhetsvalg, ikke et designvalg — du skal kunne planlegge hvor du går.

BYGD PÅ NORGES ÅPNE KARTDATA
Bygningene kommer fra Kartverkets åpne data og OpenStreetMap, bakgrunnskartet er Kartverkets eget, og tettstedsgrensene kommer fra SSB.

ROLIG SOM STANDARD
Ingen streaks. Ingen daglig mas. Ingen poengsum å jage. Du ser hvor mye du har dekket og hvor variert det er, i vanlige tall. Tar du en uke fri, mister du ingenting.

DATAENE DINE
Framgangen din ligger på telefonen din. Streif verken lagrer eller sender ruten din — ingen GPS-spor forlater enheten, og ingen blir liggende igjen etter en tur. Som i enhver kartapp hentes området rundt deg mens du går, så den omtrentlige posisjonen din når kartserverne.

Du kan slå på sikkerhetskopi til din egen Google Disk hvis du vil at framgangen skal overleve en ny telefon. Den kopien inneholder bare det du har avdekket — aldri en rute. Du trenger ingen konto for å bruke Streif.

Mens Streif er i lukket test, sender appen også anonym statistikk, slik at feil på andre telefoner enn utviklerens kan bli funnet og rettet. Du får spørsmålet ved første oppstart og kan slå det av når som helst.

SPRÅK
Engelsk, bokmål og nynorsk.

Streif er et ikke-kommersielt, allmennyttig prosjekt laget i Ørsta/Volda. Det er ment å utfylle lokale tilbud som StikkUT!, ikke å konkurrere med dem: der StikkUT! løfter fram turmål, handler Streif om den daglige utforskingen tett på der folk bor.
```

---

## Що ще потрібно для §B.3 крок 7

| Матеріал | Стан |
|---|---|
| Іконка 512×512 | ✅ `docs/store-assets/play-icon-512.png` |
| Скріншоти (мін. 2, треба 4-6) | ⏳ **знімати у Volda** — там мапа кольорова й плашка узгоджена. З Ulsteinvik кадр вийде безглуздий: «0,0% av Ulsteinvik» над зафарбованою Volda |
| Feature graphic 1024×500 | 🟡 **чернетка є**: `play-feature-1024x500-en.png` / `-nb.png`. RGB без альфи (вимога Play). Права частина — **справжній** знімок зафарбованої Volda, не колаж: графіка показує механіку такою, якою вона є. Кегль підбирається автоматично під ширину колонки — норвезький рядок довший за англійський і при фіксованому кеглі наліз би на мапу саме в тій локалі, яку побачить більшість тестерів |

---

## Release notes для першого релізу (ліміт 500 символів на мову)

> Для закритого тесту це **перше, що читає тестер**, тож три речі мусять бути тут, а не «десь у
> політиці»: (1) де взагалі є дані — інакше людина поза Møre og Romsdal вирішить, що застосунок
> зламаний; (2) що йде анонімна статистика — раніше, ніж вона побачить екран згоди; (3) що саме
> просимо повідомляти, бо інакше зворотний зв'язок буде «прикольно» замість корисного.
>
> ⚠️ **Покриття звірено з `manifest.json` на R2, не з пам'яті** (2026-07-29): `region` = **Møre og
> Romsdal**, **27 комун**, 236 456 будинків / 204 319 доступних. Стара нотатка «засіяно лише
> Volda/Ørsta» була застарілою — сьогодні застосунок польово тягнув зони під Ulsteinvik (Ulstein,
> 1516), і вони прийшли з даними.

### English

```
First closed test build.

Walk past a building and it lights up in colour by type. Also: nature POIs, a progress screen, optional Google Drive backup, four map styles.

Building data covers Møre og Romsdal. Outside the county the map stays grey — missing data, not a bug.

The app sends anonymous statistics during the test. You can switch it off in Settings.

Please report anything odd — especially a building that lights up when you did not walk past it.
```

### Norsk (no-NO, bokmål)

```
Første versjon i lukket test.

Gå forbi en bygning, og den lyser opp i farge etter type. Dessuten: turmål i naturen, framgangsskjerm, valgfri sikkerhetskopi til Google Disk og fire kartstiler.

Bygningsdata dekker Møre og Romsdal. Utenfor fylket forblir kartet grått — manglende data, ikke en feil.

Appen sender anonym statistikk under testen. Du kan slå det av i Innstillinger.

Si fra om noe er rart — særlig en bygning som lyser opp uten at du gikk forbi den.
```

---

### Про відео для FGS-декларації

**Обов'язкове, не опційне** — перевірено на support.google.com 2026-07-29. Форма прямо каже:
«Include a link to a video demonstrating each foreground service feature. The video should
demonstrate the steps the user needs to take in your app in order to trigger the feature».
Декларацію подають **усі** застосунки з targetSdk ≥ 34, які використовують foreground-служби; у нас
`targetSdk = 36` і `FOREGROUND_SERVICE_LOCATION`, тож застосовується.

⚠️ Попередній застосунок Дениса проходив без відео — майже напевно тому, що не мав
foreground-служби (або таргетував SDK до 34, коли декларації ще не існувало). Це не прецедент.
Сценарій зйомки — `play-fgs-declaration.md` §3.
