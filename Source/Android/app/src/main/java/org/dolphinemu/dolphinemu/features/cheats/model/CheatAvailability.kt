// SPDX-License-Identifier: GPL-2.0-or-later

package org.dolphinemu.dolphinemu.features.cheats.model

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.dolphinemu.dolphinemu.model.GameFile
import java.util.concurrent.ConcurrentHashMap

object CheatAvailability {
    private val cache = ConcurrentHashMap<String, Boolean>()

    suspend fun hasCheats(gameFile: GameFile): Boolean {
        val gameId = gameFile.getGameId()
        val revision = gameFile.getRevision()
        val cacheKey = "$gameId:$revision"

        cache[cacheKey]?.let { return it }

        return withContext(Dispatchers.IO) {
            cache.getOrPut(cacheKey) {
                hasLocalCodes(gameId, revision)
            }
        }
    }

    fun invalidate(gameId: String, revision: Int) {
        cache.remove("$gameId:$revision")
    }

    @JvmStatic
    private external fun hasLocalCodes(gameId: String, revision: Int): Boolean
}
