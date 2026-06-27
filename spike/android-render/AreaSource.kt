package no.streif.spike

import android.util.Xml
import org.maplibre.geojson.Feature
import org.maplibre.geojson.Point
import org.maplibre.geojson.Polygon
import org.xmlpull.v1.XmlPullParser
import java.io.IOException
import java.io.StringReader
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import kotlin.math.cos

/**
 * Spike-2 D24 — джерело будинків для зони (за інтерфейсом, щоб поміняти на Pre-hosted CC-BY CDN
 * перед публічним релізом — D24/S8). blocking, викликати off-main.
 */
interface AreaSource {
    /** Будинки в bbox ~halfKm навколо (lat,lon). null = невдача (мережа/сервер). */
    fun fetch(lat: Double, lon: Double, halfKm: Double): List<Feature>?
}

/** Тест/dogfood-джерело: публічний Overpass (ODbL, флакі — кешуємо зону раз). */
class OverpassAreaSource : AreaSource {

    private val mirrors = listOf(
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
    )

    override fun fetch(lat: Double, lon: Double, halfKm: Double): List<Feature>? {
        val dlat = halfKm / 111.32
        val dlon = halfKm / (111.32 * cos(Math.toRadians(lat)))
        val s = lat - dlat; val w = lon - dlon; val n = lat + dlat; val e = lon + dlon
        val query = "[out:xml][timeout:120];(way[\"building\"]($s,$w,$n,$e););(._;>;);out body;"
        val body = "data=" + URLEncoder.encode(query, "UTF-8")
        for (mirror in mirrors) {
            try {
                return parseOsm(post(mirror, body))
            } catch (e: Exception) { /* наступне дзеркало */ }
        }
        return null
    }

    private fun post(urlStr: String, body: String): String {
        val conn = (URL(urlStr).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"; doOutput = true
            connectTimeout = 20000; readTimeout = 130000
            setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
            setRequestProperty("User-Agent", "Streif-spike/0.4 (contact@semden.info)")
        }
        try {
            conn.outputStream.use { it.write(body.toByteArray()) }
            if (conn.responseCode != 200) throw IOException("HTTP ${conn.responseCode}")
            return conn.inputStream.bufferedReader().use { it.readText() }
        } finally { conn.disconnect() }
    }

    private fun parseOsm(xml: String): List<Feature> {
        val parser = Xml.newPullParser()
        parser.setInput(StringReader(xml))
        val nodeLon = HashMap<String, Double>(); val nodeLat = HashMap<String, Double>()
        val feats = ArrayList<Feature>()
        var wayId: String? = null
        var refs: ArrayList<String>? = null
        var tags: HashMap<String, String>? = null
        var event = parser.eventType
        while (event != XmlPullParser.END_DOCUMENT) {
            if (event == XmlPullParser.START_TAG) {
                when (parser.name) {
                    "node" -> {
                        val id = parser.getAttributeValue(null, "id")
                        nodeLon[id] = parser.getAttributeValue(null, "lon").toDouble()
                        nodeLat[id] = parser.getAttributeValue(null, "lat").toDouble()
                    }
                    "way" -> { wayId = parser.getAttributeValue(null, "id"); refs = ArrayList(); tags = HashMap() }
                    "nd" -> refs?.add(parser.getAttributeValue(null, "ref"))
                    "tag" -> tags?.put(parser.getAttributeValue(null, "k"), parser.getAttributeValue(null, "v"))
                }
            } else if (event == XmlPullParser.END_TAG && parser.name == "way") {
                val t = tags; val r = refs; val wid = wayId
                val b = t?.get("building")
                if (t != null && r != null && wid != null && b != null && b != "no" && r.size >= 4) {
                    val ring = ArrayList<Point>(r.size)
                    for (ref in r) {
                        val lo = nodeLon[ref]; val la = nodeLat[ref]
                        if (lo != null && la != null) ring.add(Point.fromLngLat(lo, la))
                    }
                    if (ring.size >= 4) {
                        val a = ring.first(); val z = ring.last()
                        if (a.longitude() != z.longitude() || a.latitude() != z.latitude()) ring.add(a)
                        val f = Feature.fromGeometry(Polygon.fromLngLats(listOf(ring)))
                        f.addStringProperty("building_id", "w$wid")
                        f.addStringProperty("type", classify(t))
                        feats.add(f)
                    }
                }
                wayId = null; refs = null; tags = null
            }
            event = parser.next()
        }
        return feats
    }

    private fun classify(t: Map<String, String>): String {
        val b = (t["building"] ?: "").lowercase()
        val am = (t["amenity"] ?: "").lowercase()
        val tour = (t["tourism"] ?: "").lowercase()
        if (b in SACRAL || am == "place_of_worship") return "sacral"
        if (b in HYTTE || tour in HYTTE_TOUR) return "hytte"
        if (b in HOUSING) return "housing"
        if (b in OUTBUILDING) return "outbuilding"
        if (b in PUBLIC) return "public"
        if (b == "yes" || b == "") {
            if (am in PUBLIC_AM || t["shop"] != null || t["office"] != null || tour in PUBLIC_TOUR) return "public"
        }
        return "other"
    }

    private companion object {
        val SACRAL = setOf("church", "chapel", "cathedral", "mosque", "temple", "synagogue", "shrine", "monastery")
        val HYTTE = setOf("cabin", "hut", "chalet")
        val HYTTE_TOUR = setOf("chalet", "alpine_hut", "wilderness_hut")
        val HOUSING = setOf("house", "detached", "residential", "apartments", "terrace", "semidetached_house", "bungalow", "dormitory", "houseboat", "static_caravan", "farm")
        val OUTBUILDING = setOf("garage", "garages", "shed", "barn", "farm_auxiliary", "carport", "greenhouse", "industrial", "warehouse", "service", "hangar", "stable", "sty", "cowshed", "silo", "storage_tank", "roof")
        val PUBLIC = setOf("commercial", "retail", "office", "school", "kindergarten", "university", "college", "hospital", "public", "civic", "hotel", "sports_centre", "sports_hall", "train_station", "transportation", "government", "fire_station")
        val PUBLIC_AM = setOf("school", "kindergarten", "university", "college", "hospital", "townhall", "library", "community_centre", "fire_station", "police")
        val PUBLIC_TOUR = setOf("hotel", "hostel", "guest_house")
    }
}
