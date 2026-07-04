package no.streif.spike

/**
 * Spike-2 — знімок статистики для UI/майбутніх рейтингів. Лягає в три виміри D13:
 *  • Coverage — `coveragePct` (розкрито / досяжних будинків D6);
 *  • Variety  — `byType` (розбивка за типами);
 *  • Discovery — `sessionNew` / `sessionDistanceM` (нове за поточний маршрут).
 * Без єдиного score (D13). Серверні рейтинги — v2 (потребують auth+бекенд, P5).
 */
data class Stats(
    val total: Int,
    val totalBuildings: Int,
    val byType: Map<String, Int>,
    val sessionNew: Int,
    val sessionDistanceM: Double,
) {
    val coveragePct: Double get() = if (totalBuildings > 0) total * 100.0 / totalBuildings else 0.0
}
