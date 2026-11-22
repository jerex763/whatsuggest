package com.whatsuggest

import android.content.Context
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

sealed class SuggestResult {
    data class Ready(val suggestions: List<String>, val revision: String?, val cached: Boolean) : SuggestResult()
    data class Hit(val suggestions: List<String>, val revision: String?) : SuggestResult()
    data class Outgoing(val revision: String?) : SuggestResult()
    object Stale : SuggestResult()
    object Muted : SuggestResult()
    object Skipped : SuggestResult()
    object Empty : SuggestResult()
    data class Error(val message: String) : SuggestResult()
}

object SuggestRepository {
    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(90, TimeUnit.SECONDS)
        .build()

    private val cacheClient = client.newBuilder()
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    suspend fun getSuggestions(
        context: Context,
        contactName: String,
        refresh: Boolean,
        includeGroups: Boolean
    ): SuggestResult {
        val serverUrl = Config.getServerUrl(context)
        val apiKey = Config.getApiKey(context)
        if (serverUrl.isEmpty() || apiKey.isEmpty()) {
            return SuggestResult.Error("服务器未配置，请检查设置")
        }
        val body = JSONObject()
            .put("contact", contactName)
            .put("refresh", refresh)
            .put("include_groups", includeGroups)
            .toString()
            .toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("$serverUrl/suggest")
            .addHeader("X-API-Key", apiKey)
            .post(body)
            .build()
        return execute(client, request)
    }

    suspend fun getCached(context: Context, contactName: String): SuggestResult {
        val serverUrl = Config.getServerUrl(context)
        val apiKey = Config.getApiKey(context)
        if (serverUrl.isEmpty() || apiKey.isEmpty()) {
            return SuggestResult.Error("服务器未配置，请检查设置")
        }
        val url = "$serverUrl/suggest/cached".toHttpUrlOrNull()?.newBuilder()
            ?.addQueryParameter("contact", contactName)
            ?.build()
            ?: return SuggestResult.Error("服务器地址无效")
        val request = Request.Builder()
            .url(url)
            .addHeader("X-API-Key", apiKey)
            .get()
            .build()
        return execute(cacheClient, request)
    }

    fun testConnection(serverUrl: String, apiKey: String): Boolean {
        val request = Request.Builder()
            .url("${serverUrl.trimEnd('/')}/health")
            .addHeader("X-API-Key", apiKey)
            .get()
            .build()
        return try {
            client.newCall(request).execute().isSuccessful
        } catch (e: Exception) {
            false
        }
    }

    private fun execute(http: OkHttpClient, request: Request): SuggestResult {
        return try {
            http.newCall(request).execute().use { response ->
                val raw = response.body?.string().orEmpty()
                parse(response.code, raw)
            }
        } catch (e: java.net.ConnectException) {
            SuggestResult.Error("无法连接，请检查 Tailscale 是否开启")
        } catch (e: java.net.SocketTimeoutException) {
            SuggestResult.Error("响应超时，请重试")
        } catch (e: IOException) {
            SuggestResult.Error("网络错误：${e.message}")
        }
    }

    private fun parse(code: Int, raw: String): SuggestResult {
        if (code == 401) return SuggestResult.Error("认证失败，请检查 API Key")
        if (code == 429) return SuggestResult.Error("服务繁忙，请稍等后重试")
        if (code == 504) return SuggestResult.Error("生成超时，请重试")
        val json = try {
            JSONObject(raw)
        } catch (e: Exception) {
            return SuggestResult.Error(if (code == 200) "解析失败，请重试" else "服务器错误 ($code)")
        }
        return when (json.optString("status")) {
            "ready" -> SuggestResult.Ready(
                readSuggestions(json),
                json.optString("revision").ifBlank { null },
                json.optBoolean("cached")
            )
            "hit" -> SuggestResult.Hit(
                readSuggestions(json),
                json.optString("revision").ifBlank { null }
            )
            "miss" -> if (json.optString("reason") == "outgoing") {
                SuggestResult.Outgoing(json.optString("revision").ifBlank { null })
            } else {
                SuggestResult.Stale
            }
            "muted" -> SuggestResult.Muted
            "skipped" -> SuggestResult.Skipped
            "empty" -> SuggestResult.Empty
            "not_found" -> SuggestResult.Error("找不到这个联系人。请在电脑的 config.yaml 里加上电话上显示的名字")
            else -> {
                val detail = json.optString("reason").ifBlank { json.optString("error") }
                when (code) {
                    404 -> SuggestResult.Error("找不到这个联系人。请在电脑的 config.yaml 里加上电话上显示的名字")
                    200 -> SuggestResult.Error(detail.ifBlank { "生成失败，请重试" })
                    else -> SuggestResult.Error(detail.ifBlank { "服务器错误 ($code)" })
                }
            }
        }
    }

    private fun readSuggestions(json: JSONObject): List<String> {
        val arr = json.optJSONArray("suggestions") ?: return emptyList()
        return (0 until arr.length()).mapNotNull { index ->
            arr.optString(index).takeIf { it.isNotBlank() }
        }
    }
}
