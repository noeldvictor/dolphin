// Copyright 2026 Dolphin Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include <string>
#include <vector>

#include <jni.h>

#include "Common/FileUtil.h"
#include "Common/IniFile.h"
#include "Core/ActionReplay.h"
#include "Core/ConfigManager.h"
#include "Core/GeckoCode.h"
#include "Core/GeckoCodeConfig.h"
#include "Core/PatchEngine.h"
#include "jni/AndroidCommon/AndroidCommon.h"

extern "C" {

JNIEXPORT jboolean JNICALL
Java_org_dolphinemu_dolphinemu_features_cheats_model_CheatAvailability_hasLocalCodes(
    JNIEnv* env, jclass, jstring jGameID, jint revision)
{
  const std::string game_id = GetJString(env, jGameID);

  Common::IniFile game_ini_local;
  game_ini_local.Load(File::GetUserPath(D_GAMESETTINGS_IDX) + game_id + ".ini");
  const Common::IniFile game_ini_default = SConfig::LoadDefaultGameIni(game_id, revision);

  if (!ActionReplay::LoadCodes(game_ini_default, game_ini_local).empty())
    return JNI_TRUE;

  if (!Gecko::LoadCodes(game_ini_default, game_ini_local).empty())
    return JNI_TRUE;

  std::vector<PatchEngine::Patch> patches;
  PatchEngine::LoadPatchSection("OnFrame", &patches, game_ini_default, game_ini_local);
  return static_cast<jboolean>(!patches.empty());
}
}
