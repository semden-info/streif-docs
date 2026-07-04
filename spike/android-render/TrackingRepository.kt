package no.streif.spike

import android.location.Location
import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection

/**
 * Spike-2 — ядро трекінгу (singleton; міст між WalkTrackingService і MainActivity).
 *
 * Stage A: accuracy-gate (fail-closed) + мінімальне переміщення + сегмент-матчинг (D5) +
 * збереження (тип+час) + статистика (Coverage/Variety/Discovery, D13).
 * Stage B (далі): vehicle/bike-gate (ActivityGate) перед матчингом.
 * Усе на main-looper (Fused callback), тож без синхронізації.
 *
 * Сесійні межі: «якір» сегмента (lastLat/lastLon) скидається на старті КОЖНОЇ прогулянки —
 * інакше перший фікс після Stop→переїзд→Start прокреслив би фантомний відрізок (баг-фікс рев'ю).
 */
object TrackingRepository {

    interface Listener {
        fun onReveal(fc: FeatureCollection, total: Int)
        fun onLocation(loc: Location, acceptedForMatch: Boolean, note: String)
    }

    const val ACC_MAX = 30f
    const val MIN_MOVE = 2.0

    // Edge-eligibility + CENTROID-closest-approach gate (D25 → D25.1, польовий ретест 2026-06-27):
    const val R_FAR = 18.0          // стіна ≤ R_FAR → будинок «у грі» (eligibility; через дорогу теж)
    const val MIN_EDGE_NEAR = 3.0   // стіна ≤ MIN_EDGE_NEAR (або всередині footprint) → розкрити ОДРАЗУ (впритул)
    const val SLACK_CEN = 1.0       // центроїд виріс на SLACK_CEN над мінімумом → проминув СЕРЕДИНУ → розкрити. 2→1 (фідбек 2026-07-04: розкривати ПРОМПТніше, менше «після проходу»; recall/precision не міняються — replay)
    const val R_TRACK = 30.0        // D23 #4: ширший радіус ВІДСТЕЖЕННЯ centroid-CA (щоб дотичний прохід не випав із кандидатів до підтвердження); розкриваємо лише eligible (стіна колись ≤ R_FAR)
    private const val SOURCE = "osm"   // D30: id-простір джерела розкриттів (dogfood OSM; продакшн → "matrikkelen")

    @Volatile var isTracking = false
    val hasStore: Boolean get() = store != null
    val currentStore: BuildingStore? get() = store   // D23 #14: reattach store після пересоздання Activity

    val revealed = LinkedHashSet<Int>()
    var listener: Listener? = null
    var areaLoader: AreaLoader? = null             // on-demand завантаження зон (D24)

    private var store: BuildingStore? = null
    private var visitDao: VisitDao? = null                     // Room-персистенція розкриттів (D11)
    private var sessionDao: SessionDao? = null                 // Room-сесії: insert@start + checkpoint (лікує D23 #11)
    private var debugVisitStore: VisitStore? = null            // DEBUG-дубль у visited.txt для analyze.py
    @Volatile private var sessionRowId: Long = 0              // rowId поточної сесії (dbIo-owned; інкрементальний checkpoint)
    private var fixesSinceCp = 0                               // фіксів від останнього session-checkpoint
    private var diag: DiagnosticRecorder? = null   // diagnostic-збір (лише debug; off у release)
    private val persistedIds = HashSet<String>()   // збережені розкриття (відновлюємо при завантаженні зон; лише main)

    // MVP-0-полір (D11): усі Room/файл-записи поза main-looper (reveal-колбек на main → блокуючий DB давав би jank/ANR)
    private val dbIo = java.util.concurrent.Executors.newSingleThreadExecutor()   // FIFO — серіалізує всі DB-операції
    private val dbMain = android.os.Handler(android.os.Looper.getMainLooper())
    private val revealedFeatures = ArrayList<Feature>()
    private val byType = HashMap<String, Int>()
    private var lastLat = Double.NaN
    private var lastLon = Double.NaN
    private val candIdx = ArrayList<Int>(64)
    private val candEdge = ArrayList<Double>(64)
    private val candCen = ArrayList<Double>(64)
    private val runMin = HashMap<Int, Double>()    // bIdx → мін. відстань до ЦЕНТРОЇДА (closest-approach тайминг, D25.1)
    private val eligible = HashSet<Int>()          // D23 #4: будинки, чия стіна колись була ≤ R_FAR (лише їх розкриваємо за passedMiddle)
    private val dist = FloatArray(1)
    // C2/D23 #5: нещодавній шлях — replay при завантаженні зони (поки тягнулась, ти вже пройшов повз будинки).
    // Вікно за ЧАСОМ (не фіксовані 12 фіксів) — холодний Overpass-fetch може тривати >24с.
    private val recentT = ArrayList<Long>()
    private val recentLat = ArrayList<Double>()
    private val recentLon = ArrayList<Double>()
    private const val RECENT_WINDOW_MS = 90_000L   // тримати ~останні 90 с шляху
    private const val RECENT_CAP = 240             // страховка від нескінченного росту при стоянні
    private const val PREFETCH_AHEAD_M = 1000.0    // (P) префетч тайла за стільки метрів попереду руху

    // поточна сесія (Discovery)
    private var sessionNew = 0
    private var sessionDistanceM = 0.0
    private var sessionStartTs = 0L

    fun init(store: BuildingStore, db: MvpDatabase, filesDir: java.io.File, debugVisitStore: VisitStore?, diag: DiagnosticRecorder?) {
        this.store = store
        this.visitDao = db.visits()
        this.sessionDao = db.sessions()
        this.debugVisitStore = debugVisitStore
        this.diag = diag
        revealed.clear(); revealedFeatures.clear(); byType.clear(); persistedIds.clear(); runMin.clear(); eligible.clear()
        lastLat = Double.NaN; lastLon = Double.NaN
        // MVP-0-полір: міграція visited.txt→Room + читання збережених розкриттів поза main; reconcile+UI назад на main.
        dbIo.execute {
            MvpImporter.importVisitsOnce(db, filesDir)
            val ids = db.visits().all().map { it.buildingId }
            dbMain.post {
                persistedIds.addAll(ids)
                reconcilePersisted()   // on-demand: зазвичай порожньо (store ще без зон) — добере onAreaLoaded
                listener?.onReveal(FeatureCollection.fromFeatures(ArrayList(revealedFeatures)), revealed.size)
            }
        }
    }

    /** Відновити збережені розкриття, чиї будинки вже є в store (після завантаження зони). */
    private fun reconcilePersisted() {
        val s = store ?: return
        for (id in persistedIds) {
            var idx = s.indexOf(id)
            if (idx == null && id.isNotEmpty() && id.all { it.isDigit() }) idx = s.indexOf("w$id")  // C3: legacy bare-id → w<id>
            if (idx == null) continue
            if (revealed.add(idx)) {
                val f = s.featureAt(idx)
                revealedFeatures.add(f)
                val type = f.getStringProperty("type") ?: "other"
                byType[type] = (byType[type] ?: 0) + 1
            }
        }
    }

    /** Викликати на main після завантаження нової зони (AreaLoader callback). */
    fun onAreaLoaded() {
        reconcilePersisted()                       // відновити збережене з нової зони
        // D23 #3: replay шляху — лише поки сесія активна (інакше зона, що довантажилась після Stop,
        // розкривала б будинки без сесії / зі старого місця).
        if (store != null && isTracking) {
            // C2: replay нещодавнього шляху через ТОЙ САМИЙ gated-матчер (closest-approach),
            // а не безкурсовий within-R — інакше довантажена зона розкривала б будинки попереду зарано.
            // D23 #2: `moved` — з РЕАЛЬНОГО зсуву між сусідніми фіксами (не i>0), інакше джитер стоячи
            // під час завантаження зони хибно розкрив би будинок на replay.
            var pl = Double.NaN; var po = Double.NaN
            for (i in recentLat.indices) {
                val mv = if (pl.isNaN()) false else {
                    Location.distanceBetween(pl, po, recentLat[i], recentLon[i], dist); dist[0] >= MIN_MOVE
                }
                matchAt(recentLat[i], recentLon[i], mv)
                pl = recentLat[i]; po = recentLon[i]
            }
        }
        listener?.onReveal(FeatureCollection.fromFeatures(ArrayList(revealedFeatures)), revealed.size)
    }

    /** Початок сесії — скинути якір + лічильники маршруту. */
    fun startSession() {
        lastLat = Double.NaN; lastLon = Double.NaN; runMin.clear(); eligible.clear()
        recentT.clear(); recentLat.clear(); recentLon.clear()
        sessionNew = 0; sessionDistanceM = 0.0; sessionStartTs = System.currentTimeMillis()
        fixesSinceCp = 0
        // D23 #11: рядок сесії існує ВІД старту → краш/OOM посеред прогулянки не губить усю сесію
        val ts = sessionStartTs   // MVP-0-полір: insert off-main; rowId ставимо в dbIo (наступні update/delete — той самий FIFO-executor)
        dbIo.execute { sessionRowId = sessionDao?.insert(SessionEntity(startTs = ts, endTs = 0, distanceM = 0.0, newCount = 0)) ?: 0 }
        ActivityGate.reset()
    }

    private fun pushRecent(lat: Double, lon: Double) {
        val now = System.currentTimeMillis()
        recentT.add(now); recentLat.add(lat); recentLon.add(lon)
        val cutoff = now - RECENT_WINDOW_MS                      // D23 #5: евікт за часом, не за к-стю
        while (recentT.isNotEmpty() && recentT[0] < cutoff) {
            recentT.removeAt(0); recentLat.removeAt(0); recentLon.removeAt(0)
        }
        while (recentT.size > RECENT_CAP) {                      // страховка від росту при стоянні
            recentT.removeAt(0); recentLat.removeAt(0); recentLon.removeAt(0)
        }
    }

    /** Кінець сесії — записати підсумок (фундамент тижневого підсумку/рейтингів). */
    fun endSession() {
        val ts = sessionStartTs; val d = sessionDistanceM; val n = sessionNew; val now = System.currentTimeMillis()
        dbIo.execute {   // MVP-0-полір: off-main; sessionRowId читаємо/скидаємо в тому ж FIFO-executor
            val id = sessionRowId
            if (id > 0L) {
                if (n > 0 || d >= 1.0) sessionDao?.update(SessionEntity(id, ts, now, d, n))
                else sessionDao?.delete(id)   // Start→Stop без руху — прибрати порожній рядок
            }
            sessionRowId = 0
        }
        lastLat = Double.NaN; lastLon = Double.NaN; sessionStartTs = 0L
        recentT.clear(); recentLat.clear(); recentLon.clear()   // D23 #3: не лишати шлях для replay після Stop
    }

    /** Інкрементальний checkpoint сесії (D23 #11) — щоб краш не з'їв прогрес між reveal-ами. */
    private fun checkpointSession() {
        val ts = sessionStartTs; val d = sessionDistanceM; val n = sessionNew; val now = System.currentTimeMillis()
        dbIo.execute { val id = sessionRowId; if (id > 0L) sessionDao?.update(SessionEntity(id, ts, now, d, n)) }
    }

    fun revealedCollection(): FeatureCollection = FeatureCollection.fromFeatures(ArrayList(revealedFeatures))

    fun stats(): Stats = Stats(revealed.size, store?.accessibleCount ?: 0, HashMap(byType), sessionNew, sessionDistanceM)

    fun onLocation(loc: Location) {
        val s = store ?: return
        val gateOk = ActivityGate.allow(loc.speed, loc.hasSpeed())  // Stage B: vehicle/bike + швидкість (D5)
        if (!gateOk) { lastLat = Double.NaN; lastLon = Double.NaN }  // не мостимо сегмент через авто/велосипед
        // D24 prefetch зони — НЕ під dwell-гейтом (D23 #6: fetch має стартувати одразу, а не після 3 dwell-фіксів),
        // лише пропускаємо авто-швидкість (марні тайли/Overpass-виклики)
        if (!(loc.hasSpeed() && loc.speed > ActivityGate.MAX_PED_SPEED)) {
            areaLoader?.ensureArea(loc.latitude, loc.longitude)     // поточний тайл
            prefetchAhead(loc)                                     // (P) наступний тайл НАПЕРЕД руху — щоб був до того, як дійдеш
        }
        val accOk = loc.hasAccuracy() && loc.accuracy <= ACC_MAX     // fail-closed
        val matchable = gateOk && accOk
        val note = when {
            !gateOk -> ActivityGate.blockedReason
            !accOk -> "точність низька"
            else -> areaLoader?.status?.ifEmpty { "" } ?: ""
        }
        listener?.onLocation(loc, matchable, note)                  // маркер «ти тут» завжди
        var matched = 0
        if (matchable) {
            var moved = true                                          // перший фікс — байдуже (runMin порожній)
            if (!lastLat.isNaN()) {
                Location.distanceBetween(lastLat, lastLon, loc.latitude, loc.longitude, dist)
                moved = dist[0] >= MIN_MOVE
                if (moved) sessionDistanceM += dist[0]
            }
            matched = matchAt(loc.latitude, loc.longitude, moved)     // eligibility edge + centroid-closest-approach (D25.1)
            lastLat = loc.latitude; lastLon = loc.longitude
            pushRecent(loc.latitude, loc.longitude)                   // C2: для replay при завантаженні зони
            if (++fixesSinceCp >= 15) { fixesSinceCp = 0; checkpointSession() }   // D23 #11: чекпойнт дистанції ~раз на 30с
        }
        diag?.log(loc, matched, revealed.size, note)               // diagnostic-збір (off у release)
    }

    /**
     * Матчинг у точці (D25.1). Eligibility — стіна (контур) ≤ R_FAR. Тайминг — по ЦЕНТРОЇДУ:
     *  • стіна ≤ MIN_EDGE_NEAR або всередині footprint → розкрити ОДРАЗУ (ти впритул), АБО
     *  • відстань до ЦЕНТРОЇДА виросла на SLACK_CEN над мінімумом → проминув СЕРЕДИНУ будинку
     *    (саме «по середині, коли йдеш уздовж»), лише на реальному русі (`moved` — guard від GPS-джитера на місці).
     * Так розкриття лягає ~навпроти центру (не на передньому куті), а через дорогу/видовжені — ловляться.
     * Повертає к-сть НОВИХ розкриттів.
     */
    private fun matchAt(lat: Double, lon: Double, moved: Boolean): Int {
        val s = store ?: return 0
        s.candidatesPoint(lat, lon, R_TRACK, candIdx, candEdge, candCen)   // D23 #4: ширше за R_FAR — щоб тайминг встиг підтвердитись
        val now = System.currentTimeMillis()
        val fresh = ArrayList<VisitRecord>()
        for (k in candIdx.indices) {
            val idx = candIdx[k]; val ed = candEdge[k]; val cd = candCen[k]
            if (!s.isAccessible(idx)) continue                       // D6: не розкриваємо будинки поза пішою мережею
            val prior = runMin[idx]                                  // мін. центроїд-дист до цього фікса
            runMin[idx] = if (prior == null) cd else minOf(prior, cd)
            if (ed <= R_FAR) eligible.add(idx)                       // D23 #4: стіна колись ≤ R_FAR → «у грі»
            if (idx in revealed) continue
            val nearWall = ed <= MIN_EDGE_NEAR                       // впритул / всередині (ed=0)
            // passedMiddle лише для eligible: інакше будинок, повз який пройшов на 20-30 м (ніколи ≤R_FAR), розкрився б
            val passedMiddle = moved && prior != null && cd > prior + SLACK_CEN && idx in eligible
            if (nearWall || passedMiddle) {
                if (revealed.add(idx)) {
                    val f = s.featureAt(idx)
                    revealedFeatures.add(f)
                    val type = f.getStringProperty("type") ?: "other"
                    byType[type] = (byType[type] ?: 0) + 1
                    fresh.add(VisitRecord(s.idAt(idx), type, now))
                    runMin.remove(idx); eligible.remove(idx)         // розкрито — стан більше не потрібен
                }
            }
        }
        if (fresh.isNotEmpty()) {
            sessionNew += fresh.size
            val rows = fresh.map { VisitEntity(it.id, it.type, it.ts, SOURCE) }
            val dbg = ArrayList(fresh)
            dbIo.execute { visitDao?.insertAll(rows); debugVisitStore?.append(dbg) }   // MVP-0-полір: Room+файл off-main
            checkpointSession()                                                        // D23 #11 (теж off-main, той самий FIFO)
            listener?.onReveal(FeatureCollection.fromFeatures(ArrayList(revealedFeatures)), revealed.size)
        }
        return fresh.size
    }

    /** (P) Префетч зони НАПЕРЕД руху — щоб тайл був завантажений ДО того, як дійдеш (менше «розкриття
     *  після проходу» на межах тайлів). Напрямок: GPS-курс, інакше сегмент попередній→поточний фікс. */
    private fun prefetchAhead(loc: Location) {
        val al = areaLoader ?: return
        val bearingRad: Double = when {
            loc.hasBearing() && loc.hasSpeed() && loc.speed > 0.4f -> Math.toRadians(loc.bearing.toDouble())
            !lastLat.isNaN() -> {
                val dy = loc.latitude - lastLat
                val dx = (loc.longitude - lastLon) * Math.cos(Math.toRadians(loc.latitude))
                if (dx == 0.0 && dy == 0.0) return
                Math.atan2(dx, dy)                                 // клоквайз від півночі (як GPS-bearing)
            }
            else -> return
        }
        val dLat = PREFETCH_AHEAD_M * Math.cos(bearingRad) / 111320.0
        val dLon = PREFETCH_AHEAD_M * Math.sin(bearingRad) / (111320.0 * Math.cos(Math.toRadians(loc.latitude)))
        al.ensureArea(loc.latitude + dLat, loc.longitude + dLon)
    }

    fun reset() {
        revealed.clear(); revealedFeatures.clear(); byType.clear(); runMin.clear(); eligible.clear()
        lastLat = Double.NaN; lastLon = Double.NaN
        sessionNew = 0; sessionDistanceM = 0.0; sessionStartTs = 0L
        dbIo.execute { visitDao?.clear(); debugVisitStore?.clear(); sessionRowId = 0 }   // MVP-0-полір: off-main
    }
}
