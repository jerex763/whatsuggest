package com.whatsuggest

import android.content.ComponentName
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class SetupWizardActivity : AppCompatActivity() {
    private var step = 1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_setup_wizard)
        showStep(1)
    }

    override fun onResume() {
        super.onResume()
        if (step == 1 && isAccessibilityEnabled()) showStep(2)
    }

    private fun showStep(s: Int) {
        step = s
        val tvStep = findViewById<TextView>(R.id.tvStep)
        val tvTitle = findViewById<TextView>(R.id.tvTitle)
        val tvDesc = findViewById<TextView>(R.id.tvDescription)
        val etUrl = findViewById<EditText>(R.id.etServerUrl)
        val etKey = findViewById<EditText>(R.id.etApiKey)
        val tvTest = findViewById<TextView>(R.id.tvTestResult)
        val btnAction = findViewById<Button>(R.id.btnAction)
        tvTest.visibility = View.GONE

        when (s) {
            1 -> {
                tvStep.text = "步骤 1 / 2"
                tvTitle.text = "开启无障碍权限"
                tvDesc.text = "WhatSuggest 需要无障碍权限来检测当前打开的 WhatsApp 对话。\n\n点击下方按钮，找到 WhatSuggest，开启开关。"
                etUrl.visibility = View.GONE; etKey.visibility = View.GONE
                btnAction.text = "去开启权限"
                btnAction.setOnClickListener { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
            }
            2 -> {
                tvStep.text = "步骤 2 / 2"
                tvTitle.text = "配置服务器"
                tvDesc.text = "输入你的 PC 服务器地址和 API Key。"
                etUrl.visibility = View.VISIBLE; etKey.visibility = View.VISIBLE
                etUrl.setText(Config.getServerUrl(this))
                etKey.setText(Config.getApiKey(this))
                btnAction.text = "测试并保存"
                btnAction.setOnClickListener {
                    val url = etUrl.text.toString().trim()
                    val key = etKey.text.toString().trim()
                    if (url.isEmpty() || key.isEmpty()) {
                        tvTest.text = "请填写所有字段"; tvTest.visibility = View.VISIBLE; return@setOnClickListener
                    }
                    btnAction.isEnabled = false
                    tvTest.text = "测试中..."; tvTest.visibility = View.VISIBLE
                    CoroutineScope(Dispatchers.IO).launch {
                        val ok = SuggestRepository.testConnection(url, key)
                        withContext(Dispatchers.Main) {
                            btnAction.isEnabled = true
                            if (ok) {
                                Config.saveServerConfig(this@SetupWizardActivity, url, key)
                                tvTest.text = "✓ 连接成功！"
                                btnAction.text = "完成"
                                btnAction.setOnClickListener {
                                    startActivity(Intent(this@SetupWizardActivity, MainActivity::class.java))
                                    finish()
                                }
                            } else {
                                tvTest.text = "✗ 连接失败。检查服务器地址、API Key 和 Tailscale 是否开启。"
                            }
                        }
                    }
                }
            }
        }
    }

    private fun isAccessibilityEnabled(): Boolean {
        val enabled = Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: return false
        val component = ComponentName(this, WhatsAppContactWatcher::class.java)
        return enabled.split(":").any { ComponentName.unflattenFromString(it) == component }
    }
}
