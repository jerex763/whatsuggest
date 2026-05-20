package com.whatsuggest

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class WhatsAppContactWatcher : AccessibilityService() {
    private lateinit var overlayManager: OverlayManager
    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var currentJob: Job? = null

    override fun onServiceConnected() {
        overlayManager = OverlayManager(this)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        val pkg = event.packageName?.toString() ?: return
        if (pkg != "com.whatsapp" && pkg != "com.whatsapp.w4b") {
            overlayManager.hideButton(); return
        }
        val contactName = readContactName()
        if (contactName != null) overlayManager.showButton { onSuggestTapped() }
        else overlayManager.hideButton()
    }

    private fun readContactName(): String? {
        val root = rootInActiveWindow ?: return null
        return try {
            val nodes = root.findAccessibilityNodeInfosByViewId(Config.getNodeId(this))
            val name = nodes.firstOrNull()?.text?.toString()?.takeIf { it.isNotBlank() }
            nodes.forEach { it.recycle() }
            root.recycle()
            name
        } catch (e: Exception) { null }
    }

    private fun onSuggestTapped() {
        val contactName = readContactName() ?: run {
            overlayManager.showLoading()
            overlayManager.showError("请先打开一个对话")
            return
        }
        currentJob?.cancel()
        overlayManager.showLoading()
        currentJob = scope.launch {
            val result = withContext(Dispatchers.IO) {
                SuggestRepository.getSuggestions(this@WhatsAppContactWatcher, contactName)
            }
            when (result) {
                is SuggestResult.Success -> overlayManager.showSuggestions(result.suggestions)
                is SuggestResult.Error -> overlayManager.showError(result.message)
            }
        }
    }

    override fun onInterrupt() {}

    override fun onDestroy() {
        super.onDestroy()
        overlayManager.hideButton()
        currentJob?.cancel()
    }
}
