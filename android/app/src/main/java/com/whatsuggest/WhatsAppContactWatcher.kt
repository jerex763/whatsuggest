package com.whatsuggest

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class WhatsAppContactWatcher : AccessibilityService() {
    private var overlayManager: OverlayManager? = null
    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var currentJob: Job? = null

    override fun onServiceConnected() {
        overlayManager = OverlayManager(this)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        val mgr = overlayManager ?: return
        val pkg = event.packageName?.toString() ?: return
        if (pkg != "com.whatsapp" && pkg != "com.whatsapp.w4b") {
            mgr.hideButton()
            return
        }
        val contactName = readContactName()
        if (contactName != null) {
            mgr.showButton { onSuggestTapped() }
        } else {
            mgr.hideButton()
        }
    }

    private fun readContactName(): String? {
        val root = rootInActiveWindow ?: return null
        val nodeId = Config.getNodeId(this)
        return try {
            val nodes = root.findAccessibilityNodeInfosByViewId(nodeId)
            try {
                nodes.firstOrNull()?.text?.toString()?.takeIf { it.isNotBlank() }
            } finally {
                nodes.forEach { it.recycle() }
            }
        } catch (e: Exception) {
            null
        } finally {
            root.recycle()
        }
    }

    private fun onSuggestTapped() {
        val mgr = overlayManager ?: return
        val contactName = readContactName()
        if (contactName == null) {
            mgr.showLoading()
            mgr.showError("请先打开一个对话")
            return
        }
        currentJob?.cancel()
        mgr.showLoading()
        currentJob = scope.launch {
            val result = SuggestRepository.getSuggestions(this@WhatsAppContactWatcher, contactName)
            when (result) {
                is SuggestResult.Success -> mgr.showSuggestions(result.suggestions)
                is SuggestResult.Error -> mgr.showError(result.message)
            }
        }
    }

    override fun onInterrupt() {}

    override fun onDestroy() {
        super.onDestroy()
        overlayManager?.hideButton()
        currentJob?.cancel()
    }
}
