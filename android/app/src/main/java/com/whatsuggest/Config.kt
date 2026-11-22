package com.whatsuggest

import android.content.Context

object Config {
    private const val PREFS = "whatsuggest_prefs"
    private const val KEY_SERVER_URL = "server_url"
    private const val KEY_API_KEY = "api_key"
    private const val KEY_NODE_ID = "wa_node_id"
    private const val KEY_ENTRY_NODE_ID = "wa_entry_node_id"
    private const val KEY_AUTO = "auto_suggest"
    private const val KEY_MUTED = "local_muted"
    private const val DEFAULT_NODE_ID = "com.whatsapp:id/conversation_contact_name"
    private const val DEFAULT_ENTRY_NODE_ID = "com.whatsapp:id/entry"

    fun getServerUrl(ctx: Context): String =
        prefs(ctx).getString(KEY_SERVER_URL, "") ?: ""

    fun getApiKey(ctx: Context): String =
        prefs(ctx).getString(KEY_API_KEY, "") ?: ""

    fun getNodeId(ctx: Context): String =
        prefs(ctx).getString(KEY_NODE_ID, DEFAULT_NODE_ID) ?: DEFAULT_NODE_ID

    fun getEntryNodeId(ctx: Context): String =
        prefs(ctx).getString(KEY_ENTRY_NODE_ID, DEFAULT_ENTRY_NODE_ID) ?: DEFAULT_ENTRY_NODE_ID

    fun isAutoSuggestEnabled(ctx: Context): Boolean =
        prefs(ctx).getBoolean(KEY_AUTO, true)

    fun setAutoSuggestEnabled(ctx: Context, enabled: Boolean) {
        prefs(ctx).edit().putBoolean(KEY_AUTO, enabled).apply()
    }

    fun saveServerConfig(ctx: Context, serverUrl: String, apiKey: String) {
        prefs(ctx).edit()
            .putString(KEY_SERVER_URL, serverUrl.trimEnd('/'))
            .putString(KEY_API_KEY, apiKey)
            .apply()
    }

    fun isConfigured(ctx: Context): Boolean =
        getServerUrl(ctx).isNotEmpty() && getApiKey(ctx).isNotEmpty()

    fun isLocallyMuted(ctx: Context, name: String): Boolean =
        getLocalMutes(ctx).any { norm(it) == norm(name) }

    fun setLocallyMuted(ctx: Context, name: String, muted: Boolean) {
        val next = getLocalMutes(ctx).toMutableSet()
        val existing = next.firstOrNull { norm(it) == norm(name) }
        if (muted) {
            if (existing == null && name.isNotBlank()) next.add(name.trim())
        } else if (existing != null) {
            next.remove(existing)
        }
        prefs(ctx).edit().putStringSet(KEY_MUTED, next).apply()
    }

    fun getLocalMutes(ctx: Context): Set<String> =
        prefs(ctx).getStringSet(KEY_MUTED, emptySet())?.toSet() ?: emptySet()

    fun clearLocalMutes(ctx: Context) {
        prefs(ctx).edit().remove(KEY_MUTED).apply()
    }

    private fun prefs(ctx: Context) =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private fun norm(value: String) = value.trim().lowercase()
}
