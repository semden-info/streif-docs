package no.streif.spike

import android.Manifest
import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.google.android.gms.location.ActivityRecognition
import com.google.android.gms.location.ActivityTransition
import com.google.android.gms.location.ActivityTransitionRequest
import com.google.android.gms.location.DetectedActivity

/**
 * Spike-2 — Foreground Service `type=location` для трекінгу прогулянки.
 *
 * Foreground-only: стартує лише з видимого екрана (тап «Старт») — БЕЗ
 * ACCESS_BACKGROUND_LOCATION (research 2026-06-22; `05` §4/ADR-09). Локація FGS не має
 * таймауту й тече при згаслому екрані. Дозвіл локації перевіряється у MainActivity ДО старту.
 */
class WalkTrackingService : Service() {

    private var provider: LocationProvider? = null
    private var arPending: PendingIntent? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopTracking()
            return START_NOT_STICKY
        }
        // Foreground-only: не «озброюємось» повторно на sticky-restart із null-intent (зомбі-FGS).
        if (intent == null) { stopSelf(); return START_NOT_STICKY }
        // Дозвіл перевіряємо тут (а не лише в Activity) — sticky/revoke шлях інакше крешить на API34+.
        if (!hasLocationPermission()) { stopSelf(); return START_NOT_STICKY }
        try {
            ServiceCompat.startForeground(
                this, NOTIF_ID, buildNotification(),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION
            )
        } catch (e: Exception) {
            stopSelf(); return START_NOT_STICKY
        }
        if (provider == null) {
            TrackingRepository.startSession()
            provider = FusedLocationProvider(this, INTERVAL_MS).also { p ->
                p.start { loc -> TrackingRepository.onLocation(loc) }
            }
            requestActivityUpdates()           // Stage B: vehicle/bike-gate (деградує, якщо немає дозволу)
        }
        TrackingRepository.isTracking = true
        return START_NOT_STICKY
    }

    private fun hasLocationPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    private fun stopTracking() {
        provider?.stop(); provider = null
        removeActivityUpdates()
        TrackingRepository.isTracking = false
        TrackingRepository.endSession()
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        provider?.stop(); provider = null
        removeActivityUpdates()
        TrackingRepository.isTracking = false
        super.onDestroy()
    }

    // ---- Activity Recognition Transition API (Stage B) ----
    @SuppressLint("MissingPermission") // ACTIVITY_RECOGNITION перевіряється тут же
    private fun requestActivityUpdates() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACTIVITY_RECOGNITION) != PackageManager.PERMISSION_GRANTED) return
        val types = intArrayOf(
            DetectedActivity.IN_VEHICLE, DetectedActivity.ON_BICYCLE,
            DetectedActivity.WALKING, DetectedActivity.RUNNING, DetectedActivity.STILL
        )
        val transitions = ArrayList<ActivityTransition>()
        for (t in types) {
            transitions.add(ActivityTransition.Builder().setActivityType(t).setActivityTransition(ActivityTransition.ACTIVITY_TRANSITION_ENTER).build())
            transitions.add(ActivityTransition.Builder().setActivityType(t).setActivityTransition(ActivityTransition.ACTIVITY_TRANSITION_EXIT).build())
        }
        val flags = (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) PendingIntent.FLAG_MUTABLE else 0) or PendingIntent.FLAG_UPDATE_CURRENT
        val pi = PendingIntent.getBroadcast(this, 7, Intent(this, ActivityTransitionReceiver::class.java), flags)
        arPending = pi
        try {
            ActivityRecognition.getClient(this).requestActivityTransitionUpdates(ActivityTransitionRequest(transitions), pi)
        } catch (e: Exception) { /* AR недоступне → ActivityGate деградує до speed-only */ }
    }

    private fun removeActivityUpdates() {
        arPending?.let { pi ->
            try { ActivityRecognition.getClient(this).removeActivityTransitionUpdates(pi) } catch (_: Exception) {}
        }
        arPending = null
    }

    private fun buildNotification(): Notification {
        createChannel()
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val stop = PendingIntent.getService(
            this, 1, Intent(this, WalkTrackingService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Streif — прогулянка")
            .setContentText("Розкриваю будинки на твоєму шляху")
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setOngoing(true)
            .setContentIntent(open)
            .addAction(0, "Стоп", stop)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(CHANNEL_ID, "Трекінг прогулянки", NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
        }
    }

    companion object {
        const val ACTION_STOP = "no.streif.spike.STOP"
        private const val CHANNEL_ID = "walk"
        private const val NOTIF_ID = 42
        private const val INTERVAL_MS = 2000L   // ~2 с (рішення 1; уточнити по battery-gate, Stage C)
    }
}
