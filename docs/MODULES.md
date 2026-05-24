# Modules — SEGE Open Source

> EN: All 55 modules grouped by their tab page, with a one-line description.
> TR: Tüm 55 modül, sekme sayfalarına göre gruplandı; her biri için tek satır açıklama.

The `key` column matches `MODULE_REGISTRY` in `segesource/app/modules.py`.
The `file` column points to `segesource/macros/<file>.py`.

---

## Page 1 — Warrior

| key | name | file | purpose (EN) | amaç (TR) |
|---|---|---|---|---|
| `wari_seriskill` | WARRIOR SERİ SKILL | `wari_seriskill` | Serial skill rotation for warrior class | Warrior için seri skill kombosu |
| `wari_des` | DES OL YERE VUR | `wari_des` | "Descend" + ground hit combo | Des ol + yere vur komboso |
| `wari_kafa` | WARRIOR KAFA | `wari_kafa` | Head-shot helper | Kafa vurma yardımcısı |
| `wari_kalkan` | KALKAN TAK | `wari_kalkan` | Equip shield hotkey | Kalkan takma kısayolu |
| `wari_silme` | DEBUFF SİLME | `wari_silme` | Auto debuff cleanse | Otomatik debuff silme |
| `firfir` | FIRFIR (SPIN) | `firfir` | Continuous spin (hold/toggle) | Sürekli dönme (tut/aç-kapa) |
| `crazydes` | CRAZY DES | `crazydes` | HP-triggered descend automation | HP tetikli des otomasyonu |

---

## Page 2 — Asas

| key | name | file | purpose (EN) | amaç (TR) |
|---|---|---|---|---|
| `asas` | ASAS | `asas` | Hybrid attack rotation for rogue | Asas için hibrit saldırı kombosu |
| `styx` | STYX / MANA SİLME | `styx` | Mana drain skill helper | Styx / mana silme yardımcısı |
| `otobicak` | OTO BIÇAK | `otobicak` | Auto-dagger combo | Otomatik bıçak komboso |

---

## Page 3 — Archer

| key | name | file | purpose (EN) | amaç (TR) |
|---|---|---|---|---|
| `threefive` | 3-5 OKÇU | `threefive` | 3+5 archer skill chain | 3-5 okçu skill zinciri |
| `icemlr` | ICE / MANA / LR | `icelr` | Ice/mana/light-reaction combo | Ice / mana / LR komboso |
| `ok72` | 72 SKILL | `ok72` | Archer 72-skill helper | Okçu 72 skill yardımcısı |

---

## Common across pages 2-3 (Asas + Archer)

| key | name | file | purpose (EN) | amaç (TR) |
|---|---|---|---|---|
| `minor` | MİNÖR | `minor` | Minor potion cycle | Minor potu döngüsü |
| `m20` | M20 | `m20` | M20 helper | M20 yardımcısı |
| `otocure` | OTO CURE | `otocure` | Auto-cure when affected by ailment | Otomatik cure |
| `otodef` | OTO DEFANS (CC) | `otodef` | Auto-defence on crowd control | CC anında oto defans |
| `oto_explore` | OTO EXPLORE | `oto_explore` | Auto-explore (radar reveal) | Otomatik explore (radar) |
| `birli` | BİRLİ TARAMA | `birli` | First-position scan | İlk sıra tarama |

---

## Page 4 — Smart Pot / Support

| key | name | file | purpose (EN) | amaç (TR) |
|---|---|---|---|---|
| `hpmp` | AKILLI HP/MP | `hpmp` | Threshold-based HP/MP potion auto-use | Eşik tabanlı HP/MP potu |
| `otodurat` | OTO DURATION | `otodurat` | Auto buff timer refresh | Buff süre yenileme |
| `itemchange` | İTEM DEĞİŞME | `itemchange` | Item swap helper | İtem değiştirme |

---

## Page 5 — Self / Custom

| key | name | file | purpose (EN) | amaç (TR) |
|---|---|---|---|---|
| `self_macro_1` | ÖZEL MAKRO 1 | `self_macro` | User-defined custom sequence #1 | Kullanıcı tanımlı özel makro 1 |
| `self_macro_2` | ÖZEL MAKRO 2 | `self_macro` | User-defined custom sequence #2 | Kullanıcı tanımlı özel makro 2 |
| `self_macro_3` | ÖZEL MAKRO 3 | `self_macro` | User-defined custom sequence #3 | Kullanıcı tanımlı özel makro 3 |
| `oto_kontrol` | OTO KONTROL | `otokontrol` | Auto-control region monitor | Otomatik kontrol bölge takibi |
| `ototiklama` | OTO TIKLAMA | `ototiklama` | Image-trigger auto-clicker | Görsel tetikli oto-tıklama |
| `macro_tasarimci` | V5 SELF EDITOR | `MacronuKendinYap` | Visual macro builder (step editor) | Görsel makro tasarımcısı |

---

## Page 6 — Priest

| key | name | file | purpose (EN) | amaç (TR) |
|---|---|---|---|---|
| `priest_goat` | PRIEST GOAT MOD | `priestgoatmod` | Priest attack/heal hybrid mode | Priest atak/heal hibrit mod |
| `priest_attack` | BP ATAK (KITAP/KOL) | `priestattack` | BP attack with book/staff swap | BP atak (kitap/kol değişimli) |
| `priest_skiller` | OTO PRIEST SKILLER | `otopriestskiller` | Configurable skill rotation | Yapılandırılabilir skill rotasyonu |
| `priest_kalkan` | PRIEST KALKAN (LOOP) | `pri_kalkan` | Looping shield cast | Döngülü kalkan dökme |
| `priest_hpmp_heal` | PRIEST OTO HEAL/POT | `Smarthpmppriest` | Priest-specific HP/MP/heal auto-use | Priest için akıllı HP/MP/heal |
| `priest_party_heal` | PARTY HEAL ASİSTANI | `priestpartyheal` | Party member HP scan + heal | Party heal asistanı |

---

## Page 7 — Mage

| key | name | file | purpose (EN) | amaç (TR) |
|---|---|---|---|---|
| `mage_staff` | MAGE STAFF | `magestaff` | Staff attack rotation | Mage staff komboso |
| `restore` | RESTORE SİLME | `restore` | Auto-restore (cleanse) | Otomatik restore |
| `mage_remote_farm` | MAGE UZAK FARM (NOVA) | `magefarm` | Nova area-farm with image scan | Nova ile uzak farm |
| `mage_oto_tp` | MAGE OTO TP | `mageototp` | Auto-TP on low HP threshold | HP düşünce oto TP |
| `mage_pt_cekme` | SIRALI PT ÇEKME | `mageptcekme` | Sequential party-summon | Sıralı party çekme |
| `mage_text_tp` | YAZI İLE TP (CHAT) | `magetexttp` | Chat-keyword triggered TP | Yazı ile tetiklenen TP |

---

## Page 8 — Kurian

| key | name | file | purpose (EN) | amaç (TR) |
|---|---|---|---|---|
| `kurian_attack` | KURIAN SERI SKILL | `kurianseriskill` | Kurian serial skill chain | Kurian seri skill zinciri |

---

## Page 9 — Farm

| key | name | file | purpose (EN) | amaç (TR) |
|---|---|---|---|---|
| `autodrop` | OTOMATİK LOOT | `loot_macro` | Auto-loot dropped items | Otomatik loot toplama |
| `oto_rpr` | OTO RPR & DEĞİŞİM | `otorpr` | Auto repair + weapon swap | Oto tamir + silah değişimi |
| `vip_storage` | VIP DEPOLAMA BOTU | `vip_storage` | Auto-store items in VIP warehouse | VIP depo botu |
| `clan_storage` | CLAN DEPOLAMA BOTU | `clan_storage` | Auto-store items in clan warehouse | Klan depo botu |
| `anti_afk` | ANTI-AFK FARM (PİKSEL) | `antiafkfarm` | Pixel-based anti-AFK | Piksel tabanlı anti-AFK |
| `farm` | FARM BOT | `farm` | Generic farm rotation | Genel farm botu |
| `pet_macro` | PET OTO | `pet` | Auto-pet HP/MP/feed | Pet HP/MP/yem otomasyonu |

---

## Page 10 — General

| key | name | file | purpose (EN) | amaç (TR) |
|---|---|---|---|---|
| `multi` | MULTIBOX | `multi` | Send same input to multiple game windows | Birden çok oyun penceresine girdi |
| `background_bot` | ARKA PLAN BOTU | `background` | Background-window automation | Arka planda otomasyon |
| `upgrade_bot` | UPGRADE BOTU | `upgrade` | Item upgrade automation | İtem upgrade otomasyonu |
| `narki` | NARKI (ITEM KIRDIRMA) | `narki` | Item-breaking automation | İtem kırdırma |
| `usko_otologin` | OTO LOGIN BOTU | `uskootologin` | Auto-login template-driven | Otomatik login botu |
| `notification` | NOTIFICATION | `notification` | Death/DC notifications (Discord/Telegram) | Ölüm/DC bildirimi |
| `flood_plus` | FLOOD MACRO | `chat` | Chat flood / shout helper | Chat flood / shout |

---

## Totals — Toplam

- **Tab pages:** 10
- **Registry entries:** 55
- **Distinct .py files:** 54 *(self_macro_1 / 2 / 3 share `self_macro.py`)*
