package no.streif.spike

import android.location.Location
import java.io.File
import java.util.concurrent.Executors

/**
 * Spike-2 — diagnostic-збір сирого треку для тюнінгу матчингу/перфу й подальшої розробки (D14).
 *
 * ⚠️ DIAGNOSTIC ONLY — НЕ ДЛЯ ПУБЛІЧНОЇ ВЕРСІЇ. Підключається лише коли `BuildConfig.DEBUG`
 * (див. MainActivity) → у release-білді збір автоматично вимкнено (забути неможливо). Дані
 * лежать ЛОКАЛЬНО (D14: сирий GPS не залишає пристрій), ручне видалення; у релізі — налаштування.
 *
 * CSV: t(epoch ms),lat,lon,accuracy(m),speed(m/s),matchedThisFix,revealedTotal,note(gate-стан)
 */
class DiagnosticRecorder(private val file: File) {

    fun log(loc: Location, matchedThisFix: Int, revealedTotal: Int, note: String) {
        val acc = if (loc.hasAccuracy()) loc.accuracy else -1f
        val spd = if (loc.hasSpeed()) loc.speed else -1f
        val n = note.ifEmpty { "ok" }
        val line = "${loc.time},${loc.latitude},${loc.longitude},$acc,$spd,$matchedThisFix,$revealedTotal,$n\n"
        val f = file
        IO.execute { f.appendText(line) }
    }

    companion object {
        private val IO = Executors.newSingleThreadExecutor()
    }
}
