package no.streif.spike

import android.app.Activity
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Choreographer
import org.json.JSONArray
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.style.sources.GeoJsonSource
import java.util.Locale

/**
 * Spike-1 перф-харнес (режими bench/combo/replay), винесений із MainActivity, щоб
 * лишити інструмент для mid-range-дозаміру (gate D22/`11` §7). Запуск:
 * `am start -n no.streif.spike/.MainActivity --es mode bench|combo|replay [--ez sync true] ...`
 */
class PerfHarness(
    private val activity: Activity,
    private val map: MapLibreMap,
    private val store: BuildingStore,
    private val source: GeoJsonSource,
    private val perf: PerfProbe,
    private val sync: Boolean,
    private val tickMs: Long,
    private val flushMs: Long,
) {
    private val main = Handler(Looper.getMainLooper())
    private val revealed = LinkedHashSet<Int>()
    private var worker: Thread? = null
    @Volatile private var stop = false
    private lateinit var routeLat: DoubleArray
    private lateinit var routeLon: DoubleArray

    fun run(mode: String) {
        loadRoute()
        when (mode) {
            "bench" -> runBench()
            "combo" -> runCombo()
            else -> runReplay()
        }
    }

    fun stopWork() { stop = true }

    private fun loadRoute() {
        val arr = JSONArray(activity.assets.open("route.json").bufferedReader().use { it.readText() })
        routeLat = DoubleArray(arr.length())
        routeLon = DoubleArray(arr.length())
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            routeLat[i] = o.getDouble("lat"); routeLon[i] = o.getDouble("lon")
        }
    }

    // ---- REPLAY: симульований GPS → радіус-матч → коалесований overlay-апдейт ----
    private fun runReplay() {
        val s = store
        val buf = ArrayList<Int>(64)
        val milestones = intArrayOf(100, 250, 500, 750, 1000, 1250)
        var nextMs = 0
        val flushNs = flushMs * 1_000_000L
        worker = Thread {
            val start = System.nanoTime()
            var lastFlush = start
            var lastMem = start
            for (i in routeLat.indices) {
                if (stop) break
                s.match(routeLat[i], routeLon[i], buf)
                var added = false
                for (idx in buf) if (revealed.add(idx)) added = true
                val now = System.nanoTime()
                if (added && now - lastFlush >= flushNs) {
                    val n = revealed.size
                    val fc = s.collectionFor(revealed)
                    val logLat = nextMs < milestones.size && n >= milestones[nextMs]
                    main.post { if (logLat) perf.markUpdate(n); source.setGeoJson(fc) }
                    if (logLat) nextMs++
                    lastFlush = now
                }
                if (now - lastMem > 5_000_000_000L) { logMem("replay n=${revealed.size}"); lastMem = now }
                try { Thread.sleep(tickMs) } catch (e: InterruptedException) { break }
            }
            val fc = s.collectionFor(revealed)
            main.post { source.setGeoJson(fc) }
            Log.i(TAG, String.format(Locale.US, "REPLAY DONE | reveals=%d/%d durSec=%.0f", revealed.size, s.size, (System.nanoTime() - start) / 1e9))
            logMem("replay end n=${revealed.size}")
        }.also { it.start() }
    }

    // ---- BENCH: рівно N visited → латентність + frame-time під паном ----
    private fun runBench() {
        val s = store
        val steps = intArrayOf(100, 500, 1000, 2000, 4000)
        val order = (0 until s.size).shuffled(kotlin.random.Random(42))
        val stirrer = CameraStirrer()
        worker = Thread {
            for (n in steps) {
                if (stop) break
                val target = n.coerceAtMost(order.size)
                revealed.clear()
                for (k in 0 until target) revealed.add(order[k])
                val fc = s.collectionFor(revealed)
                main.post { perf.markUpdate(target); source.setGeoJson(fc) }
                sleep(1200)
                main.post { perf.beginWindow(); stirrer.start() }
                sleep(3000)
                main.post { stirrer.stop(); perf.endWindow("bench N=$target sync=$sync") }
                sleep(600)
                logMem("bench N=$target")
            }
            Log.i(TAG, "BENCH DONE | sync=$sync")
        }.also { it.start() }
    }

    // ---- COMBO: пан ОДНОЧАСНО з повторними setGeoJson при кожному N ----
    private fun runCombo() {
        val s = store
        val order = (0 until s.size).shuffled(kotlin.random.Random(42))
        val milestones = intArrayOf(100, 500, 1000, 2000, 4000)
        val stirrer = CameraStirrer()
        worker = Thread {
            main.post { stirrer.start() }
            sleep(600)
            var n = 0
            for (target in milestones) {
                if (stop) break
                val t = target.coerceAtMost(s.size)
                while (n < t) { revealed.add(order[n]); n++ }
                val fc = s.collectionFor(revealed)
                main.post { perf.beginWindow() }
                var elapsed = 0L
                while (elapsed < 2500 && !stop) {
                    main.post { source.setGeoJson(fc) }
                    sleep(120); elapsed += 120
                }
                main.post { perf.endWindow("combo N=$t sync=$sync (pan+update)") }
                sleep(300)
                logMem("combo N=$t")
            }
            main.post { stirrer.stop() }
            Log.i(TAG, "COMBO DONE | sync=$sync reveals=$n")
            logMem("combo end n=$n")
        }.also { it.start() }
    }

    private inner class CameraStirrer : Choreographer.FrameCallback {
        @Volatile private var running = false
        private var dir = 1.0
        private var frames = 0
        private val dLon = 0.00012
        fun start() { running = true; frames = 0; Choreographer.getInstance().postFrameCallback(this) }
        fun stop() { running = false }
        override fun doFrame(frameTimeNanos: Long) {
            if (!running) return
            map.cameraPosition.target?.let { c ->
                map.moveCamera(CameraUpdateFactory.newLatLng(LatLng(c.latitude, c.longitude + dLon * dir)))
            }
            if (++frames % 80 == 0) dir = -dir
            Choreographer.getInstance().postFrameCallback(this)
        }
    }

    private fun sleep(ms: Long) { try { Thread.sleep(ms) } catch (_: InterruptedException) {} }

    private fun logMem(tag: String) {
        val rt = Runtime.getRuntime()
        val usedMb = (rt.totalMemory() - rt.freeMemory()) / (1024.0 * 1024.0)
        Log.i(TAG, String.format(Locale.US, "MEM %s usedMb=%.1f", tag, usedMb))
    }

    companion object { const val TAG = "SPIKEPERF" }
}
