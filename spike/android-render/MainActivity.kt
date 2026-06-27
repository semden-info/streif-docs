package no.streif.spike

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.location.Location
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapLibreMapOptions
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.FillLayer
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.sources.GeoJsonOptions
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection
import org.maplibre.geojson.Point
import java.util.Locale

/**
 * Spike-2 Stage A — реальний трекінг прогулянки (FGS + Fused GPS + сегмент-матчинг +
 * збереження) поверх двошарового рендеру spike-1.
 *
 * Режим за замовчуванням — **walk** (launcher): тап «Старт» → FGS трекає GPS → будинки на
 * шляху розкриваються. Перф-режими spike-1 — через `--es mode bench|combo|replay` (→ PerfHarness).
 */
class MainActivity : AppCompatActivity(), TrackingRepository.Listener {

    private lateinit var mapView: MapView
    private lateinit var perf: PerfProbe

    private var mode = "walk"
    private var sync = false
    private var tickMs = 40L
    private var flushMs = 150L
    private var radiusM = 20.0
    private var texture = false
    private var stats = false
    private var zoom = 14.0

    private var map: MapLibreMap? = null
    private var visitedSource: GeoJsonSource? = null
    private var meSource: GeoJsonSource? = null
    private var store: BuildingStore? = null
    private var harness: PerfHarness? = null

    private var tracking = false
    private var firstFix = true
    private lateinit var startBtn: Button
    private lateinit var statusView: TextView

    private val permLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { res ->
        if (hasFine()) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && res[Manifest.permission.POST_NOTIFICATIONS] != true)
                toast("Сповіщення вимкнено — індикатор трекінгу не показуватиметься")
            startWalk()
        } else toast("Потрібен дозвіл на точну геолокацію")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        readExtras()
        MapLibre.getInstance(this)
        mapView = if (texture)
            MapView(this, MapLibreMapOptions.createFromAttributes(this).textureMode(true))
        else MapView(this)

        if (mode == "walk") setContentView(buildWalkUi()) else setContentView(mapView)

        mapView.onCreate(savedInstanceState)
        perf = PerfProbe(mapView)
        perf.attach()
        mapView.getMapAsync { m -> setupMap(m) }
    }

    private fun readExtras() {
        intent.getStringExtra("mode")?.let { mode = it }
        sync = intent.getBooleanExtra("sync", false)
        tickMs = intent.getIntExtra("tickMs", 40).toLong()
        flushMs = intent.getIntExtra("flushMs", 150).toLong()
        radiusM = intent.getIntExtra("radius", if (mode == "walk") 20 else 30).toDouble()
        texture = intent.getBooleanExtra("texture", false)
        stats = intent.getBooleanExtra("stats", false)
        intent.getStringExtra("zoom")?.toDoubleOrNull()?.let { zoom = it }
    }

    private fun buildWalkUi(): FrameLayout {
        val mp = FrameLayout.LayoutParams.MATCH_PARENT
        val wc = FrameLayout.LayoutParams.WRAP_CONTENT
        val frame = FrameLayout(this)
        frame.addView(mapView, FrameLayout.LayoutParams(mp, mp))

        statusView = TextView(this).apply {
            setBackgroundColor(0xCC000000.toInt())
            setTextColor(Color.WHITE)
            setPadding(24, 110, 24, 24)   // top — нижче системного статус-бара
            text = "Завантаження будинків…"
        }
        frame.addView(statusView, FrameLayout.LayoutParams(mp, wc).apply { gravity = Gravity.TOP })

        startBtn = Button(this).apply {
            text = "Старт прогулянки"
            isEnabled = false
            setOnClickListener { onStartStopTap() }
        }
        frame.addView(startBtn, FrameLayout.LayoutParams(wc, wc).apply {
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            bottomMargin = 64
        })
        return frame
    }

    private fun setupMap(m: MapLibreMap) {
        map = m
        m.cameraPosition = CameraPosition.Builder()
            .target(LatLng(BuildingStore.REF_LAT, 6.071)).zoom(zoom).build()
        if (mode == "walk") centerOnLastLocation(m)        // Баг 2: одразу на твоє місце, не Volda
        val pmFile = java.io.File(filesDir, "buildings.pmtiles")
        if (!pmFile.exists())
            assets.open("buildings.pmtiles").use { i -> pmFile.outputStream().use { i.copyTo(it) } }
        val styleJson = assets.open("style.json").bufferedReader().use { it.readText() }
            .replace("pmtiles://asset://buildings.pmtiles", "pmtiles://file://" + pmFile.absolutePath)
        m.setStyle(Style.Builder().fromJson(styleJson)) { style ->
            if (stats) m.enableRenderingStatsView(true)
            addVisitedLayer(style)
            if (mode == "walk") addMeLayer(style)
            loadDataThenRun(m)
        }
    }

    private fun addVisitedLayer(style: Style) {
        val src = GeoJsonSource(SRC, FeatureCollection.fromFeatures(emptyList<Feature>()),
            GeoJsonOptions().withSynchronousUpdate(sync))
        style.addSource(src)
        visitedSource = src
        val color = Expression.match(
            Expression.get("type"),
            Expression.literal("housing"), Expression.color(Color.parseColor("#E0392B")),
            Expression.literal("hytte"), Expression.color(Color.parseColor("#F2A007")),
            Expression.literal("public"), Expression.color(Color.parseColor("#2479C2")),
            Expression.literal("sacral"), Expression.color(Color.parseColor("#9A3DC2")),
            Expression.literal("outbuilding"), Expression.color(Color.parseColor("#3FA340")),
            Expression.literal("other"), Expression.color(Color.parseColor("#CC5599")),
            Expression.color(Color.parseColor("#CC5599"))
        )
        style.addLayer(FillLayer(VISITED, SRC).withProperties(
            PropertyFactory.fillColor(color), PropertyFactory.fillOpacity(1.0f)))
    }

    private fun addMeLayer(style: Style) {
        val src = GeoJsonSource(ME_SRC)
        style.addSource(src)
        meSource = src
        style.addLayer(CircleLayer(ME_LYR, ME_SRC).withProperties(
            PropertyFactory.circleColor(Color.parseColor("#1A73E8")),
            PropertyFactory.circleRadius(7f),
            PropertyFactory.circleStrokeColor(Color.WHITE),
            PropertyFactory.circleStrokeWidth(2.5f)))
    }

    private fun loadDataThenRun(m: MapLibreMap) {
        if (mode == "walk" && TrackingRepository.hasStore) {
            reattachWalk()       // C4: store+AreaLoader уже є (пересоздання Activity) — переюзати, не плодити loader/executor
            return
        }
        if (mode == "walk") {
            // D24 on-demand: порожній store + AreaLoader (зони тягнемо на льоту, без важкого seed)
            val s = BuildingStore(radiusM)
            store = s
            val vs = VisitStore(java.io.File(filesDir, "visited.txt"))
            val ss = SessionStore(java.io.File(filesDir, "sessions.csv"))
            // ⚠️ diagnostic-збір ЛИШЕ в debug — release автоматично не збирає (D14)
            val diag = if (BuildConfig.DEBUG) DiagnosticRecorder(java.io.File(filesDir, "diag.csv")) else null
            initWalk(s, vs, ss, diag)
            val cache = AreaCache(java.io.File(filesDir, "areas").apply { mkdirs() })
            TrackingRepository.areaLoader = AreaLoader(s, cache, OverpassAreaSource()) { TrackingRepository.onAreaLoaded() }
            preloadArea()
            android.util.Log.i(TAG, "walk on-demand ready (store порожній, зони on-demand)")
        } else {
            Thread {
                val s = BuildingStore.loadSeed(this, radiusM)
                store = s
                android.util.Log.i(TAG, "loaded seed buildings=${s.size}")
                runOnUiThread { harness = PerfHarness(this, m, s, visitedSource!!, perf, sync, tickMs, flushMs).also { it.run(mode) } }
            }.start()
        }
    }

    @SuppressLint("MissingPermission")
    private fun preloadArea() {   // довантажити зону навколо поточного місця ще до старту прогулянки
        if (!hasFine()) return
        LocationServices.getFusedLocationProviderClient(this)
            .getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, CancellationTokenSource().token)
            .addOnSuccessListener { loc -> if (loc != null) TrackingRepository.areaLoader?.ensureArea(loc.latitude, loc.longitude) }
    }

    /** Activity пересоздано під час активної прогулянки: перепідключитись без re-init (зберегти live-стан, C1). */
    private fun reattachWalk() {
        visitedSource?.setGeoJson(TrackingRepository.revealedCollection())
        TrackingRepository.listener = this
        tracking = TrackingRepository.isTracking          // C4: не припускати tracking=true (пересоздання поза сесією)
        firstFix = !tracking
        startBtn.isEnabled = true
        startBtn.text = if (tracking) "Стоп прогулянку" else "Старт прогулянки"
        renderStats()
    }

    private fun initWalk(s: BuildingStore, vs: VisitStore, ss: SessionStore, diag: DiagnosticRecorder?) {
        TrackingRepository.init(s, vs, ss, diag)
        visitedSource?.setGeoJson(TrackingRepository.revealedCollection())
        TrackingRepository.listener = this
        tracking = TrackingRepository.isTracking            // синхронізуємось зі станом сервісу (recreation)
        firstFix = !tracking
        startBtn.isEnabled = true
        startBtn.text = if (tracking) "Стоп прогулянку" else "Старт прогулянки"
        renderStats()
    }

    /** Статус: Coverage (% Volda) + Variety (за типами) + Discovery (нове за маршрут) — D13. */
    private fun renderStats(live: String = "") {
        val s = TrackingRepository.stats()
        val types = s.byType.entries.sortedByDescending { it.value }
            .joinToString(" · ") { "${typeLabel(it.key)} ${it.value}" }
        statusView.text = buildString {
            append("Розкрито ${s.total} (")
            append("%.1f".format(s.coveragePct))
            append("%)")
            if (tracking) append(" · маршрут +${s.sessionNew}, ${s.sessionDistanceM.toInt()}м")
            else append(" · натисни «Старт»")
            if (types.isNotEmpty()) { append("\n"); append(types) }
            val area = TrackingRepository.areaLoader?.status ?: ""
            if (area.isNotEmpty()) { append("\n"); append(area) }
            if (live.isNotEmpty()) { append("\n"); append(live) }
        }
    }

    private fun typeLabel(t: String): String = when (t) {
        "housing" -> "житло"; "hytte" -> "hytte"; "public" -> "громад."
        "sacral" -> "сакр."; "outbuilding" -> "господ."; else -> "інше"
    }

    // ---- UI / walk control ----
    private fun onStartStopTap() {
        if (tracking) stopWalk()
        else if (hasFine()) startWalk() else permLauncher.launch(neededPerms())
    }

    private fun startWalk() {
        try {
            ContextCompat.startForegroundService(this, Intent(this, WalkTrackingService::class.java))
        } catch (e: Exception) {
            toast("Не вдалося стартувати трекінг — спробуй ще раз"); return
        }
        tracking = true; firstFix = true
        startBtn.text = "Стоп прогулянку"
    }

    private fun stopWalk() {
        startService(Intent(this, WalkTrackingService::class.java).setAction(WalkTrackingService.ACTION_STOP))
        tracking = false
        startBtn.text = "Старт прогулянки"
    }

    // ---- TrackingRepository.Listener (callbacks вже на main-looper Fused) ----
    override fun onReveal(fc: FeatureCollection, total: Int) {
        runOnUiThread {
            visitedSource?.setGeoJson(fc)
            renderStats()
        }
    }

    override fun onLocation(loc: Location, acceptedForMatch: Boolean, note: String) {
        runOnUiThread {
            meSource?.setGeoJson(Point.fromLngLat(loc.longitude, loc.latitude))
            val m = map
            if (m != null) {
                val ll = LatLng(loc.latitude, loc.longitude)
                if (firstFix) { m.moveCamera(CameraUpdateFactory.newLatLngZoom(ll, 16.5)); firstFix = false }
                else m.easeCamera(CameraUpdateFactory.newLatLng(ll), 800)
            }
            val acc = if (loc.hasAccuracy()) "%.0f".format(loc.accuracy) else "—"
            val spd = if (loc.hasSpeed()) "%.1f".format(loc.speed) else "—"
            val live = "${acc}м · ${spd}м/с" + if (note.isNotEmpty()) " · $note" else ""
            renderStats(live)
        }
    }

    private fun neededPerms(): Array<String> {
        val p = mutableListOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) p.add(Manifest.permission.ACTIVITY_RECOGNITION)  // vehicle/bike-gate
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) p.add(Manifest.permission.POST_NOTIFICATIONS)
        return p.toTypedArray()
    }

    @SuppressLint("MissingPermission") // перевіряється hasFine()
    private fun centerOnLastLocation(m: MapLibreMap) {
        if (!hasFine()) return
        val client = LocationServices.getFusedLocationProviderClient(this)
        // 1) миттєво — остання відома (якщо є), щоб не «миготіло» Volda
        client.lastLocation.addOnSuccessListener { loc ->
            if (loc != null && !tracking && firstFix)
                m.moveCamera(CameraUpdateFactory.newLatLngZoom(LatLng(loc.latitude, loc.longitude), 14.0))
        }
        // 2) свіжий фікс — уточнити (lastLocation буває застарілий: показувало Volda в Oslo)
        client.getCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY, CancellationTokenSource().token)
            .addOnSuccessListener { loc ->
                if (loc != null && !tracking)
                    m.easeCamera(CameraUpdateFactory.newLatLngZoom(LatLng(loc.latitude, loc.longitude), 14.5), 700)
            }
    }

    private fun hasFine() = ContextCompat.checkSelfPermission(
        this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED

    private fun toast(s: String) = Toast.makeText(this, s, Toast.LENGTH_LONG).show()

    override fun onStart() { super.onStart(); mapView.onStart() }
    override fun onResume() { super.onResume(); mapView.onResume() }
    override fun onPause() { mapView.onPause(); super.onPause() }
    override fun onStop() { mapView.onStop(); super.onStop() }
    override fun onLowMemory() { super.onLowMemory(); mapView.onLowMemory() }
    override fun onDestroy() {
        harness?.stopWork()
        if (TrackingRepository.listener === this) TrackingRepository.listener = null
        perf.detach()
        mapView.onDestroy()
        super.onDestroy()
    }
    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState); mapView.onSaveInstanceState(outState)
    }

    companion object {
        const val TAG = "SPIKEPERF"
        private const val SRC = "visited-src"
        private const val VISITED = "visited"
        private const val ME_SRC = "me-src"
        private const val ME_LYR = "me"
    }
}
