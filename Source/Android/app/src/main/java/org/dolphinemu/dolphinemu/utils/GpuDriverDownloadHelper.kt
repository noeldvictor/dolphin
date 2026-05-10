// SPDX-License-Identifier: GPL-2.0-or-later

package org.dolphinemu.dolphinemu.utils

import android.content.Context
import org.json.JSONArray
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale

private const val ADRENO_TOOLS_RELEASES_URL =
    "https://api.github.com/repos/K11MCH1/AdrenoToolsDrivers/releases"
private const val MAX_TURNIP_OPTIONS = 24

data class DownloadableGpuDriver(
    val releaseName: String,
    val tagName: String,
    val publishedAt: String,
    val assetName: String,
    val downloadUrl: String,
    val sizeBytes: Long,
    val recommended: Boolean
) {
    val sizeLabel: String
        get() {
            val mib = sizeBytes / (1024.0 * 1024.0)
            return String.format(Locale.US, "%.1f MiB", mib)
        }
}

object GpuDriverDownloadHelper {
    fun fetchTurnipDrivers(): List<DownloadableGpuDriver> {
        val releasesJson = readUrl(ADRENO_TOOLS_RELEASES_URL)
        val releases = JSONArray(releasesJson)
        val drivers = ArrayList<DownloadableGpuDriver>()

        for (releaseIndex in 0 until releases.length()) {
            val release = releases.getJSONObject(releaseIndex)
            val assets = release.getJSONArray("assets")
            val releaseName = release.getString("name")
            val tagName = release.getString("tag_name")
            val publishedAt = release.optString("published_at")

            for (assetIndex in 0 until assets.length()) {
                val asset = assets.getJSONObject(assetIndex)
                val assetName = asset.getString("name")

                if (!isTurnipZip(assetName)) {
                    continue
                }

                drivers.add(
                    DownloadableGpuDriver(
                        releaseName = releaseName,
                        tagName = tagName,
                        publishedAt = publishedAt,
                        assetName = assetName,
                        downloadUrl = asset.getString("browser_download_url"),
                        sizeBytes = asset.optLong("size"),
                        recommended = false
                    )
                )
            }
        }

        val recommendedUrl = drivers.firstOrNull { isRecommendedTurnip(it.assetName) }?.downloadUrl

        return drivers
            .map { driver -> driver.copy(recommended = driver.downloadUrl == recommendedUrl) }
            .sortedWith(
                compareByDescending<DownloadableGpuDriver> { it.recommended }
                    .thenByDescending { it.publishedAt }
                    .thenBy { variantRank(it.assetName) }
            )
            .take(MAX_TURNIP_OPTIONS)
    }

    fun downloadDriver(context: Context, driver: DownloadableGpuDriver): File {
        val cacheDir = File(context.cacheDir, "gpu-driver-downloads")
        if (!cacheDir.exists() && !cacheDir.mkdirs()) {
            throw IOException("Unable to create GPU driver download cache")
        }

        val outputFile = File(cacheDir, safeFileName(driver.assetName))
        openConnection(driver.downloadUrl).useConnection { connection ->
            val responseCode = connection.responseCode
            if (responseCode !in 200..299) {
                throw IOException("GPU driver download failed: HTTP $responseCode")
            }

            connection.inputStream.use { input ->
                outputFile.outputStream().use { output ->
                    input.copyTo(output)
                }
            }
        }

        return outputFile
    }

    private fun readUrl(url: String): String {
        openConnection(url).useConnection { connection ->
            val responseCode = connection.responseCode
            if (responseCode !in 200..299) {
                throw IOException("GitHub release lookup failed: HTTP $responseCode")
            }

            return connection.inputStream.bufferedReader().use { it.readText() }
        }
    }

    private fun openConnection(url: String): HttpURLConnection {
        return (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 15000
            readTimeout = 30000
            instanceFollowRedirects = true
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("User-Agent", "Dolphin-Thor-Experiment")
        }
    }

    private fun isTurnipZip(assetName: String): Boolean {
        val lowerName = assetName.lowercase(Locale.US)
        return lowerName.endsWith(".zip") && lowerName.contains("turnip")
    }

    private fun isRecommendedTurnip(assetName: String): Boolean {
        val lowerName = assetName.lowercase(Locale.US)
        val variantTerms = listOf("a8xx", "gmem", "sysmem", "profiled", "autotuner", "perf", "prefer")
        return isTurnipZip(assetName) && variantTerms.none { lowerName.contains(it) }
    }

    private fun variantRank(assetName: String): Int {
        val lowerName = assetName.lowercase(Locale.US)
        return when {
            isRecommendedTurnip(assetName) -> 0
            lowerName.contains("sysmem") -> 1
            lowerName.contains("gmem") -> 2
            lowerName.contains("a8xx") -> 3
            else -> 4
        }
    }

    private fun safeFileName(fileName: String): String {
        return fileName.replace(Regex("[^A-Za-z0-9._-]"), "_")
    }

    private inline fun <T> HttpURLConnection.useConnection(block: (HttpURLConnection) -> T): T {
        return try {
            block(this)
        } finally {
            disconnect()
        }
    }
}
