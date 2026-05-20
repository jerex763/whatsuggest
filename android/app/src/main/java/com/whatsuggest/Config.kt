package com.whatsuggest

import android.content.Context

object Config {
    private const val PREFS = "whatsuggest_prefs"
    private const val KEY_SERVER_URL = "server_url"
    private const val KEY_API_KEY = "api_key"
    private const val KEY_NODE_ID = "wa_node_id"
    private const val DEFAULT_NODE_ID = "com.whatsapp:id/conversation_contact_name"

    fun getServerUrl(ctx: Context): String =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_SERVER_URL, "") ?: ""

    fun getApiKey(ctx: Context): String =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_API_KEY, "") ?: ""

    fun getNodeId(ctx: Context): String =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_NODE_ID, DEFAULT_NODE_ID) ?: DEFAULT_NODE_ID

    fun saveServerConfig(ctx: Context, serverUrl: String, apiKey: String) {
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(KEY_SERVER_URL, serverUrl.trimEnd('/'))
            .putString(KEY_API_KEY, apiKey)
            .apply()
    }

    fun isConfigured(ctx: Context): Boolean =
        getServerUrl(ctx).isNotEmpty() && getApiKey(ctx).isNotEmpty()
}
