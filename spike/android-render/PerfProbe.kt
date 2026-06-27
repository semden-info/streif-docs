package no.streif.spike

import android.util.Log
import org.maplibre.android.maps.MapView
import java.util.Locale

/**
 * Spike-1 v2 — інструментація рендеру через ВЛАСНИЙ frame-listener MapLibre.
 *
 * Чому не JankStats / dumpsys gfxinfo / Macrobenchmark: MapLibre малює у власному
 * GL/Vulkan-треді на SurfaceView, який SurfaceFlinger компонує окремим шаром повз
 * HWUI — стандартні Android-інструменти його кадрів НЕ бачать (research 2026-06-22,
 * підтверджено доками MapLibre + Perfetto).
 *
 * Метрики:
 *  • міжкадровий wall-clock інтервал (System.nanoTime) → fps; unit-independent, надійний;
 *  • frameRenderingTime з колбека (raw, одиниці недокументовані — лог сирим);
 *  • латентність setGeoJson → перший fully-відрендерений кадр.
 *
 * Лог тег [SPIKEPERF] → знімається adb logcat.
 */
class PerfProbe(private val mapView: MapView) : MapView.OnDidFinishRenderingFrameListener {

    @Volatile private var windowActive = false
    private var lastFrameNs = 0L
    private val intervalsMs = ArrayList<Double>(4096)
    private val renderRaw = ArrayList<Double>(4096)

    @Volatile private var pendingNs = 0L
    @Volatile private var pendingN = 0

    fun attach() = mapView.addOnDidFinishRenderingFrameListener(this)
    fun detach() = mapView.removeOnDidFinishRenderingFrameListener(this)

    /** Позначити момент виклику setGeoJson — латентність зафіксуємо на найближчому fully-кадрі. */
    fun markUpdate(n: Int) { pendingN = n; pendingNs = System.nanoTime() }

    fun beginWindow() {
        intervalsMs.clear(); renderRaw.clear(); lastFrameNs = 0L; windowActive = true
    }

    fun endWindow(label: String) {
        windowActive = false
        if (intervalsMs.isEmpty()) { Log.i(TAG, "$label | no frames (static / WHEN_DIRTY)"); return }
        val iv = intervalsMs.sorted()
        val avg = iv.average()
        val p50 = iv[iv.size / 2]
        val p90 = iv[(iv.size * 9 / 10).coerceAtMost(iv.size - 1)]
        val p99 = iv[(iv.size * 99 / 100).coerceAtMost(iv.size - 1)]
        val max = iv.last()
        val fps = if (avg > 0) 1000.0 / avg else 0.0
        val jank16 = iv.count { it > 16.7 }
        val rAvg = if (renderRaw.isNotEmpty()) renderRaw.average() else -1.0
        Log.i(
            TAG, String.format(
                Locale.US,
                "%s | frames=%d fps=%.1f ivMs[avg/p50/p90/p99/max]=%.1f/%.1f/%.1f/%.1f/%.1f jank>16.7ms=%d renderRawAvg=%.5f",
                label, iv.size, fps, avg, p50, p90, p99, max, jank16, rAvg
            )
        )
    }

    override fun onDidFinishRenderingFrame(fully: Boolean, frameEncodingTime: Double, frameRenderingTime: Double) {
        val now = System.nanoTime()
        if (pendingNs != 0L && fully) {
            val ms = (now - pendingNs) / 1e6
            Log.i(TAG, String.format(Locale.US, "setGeoJson->frame | N=%d latencyMs=%.1f", pendingN, ms))
            pendingNs = 0L
        }
        if (windowActive) {
            if (lastFrameNs != 0L) intervalsMs.add((now - lastFrameNs) / 1e6)
            renderRaw.add(frameRenderingTime)
            lastFrameNs = now
        }
    }

    companion object { const val TAG = "SPIKEPERF" }
}
