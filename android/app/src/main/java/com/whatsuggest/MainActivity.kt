package com.whatsuggest

import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!Config.isConfigured(this)) {
            startActivity(Intent(this, SetupWizardActivity::class.java))
            finish()
            return
        }
        setContentView(R.layout.activity_main)
        val auto = findViewById<CheckBox>(R.id.cbAutoSuggest)
        val url = findViewById<EditText>(R.id.etServerUrl)
        val key = findViewById<EditText>(R.id.etApiKey)
        val result = findViewById<TextView>(R.id.tvSettingsResult)
        auto.isChecked = Config.isAutoSuggestEnabled(this)
        auto.setOnCheckedChangeListener { _, checked ->
            Config.setAutoSuggestEnabled(this, checked)
        }
        url.setText(Config.getServerUrl(this))
        key.setText(Config.getApiKey(this))
        findViewById<Button>(R.id.btnSaveSettings).setOnClickListener {
            val server = url.text.toString().trim()
            val apiKey = key.text.toString().trim()
            if (server.isEmpty() || apiKey.isEmpty()) {
                result.text = "请填写服务器地址和 API Key"
                result.visibility = View.VISIBLE
                return@setOnClickListener
            }
            result.text = "测试中..."
            result.visibility = View.VISIBLE
            CoroutineScope(Dispatchers.IO).launch {
                val ok = SuggestRepository.testConnection(server, apiKey)
                withContext(Dispatchers.Main) {
                    if (ok) {
                        Config.saveServerConfig(this@MainActivity, server, apiKey)
                        result.text = "已保存，连接成功"
                    } else {
                        result.text = "连接失败。检查地址、API Key 和 Tailscale。"
                    }
                }
            }
        }
        findViewById<Button>(R.id.btnClearMutes).setOnClickListener {
            Config.clearLocalMutes(this)
            refreshMutes()
        }
        findViewById<Button>(R.id.btnAccessibility).setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }
        refreshMutes()
    }

    override fun onResume() {
        super.onResume()
        if (!Config.isConfigured(this)) return
        refreshMutes()
    }

    private fun refreshMutes() {
        val view = findViewById<TextView>(R.id.tvMuted) ?: return
        val names = Config.getLocalMutes(this)
        view.text = if (names.isEmpty()) "无" else names.sorted().joinToString("\n")
    }
}
