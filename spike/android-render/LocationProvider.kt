package no.streif.spike

import android.annotation.SuppressLint
import android.content.Context
import android.location.Location
import android.os.Looper
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority

/**
 * Spike-2 — абстракція джерела локації (за інтерфейсом — щоб лишити no-GMS-шлях:
 * `LocationManager FUSED_PROVIDER`/`GPS_PROVIDER`, research 2026-06-22).
 */
interface LocationProvider {
    fun start(onLocation: (Location) -> Unit)
    fun stop()
}

/** GMS Fused — рекомендований для ходьби: PRIORITY_HIGH_ACCURACY, інтервал ~2 с (D5/research). */
class FusedLocationProvider(
    context: Context,
    private val intervalMs: Long,
) : LocationProvider {
    private val client: FusedLocationProviderClient =
        LocationServices.getFusedLocationProviderClient(context)
    private var callback: LocationCallback? = null

    @SuppressLint("MissingPermission") // дозвіл перевіряється у MainActivity перед стартом сервісу
    override fun start(onLocation: (Location) -> Unit) {
        val req = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, intervalMs)
            .setMinUpdateIntervalMillis(intervalMs)
            .setMinUpdateDistanceMeters(0f)        // фільтр по accuracy/min-move — у коді (D5)
            .setWaitForAccurateLocation(true)
            .build()
        val cb = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                result.lastLocation?.let(onLocation)
            }
        }
        callback = cb
        client.requestLocationUpdates(req, cb, Looper.getMainLooper())
    }

    override fun stop() {
        callback?.let { client.removeLocationUpdates(it) }
        callback = null
    }
}
