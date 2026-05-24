# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════════════
# SEGE OPEN SOURCE — Module registry + .py loader
# ════════════════════════════════════════════════════════════════════════════
#
# EN:
#   The closed-source build ships each macro as an encrypted blob (.enc)
#   and fetches per-module decryption keys from a license server. The
#   open-source build is straightforward: every macro lives next door at
#   `segesource/macros/<name>.py` and is imported via stock importlib.
#
#   `MODULE_REGISTRY` is the single source of truth: it lists every
#   macro's metadata (display name, tab page, Python class names, and
#   default user-settings shape). The UI walks this list to build tabs.
#
# TR:
#   Kapalı kaynak sürüm her makroyu şifreli blob (.enc) olarak paketler
#   ve modüle özel şifre çözme anahtarlarını lisans sunucusundan çeker.
#   Açık kaynak sürümde her şey düz: her makro `segesource/macros/<ad>.py`
#   altında durur ve standart importlib ile yüklenir.
#
#   `MODULE_REGISTRY` tek doğru kaynak: her makronun metadata'sını
#   (görünen ad, sekme sayfası, Python sınıf adları, varsayılan ayar
#   şekli) listeler. UI sekmeleri bu listeden kurar.
# ════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import importlib
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from core.logger import get_logger, log_event

log = get_logger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Cooperative priority gate (replaces the old DRM-bound lease gate)
# Kooperatif öncelik kapısı (eski DRM bağlı lease kapısının yerine)
# ────────────────────────────────────────────────────────────────────────────
#
# EN: Some macros (priority=0, "VIP") get a short exclusive window during
#     which lower-priority macros wait their turn. This keeps a single
#     critical action (e.g. a CC defense) from being interleaved with
#     less important input. It is purely cooperative — no kernel locks.
# TR: Bazı makrolar (priority=0, "VIP") kısa bir özel pencere alır;
#     bu pencerede düşük öncelikli makrolar sırasını bekler. Tek bir
#     kritik aksiyonun (örn. CC savunma) önemsiz girdiyle karışmasını
#     engeller. Tamamen kooperatif — kernel kilidi yok.
#
_prio_lock = threading.Lock()
_vip_busy_until: float = 0.0


def _apply_priority_patch() -> None:
    """EN: Monkey-patch `clicksend.KeyboardDriver` / `MouseDriver` to honour
        each instance's `_prio_level` and `_prio_duration` attributes.
    TR: `clicksend.KeyboardDriver` / `MouseDriver`'ı monkey-patch ederek
        her örneğin `_prio_level` ve `_prio_duration` özelliklerine
        saygı duymasını sağlar."""
    import clicksend  # type: ignore  # noqa: F401

    def _wrap(original):
        def wrapper(self, *args, **kwargs):
            global _vip_busy_until
            p = getattr(self, "_prio_level", 1)
            duration = getattr(self, "_prio_duration", 0.20)

            if p == 0:
                # VIP macro: claim the window and run immediately.
                # VIP makro: pencereyi al ve hemen çalıştır.
                with _prio_lock:
                    _vip_busy_until = time.time() + duration
                    return original(self, *args, **kwargs)
            # Non-VIP: wait until any current VIP window expires.
            # VIP değil: VIP penceresi bitene kadar bekle.
            while True:
                with _prio_lock:
                    if time.time() >= _vip_busy_until:
                        return original(self, *args, **kwargs)
                time.sleep(0.005)

        return wrapper

    kb_methods = ("tusbas", "tusbasilitut", "tusbirak")
    for name in kb_methods:
        if hasattr(clicksend.KeyboardDriver, name):
            orig = getattr(clicksend.KeyboardDriver, name)
            if not hasattr(clicksend.KeyboardDriver, f"_orig_{name}"):
                setattr(clicksend.KeyboardDriver, f"_orig_{name}", orig)
                setattr(clicksend.KeyboardDriver, name, _wrap(orig))

    ms_methods = (
        "leftclick", "rightclick",
        "mouse_left_down", "mouse_left_up",
        "mouse_right_down", "mouse_right_up",
        "mouse_move", "move",
    )
    for name in ms_methods:
        if hasattr(clicksend.MouseDriver, name):
            orig = getattr(clicksend.MouseDriver, name)
            if not hasattr(clicksend.MouseDriver, f"_orig_{name}"):
                setattr(clicksend.MouseDriver, f"_orig_{name}", orig)
                setattr(clicksend.MouseDriver, name, _wrap(orig))


def _inject_priority(macro_inst: Any, mod: Any, priority: int, duration: float) -> None:
    """EN: Set `_prio_level` / `_prio_duration` on every driver instance
        that the macro holds. Macros that ship their own driver instances
        on module-scope functions (free `_default_tap` etc.) are also
        covered.
    TR: Makronun tuttuğu her sürücü örneğine `_prio_level` /
        `_prio_duration` yaz. Modül kapsamlı serbest fonksiyonlarda
        (örn. `_default_tap`) tutulan sürücüleri de hedefler."""
    for attr in ("_driver", "kb", "mouse", "_mouse"):
        d = getattr(macro_inst, attr, None)
        if d is not None:
            d._prio_level = priority
            d._prio_duration = duration

    for func_name in (
        "_default_tap", "_send_key", "_default_send_key", "_default_hold_scan"
    ):
        func = getattr(mod, func_name, None)
        if func is None:
            continue
        if getattr(func, "_driver", None) is None:
            try:
                from clicksend import KeyboardDriver  # type: ignore
                func._driver = KeyboardDriver()
            except Exception as e:
                log.debug("inject_priority %s skip: %s", func_name, e)
                continue
        func._driver._prio_level = priority
        func._driver._prio_duration = duration


# ────────────────────────────────────────────────────────────────────────────
# MODULE_REGISTRY
# EN: Definitive metadata for all macros. Adding a new module = adding
#     one entry here + dropping the .py file in `segesource/macros/`.
# TR: Tüm makroların kesin metadata'sı. Yeni modül eklemek = buraya bir
#     girdi + `segesource/macros/` altına .py dosyası bırakmak.
# ────────────────────────────────────────────────────────────────────────────

MODULE_REGISTRY: List[Dict[str, Any]] = [
    # ════════════════════════ PAGE 1: WARRIOR ════════════════════════
    {"key": "wari_seriskill", "priority": 1, "name": "WARRIOR SERİ SKILL", "page_index": [1], "module_file": "wari_seriskill", "class_name": "WarriorSkillMacro", "widget_name": "WarriorSkillWidget", "default": {"key": "F", "order": "2rr", "z_enabled": False}},
    {"key": "wari_des", "priority": 0, "name": "DES OL YERE VUR", "page_index": [1], "module_file": "wari_des", "class_name": "WarriorDesMacro", "widget_name": "WarriorDesWidget", "default": {"key": "G", "fkey": "F2", "combo_order": "3456"}},
    {"key": "wari_kafa", "priority": 0, "name": "WARRIOR KAFA", "page_index": [1], "module_file": "wari_kafa", "class_name": "WarriorKafaMacro", "widget_name": "WarriorKafaWidget", "default": {"hotkey": "F11"}},
    {"key": "wari_kalkan", "name": "KALKAN TAK", "page_index": [1], "module_file": "wari_kalkan", "class_name": "WarriorKalkanMacro", "widget_name": "WarriorKalkanWidget", "default": {"key": "F"}},
    {"key": "wari_silme", "priority": 0, "name": "DEBUFF SİLME", "page_index": [1], "module_file": "wari_silme", "class_name": "WarriorSilmeMacro", "widget_name": "WarriorSilmeWidget", "default": {"key": "F9", "mode": "Mod 2"}},
    {"key": "firfir", "priority": 1, "name": "FIRFIR (SPIN)", "page_index": [1], "module_file": "firfir", "class_name": "FirfirMacro", "widget_name": "FirfirWidget", "default": {"hotkey": "CAPSLOCK", "mode": "hold", "direction": "Sol (A)", "speed": 0.01, "delay": 0.01}},
    {"key": "crazydes", "priority": 0, "name": "CRAZY DES", "page_index": [1], "module_file": "crazydes", "class_name": "CrazyDesMacro", "widget_name": "CrazyDesWidget", "default": {"hp_threshold": 30, "des_f": 0, "des_d": 1, "hotkey_manual": "G", "hp_active": False, "manual_active": True}},

    # ════════════════════════ PAGE 2: ASAS ════════════════════════
    {"key": "asas", "priority": 1, "name": "ASAS", "page_index": [2], "module_file": "asas", "class_name": "AsasHybridMacro", "widget_name": "AsasWidget", "default": {"hotkey": "Z", "digits": [2, 3, 4, 5, 6]}},
    {"key": "styx", "priority": 0, "priority_duration": 1, "name": "STYX / MANA SİLME", "page_index": [2], "module_file": "styx", "class_name": "StyxMacro", "widget_name": "StyxWidget", "default": {"hotkey": "K", "delay_skill": 0.05}},
    {"key": "otobicak", "priority": 0, "priority_duration": 2, "name": "OTO BIÇAK", "page_index": [2], "module_file": "otobicak", "class_name": "OtoBicakMacro", "widget_name": "OtoBicakWidget", "default": {"hotkey": "B", "f_bar": 3, "digit": 6}},

    # ════════════════════════ PAGE 3: ARCHER ════════════════════════
    {"key": "threefive", "priority": 1, "name": "3-5 OKÇU", "page_index": [3], "module_file": "threefive", "class_name": "ThreeFiveMacro", "widget_name": "ThreeFiveWidget", "default": {"hotkey": "C", "mode": "toggle", "use_f_key": True, "f_bar": 3, "key5": 2, "key3": 3, "combo_delay": 0.40, "w_delay": 0.05, "use_z": False, "z_delay": 0.10}},
    {"key": "icemlr", "priority": 0, "name": "ICE / MANA / LR", "page_index": [3], "module_file": "icelr", "class_name": "IceManaLRMacro", "widget_name": "IceManaLRWidget", "default": {"hotkey": "X", "mode": "toggle"}},
    {"key": "ok72", "priority": 0, "name": "72 SKILL", "page_index": [3], "module_file": "ok72", "class_name": "Ok72Macro", "widget_name": "Ok72Widget", "default": {"hotkey": "N", "digit": 3}},

    # ════════════ COMMON (Asas:2, Archer:3) ════════════
    {"key": "minor", "name": "MİNÖR", "page_index": [2, 3], "module_file": "minor", "class_name": "MinorMacro", "widget_name": "MinorWidget", "default": {"hotkey": "V", "minor_count": 3}},
    {"key": "m20", "name": "M20", "priority": 0, "priority_duration": 2, "page_index": [2, 3], "module_file": "m20", "class_name": "M20Macro", "widget_name": "M20Widget", "default": {"hotkey": "M", "f_bar": 3, "digit": 4}},
    {"key": "otocure", "priority": 0, "priority_duration": 2, "name": "OTO CURE", "page_index": [2, 3], "module_file": "otocure", "class_name": "OtoCureMacro", "widget_name": "OtoCureWidget", "default": {"hotkey": "C", "f_bar": 3, "digit": 5}},
    {"key": "otodef", "name": "OTO DEFANS (CC)", "page_index": [2, 3], "module_file": "otodef", "class_name": "OtoDefMacro", "widget_name": "OtoDefWidget", "default": {"hotkey": "A"}},
    {"key": "oto_explore", "name": "OTO EXPLORE", "page_index": [2, 3], "module_file": "oto_explore", "class_name": "OtoExploreMacro", "widget_name": "OtoExploreWidget", "default": {"hotkey": "CAPS LOCK"}},
    {"key": "birli", "name": "BİRLİ TARAMA", "page_index": [1, 2, 3], "module_file": "birli", "class_name": "BirliMacro", "widget_name": "BirliWidget", "default": {"hotkey": "T"}},

    # ════════════════════════ PAGE 4: SMART POT / SUPPORT ════════════════════════
    {"key": "hpmp", "name": "AKILLI HP/MP", "page_index": [4], "module_file": "hpmp", "class_name": "SmartHpMpMacro", "widget_name": "HpMpWidget", "default": {"hotkey": "H", "hp_enabled": True, "mp_enabled": True}},
    {"key": "otodurat", "name": "OTO DURATION", "page_index": [4], "module_file": "otodurat", "class_name": "OtoDuratMacro", "widget_name": "OtoDuratWidget", "default": {"key": "F12"}},
    {"key": "itemchange", "name": "İTEM DEĞİŞME", "page_index": [4], "module_file": "itemchange", "class_name": "ItemChangeMacro", "widget_name": "ItemChangeWidget", "default": {"hotkey": "G"}},

    # ════════════════════════ PAGE 5: SELF / CUSTOM ════════════════════════
    {"key": "self_macro_1", "name": "ÖZEL MAKRO 1", "page_index": [5], "module_file": "self_macro", "class_name": "SelfMacro", "widget_name": "SelfWidget", "default": {"hotkey": "F6", "sequential": True}},
    {"key": "self_macro_2", "name": "ÖZEL MAKRO 2", "page_index": [5], "module_file": "self_macro", "class_name": "SelfMacro", "widget_name": "SelfWidget", "default": {"hotkey": "F7", "sequential": True}},
    {"key": "self_macro_3", "name": "ÖZEL MAKRO 3", "page_index": [5], "module_file": "self_macro", "class_name": "SelfMacro", "widget_name": "SelfWidget", "default": {"hotkey": "F8", "sequential": True}},
    {"key": "oto_kontrol", "priority": 0, "name": "OTO KONTROL", "page_index": [5], "module_file": "otokontrol", "class_name": "OtoKontrolMacro", "widget_name": "OtoKontrolWidget", "default": {"hotkey": "F10", "threshold": 0.80}},
    {"key": "ototiklama", "name": "OTO TIKLAMA", "page_index": [5], "module_file": "ototiklama", "class_name": "OtoTiklamaMacro", "widget_name": "OtoTiklamaWidget", "default": {"hotkey": "INSERT", "threshold": 0.85, "scan_region": None, "items": {}}},
    {"key": "macro_tasarimci", "name": "V5 SELF EDITOR", "page_index": [5], "module_file": "MacronuKendinYap", "class_name": "MacroEngine", "widget_name": "MacronuKendinYapWidget", "default": {"name": "ÖZEL TASARIM", "hotkey": "G", "steps": []}},

    # ════════════════════════ PAGE 6: PRIEST ════════════════════════
    {"key": "priest_goat", "priority": 1, "name": "PRIEST GOAT MOD", "page_index": [6], "module_file": "priestgoatmod", "class_name": "PriestGoatLogic", "widget_name": "PriestGoatWidget", "default": {"attack_key": 2, "hp_key": 1, "mana_key": 3, "kitap_key": 8, "kol_key": 9, "kitap_enabled": False, "kol_enabled": False, "kitap_delay": 180.0, "kol_delay": 180.0, "inv_coords": [0, 0], "inv_mode_open": False, "mouse_return": False, "other_skill_delay": 0.5, "combo_mode": "2rr", "r_speed": 0.02, "skill_speed": 0.05}},
    {"key": "priest_attack", "priority": 1, "name": "BP ATAK (KITAP/KOL)", "page_index": [6], "module_file": "priestattack", "class_name": "PriestAttackMacro", "widget_name": "PriestAttackWidget", "default": {"skill_key": 2, "mode": "toggle", "kitap_enabled": False, "kitap_key": 8, "kol_enabled": False, "kol_key": 9}},
    {"key": "priest_skiller", "priority": 0, "priority_duration": 2, "name": "OTO PRIEST SKILLER", "page_index": [6], "module_file": "otopriestskiller", "class_name": "OtoPriestSkillerMacro", "widget_name": "OtoPriestSkillerWidget", "default": {"skills": {}}},
    {"key": "priest_kalkan", "name": "PRIEST KALKAN (LOOP)", "page_index": [6], "module_file": "pri_kalkan", "class_name": "PriestKalkanMacro", "widget_name": "PriestKalkanWidget", "default": {"key": "F", "mode": "single"}},
    {"key": "priest_hpmp_heal", "priority": 0, "priority_duration": 2, "name": "PRIEST OTO HEAL/POT", "page_index": [6], "module_file": "Smarthpmppriest", "class_name": "SmartPriestHpMpMacro", "widget_name": "PriestHpMpWidget", "default": {"hp_enabled": True, "mp_enabled": True, "heal_enabled": False, "hotkey": "H"}},
    {"key": "priest_party_heal", "priority": 0, "priority_duration": 2, "name": "PARTY HEAL ASİSTANI", "page_index": [6], "module_file": "priestpartyheal", "class_name": "PriestPartyHealMacro", "widget_name": "PriestPartyHealWidget", "default": {"region": None, "single_1920": {"active": True, "hp": 0.8}, "party_10k": {"active": True, "hp": 0.7}}},

    # ════════════════════════ PAGE 7: MAGE ════════════════════════
    {"key": "mage_staff", "name": "MAGE STAFF", "page_index": [7], "module_file": "magestaff", "class_name": "MageStaffMacro", "widget_name": "MageStaffWidget", "default": {"key": "Z", "mode": "toggle", "skill_key": 1, "order": "2rr"}},
    {"key": "restore", "name": "RESTORE SİLME", "page_index": [7], "module_file": "restore", "class_name": "RestoreMacro", "widget_name": "RestoreWidget", "default": {"key": "F5"}},
    {"key": "mage_remote_farm", "name": "MAGE UZAK FARM (NOVA)", "page_index": [7], "module_file": "magefarm", "class_name": "MageFarmMacro", "widget_name": "MageFarmWidget", "default": {"mob_image_path": None, "mob_region": None, "single_skills": [], "area_skills": []}},
    {"key": "mage_oto_tp", "name": "MAGE OTO TP", "page_index": [7], "module_file": "mageototp", "class_name": "MageOtoTpMacro", "widget_name": "MageOtoTpWidget", "default": {"active": True, "f": 1, "d": 1, "hp": 0.40, "mode": "single", "hotkey": "PAGE UP", "region": None}},
    {"key": "mage_pt_cekme", "name": "SIRALI PT ÇEKME", "page_index": [7], "module_file": "mageptcekme", "class_name": "MagePtCekmeMacro", "widget_name": "MagePtCekmeWidget", "default": {"hotkey": "G", "f": 1, "d": 1, "delay": 0.5, "coords": []}},
    {"key": "mage_text_tp", "name": "YAZI İLE TP (CHAT)", "page_index": [7], "module_file": "magetexttp", "class_name": "MageTextTpMacro", "widget_name": "MageTextTpWidget", "default": {"region_chat": None, "region_party": None, "keywords": "44,tp", "f": 1, "d": 5}},

    # ════════════════════════ PAGE 8: KURIAN ════════════════════════
    {"key": "kurian_attack", "name": "KURIAN SERI SKILL", "page_index": [8], "module_file": "kurianseriskill", "class_name": "KurianSeriSkill", "widget_name": "KurianSeriSkillWidget", "default": {"key": "X", "order": "2rr", "mode": "toggle", "z_enabled": False}},

    # ════════════════════════ PAGE 9: FARM ════════════════════════
    {"key": "autodrop", "name": "OTOMATİK LOOT", "page_index": [9], "module_file": "loot_macro", "class_name": "AutoDropMacro", "widget_name": "AutoDropWidget", "default": {"hotkey": "X", "loot_center": [960, 540], "loot_area": None, "loot_layout": "4'lü Dikey", "loot_offset": 50, "loop_delay": 15.0, "click_delay": 0.15, "path_loot": None, "path_empty": None, "confidence_loot": 0.85, "scan_offset": 80}},
    {"key": "oto_rpr", "name": "OTO RPR & DEĞİŞİM", "priority": 1, "page_index": [9], "module_file": "otorpr", "class_name": "OtoRprMacro", "widget_name": "OtoRprWidget", "default": {"equipped_pos": None, "backup_slots": [], "main_weapon_slot": None, "rpr_f": 0, "rpr_d": 0, "check_interval": 5.0, "only_hammer": False}},
    {"key": "vip_storage", "name": "VIP DEPOLAMA BOTU", "priority": 0, "page_index": [9], "module_file": "vip_storage", "class_name": "VipStorageMacro", "widget_name": "VipStorageWidget", "default": {"hotkey": "F9", "mode": "Otomatik", "item_count": 5, "trigger_slot": 28, "timer_interval": 60, "slot1_pos": [0, 0], "vip_btn_pos": [0, 0]}},
    {"key": "clan_storage", "name": "CLAN DEPOLAMA BOTU", "page_index": [9], "module_file": "clan_storage", "class_name": "ClanStorageMacro", "widget_name": "ClanStorageWidget", "default": {"hotkey": "F10", "mode": "Süreli", "item_count": 5, "timer_value": 1, "timer_unit": "Dakika", "slot1_pos": [0, 0], "clan_tab_pos": [0, 0], "clan_btn_pos": [0, 0], "confirm_pos": [0, 0], "slot_spacing": 50}},
    {"key": "anti_afk", "name": "ANTI-AFK FARM (PİKSEL)", "page_index": [9], "module_file": "antiafkfarm", "class_name": "AntiAfkEngine", "widget_name": "AntiAfkWidget", "default": {"hotkey": "INSERT", "mode": "Warrior (Seri)"}},
    {"key": "farm", "name": "FARM BOT", "page_index": [9], "module_file": "farm", "class_name": "FarmMacro", "widget_name": "FarmWidget", "default": {"mode": "Warrior (Seri)"}},
    {"key": "pet_macro", "priority": 1, "name": "PET OTO", "page_index": [9], "module_file": "pet", "class_name": "SmartPetMacro", "widget_name": "PetMacroWidget", "default": {"hotkey": "F9", "hp_enabled": True, "hp_alt_num": 1, "hp_trigger": 0.50, "mp_enabled": True, "mp_alt_num": 2, "mp_trigger": 0.30, "feed_enabled": True, "feed_type": 1, "feed_trigger": 0.40, "attack_enabled": False, "z_duration": 0.05, "alt2_duration": 0.05, "attack_interval": 1.0, "hp_region": None}},

    # ════════════════════════ PAGE 10: GENERAL ════════════════════════
    {"key": "multi", "priority": 1, "name": "MULTIBOX", "page_index": [10], "module_file": "multi", "class_name": "MultiBoxMacro", "widget_name": "MultiWidget", "default": {"hotkey": "INSERT", "keyboard_active": True, "mouse_active": True}},
    {"key": "background_bot", "name": "ARKA PLAN BOTU", "page_index": [10], "module_file": "background", "class_name": "BackgroundBotV2Macro", "widget_name": "BackgroundBotV2Widget", "default": {"hotkey": "INSERT", "target_hwnds": [], "entries": []}},
    {"key": "upgrade_bot", "name": "UPGRADE BOTU", "page_index": [10], "module_file": "upgrade", "class_name": "UpgradeMacro", "widget_name": "UpgradeWidget", "default": {"hotkey": "F10", "speed_click": 0.1, "speed_process": 0.5, "path_scroll": None, "path_confirm": None, "path_empty": None, "start_slot_pos": None}},
    {"key": "narki", "name": "NARKI (ITEM KIRDIRMA)", "page_index": [10], "module_file": "narki", "class_name": "NarkiMacro", "widget_name": "NarkiWidget", "default": {"hotkey": "F10", "item_count": 1, "speed_click": 0.1, "start_stop_delay": 0.05, "loop_delay": 0.5, "npc_coords": [0, 0], "offset_stop": [0, 30], "offset_item1": [0, 100]}},
    {"key": "usko_otologin", "name": "OTO LOGIN BOTU", "page_index": [10], "module_file": "uskootologin", "class_name": "UskoOtoLoginMacro", "widget_name": "UskoOtoLoginWidget", "default": {"key": "F12", "game_path": "C:\\NTTGame\\KnightOnlineEn\\KnightOnLine.exe", "username": "", "password": "", "server_name": "FELIS", "images_dir": "login_images"}},
    {"key": "notification", "name": "NOTIFICATION", "page_index": [10], "module_file": "notification", "class_name": "NotificationMacro", "widget_name": "NotificationWidget", "default": {"enabled_discord": False, "discord_webhook_url": "", "enabled_telegram": False, "telegram_bot_token": "", "telegram_chat_id": "", "character_name": "", "msg_death": "Press OK!", "msg_dc": "Disconnected from Server!", "msg_number_change": "Sayı değişti!", "append_character_name": True, "append_time": True, "include_screenshot": False, "images_dir": "notification_images", "scan_interval_ms": 1000, "match_threshold": 0.75, "enable_death_watch": True, "enable_dc_watch": True, "enable_number_watch": False, "number_region": None, "number_ocr_lang": "eng", "number_same_tolerance": 0}},
    {"key": "flood_plus", "priority": 1, "name": "FLOOD MACRO", "page_index": [10], "module_file": "chat", "class_name": "ChatMacro", "widget_name": "ChatWidget", "default": {"key": "CTRL", "server_mode": "usko", "speed_mode": "fixed", "message_speed": 1.0, "rand_min": 1.0, "rand_max": 3.0, "coord_all": [0, 0], "coord_shout": [0, 0], "messages": []}},
]


# ────────────────────────────────────────────────────────────────────────────
# Loader
# ────────────────────────────────────────────────────────────────────────────

def load_all_modules() -> Dict[str, Tuple[Any, type]]:
    """EN: Import every macro listed in MODULE_REGISTRY and return a dict
        keyed by registry "key" → (Macro_instance, WidgetClass). Modules
        whose .py file is missing or whose import fails are skipped with
        a warning — the rest of the app still loads.
    TR: MODULE_REGISTRY'deki her makroyu import eder ve registry "key"
        anahtarlı bir dict döner → (Makro_örneği, WidgetSınıfı). .py
        dosyası eksik veya import'u patlayan modüller uyarı ile atlanır
        — uygulamanın geri kalanı yine yüklenir."""
    _apply_priority_patch()

    loaded: Dict[str, Tuple[Any, type]] = {}

    for entry in MODULE_REGISTRY:
        key = entry["key"]
        module_file = entry["module_file"]
        full_name = f"macros.{module_file}"

        try:
            mod = importlib.import_module(full_name)
        except ModuleNotFoundError as e:
            log.warning("SKIP %s: module '%s' not found (%s)", key, full_name, e)
            log_event("module", "missing", key=key, module=module_file)
            continue
        except Exception as e:
            log.error("SKIP %s: import failed: %s", key, e, exc_info=True)
            log_event("module", "import_failed", key=key, error=str(e))
            continue

        macro_cls: Optional[type] = getattr(mod, entry["class_name"], None)
        widget_cls: Optional[type] = getattr(mod, entry["widget_name"], None)
        if macro_cls is None or widget_cls is None:
            log.error(
                "SKIP %s: missing class — %s/%s in %s",
                key, entry["class_name"], entry["widget_name"], full_name,
            )
            continue

        try:
            macro_inst = macro_cls()
        except Exception as e:
            log.error("SKIP %s: __init__ failed: %s", key, e, exc_info=True)
            continue

        prio = entry.get("priority", 1)
        dur = entry.get("priority_duration", 0.20)
        _inject_priority(macro_inst, mod, prio, dur)

        loaded[key] = (macro_inst, widget_cls)
        log.debug("Loaded module %s (%s)", key, full_name)

    log.info("Modules loaded: %d / %d", len(loaded), len(MODULE_REGISTRY))
    log_event("module", "load_complete", total=len(loaded), expected=len(MODULE_REGISTRY))
    return loaded
