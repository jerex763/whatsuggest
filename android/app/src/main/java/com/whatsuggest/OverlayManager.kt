package com.whatsuggest

import android.accessibilityservice.AccessibilityService
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Rect
import android.text.TextUtils
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.content.Context

/**
 * Floating refresh button plus the slim suggestion bar that sits just above
 * WhatsApp's message box. Taps are delivered to the service; this class never
 * presses WhatsApp's send button.
 */
class OverlayManager(private val service: AccessibilityService) {
    private val wm = service.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private var buttonView: View? = null
    private var buttonParams: WindowManager.LayoutParams? = null
    private var barView: View? = null
    private var barParams: WindowManager.LayoutParams? = null
    private var anchor: Rect? = null

    var onButtonTap: (() -> Unit)? = null
    var onButtonLongPress: (() -> Unit)? = null
    var onDismiss: (() -> Unit)? = null
    var onPick: ((String) -> Unit)? = null

    fun showButton() {
        if (buttonView != null) return
        val view = LayoutInflater.from(service).inflate(R.layout.overlay_button, null)
        val params = overlayParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT
        ).apply { gravity = Gravity.TOP or Gravity.START }
        view.findViewById<Button>(R.id.btnSuggest).setOnClickListener { onButtonTap?.invoke() }
        view.findViewById<Button>(R.id.btnSuggest).setOnLongClickListener {
            onButtonLongPress?.invoke()
            true
        }
        if (!addView(view, params)) return
        buttonView = view
        buttonParams = params
        anchor?.let { moveButton(it) }
    }

    fun hideButton() {
        remove(buttonView)
        buttonView = null
        buttonParams = null
    }

    fun isBarShown(): Boolean = barView != null

    fun showBarLoading(bounds: Rect) {
        val view = ensureBar() ?: return
        anchor = Rect(bounds)
        view.findViewById<TextView>(R.id.tvBarStatus).apply {
            text = "正在想…"
            setTextColor(Color.WHITE)
            visibility = View.VISIBLE
        }
        view.findViewById<View>(R.id.scrollSuggestions).visibility = View.GONE
        placeBar(bounds)
        moveButton(bounds)
    }

    fun showBarSuggestions(suggestions: List<String>, bounds: Rect) {
        val view = ensureBar() ?: return
        anchor = Rect(bounds)
        view.findViewById<TextView>(R.id.tvBarStatus).visibility = View.GONE
        view.findViewById<View>(R.id.scrollSuggestions).visibility = View.VISIBLE
        val chips = view.findViewById<LinearLayout>(R.id.llChips)
        chips.removeAllViews()
        suggestions.filter { it.isNotBlank() }.take(3).forEach { text ->
            chips.addView(chip(text))
        }
        placeBar(bounds)
        moveButton(bounds)
    }

    fun showBarError(message: String, bounds: Rect) {
        val view = ensureBar() ?: return
        anchor = Rect(bounds)
        view.findViewById<TextView>(R.id.tvBarStatus).apply {
            text = message
            setTextColor(0xFFFFCDD2.toInt())
            visibility = View.VISIBLE
        }
        view.findViewById<View>(R.id.scrollSuggestions).visibility = View.GONE
        placeBar(bounds)
        moveButton(bounds)
    }

    fun moveBar(bounds: Rect) {
        anchor = Rect(bounds)
        if (barView == null) return
        placeBar(bounds)
        moveButton(bounds)
    }

    fun moveButton(bounds: Rect) {
        anchor = Rect(bounds)
        val view = buttonView ?: return
        val params = buttonParams ?: return
        val barHeight = if (barView != null) (barView?.height ?: dp(48)) + dp(8) else 0
        params.x = (bounds.right - dp(56)).coerceAtLeast(0)
        params.y = (bounds.top - dp(64) - barHeight).coerceAtLeast(0)
        update(view, params)
    }

    fun hideBar() {
        remove(barView)
        barView = null
        barParams = null
        anchor?.let { moveButton(it) }
    }

    fun hideAll() {
        hideBar()
        hideButton()
        anchor = null
    }

    private fun ensureBar(): View? {
        barView?.let { return it }
        val view = LayoutInflater.from(service).inflate(R.layout.suggestion_bar, null)
        val params = overlayParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT
        ).apply { gravity = Gravity.TOP or Gravity.START }
        view.findViewById<View>(R.id.btnDismissBar).setOnClickListener { onDismiss?.invoke() }
        if (!addView(view, params)) return null
        barView = view
        barParams = params
        return view
    }

    private fun placeBar(bounds: Rect) {
        val view = barView ?: return
        val params = barParams ?: return
        params.x = bounds.left.coerceAtLeast(0)
        params.width = bounds.width().coerceAtLeast(dp(180))
        params.y = (bounds.top - dp(52)).coerceAtLeast(0)
        update(view, params)
        view.post {
            val height = view.height.coerceAtLeast(dp(40))
            params.y = (bounds.top - height - dp(6)).coerceAtLeast(0)
            update(view, params)
            moveButton(bounds)
        }
    }

    private fun chip(text: String): TextView {
        return TextView(service).apply {
            this.text = text.replace("\n", " ")
            setTextColor(Color.WHITE)
            textSize = 13f
            maxLines = 2
            ellipsize = TextUtils.TruncateAt.END
            maxWidth = dp(220)
            setPadding(dp(10), dp(6), dp(10), dp(6))
            setBackgroundColor(0x33FFFFFF)
            setOnClickListener { onPick?.invoke(text) }
            val gap = dp(6)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { marginEnd = gap }
        }
    }

    private fun overlayParams(width: Int, height: Int) = WindowManager.LayoutParams(
        width,
        height,
        WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
        PixelFormat.TRANSLUCENT
    )

    private fun addView(view: View, params: WindowManager.LayoutParams): Boolean {
        return try {
            wm.addView(view, params)
            true
        } catch (e: Exception) {
            false
        }
    }

    private fun update(view: View, params: WindowManager.LayoutParams) {
        try {
            wm.updateViewLayout(view, params)
        } catch (e: Exception) {
            // The window may already have been removed.
        }
    }

    private fun remove(view: View?) {
        if (view == null) return
        try {
            wm.removeView(view)
        } catch (e: Exception) {
            // Already detached.
        }
    }

    private fun dp(value: Int): Int =
        (value * service.resources.displayMetrics.density).toInt()
}
