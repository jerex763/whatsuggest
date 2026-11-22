package com.whatsuggest

import android.accessibilityservice.AccessibilityService
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.graphics.Rect
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.Toast
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Watches WhatsApp. When a chat is open, asks the PC for three reply drafts
 * and shows them above the message box. Tapping a draft writes it into the
 * input field. This service never presses send.
 */
class WhatsAppContactWatcher : AccessibilityService() {
    private lateinit var overlay: OverlayManager
    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private val handler = Handler(Looper.getMainLooper())
    private var refreshRunnable: Runnable? = null
    private var requestJob: Job? = null
    private var pollJob: Job? = null
    private var activeContact: String? = null
    private var dismissedContact: String? = null
    private var autoRequestedFor: String? = null
    private var composerWasMissing = false
    private var shownRevision: String? = null
    private var requestGen = 0
    private var lastAnchor: Rect? = null

    override fun onServiceConnected() {
        overlay = OverlayManager(this)
        overlay.onButtonTap = { onRefresh() }
        overlay.onButtonLongPress = { toggleMute() }
        overlay.onDismiss = { onDismissBar() }
        overlay.onPick = { text -> fillComposer(text) }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        if (!::overlay.isInitialized) return
        val pkg = event.packageName?.toString() ?: return
        if (pkg != WHATSAPP && pkg != WHATSAPP_BUSINESS) {
            leaveChat()
            return
        }
        if (refreshRunnable != null) return
        val runnable = Runnable {
            refreshRunnable = null
            refreshUi()
        }
        refreshRunnable = runnable
        handler.postDelayed(runnable, 120)
    }

    override fun onInterrupt() {}

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        requestJob?.cancel()
        pollJob?.cancel()
        if (::overlay.isInitialized) overlay.hideAll()
        super.onDestroy()
    }

    private fun refreshUi() {
        if (!Config.isConfigured(this)) {
            leaveChat()
            return
        }
        when (val presence = readPresence()) {
            Presence.Left -> leaveChat()
            is Presence.NamedOnly -> {
                // Still in the chat, but the message box is not on screen.
                composerWasMissing = true
                activeContact = presence.contact
                overlay.showButton()
                overlay.hideBar()
            }
            is Presence.Open -> {
                val cameBack = composerWasMissing
                composerWasMissing = false
                overlay.showButton()
                lastAnchor = presence.bounds
                val changed = presence.contact != activeContact
                if (changed) {
                    activeContact = presence.contact
                    shownRevision = null
                    autoRequestedFor = null
                    requestGen++
                    requestJob?.cancel()
                    stopPoll()
                    if (!shouldAutoShow(presence.contact)) overlay.hideBar()
                }
                if (shouldAutoShow(presence.contact) && autoRequestedFor != presence.contact) {
                    autoRequestedFor = presence.contact
                    loadAuto(presence.contact, presence.bounds)
                } else if (overlay.isBarShown()) {
                    overlay.moveBar(presence.bounds)
                } else if (
                    cameBack &&
                    autoRequestedFor == presence.contact &&
                    dismissedContact != presence.contact
                ) {
                    restoreFromCache(presence.contact, presence.bounds)
                } else {
                    overlay.moveButton(presence.bounds)
                }
            }
        }
    }

    private fun shouldAutoShow(contact: String): Boolean {
        return Config.isAutoSuggestEnabled(this) &&
            dismissedContact != contact &&
            !Config.isLocallyMuted(this, contact)
    }

    private fun loadAuto(contact: String, bounds: Rect) {
        val gen = ++requestGen
        overlay.showBarLoading(bounds)
        requestJob?.cancel()
        requestJob = scope.launch {
            val result = withContext(Dispatchers.IO) {
                SuggestRepository.getSuggestions(
                    this@WhatsAppContactWatcher,
                    contact,
                    refresh = false,
                    includeGroups = false
                )
            }
            if (gen != requestGen || activeContact != contact) return@launch
            if (applyResult(result)) startPoll(contact, gen)
        }
    }

    private fun onRefresh() {
        val presence = readPresence()
        val snap = presence as? Presence.Open
        if (snap == null) {
            toast("请先打开一个对话")
            return
        }
        if (dismissedContact == snap.contact) dismissedContact = null
        activeContact = snap.contact
        autoRequestedFor = snap.contact
        lastAnchor = snap.bounds
        val gen = ++requestGen
        overlay.showButton()
        overlay.showBarLoading(snap.bounds)
        requestJob?.cancel()
        requestJob = scope.launch {
            val result = withContext(Dispatchers.IO) {
                SuggestRepository.getSuggestions(
                    this@WhatsAppContactWatcher,
                    snap.contact,
                    refresh = true,
                    includeGroups = true
                )
            }
            if (gen != requestGen) return@launch
            if (applyResult(result)) startPoll(snap.contact, gen)
        }
    }

    private fun applyResult(result: SuggestResult): Boolean {
        val anchor = lastAnchor ?: return false
        when (result) {
            is SuggestResult.Ready -> {
                if (result.suggestions.isEmpty()) {
                    overlay.hideBar()
                    return false
                }
                shownRevision = result.revision
                overlay.showBarSuggestions(result.suggestions, anchor)
            }
            is SuggestResult.Hit -> {
                if (result.suggestions.isEmpty()) return true
                shownRevision = result.revision
                overlay.showBarSuggestions(result.suggestions, anchor)
            }
            is SuggestResult.Muted, is SuggestResult.Skipped -> {
                overlay.hideBar()
                return false
            }
            is SuggestResult.Empty -> overlay.showBarError("还没有同步到消息，请稍后再试", anchor)
            is SuggestResult.Outgoing -> {
                shownRevision = null
                overlay.hideBar()
            }
            is SuggestResult.Stale -> Unit
            is SuggestResult.Error -> overlay.showBarError(result.message, anchor)
        }
        return true
    }

    private fun startPoll(contact: String, gen: Int) {
        pollJob?.cancel()
        pollJob = scope.launch {
            while (isActive && gen == requestGen && activeContact == contact) {
                delay(5_000)
                if (gen != requestGen || activeContact != contact) break
                val cached = withContext(Dispatchers.IO) {
                    SuggestRepository.getCached(this@WhatsAppContactWatcher, contact)
                }
                if (gen != requestGen || activeContact != contact) break
                when (cached) {
                    is SuggestResult.Hit -> {
                        if (cached.revision != shownRevision && cached.suggestions.isNotEmpty()) {
                            shownRevision = cached.revision
                            lastAnchor?.let { overlay.showBarSuggestions(cached.suggestions, it) }
                        }
                    }
                    is SuggestResult.Outgoing -> {
                        // Hide drafts for an older message after she replies.
                        // Follow-up drafts for this outgoing message stay up.
                        if (shownRevision != null && cached.revision != null && cached.revision != shownRevision) {
                            shownRevision = null
                            overlay.hideBar()
                        }
                    }
                    is SuggestResult.Muted, is SuggestResult.Skipped -> overlay.hideBar()
                    else -> Unit
                }
            }
        }
    }

    private fun onDismissBar() {
        dismissedContact = activeContact
        requestGen++
        requestJob?.cancel()
        stopPoll()
        overlay.hideBar()
    }

    private fun restoreFromCache(contact: String, bounds: Rect) {
        val gen = requestGen
        scope.launch {
            val cached = withContext(Dispatchers.IO) {
                SuggestRepository.getCached(this@WhatsAppContactWatcher, contact)
            }
            if (gen != requestGen || activeContact != contact) return@launch
            if (cached is SuggestResult.Hit && cached.suggestions.isNotEmpty()) {
                shownRevision = cached.revision
                overlay.showBarSuggestions(cached.suggestions, bounds)
            }
        }
    }

    private fun toggleMute() {
        val fallback = readPresence()
        val name = activeContact
            ?: (fallback as? Presence.Open)?.contact
            ?: (fallback as? Presence.NamedOnly)?.contact
            ?: return
        val muted = !Config.isLocallyMuted(this, name)
        Config.setLocallyMuted(this, name, muted)
        toast(if (muted) "已静音 $name，长按 AI 可取消" else "已取消静音 $name")
        if (muted) {
            dismissedContact = name
            requestGen++
            stopPoll()
            overlay.hideBar()
        }
    }

    private fun leaveChat() {
        activeContact = null
        dismissedContact = null
        autoRequestedFor = null
        composerWasMissing = false
        shownRevision = null
        lastAnchor = null
        requestGen++
        requestJob?.cancel()
        stopPoll()
        if (::overlay.isInitialized) overlay.hideAll()
    }

    private fun stopPoll() {
        pollJob?.cancel()
        pollJob = null
    }

    /**
     * Writes [text] into WhatsApp's composer.
     * Uses ACTION_SET_TEXT, then clipboard paste. Never clicks the send button.
     */
    private fun fillComposer(text: String) {
        val root = rootInActiveWindow
        if (root == null) {
            copyToClipboard(text)
            toast("已复制，请粘贴到输入框后自己发送")
            return
        }
        val node = try {
            findComposer(root)
        } catch (e: Exception) {
            null
        }
        if (node == null) {
            root.recycle()
            copyToClipboard(text)
            toast("已复制，请粘贴到输入框后自己发送")
            return
        }
        try {
            node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
            val args = Bundle().apply {
                putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
            }
            if (node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) {
                toast("已填入输入框，请自己按发送")
                return
            }
            copyToClipboard(text)
            val pasted = node.performAction(AccessibilityNodeInfo.ACTION_PASTE)
            toast(if (pasted) "已粘贴到输入框，请自己按发送" else "已复制，请粘贴到输入框后自己发送")
        } finally {
            if (node !== root) node.recycle()
            root.recycle()
        }
    }

    private fun copyToClipboard(text: String) {
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText("suggestion", text))
    }

    private sealed class Presence {
        object Left : Presence()
        data class NamedOnly(val contact: String) : Presence()
        data class Open(val contact: String, val bounds: Rect) : Presence()
    }

    private fun readPresence(): Presence {
        val root = rootInActiveWindow ?: return Presence.Left
        val pkg = root.packageName?.toString()
        if (pkg != WHATSAPP && pkg != WHATSAPP_BUSINESS) {
            root.recycle()
            return Presence.Left
        }
        return try {
            val name = contactName(root) ?: return Presence.Left
            val bounds = composerBounds(root)
            if (bounds == null) Presence.NamedOnly(name) else Presence.Open(name, bounds)
        } catch (e: Exception) {
            Presence.Left
        } finally {
            root.recycle()
        }
    }

    private fun contactName(root: AccessibilityNodeInfo): String? {
        val nodes = root.findAccessibilityNodeInfosByViewId(Config.getNodeId(this))
        val name = nodes.firstOrNull()?.text?.toString()?.trim()?.takeIf { it.isNotEmpty() }
        nodes.forEach { if (it !== root) it.recycle() }
        return name
    }

    private fun composerBounds(root: AccessibilityNodeInfo): Rect? {
        val node = findComposer(root) ?: return null
        val rect = Rect()
        node.getBoundsInScreen(rect)
        if (node !== root) node.recycle()
        if (rect.width() <= 0 || rect.height() <= 0) return null
        return rect
    }

    private fun findComposer(root: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        val byId = root.findAccessibilityNodeInfosByViewId(Config.getEntryNodeId(this))
        val preferred = byId.firstOrNull { it.isEditable && !isSendControl(it) }
        byId.forEach { if (it !== preferred) it.recycle() }
        if (preferred != null) return preferred
        return findEditable(root)
    }

    private fun findEditable(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isEditable && !isSendControl(node)) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val found = findEditable(child)
            if (found != null) return found
            child.recycle()
        }
        return null
    }

    private fun isSendControl(node: AccessibilityNodeInfo): Boolean {
        val id = node.viewIdResourceName ?: return false
        return id.endsWith("/send") || id.endsWith("send_container")
    }

    private fun toast(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }

    companion object {
        private const val WHATSAPP = "com.whatsapp"
        private const val WHATSAPP_BUSINESS = "com.whatsapp.w4b"
    }
}
