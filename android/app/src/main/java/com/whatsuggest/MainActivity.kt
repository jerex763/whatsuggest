package com.whatsuggest

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!Config.isConfigured(this)) {
            startActivity(Intent(this, SetupWizardActivity::class.java))
        }
        finish()
    }
}
