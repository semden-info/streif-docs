package no.streif.spike

import com.google.android.gms.location.DetectedActivity

/**
 * Spike-2 Stage B — gate авто/велосипеда (D5).
 *
 * Поєднує Activity Recognition (блокує `IN_VEHICLE`/`ON_BICYCLE`) + GPS-швидкість
 * (пішохідний діапазон) з **гістерезисом**. Консервативно (рішення 3): розкривати лише
 * після підтвердження ходьби (dwell), бо AR лагає ~30–60 с і плутає stop-go-затор
 * (research 2026-06-22). Якщо `ACTIVITY_RECOGNITION` не надано — **деградує до speed-only**
 * (vehicleOrBike лишається false, працює лише over-speed-фільтр).
 *
 * Пороги — стартові гіпотези, польове тюнінг (P2).
 */
object ActivityGate {
    const val MAX_PED_SPEED = 7.0f   // м/с (~25 км/год): вище — точно не пішки (над спринтом ~6, під велокрейсером)
    const val OPEN_DWELL = 3         // підряд фіксів у діапазоні, щоб (пере)відкрити gate

    @Volatile private var vehicleOrBike = false
    private var inBandStreak = 0

    /** Причина блокування для статусу UI (порожньо = дозволено). */
    @Volatile var blockedReason: String = ""
        private set

    fun reset() { vehicleOrBike = false; inBandStreak = 0; blockedReason = "" }

    /** ENTER-подія Activity Transition API. */
    fun onActivityEnter(activityType: Int) {
        when (activityType) {
            DetectedActivity.IN_VEHICLE, DetectedActivity.ON_BICYCLE -> { vehicleOrBike = true; inBandStreak = 0 }
            DetectedActivity.WALKING, DetectedActivity.RUNNING -> vehicleOrBike = false
            // STILL/інше — стан не міняємо
        }
    }

    /** На кожен GPS-фікс: чи дозволити матчинг (з гістерезисом на відкриття). */
    fun allow(speedMps: Float, hasSpeed: Boolean): Boolean {
        val overSpeed = hasSpeed && speedMps > MAX_PED_SPEED
        if (vehicleOrBike || overSpeed) {
            inBandStreak = 0
            blockedReason = if (vehicleOrBike) "авто/велосипед — пауза" else "надто швидко — пауза"
            return false
        }
        if (inBandStreak < OPEN_DWELL) inBandStreak++
        return if (inBandStreak >= OPEN_DWELL) {
            blockedReason = ""; true
        } else {
            blockedReason = "підтвердження ходьби…"; false
        }
    }
}
