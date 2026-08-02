> ⚠️ **Цей довідник — під СТАРУ шістку категорій.** Схему ухвалено на 11 змістових + `Andre`
> (D42, `08` §15.11); чинний мапінг «код → категорія» живе в `BuildingCategory.kt`, а не тут.
> Колонка «наша категорія» показує історичний стан. ⚠️ Генератора цього файла немає — щоб
> перегенерувати під 12, доведеться його написати.

# Довідник категорій будівель — SSB KLASS #31 проти наших 6

> Згенеровано з `app/src/main/assets/bygningstype.json` (той самий асет, що в застосунку) +
> `manifest.json` (кількість **досяжних** будівель у регіоні Møre og Romsdal, D6).
> Джерело SSB: <https://www.ssb.no/klass/klassifikasjoner/31> · API:
> `https://data.ssb.no/api/klass/v1/classifications/31/codesAt?date=YYYY-MM-DD`

⚠️ **Головне зі звірки:** верхній рівень SSB (`main`, 8 штук) для мапи **гірший** за наші 6 —
він кладе `Naust` і `Garasje` в **Bolig** разом із житлом (група «Garasje og uthus til bolig»),
тобто 161 008 будівель одним кольором. Наші 6 їх розділяють: `housing` 88 147 проти
`outbuilding` 83 795. Для пішохода це різні речі.

**Корисний рівень SSB — середній (`group`, 35 штук):** саме він дає природні назви колекцій
(«Kyrkje», «Butikkbygning», «Lagerbygning»), не зливаючи те, що не можна зливати.

| Група SSB | Верхній рівень SSB | Досяжних | Кодів | Наші категорії в ній |
|---|---|---|---|---|
| Enebolig | Bolig | 68614 | 3 | housing |
| Garasje og uthus til bolig | Bolig | 58700 | 3 | outbuilding |
| Fiskeri- og landbruksbygning | Industri og lagerbygning | 22778 | 6 | outbuilding |
| Fritidsbolig | Bolig | 13003 | 3 | hytte |
| Tomannsbolig | Bolig | 10271 | 4 | housing |
| Rekkehus, kjedehus, andre småhus | Bolig | 7283 | 4 | housing |
| Industribygning | Industri og lagerbygning | 2554 | 5 | other |
| Lagerbygning | Industri og lagerbygning | 2086 | 4 | outbuilding |
| Bygning for overnatting | Hotell-  og restaurantbygning | 1472 | 5 | public |
| Forretningsbygning | Kontor- og forretningsbygning | 1419 | 5 | public |
| Store boligbygg | Bolig | 1273 | 6 | housing |
| Koie, seterhus og lignende | Bolig | 1158 | 2 | hytte |
| Skolebygning | Kultur- og forskningsbygning | 885 | 7 | public |
| Kontorbygning | Kontor- og forretningsbygning | 691 | 4 | public |
| Bygning for religiøse aktiviteter | Kultur- og forskningsbygning | 525 | 6 | sacral |
| Idrettsbygning | Kultur- og forskningsbygning | 507 | 6 | public |
| Kulturhus | Kultur- og forskningsbygning | 494 | 4 | public |
| Annen boligbygning | Bolig | 415 | 2 | housing |
| (без групи) | (немає) | 410 | 3 | other |
| Bygning for bofellesskap | Bolig | 291 | 3 | housing |
| Restaurantbygning | Hotell-  og restaurantbygning | 278 | 4 | public |
| Museums- og biblioteksbygning | Kultur- og forskningsbygning | 274 | 4 | public |
| Garasje- og hangarbygning | Samferdsels- og kommunikasjonsbygning | 169 | 2 | outbuilding |
| Sykehjem | Helsebygning | 157 | 4 | public |
| Ekspedisjonsbygning, terminal | Samferdsels- og kommunikasjonsbygning | 105 | 5 | public |
| Hotellbygning | Hotell-  og restaurantbygning | 104 | 3 | public |
| Beredskapsbygning | Fengsel, beredskapsbygning mv. | 87 | 6 | public |
| Primærhelsebygning | Helsebygning | 81 | 3 | public |
| Veg- og trafikktilsynsbygning | Samferdsels- og kommunikasjonsbygning | 62 | 2 | outbuilding |
| Offentlig toalett | Fengsel, beredskapsbygning mv. | 61 | 1 | public |
| Universitet- og høgskolebygning | Kultur- og forskningsbygning | 35 | 3 | public |
| Sykehus | Helsebygning | 11 | 1 | public |
| Monument | Fengsel, beredskapsbygning mv. | 1 | 1 | public |
| Energiforsyningsbygning | Industri og lagerbygning | 0 | 3 | other |
| Telekommunikasjonsbygning | Samferdsels- og kommunikasjonsbygning | 0 | 1 | public |
| Fengselsbygning | Fengsel, beredskapsbygning mv. | 0 | 1 | public |

⚠️ = група SSB розпадається на кілька наших категорій, тобто перехід на SSB там не безшовний.

## Повний перелік кодів по групах

### Enebolig  ·  Bolig  ·  68614 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 111 | Enebolig | 51815 | housing |
| 113 | Våningshus | 9586 | housing |
| 112 | Enebolig med hybelleilighet, sokkelleilighet o.l. | 7213 | housing |

### Garasje og uthus til bolig  ·  Bolig  ·  58700 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 181 | Garasje, uthus, anneks knyttet til bolig | 46385 | outbuilding |
| 183 | Naust, båthus, sjøbu | 8866 | outbuilding |
| 182 | Garasje, uthus, anneks knyttet til fritidsbolig | 3449 | outbuilding |

### Fiskeri- og landbruksbygning  ·  Industri og lagerbygning  ·  22778 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 241 | Hus for dyr, fôrlager, strølager, frukt- og grønnsakslager, landbrukssilo, høy-/korntørke | 14275 | outbuilding |
| 249 | Annen landbruksbygning | 7526 | outbuilding |
| 244 | Driftsbygning for fiske og fangst, inkl. oppdrettsanlegg | 581 | outbuilding |
| 245 | Naust/redskapshus for fiske | 216 | outbuilding |
| 243 | Veksthus | 128 | outbuilding |
| 248 | Annen fiskeri- og fangstbygning | 52 | outbuilding |

### Fritidsbolig  ·  Bolig  ·  13003 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 161 | Fritidsbygning (hytter, sommerhus o.l.) | 10900 | hytte |
| 163 | Våningshus benyttet som fritidsbolig | 1079 | hytte |
| 162 | Helårsbolig benyttet som fritidsbolig | 1024 | hytte |

### Tomannsbolig  ·  Bolig  ·  10271 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 121 | Tomannsbolig, vertikaldelt | 6910 | housing |
| 122 | Tomannsbolig, horisontaldelt | 2506 | housing |
| 123 | Våningshus, tomannsbolig, vertikaldelt | 489 | housing |
| 124 | Våningshus, tomannsbolig, horisontaldelt | 366 | housing |

### Rekkehus, kjedehus, andre småhus  ·  Bolig  ·  7283 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 131 | Rekkehus | 3835 | housing |
| 136 | Andre småhus med 3 boliger eller flere | 2850 | housing |
| 133 | Kjedehus inkl. atriumhus | 411 | housing |
| 135 | Terrassehus | 187 | housing |

### Industribygning  ·  Industri og lagerbygning  ·  2554 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 219 | Annen industribygning | 1088 | other |
| 212 | Verkstedbygning | 706 | other |
| 211 | Fabrikkbygning | 359 | other |
| 216 | Bygning for vannforsyning, bl.a. pumpestasjon | 247 | other |
| 214 | Bygning for renseanlegg | 154 | other |

### Lagerbygning  ·  Industri og lagerbygning  ·  2086 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 231 | Lagerhall | 1120 | outbuilding |
| 239 | Annen lagerbygning | 939 | outbuilding |
| 232 | Kjøle- og fryselager | 27 | outbuilding |
| 233 | Silobygning | 0 | outbuilding |

### Bygning for overnatting  ·  Hotell-  og restaurantbygning  ·  1472 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 524 | Campinghytte/utleiehytte | 639 | public |
| 522 | Vandrerhjem, feriehjem/-koloni, turisthytte | 595 | public |
| 529 | Annen bygning for overnatting | 191 | public |
| 523 | Appartement | 34 | public |
| 521 | Hospits, pensjonat | 13 | public |

### Forretningsbygning  ·  Kontor- og forretningsbygning  ·  1419 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 322 | Butikkbygning | 846 | public |
| 329 | Annen forretningsbygning | 350 | public |
| 323 | Bensinstasjon | 115 | public |
| 321 | Kjøpesenter, varehus | 106 | public |
| 330 | Messe- og kongressbygning | 2 | public |

### Store boligbygg  ·  Bolig  ·  1273 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 142 | Store frittliggende boligbygg på 3 og 4 etasjer | 758 | housing |
| 141 | Store frittliggende boligbygg på 2 etasjer | 233 | housing |
| 143 | Store frittliggende boligbygg på 5 etasjer eller over | 106 | housing |
| 145 | Store sammenbygde boligbygg på 3 og 4 etasjer | 79 | housing |
| 146 | Store sammenbygde boligbygg på 5 etasjer og over | 70 | housing |
| 144 | Store sammenbygde boligbygg på 2 etasjer | 27 | housing |

### Koie, seterhus og lignende  ·  Bolig  ·  1158 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 171 | Seterhus, sel, rorbu o.l. | 951 | hytte |
| 172 | Skogs- og utmarkskoie, gamme | 207 | hytte |

### Skolebygning  ·  Kultur- og forskningsbygning  ·  885 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 612 | Barnehage | 294 | public |
| 613 | Barneskole | 195 | public |
| 619 | Annen skolebygning | 163 | public |
| 611 | Lekepark | 89 | public |
| 616 | Videregående skole | 59 | public |
| 614 | Ungdomsskole | 46 | public |
| 615 | Kombinert barne- og ungdomsskole | 39 | public |

### Kontorbygning  ·  Kontor- og forretningsbygning  ·  691 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 311 | Kontor- og administrasjonsbygning, rådhus | 364 | public |
| 319 | Annen kontorbygning | 272 | public |
| 312 | Bankbygning, posthus | 51 | public |
| 313 | Mediebygning | 4 | public |

### Bygning for religiøse aktiviteter  ·  Kultur- og forskningsbygning  ·  525 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 672 | Bedehus, menighetshus | 258 | sacral |
| 671 | Kirke, kapell | 152 | sacral |
| 673 | Krematorium, gravkapell, bårehus | 68 | sacral |
| 679 | Annen bygning for religiøse aktiviteter | 47 | sacral |
| 674 | Synagoge, moské | 0 | sacral |
| 675 | Kloster | 0 | sacral |

### Idrettsbygning  ·  Kultur- og forskningsbygning  ·  507 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 659 | Annen idrettsbygning | 330 | public |
| 651 | Idrettshall | 90 | public |
| 654 | Tribune og idrettsgarderobe | 52 | public |
| 655 | Helsestudio | 19 | public |
| 653 | Svømmehall | 15 | public |
| 652 | Ishall | 1 | public |

### Kulturhus  ·  Kultur- og forskningsbygning  ·  494 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 662 | Samfunnshus, grendehus | 323 | public |
| 669 | Annet kulturhus | 143 | public |
| 661 | Kinobygning, teaterbygning, opera/konserthus | 16 | public |
| 663 | Diskotek | 12 | public |

### Annen boligbygning  ·  Bolig  ·  415 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 199 | Annen boligbygning (f.eks. sekundærbolig reindrift) | 272 | housing |
| 193 | Boligbrakker | 143 | housing |

### (без групи)  ·  (немає)  ·  410 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 999 | Ukjent bygningstype | 410 | other |
| 956 | Turisthytter | 0 | other |
| 970 | Sykehus med akuttmottak | 0 | other |

### Bygning for bofellesskap  ·  Bolig  ·  291 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 151 | Bo- og servicesenter | 176 | housing |
| 159 | Annen bygning for bofellesskap | 74 | housing |
| 152 | Studenthjem/studentboliger | 41 | housing |

### Restaurantbygning  ·  Hotell-  og restaurantbygning  ·  278 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 531 | Restaurantbygning, kafébygning | 113 | public |
| 533 | Gatekjøkken, kioskbygning | 112 | public |
| 539 | Annen restaurantbygning | 45 | public |
| 532 | Sentralkjøkken, kantinebygning | 8 | public |

### Museums- og biblioteksbygning  ·  Kultur- og forskningsbygning  ·  274 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 641 | Museum, kunstgalleri | 212 | public |
| 649 | Annen museums- og bibliotekbygning | 50 | public |
| 642 | Bibliotek, mediatek | 9 | public |
| 643 | Zoologisk og botanisk hage | 3 | public |

### Garasje- og hangarbygning  ·  Samferdsels- og kommunikasjonsbygning  ·  169 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 439 | Annen garasje- hangarbygning | 150 | outbuilding |
| 431 | Parkeringshus | 19 | outbuilding |

### Sykehjem  ·  Helsebygning  ·  157 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 722 | Bo- og behandlingssenter, aldershjem | 77 | public |
| 721 | Sykehjem | 53 | public |
| 723 | Rehabiliteringsinstitusjon, kurbad | 16 | public |
| 729 | Annet sykehjem | 11 | public |

### Ekspedisjonsbygning, terminal  ·  Samferdsels- og kommunikasjonsbygning  ·  105 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 419 | Annen ekspedisjons- og terminalbygning | 51 | public |
| 415 | Godsterminal | 27 | public |
| 411 | Ekspedisjonsbygning, flyterminal, kontrolltårn | 16 | public |
| 416 | Postterminal | 7 | public |
| 412 | Jernbane- og T-banestasjon | 4 | public |

### Hotellbygning  ·  Hotell-  og restaurantbygning  ·  104 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 511 | Hotellbygning | 77 | public |
| 519 | Annen hotellbygning | 21 | public |
| 512 | Motellbygning | 6 | public |

### Beredskapsbygning  ·  Fengsel, beredskapsbygning mv.  ·  87 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 822 | Brannstasjon, ambulansestasjon | 72 | public |
| 823 | Fyrstasjon, losstasjon | 11 | public |
| 821 | Politistasjon | 4 | public |
| 824 | Stasjon for radarovervåkning av fly- og/eller skipstrafikk | 0 | public |
| 825 | Tilfluktsrom/bunker | 0 | public |
| 829 | Annen beredskapsbygning | 0 | public |

### Primærhelsebygning  ·  Helsebygning  ·  81 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 739 | Annen primærhelsebygning | 36 | public |
| 731 | Klinikk, legekontor/-senter/-vakt | 25 | public |
| 732 | Helse- og sosialsenter, helsestasjon | 20 | public |

### Veg- og trafikktilsynsbygning  ·  Samferdsels- og kommunikasjonsbygning  ·  62 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 449 | Annen veg- og trafikktilsynsbygning | 51 | outbuilding |
| 441 | Trafikktilsynsbygning | 11 | outbuilding |

### Offentlig toalett  ·  Fengsel, beredskapsbygning mv.  ·  61 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 840 | Offentlig toalett | 61 | public |

### Universitet- og høgskolebygning  ·  Kultur- og forskningsbygning  ·  35 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 621 | Universitets- og høgskolebygning med integrerte funksjoner, auditorium, lesesal o.a. | 18 | public |
| 629 | Annen universitets-, høgskole- og forskningsbygning | 16 | public |
| 623 | Laboratoriebygning | 1 | public |

### Sykehus  ·  Helsebygning  ·  11 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 719 | Sykehus | 11 | public |

### Monument  ·  Fengsel, beredskapsbygning mv.  ·  1 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 830 | Monument | 1 | public |

### Energiforsyningsbygning  ·  Industri og lagerbygning  ·  0 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 221 | Kraftstasjon (>15 000 kVA) | 0 | other |
| 223 | Transformatorstasjon (>10 000 kVA) | 0 | other |
| 229 | Annen energiforsyningsbygning | 0 | other |

### Telekommunikasjonsbygning  ·  Samferdsels- og kommunikasjonsbygning  ·  0 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 429 | Telekommunikasjonsbygning | 0 | public |

### Fengselsbygning  ·  Fengsel, beredskapsbygning mv.  ·  0 досяжних

| код | назва | досяжних | наша категорія |
|---|---|---|---|
| 819 | Fengselsbygning | 0 | public |
