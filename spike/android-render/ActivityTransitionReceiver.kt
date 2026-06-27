package no.streif.spike

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.google.android.gms.location.ActivityTransition
import com.google.android.gms.location.ActivityTransitionResult

/**
 * Spike-2 Stage B — приймає ENTER/EXIT-події Activity Recognition Transition API
 * (PendingIntent із WalkTrackingService) і годує ActivityGate. ENTER важливі: вони
 * виставляють стан vehicle/bike (research 2026-06-22).
 */
class ActivityTransitionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (!ActivityTransitionResult.hasResult(intent)) return
        val result = ActivityTransitionResult.extractResult(intent) ?: return
        for (e in result.transitionEvents) {
            if (e.transitionType == ActivityTransition.ACTIVITY_TRANSITION_ENTER) {
                ActivityGate.onActivityEnter(e.activityType)
            }
        }
    }
}
