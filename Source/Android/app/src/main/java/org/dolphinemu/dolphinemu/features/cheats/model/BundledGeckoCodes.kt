// SPDX-License-Identifier: GPL-2.0-or-later

package org.dolphinemu.dolphinemu.features.cheats.model

import org.dolphinemu.dolphinemu.features.cheats.model.Cheat.Companion.TRY_SET_SUCCESS
import org.dolphinemu.dolphinemu.utils.DirectoryInitialization
import java.io.File
import java.util.zip.ZipFile

object BundledGeckoCodes {
    private const val ZIP_NAME = "GeckoCodes.zip"

    private val zipLock = Any()
    private var zipFile: ZipFile? = null

    fun hasCodes(gameTdbId: String): Boolean =
        gameTdbId.isNotEmpty() && getZipFile()?.getEntry(entryName(gameTdbId)) != null

    fun loadCodes(gameTdbId: String): Array<GeckoCheat>? {
        if (gameTdbId.isEmpty()) {
            return null
        }

        val zip = getZipFile() ?: return null
        val entry = zip.getEntry(entryName(gameTdbId)) ?: return null
        val text = zip.getInputStream(entry).bufferedReader(Charsets.UTF_8).use { it.readText() }
        return parseCodes(text)
    }

    private fun getZipFile(): ZipFile? =
        synchronized(zipLock) {
            zipFile ?: runCatching {
                ZipFile(File(DirectoryInitialization.getSysDirectory(), ZIP_NAME))
            }.getOrNull()?.also { zipFile = it }
        }

    private fun parseCodes(text: String): Array<GeckoCheat> {
        val codes = mutableListOf<GeckoCheat>()
        var name = ""
        var creator = ""
        val notes = mutableListOf<String>()
        val codeLines = mutableListOf<String>()

        fun flushCode() {
            if (name.isNotEmpty() && codeLines.isNotEmpty()) {
                val cheat = GeckoCheat()
                val result = cheat.setCheat(
                    name,
                    creator,
                    notes.joinToString("\n"),
                    codeLines.joinToString("\n")
                )
                if (result == TRY_SET_SUCCESS) {
                    codes.add(cheat)
                }
            }

            name = ""
            creator = ""
            notes.clear()
            codeLines.clear()
        }

        text.lineSequence().drop(3).forEach { rawLine ->
            val line = rawLine.trim()
            if (line.isEmpty()) {
                flushCode()
            } else if (name.isEmpty()) {
                name = line.substringBefore('[').trim()
                creator = line.substringAfter('[', "").substringBefore(']').trim()
            } else if (looksLikeCodeLine(line)) {
                codeLines.add(line)
            } else {
                notes.add(line)
            }
        }
        flushCode()

        return codes.toTypedArray()
    }

    private fun looksLikeCodeLine(line: String): Boolean {
        val parts = line.split(Regex("\\s+"), limit = 3)
        return parts.size >= 2 && parts[0].length == 8 && parts[1].length == 8
    }

    private fun entryName(gameTdbId: String): String = "${gameTdbId.uppercase()}.txt"
}
