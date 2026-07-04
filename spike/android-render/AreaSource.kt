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
import kotlin.math.floor

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
        // D6: тягнемо ще й highway (пішу мережу) — щоб порахувати eligibility (доступність з пішої мережі)
        val query = "[out:xml][timeout:120];(way[\"building\"]($s,$w,$n,$e);way[\"highway\"]($s,$w,$n,$e););(._;>;);out body;"
        val body = "data=" + URLEncoder.encode(query, "UTF-8")
        for (mirror in mirrors) {
            try {
                val (buildings, ways) = parseOsm(post(mirror, body))
                tagAccessible(buildings, ways, lat)   // D6: прапорець accessible на кожен будинок
                return buildings
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

    private fun parseOsm(xml: String): Pair<List<Feature>, List<List<Point>>> {
        val parser = Xml.newPullParser()
        parser.setInput(StringReader(xml))
        val nodeLon = HashMap<String, Double>(); val nodeLat = HashMap<String, Double>()
        val feats = ArrayList<Feature>()
        val ways = ArrayList<List<Point>>()            // D6: пішохідні полілінії
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
                if (t != null && r != null && wid != null) {
                    val pts = ArrayList<Point>(r.size)
                    for (ref in r) {
                        val lo = nodeLon[ref]; val la = nodeLat[ref]
                        if (lo != null && la != null) pts.add(Point.fromLngLat(lo, la))
                    }
                    val b = t["building"]; val hw = t["highway"]
                    if (b != null && b != "no" && pts.size >= 4) {
                        val a = pts.first(); val z = pts.last()
                        if (a.longitude() != z.longitude() || a.latitude() != z.latitude()) pts.add(a)
                        val f = Feature.fromGeometry(Polygon.fromLngLats(listOf(pts)))
                        f.addStringProperty("building_id", "w$wid")
                        f.addStringProperty("type", classify(t))
                        feats.add(f)
                    } else if (hw != null && hw in WALKABLE && pts.size >= 2) {
                        ways.add(pts)                  // D6: пішохідна лінія (footway/residential/…)
                    }
                }
                wayId = null; refs = null; tags = null
            }
            event = parser.next()
        }
        return Pair(feats, ways)
    }

    /**
     * D6: позначити кожен будинок `accessible`, якщо його контур ≤ BUFFER від пішої мережі (OSM highway).
     * Fail-open: якщо мережі нема (порожньо/не завантажилась) — усі accessible (не блокуємо reveal взагалі).
     * Grid над сегментами доріг → per-vertex nearest. Локальна проєкція за широтою запиту.
     */
    private fun tagAccessible(buildings: List<Feature>, ways: List<List<Point>>, qlat: Double) {
        if (ways.isEmpty()) { for (f in buildings) f.addBooleanProperty("accessible", true); return }
        val kLon = 111320.0 * cos(Math.toRadians(qlat)); val kLat = 111320.0
        val x1 = ArrayList<Double>(); val y1 = ArrayList<Double>(); val x2 = ArrayList<Double>(); val y2 = ArrayList<Double>()
        for (poly in ways) for (i in 0 until poly.size - 1) {
            x1.add(poly[i].longitude() * kLon); y1.add(poly[i].latitude() * kLat)
            x2.add(poly[i + 1].longitude() * kLon); y2.add(poly[i + 1].latitude() * kLat)
        }
        val grid = HashMap<Long, ArrayList<Int>>()
        for (i in x1.indices) {
            var cx = floor(minOf(x1[i], x2[i]) / CELL).toInt(); val cxM = floor(maxOf(x1[i], x2[i]) / CELL).toInt()
            val cyM = floor(maxOf(y1[i], y2[i]) / CELL).toInt()
            while (cx <= cxM) {
                var cy = floor(minOf(y1[i], y2[i]) / CELL).toInt()
                while (cy <= cyM) { grid.getOrPut(cellKey(cx, cy)) { ArrayList() }.add(i); cy++ }
                cx++
            }
        }
        val b2 = BUFFER * BUFFER; val span = (BUFFER / CELL).toInt() + 1
        var accCount = 0
        for (f in buildings) {
            val ring = (f.geometry() as? Polygon)?.coordinates()?.firstOrNull()
            var acc = false
            if (ring != null) outer@ for (p in ring) {
                val px = p.longitude() * kLon; val py = p.latitude() * kLat
                val cx0 = floor(px / CELL).toInt(); val cy0 = floor(py / CELL).toInt()
                for (dx in -span..span) for (dy in -span..span) {
                    val bucket = grid[cellKey(cx0 + dx, cy0 + dy)] ?: continue
                    for (si in bucket) if (distPtSeg2(px, py, x1[si], y1[si], x2[si], y2[si]) <= b2) { acc = true; break@outer }
                }
            }
            f.addBooleanProperty("accessible", acc); if (acc) accCount++
        }
        android.util.Log.i("SPIKEPERF", "D6 accessible $accCount/${buildings.size} (ways=${ways.size})")
    }

    private fun cellKey(cx: Int, cy: Int): Long = (cx.toLong() shl 32) or (cy.toLong() and 0xffffffffL)

    private fun distPtSeg2(px: Double, py: Double, ax: Double, ay: Double, bx: Double, by: Double): Double {
        val dx = bx - ax; val dy = by - ay; val len2 = dx * dx + dy * dy
        val t = if (len2 <= 0.0) 0.0 else (((px - ax) * dx + (py - ay) * dy) / len2).coerceIn(0.0, 1.0)
        val ex = px - (ax + t * dx); val ey = py - (ay + t * dy)
        return ex * ex + ey * ey
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
        // D6: пішохідно-доступні highway (motorway/trunk/primary самі по собі — не «піша мережа»)
        val WALKABLE = setOf("footway", "pedestrian", "path", "steps", "residential", "living_street", "service", "unclassified", "track", "cycleway", "tertiary")
        const val BUFFER = 28.0    // будинок eligible якщо контур ≤ цього від пішої мережі (тюнабельно, як R_FAR)
        const val CELL = 40.0      // розмір комірки grid сегментів доріг (м)
    }
}
