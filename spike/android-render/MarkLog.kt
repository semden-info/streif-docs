package no.streif.spike

import java.io.File
import java.util.concurrent.Executors

/**
 * Spike-2 — лог ground-truth міток (debug-only): користувач тапає будинок на тесті й
 * каже «розкрито правильно / хибно». Точний фідбек для тюнінгу порогів матчингу.
 * CSV: t(epoch ms),building_id,mark(correct|wrong|clear),lat,lon,wasRevealed
 */
class MarkLog(private val file: File) {

    fun log(buildingId: String, mark: String, lat: Double, lon: Double, wasRevealed: Boolean) {
        val line = "${System.currentTimeMillis()},$buildingId,$mark,$lat,$lon,$wasRevealed\n"
        val f = file
        IO.execute { f.appendText(line) }
    }

    companion object { private val IO = Executors.newSingleThreadExecutor() }
}
