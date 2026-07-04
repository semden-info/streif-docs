package no.streif.spike

import android.content.Context
import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection
import org.maplibre.geojson.MultiPolygon
import org.maplibre.geojson.Point
import org.maplibre.geojson.Polygon
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.sqrt

/**
 * Spike-2 — in-memory сховище будинків + uniform-grid індекс для **edge-матчингу** (відстань до
 * КОНТУРУ полігона, не до центроїда — польовий присуд 2026-06-26, D25).
 *
 * **Інкрементальне** (D24, on-demand): починається порожнім, `AreaLoader` додає зони на льоту
 * (`addFeatures`). Thread-safe: `addFeatures` (фон) і `candidatesPoint`/`match` (main) синхронізовані.
 *
 * Геометрія зберігається в lon/lat; точна відстань рахується в **локальній планарній проєкції за
 * широтою ЗАПИТУ** (kLon=kLonAt(qlat)) — коректно на будь-якій широті Норвегії, не лише на REF_LAT.
 * Grid — лише broad-phase: будинок індексується у ВСІ комірки, що накриває його bbox (тому великий/
 * видовжений будинок із далеким центроїдом, але близькою стіною не випадає до edge-тесту — фікс grid-
 * gather з адверсивного рев'ю). Комірки — у фіксованій REF-проєкції, скан запиту з запасом (PAD).
 */
class BuildingStore(rMeters: Double) {

    private val defaultR = rMeters                       // R за замовч. для match() (PerfHarness/тести)
    private val kLat = 111320.0
    private val kLonRef = 111320.0 * cos(REF_LAT * PI / 180.0)   // лише для grid-комірок
    private val gcell = 32.0                             // розмір комірки grid (м)

    // per-building (index-aligned)
    private val features = ArrayList<Feature>()
    private val ids = ArrayList<String>()
    private val indexOfId = HashMap<String, Int>()
    private val clat = ArrayList<Double>()               // центроїд (для nearest/маркування)
    private val clon = ArrayList<Double>()
    private val accessible = ArrayList<Boolean>()        // D6: доступний з пішої мережі (лише такі розкриваються)
    private var accCount = 0                              // к-сть accessible (знаменник Coverage-%)
    private val ringLon = ArrayList<DoubleArray>()       // зовнішнє кільце (закрите), lon/lat
    private val ringLat = ArrayList<DoubleArray>()

    private val grid = HashMap<Long, MutableList<Int>>()
    private val seen = HashSet<Int>()                    // дедуп у межах одного запиту (будинок у кількох комірках)
    private val scratch = ArrayList<Double>()

    // Синхронізовані аксесори (C1: мутація з фону, читання з main — лише через лок BuildingStore)
    @Synchronized fun featureAt(idx: Int): Feature = features[idx]
    @Synchronized fun idAt(idx: Int): String = ids[idx]
    @Synchronized fun indexOf(id: String): Int? = indexOfId[id]
    @Synchronized fun centroidLatLon(idx: Int): DoubleArray = doubleArrayOf(clat[idx], clon[idx])
    @Synchronized fun isAccessible(idx: Int): Boolean = accessible[idx]   // D6 eligibility (доступний з пішої мережі)

    private fun gcx(lon: Double) = floor(lon * kLonRef / gcell).toInt()
    private fun gcy(lat: Double) = floor(lat * kLat / gcell).toInt()
    private fun cellKey(cx: Int, cy: Int): Long = (cx.toLong() shl 32) or (cy.toLong() and 0xffffffffL)
    private fun kLonAt(lat: Double) = 111320.0 * cos(lat * PI / 180.0)

    /** Додати зону будинків (дедуп за building_id). Геометрію/центроїд готуємо ПОЗА локом, вставку — під локом. */
    fun addFeatures(feats: List<Feature>): Int {
        val prepared = ArrayList<Prepared>(feats.size)
        for (f in feats) {
            val id = f.getStringProperty("building_id") ?: continue
            val ring = outerRing(f) ?: continue
            val n = ring.size
            if (n < 4) continue
            val acc = f.getBooleanProperty("accessible") ?: true      // D6: seed/без-прапорця → доступний (не ламаємо perf-режими)
            val rlon = DoubleArray(n); val rlat = DoubleArray(n)
            var sLon = 0.0; var sLat = 0.0
            var minLon = Double.MAX_VALUE; var maxLon = -Double.MAX_VALUE
            var minLat = Double.MAX_VALUE; var maxLat = -Double.MAX_VALUE
            for (i in 0 until n) {
                val lo = ring[i].longitude(); val la = ring[i].latitude()
                rlon[i] = lo; rlat[i] = la; sLon += lo; sLat += la
                if (lo < minLon) minLon = lo; if (lo > maxLon) maxLon = lo
                if (la < minLat) minLat = la; if (la > maxLat) maxLat = la
            }
            prepared.add(Prepared(f, id, sLat / n, sLon / n, rlon, rlat, minLon, maxLon, minLat, maxLat, acc))
        }
        var added = 0
        synchronized(this) {
            for (p in prepared) {
                if (indexOfId.containsKey(p.id)) continue
                val idx = features.size
                features.add(p.f); ids.add(p.id); indexOfId[p.id] = idx
                clat.add(p.cLat); clon.add(p.cLon)
                ringLon.add(p.rlon); ringLat.add(p.rlat)
                accessible.add(p.acc); if (p.acc) accCount++
                var ci = gcx(p.minLon)
                val ciMax = gcx(p.maxLon); val cjMax = gcy(p.maxLat)
                while (ci <= ciMax) {
                    var cj = gcy(p.minLat)
                    while (cj <= cjMax) {
                        grid.getOrPut(cellKey(ci, cj)) { ArrayList() }.add(idx)
                        cj++
                    }
                    ci++
                }
                added++
            }
        }
        return added
    }

    /**
     * Кандидати — будинки, чия СТІНА (контур) у межах maxR від (lat,lon) — це **eligibility** (D25).
     * Заповнює outIdx + outEdge (edge-відстань, 0 якщо всередині) + outCen (відстань до ЦЕНТРОЇДА —
     * для closest-approach тайминга «по середині будинку», D25.1).
     */
    @Synchronized
    fun candidatesPoint(lat: Double, lon: Double, maxR: Double, outIdx: MutableList<Int>, outEdge: MutableList<Double>, outCen: MutableList<Double>) =
        candidatesPointLocked(lat, lon, maxR, outIdx, outEdge, outCen)

    /** Зручний обгортувач (PerfHarness/тести): індекси будинків зі стіною ≤ defaultR. */
    @Synchronized
    fun match(lat: Double, lon: Double, out: MutableList<Int>) = candidatesPointLocked(lat, lon, defaultR, out, scratch, null)

    /** Edge-distance² від (qx,qy) до контуру будинку idx у локальній проєкції; 0 якщо точка всередині. */
    private fun edgeDist2(qlat: Double, qlon: Double, qx: Double, qy: Double, kLon: Double, idx: Int): Double {
        val lons = ringLon[idx]; val lats = ringLat[idx]; val n = lons.size
        var inside = false; var mind2 = Double.MAX_VALUE
        for (i in 0 until n - 1) {
            val ax = lons[i] * kLon; val ay = lats[i] * kLat
            val bx = lons[i + 1] * kLon; val by = lats[i + 1] * kLat
            val d2 = distPointToSeg2(qx, qy, ax, ay, bx, by)
            if (d2 < mind2) mind2 = d2
            val yi = lats[i]; val yj = lats[i + 1]
            if ((yi > qlat) != (yj > qlat)) {
                val xint = (lons[i + 1] - lons[i]) * (qlat - lats[i]) / (lats[i + 1] - lats[i]) + lons[i]
                if (qlon < xint) inside = !inside
            }
        }
        return if (inside) 0.0 else mind2
    }

    private fun distPointToSeg2(px: Double, py: Double, ax: Double, ay: Double, bx: Double, by: Double): Double {
        val dx = bx - ax; val dy = by - ay
        val len2 = dx * dx + dy * dy
        val t = if (len2 <= 0.0) 0.0 else (((px - ax) * dx + (py - ay) * dy) / len2).coerceIn(0.0, 1.0)
        val cx = ax + t * dx; val cy = ay + t * dy
        val ex = px - cx; val ey = py - cy
        return ex * ex + ey * ey
    }

    /** Найближчий будинок (за стіною) до (lat,lon) у межах maxMeters — для debug-маркування. */
    @Synchronized
    fun nearest(lat: Double, lon: Double, maxMeters: Double): Int? {
        val idx = ArrayList<Int>(); val ds = ArrayList<Double>()
        candidatesPointLocked(lat, lon, maxMeters, idx, ds, null)
        var best = -1; var bd = Double.MAX_VALUE
        for (k in idx.indices) if (ds[k] < bd) { bd = ds[k]; best = idx[k] }
        return if (best >= 0) best else null
    }

    // внутрішній (без повторного локу) — викликається з уже синхронізованих методів.
    // outCen != null → додатково віддає відстань до центроїда (для тайминга D25.1).
    private fun candidatesPointLocked(lat: Double, lon: Double, maxR: Double, outIdx: MutableList<Int>, outEdge: MutableList<Double>, outCen: MutableList<Double>?) {
        outIdx.clear(); outEdge.clear(); outCen?.clear(); seen.clear()
        val kLon = kLonAt(lat); val qx = lon * kLon; val qy = lat * kLat; val r2 = maxR * maxR
        val pad = maxR + 40.0; val qxr = lon * kLonRef
        val ci0 = floor((qxr - pad) / gcell).toInt(); val ci1 = floor((qxr + pad) / gcell).toInt()
        val cj0 = floor((qy - pad) / gcell).toInt(); val cj1 = floor((qy + pad) / gcell).toInt()
        var ci = ci0
        while (ci <= ci1) {
            var cj = cj0
            while (cj <= cj1) {
                val bucket = grid[cellKey(ci, cj)]
                if (bucket != null) for (i2 in bucket) {
                    if (!seen.add(i2)) continue
                    val d2 = edgeDist2(lat, lon, qx, qy, kLon, i2)
                    if (d2 <= r2) {
                        outIdx.add(i2); outEdge.add(sqrt(d2))
                        if (outCen != null) {
                            val dxc = (clon[i2] - lon) * kLon; val dyc = (clat[i2] - lat) * kLat
                            outCen.add(sqrt(dxc * dxc + dyc * dyc))
                        }
                    }
                }
                cj++
            }
            ci++
        }
    }

    @Synchronized
    fun collectionFor(indices: Collection<Int>): FeatureCollection {
        val list = ArrayList<Feature>(indices.size)
        for (i in indices) list.add(features[i])
        return FeatureCollection.fromFeatures(list)
    }

    /** Усі завантажені будинки (debug-шар «все»: дає мітити будь-який, навіть нерозкритий). */
    @Synchronized
    fun allCollection(): FeatureCollection = FeatureCollection.fromFeatures(ArrayList(features))

    val size: Int @Synchronized get() = features.size
    val accessibleCount: Int @Synchronized get() = accCount   // D6: знаменник Coverage-% (досяжні будинки)

    private class Prepared(
        val f: Feature, val id: String, val cLat: Double, val cLon: Double,
        val rlon: DoubleArray, val rlat: DoubleArray,
        val minLon: Double, val maxLon: Double, val minLat: Double, val maxLat: Double,
        val acc: Boolean,
    )

    companion object {
        const val REF_LAT = 62.146

        /** Завантажити bundled geojson як seed (для перф-режимів). */
        fun loadSeed(ctx: Context, rMeters: Double): BuildingStore {
            val store = BuildingStore(rMeters)
            val json = ctx.assets.open("buildings.geojson").bufferedReader().use { it.readText() }
            store.addFeatures(FeatureCollection.fromJson(json).features() ?: emptyList())
            return store
        }

        /** Тест-фабрика (без Context). */
        internal fun fromFeatures(feats: List<Feature>, rMeters: Double): BuildingStore {
            val store = BuildingStore(rMeters)
            store.addFeatures(feats)
            return store
        }

        private fun outerRing(f: Feature): List<Point>? = when (val g = f.geometry()) {
            is MultiPolygon -> g.coordinates().firstOrNull()?.firstOrNull()
            is Polygon -> g.coordinates().firstOrNull()
            else -> null
        }
    }
}
