package no.streif.spike

import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection
import java.io.File

/**
 * Spike-2 D24 — локальний кеш зон (filesDir). Зона = тайл ~0.05° (раз стягнули — назавжди).
 */
class AreaCache(private val dir: File) {

    fun keyFor(lat: Double, lon: Double): String {
        val la = Math.round(lat / TILE)
        val lo = Math.round(lon / TILE)
        return "area_${la}_${lo}"
    }

    fun centerLat(lat: Double) = Math.round(lat / TILE).toDouble() * TILE
    fun centerLon(lon: Double) = Math.round(lon / TILE).toDouble() * TILE

    fun load(key: String): List<Feature>? {
        val f = File(dir, "$key.geojson")
        if (!f.exists()) return null
        return try { FeatureCollection.fromJson(f.readText()).features() } catch (e: Exception) { null }
    }

    fun save(key: String, feats: List<Feature>) {
        try { File(dir, "$key.geojson").writeText(FeatureCollection.fromFeatures(feats).toJson()) } catch (e: Exception) {}
    }

    // 0.05→0.02 (P): дрібніші тайли = швидший cold-load стартового тайла + працює префетч-наперед
    companion object { const val TILE = 0.02 }   // ~2.2 км lat / ~1.0 км lon @62° N
}
