package no.streif.spike

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.Update
import androidx.sqlite.driver.bundled.BundledSQLiteDriver
import kotlinx.coroutines.Dispatchers
import java.io.File

/**
 * MVP-0 — Room-персистенція (D11), заміна flat-файлів VisitStore/SessionStore.
 *
 * `building_id` — ключ розкриття. D30: продакшн-id = Matrikkelen `bygningsnummer` (`source`="matrikkelen"),
 * зараз dogfood-джерело OSM (`source`="osm"). Колонка `source` дає простір імен для міграції Overpass→CC-BY
 * (щоб не сплутати `w<wayId>` з `m<nr>` і не осиротити розкриття при зміні джерела).
 *
 * `session` пишеться інкрементально (insert на старті → checkpoint по ходу) — інакше краш/OOM/force-stop
 * посеред прогулянки губить усю сесію (D23-review #11: sessions.csv писався лише на штатний Stop).
 *
 * MVP-0-полір (D11): УСІ Room-виклики винесено з головного потоку (`TrackingRepository.dbIo` —
 * single-thread executor), тож `allowMainThreadQueries` прибрано. Локаційні колбеки (де reveal→insert)
 * ідуть на main looper — блокуючий DB-запис там давав би jank/ANR при рості історії розкриттів.
 */

@Entity(tableName = "visits")
data class VisitEntity(
    @PrimaryKey val buildingId: String,
    val type: String,
    val firstSeenTs: Long,
    val source: String,             // "osm" | "matrikkelen" (D30)
)

@Entity(tableName = "sessions")
data class SessionEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val startTs: Long,
    val endTs: Long,                // 0 поки триває
    val distanceM: Double,
    val newCount: Int,
)

@Dao
interface VisitDao {
    @Query("SELECT * FROM visits")
    fun all(): List<VisitEntity>

    @Insert(onConflict = OnConflictStrategy.IGNORE)   // ідемпотентно за building_id
    fun insert(v: VisitEntity)

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    fun insertAll(vs: List<VisitEntity>)

    @Query("SELECT COUNT(*) FROM visits")
    fun count(): Int

    @Query("DELETE FROM visits")
    fun clear()
}

@Dao
interface SessionDao {
    @Insert
    fun insert(s: SessionEntity): Long        // повертає rowId → оновлюємо по ходу

    @Update
    fun update(s: SessionEntity)

    @Query("DELETE FROM sessions WHERE id = :id")
    fun delete(id: Long)

    @Query("SELECT * FROM sessions ORDER BY startTs")
    fun all(): List<SessionEntity>
}

@Database(entities = [VisitEntity::class, SessionEntity::class], version = 1, exportSchema = false)
abstract class MvpDatabase : RoomDatabase() {
    abstract fun visits(): VisitDao
    abstract fun sessions(): SessionDao

    companion object {
        @Volatile private var inst: MvpDatabase? = null
        fun get(ctx: Context): MvpDatabase = inst ?: synchronized(this) {
            inst ?: Room.databaseBuilder(ctx.applicationContext, MvpDatabase::class.java, "streif.db")
                .setDriver(BundledSQLiteDriver())               // D11: bundled SQLite — однакова версія на всіх пристроях
                .setQueryCoroutineContext(Dispatchers.IO)       // контекст драйвера (виклики й так off-main через dbIo)
                .build().also { inst = it }   // MVP-0-полір: усі Room-виклики off-main (TrackingRepository.dbIo)
        }
    }
}

/**
 * Одноразова міграція flat `visited.txt` → Room (D30 source="osm"). Запускати ДО init.
 * Файл НЕ видаляємо: у DEBUG TrackingRepository далі дублює туди розкриття для `analyze.py`.
 */
object MvpImporter {
    fun importVisitsOnce(db: MvpDatabase, filesDir: File) {
        if (db.visits().count() > 0) return                 // уже імпортовано
        val old = File(filesDir, "visited.txt")
        if (!old.exists()) return
        val recs = VisitStore(old).load()
        if (recs.isNotEmpty()) {
            db.visits().insertAll(recs.map { VisitEntity(it.id, it.type, it.ts, "osm") })
        }
    }
}
