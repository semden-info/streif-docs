package no.streif.spike

import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * Spike-2 D24/S8 (Варіант 1) — pre-hosted CC-BY джерело будинків: OSM-геометрія [ODbL] +
 * тип Matrikkelen [CC-BY], попередньо з'єднані офлайн-пайплайном у статичні тайли
 * `area_{la}_{lo}.geojson` на CDN. Заміна runtime-Overpass перед публічним релізом.
 *
 * Фічі вже несуть `building_id` (m<bygningsnummer> | w<osmid>), `type`, `accessible` —
 * жодного runtime-збагачення не треба (тільки GET + parse). blocking, викликати off-main.
 */
class CdnGeoJsonAreaSource(private val baseUrl: String) : AreaSource {

    override fun fetch(lat: Double, lon: Double, halfKm: Double): List<Feature>? {
        // Ключ тайла ЗБІГАЄТЬСЯ з AreaCache.keyFor (сітка 0.02°); AreaLoader передає центр тайла.
        val la = Math.round(lat / AreaCache.TILE)
        val lo = Math.round(lon / AreaCache.TILE)
        val url = "${baseUrl.trimEnd('/')}/area_${la}_${lo}.geojson"
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 15000; readTimeout = 30000
            setRequestProperty("User-Agent", "Streif/0.4 (contact@semden.info)")
            // без ручного Accept-Encoding — HttpURLConnection сам додає gzip і прозоро розпаковує
        }
        try {
            val code = conn.responseCode
            if (code == 404) return emptyList()          // порожня зона — позначити завантаженою, не ретраїти
            if (code != 200) throw IOException("HTTP $code")
            val text = conn.inputStream.bufferedReader().use { it.readText() }
            return FeatureCollection.fromJson(text).features()
        } catch (e: Exception) {
            return null                                   // мережа/парс — AreaLoader ретрайне з backoff
        } finally {
            conn.disconnect()
        }
    }
}
