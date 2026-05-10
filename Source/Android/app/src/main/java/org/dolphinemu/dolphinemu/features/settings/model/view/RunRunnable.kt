// SPDX-License-Identifier: GPL-2.0-or-later

package org.dolphinemu.dolphinemu.features.settings.model.view

import android.content.Context
import org.dolphinemu.dolphinemu.NativeLibrary
import org.dolphinemu.dolphinemu.features.settings.model.AbstractSetting

class RunRunnable : SettingsItem {
    val alertText: Int
    val toastTextAfterRun: Int
    private val worksDuringEmulation: Boolean
    val runnable: Runnable

    constructor(
        context: Context,
        titleId: Int,
        descriptionId: Int,
        alertText: Int,
        toastTextAfterRun: Int,
        worksDuringEmulation: Boolean,
        runnable: Runnable
    ) : super(context, titleId, descriptionId) {
        this.alertText = alertText
        this.toastTextAfterRun = toastTextAfterRun
        this.worksDuringEmulation = worksDuringEmulation
        this.runnable = runnable
    }

    constructor(
        title: CharSequence,
        description: CharSequence,
        alertText: Int,
        toastTextAfterRun: Int,
        worksDuringEmulation: Boolean,
        runnable: Runnable
    ) : super(title, description) {
        this.alertText = alertText
        this.toastTextAfterRun = toastTextAfterRun
        this.worksDuringEmulation = worksDuringEmulation
        this.runnable = runnable
    }

    override val type: Int = TYPE_RUN_RUNNABLE

    override val setting: AbstractSetting? = null

    override val isEditable: Boolean
        get() = worksDuringEmulation || NativeLibrary.IsUninitialized()
}
