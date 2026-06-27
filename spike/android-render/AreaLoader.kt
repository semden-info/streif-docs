package no.streif.spike

import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import java.util.Collections
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors

/**
 * Spike-2 D24 — on-demand завантаження зон. На кожному (gate-ok) фіксі гарантує, що тайл
 * навколо тебе завантажений: кеш → інакше Overpass (фон) → `BuildingStore.addFeatures` →
 * колбек на main (перематчити поточну точку, щоб розкрити одразу). Кожен тайл — раз.
 */
class AreaLoader(
    private val store: BuildingStore,
    private val cache: AreaCache,
    private val source: AreaSource,
    private val onAreaLoaded: () -> Unit,
) {
    private val main = Handler(Looper.getMainLooper())
    private val loaded = Collections.synchronizedSet(HashSet<String>())
    private val loading = Collections.synchronizedSet(HashSet<String>())
    private val failedUntil = ConcurrentHashMap<String, Long>()   // кулдаун після невдачі (не спамити Overpass)
    private val io = Executors.newSingleThreadExecutor()

    /** Стан для UI: остання дія завантаження. */
    @Volatile var status: String = ""
        private set

    fun ensureArea(lat: Double, lon: Double) {
        val key = cache.keyFor(lat, lon)
        if (loaded.contains(key) || loading.contains(key)) return
        val until = failedUntil[key]
        if (until != null && SystemClock.elapsedRealtime() < until) return   // нещодавно впало — почекати (retry-backoff)
        loading.add(key)
        val cLat = cache.centerLat(lat); val cLon = cache.centerLon(lon)
        io.execute {
            val cached = cache.load(key)
            status = "завантаження зони…"
            val feats = cached ?: source.fetch(cLat, cLon, 3.0)?.also { cache.save(key, it) }
            if (feats != null) {
                val n = store.addFeatures(feats)
                loaded.add(key); failedUntil.remove(key)
                status = ""
                Log.i("SPIKEPERF", "area $key ${if (cached != null) "cache" else "fetch"}: +$n (store=${store.size})")
                main.post { onAreaLoaded() }
            } else {
                failedUntil[key] = SystemClock.elapsedRealtime() + RETRY_COOLDOWN_MS
                status = "немає даних зони (мережа?)"
                Log.i("SPIKEPERF", "area $key FETCH FAILED (retry за ${RETRY_COOLDOWN_MS / 1000}с)")
            }
            loading.remove(key)
        }
    }

    companion object { const val RETRY_COOLDOWN_MS = 20000L }
}
