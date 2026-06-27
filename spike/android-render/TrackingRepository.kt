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

    @Volatile var isTracking = false
    val hasStore: Boolean get() = store != null

    val revealed = LinkedHashSet<Int>()
    var listener: Listener? = null
    var areaLoader: AreaLoader? = null             // on-demand завантаження зон (D24)

    private var store: BuildingStore? = null
    private var visitStore: VisitStore? = null
    private var sessionStore: SessionStore? = null
    private var diag: DiagnosticRecorder? = null   // diagnostic-збір (лише debug; off у release)
    private val persistedIds = HashSet<String>()   // збережені розкриття (відновлюємо при завантаженні зон)
    private val revealedFeatures = ArrayList<Feature>()
    private val byType = HashMap<String, Int>()
    private var lastLat = Double.NaN
    private var lastLon = Double.NaN
    private val buf = ArrayList<Int>(64)
    private val dist = FloatArray(1)
    // C2: нещодавній шлях — replay при завантаженні зони (поки тягнулась, ти вже пройшов повз будинки)
    private val recentLat = ArrayList<Double>()
    private val recentLon = ArrayList<Double>()
    private val recentMax = 12

    // поточна сесія (Discovery)
    private var sessionNew = 0
    private var sessionDistanceM = 0.0
    private var sessionStartTs = 0L

    fun init(store: BuildingStore, visitStore: VisitStore, sessionStore: SessionStore, diag: DiagnosticRecorder?) {
        this.store = store
        this.visitStore = visitStore
        this.sessionStore = sessionStore
        this.diag = diag
        revealed.clear(); revealedFeatures.clear(); byType.clear(); persistedIds.clear()
        lastLat = Double.NaN; lastLon = Double.NaN
        for (r in visitStore.load()) persistedIds.add(r.id)
        reconcilePersisted()   // seed-store (perf) — одразу; on-demand — порожньо, доберемо при завантаженні зон
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
        val s = store
        if (s != null) {
            for (i in 1 until recentLat.size) {    // C2: replay нещодавнього шляху (пройдене, поки зона тягнулась)
                s.matchSegment(recentLat[i - 1], recentLon[i - 1], recentLat[i], recentLon[i], buf); absorb(s)
            }
            if (!lastLat.isNaN()) { s.match(lastLat, lastLon, buf); absorb(s) }
        }
        listener?.onReveal(FeatureCollection.fromFeatures(ArrayList(revealedFeatures)), revealed.size)
    }

    /** Початок сесії — скинути якір + лічильники маршруту. */
    fun startSession() {
        lastLat = Double.NaN; lastLon = Double.NaN; buf.clear()
        recentLat.clear(); recentLon.clear()
        sessionNew = 0; sessionDistanceM = 0.0; sessionStartTs = System.currentTimeMillis()
        ActivityGate.reset()
    }

    private fun pushRecent(lat: Double, lon: Double) {
        recentLat.add(lat); recentLon.add(lon)
        if (recentLat.size > recentMax) { recentLat.removeAt(0); recentLon.removeAt(0) }
    }

    /** Кінець сесії — записати підсумок (фундамент тижневого підсумку/рейтингів). */
    fun endSession() {
        if (sessionStartTs > 0L && (sessionNew > 0 || sessionDistanceM >= 1.0)) {
            sessionStore?.append(sessionStartTs, System.currentTimeMillis(), sessionDistanceM, sessionNew)
        }
        lastLat = Double.NaN; lastLon = Double.NaN; sessionStartTs = 0L
    }

    fun revealedCollection(): FeatureCollection = FeatureCollection.fromFeatures(ArrayList(revealedFeatures))

    fun stats(): Stats = Stats(revealed.size, store?.size ?: 0, HashMap(byType), sessionNew, sessionDistanceM)

    fun onLocation(loc: Location) {
        val s = store ?: return
        val gateOk = ActivityGate.allow(loc.speed, loc.hasSpeed())  // Stage B: vehicle/bike + швидкість (D5)
        if (!gateOk) { lastLat = Double.NaN; lastLon = Double.NaN }  // не мостимо сегмент через авто/велосипед
        if (gateOk) areaLoader?.ensureArea(loc.latitude, loc.longitude)   // D24: довантажити зону на льоту
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
            if (lastLat.isNaN()) {
                s.match(loc.latitude, loc.longitude, buf)
                lastLat = loc.latitude; lastLon = loc.longitude
                matched = absorb(s)
            } else {
                Location.distanceBetween(lastLat, lastLon, loc.latitude, loc.longitude, dist)
                if (dist[0] >= MIN_MOVE) {                          // рухаємось — буферуємо сегмент
                    sessionDistanceM += dist[0]
                    s.matchSegment(lastLat, lastLon, loc.latitude, loc.longitude, buf)
                    lastLat = loc.latitude; lastLon = loc.longitude
                    matched = absorb(s)
                }
                // інакше стоїмо — лишаємо якір, не матчимо
            }
            pushRecent(loc.latitude, loc.longitude)   // C2: для replay шляху при завантаженні зони
        }
        diag?.log(loc, matched, revealed.size, note)               // diagnostic-збір (off у release)
    }

    /** Поглинути матчі з buf: нові → revealed/overlay/byType/збереження/onReveal. Повертає к-сть нових. */
    private fun absorb(s: BuildingStore): Int {
        val now = System.currentTimeMillis()
        val fresh = ArrayList<VisitRecord>()
        for (idx in buf) if (revealed.add(idx)) {
            val f = s.featureAt(idx)
            revealedFeatures.add(f)
            val type = f.getStringProperty("type") ?: "other"
            byType[type] = (byType[type] ?: 0) + 1
            fresh.add(VisitRecord(s.idAt(idx), type, now))
        }
        if (fresh.isNotEmpty()) {
            sessionNew += fresh.size
            visitStore?.append(fresh)
            listener?.onReveal(FeatureCollection.fromFeatures(ArrayList(revealedFeatures)), revealed.size)
        }
        return fresh.size
    }

    fun reset() {
        revealed.clear(); revealedFeatures.clear(); byType.clear()
        lastLat = Double.NaN; lastLon = Double.NaN
        sessionNew = 0; sessionDistanceM = 0.0; sessionStartTs = 0L
        visitStore?.clear()
    }
}
