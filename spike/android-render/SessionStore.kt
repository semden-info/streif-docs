package no.streif.spike

import java.io.File
import java.util.concurrent.Executors

/**
 * Spike-2 — підсумки прогулянок (фундамент під тижневий підсумок і майбутні рейтинги).
 * CSV `startTs,endTs,distanceM,newCount` по рядку. Локально (D14); агрегати на сервер — лише v2.
 */
class SessionStore(private val file: File) {

    fun append(startTs: Long, endTs: Long, distanceM: Double, newCount: Int) {
        val line = "$startTs,$endTs,${distanceM.toInt()},$newCount\n"
        val f = file
        IO.execute { f.appendText(line) }
    }

    companion object {
        private val IO = Executors.newSingleThreadExecutor()
    }
}
