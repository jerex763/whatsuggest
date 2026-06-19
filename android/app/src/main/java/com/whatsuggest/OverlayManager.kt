package com.whatsuggest

import android.accessibilityservice.AccessibilityService
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.graphics.PixelFormat
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

class OverlayManager(private val service: AccessibilityService) {
    private val wm = service.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private var buttonView: View? = null
    private var popupView: View? = null

    private fun overlayParams(w: Int, h: Int) = WindowManager.LayoutParams(
        w, h,
        WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
        PixelFormat.TRANSLUCENT
    )

    fun showButton(onTap: () -> Unit) {
        if (buttonView != null) return
        val view = LayoutInflater.from(service).inflate(R.layout.overlay_button, null)
        val params = overlayParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT
        ).apply { gravity = Gravity.BOTTOM or Gravity.END; x = 24; y = 200 }
        view.findViewById<Button>(R.id.btnSuggest).setOnClickListener { onTap() }
        try {
            wm.addView(view, params)
            buttonView = view
        } catch (e: Exception) {
            return
        }
    }

    fun hideButton() {
        buttonView?.let {
            try {
                wm.removeView(it)
            } catch (e: Exception) {
                buttonView = null
                return
            }
            buttonView = null
        }
        hidePopup()
    }

    fun showLoading() {
        dismissPopupView()
        val view = LayoutInflater.from(service).inflate(R.layout.suggestion_popup, null)
        view.findViewById<TextView>(R.id.tvLoading).visibility = View.VISIBLE
        view.findViewById<LinearLayout>(R.id.llSuggestions).visibility = View.GONE
        view.findViewById<TextView>(R.id.tvError).visibility = View.GONE
        val params = overlayParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT
        ).apply { gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL; y = 280 }
        try {
            wm.addView(view, params)
            popupView = view
        } catch (e: Exception) {
            return
        }
    }

    fun showSuggestions(suggestions: List<String>) {
        val view = popupView ?: return
        view.findViewById<TextView>(R.id.tvLoading).visibility = View.GONE
        view.findViewById<TextView>(R.id.tvError).visibility = View.GONE
        val ll = view.findViewById<LinearLayout>(R.id.llSuggestions)
        ll.visibility = View.VISIBLE
        listOf(R.id.btnSuggestion1, R.id.btnSuggestion2, R.id.btnSuggestion3)
            .forEachIndexed { i, id ->
                val text = suggestions.getOrElse(i) { "" }
                val btn = view.findViewById<Button>(id)
                if (text.isBlank()) { btn.visibility = View.GONE; return@forEachIndexed }
                btn.text = text
                btn.setOnClickListener {
                    val cm = service.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                    cm.setPrimaryClip(ClipData.newPlainText("suggestion", text))
                    Toast.makeText(service, "已复制", Toast.LENGTH_SHORT).show()
                    hidePopup()
                }
            }
    }

    fun showError(message: String) {
        val view = popupView ?: return
        view.findViewById<TextView>(R.id.tvLoading).visibility = View.GONE
        view.findViewById<LinearLayout>(R.id.llSuggestions).visibility = View.GONE
        view.findViewById<TextView>(R.id.tvError).apply {
            text = message; visibility = View.VISIBLE
        }
    }

    fun hidePopup() = dismissPopupView()

    private fun dismissPopupView() {
        popupView?.let {
            try {
                wm.removeView(it)
            } catch (e: Exception) {
                popupView = null
                return
            }
            popupView = null
        }
    }
}
