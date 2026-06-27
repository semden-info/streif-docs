package no.streif.spike

import android.content.Context
import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection
import org.maplibre.geojson.MultiPolygon
import org.maplibre.geojson.Polygon
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.floor

/**
 * Spike-2 — in-memory сховище будинків + uniform-grid індекс для радіус/сегмент-матчингу.
 *
 * **Інкрементальне** (D24, on-demand): починається порожнім, `AreaLoader` додає зони на льоту
 * (`addFeatures`). Thread-safe: `addFeatures` (фон) і `match` (main) синхронізовані.
 *
 * Grid-комірки рахуються на REF_LAT (Volda — найпівнічніша → найбільші комірки → 3×3 коректне
 * на всіх нижчих широтах). Дистанція — за ЛОКАЛЬНОЮ широтою (`kLonAt`). centroid-within-R;
 * PIP/eligibility — пізніше.
 */
class BuildingStore(rMeters: Double) {

    private val kLat = 111320.0
    private val cellLatDeg = rMeters / kLat
    private val cellLonDeg = rMeters / (111320.0 * cos(REF_LAT * PI / 180.0))  // комірки на REF_LAT
    private val r2 = rMeters * rMeters

    private val grid = HashMap<Long, MutableList<Int>>()
    private val features = ArrayList<Feature>()
    private val clat = ArrayList<Double>()
    private val clon = ArrayList<Double>()
    private val ids = ArrayList<String>()
    private val indexOfId = HashMap<String, Int>()

    // Синхронізовані аксесори (C1: читання з main, мутація з фону — лише через лок BuildingStore)
    @Synchronized fun featureAt(idx: Int): Feature = features[idx]
    @Synchronized fun idAt(idx: Int): String = ids[idx]
    @Synchronized fun indexOf(id: String): Int? = indexOfId[id]

    /** Додати зону будинків (дедуп за building_id). Центроїди рахуємо ПОЗА локом, вставку — під локом. */
    fun addFeatures(feats: List<Feature>): Int {
        val prepared = ArrayList<Triple<Feature, String, DoubleArray>>(feats.size)
        for (i in feats.indices) {
            val f = feats[i]
            val id = f.getStringProperty("building_id") ?: continue
            prepared.add(Triple(f, id, centroid(f)))
        }
        var added = 0
        synchronized(this) {
            for ((f, id, c) in prepared) {
                if (indexOfId.containsKey(id)) continue
                val idx = features.size
                features.add(f); clon.add(c[0]); clat.add(c[1]); ids.add(id); indexOfId[id] = idx
                grid.getOrPut(cellKey(latIdx(c[1]), lonIdx(c[0]))) { ArrayList() }.add(idx)
                added++
            }
        }
        return added
    }

    private fun latIdx(lat: Double) = floor(lat / cellLatDeg).toInt()
    private fun lonIdx(lon: Double) = floor(lon / cellLonDeg).toInt()
    private fun cellKey(la: Int, lo: Int): Long = (la.toLong() shl 32) or (lo.toLong() and 0xffffffffL)
    private fun kLonAt(lat: Double) = 111320.0 * cos(lat * PI / 180.0)

    @Synchronized
    fun match(lat: Double, lon: Double, out: MutableList<Int>) {
        out.clear()
        val kLonL = kLonAt(lat)
        val la = latIdx(lat); val lo = lonIdx(lon)
        for (dla in -1..1) for (dlo in -1..1) {
            val bucket = grid[cellKey(la + dla, lo + dlo)] ?: continue
            for (idx in bucket) {
                val dx = (clon[idx] - lon) * kLonL
                val dy = (clat[idx] - lat) * kLat
                if (dx * dx + dy * dy <= r2) out.add(idx)
            }
        }
    }

    @Synchronized
    fun matchSegment(lat0: Double, lon0: Double, lat1: Double, lon1: Double, out: MutableList<Int>) {
        out.clear()
        val kLonL = kLonAt(lat0)
        val laMin = latIdx(minOf(lat0, lat1)) - 1; val laMax = latIdx(maxOf(lat0, lat1)) + 1
        val loMin = lonIdx(minOf(lon0, lon1)) - 1; val loMax = lonIdx(maxOf(lon0, lon1)) + 1
        val ax = lon0 * kLonL; val ay = lat0 * kLat
        val bx = lon1 * kLonL; val by = lat1 * kLat
        for (la in laMin..laMax) for (lo in loMin..loMax) {
            val bucket = grid[cellKey(la, lo)] ?: continue
            for (idx in bucket) {
                val px = clon[idx] * kLonL; val py = clat[idx] * kLat
                if (distPointToSeg2(px, py, ax, ay, bx, by) <= r2) out.add(idx)
            }
        }
    }

    private fun distPointToSeg2(px: Double, py: Double, ax: Double, ay: Double, bx: Double, by: Double): Double {
        val dx = bx - ax; val dy = by - ay
        val len2 = dx * dx + dy * dy
        val t = if (len2 <= 0.0) 0.0 else (((px - ax) * dx + (py - ay) * dy) / len2).coerceIn(0.0, 1.0)
        val cx = ax + t * dx; val cy = ay + t * dy
        val ex = px - cx; val ey = py - cy
        return ex * ex + ey * ey
    }

    @Synchronized
    fun collectionFor(indices: Collection<Int>): FeatureCollection {
        val list = ArrayList<Feature>(indices.size)
        for (i in indices) list.add(features[i])
        return FeatureCollection.fromFeatures(list)
    }

    val size: Int @Synchronized get() = features.size

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

        fun centroid(f: Feature): DoubleArray {
            val ring = when (val g = f.geometry()) {
                is MultiPolygon -> g.coordinates().firstOrNull()?.firstOrNull()
                is Polygon -> g.coordinates().firstOrNull()
                else -> null
            } ?: return doubleArrayOf(0.0, 0.0)
            var sx = 0.0; var sy = 0.0
            for (p in ring) { sx += p.longitude(); sy += p.latitude() }
            val k = ring.size.toDouble().coerceAtLeast(1.0)
            return doubleArrayOf(sx / k, sy / k)
        }
    }
}
