package no.streif.spike

import java.io.File
import java.util.concurrent.Executors

/** Один запис розкриття: стабільний `building_id`, тип, час (epoch ms). */
data class VisitRecord(val id: String, val type: String, val ts: Long)

/**
 * Spike-2 — збереження розкритих будинків між запусками (фундамент статистики).
 * CSV `id,type,ts` по рядку у filesDir (Room — на MVP-0, D11). Тип+час дають Variety+Discovery
 * (D13). Стабільний `building_id` переживає регенерацію даних.
 *
 * Запис — поза main-тредом через **спільний** single-thread executor (один на процес — C3).
 * Trade-off (C2): append асинхронний; при hard-kill за мс до flush можна втратити останній
 * батч (живий стан тримає TrackingRepository; у межах сесії втрати нема). Прийнятно для spike.
 */
class VisitStore(private val file: File) {

    fun load(): List<VisitRecord> {
        if (!file.exists()) return emptyList()
        return file.readLines().mapNotNull { line ->
            if (line.isBlank()) return@mapNotNull null
            val p = line.split(",")
            when {
                p.size >= 3 -> VisitRecord(p[0], p[1], p[2].toLongOrNull() ?: 0L)
                p.size == 1 -> VisitRecord(p[0], "other", 0L)   // legacy-формат (лише id)
                else -> null
            }
        }
    }

    fun append(records: Collection<VisitRecord>) {
        if (records.isEmpty()) return
        val lines = records.map { "${it.id},${it.type},${it.ts}" }
        val f = file
        IO.execute { f.appendText(lines.joinToString(separator = "\n", postfix = "\n")) }
    }

    fun clear() { val f = file; IO.execute { if (f.exists()) f.delete() } }

    companion object {
        private val IO = Executors.newSingleThreadExecutor()
    }
}
