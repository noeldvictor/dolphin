// SPDX-License-Identifier: GPL-2.0-or-later

package org.dolphinemu.dolphinemu.features.input.model

import android.view.KeyEvent
import android.view.MotionEvent
import android.widget.Toast
import org.dolphinemu.dolphinemu.NativeLibrary
import org.dolphinemu.dolphinemu.R
import org.dolphinemu.dolphinemu.features.settings.model.BooleanSetting
import org.dolphinemu.dolphinemu.features.settings.model.FloatSetting
import org.dolphinemu.dolphinemu.features.settings.model.IntSetting
import kotlin.math.abs

class AndroidHotkeyManager {
    private val pressedKeys = mutableSetOf<Int>()
    private val firedCombos = mutableSetOf<Int>()

    fun dispatchKeyEvent(event: KeyEvent): Boolean {
        val keyCode = event.keyCode

        when (event.action) {
            KeyEvent.ACTION_DOWN -> {
                pressedKeys.add(keyCode)

                if (event.repeatCount > 0) {
                    return isKeyPartOfActiveCombo(keyCode)
                }

                val combo = comboForKey(keyCode)
                if (combo != HOTKEY_DISABLED && isSelectPressed()) {
                    return triggerOrConsume(combo)
                }
            }

            KeyEvent.ACTION_UP -> {
                val combo = comboForKey(keyCode)
                val wasHotkeyKey = combo != HOTKEY_DISABLED && isSelectPressed()
                pressedKeys.remove(keyCode)

                if (keyCode == KeyEvent.KEYCODE_BUTTON_SELECT) {
                    firedCombos.clear()
                } else if (combo != HOTKEY_DISABLED) {
                    firedCombos.remove(combo)
                }

                if (wasHotkeyKey) {
                    return isComboConfigured(combo)
                }
            }
        }

        return false
    }

    fun dispatchGenericMotionEvent(event: MotionEvent): Boolean {
        if (!isSelectPressed()) {
            firedCombos.remove(HOTKEY_SELECT_RIGHT_STICK_UP)
            firedCombos.remove(HOTKEY_SELECT_RIGHT_STICK_DOWN)
            return false
        }

        val y = rightStickY(event)
        val combo = when {
            y <= -RIGHT_STICK_THRESHOLD -> HOTKEY_SELECT_RIGHT_STICK_UP
            y >= RIGHT_STICK_THRESHOLD -> HOTKEY_SELECT_RIGHT_STICK_DOWN
            else -> HOTKEY_DISABLED
        }

        if (combo == HOTKEY_DISABLED) {
            firedCombos.remove(HOTKEY_SELECT_RIGHT_STICK_UP)
            firedCombos.remove(HOTKEY_SELECT_RIGHT_STICK_DOWN)
            return false
        }

        return triggerOrConsume(combo)
    }

    private fun triggerOrConsume(combo: Int): Boolean {
        if (!isComboConfigured(combo)) {
            return false
        }

        if (firedCombos.add(combo)) {
            performAction(combo)
        }

        return true
    }

    private fun performAction(combo: Int) {
        when (combo) {
            IntSetting.MAIN_HOTKEY_SAVE_STATE.int -> saveState()
            IntSetting.MAIN_HOTKEY_LOAD_STATE.int -> loadState()
            IntSetting.MAIN_HOTKEY_SPEED_TOGGLE.int -> toggleSpeed()
        }
    }

    private fun saveState() {
        if (!BooleanSetting.MAIN_ENABLE_SAVESTATES.boolean) {
            showToast(R.string.hotkey_savestates_disabled)
            return
        }

        NativeLibrary.SaveState(QUICK_SAVE_SLOT)
        showToast(R.string.hotkey_saved_state)
    }

    private fun loadState() {
        if (!BooleanSetting.MAIN_ENABLE_SAVESTATES.boolean) {
            showToast(R.string.hotkey_savestates_disabled)
            return
        }

        NativeLibrary.LoadState(QUICK_SAVE_SLOT)
        showToast(R.string.hotkey_loaded_state)
    }

    private fun toggleSpeed() {
        val currentSpeed = FloatSetting.MAIN_EMULATION_SPEED.float
        val fastForwardSpeed = sanitizeFastForwardSpeed(
            FloatSetting.MAIN_HOTKEY_FAST_FORWARD_SPEED.float
        )
        val isNormalSpeed = currentSpeed.isFinite() && abs(currentSpeed - 1.0f) < SPEED_EPSILON
        val nextSpeed = if (isNormalSpeed) fastForwardSpeed else 1.0f

        NativeLibrary.SetEmulationSpeedLimit(nextSpeed)

        if (abs(nextSpeed - 1.0f) < SPEED_EPSILON) {
            showToast(R.string.hotkey_speed_normal)
        } else {
            showToast(R.string.hotkey_speed_fast, (nextSpeed * 100).toInt())
        }
    }

    private fun sanitizeFastForwardSpeed(speed: Float): Float =
        if (speed.isFinite()) {
            speed.coerceIn(MIN_FAST_FORWARD_SPEED, MAX_FAST_FORWARD_SPEED)
        } else {
            DEFAULT_FAST_FORWARD_SPEED
        }

    private fun showToast(messageId: Int, vararg args: Any) {
        NativeLibrary.getEmulationActivity()?.let {
            val message = if (args.isEmpty()) it.getString(messageId) else it.getString(messageId, *args)
            Toast.makeText(it, message, Toast.LENGTH_SHORT).show()
        }
    }

    private fun isComboConfigured(combo: Int): Boolean =
        combo != HOTKEY_DISABLED && (
                IntSetting.MAIN_HOTKEY_SAVE_STATE.int == combo ||
                        IntSetting.MAIN_HOTKEY_LOAD_STATE.int == combo ||
                        IntSetting.MAIN_HOTKEY_SPEED_TOGGLE.int == combo
                )

    private fun isKeyPartOfActiveCombo(keyCode: Int): Boolean =
        comboForKey(keyCode).let { it != HOTKEY_DISABLED && isComboConfigured(it) && firedCombos.contains(it) }

    private fun isSelectPressed(): Boolean = pressedKeys.contains(KeyEvent.KEYCODE_BUTTON_SELECT)

    private fun comboForKey(keyCode: Int): Int =
        when (keyCode) {
            KeyEvent.KEYCODE_BUTTON_R1 -> HOTKEY_SELECT_R
            KeyEvent.KEYCODE_BUTTON_L1 -> HOTKEY_SELECT_L
            KeyEvent.KEYCODE_DPAD_UP -> HOTKEY_SELECT_DPAD_UP
            KeyEvent.KEYCODE_DPAD_DOWN -> HOTKEY_SELECT_DPAD_DOWN
            KeyEvent.KEYCODE_DPAD_LEFT -> HOTKEY_SELECT_DPAD_LEFT
            KeyEvent.KEYCODE_DPAD_RIGHT -> HOTKEY_SELECT_DPAD_RIGHT
            KeyEvent.KEYCODE_BUTTON_START -> HOTKEY_SELECT_START
            else -> HOTKEY_DISABLED
        }

    private fun rightStickY(event: MotionEvent): Float {
        val rz = event.getAxisValue(MotionEvent.AXIS_RZ)
        val ry = event.getAxisValue(MotionEvent.AXIS_RY)
        return if (abs(rz) >= abs(ry)) rz else ry
    }

    companion object {
        const val HOTKEY_DISABLED = 0
        const val HOTKEY_SELECT_RIGHT_STICK_UP = 1
        const val HOTKEY_SELECT_RIGHT_STICK_DOWN = 2
        const val HOTKEY_SELECT_R = 3
        const val HOTKEY_SELECT_L = 4
        const val HOTKEY_SELECT_DPAD_UP = 5
        const val HOTKEY_SELECT_DPAD_DOWN = 6
        const val HOTKEY_SELECT_DPAD_LEFT = 7
        const val HOTKEY_SELECT_DPAD_RIGHT = 8
        const val HOTKEY_SELECT_START = 9

        private const val QUICK_SAVE_SLOT = 9
        private const val RIGHT_STICK_THRESHOLD = 0.65f
        private const val SPEED_EPSILON = 0.01f
        private const val MIN_FAST_FORWARD_SPEED = 1.0f
        private const val DEFAULT_FAST_FORWARD_SPEED = 2.0f
        private const val MAX_FAST_FORWARD_SPEED = 10.0f
    }
}
