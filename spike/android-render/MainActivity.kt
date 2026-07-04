package no.streif.spike

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
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
class MainActivity : AppCompatActivity(), TrackingRepository.Listener, SensorEventListener {

    private lateinit var mapView: MapView
    private lateinit var perf: PerfProbe

    private var mode = "walk"
    private var sync = false
    private var tickMs = 40L
    private var flushMs = 150L
    private var radiusM = 18.0
    private var texture = false
    private var stats = false
    private var zoom = 14.0

    private var map: MapLibreMap? = null
    private var visitedSource: GeoJsonSource? = null
    private var meSource: GeoJsonSource? = null
    private var store: BuildingStore? = null
    private var harness: PerfHarness? = null

    // debug ground-truth мітки (тап будинку → ✓/✗)
    private var allSource: GeoJsonSource? = null
    private var marksSource: GeoJsonSource? = null
    private var markLog: MarkLog? = null
    private val marks = HashMap<String, String>()
    private val markFeatures = HashMap<String, Feature>()
    private var lastAllSize = 0

    private var tracking = false
    private var firstFix = true
    private lateinit var startBtn: Button
    private lateinit var statusView: TextView

    // P17: обертання мапи за напрямком (компас). Дефолт — north-up; перемикач як у Google Maps.
    private var courseUp = false
    private var azimuthDeg = Float.NaN          // згладжений компас-курс (0..360)
    private var lastLatLng: LatLng? = null
    private var lastRotMs = 0L
    private var sensorMgr: SensorManager? = null
    private var rotSensor: Sensor? = null
    private var compassBtn: Button? = null

    // Google-Maps-стиль: вільний пан + кнопка «до мене». followMe=false щойно юзер перетягнув мапу.
    private var followMe = true
    private var recenterBtn: Button? = null

    private val permLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { res ->
        if (hasFine()) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && res[Manifest.permission.POST_NOTIFICATIONS] != true)
                toast(getString(R.string.toast_notifications_off))
            startWalk()
        } else toast(getString(R.string.toast_need_fine_location))
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
        if (mode == "walk") {
            sensorMgr = getSystemService(SENSOR_SERVICE) as SensorManager
            rotSensor = sensorMgr?.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
            maybeShowOnboarding()
        }
    }

    private fun readExtras() {
        intent.getStringExtra("mode")?.let { mode = it }
        sync = intent.getBooleanExtra("sync", false)
        tickMs = intent.getIntExtra("tickMs", 40).toLong()
        flushMs = intent.getIntExtra("flushMs", 150).toLong()
        radiusM = intent.getIntExtra("radius", if (mode == "walk") 18 else 30).toDouble()
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
            text = getString(R.string.status_loading)
        }
        frame.addView(statusView, FrameLayout.LayoutParams(mp, wc).apply { gravity = Gravity.TOP })

        startBtn = Button(this).apply {
            text = getString(R.string.action_start)
            isEnabled = false
            setOnClickListener { onStartStopTap() }
        }
        frame.addView(startBtn, FrameLayout.LayoutParams(wc, wc).apply {
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            bottomMargin = 64
        })

        compassBtn = Button(this).apply {
            text = "🧭"                                    // лише іконка (без тексту)
            textSize = 20f
            setBackgroundColor(0x66222222.toInt())         // north-up = приглушений; course-up підсвітиться (toggleCourseUp)
            setOnClickListener { toggleCourseUp() }
        }
        frame.addView(compassBtn, FrameLayout.LayoutParams(wc, wc).apply {
            gravity = Gravity.CENTER_VERTICAL or Gravity.END   // справа ПО ЦЕНТРУ — не налазить на статус угорі
            rightMargin = 16
        })

        recenterBtn = Button(this).apply {
            text = "◎"                                     // «повернутись до моєї позиції» (як my-location у Google Maps)
            textSize = 20f
            setBackgroundColor(0x66222222.toInt())
            setOnClickListener { recenter() }
        }
        frame.addView(recenterBtn, FrameLayout.LayoutParams(wc, wc).apply {
            gravity = Gravity.BOTTOM or Gravity.END
            rightMargin = 16; bottomMargin = 64
        })
        return frame
    }

    private fun setupMap(m: MapLibreMap) {
        map = m
        m.addOnCameraMoveStartedListener { reason ->
            // юзер перетягнув/зумнув пальцем → перестати центрувати (щоб можна було оглядати мапу)
            if (reason == MapLibreMap.OnCameraMoveStartedListener.REASON_API_GESTURE) followMe = false
        }
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
            if (mode == "walk" && BuildConfig.DEBUG) addBuildingsAllLayer(style)   // тонкий сірий, нижче visited (для тапу)
            addVisitedLayer(style)
            if (mode == "walk") addMeLayer(style)
            if (mode == "walk" && BuildConfig.DEBUG) addMarksLayer(style)           // мітки зверху
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

    private fun addBuildingsAllLayer(style: Style) {
        val src = GeoJsonSource(ALL_SRC, FeatureCollection.fromFeatures(emptyList<Feature>()))
        style.addSource(src)
        allSource = src
        style.addLayer(FillLayer(ALL_LYR, ALL_SRC).withProperties(
            PropertyFactory.fillColor(Color.parseColor("#9CA3AA")),
            PropertyFactory.fillOpacity(0.30f)))
    }

    private fun addMarksLayer(style: Style) {
        val src = GeoJsonSource(MARK_SRC, FeatureCollection.fromFeatures(emptyList<Feature>()))
        style.addSource(src)
        marksSource = src
        val color = Expression.match(
            Expression.get("mark"),
            Expression.literal("correct"), Expression.color(Color.parseColor("#2E7D32")),
            Expression.literal("wrong"), Expression.color(Color.parseColor("#C62828")),
            Expression.color(Color.parseColor("#999999"))
        )
        style.addLayer(CircleLayer(MARK_LYR, MARK_SRC).withProperties(
            PropertyFactory.circleColor(color),
            PropertyFactory.circleRadius(8f),
            PropertyFactory.circleStrokeColor(Color.WHITE),
            PropertyFactory.circleStrokeWidth(2f)))
    }

    private fun refreshAllBuildings() {
        val s = store ?: return
        if (allSource != null && s.size != lastAllSize) {
            allSource?.setGeoJson(s.allCollection())
            lastAllSize = s.size
        }
    }

    private fun setupMarkTap() {
        if (!BuildConfig.DEBUG) return
        markLog = MarkLog(java.io.File(filesDir, "marks.csv"))
        map?.addOnMapClickListener { ll -> onMapClickMark(ll); true }
    }

    /** Тап будинку (debug ground-truth): цикл мітки ✓ → ✗ → зняти + лог у marks.csv.
     *  Ідентифікація — через НАШ store (`nearest`), не render-query: надійно, незалежно від режиму рендеру. */
    private fun onMapClickMark(ll: LatLng) {
        val s = store ?: return
        val idx = s.nearest(ll.latitude, ll.longitude, 35.0)
        if (idx == null) { toast(getString(R.string.toast_no_building)); return }
        val id = s.idAt(idx)
        val next = when (marks[id]) { null -> "correct"; "correct" -> "wrong"; else -> null }
        val c = s.centroidLatLon(idx)   // [lat, lon]
        val wasRevealed = TrackingRepository.revealed.contains(idx)
        if (next == null) { marks.remove(id); markFeatures.remove(id) } else {
            marks[id] = next
            markFeatures[id] = Feature.fromGeometry(Point.fromLngLat(c[1], c[0])).apply { addStringProperty("mark", next) }
        }
        marksSource?.setGeoJson(FeatureCollection.fromFeatures(ArrayList(markFeatures.values)))
        markLog?.log(id, next ?: "clear", c[0], c[1], wasRevealed)
        toast(when (next) { "correct" -> getString(R.string.toast_mark_correct); "wrong" -> getString(R.string.toast_mark_wrong); else -> getString(R.string.toast_mark_cleared) })
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
            val db = MvpDatabase.get(this)                       // MVP-0: Room-персистенція (D11)
            MvpImporter.importVisitsOnce(db, filesDir)           // одноразова міграція visited.txt → Room
            // DEBUG-дубль у visited.txt — щоб analyze.py (польовий аналіз) далі працював під час тюнінгу
            val debugVs = if (BuildConfig.DEBUG) VisitStore(java.io.File(filesDir, "visited.txt")) else null
            // ⚠️ diagnostic-збір ЛИШЕ в debug — release автоматично не збирає (D14)
            val diag = if (BuildConfig.DEBUG) DiagnosticRecorder(
                java.io.File(filesDir, "diag.csv"),
                getSystemService(android.os.BatteryManager::class.java)
            ) else null
            initWalk(s, db, debugVs, diag)
            val cache = AreaCache(java.io.File(filesDir, "areas").apply { mkdirs() })
            // D24/S8 (Варіант 1): CDN pre-hosted CC-BY тайли vs runtime-Overpass (dogfood) — перемикач BuildConfig
            val areaSource: AreaSource =
                if (BuildConfig.USE_CDN) CdnGeoJsonAreaSource(BuildConfig.CDN_BASE_URL) else OverpassAreaSource()
            TrackingRepository.areaLoader = AreaLoader(s, cache, areaSource) { TrackingRepository.onAreaLoaded() }
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
        store = TrackingRepository.currentStore          // D23 #14: без цього DEBUG all-шар + ✓/✗-мітки мертві після пересоздання
        visitedSource?.setGeoJson(TrackingRepository.revealedCollection())
        TrackingRepository.listener = this
        tracking = TrackingRepository.isTracking          // C4: не припускати tracking=true (пересоздання поза сесією)
        firstFix = !tracking
        startBtn.isEnabled = true
        startBtn.text = if (tracking) getString(R.string.action_stop) else getString(R.string.action_start)
        setupMarkTap(); refreshAllBuildings()
        renderStats()
    }

    private fun initWalk(s: BuildingStore, db: MvpDatabase, debugVs: VisitStore?, diag: DiagnosticRecorder?) {
        TrackingRepository.init(s, db.visits(), db.sessions(), debugVs, diag)
        visitedSource?.setGeoJson(TrackingRepository.revealedCollection())
        TrackingRepository.listener = this
        tracking = TrackingRepository.isTracking            // синхронізуємось зі станом сервісу (recreation)
        firstFix = !tracking
        startBtn.isEnabled = true
        startBtn.text = if (tracking) getString(R.string.action_stop) else getString(R.string.action_start)
        setupMarkTap(); refreshAllBuildings()
        renderStats()
    }

    /** Статус: Coverage (% Volda) + Variety (за типами) + Discovery (нове за маршрут) — D13. */
    private fun renderStats(live: String = "") {
        val s = TrackingRepository.stats()
        val types = s.byType.entries.sortedByDescending { it.value }
            .joinToString(" · ") { "${typeLabel(it.key)} ${it.value}" }
        statusView.text = buildString {
            append(getString(R.string.status_revealed, s.total, s.coveragePct))
            if (tracking) append(getString(R.string.status_route, s.sessionNew, s.sessionDistanceM.toInt()))
            else append(getString(R.string.status_hint_start))
            if (types.isNotEmpty()) { append("\n"); append(types) }
            val area = TrackingRepository.areaLoader?.status ?: ""
            if (area.isNotEmpty()) { append("\n"); append(area) }
            if (live.isNotEmpty()) { append("\n"); append(live) }
        }
    }

    private fun typeLabel(t: String): String = when (t) {
        "housing" -> getString(R.string.type_housing); "hytte" -> getString(R.string.type_hytte); "public" -> getString(R.string.type_public)
        "sacral" -> getString(R.string.type_sacral); "outbuilding" -> getString(R.string.type_outbuilding); else -> getString(R.string.type_other)
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
            toast(getString(R.string.toast_start_failed)); return
        }
        tracking = true; firstFix = true
        startBtn.text = getString(R.string.action_stop)
    }

    private fun stopWalk() {
        startService(Intent(this, WalkTrackingService::class.java).setAction(WalkTrackingService.ACTION_STOP))
        tracking = false
        startBtn.text = getString(R.string.action_start)
    }

    // ---- TrackingRepository.Listener (callbacks вже на main-looper Fused) ----
    override fun onReveal(fc: FeatureCollection, total: Int) {
        runOnUiThread {
            visitedSource?.setGeoJson(fc)
            refreshAllBuildings()
            renderStats()
        }
    }

    override fun onLocation(loc: Location, acceptedForMatch: Boolean, note: String) {
        runOnUiThread {
            meSource?.setGeoJson(Point.fromLngLat(loc.longitude, loc.latitude))
            val m = map
            if (m != null) {
                val ll = LatLng(loc.latitude, loc.longitude)
                lastLatLng = ll
                if (firstFix) { m.moveCamera(CameraUpdateFactory.newLatLngZoom(ll, 16.5)); firstFix = false }
                else updateCamera(animate = true)                    // P17: центр + bearing (course-up/north-up)
            }
            val acc = if (loc.hasAccuracy()) "%.0f".format(loc.accuracy) else "—"
            val spd = if (loc.hasSpeed()) "%.1f".format(loc.speed) else "—"
            val live = getString(R.string.status_live, acc, spd) + if (note.isNotEmpty()) " · $note" else ""
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
                if (loc != null && !tracking) {
                    lastLatLng = LatLng(loc.latitude, loc.longitude)     // P17: щоб course-up працював і до старту
                    m.easeCamera(CameraUpdateFactory.newLatLngZoom(LatLng(loc.latitude, loc.longitude), 14.5), 700)
                }
            }
    }

    private fun hasFine() = ContextCompat.checkSelfPermission(
        this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED

    // ---- P17: обертання мапи (north-up ↔ course-up за компасом; перемикач як у Google Maps) ----
    private fun toggleCourseUp() {
        courseUp = !courseUp
        compassBtn?.setBackgroundColor(if (courseUp) 0xCC1A73E8.toInt() else 0x66222222.toInt())  // синій = course-up активний
        updateCamera(animate = true)                         // при вимкненні — плавно повернути на північ
    }

    /** Оновити камеру: центр = остання позиція, bearing = компас-курс (course-up) або 0 (north-up). */
    private fun updateCamera(animate: Boolean) {
        if (!followMe) return                                // юзер оглядає мапу — не смикати назад
        val m = map ?: return; val ll = lastLatLng ?: return
        val bearing = if (courseUp && !azimuthDeg.isNaN()) azimuthDeg.toDouble() else 0.0
        val pos = CameraPosition.Builder().target(ll).bearing(bearing).zoom(m.cameraPosition.zoom).build()
        val upd = CameraUpdateFactory.newCameraPosition(pos)
        if (animate) m.easeCamera(upd, 400) else m.moveCamera(upd)
    }

    /** Повернутись до поточної позиції й відновити слідування (кнопка «до мене»). */
    private fun recenter() {
        followMe = true
        val m = map ?: return
        val ll = lastLatLng ?: run { centerOnLastLocation(m); return }
        val bearing = if (courseUp && !azimuthDeg.isNaN()) azimuthDeg.toDouble() else 0.0
        val pos = CameraPosition.Builder().target(ll).bearing(bearing).zoom(16.5).build()
        m.easeCamera(CameraUpdateFactory.newCameraPosition(pos), 400)
    }

    override fun onSensorChanged(e: SensorEvent) {
        if (e.sensor.type != Sensor.TYPE_ROTATION_VECTOR) return
        val r = FloatArray(9); SensorManager.getRotationMatrixFromVector(r, e.values)
        val o = FloatArray(3); SensorManager.getOrientation(r, o)   // азимут при телефоні ~горизонтально (тримай пласко)
        var az = Math.toDegrees(o[0].toDouble()).toFloat(); if (az < 0f) az += 360f   // компас-курс 0..360
        // кутовий low-pass (враховує перехід через 360°) — інакше карта смикається від шуму магнітометра
        azimuthDeg = if (azimuthDeg.isNaN()) az else smoothAngle(azimuthDeg, az, 0.15f)
        if (courseUp) {
            val now = System.currentTimeMillis()
            if (now - lastRotMs > 80L) { lastRotMs = now; updateCamera(animate = false) }   // throttle ~12 Hz
        }
    }
    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    /** Кутове згладжування з переходом через 360°. */
    private fun smoothAngle(prev: Float, target: Float, a: Float): Float {
        val d = ((target - prev + 540f) % 360f) - 180f      // найкоротша різниця (-180..180)
        var res = prev + a * d
        if (res < 0f) res += 360f; if (res >= 360f) res -= 360f
        return res
    }

    /** Перший запуск — коротке «ага»: карта твоя, ходьба її розкриває (спокій, без логіну — D26/D28/D20). */
    private fun maybeShowOnboarding() {
        val prefs = getSharedPreferences("streif", MODE_PRIVATE)
        if (prefs.getBoolean("onboarded", false)) return
        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle(getString(R.string.onboarding_title))
            .setMessage(getString(R.string.onboarding_message))
            .setPositiveButton(getString(R.string.action_got_it)) { d, _ -> d.dismiss() }
            .setCancelable(false)
            .show()
        prefs.edit().putBoolean("onboarded", true).apply()
    }

    private fun toast(s: String) = Toast.makeText(this, s, Toast.LENGTH_LONG).show()

    override fun onStart() { super.onStart(); mapView.onStart() }
    override fun onResume() {
        super.onResume(); mapView.onResume()
        rotSensor?.let { sensorMgr?.registerListener(this, it, SensorManager.SENSOR_DELAY_UI) }   // P17
    }
    override fun onPause() {
        sensorMgr?.unregisterListener(this)                                                       // P17
        mapView.onPause(); super.onPause()
    }
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
        private const val ALL_SRC = "all-src"
        private const val ALL_LYR = "all"
        private const val MARK_SRC = "mark-src"
        private const val MARK_LYR = "marks"
    }
}
