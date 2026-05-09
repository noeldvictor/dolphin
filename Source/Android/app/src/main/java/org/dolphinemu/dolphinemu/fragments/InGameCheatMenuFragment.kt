// SPDX-License-Identifier: GPL-2.0-or-later

package org.dolphinemu.dolphinemu.fragments

import android.graphics.Typeface
import android.os.Bundle
import android.text.TextUtils
import android.util.TypedValue
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.CompoundButton
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.google.android.material.color.MaterialColors
import com.google.android.material.divider.MaterialDivider
import com.google.android.material.materialswitch.MaterialSwitch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.dolphinemu.dolphinemu.NativeLibrary
import org.dolphinemu.dolphinemu.R
import org.dolphinemu.dolphinemu.databinding.FragmentIngameCheatMenuBinding
import org.dolphinemu.dolphinemu.features.cheats.model.ARCheat
import org.dolphinemu.dolphinemu.features.cheats.model.BundledGeckoCodes
import org.dolphinemu.dolphinemu.features.cheats.model.Cheat
import org.dolphinemu.dolphinemu.features.cheats.model.GeckoCheat
import org.dolphinemu.dolphinemu.features.cheats.model.GraphicsMod
import org.dolphinemu.dolphinemu.features.cheats.model.GraphicsModGroup
import org.dolphinemu.dolphinemu.features.cheats.model.PatchCheat
import org.dolphinemu.dolphinemu.features.settings.model.BooleanSetting
import org.dolphinemu.dolphinemu.features.settings.model.NativeConfig
import kotlin.math.roundToInt

class InGameCheatMenuFragment : Fragment() {
    private var gameId = ""
    private var gameTdbId = ""
    private var revision = 0

    private var graphicsModGroup: GraphicsModGroup? = null
    private val graphicsMods = ArrayList<GraphicsMod>()
    private val patchCheats = ArrayList<PatchCheat>()
    private val arCheats = ArrayList<ARCheat>()
    private val geckoCheats = ArrayList<GeckoCheat>()

    private var _binding: FragmentIngameCheatMenuBinding? = null
    private val binding get() = _binding!!

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        gameId = requireArguments().getString(KEY_GAME_ID)!!
        gameTdbId = requireArguments().getString(KEY_GAMETDB_ID)!!
        revision = requireArguments().getInt(KEY_REVISION)
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentIngameCheatMenuBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        viewLifecycleOwner.lifecycleScope.launch {
            withContext(Dispatchers.IO) {
                loadCheats()
            }

            if (_binding != null) {
                renderCheats()
            }
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }

    private fun loadCheats() {
        graphicsMods.clear()
        patchCheats.clear()
        arCheats.clear()
        geckoCheats.clear()

        graphicsModGroup = GraphicsModGroup.load(gameId)
        graphicsMods.addAll(graphicsModGroup!!.mods)
        patchCheats.addAll(PatchCheat.loadCodes(gameId, revision))
        arCheats.addAll(ARCheat.loadCodes(gameId, revision))
        geckoCheats.addAll(GeckoCheat.loadCodes(gameId, revision))

        if (gameTdbId.isNotEmpty()) {
            BundledGeckoCodes.loadCodes(gameTdbId)?.let { bundledCodes ->
                for (cheat in bundledCodes) {
                    if (!geckoCheats.contains(cheat)) {
                        geckoCheats.add(cheat)
                    }
                }
            }
        }
    }

    private fun renderCheats() {
        val container = binding.layoutCheatOptions
        container.removeAllViews()

        addGlobalCheatToggle(container)
        addDivider(container)

        var hasSpecificCheats = false
        hasSpecificCheats = addCheatGroup(
            container,
            R.string.cheats_header_graphics_mod,
            graphicsMods
        ) { graphicsModGroup?.save() } || hasSpecificCheats
        hasSpecificCheats = addCheatGroup(
            container,
            R.string.cheats_header_patch,
            patchCheats
        ) { savePatchCheats() } || hasSpecificCheats
        hasSpecificCheats = addCheatGroup(
            container,
            R.string.cheats_header_ar,
            arCheats
        ) { saveArCheats() } || hasSpecificCheats
        hasSpecificCheats = addCheatGroup(
            container,
            R.string.cheats_header_gecko,
            geckoCheats
        ) { saveGeckoCheats() } || hasSpecificCheats

        if (!hasSpecificCheats) {
            addEmptyMessage(container)
        }
    }

    private fun addGlobalCheatToggle(container: LinearLayout) {
        addSwitchRow(
            container,
            getString(R.string.emulation_general_cheats),
            BooleanSetting.MAIN_ENABLE_CHEATS.boolean
        ) { enabled ->
            BooleanSetting.MAIN_ENABLE_CHEATS.setBoolean(NativeConfig.LAYER_BASE_OR_CURRENT, enabled)
            BooleanSetting.MAIN_ENABLE_CHEATS.setBoolean(NativeConfig.LAYER_BASE, enabled)
            NativeConfig.save(NativeConfig.LAYER_BASE)
            NativeLibrary.ReloadCheats()

            val message = if (enabled) R.string.cheats_enabled else R.string.cheats_disabled
            Toast.makeText(requireContext(), message, Toast.LENGTH_SHORT).show()
        }
    }

    private fun addCheatGroup(
        container: LinearLayout,
        titleId: Int,
        cheats: List<Cheat>,
        save: () -> Unit
    ): Boolean {
        if (cheats.isEmpty()) {
            return false
        }

        addHeader(container, titleId)
        for (cheat in cheats) {
            addSwitchRow(container, getCheatName(cheat), cheat.getEnabled()) { enabled ->
                cheat.setEnabled(enabled)
                save()
                NativeLibrary.ReloadCheats()
            }
        }
        addDivider(container)
        return true
    }

    private fun addHeader(container: LinearLayout, titleId: Int) {
        val horizontalPadding = resources.getDimensionPixelSize(R.dimen.spacing_large)
        val topPadding = dp(24)
        val bottomPadding = dp(8)
        val header = TextView(requireContext()).apply {
            setText(titleId)
            setTextColor(MaterialColors.getColor(binding.root, R.attr.colorPrimary))
            setTypeface(typeface, Typeface.BOLD)
            textAlignment = View.TEXT_ALIGNMENT_VIEW_START
            gravity = android.view.Gravity.CENTER_VERTICAL or android.view.Gravity.START
            setPadding(horizontalPadding, topPadding, horizontalPadding, bottomPadding)
        }
        container.addView(header, matchWrapParams())
    }

    private fun addSwitchRow(
        container: LinearLayout,
        title: CharSequence,
        checked: Boolean,
        onChanged: (Boolean) -> Unit
    ) {
        val context = requireContext()
        val horizontalPadding = resources.getDimensionPixelSize(R.dimen.spacing_large)
        val row = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
            isClickable = true
            isFocusable = true
            minimumHeight = dp(56)
            setPadding(horizontalPadding, 0, horizontalPadding, 0)
            setSelectableBackground(this)
        }
        val label = TextView(context).apply {
            text = title
            ellipsize = TextUtils.TruncateAt.END
            maxLines = 2
            setTextColor(MaterialColors.getColor(binding.root, R.attr.colorOnSurface))
            textAlignment = View.TEXT_ALIGNMENT_VIEW_START
            textSize = 16f
        }
        val toggle = MaterialSwitch(context).apply {
            isChecked = checked
            setOnCheckedChangeListener { _: CompoundButton, enabled: Boolean -> onChanged(enabled) }
        }

        row.setOnClickListener { toggle.isChecked = !toggle.isChecked }
        row.addView(label, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(toggle)
        container.addView(row, matchWrapParams())
    }

    private fun addDivider(container: LinearLayout) {
        container.addView(MaterialDivider(requireContext()), matchWrapParams())
    }

    private fun addEmptyMessage(container: LinearLayout) {
        val padding = resources.getDimensionPixelSize(R.dimen.spacing_large)
        val empty = TextView(requireContext()).apply {
            setText(R.string.emulation_no_cheats)
            setTextColor(MaterialColors.getColor(binding.root, R.attr.colorOnSurfaceVariant))
            textAlignment = View.TEXT_ALIGNMENT_VIEW_START
            setPadding(padding, padding, padding, padding)
        }
        container.addView(empty, matchWrapParams())
    }

    private fun getCheatName(cheat: Cheat): String =
        cheat.getName().ifBlank { getString(R.string.cheats) }

    private fun savePatchCheats() {
        PatchCheat.saveCodes(gameId, revision, patchCheats.toTypedArray())
    }

    private fun saveArCheats() {
        ARCheat.saveCodes(gameId, revision, arCheats.toTypedArray())
    }

    private fun saveGeckoCheats() {
        GeckoCheat.saveCodes(gameId, revision, geckoCheats.toTypedArray())
    }

    private fun setSelectableBackground(view: View) {
        val outValue = TypedValue()
        view.context.theme.resolveAttribute(android.R.attr.selectableItemBackground, outValue, true)
        view.setBackgroundResource(outValue.resourceId)
    }

    private fun matchWrapParams() =
        LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        )

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).roundToInt()

    companion object {
        private const val KEY_GAME_ID = "game_id"
        private const val KEY_GAMETDB_ID = "gametdb_id"
        private const val KEY_REVISION = "revision"

        fun newInstance(): InGameCheatMenuFragment {
            val fragment = InGameCheatMenuFragment()
            val arguments = Bundle()
            arguments.putString(KEY_GAME_ID, NativeLibrary.GetCurrentGameID())
            arguments.putString(KEY_GAMETDB_ID, NativeLibrary.GetCurrentGameTdbID())
            arguments.putInt(KEY_REVISION, NativeLibrary.GetCurrentRevision())
            fragment.arguments = arguments
            return fragment
        }
    }
}
