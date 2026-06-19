package com.whatsuggest

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

sealed class SuggestResult {
    data class Success(val suggestions: List<String>) : SuggestResult()
    data class Error(val message: String) : SuggestResult()
}

object SuggestRepository {
    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(90, TimeUnit.SECONDS)
        .build()

    suspend fun getSuggestions(context: Context, contactName: String): SuggestResult {
        val serverUrl = Config.getServerUrl(context)
        val apiKey = Config.getApiKey(context)
        if (serverUrl.isEmpty() || apiKey.isEmpty()) {
            return SuggestResult.Error("服务器未配置，请检查设置")
        }
        val body = JSONObject().put("contact", contactName).toString()
            .toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("$serverUrl/suggest")
            .addHeader("X-API-Key", apiKey)
            .post(body)
            .build()
        return withContext(Dispatchers.IO) {
            try {
                client.newCall(request).execute().use { response ->
                    when (response.code) {
                        200 -> {
                            val bodyStr = response.body?.string()
                                ?: return@withContext SuggestResult.Error("服务器返回空响应")
                            val json = JSONObject(bodyStr)
                            val arr = json.getJSONArray("suggestions")
                            val list = (0 until arr.length()).map { arr.getString(it) }
                            SuggestResult.Success(list)
                        }
                        401 -> SuggestResult.Error("认证失败，请检查 API Key")
                        429 -> SuggestResult.Error("服务繁忙，请稍等后重试")
                        504 -> SuggestResult.Error("生成超时，请重试")
                        else -> SuggestResult.Error("服务器错误 (${response.code})")
                    }
                }
            } catch (e: java.net.ConnectException) {
                SuggestResult.Error("无法连接，请检查 Tailscale 是否开启")
            } catch (e: java.net.SocketTimeoutException) {
                SuggestResult.Error("响应超时，请重试")
            } catch (e: IOException) {
                SuggestResult.Error("网络错误：${e.message}")
            }
        }
    }

    fun testConnection(serverUrl: String, apiKey: String): Boolean {
        val request = Request.Builder()
            .url("$serverUrl/health")
            .addHeader("X-API-Key", apiKey)
            .get().build()
        return try {
            client.newCall(request).execute().isSuccessful
        } catch (e: Exception) {
            false
        }
    }
}
