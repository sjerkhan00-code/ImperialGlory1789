"""Step 3 and the nation polish: brand-new nations, flags, colours and the playable-nation data.

Called from make_map.py after the provinces and the step-2 reskins are in the database.
New nations are cloned from a template nation (troops, ships, capital building, AI graph, battle
textures) and then given their own keys, names, flags and colours.
"""
import os, re, struct, shutil, math
from igmod import *
import meshgen as MG
import flags as FL
import tga

# key: country enum name (also used for flag files); player key = 'JUG_' + key
NEW_NATIONS = [
    dict(key='PERSIA', name='Persia', adjective='Persian', provinces=[5, 6], capital_prov=5, capital_key='CAP_PERSIA',
         capital='Teheran', template='OTOMANO', template_player='JUG_OTOMANO', models='07Otomano', folder='25Persia',
         units='DefUnidadesArabes.sb', start=[1500, 1600, 300, 1900, 0],
         info='Persia rises again under the new Qajar dynasty. Rich in men but poor in coin, it stands between the Ottoman '
              'Empire and the steppe peoples. Its cavalry is excellent and its mountains are hard to conquer.'),
    dict(key='ARABIA', name='Arabia', adjective='Arabian', provinces=[3, 4], capital_prov=3, capital_key='CAP_ARABIA',
         capital='Diriyah', template='TRIPOLITANIA', template_player='JUG_TRIPOLITANIA', models='24Tripolitania', folder='26Arabia',
         units='DefUnidadesArabes.sb', start=[1100, 1200, 200, 1500, 0],
         info='The emirs of Diriyah are uniting the tribes of the Arabian peninsula. The desert protects them, but it gives little. '
              'Camel riders and fast cavalry are their strength; Oman gives them a window on the sea.'),
    dict(key='TURKESTAN', name='Turkestan', adjective='Turkestani', provinces=[7], capital_prov=7, capital_key='CAP_TURKESTAN',
         capital='Bukhara', template='MARRUECOS', template_player='JUG_MARRUECOS', models='22Marruecos', folder='27Turkestan',
         units='DefUnidadesArabes.sb', start=[1000, 1300, 200, 1500, 0],
         info='The Emirate of Bukhara rules the old Silk Road cities east of the Caspian Sea. Trade brings wealth, '
              'but Russia and Persia watch its borders closely.'),
    dict(key='CHECHNYA', name='Chechenya', adjective='Chechen', provinces=[11], capital_prov=11, capital_key='CAP_CHECHNYA',
         capital='Aldy', template='OTOMANO', template_player='JUG_OTOMANO', models='07Otomano', folder='67Chechnya',
         units='DefUnidadesArabes.sb', start=[1800, 1600, 400, 1800, 0],
         info='Sheikh Mansur has raised the mountain peoples of the North Caucasus against the Russian advance. The forests '
              'and gorges of Chechenya and Dagestan are a fortress; the Ottomans are distant friends, Russia a near enemy.'),
]
# step-2 reskins made playable: player key -> (country key, flag design, info text)
RESKIN_PLAYABLE = {
    # Moldavia's and Saxony's slots hold two regions of the independent peoples (world_nations.RESKIN_REGIONS): not playable
    # (designs REGION_*: the regions' banner in each region's own map colour, world_nations.REGION_COLOUR)
    'JUG_MOLDAVIA': ('MOLDAVIA', 'REGION_MOLDAVIA', 'Southern Kingdoms', 'Southern', 'The kingdoms of the Kongo, the Lunda, the Rozvi and Madagascar.'),
    'JUG_SAJONIA': ('SAJONIA', 'REGION_SAJONIA', 'Sahel Kingdoms', 'Sahelian', 'The oases of the Sahara and the kingdoms of the Niger and Volta.'),
    'JUG_HANNOVER': ('HANNOVER', 'KAZAKHSTAN', 'Kazakh Khanate', 'Kazakh',
                     'The Kazakh hordes roam the great steppe between Russia and Turkestan. Their horsemen are feared, '
                     'but the khanate has few towns and little industry.'),
}
# the original minor nations, made playable as they are: player key -> (Models/BANDERAS file, Select Empire text)
MINORS_PLAYABLE = {
    'JUG_ESPANYA': ('Espanya', 'Spain still rules a vast empire overseas, but at home it is a tired power between France and the sea. '
                               'Its fleet and its American silver are its strength.'),
    'JUG_OTOMANO': ('Otomano', 'The Sultan in Constantinople rules from the Balkans to Arabia. The empire is huge but slow, '
                               'and Russia and Austria press on its borders.'),
    'JUG_EGIPTO': ('Egipto', 'Egypt, rich from the Nile and the trade between two seas, is nominally Ottoman but goes its own way.'),
    'JUG_DOS_SICILIAS': ('Dos_Sicilias', 'The Kingdom of the Two Sicilies holds southern Italy and Sicily, '
                                         'a Mediterranean crossroads with a modest fleet.'),
    'JUG_DINAMARCA': ('Dinamarca', 'Denmark and Norway guard the gates of the Baltic. A small kingdom with a proud navy.'),
    'JUG_SUECIA': ('Suecia', 'Sweden, once the master of the Baltic, rules Sweden and Finland and dreams of its old glory.'),
    'JUG_PORTUGAL': ('Portugal', 'Portugal looks to the ocean and its colonies, an old ally of Britain at the edge of Europe.'),
    'JUG_LOMBARDIA': ('Lombardia', 'Lombardy and Venice, the rich plains and trading cities of northern Italy.'),
    'JUG_PIAMONTE': ('Piamonte', 'Piedmont-Sardinia, a small but ambitious kingdom at the foot of the Alps.'),
    'JUG_EPAPALES': ('EPapales', 'The Papal States rule central Italy from Rome, with more influence than armies.'),
    'JUG_RHELVETICA': ('RHelvetica', 'The Swiss cantons, a mountain fortress in the heart of Europe.'),
    'JUG_BATAVIA': ('Batavia', 'The Netherlands, a nation of merchants and sailors with a worldwide trade.'),
    'JUG_POLONIA': ('Polonia', 'Poland, a great old commonwealth squeezed between Prussia, Austria and Russia.'),
    'JUG_MARRUECOS': ('Marruecos', 'The Sultanate of Morocco, between the Atlantic, the Atlas mountains and the Sahara.'),
    'JUG_TUNEZ': ('Tunez', 'Tunis, a Barbary state of corsairs and caravan trade on the African shore.'),
    'JUG_TRIPOLITANIA': ('Tripolitania', 'Tripoli, a Barbary regency whose corsairs raid the Mediterranean.'),
}
PLAYABLE = (['JUG_FRANCIA', 'JUG_AUSTRIA', 'JUG_PRUSIA', 'JUG_RUSIA', 'JUG_GRAN_BRETANYA',
             'JUG_HANNOVER', 'JUG_PERSIA', 'JUG_ARABIA', 'JUG_TURKESTAN']
            + list(MINORS_PLAYABLE))
# the larger powers of the bigger map (tools/world_nations.py), also playable
WORLD_PLAYABLE = ['QING', 'JAPAN', 'MARATHA', 'ETHIOPIA']
PLAYABLE += ['JUG_' + k for k in WORLD_PLAYABLE] + ['JUG_CHECHNYA']
# small AI nations that skip AI planning each turn (only defend); filled with .mng player ids by make_map
CAMERA_ZOOM_MIN = -4.0     # campaign camera: original Camara.sb except this (original -2)
AI_SKIP = ['INDEPENDENT', 'PRINCES', 'SHEIKHS', 'NILE', 'PACIFIC', 'MOLDAVIA', 'SAJONIA']   # regional independent peoples
AI_ROUTE_VIA_CAP = 8      # exe patch 12: via-nodes tried per AI sea route (was all; 41 for a big empire)
AI_ROUTE_REBUILD_EVERY = 64  # exe patch 14: route-table rebuilds for the same AI only every 64th trigger (16 gave Britain ~24 s)
AI_YIELD_EVERY = 8          # exe patch 16: the AI ends a frame after every 8th command (window keeps answering)
TROOP_STRENGTH = {'CHECHNYA': 2.0}    # the user's wish: Chechen troops twice as strong as everyone else's
# per-type override of TROOP_STRENGTH (user 2026-10-21: the Chechen elite warriors much stronger), each value capped at
# STRENGTH_TYPE_CAP = 1.5 x the highest value of any original troop (100). NOTE: record ints 16..21 feed neither the
# info panel nor the real-time battle (both use Game/GameModes/ModeloCombate.dt per troop type); see START_LEVEL and
# BATTLE_STRENGTH (exe patch 29, the real battle multiplier).
TROOP_STRENGTH_TYPE = {('CHECHNYA', 'ELITE'): 4.0, ('CHECHNYA', 'CAB_ELITE'): 4.0}
STRENGTH_TYPE_CAP = 150
NO_CAMELS = {'CHECHNYA', 'QING', 'JAPAN'}     # template troops CAM_* are not cloned for these
# troop types a new nation gets on top of its template's roster: key -> [(troop type, country whose record is cloned)].
# Poland's grenadiers / dragoons / cuirassiers carry the game's generic names; Jaegers and Guard exist only for the
# great powers (Russia: 'Jaegers', 'Ismailovski Guard'), the elite horse only for Egypt (Mamelukes) and Poland (lancers):
# those three get the nation's own names (EXTRA_TROOP_TEXT).
# SAVE COMPATIBILITY: add_nations appends these records after every other troop, in THIS dict's order (not in
# NEW_NATIONS order), so new entries go at the END of the dict and existing entries are never reordered or removed:
# CHECHNYA = ids 564..569 (installed 2026-10-21), then the signature elites of the other new great powers (2026-10-21,
# report_ideas_research.md tip 5: one elite type mask per nation, only where its roster lacks that type; Maratha and
# Ethiopia already own CAB_ELITE through their Egyptian template, so they get a name and uniform, no new record).
EXTRA_TROOPS = {'CHECHNYA': [('GRANADERO', 'POLONIA'), ('CAZADOR', 'RUSIA'), ('ELITE', 'RUSIA'),
                             ('CAB_DRAGON', 'POLONIA'), ('CAB_CORACERO', 'POLONIA'), ('CAB_ELITE', 'EGIPTO')],
                'QING': [('CAB_ELITE', 'EGIPTO')],
                'JAPAN': [('ELITE', 'RUSIA')],
                'PERSIA': [('ELITE', 'RUSIA')],
                'ARABIA': [('CAB_ELITE', 'EGIPTO')],
                'TURKESTAN': [('CAB_ELITE', 'EGIPTO')]}
# (nation, troop type) -> (name, description[, short description]): keys LTEXT_<NATION>_<TYPE> /
# LTEXT_DESC_<NATION>_<TYPE>(_SHORT; the game adds _SHORT to the description key) in
# Management/TiposTropas/TiposTropasNeutral.sb (texts_new); Russian in build/i18n/ru_troops.json. _clone_troop also
# renames a template clone of that type (Maratha / Ethiopia CAB_ELITE, the Egyptian 'Mamelukes'): text keys only.
# Names at most 22 characters (the longest original troop name, English and Russian); latin1 files: ASCII only.
EXTRA_TROOP_TEXT = {
    ('CHECHNYA', 'CAZADOR'): ('Mountain Marksmen',
                              'Hunters from the high auls of Chechenya and Dagestan, they know every gorge and forest path. '
                              'From cover their long rifles strike down officers long before the enemy can reply.',
                              # _SHORT (tooltip) added 2026-10-22: it was missing, so the tooltip was blank. Stat sentence of
                              # the original Russian Jaegers (same type mask); ELITE after the Ismailovski Guard, CAB_ELITE
                              # after the Mamelukes, as the other new elites below.
                              '\\cFFFF61Mountain Marksmen\\c: Light Infantry-like unit, though better skilled in both '
                              'ranged attacks and melee combat.'),
    ('CHECHNYA', 'ELITE'): ("Sheikh Mansur's Murids",
                            'The sworn disciples of Sheikh Mansur, who have given their lives to the holy war. They hold '
                            'their ground where others break and fall on the enemy with sabre and dagger.',
                            "\\cFFFF61Sheikh Mansur's Murids\\c: The elite Infantry unit of the Chechen army, with excellent "
                            'ranged attacks and melee combat.'),
    ('CHECHNYA', 'CAB_ELITE'): ('Uzden Horse Guard',
                                'The noble horsemen of the mountain clans in mail and cherkeska. Superb riders and '
                                'swordsmen, their charge decides battles.',
                                '\\cFFFF61Uzden Horse Guard\\c: Elite Chechen Cavalry unit, fierce in melee combat, but '
                                'incapable of ranged attacks.'),
    # signature elites of the new great powers (2026-10-21; c. 1789). Short texts follow the originals of the same
    # type (Mamelukes for CAB_ELITE, Spanish Guerrillas for ELITE): the stats are the type's (ModeloCombate.dt).
    ('QING', 'CAB_ELITE'): ('Manchu Bannermen',
                            "Manchu horsemen of the Upper Three Banners, the emperor's own. Raised in the saddle from "
                            'childhood, they guard Beijing and ride wherever the empire must win.',
                            '\\cFFFF61Manchu Bannermen\\c: Elite Chinese Cavalry unit, fierce in melee combat, but incapable '
                            'of ranged attacks.'),
    ('JAPAN', 'ELITE'): ('Hatamoto Samurai',
                         "The shogun's own retainers, sworn to the Tokugawa house for generations. Trained with sword and "
                         'musket alike, they stand firm where lesser troops would break.',
                         '\\cFFFF61Hatamoto Samurai\\c: The elite Infantry unit of the Japanese army, with excellent ranged '
                         'attacks and melee combat.'),
    ('MARATHA', 'CAB_ELITE'): ('Huzurat Horse',
                               "The Peshwa's household cavalry at Pune, picked men on the best horses of the Deccan. "
                               'Swift and hard-hitting, they have carried the Maratha banners from the Deccan to Delhi.',
                               '\\cFFFF61Huzurat Horse\\c: Elite Maratha Cavalry unit, fierce in melee combat, but incapable '
                               'of ranged attacks.'),
    ('PERSIA', 'ELITE'): ('Jazayerchi Musketeers',
                          "Musketeers of the shah's guard, armed with the jazayer, a heavy long-barrelled musket. Since "
                          "Nader Shah's day they have been the steady core of every Persian army.",
                          '\\cFFFF61Jazayerchi Musketeers\\c: The elite Infantry unit of the Persian army, with excellent '
                          'ranged attacks and melee combat.'),
    ('ETHIOPIA', 'CAB_ELITE'): ('Oromo Horsemen',
                                'Horsemen of the Yejju Oromo lords, the real masters of Gondar in the Era of the Princes. '
                                'Bold riders with spear and shield, they fall upon the enemy before he can form.',
                                '\\cFFFF61Oromo Horsemen\\c: Elite Ethiopian Cavalry unit, fierce in melee combat, but '
                                'incapable of ranged attacks.'),
    ('ARABIA', 'CAB_ELITE'): ('Najdi Horsemen',
                              'Warriors of the towns and tribes of Najd, mounted on the finest Arabian horses. Under the '
                              'emirs of Diriyah they strike far across the desert and are gone before the enemy can gather.',
                              '\\cFFFF61Najdi Horsemen\\c: Elite Arabian Cavalry unit, fierce in melee combat, but incapable '
                              'of ranged attacks.'),
    ('TURKESTAN', 'CAB_ELITE'): ('Turkmen Horse',
                                 'Turkmen tribesmen in the service of the Emir of Bukhara, riding the famous long-legged '
                                 'horses of the Kara Kum. Feared raiders, they strike hard and vanish into the desert.',
                                 '\\cFFFF61Turkmen Horse\\c: Elite Turkestani Cavalry unit, fierce in melee combat, but '
                                 'incapable of ranged attacks.'),
}
# Own troop names for the Arab-template clones (Japan raised "Arabian Line Infantry") and the reskin slots (Kazakhs,
# Sahel, Southern Kingdoms: generic European names): tools/troop_texts.py (2026-10-22), 68 (nation, type) pairs with
# English name / description / short text; translations build/i18n/<code>_troops.json. SAVE-SAFE: only the two text
# keys inside existing troop records change (_clone_troop for the clones, the RESKIN_TROOP_COUNTRIES pass in
# add_nations for the original Hannover / Sajonia / Moldavia records); ids, order, enum names, owners stay.
import troop_texts as _TT
EXTRA_TROOP_TEXT.update(_TT.TEXT)
RESKIN_TROOP_COUNTRIES = ('HANNOVER', 'SAJONIA', 'MOLDAVIA')     # = the countries of RESKIN_PLAYABLE
# camel troop types (cloned from the template, ids kept for save games) on a camel-less unit file (Asia / Africa /
# Pacific / Caucasus, tools/art/units/cultures.unit_files) ride horses in battle: CAM_LANCERO the lancer body,
# CAM_TIRADOR the hussar body. Their name follows the model (review V2): type -> (name, description, short
# description), keys LTEXT_<TYPE>_HORSE / LTEXT_DESC_<TYPE>_HORSE(_SHORT; the game adds _SHORT to the description key)
# in TiposTropasNeutral.sb (texts_new); Russian in build/i18n/ru_troops.json. Stats stay the camel types'.
HORSE_CAMEL_TEXT = {
    'CAM_LANCERO': ('Heavy Lancers',
                    'Heavy Lancers ride big, hardy horses. Slower than ordinary Lancers but harder to break, they are a '
                    'powerful unit with great endurance.',
                    '\\cFFFF61Heavy Lancers\\c: Similar to Lancers; heavier mounts make this unit more resistant to attack, '
                    'but slower.'),
    'CAM_TIRADOR': ('Mounted Marksmen',
                    'Mounted Marksmen ride to the fight and shoot from the saddle. Their main strengths are their great '
                    'mobility and accurate aim.',
                    '\\cFFFF61Mounted Marksmen\\c: Similar to Dragoons, but less resistant to attack.'),
}
CAMEL_BODIES = ('GenericoA4', 'GenericoG3')      # the camel-mounted bodies (DefUnidadesArabes.sb CAM_TIRADOR / CAM_LANCERO)
_HORSE_CAMELS = {}


def rides_horse(key, tname):
    """True when nation `key`'s unit file (cultures.UNIT_FILE_OF, else its NEW_NATIONS 'units') draws the camel type
    tname on a horse body."""
    if tname not in HORSE_CAMEL_TEXT:
        return False
    if key not in _HORSE_CAMELS:
        import sys as _s
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'art', 'units')
        if d not in _s.path:
            _s.path.insert(0, d)
        import cultures as CU
        nn = next((n for n in NEW_NATIONS if n['key'] == key), None)
        f = CU.UNIT_FILE_OF.get(key, nn['units'] if nn else None)
        txt = CU.unit_text(f) if f else ''
        _HORSE_CAMELS[key] = {t: os.path.splitext(os.path.basename(u[0]))[0] not in CAMEL_BODIES
                              for t in HORSE_CAMEL_TEXT for u in [CU.unit_textures(txt, t)] if u}
    return _HORSE_CAMELS[key].get(tname, False)


TRAIN_TURNS = {'CHECHNYA': 1}         # recruitment turns (troop record int 8) of every troop of the nation (user 2026-10-21)
# starting experience of the nation's newly raised battalions: record int 10 = level 0..4 (novice .. elite; selects the
# per-level combat records of ModeloCombate.dt, i.e. real battle strength) and int 11 = experience points of that level
# (DefReglasResolucionBatalla.sb EXP_RANGOS_BATALLON). Officers keep theirs.
START_LEVEL = {'CHECHNYA': 2}
START_LEVEL_TYPE = {('CHECHNYA', 'ELITE'): 4, ('CHECHNYA', 'CAB_ELITE'): 4}
# exe patch 29: battle strength in real-time battles and auto-resolve (damage dealt x factor, damage taken / factor), per
# troop record owner (country key) with per-(country, troop type) overrides; any battalion of these troop types, whoever
# owns it (human or AI). Values are rounded to 1/16, range 1/16 .. 15.9. NOTE: START_LEVEL above stacks on top of this.
# The factor works on both damage dealt and damage taken, so the exchange ratio is factor²: 1.4 -> about 2x as strong
# (the user's "twice as strong"), 2.0 for the elites -> about 4x ("much stronger").
BATTLE_STRENGTH = {'CHECHNYA': 1.4}
BATTLE_STRENGTH_TYPE = {('CHECHNYA', 'ELITE'): 2.0, ('CHECHNYA', 'CAB_ELITE'): 2.0}
LEVEL_POINTS = (0, 6, 12, 18, 25)
OFFICER_TYPES = {'TENIENTE', 'CAPITAN', 'GENERAL', 'MARISCAL', 'MARISCAL_RED'}
AI_SKIP_IDS = []

FIG = 'Game/GameModes/Gestion/Figuras/'
ATLAS = 'Game/UI/Mod/BanderasMod.tga'

OFFICERS = {}       # key -> officer names; the pools of all new nations are HIST_OFFICERS, set after world_nations.install below
SHIP_WORDS = {
    'PERSIA': ['Simorgh', 'Rostam', 'Shahnameh', 'Bushehr', 'Hormuz', 'Kharg', 'Qeshm', 'Bandar Abbas', 'Shiraz', 'Isfahan',
               'Tabriz', 'Mashhad', 'Kerman', 'Yazd', 'Rasht', 'Gilan', 'Mazandaran', 'Persepolis', 'Pasargad', 'Ctesiphon',
               'Ahura', 'Mithra', 'Anahita', 'Homa', 'Sepehr', 'Toufan', 'Darya', 'Shir', 'Babr', 'Oghab', 'Shahin',
               'Sorush', 'Azar', 'Khorshid', 'Mah', 'Setareh', 'Nahid', 'Bahman', 'Sahand', 'Damavand', 'Alborz', 'Zagros',
               'Karun', 'Aras', 'Sefid Rud', 'Zayandeh', 'Lar', 'Hirmand', 'Jask', 'Lengeh', 'Chabahar', 'Bam', 'Sistan',
               'Khuzestan', 'Fars'],
    'ARABIA': ['Al-Diriyah', 'Najd', 'Hasa', 'Qatif', 'Muscat', 'Sohar', 'Sur', 'Nizwa', 'Dhofar', 'Ras al-Hadd', 'Al-Fath',
               'Al-Nasr', 'Al-Saqr', 'Al-Shamal', 'Al-Janub', 'Al-Badr', 'Al-Hilal', 'Al-Najm', 'Al-Bahr', 'Al-Rih', 'Al-Barq',
               'Al-Asad', 'Al-Faris', 'Al-Sayf', 'Al-Rumh', 'Al-Shahin', 'Al-Nimr', 'Al-Dhib', 'Al-Ghazal', 'Al-Khayl',
               'Al-Jamal', 'Al-Nakhl', 'Al-Lulu', 'Al-Marjan', 'Al-Yaqut', 'Al-Zumurrud', 'Al-Dhahab', 'Al-Fidda', 'Al-Qamar',
               'Al-Shams', 'Bahrain', 'Kuwait', 'Zubara', 'Julfar', 'Masirah', 'Khasab', 'Sharjah', 'Ajman', 'Dibba',
               'Khor Fakkan', 'Qalhat', 'Mirbat', 'Salalah', 'Hadramawt', 'Mukalla'],
    'TURKESTAN': ['Bukhara', 'Samarkand', 'Khiva', 'Merv', 'Urgench', 'Kokand', 'Tashkent', 'Karshi', 'Termez', 'Nasaf',
                  'Amu Darya', 'Syr Darya', 'Zarafshan', 'Kyzyl Kum', 'Kara Kum', 'Aral', 'Khwarezm', 'Sogdia', 'Bactria',
                  'Timur', 'Ulugh Beg', 'Babur', 'Shaybani', 'Registan', 'Ark', 'Kalyan', 'Lyabi Hauz', 'Chorsu', 'Shahrisabz',
                  'Gijduvan', 'Kermine', 'Chardzhou', 'Kerki', 'Panj', 'Hissar', 'Kulob', 'Garm', 'Darvaz', 'Badakhshan',
                  'Pamir', 'Tian Shan', 'Altai', 'Turan', 'Oxus', 'Jaxartes', 'Kara Bugaz', 'Mangyshlak', 'Ustyurt',
                  'Krasnovodsk', 'Balkan', 'Kopet Dag', 'Ashkhabad', 'Nisa', 'Abiverd', 'Sarakhs'],
}
HEIRS = {}          # key -> (female, male) heir names; the new nations' are HIST_HEIRS, set after world_nations.install below
SHIP_WORDS['CHECHNYA'] = ['Terek', 'Sunzha', 'Argun', 'Aldy', 'Derbent', 'Tarki', 'Kizlyar', 'Andi', 'Vedeno', 'Shali',
                          'Sulak', 'Assa', 'Fortanga', 'Bass', 'Aksai', 'Yaryksu', 'Sharo Argun', 'Chanty Argun', 'Martan',
                          'Gekhi', 'Urus Martan', 'Germenchuk', 'Mayrtup', 'Kurchaloy', 'Dargo', 'Itum Kale', 'Kezenoi Am',
                          'Tebulos', 'Kazbek', 'Elbrus', 'Bazardyuzyu', 'Shalbuzdag', 'Andi Koysu', 'Avar Koysu', 'Samur',
                          'Endirey', 'Gudermes', 'Kumukh', 'Khunzakh', 'Gimry', 'Akhulgo', 'Tsontoroy', 'Benoy', 'Nokhchi',
                          'Ichkeria', 'Lamaroy', 'Galgai', 'Nashkh', 'Kabarda', 'Malka', 'Baksan', 'Chegem', 'Laba',
                          'Kuban', 'Anapa']


# AI nations of the bigger map (1789)
import sys as _sys, world_nations as _WN
_WN.install(_sys.modules[__name__])


# ---------------------------------------------------------------- historical officers and heirs (2026-10-21)
# Officer name pools of the new nations (the exe reads 48 names per nation, LTEXT_GESTION_NOMBRE_MANDO_JUG_<KEY>n, and hands
# them out IN ORDER to new officers; after the last name it starts again with the title II, III ... from
# LTEXT_GESTION_MANDO_TITULO): real commanders and statesmen of about 1785-95 stand first, so the starting generals and the
# first recruits carry their names. Russian versions: build/i18n/ru_names.json (same key, same order). Text only: no enum,
# no mng record and no save-game id depends on a name.
OFFICER_NAME_MAX = 24        # the longest original English name is 24 characters ('Muhammad Pasha Busatlija'; Russian 22)
HEIR_NAME_MAX = 15           # the longest original heir name ('Heinrich Ludwig', 'Louis Philipppe'; Russian 15)
HIST_OFFICERS = {
    'PERSIA': [
        # Agha Mohammad Khan, his Qajar brothers, nephew Baba Khan, the last Zands and their generals
        'Agha Mohammad Khan', 'Baba Khan', 'Lotf Ali Khan', 'Jafar Khan Zand', 'Hajji Ebrahim', 'Ali Qoli Khan',
        'Hossein Qoli Khan', 'Jafar Qoli Khan', 'Reza Qoli Khan', 'Morteza Qoli Khan', 'Seyyed Morad Khan',
        'Sheikh Veis Khan', 'Hosayn Qoli Donboli', 'Mostafa Qoli Khan', 'Mehdi Qoli Khan', 'Rustam Khan Zand',
        'Soleyman Khan Qajar', 'Mehdi Beg Khalatbari', 'Sadeq Khan Shaqaqi', 'Shahrokh Shah', 'Hedayat-Allah Khan',
        'Mirza Shafi', 'Mirza Asadollah', 'Mirza Ismail', 'Sheikh Naser', 'Mohammad Zahir Khan',
        # later and earlier figures of the same realm, then period names
        'Karim Khan', 'Zaki Khan', 'Sadegh Khan', 'Ali Morad', 'Taqi Khan', 'Amir Mohammad Khan', 'Khosrow Khan',
        'Mohammad Hassan', 'Allah Yar', 'Esmail Beg', 'Nader Qoli', 'Jahangir Khan', 'Kazem Beg', 'Hamzeh Mirza',
        'Hormoz Khan', 'Yazdan Beg', 'Farhad Mirza', 'Shahrokh Beg', 'Babak Beg', 'Bahram Mirza', 'Parviz Mirza',
        'Gudarz Mirza',
    ],
    'ARABIA': [
        # the Al Saud house (Abdulaziz and his sons Saud, Abdullah, Abd al-Rahman, Umar) and the Wahhabi scholar
        'Abdulaziz Al Saud', 'Saud ibn Abdulaziz', 'Abdullah ibn Muhammad', 'Abd al-Rahman Al Saud',
        'Umar ibn Abdulaziz', 'Ibn Abd al-Wahhab', 'Abdullah ibn Ufaysan', 'Abdullah ibn Saud', 'Turki ibn Abdullah',
        'Faisal ibn Turki',
        # later and earlier figures of the same realm, then period names
        'Muhammad ibn Saud', 'Uthman ibn Muammar', 'Mishari ibn Saud', 'Thunayan ibn Saud', 'Mutlaq al-Mutairi',
        'Rashid al-Harbi', 'Fahd al-Dawsari', 'Majid al-Qahtani', 'Nasser al-Otaibi', 'Khalid al-Shammari',
        'Omar al-Anazi', 'Yusuf al-Ajmi', 'Hamza al-Subaie', 'Mishal al-Harbi', 'Bandar al-Sudairi',
        'Fawaz al-Sharari', 'Nayef al-Ruwaili', 'Awad al-Balawi', 'Sulayman al-Huwaiti', 'Hadi al-Murri',
        'Fahad al-Ajmani', 'Ghazi al-Mutairi', 'Salim al-Harithi', 'Hasan al-Ahsai', 'Mansur al-Yami',
        'Dhaifallah al-Juhani', 'Ahmad al-Jalahma', 'Ibrahim al-Hasan', 'Hamad ibn Nasir', 'Ali ibn Hussein',
        'Saqr al-Qasimi', 'Rashid al-Nuaimi', 'Sultan ibn Ahmad', 'Hilal al-Busaidi', 'Sayf al-Yarubi',
        'Muhanna al-Ghafiri', 'Said ibn Sultan', 'Ali ibn Abd al-Wahhab',
    ],
    'TURKESTAN': [
        # Shah Murad of Bukhara and his Manghit house, the Khiva and Kokand rulers
        'Shah Murad', 'Haydar Tora', 'Daniyal Biy', 'Avaz Inaq', 'Narbuta Biy', 'Alim Khan', 'Eltuzar Inaq',
        'Muhammad Rahim Biy', 'Erdeni Biy', 'Umar Khan',
        # later and earlier figures of the same realm, then period names
        'Rahim Biy', 'Muhammad Amin', 'Allah Quli', 'Rahim Quli', 'Qutlugh Murad', 'Kurban Bek', 'Ernazar Bek',
        'Tashmuhammad', 'Nurmuhammad', 'Abdusamad', 'Sayyid Mir', 'Ismail Tora', 'Ishan Khoja', 'Bahadur Khoja',
        'Yusuf Bek', 'Karim Berdi', 'Aman Geldi', 'Ata Murad', 'Durdy Bek', 'Gurban Nazar', 'Hojamyrat', 'Kakajan',
        'Mammet Bek', 'Nury Berdi', 'Orazgeldi', 'Pirnazar', 'Rejep Bek', 'Saparmyrat', 'Tagan Bek', 'Usman Bek',
        'Velmyrat', 'Yagmyr Bek', 'Akbar Bek', 'Bayram Ali', 'Mahmud Biy', 'Hakim Biy', 'Murad Bek', 'Ibrahim Biy',
    ],
    'CHECHNYA': [
        # Sheikh Mansur, his Kabardian and Ottoman allies (Dol Mudarov, Batal Hussein Pasha) and the Dagestani khans
        'Sheikh Mansur', 'Dol Mudarov', 'Batal Hussein Pasha', 'Beibulat Taimiev', 'Uma Duev', 'Misost Bamat',
        'Dzhambulat', 'Ali Sultan', 'Tashav Haji', 'Akhverdi Mahoma', 'Shamkhal Murtazali', 'Nutsal Khan',
        'Surkhay Khan',
        # later and earlier figures of the same realm, then period names
        'Baysungur', 'Aldam Gezi', 'Soltamurad', 'Gaybulla', 'Adilgirey', 'Kuchuk Bek', 'Edi Mulla', 'Shoip Mulla',
        'Tagir Mulla', 'Ahmad Khan', 'Umalat Bek', 'Chopan Shamkhal', 'Mahomet Kadi', 'Aslanbek', 'Zaurbek',
        'Dzhabrail', 'Elmurza', 'Isa Gendergenoi', 'Sultan Murad', 'Arslan Bek', 'Bei Mulla', 'Yusup Hadji',
        'Abdurrahman', 'Iskhak Bek', 'Batyrbek', 'Kunta Bek', 'Hamzat Bek', 'Kazi Mulla', 'Khasbulat', 'Talkhig',
        'Ismail Bek', 'Daud Mirza', 'Kurban Ali', 'Musa Hadji', 'Magomed Bek',
    ],
    'QING': [
        # the generals of the 1787-96 campaigns (Taiwan, Vietnam, Nepal, Miao) and ministers of Qianlong
        "Fuk'anggan", 'Hailancha', 'Agui', 'Heshen', 'Sun Shiyi', 'Li Shiyao', "Fuchang'an", 'Xu Shiheng',
        'Ba Zhong', 'Helin', 'Mingliang', 'Eldengbao', 'Lebao', 'Ehui', 'Yang Yuchun', 'Chang Ling', 'Qing Gui',
        'Bao Ning', 'Yang Fang', 'Fengshen Yinde', 'Nayancheng', 'Zhu Gui', 'Dong Gao', 'Li Changgeng', 'Hui Ling',
        # later and earlier figures of the same realm, then period names
        'Wang Jie', 'Liu Yong', 'Ji Yun', 'Fuheng', 'Ming Rui', 'Zhang Guangsi', 'Nasutu', 'Yue Zhongqi', 'Bandi',
        'Daldangga', 'Yongchang', 'Yarhashan', 'Fude', 'Aligun', 'Yang Yingju', 'Wenfu', 'Zhaohui', 'Shuhede',
        'Qingfu', 'Bao Tai', 'Luo Siju', 'Wu Xiongguang', 'Songyun',
    ],
    'JAPAN': [
        # the rojuu and daimyo of the Kansei reforms and the explorers of Ezo
        'Matsudaira Sadanobu', 'Matsudaira Nobuakira', 'Tanuma Okitsugu', 'Honda Tadakazu', 'Toda Ujinori',
        'Abe Masatomo', 'Mizuno Tadatomo', 'Hasegawa Nobutame', 'Matsumae Michihiro', 'Mogami Tokunai',
        'Hayashi Shihei', 'Kudo Heisuke', 'Tokugawa Ienari', 'Tokugawa Harusada', 'Shimazu Shigehide',
        'Date Shigemura', 'Hosokawa Shigekata', 'Uesugi Harunori', 'Nabeshima Harushige', 'Maeda Harunaga',
        # later and earlier figures of the same realm, then period names
        'Matsudaira Harusato', 'Mori Haruchika', 'Ii Naohide', 'Sakai Tadazumi', 'Ogasawara Tadahiro',
        'Kuroda Harutaka', 'Ikeda Harumasa', 'Asano Shigeakira', 'Hachisuka Haruaki', 'Tsugaru Nobuharu',
        'Toda Tadato', 'Hotta Masanari', 'Ota Sukeyoshi', 'Tokugawa Muneharu', 'Tokugawa Harutomi', 'Ino Tadataka',
        'Honda Toshiaki', 'Otsuki Gentaku', 'Sugita Genpaku', 'Kondo Juzo', 'Mamiya Rinzo', 'Takahashi Yoshitoki',
        'Matsumoto Hidemochi', 'Kakizaki Hakyo', 'Tokugawa Ieharu', 'Shimazu Narinobu', 'Ii Naoyuki',
        'Hotta Masaatsu',
    ],
    'MARATHA': [
        # Mahadji Shinde and his generals, the Holkars, the Peshwa court and de Boigne
        'Mahadji Shinde', 'Tukoji Holkar', 'Nana Phadnavis', 'Parashuram Bhau', 'Haripant Phadke',
        'Daulat Rao Shinde', 'Benoit de Boigne', 'Ahilyabai Holkar', 'Raghuji Bhonsle', 'Ambaji Inglia',
        'Gopal Rao Bhau', 'Lakwa Dada', 'Jiva Dada Bakshi', 'Rane Khan', 'Appa Khande Rao',
        # later and earlier figures of the same realm, then period names
        'Yashwant Rao Holkar', 'Malhar Rao Holkar', 'Sakharam Bapu', 'Manaji Angre', 'Baji Rao II',
        'Sawai Madhavrao', 'Chimnaji Appa', 'Amrut Rao', 'Pierre Perron', 'Sarje Rao Ghatge', 'Manaji Gaekwad',
        'Govind Rao Gaekwad', 'Fateh Singh Gaekwad', 'Shahu II', 'Bapu Gokhale', 'Damaji Gaekwad', 'Balaji Rao',
        'Raja Ram', 'Trimbak Rao', 'Anand Rao', 'Khande Rao', 'Moro Pant', 'Govind Pant', 'Ganesh Pant',
        'Ramchandra Pant', 'Visaji Krishna', 'Haibat Rao', 'Naro Pant', 'Bhiwa Rao', 'Appa Saheb', 'Balwant Rao',
        'Sadashiv Rao', 'Vithal Rao',
    ],
    'ETHIOPIA': [
        # the rases of the Zemene Mesafint and the puppet emperors
        'Ras Aligaz', 'Ras Wolde Selassie', 'Ras Hailu Yosedeq', 'Ras Ali I', 'Ras Wand Bewossen', 'Ras Fasil',
        'Ras Goshu', 'Ras Mikael Sehul', 'Tekle Giyorgis', 'Hezqeyas', 'Iyasu III', 'Tekle Haymanot', 'Ras Gugsa',
        'Asfa Wossen',
        # later and earlier figures of the same realm, then period names
        'Ras Dori', 'Ras Yimam', 'Ras Marye', 'Ras Ali II', 'Sabagadis Woldu', 'Wube Haile Mariam', 'Kenfu Hailu',
        'Sahle Selassie', 'Dullu', 'Fitawrari Bahru', 'Fitawrari Gebre', 'Fitawrari Haile', 'Fitawrari Tessema',
        'Dejazmach Aberra', 'Dejazmach Wolde', 'Dejazmach Tesfaye', 'Dejazmach Mengesha', 'Dejazmach Alula',
        'Dejazmach Zewde', 'Kenyazmach Mekonnen', 'Kenyazmach Gebre', 'Grazmach Haile', 'Grazmach Tekle',
        'Azmach Wolde', 'Azmach Mulat', 'Balambaras Kidane', 'Balambaras Desta', 'Blatta Yohannes',
        'Liqe Mekwas Tamrat', 'Fitawrari Kassa', 'Dejazmach Hailu', 'Ras Gebre', 'Dejazmach Gebru', 'Azmach Desta',
    ],
    'INDEPENDENT': [
        # Tay Son and Nguyen generals, Burmese and Siamese commanders of 1785-86, the court of King Jeongjo, Malay sultans
        'Nguyen Hue', 'Nguyen Nhac', 'Nguyen Lu', 'Ngo Van So', 'Phan Van Lan', 'Tran Quang Dieu', 'Vo Van Dung',
        'Bui Thi Xuan', 'Nguyen Anh', 'Pigneau de Behaine', 'Vo Tanh', 'Nguyen Van Thanh', 'Le Van Duyet',
        'Bodawpaya', 'Thado Minsaw', 'Thado Thiri Maha Uzana', 'Maha Thiri Thihathu', 'Nemyo Nawrahta',
        'Minhla Kyawdin', 'Chaophraya Chakri', 'Maha Sura Singhanat', 'Anurak Devesh', 'Thepharirak',
        'Chao Phraya Mahasena', 'Chao Kawila',
        # later and earlier figures of the same realm, then period names
        'Yi San', 'Chae Je-gong', 'Seo Yu-rin', 'Yi Byeong-mo', 'Yi Deok-mu', 'Baek Dong-su', 'Seo Jang-su',
        'Hong Guk-yeong', 'Kim Jong-su', 'Yun Si-dong', 'Pak Che-ga', 'Jeong Yak-yong', 'Kim Jo-sun', 'Sim Hwan-ji',
        'Raja Haji', 'Mahmud Riayat Shah', 'Omar Ali Saifuddin', 'Muhammad Alamuddin', 'Sultan Ibrahim', 'Alauddin',
        'Muhammad Kanzul Alam', 'Azim ud-Din', 'Daeng Kemboja',
    ],
    'PRINCES': [
        # Mysore, Hyderabad, the Sikh misls, Nepal, Travancore, Assam and the Durrani court
        'Tipu Sultan', 'Purnaiya', 'Burhanuddin', 'Mir Sadiq', 'Sayyid Saheb', 'Qamar ud-Din Khan', 'Syed Ghaffar',
        'Haidar Ali', 'Nizam Ali Khan', 'Mir Alam', 'Arastu Jah', 'Michel Raymond', 'Ranjit Singh', 'Mahan Singh',
        'Jassa Singh Ahluwalia', 'Jassa Singh Ramgarhia', 'Jai Singh Kanhaiya', 'Baghel Singh', 'Sada Kaur',
        'Gujjar Singh Bhangi', 'Bahadur Shah', 'Rana Bahadur Shah', 'Damodar Pande', 'Kalu Pande',
        'Amar Singh Thapa', 'Bhimsen Thapa', 'Dharma Raja', 'Raja Kesavadas', 'Purnananda Burhagohain',
        'Gaurinath Singha', 'Timur Shah', 'Zaman Shah', 'Payinda Khan', 'Madad Khan', 'Fateh Khan', 'Shah Wali Khan',
        'Mahmud Shah', 'Shuja ul-Mulk',
        # later and earlier figures of the same realm, then period names
        'Prithvi Narayan', 'Swarup Singh', 'Bam Shah', 'Sarbajit Rana', 'Charat Singh', 'Mir Fateh Ali',
        'Nasir Khan', 'Ali Khan', 'Abdullah Khan', 'Rahmat Khan',
    ],
    'SHEIKHS': [
        # the Al Bu Said sultans, the Gulf sheikhs, the Yemeni imam and the Mazrui of Mombasa
        'Hamad ibn Said', 'Sultan ibn Ahmad', 'Said ibn Ahmad', 'Qais ibn Ahmad', 'Saif ibn Ahmad',
        'Said ibn Sultan', 'Salim ibn Sultan', 'Hilal ibn Ahmad', 'Badr ibn Saif', 'Imam al-Mansur Ali',
        'Saqr ibn Rashid', 'Shakhbut ibn Dhiyab', 'Rahma ibn Jabir', 'Abdullah al-Sabah', 'Ahmad al-Fateh',
        'Salman ibn Ahmad', 'Abdallah al-Mazrui',
        # later and earlier figures of the same realm, then period names
        'Hilal al-Busaidi', 'Sayf al-Yarubi', 'Muhanna al-Ghafiri', 'Rashid al-Nuaimi', 'Sulayman al-Hinai',
        'Mazin al-Riyami', 'Salih al-Harthi', 'Said al-Maamari', 'Humaid al-Hajri', 'Khalfan al-Busaidi',
        'Nasir al-Kindi', 'Zahir al-Siyabi', 'Hamyar al-Hinai', 'Muhammad al-Mazrui', 'Ali al-Mazrui',
        'Rashid al-Mazrui', 'Ahmad al-Shami', 'Yahya al-Hamdani', 'Qasim al-Ansi', 'Husayn al-Wazir', 'Ali al-Zaydi',
        'Abdullah al-Shaybani', 'Muhsin al-Abdali', 'Fadl al-Abdali', 'Awad al-Kathiri', 'Mubarak al-Kathiri',
        'Saeed al-Kalbani', 'Humud al-Rawahi', 'Nasir al-Wahibi', 'Salim al-Bakri', 'Sultan al-Rashdi',
    ],
    'NILE': [
        # Darfur (Abd al-Rahman, Tayrab, Kurra), the Funj and Hamaj of Sennar, the Kabakas of Buganda
        'Abd al-Rahman al-Rashid', 'Muhammad Tayrab', 'Muhammad Kurra', 'Ali bin Jami', 'Muhammad al-Fadl',
        'Abu al-Qasim', 'Badi VI', 'Adlan', 'Muhammad Abu Likaylik', 'Kabaka Junju', 'Semakokiro', 'Kyabaggu',
        # later and earlier figures of the same realm, then period names
        'Kamanya', 'Mawanda', 'Salih Derret', 'Sabun', 'Omar Lel', 'Ahmad Bukr', 'Abd al-Qadir', 'Ahmad Ibrahim',
        'Idris wad Adlan', 'Hasan wad Rajab', 'Rajab wad Badi', 'Kisolo', 'Mukwenda', 'Mulondo', 'Wasswa', 'Mugema',
        'Ibrahim wad Hasan', 'Fadlallah wad Salih', 'Abdallah wad Jabir', 'Muhammad wad Ali', 'Ahmad wad Idris',
        'Hamad wad Nasir', 'Salih wad Omar', 'Adam wad Ahmad', 'Yusuf wad Hamad', 'Musa wad Ibrahim',
        'Isa wad Salih', 'Bakheit wad Ali', 'Tom wad Hasan', 'Omar wad Adam', 'Khalil wad Musa', 'Sebowa', 'Kayemba',
        'Mutesa', 'Ssekabaka', 'Nsubuga',
    ],
    'PACIFIC': [
        # Maori chiefs of the Bay of Islands and Cook Strait, and Aboriginal leaders of Sydney (Pemulwuy, Bennelong)
        'Pemulwuy', 'Bennelong', 'Hongi Hika', 'Te Rauparaha', 'Colebee', 'Te Pahi', 'Balloderree', 'Tuki', 'Huru',
        'Te Pehi Kupe', 'Te Wherowhero', 'Te Morenga', 'Titore', 'Tareha', 'Te Rangihaeata', 'Patuone', 'Waka Nene',
        'Kawiti', 'Te Waharoa', 'Ruatara', 'Te Hapuku',
        # later and earlier figures of the same realm, then period names
        'Te Heuheu', 'Te Kani-a-Takirau', 'Pomare', 'Rewa', 'Moka', 'Yemmerrawanne', 'Arabanoo', 'Bungaree',
        'Tedbury', 'Musquito', 'Wileemarin', 'Nanbaree', 'Gnung-a Gnung-a', 'Yuranigh', 'Bidgee Bidgee', 'Korokoro',
        'Te Whareumu', 'Tuwhare', 'Te Kawau', 'Hone Heke', 'Te Puni', 'Te Wharepouri', 'Kiwikiwi', 'Tamati Waka',
        'Te Kauri', 'Taiwhanga', 'Te Rangi Kaihau',
    ],
}
OFFICERS.update(HIST_OFFICERS)

# ---- officer pools of the three reskinned slots (2026-10-21, review C3) ----------------------------------------------------
# Moldavia, Saxony and Hanover were original minor nations; their player records now hold the Southern Kingdoms, the Sahel
# Kingdoms and the Kazakh Khanate. The new nations fall back to their own text keys (..._MANDO_JUG_<KEY>n, patch 1), but the
# exe still maps these three players to ORIGINAL pools (FUN_006577d0 = pool name, FUN_00657200 = counter slot):
#   JUG_MOLDAVIA               -> pool JUG_MOLDAVIA  (52 names, own counter slot 0xc)           = Southern Kingdoms
#   JUG_HANNOVER + JUG_SAJONIA -> the SAME pool JUG_GERMANICO (53 names, ONE counter slot 0xd)  = Kazakh Khanate + Sahel Kingdoms
# So their names are replaced in place (same keys, text only: no enum, no mng record, no id; all 8 languages carry the English
# name, Russian replaces it from build/i18n/ru_names.json under the original file) and the WHOLE pool is replaced (a shorter
# list would leave old German / Moldavian names at the end of the pool).
# Kazakhs and Sahel read one pool and the player -> pool mapping is code. The Germanic pool is the Kazakhs' (playable, active
# AI that recruits many officers). Exe patch 47 (SAHEL_OWN_OFFICERS, 2026-10-22) gives the Sahel Kingdoms their own officer
# NAMES: only while the officer-name builder FUN_00657eb0 asks, FUN_006577d0 lets JUG_SAJONIA fall through to its own key, so
# new Sahel officers read LTEXT_GESTION_NOMBRE_MANDO_JUG_SAJONIA<n> (SAHEL_POOL, sahel_officer_texts: NEW keys appended to
# TextOficialesGermanicos.sb, all 8 languages, Russian from SAJONIA_OFFICERS_RESERVE_RU). Ships, heirs and the
# DefInfoNombres sizes keep the Germanic pool, and the name COUNTER stays the shared slot 0xd, whose NUM_NOMBRES the loader
# takes from MANDO_JUG_GERMANICO (53): so the Sahel pool has exactly 53 names too (index n of the shared counter).
RESKIN_POOL = {'MOLDAVIA': ('MOLDAVIA', 'TextOficialesMoldavia.sb', 52),       # slot -> (pool name, text file, NUM_NOMBRES)
               'HANNOVER': ('GERMANICO', 'TextOficialesGermanicos.sb', 53)}
SAHEL_POOL = ('SAJONIA', 'TextOficialesGermanicos.sb', 53)   # patch 47: own key, file, size = the Germanic NUM_NOMBRES (slot 0xd)
RESKIN_OFFICERS = {
    'HANNOVER': [   # Kazakh Khanate (53); Russian: ru_names.json, TextOficialesGermanicos.sb
        # Wali Khan (Ablai's son, khan of the Middle Zhuz 1781-1819), Syrym Datuly, the khans and sultans of the three zhuz
        # around 1780-1800 (sons of Ablai and Nuraly), the old Ablai Khan (d. 1781)
        'Wali Khan', 'Syrym Datuly', 'Nuraly Khan', 'Eraly Khan', 'Aichuvak Khan', 'Bukey Sultan', 'Kasym Tore',
        'Adil Sultan', 'Gubaidulla Sultan', 'Karasakal Erimbet', 'Ablai Khan',
        # earlier figures: batyrs and khans of Ablai's age and before; later heroes of the steppe
        'Bogenbai Batyr', 'Kabanbai Batyr', 'Raiymbek Batyr', 'Nauryzbai Batyr', 'Zhanibek Batyr', 'Karasai Batyr',
        'Kokzhal Barak', 'Tole Bi', 'Abulfeiz Khan', 'Abilmambet Khan', 'Semeke Khan', 'Bolat Khan', 'Abulkhair Khan',
        'Tauke Khan', 'Esim Khan', 'Kasym Khan', 'Zhanibek Khan', 'Kenesary Khan', 'Isatay Taymanuly',
        'Makhambet Utemisuly', 'Sarzhan Kasymuly', 'Zhankozha Batyr', 'Shergazy Khan', 'Zhangir Khan',
        # period names (common Kazakh given names with batyr / sultan, not specific persons)
        'Aldiyar Sultan', 'Seitkul Batyr', 'Tolegen Batyr', 'Zhumabai Batyr', 'Bekbolat Batyr', 'Sultanbek Batyr',
        'Mukhamed Batyr', 'Kenzhebai Batyr', 'Yerzhan Sultan', 'Tauasar Batyr', 'Alibek Batyr', 'Baimurat Batyr',
        'Orazbai Batyr', 'Karabay Batyr', 'Sabyr Sultan', 'Dosan Batyr', 'Esengeldi Batyr', 'Baizhigit Batyr',
    ],
    'MOLDAVIA': [   # Southern Kingdoms (52); Russian: ru_names.json, TextOficialesMoldavia.sb
        # Merina (Andrianampoinimerina, Andriambelomasina), Mthethwa / Ndwandwe / Zulu (Dingiswayo, Zwide, Senzangakhona),
        # Rozvi, Ngwaketse, Swazi, Lunda, Kongo and Sakalava rulers around 1780-1800
        'Andrianampoinimerina', 'Dingiswayo', 'Zwide', 'Senzangakhona', 'Changamire Chirisamhuru', 'Makaba II',
        'Ndvungunye', 'Andriambelomasina', 'Kazembe Lukwesa', 'Mwata Yamvo', 'Garcia V', 'Andriamandisoarivo',
        # earlier figures: Merina and Betsimisaraka kings, the Mutapa and Rozvi founders, the kings of Kongo and Ndongo
        'Andriamasinavalona', 'Ralambo', 'Andrianjaka', 'Andriamanelo', 'Ratsimilaho', 'Changamire Dombo',
        'Nyatsimba Mutota', 'Matope', 'Afonso I', 'Garcia II', 'Antonio I', 'Pedro IV', 'Lukeni lua Nimi', 'Ngola Kiluanje',
        # later figures: Zulu, Ndebele, Sotho, Swazi, Kololo, Tswana and Merina leaders of the next generation
        'Shaka', 'Dingane', 'Mpande', 'Mzilikazi', 'Moshoeshoe', 'Sobhuza I', 'Matiwane', 'Sebetwane', 'Sekonyela',
        'Mothibi', 'Radama I', 'Rainiharo', 'Ndlela kaSompisi', 'Nongalaza', 'Andriantsoly',
        # Kongo kings (regnal numbers uncertain), Zulu forefathers, Luba / Lunda / Kasanje names
        'Henrique I', 'Jose I', 'Afonso V', 'Jama', 'Ndaba', 'Mageba', 'Tau', 'Tshwene', 'Kalala Ilunga', 'Mutombo',
        'Kasanje',
    ],
}
# names whose person, dates or spelling are not firmly established (to check with a source); every 'period name' of the
# Kazakh list and the last 8 names of the Southern list are generic or legendary by design
RESKIN_UNCERTAIN = {
    'HANNOVER': ['Adil Sultan', 'Gubaidulla Sultan (both: sons of Ablai?)', 'Karasakal Erimbet (role)', 'Eraly Khan / Aichuvak Khan (reign dates)',
                 'Nauryzbai Batyr', 'Karasai Batyr', 'Kokzhal Barak', 'Abilmambet Khan', 'Zhankozha Batyr (dates)'],
    'MOLDAVIA': ['Changamire Chirisamhuru (spelling, dates)', 'Makaba II', 'Ndvungunye', 'Kazembe Lukwesa', 'Mwata Yamvo (which holder)',
                 'Garcia V (reigned 1803-30)', 'Andriamandisoarivo', 'Henrique I / Jose I / Afonso V (Kongo regnal numbers)',
                 'Tau', 'Tshwene', 'Kalala Ilunga (legendary)', 'Mutombo', 'Kasanje'],
    'SAJONIA': ['Naba Kango', 'Naba Saaga', 'Naba Dulugu', 'Opoku Fofie', 'Apea Nti', 'Ali Shandora', 'Amari Ngone',
                'Ahmad Alimi (dates)', 'the last 6 names (generic Sahel names)',
                'Desse Koro (Kaarta, reign c. 1788-99)', 'Ali bin Dunama (= Mai Ali IV of Bornu, reign c. 1742-92)'],
}
SAJONIA_OFFICERS_RESERVE = [    # Sahel Kingdoms (53 = SAHEL_POOL size), used by exe patch 47 (see above); Russian below, same order
    # Segu (Ngolo and Mansong Diarra), Futa Toro, Asante, Oyo, Bornu, Kunta of Timbuktu, Gobir and the Hausa states,
    # Futa Jallon, the Mossi kingdoms, the Moorish emirs, Kajoor
    'Mansong Diarra', 'Ngolo Diarra', 'Abdul Kader Kane', 'Osei Kwame', 'Awole', 'Afonja', 'Ahmad Alimi',
    'Sidi al-Mukhtar', 'Usman dan Fodio', 'Nafata', 'Bawa Jan Gwarzo', 'Ibrahima Sori', 'Alwali', 'Abiodun',
    'Naba Kango', 'Naba Saaga', 'Naba Dulugu', 'Opoku Fofie', 'Apea Nti', 'Ali Shandora', 'Amari Ngone',
    # later and earlier figures of the same realms
    'Dunama Lefiami', 'Muhammad al-Kanemi', 'Muhammad Bello', 'Abdullahi dan Fodio', 'Yunfa', 'Osei Bonsu',
    'Opoku Ware II', 'Kusi Obodom', 'Osei Tutu', 'Biton Coulibaly', 'Da Monzon', 'Sekou Watara', 'Karamokho Alfa',
    'Al-Maghili', 'Ahmad al-Bakkai', 'Muhammad al-Habib', 'Adebo', 'Maku', 'Majotu', 'Bashorun Gaha', 'Opoku Ware',
    'Seku Amadu',
    # period names (common Sahel given names with clan names, not specific persons)
    'Bakary Traore', 'Moussa Keita', 'Amadou Cisse', 'Sambou Sy', 'Issa Maiga',
    # patch 47 (2026-10-22): five more to fill the 53 slots of the shared counter: Kaarta, Bornu (Mai Ali IV, the ruler
    # of 1789; Idris Alooma), Songhai, the Torodbe leader of Futa Toro
    'Desse Koro', 'Ali bin Dunama', 'Idris Alooma', 'Askia Muhammad', 'Sulayman Bal',
]
SAJONIA_OFFICERS_RESERVE_RU = [
    'Мансонг Диарра', 'Нголо Диарра', 'Абдул Кадер Кан', 'Осей Кваме', 'Аволе', 'Афонджа', 'Ахмад Алими',
    'Сиди аль-Мухтар', 'Усман дан Фодио', 'Нафата', 'Бава Ян Гварзо', 'Ибрахима Сори', 'Алвали', 'Абиодун',
    'Наба Канго', 'Наба Сага', 'Наба Дулугу', 'Опоку Фофие', 'Апеа Нти', 'Али Шандора', 'Амари Нгоне',
    'Дунама Лефиами', 'Мухаммад аль-Канеми', 'Мухаммад Белло', 'Абдуллахи дан Фодио', 'Юнфа', 'Осей Бонсу',
    'Опоку Варе II', 'Куси Ободом', 'Осей Туту', 'Битон Кулибали', 'Да Монзон', 'Секу Ватара', 'Карамоко Альфа',
    'Аль-Магили', 'Ахмад аль-Баккай', 'Мухаммад аль-Хабиб', 'Адебо', 'Маку', 'Маджоту', 'Башорун Гаха', 'Опоку Варе',
    'Секу Амаду',
    'Бакари Траоре', 'Муса Кейта', 'Амаду Сиссе', 'Самбу Си', 'Исса Майга',
    'Десе Коро', 'Али бин Дунама', 'Идрис Алаома', 'Аския Мухаммед', 'Сулейман Бал',
]
RESKIN_RU_MAX = 22           # the longest original Russian officer name


def reskin_officer_texts():
    """{text file relative to Texto/<lang>: {key: 'Name%s'}}: the officer names that REPLACE the original pool texts of the
    reskinned slots (Southern Kingdoms in the Moldavian pool, Kazakh Khanate in the Germanic pool; see the comment above).
    make_map.reskin_officer_texts() applies them to all 8 languages; Russian follows from ru_names.json."""
    out = {}
    for slot, (pool, fn, size) in RESKIN_POOL.items():
        names = RESKIN_OFFICERS[slot]
        assert len(names) == size and len(set(names)) == size, (slot, 'one distinct name for every slot of the original pool')
        assert max(len(n) for n in names) <= OFFICER_NAME_MAX, (slot, 'English officer names: at most %d characters' % OFFICER_NAME_MAX)
        assert all(n.isascii() and '"' not in n and '%' not in n for n in names), slot      # the Latin-1 language files
        out['Management/TextNombresOficiales/' + fn] = {
            'LTEXT_GESTION_NOMBRE_MANDO_JUG_%s%d' % (pool, i): n + '%s' for i, n in enumerate(names)}
    sah, ru, size = SAJONIA_OFFICERS_RESERVE, SAJONIA_OFFICERS_RESERVE_RU, SAHEL_POOL[2]
    assert size == RESKIN_POOL['HANNOVER'][2], 'patch 47: the Sahel pool must be as long as the shared counter slot 0xd'
    assert len(sah) == size == len(set(sah)) == len(ru) == len(set(ru)), 'Sahel pool'
    assert max(map(len, sah)) <= OFFICER_NAME_MAX and max(map(len, ru)) <= RESKIN_RU_MAX, 'Sahel pool'
    assert all(n.isascii() and '"' not in n and '%' not in n for n in sah) and not any('"' in n or '%' in n for n in ru)
    return out


def sahel_officer_texts(lang):
    """Exe patch 47: {text file relative to Texto/<lang>: {key: 'Name%s'}}, the Sahel Kingdoms' OWN officer pool, NEW keys
    LTEXT_GESTION_NOMBRE_MANDO_JUG_SAJONIA0..52 (make_map.reskin_officer_texts appends them; Russian names for 'Russian',
    the English ones in the other 7 languages). {} without SAHEL_OWN_OFFICERS (the exe patch is off too)."""
    if not SAHEL_OWN_OFFICERS:
        return {}
    pool, fn, size = SAHEL_POOL
    names = SAJONIA_OFFICERS_RESERVE_RU if lang == 'Russian' else SAJONIA_OFFICERS_RESERVE
    assert len(names) == size, 'Sahel pool'
    return {'Management/TextNombresOficiales/' + fn: {
        'LTEXT_GESTION_NOMBRE_MANDO_JUG_%s%d' % (pool, i): n + '%s' for i, n in enumerate(names)}}


# Heirs: the five original empires have 8 female + 8 male names (France 5 female + 4 male), every other original nation
# 1 + 1. The playable new nations get 8 + 8 of the ruling houses of about 1789 (children and relatives of the rulers, as far
# as they are known); the regional peoples keep 1 + 1. HEIRS[key] = (female, male), each a name or a list of names
# (heir_names); DefHerederos.sb gets MAX_NOMBRES_HEREDEROS_* = the number of names (heirs()).
HIST_HEIRS = {
    'PERSIA': (
        ['Fatemeh', 'Homayoon Soltan', 'Begum Jan', 'Seyyedeh Begum', 'Tayghun Khanum', 'Fakhr Jahan',
         'Zia al-Saltaneh', 'Asiyeh Khanum'],
        ['Abbas Mirza', 'Mohammad Ali', 'Mohammad Qoli', 'Mohammad Vali', 'Hossein Ali', 'Hasan Ali',
         'Mohammad Taqi', 'Ali Naqi']),
    'ARABIA': (
        ['Aisha', 'Hessa', 'Nura', 'Sara', 'Fatima', 'Lulwa', 'Jawhara', 'Moudi'],
        ['Saud', 'Abdullah', 'Abd al-Rahman', 'Umar', 'Muhammad', 'Turki', 'Faisal', 'Mishari']),
    'TURKESTAN': (
        ['Bibi Khanum', 'Nodira', 'Uvaysiy', 'Gulbadan', 'Khurshida', 'Salima', 'Zuhra', 'Oyim'],
        ['Haydar', 'Hussein', 'Umar', 'Nasrullah', 'Muhammad Rahim', 'Daniyal', 'Ibrahim', 'Masum']),
    'CHECHNYA': (
        ['Zainab', 'Aminat', 'Khava', 'Zulikhan', 'Aishat', 'Petimat', 'Zarema', 'Khadizhat'],
        ['Ghazi', 'Beibulat', 'Umalat', 'Hamzat', 'Isa', 'Musa', 'Dzhabrail', 'Ahmad']),
    'QING': (
        ['Hexiao', 'Hejing', 'Heke', 'Hejia', 'Hewan', 'Zhuangjing', 'Lingfei', 'Shufei'],
        ['Yongyan', 'Yongxuan', 'Yongrong', 'Yongxing', 'Yonglin', 'Mianning', 'Miankai', 'Mianxin']),
    'JAPAN': (
        ['Toshihime', 'Hidehime', 'Ayahime', 'Sohime', 'Kakuhime', 'Minehime', 'Asahime', 'Yohime'],
        ['Ieyoshi', 'Takechiyo', 'Keinosuke', 'Atsunosuke', 'Toyasaburo', 'Nariyuki', 'Torachiyo', 'Narinori']),
    'MARATHA': (
        ['Yashodabai', 'Anandibai', 'Muktabai', 'Ahilyabai', 'Baizabai', 'Kashibai', 'Lakshmibai', 'Radhabai'],
        ['Madhavrao', 'Baji Rao', 'Chimnaji', 'Amrutrao', 'Daulat Rao', 'Yashwantrao', 'Malharrao', 'Raghuji']),
    'ETHIOPIA': (
        ['Mentewab', 'Menen', 'Wubit', 'Seble Wongel', 'Welete Israel', 'Berhane Mogasa', 'Zenebech', 'Tsehay'],
        ['Tekle Giyorgis', 'Hezqeyas', 'Iyasu', 'Solomon', 'Yonas', 'Baeda Maryam', 'Demetros', 'Tekle Haymanot']),
}
HEIRS.update(HIST_HEIRS)


# ---------------------------------------------------------------- public (Nexus) release variant (2026-10-21)
# `python tools/make_map.py --public` builds the release for Nexus into build/public/ WITHOUT the nations in PUBLIC_DROP
# (Chechenya was made only for the user's father). make_map sets IG_PUBLIC=1 before it imports this module; nothing below
# runs without it, so the father's build is unchanged. The province (make_map.PROVINCES[11], idx 93) stays on the map with
# its art and battlefield; make_map gives it PUBLIC_PROVINCE_OWNER. Dropping a nation shifts the player / country / troop
# ids of every later nation: the public build needs a new campaign (validate_build --public skips the save-prefix check).
# Patch 29 stays: with empty BATTLE_STRENGTH tables every factor is 16 (x1.0), so its damage formulas leave the original
# values, and the Super Troops cheat (patch 32) still multiplies that factor.
PUBLIC = os.environ.get('IG_PUBLIC') == '1'
PUBLIC_DROP = ('CHECHNYA',)
PUBLIC_DROPPED = [nn for nn in NEW_NATIONS if nn['key'] in PUBLIC_DROP] if PUBLIC else []   # their entries (model folders)


def public_drops_text(k):
    """True for a text key of a nation left out of the public build: player, country, capital, Select Empire text, fleet /
    ship / officer / heir names, troop names (LTEXT_<KEY>_<TYPE>, LTEXT_DESC_<KEY>_<TYPE>[_SHORT]). The province keys stay
    (LTEXT_PROVINCIA_<KEY>, LTEXT_DESC_<KEY>, LTEXT_UI_BATALLA_INITVENT_<KEY>_*, LTEXT_OBJETIVOS_*)."""
    return any(re.match(r'LTEXT_(JUGADOR|PAIS|CAPITAL|UI_MAINMENU_SI_INFO)_%s$|LTEXT_\w*JUG_%s(\d|_|$)|LTEXT_(DESC_)?%s_\w'
                        % (d, d, d), k) for d in PUBLIC_DROP)


if PUBLIC:
    NEW_NATIONS[:] = [nn for nn in NEW_NATIONS if nn['key'] not in PUBLIC_DROP]
    PLAYABLE[:] = [p for p in PLAYABLE if p[len('JUG_'):] not in PUBLIC_DROP]
    for _d in (TROOP_STRENGTH, TRAIN_TURNS, START_LEVEL, BATTLE_STRENGTH, EXTRA_TROOPS, OFFICERS, SHIP_WORDS, HEIRS,
               HIST_OFFICERS, HIST_HEIRS):
        for _k in PUBLIC_DROP:
            _d.pop(_k, None)
    for _d in (TROOP_STRENGTH_TYPE, START_LEVEL_TYPE, BATTLE_STRENGTH_TYPE, EXTRA_TROOP_TEXT):
        for _k in [k for k in _d if k[0] in PUBLIC_DROP]:
            del _d[_k]
    NO_CAMELS.difference_update(PUBLIC_DROP)


def heir_names(key):
    """(female names, male names) of nation `key`: HEIRS holds one name each or a list of names each."""
    f, m = HEIRS[key]
    return ([f] if isinstance(f, str) else list(f)), ([m] if isinstance(m, str) else list(m))


# ---------------------------------------------------------------- database
def _owner_field(rec, n_tail, k):
    return len(rec) - 4 * n_tail + 4 * k


def _clone_troop(rec, key, tname, cid, folder, idx):
    """A troop record (section 7: u32 id, 4 strings, 24 ints) cloned for new nation `key`: id idx, owner cid (int 14),
    figure folder, own name keys (EXTRA_TROOP_TEXT), strength (ints 16..20), training turns (int 8), starting
    experience (ints 10/11)."""
    strs, _ = rec_strings(rec, 4)
    if strs[3]:
        strs[3] = folder
    if (key, tname) in EXTRA_TROOP_TEXT:
        strs[0], strs[1] = 'LTEXT_%s_%s' % (key, tname), 'LTEXT_DESC_%s_%s' % (key, tname)
    elif rides_horse(key, tname):                   # camel type drawn on a horse: the name follows the model
        strs[0], strs[1] = 'LTEXT_%s_HORSE' % tname, 'LTEXT_DESC_%s_HORSE' % tname
    new = rec_rebuild(rec, 4, strs, idx)
    struct.pack_into('<I', new, _owner_field(new, 23, 13), cid)
    _, q = rec_strings(new, 4)
    f = TROOP_STRENGTH_TYPE.get((key, tname), TROOP_STRENGTH.get(key))
    if f:                                           # combat values (record ints 16..20) x factor; 21, 22 kept
        vals = [int(round(v * f)) for v in struct.unpack_from('<5I', new, q + 16 * 4)]
        if (key, tname) in TROOP_STRENGTH_TYPE:
            vals = [min(v, STRENGTH_TYPE_CAP) for v in vals]
        struct.pack_into('<5I', new, q + 16 * 4, *vals)
    if key in TRAIN_TURNS:
        struct.pack_into('<I', new, q + 8 * 4, TRAIN_TURNS[key])
    lvl = START_LEVEL_TYPE.get((key, tname), START_LEVEL.get(key))
    if lvl and tname not in OFFICER_TYPES:
        struct.pack_into('<2I', new, q + 10 * 4, lvl, LEVEL_POINTS[lvl])
    return new


def bgr3(hexcol):
    r, g, b = FL.rgb(hexcol)
    out = b''
    for f in (1.0, 1.25, 0.75):
        out += bytes((min(255, int(b * f)), min(255, int(g * f)), min(255, int(r * f)), 0)) + struct.pack('<I', 1)
    return out


def add_nations(m, idx_of, shapes, LIFT):
    """Create the NEW_NATIONS in the database; recolour/flag-prepare the reskins. Returns info for file steps."""
    t_players, t_countries, t_caps = m.table(0), m.table(1), m.table(3)
    penum = {v: k for k, v in Mng.parse_enum(t_players).items()}
    cenum = {v: k for k, v in Mng.parse_enum(t_countries).items()}
    benum = {v: k for k, v in Mng.parse_enum(m.table(7)).items()}
    recs = Mng.parse_provinces(m.section(4)); provs = {r['idx']: r for r in recs}
    cs = Mng.parse_countries(m.section(3)); cby = {c['idx']: c for c in cs}
    players = parse_players(m.section(2))
    caps = parse_capitals(m.section(5)); capby = {c['idx']: c for c in caps}
    troops = split_records(m.section(7), 'troop')
    ships = split_records(m.section(15), 'ship')
    blds = split_records(m.section(9), 'building')
    pos = Mng.parse_positions(m.section(13))
    info = {}

    next_player = max(Mng.parse_enum(t_players)) + 1
    next_country = max(Mng.parse_enum(t_countries)) + 1
    next_cap = max(Mng.parse_enum(t_caps)) + 1
    next_bld = max(Mng.parse_enum(m.table(7))) + 1
    next_troop = max(Mng.parse_enum(m.table(5))) + 1
    next_ship = max(Mng.parse_enum(m.table(13))) + 1
    extra_queue = []                                    # EXTRA_TROOPS records, appended after the loop

    for nn in NEW_NATIONS:
        key, tpl = nn['key'], nn['template']
        tcid = cenum[tpl]
        pid, cid, capid, bid = next_player, next_country, next_cap, next_bld
        next_player += 1; next_country += 1; next_cap += 1; next_bld += 1
        Mng.enum_add(t_players, pid, 'JUG_' + key)
        Mng.enum_add(t_countries, cid, key)
        Mng.enum_add(t_caps, capid, nn['capital_key'])
        Mng.enum_add(m.table(7), bid, 'CAPITAL_BASE_' + key)
        folder = FIG + nn['folder'] + '/'
        # troops: clone the template country's records
        idmap = {}
        tnames = Mng.parse_enum(m.table(5))             # the original troop ids (new ones are only appended)
        have = set()
        for r in list(troops):
            if struct.unpack_from('<I', r, _owner_field(r, 23, 13))[0] != tcid:
                continue
            tname = tnames[struct.unpack_from('<I', r, 0)[0]]
            if key in NO_CAMELS and tname.startswith('CAM_'):
                continue                                # no camel corps in the Caucasus or East Asia
            new = _clone_troop(r, key, tname, cid, folder, next_troop)
            idmap[struct.unpack_from('<I', r, 0)[0]] = next_troop
            Mng.enum_add(m.table(5), next_troop, tname)
            troops.append(new); next_troop += 1; have.add(tname)
        # extra troop types the template lacks, cloned from another country's records (EXTRA_TROOPS). Only queued
        # here and appended after ALL other troop records below, so that they never move an existing troop id.
        extra = 0
        for tname, src in EXTRA_TROOPS.get(key, ()):
            if tname in have:
                continue
            extra_queue.append((key, tname, src, cid, folder))
            have.add(tname); extra += 1
        for r in list(ships):
            if struct.unpack_from('<I', r, _owner_field(r, 30, 10))[0] != tcid:
                continue
            strs, _ = rec_strings(r, 4)
            strs[3] = folder
            new = rec_rebuild(r, 4, strs, next_ship)
            struct.pack_into('<I', new, _owner_field(new, 30, 10), cid)
            Mng.enum_add(m.table(13), next_ship, Mng.parse_enum(m.table(13))[struct.unpack_from('<I', r, 0)[0]])
            ships.append(new); next_ship += 1
        # capital building
        tcap_bld = next(r for r in blds if Mng.parse_enum(m.table(7))[struct.unpack_from('<I', r, 0)[0]].startswith('CAPITAL_BASE_')
                        and struct.unpack_from('<I', r, 0)[0] == benum.get('CAPITAL_BASE_' + tpl, -1))
        strs, _ = rec_strings(tcap_bld, 3)
        blds.append(rec_rebuild(tcap_bld, 3, ['LTEXT_CAPITAL_' + nn['capital_key'][4:], strs[1], strs[2]], bid))
        # capital
        tprov = next(p for p in cby[tcid]['provs'] if provs[p]['vals'][12])
        tcap = capby[provs[tprov]['vals'][12]]
        cap_prov = idx_of[nn['capital_prov']]
        cx, cz = MG.centre_point(shapes[nn['capital_prov']])
        caps.append(dict(idx=capid, ltext='LTEXT_CAPITAL_' + nn['capital_key'][4:], s1='', s2='', pos=[cx, LIFT - 0.0147, cz],
                         level=1, blds=list(tcap['blds'])))
        provs[cap_prov]['vals'][4] = max(provs[tprov]['vals'][4], 200)
        provs[cap_prov]['vals'][12] = capid
        # map buildings in the capital province
        spots = sorted(MG.interior_points(shapes[nn['capital_prov']], 220, 120),
                       key=lambda q: math.hypot(q[0] - cx, q[1] - cz))[1:3] or [(cx + 150, cz), (cx - 150, cz)]
        pos.append((bid, cap_prov, cx, LIFT - 0.0147, cz, 0))
        pos.append((benum['DELEGACION_COMERCIAL'], cap_prov, spots[0][0], LIFT - 0.0147, spots[0][1], 0))
        pos.append((benum['CUARTEL_BASICO'], cap_prov, spots[-1][0], LIFT - 0.0147, spots[-1][1], 0))
        # country (provinces move from their temporary owner)
        new_provs = [idx_of[k] for k in nn['provinces']]
        for c in cs:
            c['provs'] = [p for p in c['provs'] if p not in new_provs]
        tc = cby[tcid]
        cs.append(dict(idx=cid, ltext='LTEXT_PAIS_' + key, flags=tc['flags'], provs=new_provs,
                       colours=bgr3(FL.COLOURS[key]), lists=[[], []]))
        cby[cid] = cs[-1]
        # player
        tp = next(p for p in players if p['idx'] == penum[nn['template_player']])
        army_units = [[u[0], idmap.get(u[1], u[1]), u[2]] for a in tp['armies'] for u in a['units']]
        officer = next((idmap[o] for o in idmap if Mng.parse_enum(m.table(5))[o] == 'TENIENTE'), idmap.get(tp['armies'][0]['officer']))
        players.append(dict(idx=pid, ltext='LTEXT_JUGADOR_' + key, info='LTEXT_UI_MAINMENU_SI_INFO_' + key, country=cid,
                            start=list(nn['start']), objects=[[bid, 0, capid, 0, 0]],
                            armies=[dict(province=cap_prov, name='', officer_name='', officer=officer, zero=0, units=army_units[:6])],
                            tail=tp['tail']))
        info[key] = dict(player='JUG_' + key, country=key, cid=cid, pid=pid, troops=len(idmap) + extra)
        print('  new nation %-9s player %d country %d capital %s, %d troops%s, provinces %s'
              % (key, pid, cid, nn['capital'], len(idmap) + extra, ' (%d extra types)' % extra if extra else '',
                 new_provs))

    # SAVE COMPATIBILITY: the EXTRA_TROOPS records (and their table-5 enum entries) come after every other troop
    # record, so each pre-existing troop keeps its record id, enum entry and section-7 position. A save stores a
    # battalion's troop type as the raw record id (battalion save FUN_005ad1e0 writes [bat+0x14]; the game resolves
    # it with a linear search on record field 0, FUN_005cb030), so a shifted id turned e.g. a saved Qing hussar
    # into a Chechen grenadier. New troop records must always be appended here, at the very end, in EXTRA_TROOPS order
    # (Chechnya's 564..569 first, then the later additions), whatever the order of NEW_NATIONS.
    tnames = Mng.parse_enum(m.table(5))
    order = [(k, t) for k, lst in EXTRA_TROOPS.items() for t, _ in lst]
    extra_queue.sort(key=lambda e: order.index((e[0], e[1])))
    for key, tname, src, cid, folder in extra_queue:
        r = next(t for t in troops if tnames.get(struct.unpack_from('<I', t, 0)[0]) == tname
                 and struct.unpack_from('<I', t, _owner_field(t, 23, 13))[0] == cenum[src])
        Mng.enum_add(m.table(5), next_troop, tname)
        troops.append(_clone_troop(r, key, tname, cid, folder, next_troop)); next_troop += 1

    # reskins: playable info key and new colours
    reskin_start = {'JUG_MOLDAVIA': [700, 900, 150, 1100, 0], 'JUG_SAJONIA': [700, 900, 150, 1100, 0],
                    'JUG_HANNOVER': [1200, 1500, 200, 1700, 0]}
    for pkey, (ckey, design, name, adj, text) in RESKIN_PLAYABLE.items():
        p = next(q for q in players if q['ltext'] == 'LTEXT_JUGADOR_' + pkey[4:])
        p['info'] = 'LTEXT_UI_MAINMENU_SI_INFO_' + pkey[4:]
        p['start'] = list(reskin_start[pkey])
        c = cby[cenum[ckey]]
        c['colours'] = bgr3(FL.COLOURS[design])
    # the original minors made playable: their player records carry no Select Empire text key ('' in the original,
    # a blank info panel). Campaign mode reads the key from the player record; texts_new writes
    # LTEXT_UI_MAINMENU_SI_INFO_<KEY> in all 8 languages. Only a string field changes, no record or id.
    for pkey in MINORS_PLAYABLE:
        p = next(q for q in players if q['idx'] == penum[pkey])
        if not p['info']:
            p['info'] = 'LTEXT_UI_MAINMENU_SI_INFO_' + pkey[4:]

    # reskin slots (Kazakhs = HANNOVER, Sahel = SAJONIA, Southern Kingdoms = MOLDAVIA): their ORIGINAL troop records get
    # the nations' own name keys (EXTRA_TROOP_TEXT / tools/troop_texts.py). SAVE-SAFE: only strings 0 and 1 of existing
    # records change (rec_rebuild keeps the id, ints and order); the type enum names and the owners stay.
    _tn, _cn = Mng.parse_enum(m.table(5)), Mng.parse_enum(t_countries)
    for i, r in enumerate(troops):
        _ck = _cn.get(struct.unpack_from('<I', r, _owner_field(r, 23, 13))[0])
        _tk = (_ck, _tn[struct.unpack_from('<I', r, 0)[0]])
        if _ck in RESKIN_TROOP_COUNTRIES and _tk in EXTRA_TROOP_TEXT:
            _s, _ = rec_strings(r, 4)
            _s[0], _s[1] = 'LTEXT_%s_%s' % _tk, 'LTEXT_DESC_%s_%s' % _tk
            troops[i] = rec_rebuild(r, 4, _s)

    Mng.set_countries(m.section(3), cs)
    Mng.set_provinces(m.section(4), recs)
    pack_players(m.section(2), players)
    pack_capitals(m.section(5), caps)
    for sid, lst in ((7, troops), (15, ships), (9, blds)):
        m.section(sid).body = b''.join(bytes(r) for r in lst); m.section(sid).cnt = len(lst)
    m.section(13).body = b''.join(struct.pack('<IIfffI', *q) for q in pos); m.section(13).cnt = len(pos)
    return info


# ---------------------------------------------------------------- script files
def _insert_before_last_bracket(txt, add):
    i = txt.rstrip().rfind(']')
    return txt[:i] + add + txt[i:]


def turn_order(txt, new_players, playable_new):
    """Add the new players to every turn-order list and give each newly playable nation its own list."""
    blocks = list(re.finditer(r'^\.(JUG_\w+)\s*\r?\n\[', txt, re.M))
    for b in reversed(blocks):
        a, e = find_block(txt, b.start())
        body = txt[a:e]
        add = ''.join('  %s\r\n' % p for p in new_players if p not in body and p != b.group(1))
        txt = txt[:e - 1] + add + txt[e - 1:]
    allp = re.findall(r'^\s+(JUG_\w+)', txt[blocks[0].start():find_block(txt, blocks[0].start())[1]], re.M)
    allp = [blocks[0].group(1)] + allp
    for p in playable_new:
        if re.search(r'^\.' + p + r'\s*$', txt, re.M):
            continue
        txt += '\r\n.%s\r\n[\r\n%s]\r\n' % (p, ''.join('  %s\r\n' % q for q in allp if q != p))
    return txt


def hostility(txt, new_players, all_players):
    add = ''
    for p in new_players:
        add += '\r\n.%s\r\n[\r\n%s]\r\n' % (p, ''.join('  .%s [ .HOSTILIDAD 50.0 ]\r\n' % q for q in all_players if q != p))
    return txt + add


def heirs(txt, new_players):
    i = re.search(r'^.JUGADORES', txt, re.M).start()
    a, e = find_block(txt, i)
    add = ''
    for p in new_players:                       # name counts = the names texts_new writes (heir_names); the five empires have 8 + 8
        f, m = heir_names(p[len('JUG_'):])
        add += ('\r\n .%s\r\n [\r\n  .TURNOS_ESPERA_NACIMIENTO         6\r\n  .MAX_NOMBRES_HEREDEROS_MASCULINOS %d\r\n'
                '  .MAX_NOMBRES_HEREDEROS_FEMENINOS  %d\r\n ]\r\n' % (p, len(m), len(f)))
    return txt[:e - 1] + add + txt[e - 1:]


def def_tropas(txt):
    # unit models per culture (tools/art/units/cultures.py: Asia / India / Africa / Pacific / Arab sets)
    import sys as _s
    _s.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'art', 'units'))
    import cultures as CU
    for nn in NEW_NATIONS:
        nn['units'] = CU.UNIT_FILE_OF.get(nn['key'], nn['units'])
    # the reskin slots use their culture unit files (cultures.UNIT_FILE_OF: Sahel and Kazakh files = the Arab set with
    # their own grenadiers / dragoons / cuirassiers, Southern Kingdoms file; 2026-10-21). Only the file reference changes
    for key in ('SAJONIA', 'HANNOVER', 'MOLDAVIA'):
        uf = CU.UNIT_FILE_OF.get(key)
        if uf and uf != 'DefUnidadesStandard.sb':
            txt = re.sub(r'(\.NAME\s+"%s"\s+\.DEFTROPAS\s+"[^"]+"\s+\.DEFUNIDADES\s+)"[^"]+"' % key,
                         lambda m, uf=uf: m.group(1) + '"Game/GameModes/Batalla/%s"' % uf, txt)
    add = ''.join('\r\n[\r\n  .NAME          "%s"\r\n  .DEFTROPAS     "Game/GameModes/Batalla/DefTropasStandard.sb"\r\n'
                  '  .DEFUNIDADES   "Game/GameModes/Batalla/%s"\r\n  .PATHTEX       "Models\\%s\\"\r\n]\r\n'
                  % (nn['key'], nn['units'], nn['folder']) for nn in NEW_NATIONS)
    return txt + add


def def_barcos(txt):
    add = ''
    for nn in NEW_NATIONS:
        for kind in ('NAVIO', 'FRAGATA', 'CORBETA'):
            m0 = re.search(r'^\.%s_%s\s*\r?\n' % (nn['template'], kind), txt, re.M)
            a, e = find_block(txt, m0.end())
            block = txt[m0.start():e].replace('.%s_%s' % (nn['template'], kind), '.%s_%s' % (nn['key'], kind))
            block = block.replace('Models\\%s\\' % nn['models'], 'Models\\%s\\' % nn['folder'])
            add += '\r\n' + block + '\r\n'
    return txt + add


# ---------------------------------------------------------------- flags and UI
FLAG_KEYS = {nn['key']: nn['key'] for nn in NEW_NATIONS}                       # country key -> design
FLAG_KEYS.update({v[0]: v[1] for v in RESKIN_PLAYABLE.values()})               # MOLDAVIA -> SIBERIA ...
PLAYER_OF = {nn['key']: 'JUG_' + nn['key'] for nn in NEW_NATIONS}
PLAYER_OF.update({v[0]: k for k, v in RESKIN_PLAYABLE.items()})


ATLAS_OF = {}       # country -> atlas file (several 1024 x 1024 atlases when there are many nations)


def atlas_name(k):
    return ATLAS if k == 0 else ATLAS.replace('.tga', 'N%d.tga' % (k + 1))


def build_atlas(out_path):
    """1024x1024 atlases with every UI flag variant, one nation never split over two. Returns
    ({(country, variant): (u, v, w, h)}, {country: variants}); ATLAS_OF[country] names the file."""
    order = ['s33', 's46', 'd54_disable', 'd54_normal', 'd54_select', 'i38_normal', 'i38_disable', 'h38', 'e57', 'b297_fondo', 'b297_disable', 'b297_sel']
    where, big = {}, {}
    sheets = [FL.blank(1024, 1024)]
    x = y = rowh = 0
    for country, design in FLAG_KEYS.items():
        v = FL.derive(design)
        big[country] = v
        # lay the nation out on a scratch copy of the cursor; start a new sheet if it does not fit
        for attempt in range(2):
            cx, cy, ch, spots = x, y, rowh, {}
            for name in order:
                w, h = len(v[name][0]) // 4, len(v[name])
                if cx + w > 1024:
                    cx = 0; cy += ch + 2; ch = 0
                spots[name] = (cx, cy, w, h)
                cx += w + 2; ch = max(ch, h)
            if cy + ch <= 1024:
                break
            sheets.append(FL.blank(1024, 1024)); x = y = rowh = 0
        for name in order:
            FL.paste(sheets[-1], v[name], spots[name][0], spots[name][1])
            where[(country, name)] = spots[name]
        ATLAS_OF[country] = atlas_name(len(sheets) - 1)
        x, y, rowh = cx, cy, ch
    base = os.path.dirname(os.path.dirname(out_path))
    for k, s in enumerate(sheets):
        p = os.path.join(os.path.dirname(out_path), os.path.basename(atlas_name(k)))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tga.write_tga(p, 1024, 1024, s)
    return where, big


def _entry(key, f, u, v, w, h, prio, extra=''):
    return ('\r\n[\r\n  .KEY %s\r\n  .PARAMS\r\n  [\r\n    .FILE "%s" .SX %d .SY %d .U %d .V %d .ALPHA TRUE%s\r\n'
            '    .PRIORITY %d\r\n  ]\r\n]\r\n' % (key, f, w, h, u, v, extra, prio))


def set_sprite(txt, key, new_entry):
    """Replace the [ .KEY key ... ] entry if present, else append."""
    m0 = re.search(r'\[\s*\.KEY\s+' + re.escape(key) + r'\s', txt)
    if m0:
        a, e = find_block(txt, m0.start())
        return txt[:a] + new_entry.strip() + txt[e:]
    return txt + new_entry


def ui_flags(files, where, prio_of):
    """files: dict rel -> text. Updates every flag sprite definition. Returns the dict."""
    def at(c, n):
        return where[(c, n)]
    for c, pk in PLAYER_OF.items():
        for rel, prio in (('Game/UI/ModeloGestion/UIDefs_Banderas.sb', 240), ('Game/UI/ModeloBatalla/UIDefs_Banderas.sb', 240),
                          ('Game/UI/ModeloNaval/UIDefs_Banderas.sb', 10)):
            files[rel] = set_sprite(files[rel], pk, _entry(pk, ATLAS_OF[c], *at(c, 's33'), prio))
        rel = 'Game/UI/ModeloGestion/UIDefs_Banderas.sb'
        files[rel] = set_sprite(files[rel], 'BANDERA_ICONO_' + c, _entry('BANDERA_ICONO_' + c, ATLAS_OF[c], *at(c, 's46'), 245))
        rel = 'Game/UI/ModeloGestion/Iconos/UIDefs_FlagIcons.sb'
        for n, var in (('NORMAL', 'i38_normal'), ('DISABLE', 'i38_disable')):
            u, v, w, h = at(c, var)
            e = '\r\n[\r\n  .KEY BANDERA_%s_IMG_%s\r\n  .PARAMS\r\n  [\r\n    .FILE "%s"\r\n    .U %d .V %d .SX %d .SY %d .ALPHA TRUE\r\n  ]\r\n]\r\n' % (c, n, ATLAS_OF[c], u, v, w, h)
            files[rel] = set_sprite(files[rel], 'BANDERA_%s_IMG_%s' % (c, n), e)
        rel = 'Game/UI/MainMenu/SelectEmpire/UIDefs_Banderas.sb'
        for suf, var, pr in SE_VARIANTS:
            files[rel] = set_sprite(files[rel], '%s_BANDERA_%s' % (pk, suf), _entry('%s_BANDERA_%s' % (pk, suf), ATLAS_OF[c], *at(c, var), pr))
    # the five originals: the list strips are painted into the dialog background; the (now visible and scrolling)
    # FONDO bitmaps get the same normal-brightness strips (SeleccionImperioA_.tga, top to bottom GB FR AU PR RU)
    rel = 'Game/UI/MainMenu/SelectEmpire/UIDefs_Banderas.sb'
    for k, pk in enumerate(('JUG_GRAN_BRETANYA', 'JUG_FRANCIA', 'JUG_AUSTRIA', 'JUG_PRUSIA', 'JUG_RUSIA')):
        key = pk + '_BANDERA_FONDO'
        files[rel] = set_sprite(files[rel], key, _entry(key, 'Game/UI/MainMenu/SelectEmpire/SeleccionImperioA_.tga', 49, 153 + 60 * k, 297, 57, 40))
    return files


# Select Empire row sprites: (suffix, variant, priority) as in the original UIDefs_Banderas.sb
SE_VARIANTS = (('INFO', 'e57', 45), ('SEL', 'b297_sel', 45), ('FONDO', 'b297_fondo', 40), ('DISABLE', 'b297_disable', 75))


def diplomacy_flags(txt, where):
    """Diplomacy screen buttons: repack the last row (Barbary states + the three new nations)."""
    last = ['MARRUECOS', 'TUNEZ', 'TRIPOLITANIA'] + [nn['key'] for nn in NEW_NATIONS]
    rows = [last[i:i + 7] for i in range(0, len(last), 7)]
    places = []
    for ri, row in enumerate(rows):
        places += [(c, 217 + 30 * (7 - len(row)) + 60 * k, 347 + 58 * ri) for k, c in enumerate(row)]
    for c, x, yy in places:
        m0 = re.search(r'\[\s*\.KEY\s+BANDERA_' + c + r'\s', txt)
        if m0:
            a, e = find_block(txt, m0.start())
            blk = re.sub(r'\.X\s+\d+\s+\.Y\s+\d+', '.X %d .Y %d' % (x, yy), txt[a:e], count=1)
            txt = txt[:a] + blk + txt[e:]
        else:
            tpl = re.search(r'\[\s*\.KEY\s+BANDERA_TRIPOLITANIA\s', txt)
            a, e = find_block(txt, tpl.start())
            blk = txt[a:e].replace('BANDERA_TRIPOLITANIA', 'BANDERA_' + c).replace('LTEXT_PAIS_TRIPOLITANIA', 'LTEXT_PAIS_' + c)
            blk = re.sub(r'\.X\s+\d+\s+\.Y\s+\d+', '.X %d .Y %d' % (x, yy), blk, count=1)
            txt = txt[:e] + '\r\n\r\n' + blk + txt[e:]
    for c in FLAG_KEYS:
        m0 = re.search(r'\[\s*\.KEY\s+BANDERA_' + c + r'\s', txt)
        a, e = find_block(txt, m0.start())
        blk = txt[a:e]
        for tag, var in (('DISABLE', 'd54_disable'), ('SOLTADO', 'd54_normal'), ('SELECCIONADO', 'd54_select'), ('PULSADO', 'd54_select')):
            u, v, w, h = where[(c, var)]
            blk = re.sub(r'(\.%s\s*\[)[^\]]*\]' % tag, r'\1 .FILE "%s" .U %d .V %d ]' % (ATLAS_OF[c], u, v), blk, count=1)
        txt = txt[:a] + blk + txt[e:]
    return txt


def recipient_checkboxes(txt):
    add = ''.join('\r\n    .JUG_%s\r\n    [\r\n      .PARAMS\r\n      [\r\n        .IDSELECTSOUND "S_FXUI_CHECKBUTTON"\r\n'
                  '        .STYLE BANDERA_%s\r\n      ]\r\n    ]\r\n' % (nn['key'], nn['key']) for nn in NEW_NATIONS)
    return txt.rstrip() + '\r\n' + add


def historical_flags(txt, where):
    m0 = re.search(r'\.BITMAP_PAISES\s*\r?\n?\s*\[', txt)
    if not m0:
        return txt
    a, e = find_block(txt, m0.start())
    blk = txt[a:e]
    for c in FLAG_KEYS:
        u, v, w, h = where[(c, 'h38')]
        line = '.%s [ .U %d .V %d .SX 38 .SY 38 .FILE "%s" ]' % (c, u, v, ATLAS_OF[c])
        if re.search(r'^\s*\.' + c + r'\s*\[', blk, re.M):
            blk = re.sub(r'^(\s*)\.' + c + r'\s*\[[^\]]*\]', lambda mm: mm.group(1) + line, blk, count=1, flags=re.M)
        else:
            i = blk.rstrip().rfind(']')
            blk = blk[:i] + '  ' + line + '\r\n' + blk[i:]
    return txt[:a] + blk + txt[e:]


def colour_ids(txt):
    for c, design in FLAG_KEYS.items():
        r, g, b = FL.rgb(FL.COLOURS[design])
        line = '[ .DESC %-13s .COLOR [ .R %d .G %d .B %d ] ]' % (c, r, g, b)
        if re.search(r'\.DESC\s+' + c + r'\s', txt):
            txt = re.sub(r'\[\s*\.DESC\s+' + c + r'\s.*?\]\s*\]', line, txt, count=1)
        else:
            i = txt.rstrip().rfind(']')
            txt = txt[:i] + line + '\r\n' + txt[i:]
    return txt


# ---------------------------------------------------------------- text
def texts_new(lang_files):
    """Entries to add per file (relative to texto/<lang>/)."""
    add = {}
    def put(f, k, v):
        add.setdefault(f, []).append((k, v))
    for nn in NEW_NATIONS:
        k = nn['key']
        put('Management/TextJugadores.sb', 'LTEXT_JUGADOR_' + k, nn['name'])
        put('Management/TextPaises.sb', 'LTEXT_PAIS_' + k, nn['name'])
        put('Management/TextCapitales.sb', 'LTEXT_CAPITAL_' + nn['capital_key'][4:], nn['capital'])
        put('Management/TextNombresFlotas/TextFlotasArabes.sb', 'LTEXT_GESTION_NOMBRE_FLOTA_JUG_' + k, nn['adjective'] + ' Fleet%s')
        assert len(OFFICERS[k]) >= 48 and len(SHIP_WORDS[k]) >= 55, (k, 'the exe reads 48 officer / 55 ship names')
        assert len(set(OFFICERS[k][:48])) == 48 and max(len(n) for n in OFFICERS[k][:48]) <= OFFICER_NAME_MAX, \
            (k, 'officer names must be distinct and at most %d characters (the longest original)' % OFFICER_NAME_MAX)
        for i, n in enumerate(OFFICERS[k][:48]):
            put('Management/TextNombresOficiales/TextOficialesArabes.sb', 'LTEXT_GESTION_NOMBRE_MANDO_JUG_%s%d' % (k, i), n + '%s')
        for i, n in enumerate(SHIP_WORDS[k][:55]):
            put('Management/TextNombresFlotas/TextFlotasArabes.sb', 'LTEXT_GESTION_NOMBRE_BARCO_JUG_%s%d' % (k, i), n + '%s')
        hf, hm = heir_names(k)
        assert all(len(n) <= HEIR_NAME_MAX for n in hf + hm), (k, 'heir names: at most %d characters' % HEIR_NAME_MAX)
        for i, n in enumerate(hf):                  # keys F_1.. / M_1.. as in the original TextHerederos.sb
            put('Management/TextHerederos.sb', 'LTEXT_HEREDERO_JUG_%s_F_%d' % (k, i + 1), n)
        for i, n in enumerate(hm):
            put('Management/TextHerederos.sb', 'LTEXT_HEREDERO_JUG_%s_M_%d' % (k, i + 1), n)
        put('Others/TextUIMainMenu.sb', 'LTEXT_UI_MAINMENU_SI_INFO_' + k, nn['info'])
    for (k, t), txt in EXTRA_TROOP_TEXT.items():                   # names of the extra troop types (add_nations)
        assert len(txt[0]) <= 22 and all(ord(c) < 128 for c in ''.join(txt)), (k, t, 'name <= 22 chars, ASCII only')
        put('Management/TiposTropas/TiposTropasNeutral.sb', 'LTEXT_%s_%s' % (k, t), txt[0])
        put('Management/TiposTropas/TiposTropasNeutral.sb', 'LTEXT_DESC_%s_%s' % (k, t), txt[1])
        if len(txt) > 2:
            put('Management/TiposTropas/TiposTropasNeutral.sb', 'LTEXT_DESC_%s_%s_SHORT' % (k, t), txt[2])
    for t, (name, desc, short) in HORSE_CAMEL_TEXT.items():         # camel types on horses (_clone_troop)
        put('Management/TiposTropas/TiposTropasNeutral.sb', 'LTEXT_%s_HORSE' % t, name)
        put('Management/TiposTropas/TiposTropasNeutral.sb', 'LTEXT_DESC_%s_HORSE' % t, desc)
        put('Management/TiposTropas/TiposTropasNeutral.sb', 'LTEXT_DESC_%s_HORSE_SHORT' % t, short)
    for pkey, (ckey, design, name, adj, text) in RESKIN_PLAYABLE.items():
        put('Others/TextUIMainMenu.sb', 'LTEXT_UI_MAINMENU_SI_INFO_' + pkey[4:], text)
    for pkey, (flag, text) in MINORS_PLAYABLE.items():
        put('Others/TextUIMainMenu.sb', 'LTEXT_UI_MAINMENU_SI_INFO_' + pkey[4:], text)
        put('Others/TextUIMainMenu.sb', 'LTEXT_UI_MAINMENU_SI_INFO_' + pkey[4:] + '_QUICKGAME', text)
    return add


# ---------------------------------------------------------------- exe patch
EXE_BASE = 0x400000


# cheat patches 18+: caves in the int3 run 0x88a47b-0x88afff (round 1 at 0x88a500-0x88a847, later rounds from
# CHEAT_FREE), handler table for the panel buttons 'CH_A'..'CH_Z', captured campaign-map UI object in the .data tail
CHEAT_CAVE, CHEAT_TABLE, CHEAT_FREE, CHEAT_UI = 0x88a500, 0x88a700, 0x88a900, 0x942fe0
# toggle bytes of the round-2 cheats (zero-filled .data tail: all off at start, not saved)
CHEAT_MOVE, CHEAT_FOG, CHEAT_GOD, CHEAT_GOD_ON, CHEAT_COST = 0x942fe4, 0x942fe5, 0x942fe6, 0x942fe7, 0x942fe8
# round 3 (patches 32-39): toggle bytes, and the local human's player id, refreshed by the map-UI capture of patch 18
# on every campaign-map event (so a game loaded with another nation never keeps the old id)
CHEAT_BATTLE, CHEAT_INTEL, CHEAT_UPKEEP, CHEAT_HUMAN = 0x942fe9, 0x942fea, 0x942feb, 0x942fec
# patch 27: queue length of the human player (item in progress + queued) for buildings per province and units per
# barracks / shipyard (original 6 / 7 / 7, kept for the AI); 'Finish all queues' (patch 21) runs one pass per item
HUMAN_QUEUE_CAP = 13
QUEUE_PASSES = HUMAN_QUEUE_CAP + 1
# patch 31: the 6 fullscreen (width, height) pairs the D3D9 mode filter accepts (exactly 6: the loop is compiled in).
# The installed exe's table was a broken hex edit (3840x2160 three times, 3840x552960, no 1920x1080).
FULLSCREEN_MODES = [(1024, 768), (1280, 720), (1600, 900), (1920, 1080), (2560, 1440), (3840, 2160)]
# patch 40 + make_map.provincial_military (user 2026-10-21): the HUMAN may build the BASIC military buildings in his
# non-capital provinces too, at PROVINCIAL_COST_MULT x the price (every resource) and PROVINCIAL_EXTRA_TURNS more
# turns; troops are then trained there (native troops of that province). Capitals and the AI keep the original rules.
# The records get location bit PROVINCIAL_MASK (value change only); advanced and elite tiers stay capital-only.
PROVINCIAL_MILITARY = True
PROVINCIAL_COST_MULT = 3
PROVINCIAL_EXTRA_TURNS = 2
PROVINCIAL_BUILDINGS = ('CUARTEL_BASICO', 'BARRACAS_BASICAS', 'CUADRAS_BASICAS', 'FUNDICION_BASICA')
PROVINCIAL_MASK = 0x20
# patches 44-46 (user 2026-10-21, needs PROVINCIAL_MILITARY): the AI may build the same provincial military buildings
# (the ORIGINAL records, patch 40's price and turns), but only in ONE province per AI turn, chosen near its war front,
# and it recruits FORMAR_BATALLON orders in its cuartel nearest to that front. False = exe exactly as without them.
AI_PROVINCIAL = True
AI_PROVINCIAL_MAX = 2          # provincial cuarteles per AI (built + being built)
AI_PROVINCIAL_REACH = 2        # at most this many route hops from the military minister's best objective
AI_PROVINCIAL_SAVE = 2         # and at least this many hops nearer than the AI's nearest existing cuartel
AI_PROVINCIAL_RESERVE = 2      # the AI only builds one while it holds this many times its provincial price
# patch 47 (2026-10-22): the Sahel Kingdoms (Saxony's slot) name NEW officers from their own pool (SAHEL_POOL,
# SAJONIA_OFFICERS_RESERVE) instead of the Kazakhs' Germanic one; the Kazakhs, ships and heirs are unchanged. Text + exe only
# (save-safe). False = no exe change and no new text keys.
SAHEL_OWN_OFFICERS = True
# patches 48-50 (2026-10-22): exe support of the scripted historical events (tools/historical_events.py). make_map sets
# this from its own HISTORICAL_EVENTS right before patch_exe (one switch for the Lua, the texts and the exe); False = the
# exe is byte-identical to the build without them. 48: the campaign sequence script is loaded once per campaign map and
# HIST_TURN_HOOK is called at the start of every human turn (the sequence manager stays INACTIVE, see patch 48);
# 49: Lua native get_turno_actual(); 50: Lua native firma_paz_entre(jugA, jugB) (HIST_PEACE_NATIVE).
HISTORICAL_EVENTS = False
HIST_TURN_HOOK = 'eh_inicio_turno'   # Lua global function (no arguments) run at each human turn start (patch 48)
HIST_PEACE_NATIVE = True             # patch 50 (only with HISTORICAL_EVENTS)
# patch 51 (2026-10-23): at a new campaign the camera of every nation without one of the five original intro flights
# (GB, France, Austria, Prussia, Russia) starts on the human's capital, as the original does after loading a save.
# False = the original (no start camera: a fixed default spot, often over the fog).
CAPITAL_START_CAMERA = True


class CaveAsm:
    """Tiny x86 emitter for the code caves of patches 18+ (VA based, labels for short/near jumps)."""

    def __init__(self, org):
        self.org, self.b, self.lab, self.fix = org, bytearray(), {}, []

    def here(self):
        return self.org + len(self.b)

    def e(self, hx):                                    # raw bytes from hex (spaces allowed)
        self.b += bytes.fromhex(hx.replace(' ', ''))

    def imm(self, v):                                   # 32-bit immediate / absolute address
        self.b += struct.pack('<I', v & 0xffffffff)

    def mark(self, name):
        self.lab[name] = self.here()

    def call(self, target):
        self.b += b'\xe8' + struct.pack('<i', target - (self.here() + 5))

    def jmp(self, target):
        self.b += b'\xe9' + struct.pack('<i', target - (self.here() + 5))

    def js(self, op, name):                             # short jmp/jcc ('eb', '74', ...) to a label
        self.e(op); self.fix.append((len(self.b), name, 1)); self.b.append(0)

    def jl(self, op, name):                             # near jmp/jcc ('e9', '0f84', ...) to a label
        self.e(op); self.fix.append((len(self.b), name, 4)); self.b += bytes(4)

    def done(self):
        for pos, name, size in self.fix:
            rel = self.lab[name] - (self.org + pos + size)
            if size == 1:
                assert -128 <= rel <= 127, name
                self.b[pos] = rel & 0xff
            else:
                struct.pack_into('<i', self.b, pos, rel)
        return bytes(self.b)


def patch_exe(src_path, dst_path, mng_path=None):
    """Copy the exe and apply two patches; returns a list of (file offset, old bytes, new bytes)."""
    d = bytearray(open(src_path, 'rb').read())
    changes = []

    def put(off, new, expect=None):
        old = bytes(d[off:off + len(new)])
        if expect is not None:
            assert old == expect, (hex(off), old.hex(), expect.hex())
        d[off:off + len(new)] = new
        changes.append((off, old, bytes(new)))

    # 1) unknown nations use the Arab officer/ship name pool (index 15) instead of the invalid 16
    put(0x257218, bytes.fromhex('c74424100f000000'),
        bytes.fromhex('c744241010000000'))

    # 2) Select Empire filter: accept any player whose name is in a table (code cave in int3 padding)
    cave = 0x881100                                   # VA, inside a 3947-byte int3 run of .text
    cave_off = cave - EXE_BASE
    assert set(d[cave_off:cave_off + 0x400]) == {0xCC}
    names = [n.encode() + b'\0' for n in PLAYABLE]
    str_va = cave + 0xA00                             # free part of the cave (0x200..0x300 is too small for all names)
    table, strings, p = b'', b'', str_va
    for n in names:
        table += struct.pack('<I', p); strings += n; p += len(n)
    table += struct.pack('<I', 0)
    INTERN, RELEASE, BACK = 0x530800, 0x530890, 0x5d355e
    code = bytearray()
    labels, fix = {}, []
    def emit(b): code.extend(b)
    def here(): return cave + len(code)
    def rel32(target): return struct.pack('<i', target - (here() + 4))
    emit(b'\xBF' + struct.pack('<I', cave + 0x100))          # mov edi, table
    labels['loop'] = here()
    emit(b'\x8B\x07\x85\xC0')                                # mov eax,[edi]; test eax,eax
    emit(b'\x0F\x84'); fix.append((len(code), 'reject')); emit(b'\0\0\0\0')   # jz reject
    emit(b'\x50\xE8'); emit(rel32(INTERN)); emit(b'\x83\xC4\x04')            # push eax; call intern; add esp,4
    emit(b'\x39\x46\x0C\x0F\x94\xC3')                        # cmp [esi+0xc],eax; sete bl
    emit(b'\x85\xC0\x74\x09')                                # test eax,eax; jz +9 (skip release)
    emit(b'\x50\xE8'); emit(rel32(RELEASE)); emit(b'\x83\xC4\x04')           # push eax; call release; add esp,4
    emit(b'\x84\xDB')                                        # test bl,bl
    emit(b'\x0F\x85'); fix.append((len(code), 'accept')); emit(b'\0\0\0\0')   # jnz accept
    emit(b'\x83\xC7\x04')                                    # add edi,4
    emit(b'\xE9'); emit(rel32(labels['loop']))               # jmp loop
    labels['accept'] = here()
    emit(b'\xC6\x44\x24\x13\x01\xEB\x05')                    # mov byte [esp+0x13],1; jmp done
    labels['reject'] = here()
    emit(b'\xC6\x44\x24\x13\x00')                            # mov byte [esp+0x13],0
    emit(b'\x31\xDB\x31\xF6')                                # done: xor ebx,ebx; xor esi,esi
    emit(b'\xE9'); emit(rel32(BACK))                         # jmp back into the function
    for pos_, lab in fix:
        struct.pack_into('<i', code, pos_, labels[lab] - (cave + pos_ + 4))
    assert len(code) < 0x100 and len(table) < 0x100 and len(strings) < 0x400
    assert set(d[cave_off + 0xA00:cave_off + 0xA00 + len(strings)]) == {0xCC}
    put(cave_off, bytes(code))
    put(cave_off + 0x100, table)
    put(cave_off + 0xA00, strings)
    hook = 0x5d344c                                          # "push 'JUG_FRANCIA'" at the start of the name chain
    put(hook - EXE_BASE, b'\xE9' + struct.pack('<i', cave - (hook + 5)), bytes.fromhex('6810458c00'))

    # 3) trade routes: the game shows/hides a pre-drawn route mesh per capital/port pair and crashes when
    #    a pair has no mesh (new or moved capitals). Each "mov byte [eax+0x10c], X" after the mesh lookup
    #    becomes a call to a stub that skips missing meshes.
    stubs = {}
    sva = cave + 0x300
    for val in (0, 1):
        stub = b'\x85\xC0\x74\x07\xC6\x80\x0C\x01\x00\x00' + bytes([val]) + b'\xC3'   # test eax,eax; jz +7; mov byte [eax+0x10c],val; ret
        put(sva - EXE_BASE, stub)
        stubs[val] = sva
        sva += 0x10
    for site, val in ((0x66ad1f, 0), (0x6750f6, 1), (0x675157, 0), (0x675303, 1), (0x675368, 0)):
        old = bytes.fromhex('c6800c010000') + bytes([val])
        put(site - EXE_BASE, b'\xE8' + struct.pack('<i', stubs[val] - (site + 5)) + b'\x90\x90', old)

    # 4) turn order (DefOrdenTurnos.sb): the loader at 0x6c0d30 only reads the lists of the five empires,
    #    so a human playing another nation has no turn order. Replace it with a loop over the same table:
    #    for each name: id = intern(name); ok = load_list(this, &id, node); release(id); stop on failure.
    LOAD_LIST = 0x6c0ad0
    fn = cave + 0x400
    code = bytearray()
    def here2(): return fn + len(code)
    def rel(target): return struct.pack('<i', target - (here2() + 4))
    lab, fx = {}, []
    code += b'\x53\x56\x57\x55'                               # push ebx, esi, edi, ebp
    code += b'\x8B\xF9'                                       # mov edi, ecx (this)
    code += b'\x8B\x6C\x24\x14'                               # mov ebp, [esp+0x14] (node)
    code += b'\xBE' + struct.pack('<I', cave + 0x100)         # mov esi, table
    code += b'\xB3\x01'                                       # mov bl, 1
    lab['loop'] = here2()
    code += b'\x8B\x06\x85\xC0'                               # mov eax,[esi]; test eax,eax
    code += b'\x0F\x84'; fx.append((len(code), 'done')); code += b'\0\0\0\0'
    code += b'\x84\xDB'                                       # test bl,bl
    code += b'\x0F\x84'; fx.append((len(code), 'done')); code += b'\0\0\0\0'
    code += b'\x50\xE8'; code += rel(INTERN); code += b'\x83\xC4\x04'   # push eax; call intern; add esp,4
    code += b'\x50'                                           # push eax (id lives on the stack)
    code += b'\x8B\xD4'                                       # mov edx, esp (&id)
    code += b'\x55\x52'                                       # push ebp (node); push edx (&id)
    code += b'\x8B\xCF\xE8'; code += rel(LOAD_LIST)           # mov ecx, edi; call load_list (ret 8)
    code += b'\x8A\xD8'                                       # mov bl, al
    code += b'\x58'                                           # pop eax (id)
    code += b'\x85\xC0\x74\x09'                               # test eax,eax; jz +9
    code += b'\x50\xE8'; code += rel(RELEASE); code += b'\x83\xC4\x04'  # push eax; call release; add esp,4
    code += b'\x83\xC6\x04'                                   # add esi,4
    code += b'\xE9'; code += rel(lab['loop'])
    lab['done'] = here2()
    code += b'\x8A\xC3\x5D\x5F\x5E\x5B\xC2\x04\x00'           # mov al,bl; pop ebp,edi,esi,ebx; ret 4
    for pos_, l in fx:
        struct.pack_into('<i', code, pos_, lab[l] - (fn + pos_ + 4))
    assert len(code) < 0x100
    put(fn - EXE_BASE, bytes(code))
    entry = 0x6c0d30
    put(entry - EXE_BASE, b'\xE9' + struct.pack('<i', fn - (entry + 5)), bytes.fromhex('83ec185356'))

    # 5) scrollable Select Empire list (up/down buttons and arrow keys), see scroll_patch.py
    import scroll_patch
    sbase = cave + 0x500
    code5, _ = scroll_patch.build(sbase)
    assert set(d[sbase - EXE_BASE:sbase - EXE_BASE + len(code5)]) == {0xCC}
    assert sbase + len(code5) < 0x882000
    scroll_patch.apply(put, sbase, EXE_BASE)

    # 6) Large Address Aware: every province clones the whole map model (FUN_00429050), and with the bigger map
    #    that no longer fits in the 2 GB of a plain 32-bit process; LAA gives 4 GB on 64-bit Windows
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    ch = struct.unpack_from('<H', d, pe + 22)[0]
    put(pe + 22, struct.pack('<H', ch | 0x20), struct.pack('<H', ch))

    # 7) turn visor (flags of the players while the AI moves, UIDefs_VisorTurnos.sb): 0x622f7a centres one row of n
    #    flags with an unsigned shift, so n x 38 px > 1024 puts it far off-screen. Cap n at the column count
    #    ([control+0x64]); the data then uses 3 rows of 22.
    vis = 0x882800
    assert set(d[vis - EXE_BASE:vis - EXE_BASE + 0x20]) == {0xCC}
    put(vis - EXE_BASE, bytes.fromhex('3b48647e038b48648b707403706c0faff1c3'))   # cmp ecx,[eax+64]; jle; mov ecx,[eax+64]; orig 3 ops; ret
    put(0x622f7a - EXE_BASE, bytes.fromhex('e8') + struct.pack('<i', vis - (0x622f7a + 5)) + bytes.fromhex('90909090'), bytes.fromhex('8b707403706c0faff1'))

    # 8) AI speed (re_tools/report_aispeed.md): the AI brain FUN_006f1350 ends the frame after every executed command
    #    (states 5 and 0xB), so each order costs one rendered frame of the whole map. Jump back to the state loop
    #    instead; busy commands (camera, animation) still end the frame, and the 50-command cap stays.
    put(0x6f165f - EXE_BASE, bytes.fromhex('e9fdfcffff'), bytes.fromhex('e962040000'))
    put(0x6f19b3 - EXE_BASE, bytes.fromhex('e9a9f9ffff'), bytes.fromhex('e90e010000'))

    # 9) small AI nations skip AI planning (states 3 and 9 -> 7 / 0xD, as if they found no tasks) but keep their turn,
    #    economy and defence. Flag table (player id from the .mng) at VA 0x882900.
    cave9, table9 = 0x882820, 0x882900
    assert set(d[cave9 - EXE_BASE:table9 - EXE_BASE + 256]) == {0xCC}
    put(cave9 - EXE_BASE, bytes.fromhex(
        'e83300000084c00f8437ece6ffc7868c14000007000000e98af2e6ffe81700000084c00f8408efe6ffc7868c1400000d000000'
        'e96ef2e6ffffb6c01200008b4e0ce82a86ddff85c074168bc8e89f1bdbff3d0001000073080fb68000298800c331c0c3'))
    flags = bytearray(256)
    for pid in AI_SKIP_IDS:
        flags[pid] = 1
    put(table9 - EXE_BASE, bytes(flags))
    put(0x6f1aec - EXE_BASE, struct.pack('<I', 0x882820), bytes.fromhex('64146f00'))
    put(0x6f1b04 - EXE_BASE, struct.pack('<I', 0x88283c), bytes.fromhex('51176f00'))

    # 10) camera auto-focus (province focus, AI moves) zooms to ZOOM_MIN + f*(MAX-MIN); keep the old focus level with
    #     the wider zoom range of Camara.sb (f 0.3 -> 0.7667)
    f = (-1.1 - CAMERA_ZOOM_MIN) / (1.0 - CAMERA_ZOOM_MIN)        # keep the original focus level -1.1
    put(0x8c4ac8 - EXE_BASE, struct.pack('<f', f), bytes.fromhex('9a99993e'))

    # 11) province info dialog: FUN_007f0130 / 007f02b0 / 007f0430 map only the 5 empires to their percentage bar,
    #     image button and text ('BPxx', 'BTxx', 'WTxx') and return 0 for everyone else -> null widget -> crash at
    #     0x552074 once another nation (e.g. Chechenya) holds a share in a province. Others now get hidden dummy
    #     widgets 'BPXX' / 'BTXX' / 'WTXX' (added to the dialog's .sb files by make_map).
    for k, (fn, gb, dummy) in enumerate(((0x7f0130, b'BPGB', b'BPXX'), (0x7f02b0, b'BTGB', b'BTXX'), (0x7f0430, b'WTGB', b'WTXX'))):
        tail = bytes.fromhex('84dbb8') + gb[::-1] + bytes.fromhex('75028bc55f5e5d5b59c20400')
        site = d.find(tail, fn - EXE_BASE, fn - EXE_BASE + 0x200)
        assert site > 0, hex(fn)
        site += 7                                       # at 'jnz +2; mov eax,ebp; pop edi'
        cave = 0x882a00 + 0x20 * k
        assert set(d[cave - EXE_BASE:cave - EXE_BASE + 0x20]) == {0xCC}
        back = site + EXE_BASE + 5                      # the 'pop esi' after the patched bytes
        code = bytes.fromhex('7505b8') + dummy[::-1] + bytes.fromhex('5fe9') + struct.pack('<i', back - (cave + 13))
        put(cave - EXE_BASE, code)
        put(site, bytes.fromhex('e9') + struct.pack('<i', cave - (site + EXE_BASE + 5)), bytes.fromhex('75028bc55f'))
    # 12) late-game AI hang (10-60 min for one big nation, profiled 2026-10-20): FUN_00727790 builds the AI route
    #     table for all pairs of land provinces (195^2 here, 51^2 in 1805); each pair's sea route (FUN_00725d80) tries
    #     every via-node of the nation (41 for a big empire) and each leg (FUN_00725540) again every node of a set.
    #     Both set loops now stop after AI_ROUTE_VIA_CAP nodes (counters in the unused tail of the .data page).
    M = AI_ROUTE_VIA_CAP
    cnt1, cnt2 = 0x942f00, 0x942f04
    h = bytes.fromhex
    jmp = lambda at, to: h('e9') + struct.pack('<i', to - (at + 5))
    jcc = lambda op, at, to: h(op) + struct.pack('<i', to - (at + 6))          # 0f84 je / 0f83 jae, 6 bytes
    caves = 0x882a60                                    # after patch 11's caves (0x882a00-0x882a5f)
    assert set(d[caves - EXE_BASE:caves - EXE_BASE + 0xa0]) == {0xCC}

    def capped_back_edge(at, cmp_bytes, done, head, cnt):
        code = cmp_bytes
        code += jcc('0f84', at + len(code), done)
        code += h('ff05') + struct.pack('<I', cnt)
        code += h('833d') + struct.pack('<I', cnt) + bytes([M])
        code += jcc('0f83', at + len(code), done)
        code += jmp(at + len(code), head)
        return code
    # FUN_00725d80: reset at the 6-byte nop before the loop (0x725e4a), cap at the back edge (0x725f72)
    c3 = caves
    code3 = h('c705') + struct.pack('<I', cnt1) + bytes(4)
    code3 += jmp(c3 + len(code3), 0x725e50)
    put(c3 - EXE_BASE, code3)
    put(0x725e4a - EXE_BASE, jmp(0x725e4a, c3) + h('90'), h('8d9b00000000'))
    c4 = c3 + 0x18
    code4 = capped_back_edge(c4, h('3b6c2428'), 0x725f7c, 0x725e50, cnt1)
    put(c4 - EXE_BASE, code4)
    put(0x725f72 - EXE_BASE, jmp(0x725f72, c4) + h('90') * 5, h('3b6c24280f85d4feffff'))
    # FUN_00725540: reset where the loop is entered (0x725606..0x72560f), cap at the back edge (0x725672)
    c1 = c4 + 0x28
    code1 = h('89442418') + h('c705') + struct.pack('<I', cnt2) + bytes(4)   # mov [esp+18],eax; cnt2 = 0
    code1 += jcc('0f84', c1 + len(code1), 0x725678)                           # flags still from cmp esi,eax
    code1 += jmp(c1 + len(code1), 0x725610)
    put(c1 - EXE_BASE, code1)
    put(0x725606 - EXE_BASE, jmp(0x725606, c1) + h('90') * 5, h('89442418746c8d642400'))
    c2 = c1 + 0x20
    code2 = capped_back_edge(c2, h('3b742418'), 0x725678, 0x725610, cnt2)
    put(c2 - EXE_BASE, code2)
    put(0x725672 - EXE_BASE, jmp(0x725672, c2) + h('90'), h('3b7424187598'))
    assert len(code3) <= 0x18 and len(code4) <= 0x28 and len(code1) <= 0x20 and c2 + len(code2) <= caves + 0xa0

    # 13) the same route table: FUN_007264e0 computes the expensive sea route (FUN_00725d80) for every pair and only
    #     then the land distance (FUN_007117f0, a pure table lookup), keeping the shorter. Eurasia and Africa are one
    #     land mass, so most pairs have a land route: look it up first and compute the sea route only when there is
    #     none (islands, overseas). Skipping leaves the same outputs as 'no sea route found'.
    c5 = 0x882b00
    assert set(d[c5 - EXE_BASE:c5 - EXE_BASE + 0x40]) == {0xCC}
    code5 = h('50') + h('8b4c2414') + h('83c174') + h('505553')      # push eax; ecx = this+0x74; push p3, v, u
    code5 += h('e8') + struct.pack('<i', 0x7117f0 - (c5 + len(code5) + 5))
    code5 += h('3b05') + struct.pack('<I', 0x8d4e28) + h('58')        # cmp eax, [inf]; pop eax (flags kept)
    je_at = len(code5); code5 += h('7400')                            # je sea (patched below)
    code5 += h('8944243c')                                            # the skipped 'mov [esp+0x54],eax' (6 pushes less)
    code5 += jmp(c5 + len(code5), 0x7265d3)                           # continue after the sea-route call
    sea = len(code5)
    code5 += h('8d54243852')                                          # original: lea edx,[esp+0x38]; push edx
    code5 += jmp(c5 + len(code5), 0x7265b9)
    code5 = code5[:je_at + 1] + bytes([sea - (je_at + 2)]) + code5[je_at + 2:]
    put(c5 - EXE_BASE, code5)
    put(0x7265b4 - EXE_BASE, jmp(0x7265b4, c5), h('8d54243852'))
    assert len(code5) <= 0x40

    # 14) ... and the whole table was rebuilt on every unit move into or out of a province of another owner; sea zones
    #     belong to nobody, so each move at sea (the player's fleets, Britain's navy) rebuilt it again, thousands of times
    #     in one turn. Repeated rebuilds for the same AI now run only every AI_ROUTE_REBUILD_EVERY-th time (in between
    #     it keeps the previous table); a different AI always rebuilds at once.
    N = AI_ROUTE_REBUILD_EVERY
    assert N & (N - 1) == 0
    last, cnt = 0x942f08, 0x942f0c
    c6 = 0x882b40
    assert set(d[c6 - EXE_BASE:c6 - EXE_BASE + 0x40]) == {0xCC}
    code6 = h('3b0d') + struct.pack('<I', last)                 # cmp ecx, [last]
    jne_at = len(code6); code6 += h('7500')                     # jne rebuild (patched below)
    code6 += h('ff05') + struct.pack('<I', cnt)                 # inc [cnt]
    code6 += h('f605') + struct.pack('<I', cnt) + bytes([N - 1])  # test byte [cnt], N-1
    jz_at = len(code6); code6 += h('7400')                      # jz rebuild_now (patched below)
    code6 += h('c3')                                            # ret: keep the previous table
    rebuild = len(code6)
    code6 += h('890d') + struct.pack('<I', last)                # mov [last], ecx
    code6 += h('c705') + struct.pack('<I', cnt) + bytes(4)      # mov [cnt], 0
    rebuild_now = len(code6)
    code6 += h('83ec445355')                                    # the original first instructions
    code6 += jmp(c6 + len(code6), 0x727795)
    code6 = bytearray(code6)
    code6[jne_at + 1] = rebuild - (jne_at + 2)
    code6[jz_at + 1] = rebuild_now - (jz_at + 2)
    put(c6 - EXE_BASE, bytes(code6))
    put(0x727790 - EXE_BASE, jmp(0x727790, c6), h('83ec445355'))
    assert len(code6) <= 0x40

    # 15) campaign notifications: SHIFT + OK (click) on a notification box drops the rest of the queued plain ones.
    #     Queue: the Gestion UI object (vtable 0x8c8490) keeps a std::list at +0x1d4 (sentinel), +0x1d8 count,
    #     +0x1dc 'box shown'; node = next, prev, 0xc0-byte entry (+0x14 button mode, +0x1c/+0x20 custom button texts
    #     begin/end, +0xa8 type = DefNotificaciones index, +0xac.. 5 params). FUN_00646c90 moves the model queue
    #     (player data +0x654, FUN_005a1390) into it, FUN_0082a360 inserts, FUN_0082a170 pops the front and shows it in
    #     'CMSB'/'CMBP'/'CMBG'/'CMBX' (callback = type + params -> +0x1e0..+0x1f4). On a button event (0x30) of those
    #     boxes FUN_0082a3d0 builds the answer (FUN_0081b420), sends it to the game mode (0x64a750 -> FUN_0064a240,
    #     the only consumer) and calls FUN_0082a170 at 0x82a520 for the next one. That call now goes to a cave: with
    #     SHIFT down (GetAsyncKeyState, IAT 0x8af228) and no tutorial running (+0x2c0 ->vf 0x50) it unlinks and
    #     destroys (FUN_005e33c0 + free, as FUN_0082a170 does) every queued entry with only an OK button (mode bits
    #     1-3 clear, no custom buttons) whose type FUN_0064a240 ignores, then calls FUN_0082a170 as before; so a dropped
    #     entry ends exactly like a box answered with OK. Kept (still shown in order): every box with Yes/No, Cancel or
    #     custom buttons, and the types FUN_0064a240 acts on (tech researched / government building -> tech tree,
    #     level change, heir choice, resistance detection, feature activations, 0x01, 0x9b, 0xe6/0xee/0xf6/0xff).
    #     Type 2 (construction completed: its OK only refreshes the construction panel 'PCON') is dropped and the
    #     panel is refreshed once afterwards. ESC is not used: the notification buttons only bind KEY_RETURN in data.
    NOTIF_KEEP = (0x00, 0x01, 0x04, 0x7d, 0x8c, 0x9b, 0x9e, 0x9f, 0xa0, 0xa1, 0xa2, 0xa3,
                  0xc7, 0xc8, 0xca, 0xcc, 0xcf, 0xd1, 0xe6, 0xee, 0xf6, 0xff)
    c7, t7 = 0x882c00, 0x882d00                         # code, then a 256-byte 'keep' table indexed by type
    assert set(d[c7 - EXE_BASE:t7 - EXE_BASE + 0x100]) == {0xCC}
    GET_ASYNC_KEY_STATE = 0x8af228                      # USER32 IAT slot
    SHOW_NEXT, NOTIF_DTOR, FREE, FIND_CHILD, PCON_REFRESH = 0x82a170, 0x5e33c0, 0x405cc9, 0x56a600, 0x7e66c0
    SKIPALL_SHOWN = 0x942f20                             # scratch byte: 1 = the box on screen carries a 'Skip all' button (patch 17)
    a7, lab7, fx7 = bytearray(), {}, []

    def e7(hx): a7.extend(h(hx))

    def j7(op, name):                                   # short jcc / jmp to a label, patched below
        e7(op); fx7.append((len(a7), name, 1)); a7.append(0)

    def j7n(op, name):                                  # near jcc (0f 8x rel32) to a label
        e7(op); fx7.append((len(a7), name, 4)); a7.extend(bytes(4))

    def call7(t): a7.extend(b'\xe8' + struct.pack('<i', t - (c7 + len(a7) + 5)))

    def mark7(name): lab7[name] = len(a7)
    # drain when SHIFT is held, or when the visible 'Skip all' button (patch 17, custom id >= 0x100) was pressed.
    # esi = the button event (only caller is the hooked 0x82a520); [esi+8] = pressed id. ecx = this.
    e7('51')                                            # push ecx (save this)
    e7('8b4608'); e7('50')                              # mov eax,[esi+8] (pressed button id); push eax
    e7('6a10'); e7('ff15' + struct.pack('<I', GET_ASYNC_KEY_STATE).hex())   # push 0x10; GetAsyncKeyState(VK_SHIFT)
    e7('5a'); e7('59')                                  # pop edx (pressed); pop ecx (this)
    e7('f6c480'); j7('75', 'drain')                     # test ah,0x80; jnz drain (SHIFT held)
    e7('803d' + struct.pack('<I', SKIPALL_SHOWN).hex() + '00'); j7n('0f84', 'out')   # cmp byte[skipall],0; jz out
    e7('81fa00010000'); j7n('0f82', 'out')             # cmp edx,0x100; jb out (OK pressed, advance one)
    mark7('drain')
    e7('53565755'); e7('8bf1')                          # push ebx,esi,edi,ebp; mov esi,this
    e7('8b8ec0020000'); e7('8b01'); e7('ff5050')        # tutorial manager ->vf 0x50 (mov al,[ecx+0x81]; ret)
    e7('84c0'); j7n('0f85', 'end')                      # tutorial running: leave the queue alone
    e7('33ed')                                          # xor ebp,ebp (1 = a construction notice was dropped)
    e7('8b9ed4010000'); e7('8b3b')                      # ebx = sentinel; edi = first node
    mark7('loop')
    e7('3bfb'); j7('74', 'refresh')                     # cmp edi,ebx; je refresh
    e7('f6471c0e'); j7('75', 'keep')                    # mode & (OK/Cancel | Yes/No | Yes/No/Cancel) -> keep
    e7('8b4728'); e7('3b4724'); j7('75', 'keep')        # custom button texts end != begin -> keep
    e7('8b87b0000000')                                  # eax = type
    e7('3d00010000'); j7('73', 'drop')                  # FUN_0064a240 ignores types >= 0x100
    e7('80b8' + struct.pack('<I', t7).hex() + '00'); j7('75', 'keep')
    e7('83f802'); j7('75', 'drop'); e7('bd01000000')    # type 2: refresh the construction panel at the end
    mark7('drop')
    e7('8b5704'); e7('8b07'); e7('8902'); e7('895004')  # unlink: prev->next = next; next->prev = prev
    e7('50'); e7('8d4f08'); call7(NOTIF_DTOR)           # push next; entry destructor (ecx = node+8)
    e7('57'); call7(FREE); e7('83c404')                 # free(node)
    e7('8386d8010000ff'); e7('5f'); j7('eb', 'loop')    # count -= 1; edi = next
    mark7('keep')
    e7('8b3f'); j7('eb', 'loop')                        # edi = edi->next
    mark7('refresh')
    e7('85ed'); j7('74', 'end')
    e7('68' + b'NOCP'.hex()); e7('8bce'); call7(FIND_CHILD)   # this->child('PCON') (thiscall, ret 4)
    e7('85c0'); j7('74', 'end'); e7('8bc8'); call7(PCON_REFRESH)
    mark7('end')
    e7('8bce'); e7('5d5f5e5b')                          # mov ecx,this; pop ebp,edi,esi,ebx
    mark7('out')
    a7.extend(jmp(c7 + len(a7), SHOW_NEXT))             # the original call target, same stack and ecx
    for pos_, name, size_ in fx7:
        rel_ = lab7[name] - (pos_ + size_)
        if size_ == 1:
            assert -128 <= rel_ <= 127, name
            a7[pos_] = rel_ & 0xff
        else:
            struct.pack_into('<i', a7, pos_, rel_)
    assert len(a7) <= t7 - c7
    keep7 = bytearray(256)
    for t_ in NOTIF_KEEP:
        keep7[t_] = 1
    put(c7 - EXE_BASE, bytes(a7))
    put(t7 - EXE_BASE, bytes(keep7))
    put(0x82a520 - EXE_BASE, b'\xE8' + struct.pack('<i', c7 - (0x82a520 + 5)), h('e84bfcffff'))   # call 0x82a170

    # 16) patch 8 never ends the frame during an AI turn, so the window stops answering Windows ('Not Responding')
    #     after 5 s. Now every AI_YIELD_EVERY-th finished command takes the original path to the end of the frame
    #     (0x6f1ac6: the engine draws a frame and pumps messages), the others keep looping at once.
    Y = AI_YIELD_EVERY
    assert Y & (Y - 1) == 0
    cnt16, c16 = 0x942f10, 0x882e00
    assert set(d[c16 - EXE_BASE:c16 - EXE_BASE + 0x40]) == {0xCC}
    code16 = h('ff05') + struct.pack('<I', cnt16)                       # inc [cnt]
    code16 += h('f605') + struct.pack('<I', cnt16) + bytes([Y - 1])     # test byte [cnt], Y-1
    code16 += jcc('0f84', c16 + len(code16), 0x6f1ac6)                 # every Y-th: end the frame as originally
    code16 += jmp(c16 + len(code16), 0x6f1361)                         # else: next command at once (patch 8)
    put(c16 - EXE_BASE, code16)
    put(0x6f165f - EXE_BASE, jmp(0x6f165f, c16), h('e9fdfcffff'))
    put(0x6f19b3 - EXE_BASE, jmp(0x6f19b3, c16), h('e9a9f9ffff'))

    # 17) visible 'Skip all' button (the user asked for a control instead of Shift+click). Just before FUN_0082a170
    #     shows the front notification, if that notification is droppable by patch 15's rules (single OK button,
    #     no custom buttons, type < 0x100 and not in NOTIF_KEEP, or type >= 0x100) a second button labelled
    #     LTEXT_UI_NOTIF_SKIP_ALL is appended to the entry's button-text vector and SKIPALL_SHOWN is set to 1; for a
    #     notification that keeps its own buttons SKIPALL_SHOWN is set to 0.
    #       - Entry layout (entry = node+8): +0x14 button mode, +0x1c/+0x20 custom button-text vector begin/end,
    #         +0xa8 type; so on the node those are +0x1c, +0x24/+0x28, +0xb0, and the vector object sits at node+0x20
    #         (begin/end/cap at +0x24/+0x28/+0x2c). The label is a string handle: id = FUN_00530800(key) then
    #         handle = FUN_0052fb10(id), id released; the handle is pushed with the engine's own std::vector grow
    #         helper FUN_008327b0, exactly as every other custom-button notification does, so the entry copy-ctor
    #         (FUN_008221b0 -> FUN_0059cb30 duplicates each handle) and destructor (FUN_005e33c0 -> FUN_0041dbc0
    #         releases each handle) keep it balanced. The engine gives this first custom button id 0x100 and draws it
    #         next to OK (MsgBox .BOTONES .CENTER lays out buttons automatically with .XSPACE, so two fit like the
    #         Yes/No boxes already do).
    #       - Pressing it fires the same event 0x30 as OK, so FUN_0082a3d0 sends the answer to the mode (which does
    #         nothing for a droppable type, exactly as for OK) and reaches the patch 15 cave at 0x82a520, which now
    #         also drains the queue when SKIPALL_SHOWN is set and the pressed id is >= 0x100. OK (id 0x80) still
    #         advances one notification; the Shift+click path is unchanged. The label text is resolved from
    #         text/texto/<lang>/Others/TextUI.sb (.ENTRADAS); if the key is missing the engine shows the raw key, no
    #         crash. The hook replaces FUN_0082a170's 'sub esp,0xc4' prologue with a jump to the cave; the cave does
    #         its work with the stack still at the entry state, runs the stolen instruction and jumps back.
    c17 = 0x882e40                                       # after patch 16 (0x882e00..0x882e17)
    SKIP_KEY = b'LTEXT_UI_NOTIF_SKIP_ALL\0'
    str17 = c17 + 0x100                                  # label key string, past the code
    assert set(d[c17 - EXE_BASE:str17 - EXE_BASE + len(SKIP_KEY)]) == {0xCC}
    INTERN_TEXT, DUP_STR, REL_STR, VGROW = 0x530800, 0x52fb10, 0x530890, 0x8327b0
    a17, lab17, fx17 = bytearray(), {}, []

    def e17(hx): a17.extend(h(hx))

    def j17(op, name): e17(op); fx17.append((len(a17), name, 1)); a17.append(0)

    def j17n(op, name): e17(op); fx17.append((len(a17), name, 4)); a17.extend(bytes(4))

    def call17(t): a17.extend(b'\xe8' + struct.pack('<i', t - (c17 + len(a17) + 5)))

    def mark17(name): lab17[name] = len(a17)
    # ecx = this, esp/esi/edi as at FUN_0082a170 entry. Preserve ecx (needed at 0x82a177) and ebx/ebp (callee-saved).
    e17('53'); e17('55'); e17('51')                     # push ebx; push ebp; push ecx (this saved as [esp])
    e17('80b9dc01000000'); j17n('0f85', 'done')         # cmp byte[ecx+0x1dc],0; jne done (a box is already shown)
    e17('83b9d801000000'); j17n('0f84', 'clr')          # cmp dword[ecx+0x1d8],0; je clr (empty queue)
    e17('8b81d4010000'); e17('8b18')                    # eax = sentinel [this+0x1d4]; ebx = first node
    e17('f6431c0e'); j17n('0f85', 'clr')                # node+0x1c mode & 0x0e (Cancel/Yes/No) -> keeps own buttons
    e17('8b4328'); e17('3b4324'); j17n('0f85', 'clr')   # custom button vector end != begin -> keeps own buttons
    e17('8b83b0000000')                                 # eax = type (node+0xb0)
    e17('3d00010000'); j17('73', 'add')                 # type >= 0x100 -> droppable
    e17('0fb680' + struct.pack('<I', t7).hex())         # movzx eax, byte[eax + NOTIF_KEEP table]
    e17('85c0'); j17n('0f85', 'clr')                    # in NOTIF_KEEP -> keeps own buttons
    mark17('add')
    e17('68' + struct.pack('<I', str17).hex()); call17(INTERN_TEXT); e17('83c404')   # push &key; id=FUN_00530800; add esp,4
    e17('8be8')                                          # mov ebp, eax (id)
    e17('50'); call17(DUP_STR); e17('83c404')           # push id; handle=FUN_0052fb10(id); add esp,4
    e17('50')                                           # push handle (save across release)
    e17('55'); call17(REL_STR); e17('83c404')           # push id(ebp); FUN_00530890(id); add esp,4
    e17('5d')                                           # pop ebp (ebp = handle)
    # append handle (ebp) to the std::vector at node+0x20: begin/end/cap at +0x24/+0x28/+0x2c
    e17('8b5324')                                       # mov edx,[ebx+0x24] (begin)
    e17('85d2'); j17('74', 'grow')                      # test edx,edx; jz grow (empty vector)
    e17('8b4328'); e17('2bc2'); e17('c1f802')           # eax = (end-begin)>>2  (size)
    e17('8b4b2c'); e17('2bca'); e17('c1f902')           # ecx = (cap-begin)>>2  (capacity)
    e17('3bc1'); j17('73', 'grow')                      # size >= cap -> grow
    e17('8b4328'); e17('8928'); e17('83c004'); e17('894328')   # eax=end; *end = handle; end += 4; store end
    j17('eb', 'mark1')
    mark17('grow')
    e17('55')                                           # push ebp (value storage for &value)
    e17('8b4328')                                       # mov eax,[ebx+0x28] (end)
    e17('89e1')                                         # mov ecx, esp (&value)
    e17('51'); e17('6a01'); e17('50')                   # push &value; push 1; push end
    e17('8d4b20')                                       # lea ecx,[ebx+0x20] (vector object)
    call17(VGROW); e17('83c404')                        # FUN_008327b0 (ret 0xc); pop value
    mark17('mark1')
    e17('c605' + struct.pack('<I', SKIPALL_SHOWN).hex() + '01'); j17('eb', 'out17')   # SKIPALL_SHOWN = 1
    mark17('clr')
    e17('c605' + struct.pack('<I', SKIPALL_SHOWN).hex() + '00')   # SKIPALL_SHOWN = 0
    mark17('out17'); mark17('done')
    e17('59'); e17('5d'); e17('5b')                     # pop ecx (this); pop ebp; pop ebx
    e17('81ecc4000000')                                 # the stolen 'sub esp,0xc4'
    a17.extend(jmp(c17 + len(a17), 0x82a176))           # back to FUN_0082a170 after its prologue
    for pos_, name, size_ in fx17:
        rel_ = lab17[name] - (pos_ + size_)
        if size_ == 1:
            assert -128 <= rel_ <= 127, name
            a17[pos_] = rel_ & 0xff
        else:
            struct.pack_into('<i', a17, pos_, rel_)
    assert len(a17) <= str17 - c17
    put(c17 - EXE_BASE, bytes(a17))
    put(str17 - EXE_BASE, SKIP_KEY)
    put(0x82a170 - EXE_BASE, jmp(0x82a170, c17) + h('90'), h('81ecc4000000'))   # hook FUN_0082a170 prologue

    # 18) campaign cheats (re_tools/report_cheats.md), round 1.
    #   a) The built-in cheats (Ctrl+Alt + F/G/U fast build/training/research, D/N/Y/X +10000 gold/food/raw/men) work
    #      without typing PYROGODMODE on the credits screen: that code only sets bit 0x4000 of the game-state flags
    #      [GS+0xad8] (Lua switchCheatMode, 0x767ce0), and the only readers are the 7 'je' below in FUN_0082a3d0 (map UI).
    #      All 7 cheats act on the local human only ([ui+0x160]; the fast flags are gated by 'is human' FUN_0065b4a0).
    #   b) 'Cheats' button in the campaign ESC menu (UIDefs_IngameMenu.sb, written by make_map: 'EMCH' under Save Game
    #      links to the panel menu 'EM_4' whose buttons are 'CH_A'..'CH_Z'). Every button of the ESC menu reaches the
    #      mode handler FUN_00628c30 (thiscall(M; event*), ret 4: the menu manager forwards child events before it
    #      follows .ENLACES). Its entry now jumps to a dispatcher: event 0x19 (click) with id 'CH_A'+i, i < 26, calls
    #      table[i] with ecx = campaign-map UI object (vtable 0x8c8490; captured at its event entry FUN_0082b580 into
    #      CHEAT_UI). A handler returns eax = 0 or an LTEXT key that is shown in an OK box over the menu (same call as
    #      the Exit confirmation, FUN_005b8c40 on [M+0x234], id 'MBCH', flags 0xe0000001 = OK only).
    #      Handler convention (also for patches 19+): thiscall(ecx = map UI) -> eax; keep ebx/esi/edi/ebp.
    #      Map UI fields: +0xa8 armies, +0xb8 provinces/model, +0xc0 players, +0xd0 game state, +0x160 local player id.
    for va, old in ((0x82a7eb, '0f846dfdffff'), (0x82a818, '0f8440fdffff'), (0x82a845, '0f8413fdffff'),   # TC_1..3
                    (0x82a871, '0f84e7fcffff'), (0x82a8dd, '0f847bfcffff'), (0x82a9f8, '0f8460fbffff'),   # TC_4,5,6
                    (0x82a98c, '0f84ccfbffff')):                                                          # TC_7
        put(va - EXE_BASE, h('660f1f440000'), h(old))                     # 6-byte NOP instead of 'je skip'
    c18 = CHEAT_CAVE
    assert set(d[c18 - EXE_BASE:c18 - EXE_BASE + 0x400]) == {0xCC}
    C_CAP, C_DISP, C_INFO, C_HND = c18, c18 + 0x20, c18 + 0x80, c18 + 0x130
    C_PAIRS, C_STR = CHEAT_TABLE + 26 * 4, CHEAT_TABLE + 0x80
    FIND_PLAYER, ADD_RES, RES_VTBL = 0x65ae90, 0x6353f0, 0x8b6ad8
    INTERN_TEXT, REL_STR = 0x530800, 0x530890                            # string id from a key / release it (cdecl)
    UI_OBJ, OBJ_CTOR, OBJ_DTOR, VEC_DTOR, MSGBOX = 0x5643a0, 0x53c0d0, 0x53c130, 0x41e330, 0x5b8c40
    # key strings, then the ON/OFF pairs of the three fast-flag toggles
    strs, str_va = bytearray(), {}
    for k in ['LTEXT_UI_CHEATS_TITLE'] + ['LTEXT_UI_CHEAT_%s_%s' % (f, s) for f in ('FASTBUILD', 'FASTTRAIN', 'FASTRESEARCH')
                                         for s in ('ON', 'OFF')]:
        str_va[k] = C_STR + len(strs); strs += k.encode() + b'\0'
    assert C_STR + len(strs) <= CHEAT_FREE
    pairs = b''.join(struct.pack('<II', str_va['LTEXT_UI_CHEAT_%s_ON' % f], str_va['LTEXT_UI_CHEAT_%s_OFF' % f])
                     for f in ('FASTBUILD', 'FASTTRAIN', 'FASTRESEARCH'))
    # capture of the map UI object at FUN_0082b580 (its event entry; all map modes call FUN_0082a3d0 from there)
    a = CaveAsm(C_CAP)
    a.e('890d'); a.imm(CHEAT_UI)                                         # mov [CHEAT_UI], ecx
    a.e('50 8b8160010000 a3'); a.imm(CHEAT_HUMAN); a.e('58')             # [CHEAT_HUMAN] = [ui+0x160] (patch 32), eax kept
    a.e('56 8bf1 807e1800')                                              # displaced: push esi; mov esi,ecx; cmp byte[esi+0x18],0
    a.jmp(0x82b587)                                                      # (flags of the cmp survive the jmp)
    cap = a.done(); assert len(cap) <= C_DISP - C_CAP
    # dispatcher at FUN_00628c30 (this = M, [esp+4] = event)
    a = CaveAsm(C_DISP)
    a.e('8b442404 833819'); a.js('75', 'orig')                           # event type 0x19 (button clicked)?
    a.e('8b4004 2d415f4843 83f819'); a.js('77', 'orig')                  # i = id - 'CH_A' (unsigned) <= 25 ?
    a.e('56 8bf1')                                                       # push esi; esi = M
    a.e('8b1485'); a.imm(CHEAT_TABLE)                                    # edx = table[i]
    a.e('85d2'); a.js('74', 'done')
    a.e('8b0d'); a.imm(CHEAT_UI); a.e('85c9'); a.js('74', 'done')
    a.e('8139'); a.imm(0x8c8490); a.js('75', 'done')                     # still a campaign-map UI object
    a.e('ffd2 85c0'); a.js('74', 'done')                                 # eax = handler(ecx = map UI)
    a.e('50 8bce'); a.call(C_INFO)                                       # show_info(M, key)
    a.mark('done'); a.e('5e c20400')
    a.mark('orig'); a.e('83ec54 53 56'); a.jmp(0x628c35)                 # displaced: sub esp,0x54; push ebx; push esi
    disp = a.done(); assert len(disp) <= C_INFO - C_DISP
    # show_info(this = M, [esp+4] = LTEXT key) ret 4: the Exit confirmation's call (0x628cb3) with id 'MBCH', OK only
    a = CaveAsm(C_INFO)
    a.e('55 8bec 83ec58 53 56 57 8bf1')               # [ebp-0x10] vector(16) [ebp-0x50] obj(0x40) [ebp-0x54] title [ebp-0x58] body
    a.e('ffb60c030000'); a.call(UI_OBJ); a.e('83c404 8bf8')             # edi = ESC-menu UI object (handle [M+0x30c])
    a.e('68'); a.imm(str_va['LTEXT_UI_CHEATS_TITLE']); a.call(INTERN_TEXT); a.e('83c404 8945ac')
    a.e('ff7508'); a.call(INTERN_TEXT); a.e('83c404 8945a8')
    a.e('33c0 8945f4 8945f8 8945fc')                                     # vector first/last/end = 0
    a.e('8d4db0'); a.call(OBJ_CTOR)                                      # eax = obj
    a.e('68dcc09300 50 8d45f0 50 6a00 68010000e0 6a01 8d45a8 50 8d45ac 50 684843424d 57')
    a.e('8b8e34020000'); a.call(MSGBOX)                                  # (parent,'MBCH',&title,&body,1,0xe0000001,0,&vec,obj,0x93c0dc)
    a.e('8d4df0'); a.call(VEC_DTOR)
    a.e('8d4db0'); a.call(OBJ_DTOR)
    for slot in ('8b45ac', '8b45a8'):                                    # release title, body
        a.e(slot + ' 85c0 7407 50'); a.call(REL_STR); a.e('59')
    a.e('5f 5e 5b 8be5 5d c20400')
    info = a.done(); assert len(info) <= C_HND - C_INFO
    # handlers
    a = CaveAsm(C_HND)
    a.mark('add_res')                                  # ecx = UI, edx = field of the resource struct: as the Ctrl+Alt keys
    a.e('56 57 8bf1 8bfa ffb660010000 8b8ec0000000'); a.call(FIND_PLAYER)   # FUN_0065ae90([ui+0xc0], [ui+0x160])
    a.e('85c0'); a.js('74', 'res_out')
    a.e('6a00' * 7); a.e('68'); a.imm(RES_VTBL)                          # reason 0, fields +0x18..+4 = 0, vtable
    a.e('c7043c'); a.imm(10000)                                          # mov dword [esp+edi], 10000
    a.e('8bc8'); a.call(ADD_RES)                                         # FUN_006353f0(player; struct, 0) ret 0x20
    a.mark('res_out'); a.e('33c0 5f 5e c3')
    a.mark('toggle')                                   # ecx = UI, edx = mask in [GS+0xad8], eax = &{key_on, key_off}
    a.e('8b89d0000000 3191d80a0000 8591d80a0000'); a.js('75', 'tg_on'); a.e('83c004')
    a.mark('tg_on'); a.e('8b00 c3')
    a.mark('toggle_byte')                              # for patches 19+: edx = toggle byte, eax = &{key_on, key_off}
    a.e('803201'); a.js('75', 'tb_on'); a.e('83c004'); a.mark('tb_on'); a.e('8b00 c3')
    hnd18 = {}
    for name, field in (('gold', 4), ('food', 0xc), ('raw', 8), ('men', 0x10)):
        hnd18[name] = a.here(); a.e('ba'); a.imm(field); a.jl('e9', 'add_res')
    for k, (name, mask) in enumerate((('fastbuild', 1), ('fasttrain', 2), ('fastres', 0x400))):
        hnd18[name] = a.here(); a.e('ba'); a.imm(mask); a.e('b8'); a.imm(C_PAIRS + 8 * k); a.jl('e9', 'toggle')
    hnd = a.done(); assert len(hnd) <= CHEAT_TABLE - C_HND
    toggle_byte18 = a.lab['toggle_byte']                 # used by the toggles of patches 19+
    table = bytearray(26 * 4)
    for i, name in enumerate(('gold', 'food', 'raw', 'men', 'fastbuild', 'fasttrain', 'fastres')):   # 'CH_A'..'CH_G'
        struct.pack_into('<I', table, 4 * i, hnd18[name])
    put(C_CAP - EXE_BASE, cap)
    put(0x82b580 - EXE_BASE, jmp(0x82b580, C_CAP) + h('9090'), h('568bf1807e1800'))
    put(C_DISP - EXE_BASE, disp)
    put(C_INFO - EXE_BASE, info)
    put(C_HND - EXE_BASE, hnd)
    put(CHEAT_TABLE - EXE_BASE, bytes(table))
    put(C_PAIRS - EXE_BASE, pairs)
    put(C_STR - EXE_BASE, bytes(strs))
    put(0x628c30 - EXE_BASE, jmp(0x628c30, C_DISP), h('83ec545356'))

    # ---- round 2 helpers: handler stubs and their key strings / ON-OFF pairs live after round 1 in the same int3 run
    #      (0x88a900-0x88a9ff: movement + fog caves; 0x88aa00-0x88acff: handlers; 0x88ad00-0x88afff: strings/pairs)
    r2 = {'hnd': 0x88aa00, 'str': 0x88ad00}

    def cave_free(va, n):
        assert set(d[va - EXE_BASE:va - EXE_BASE + n]) == {0xCC}, hex(va)

    def r2_str(s):
        va = r2['str']; bs = s.encode() + b'\0'
        cave_free(va, len(bs)); put(va - EXE_BASE, bs); r2['str'] += len(bs)
        assert r2['str'] <= 0x88b000
        return va

    def r2_pair(on_key, off_key):
        on_va, off_va = r2_str(on_key), r2_str(off_key)
        r2['str'] = (r2['str'] + 3) & ~3
        va = r2['str']; cave_free(va, 8); put(va - EXE_BASE, struct.pack('<II', on_va, off_va)); r2['str'] += 8
        return va

    def r2_handler(build):                              # build(a: CaveAsm) emits a handler (thiscall(ecx = map UI) -> eax)
        a = CaveAsm(r2['hnd']); build(a); code = a.done()
        cave_free(r2['hnd'], len(code)); put(r2['hnd'] - EXE_BASE, code)
        va = r2['hnd']; r2['hnd'] = (r2['hnd'] + len(code) + 15) & ~15
        assert r2['hnd'] <= 0x88ad00
        return va

    def r2_slot(letter, handler_va):                    # panel button 'CH_<letter>' -> handler
        i = ord(letter) - ord('A')
        put(CHEAT_TABLE + 4 * i - EXE_BASE, struct.pack('<I', handler_va), bytes(4))

    def r2_toggle(letter, byte_va, key, extra=None):   # ON/OFF toggle button on a byte in the .data tail
        pair = r2_pair('LTEXT_UI_CHEAT_%s_ON' % key, 'LTEXT_UI_CHEAT_%s_OFF' % key)

        def build(a):
            if extra is None:
                a.e('ba'); a.imm(byte_va); a.e('b8'); a.imm(pair); a.jmp(toggle_byte18)
            else:                                       # toggle, then run extra(a) with ecx = map UI; keep eax (the key)
                a.e('ba'); a.imm(byte_va); a.e('b8'); a.imm(pair); a.call(toggle_byte18)
                a.e('50'); extra(a); a.e('58 c3')
        r2_slot(letter, r2_handler(build))

    # 19) GODMODE (panel 'CH_H', toggle CHEAT_GOD): the local human's armies and fleets lose nobody in AUTO-RESOLVED
    #     battles and win them. Land: FUN_006be0f0 (real resolves come from FUN_006be5e0 at 0x6be604 and the pursuit
    #     FUN_006be290 at 0x6be434; the AI's battle predictions call it from 0x715f09/0x71660a/0x71770b/0x717aa4 and are
    #     left alone) runs the simulation FUN_006b6060 (ret 0x2c) and gives FUN_006bdec0(battle, resA, resB) the result
    #     of each side = 1 + fraction left (2.0 = untouched; losses = floor(men * (2 - res)); the attacker wins only if
    #     resA > resB). Cave P (on the call of the simulation) sets CHEAT_GOD_ON for a real human battle; cave M then
    #     gives the human side's stat multiplier table (FUN_006b4ea0, normally DefReglasCombateAutomatico.sb's
    #     DIFICULTAD_* at R+0x394/0x3ac/0x3c4, used for the local player only) 6 x 100.0; cave L clamps the human side's
    #     result to 2.0 (and an untouched enemy to just below 2.0, so the human attacker still wins). Naval: FUN_006be200
    #     (only called by the real resolve at 0x6be953; its simulation has no multipliers) is clamped the same way (N).
    #     The human = FUN_0065ae50([R+0x30]); battle+8 attacker id, +0xc defender id. Nothing stored is changed.
    GOD_P, GOD_M, GOD_TBL, GOD_L, GOD_N = 0x883a00, 0x883a30, 0x883a58, 0x883a80, 0x883b00
    cave_free(0x883a00, 0x200)
    HUMAN_ID, SIMULATE = 0x65ae50, 0x6b6060
    a = CaveAsm(GOD_P)
    a.e('803d'); a.imm(CHEAT_GOD); a.e('00'); a.js('74', 'go')
    a.e('8b842438010000')                                                # return address of FUN_006be0f0
    a.e('3d'); a.imm(0x6be609); a.js('74', 'set')                        # from FUN_006be5e0 (land auto-resolve)
    a.e('3d'); a.imm(0x6be439); a.js('75', 'go')                         # from FUN_006be290 (pursuit battle)
    a.mark('set'); a.e('c605'); a.imm(CHEAT_GOD_ON); a.e('01')
    a.mark('go'); a.jmp(SIMULATE)                                        # the simulation returns straight to 0x6be1cf
    god_p = a.done()
    a = CaveAsm(GOD_M)
    a.e('803d'); a.imm(CHEAT_GOD_ON); a.e('00'); a.js('74', 'orig')
    a.e('ddd8 b8'); a.imm(GOD_TBL); a.jmp(0x6b4eff)                      # fstp st0 (as the original); eax = table
    a.mark('orig'); a.e('8b5158 ddd8 8b5244'); a.jmp(0x6b4ed9)
    god_m = a.done()

    def god_clamp(org, check, battle_off, a_off, b_off, displaced, back):
        a = CaveAsm(org)
        check(a)
        a.e('8b4e30'); a.call(HUMAN_ID); a.e('85c0'); a.js('74', 'orig')   # eax = human id ([R+0x30] = players)
        a.e('8b9424'); a.imm(battle_off); a.e('394208'); a.js('75', 'def')  # human = attacker?
        a.e('c74424%02x' % a_off); a.imm(0x40000000)                       # attacker result 2.0: no losses
        a.e('817c24%02x' % b_off); a.imm(0x40000000); a.js('7c', 'orig')
        a.e('c74424%02x' % b_off); a.imm(0x3fffffff); a.js('eb', 'orig')   # untouched enemy: just below 2.0 -> loses
        a.mark('def'); a.e('39420c'); a.js('75', 'orig')                    # human = defender?
        a.e('c74424%02x' % b_off); a.imm(0x40000000)                       # defender 2.0 (ties go to the defender)
        a.mark('orig'); a.e(displaced); a.jmp(back)
        return a.done()

    def chk_land(a):                                    # only after cave P marked a real human battle; clear the mark
        a.e('803d'); a.imm(CHEAT_GOD_ON); a.e('00'); a.js('74', 'orig'); a.e('c605'); a.imm(CHEAT_GOD_ON); a.e('00')

    def chk_sea(a):
        a.e('803d'); a.imm(CHEAT_GOD); a.e('00'); a.js('74', 'orig')
    god_l = god_clamp(GOD_L, chk_land, 0x10c, 0x08, 0x0c, '8b44240c 8b4c2408', 0x6be1e7)
    god_n = god_clamp(GOD_N, chk_sea, 0x8c, 0x0c, 0x08, '8b542408 8b44240c', 0x6be27b)
    assert GOD_P + len(god_p) <= GOD_M and GOD_M + len(god_m) <= GOD_TBL and GOD_L + len(god_l) <= GOD_N
    assert GOD_N + len(god_n) <= 0x883c00
    put(GOD_P - EXE_BASE, god_p); put(GOD_M - EXE_BASE, god_m); put(GOD_TBL - EXE_BASE, struct.pack('<6f', *[100.0] * 6))
    put(GOD_L - EXE_BASE, god_l); put(GOD_N - EXE_BASE, god_n)
    put(0x6be1ca - EXE_BASE, b'\xe8' + struct.pack('<i', GOD_P - (0x6be1ca + 5)), h('e8917effff'))
    put(0x6b4ed1 - EXE_BASE, jmp(0x6b4ed1, GOD_M) + h('909090'), h('8b5158ddd88b5244'))
    put(0x6be1df - EXE_BASE, jmp(0x6be1df, GOD_L) + h('909090'), h('8b44240c8b4c2408'))
    put(0x6be273 - EXE_BASE, jmp(0x6be273, GOD_N) + h('909090'), h('8b5424088b44240c'))
    r2_toggle('H', CHEAT_GOD, 'GODMODE')

    # 20) UNLIMITED MOVEMENT (panel 'CH_I', toggle CHEAT_MOVE): an army can go only one province per turn because the
    #     drop targets are the provinces within reach 1 of where it stands: picking up a figure (FUN_00822880, only the
    #     local player's own armies/fleets, 0x8228ac) pushes depth 1 for FUN_00663b30(prov, mask, depth, set) at 0x8229d4.
    #     With the toggle on the depth becomes MOVE_DEPTH (not for a commander without troops, mask 0x17). The order
    #     itself only stores origin and destination: the UI accepts any province of that set (FUN_0081d9d0), the model
    #     checks relations / passage but no distance (FUN_00649990 -> FUN_00663590 -> FUN_00663440, FUN_00660660), and
    #     FUN_00663d40 carries every order out at the end of the turn without an adjacency test. The game's own neighbour
    #     search FUN_00661010 is kept as it is: it goes through provinces and sea zones of ANY owner (a province of
    #     another holder is a destination where mask bit 8 allows), so armies and fleets reach MOVE_DEPTH steps through
    #     any territory; entering the land of a nation not at war still brings the game's own war / passage question.
    #     (An earlier version stopped the search at provinces of another holder country, record +0x10, which also cut
    #     through the player's own multi-country empire.)
    MOVE_DEPTH, c20 = 8, CHEAT_FREE
    cave_free(c20, 0x40)
    a = CaveAsm(c20)
    a.e('803d'); a.imm(CHEAT_MOVE); a.e('00'); a.js('74', 'done')
    a.e('83f817'); a.js('74', 'done')                                    # commander without troops: keep 1
    a.e('c70424'); a.imm(MOVE_DEPTH)                                     # replace the pushed depth 1
    a.mark('done'); a.e('8b8e94010000'); a.jmp(0x8229e4)                # displaced: mov ecx,[esi+0x194]
    mv = a.done(); assert len(mv) <= 0x40
    put(c20 - EXE_BASE, mv)
    put(0x8229de - EXE_BASE, jmp(0x8229de, c20) + h('90'), h('8b8e94010000'))
    r2_toggle('I', CHEAT_MOVE, 'MOVE')

    # 21) FINISH ALL QUEUES (panel 'CH_J', one-shot): every queued building of the human in every province and every
    #     queued unit of every barracks / shipyard is completed now, the normal way. The construction / troop / ship
    #     managers (vtables 0x8ca2e8 / 0x8ca3b0 / 0x8ca418, checked) are taken from the campaign view, which caches them
    #     at its construction: V = [ui+0x58] - 0x1ad0 (vtable 0x8c7018 at [ui+0x58]), [V+0x1b3c] construction,
    #     [V+0x1b24] troops, [V+0x1b2c] ships, i.e. [[ui+0x58]+0x6c / +0x54 / +0x5c] (verified in the running game; the
    #     'RSYS' registry cannot be used: its service list is empty once the campaign is set up, so an earlier version
    #     found no manager and did nothing). The managers have a start-of-turn pass vf+4(pid) that steps the head item
    #     of each of that player's queues (pays it,
    #     counts its turns down, completes it with building / unit / notification as usual); with the Fast Build and
    #     Fast Training bits of the game state ([mgr+4]+0xad8 bits 1|2, human only) the head completes in that pass. The
    #     cave sets both bits, runs the three passes QUEUE_PASSES times (the human's queues hold up to HUMAN_QUEUE_CAP
    #     items with patch 27) and restores the bits.
    #     Items the player cannot pay for, or in blocked provinces, wait as usual. Research is left out (an era change
    #     in the middle of a turn); the Fast Research toggle covers it.
    c21 = 0x883c00
    cave_free(c21, 0x180)
    a = CaveAsm(c21)                                    # finish_all(ui): stdcall ret 4, keeps ebx/esi/edi/ebp
    a.e('53 56 57 55 83ec10 8b442424')                   # [esp] troops, [esp+4] ships, [esp+0xc] saved flags; eax = ui
    a.e('8bb860010000 8b4058 85c0'); a.jl('0f84', 'out')  # edi = [ui+0x160] (human); eax = [ui+0x58] (view+0x1ad0)
    a.e('8138'); a.imm(0x8c7018); a.jl('0f85', 'out')
    a.e('8b686c 8b4854 890c24 8b485c 894c2404')          # ebp = construction, [esp] = troops, [esp+4] = ships
    a.e('85ed'); a.jl('0f84', 'out')
    a.e('817d00'); a.imm(0x8ca2e8); a.jl('0f85', 'out')                 # construction manager?
    a.e('8b0424 85c0'); a.js('74', 't_bad'); a.e('8138'); a.imm(0x8ca3b0); a.js('74', 't_ok')
    a.mark('t_bad'); a.e('c7042400000000'); a.mark('t_ok')
    a.e('8b442404 85c0'); a.js('74', 's_bad'); a.e('8138'); a.imm(0x8ca418); a.js('74', 's_ok')
    a.mark('s_bad'); a.e('c744240400000000'); a.mark('s_ok')
    a.e('8b4504 8b88d80a0000 894c240c 8388d80a000003')   # save flags; or [gs+0xad8], 3 (fast build + fast training)
    a.e('b3%02x' % QUEUE_PASSES)                         # one pass per item a queue can hold (patch 27 caps)
    a.mark('pass')
    a.e('57 8bcd 8b01 ff5004')                           # construction vf+4(pid)
    a.e('8b0c24 85c9'); a.js('74', 's1'); a.e('57 8b01 ff5004'); a.mark('s1')
    a.e('8b4c2404 85c9'); a.js('74', 's2'); a.e('57 8b01 ff5004'); a.mark('s2')
    a.e('fecb'); a.js('75', 'pass')
    a.e('8b4504 8b4c240c 83e103 8b90d80a0000 83e2fc 0bd1 8990d80a0000')   # restore bits 1|2 exactly
    a.mark('out'); a.e('83c410 5d 5f 5e 5b c20400')
    core21 = a.done(); assert len(core21) <= 0x180
    put(c21 - EXE_BASE, core21)
    key21 = r2_str('LTEXT_UI_CHEAT_QUEUES_DONE')

    def build21(a):
        a.e('56 8bf1 56'); a.call(c21)                                    # finish_all(ui)
        a.e('68'); a.imm(0x50434f4e); a.e('8bce'); a.call(0x56a600)      # ui->child('PCON')
        a.e('85c0'); a.js('74', 'o'); a.e('8bc8'); a.call(0x7e66c0)     # refresh the construction panel
        a.mark('o'); a.e('b8'); a.imm(key21); a.e('5e c3')
    r2_slot('J', r2_handler(build21))

    # 22) REVEAL MAP (panel 'CH_K', toggle CHEAT_FOG): fog of war off for the human's map display. The province flags
    #     +0xc9 (known) and +0xc8 (enemy armies shown) of the map are only set by FUN_0065ffb0 / FUN_00660110 (recompute
    #     for the human, called together by FUN_00663430) and FUN_00661570 (after the human's armies move); with the
    #     toggle on they mark the set of all provinces visible instead of the human's visible set. Display only (map
    #     tint, fog texture, enemy army figures/tooltips); diplomacy, trade reach and the AI are unchanged. After the
    #     toggle the handler calls FUN_00663430 ([ui+0xb8]) so it takes effect at once (the fog texture rebuilds itself).
    c22 = CHEAT_FREE + 0x40
    cave_free(c22, 0xc0)

    def fog_recompute(org, setter, skip, back):
        a = CaveAsm(org)
        a.e('803d'); a.imm(CHEAT_FOG); a.e('00'); a.js('74', 'normal')
        a.e('8d44243c 50 6a01 8bce'); a.call(setter); a.jmp(skip)         # setter(1, &all provinces); skip the rest
        a.mark('normal'); a.e('8d542408 52'); a.jmp(back)                   # displaced: lea edx,[esp+8]; push edx
        return a.done()
    f1 = fog_recompute(c22, 0x65e7c0, 0x6600f0, 0x6600cb)                  # FUN_0065ffb0 (known, +0xc9)
    f2 = fog_recompute(c22 + 0x30, 0x65e730, 0x66025f, 0x66023b)           # FUN_00660110 (military, +0xc8)
    a = CaveAsm(c22 + 0x60)                                                 # FUN_00661570
    a.e('8d542408 52')                                                      # displaced: lea edx,[esp+8]; push edx (all)
    a.e('803d'); a.imm(CHEAT_FOG); a.e('00'); a.js('74', 'normal')
    a.e('6a01 8bce'); a.call(0x65e730)                                      # all provinces military-visible
    a.e('8d4c2408'); a.call(0x4f7c90); a.jmp(0x6615f4)                     # free the set; function epilogue
    a.mark('normal'); a.jmp(0x6615a3)
    f3 = a.done()
    assert len(f1) <= 0x30 and len(f2) <= 0x30 and len(f3) <= 0x60
    put(c22 - EXE_BASE, f1); put(c22 + 0x30 - EXE_BASE, f2); put(c22 + 0x60 - EXE_BASE, f3)
    put(0x6600c6 - EXE_BASE, jmp(0x6600c6, c22), h('8d54240852'))
    put(0x660236 - EXE_BASE, jmp(0x660236, c22 + 0x30), h('8d54240852'))
    put(0x66159e - EXE_BASE, jmp(0x66159e, c22 + 0x60), h('8d54240852'))

    def fog_refresh(a):                                 # ecx = map UI: FUN_00663430([ui+0xb8]) recomputes both flags
        a.e('8b89b8000000'); a.call(0x663430)
    r2_toggle('K', CHEAT_FOG, 'REVEAL', fog_refresh)

    # 23) SPAWN ARMY (panel 'CH_L', one-shot): a marshal with 6 battalions of the best troop types the human's nation has
    #     appears in its home capital (else in another owned capital, else in any owned land province with a free army
    #     slot). Same call as the quest rewards (FUN_00652f90) and the tutorial's crea_ficha (FUN_00767220):
    #     FUN_0068b600(this = army manager [ui+0xa8]; pid, &commander name, &vector of unit names, province id) ret 0x10
    #     creates commander, army, map figure and battalions. It does not check the names, so every name is first checked
    #     with FUN_005bc8e0(this = [[ui+0xa8]+0x24]; &name, troop nation) ret 8 (0 = this nation has no such troop).
    #     Names are interned for the call and released afterwards (FUN_00530800 / FUN_00530890). Province: owner =
    #     FUN_0063ab00 (must be the human), free slots = vf+0x48(player) > 0, capital = [prov+0x8c] != 0, home pais =
    #     player data +0x408 vs province record +0xc (FUN_005a6020); sea zones (vtable 0x8c6da0) are skipped.
    c23 = 0x883700
    cave_free(c23, 0x300)
    SP_NAMES = ['MARISCAL', 'ELITE', 'GRANADERO', 'FUSILERO', 'TIRADOR', 'CAB_CORACERO', 'CAB_DRAGON', 'CAB_HUSAR',
                'CANON', 'OBUS']
    SP_SLOTS = [[1, 2, 3], [2, 3], [4, 3], [5, 6, 7], [6, 7], [8, 9]]      # 6 battalions, best candidate first
    FIND_PLAYER2, NATION_OF, HOME_PAIS, TYPE_OF = 0x65ae90, 0x634f60, 0x634430, 0x5bc8e0
    PROV_REC, OWNER_OF, MAKE_ARMY = 0x5a6020, 0x63ab00, 0x68b600
    sp_ptrs = c23 + 0x200                                # name pointers, strings and the slot stream follow the code
    sp_strs, sp_bytes = c23 + 0x200 + 4 * len(SP_NAMES), b''
    for n in SP_NAMES:
        sp_bytes += n.encode() + b'\0'
    sp_slots = sp_strs + len(sp_bytes)
    def spawn_code(a, units):                            # spawn(ecx = map UI) -> eax = army id or 0
        # frame: [ebp-0x28] 10 name ids, [ebp-0x40] 6 unit ids, [ebp-0x50] vector {alloc, first, last, end},
        #        [ebp-0x54] human id, [ebp-0x58] troop nation, [ebp-0x5c] UI, [ebp-0x60] result
        # units=False (patch 37, FREE GENERAL): the same marshal and province search with an empty unit vector.
        a.e('55 8bec 83ec60 53 56 57 894da4 c745a000000000 33db')
        a.mark('il'); a.e('ff349d'); a.imm(sp_ptrs); a.call(INTERN_TEXT); a.e('83c404 89449dd8 43 83fb0a'); a.js('72', 'il')
        a.e('8b4da4 8b8160010000 8945ac 50 8b89c0000000'); a.call(FIND_PLAYER2)
        a.e('85c0'); a.jl('0f84', 'release')
        a.e('8bf0 8bce'); a.call(NATION_OF); a.e('8945a8')
        a.e('ff75a8 8d45d8 50 8b4da4 8b89a8000000 8b4924'); a.call(TYPE_OF)  # the marshal exists for this nation?
        a.e('85c0'); a.jl('0f84', 'release')
        if units:
            a.e('8d7dc0 bb'); a.imm(sp_slots)
            a.mark('sl'); a.e('0fb603 43 3cfe'); a.js('74', 'sdone'); a.e('3cff'); a.js('74', 'sl')
            a.e('8d4485d8 50 ff75a8 50 8b4da4 8b89a8000000 8b4924'); a.call(TYPE_OF)
            a.e('5a 85c0'); a.js('74', 'sl')                     # not in this nation: next candidate
            a.e('8b02 8907 83c704')                              # take it
            a.mark('skip'); a.e('0fb603 43 3cff'); a.js('75', 'skip'); a.js('eb', 'sl')
            a.mark('sdone'); a.e('8d45c0 3bf8'); a.jl('0f84', 'release')
        else:
            a.e('8d7dc0 8d45c0')                                 # edi = eax = first: no battalions
        a.e('8945b4 897db8 897dbc')                          # vector first / last / end
        a.e('8bce'); a.call(HOME_PAIS); a.e('8bf0 bb02000000')   # esi = home pais; ebx = pass 2, 1, 0
        a.mark('pass'); a.e('8b45a4 8b80b8000000 8bb888000000')  # edi = provinces.first
        a.mark('pl'); a.e('8b45a4 8b80b8000000 3bb88c000000'); a.jl('0f83', 'pend')
        a.e('8b0f 85c9'); a.jl('0f84', 'next')
        a.e('8139'); a.imm(0x8c6da0); a.jl('0f84', 'next')   # sea zone
        a.e('85db'); a.js('74', 'own')
        a.e('83b98c00000000'); a.jl('0f84', 'next')          # passes 2/1: must hold a capital
        a.e('83fb01'); a.js('74', 'own')
        a.e('ff717c 8b4940'); a.call(PROV_REC); a.e('85c0'); a.jl('0f84', 'next')
        a.e('39700c'); a.jl('0f85', 'next')                  # pass 2: the home pais' capital
        a.e('8b0f')
        a.mark('own'); a.call(OWNER_OF); a.e('3b45ac'); a.jl('0f85', 'next')
        a.e('8b0f 8b01 ff75ac ff5048 85c0'); a.js('7f', 'found')   # free army slots for the human
        a.mark('next'); a.e('83c704'); a.jl('e9', 'pl')
        a.mark('pend'); a.e('4b'); a.jl('0f89', 'pass'); a.jl('e9', 'release')
        a.mark('found'); a.e('8b0f ff717c 8d45b0 50 8d45d8 50 ff75ac 8b4da4 8b89a8000000'); a.call(MAKE_ARMY)
        a.e('8945a0')
        a.mark('release'); a.e('33db')
        a.mark('rl'); a.e('8b449dd8 85c0'); a.js('74', 'rn'); a.e('50'); a.call(REL_STR); a.e('83c404')
        a.mark('rn'); a.e('43 83fb0a'); a.js('72', 'rl')
        a.e('8b45a0 5f 5e 5b 8be5 5d c3')
    a = CaveAsm(c23)
    spawn_code(a, True)
    sp_code = a.done(); assert len(sp_code) <= 0x200
    put(c23 - EXE_BASE, sp_code)
    put(sp_ptrs - EXE_BASE, b''.join(struct.pack('<I', sp_strs + sum(len(x) + 1 for x in SP_NAMES[:k]))
                                     for k in range(len(SP_NAMES))))
    put(sp_strs - EXE_BASE, sp_bytes)
    put(sp_slots - EXE_BASE, b''.join(bytes(s) + b'\xff' for s in SP_SLOTS) + b'\xfe')
    assert sp_slots + 21 <= c23 + 0x300
    key23_ok, key23_fail = r2_str('LTEXT_UI_CHEAT_SPAWN_DONE'), r2_str('LTEXT_UI_CHEAT_SPAWN_FAIL')

    def build23(a):
        a.call(c23); a.e('85c0 b8'); a.imm(key23_ok); a.js('75', 'r'); a.e('b8'); a.imm(key23_fail); a.mark('r'); a.e('c3')
    r2_slot('L', r2_handler(build23))

    # 24) FREE BUILDINGS / TROOPS / SHIPS (panel 'CH_M', toggle CHEAT_COST): the payment FUN_006352d0(this = player;
    #     cost by value, reason) ret 0x20 is skipped for the local human for reasons 1 (construction), 2 (troops) and
    #     3 (ships); upkeep (0), healing (4/5), treaties (6) and quests (7) are paid as usual. The affordability test
    #     FUN_006a42b0(this = production manager; player id, &cost) ret 8, used only by the troop / ship / construction
    #     managers and the production panel, answers 'affordable' for the human while the toggle is on.
    c24 = 0x883e00
    cave_free(c24, 0x80)
    IS_HUMAN_P = 0x6345b0                                # thiscall(player) -> al
    a = CaveAsm(c24)
    a.e('803d'); a.imm(CHEAT_COST); a.e('00'); a.js('74', 'orig')
    a.e('8b442420 48 83f802'); a.js('77', 'orig')        # reason 1..3 only
    a.e('51'); a.call(IS_HUMAN_P); a.e('59 84c0'); a.js('74', 'orig')
    a.e('c22000')                                        # skip the payment
    a.mark('orig'); a.e('83ec38 53 55'); a.jmp(0x6352d5)
    pay24 = a.done()
    a = CaveAsm(c24 + 0x40)
    a.e('803d'); a.imm(CHEAT_COST); a.e('00'); a.js('74', 'orig')
    a.e('51 8b899c000000 ff742408'); a.call(FIND_PLAYER2)    # player of [esp+4] (players = [this+0x9c])
    a.e('85c0'); a.js('74', 'restore')
    a.e('8bc8'); a.call(IS_HUMAN_P); a.e('84c0'); a.js('74', 'restore')
    a.e('59 b801000000 c20800')                          # affordable
    a.mark('restore'); a.e('59')
    a.mark('orig'); a.e('53 55 8b6c240c'); a.jmp(0x6a42b6)
    aff24 = a.done()
    assert len(pay24) <= 0x40 and len(aff24) <= 0x40
    put(c24 - EXE_BASE, pay24); put(c24 + 0x40 - EXE_BASE, aff24)
    put(0x6352d0 - EXE_BASE, jmp(0x6352d0, c24), h('83ec385355'))
    put(0x6a42b0 - EXE_BASE, jmp(0x6a42b0, c24 + 0x40) + h('90'), h('53558b6c240c'))
    r2_toggle('M', CHEAT_COST, 'FREE')

    # 25) PEACE WITH ALL (panel 'CH_N', one-shot) and 26) EVERYONE FRIENDLY ('CH_O', one-shot): for every other player
    #     the diplomacy object [ui+0xf0] (registry 0x5de540) signs peace with the human, FUN_00692cc0(human, other)
    #     ret 8 (does nothing unless the two are at war; else peace both ways, map refresh and news, as the game's own
    #     'universal peace' quest effect does), and the hostility object [ui+0xf8] (registry 0x5de500) sets the pair's
    #     hostility to 0, FUN_0068ee20(human, other, 0.0, 0, 0, 0) ret 0x18 (skips eliminated players), followed by one
    #     FUN_0068e0c0(human) ret 4. The AI may still declare war later; alliances can still pull it into wars.
    def players_loop(a, field, body, tail):
        a.e('53 56 57 55 8bd9 8b83c0000000 8b7024 8b7828 8bab60010000')   # ebx = UI; esi..edi players; ebp = human
        a.e('83bb%02x00000000' % field); a.js('74', 'done')                # no diplomacy object: nothing to do
        a.mark('loop'); a.e('3bf7'); a.js('73', 'fin')
        a.e('8b06 8b80f4000000 3bc5'); a.js('74', 'next')                  # skip the human
        body(a)
        a.mark('next'); a.e('83c604'); a.js('eb', 'loop')
        a.mark('fin'); tail(a)
        a.mark('done')
    key25 = r2_str('LTEXT_UI_CHEAT_PEACE_DONE')

    def build25(a):
        players_loop(a, 0xf0, lambda a: (a.e('50 55 8b8bf0000000'), a.call(0x692cc0)), lambda a: None)
        a.e('b8'); a.imm(key25); a.e('5d 5f 5e 5b c3')
    r2_slot('N', r2_handler(build25))
    key26 = r2_str('LTEXT_UI_CHEAT_FRIENDLY_DONE')

    def build26(a):
        players_loop(a, 0xf8, lambda a: (a.e('6a00 6a00 6a00 6a00 50 55 8b8bf8000000'), a.call(0x68ee20)),
                     lambda a: (a.e('55 8b8bf8000000'), a.call(0x68e0c0)))
        a.e('b8'); a.imm(key26); a.e('5d 5f 5e 5b c3')
    r2_slot('O', r2_handler(build26))
    # (complete era / next era: left out on purpose. It needs ~280 bytes of untested code that grants technologies
    #  one by one and triggers the era change and the government choice from inside the ESC menu; granting the techs of
    #  later eras would hand out the mutually exclusive government branches. The Fast Research toggle finishes the
    #  technologies being researched at the next turn start, which is the safe way to the next era.)

    # 27) longer production queues for the HUMAN player (the AI keeps the original caps). The queues are linked lists
    #     (queue +8 count, +0x14 head, +0x18 tail, items linked through +0x1c; FUN_0069b460 inserts), so the cap is only
    #     a compare, made in exactly three places when an item is ordered (esi = manager, edi = player id there):
    #       buildings  FUN_0069a810 at 0x69a8df: cmp eax,[esi+0x54] (6: the player's items in that province); je full
    #       troops     FUN_00698980 at 0x698a53: cmp ecx,[esi+0x5c] (7: items in the barracks queue);      je full
    #       ships      FUN_00699920 at 0x6999e9: cmp ecx,[esi+0x64] (7: items in the shipyard queue);     jae full
    #     Each compare now goes through a cave: for the human (players object [esi+0x34] / [esi+0x44],
    #     FUN_0065b4a0(players; pid) ret 4) the count is compared with HUMAN_QUEUE_CAP instead. The production dialogs
    #     show the extra items with the original scroll bar of their queue viewers (make_map.production_queue_ui).
    c27 = 0x883d40                                       # after patch 21's core (0x883c00..), before patch 24 (0x883e00)
    assert c21 + len(core21) <= c27
    cave_free(c27, 0x90)
    IS_HUMAN_ID = 0x65b4a0

    def cap_cave(org, reg, players_off, cap_off, jcc, full, back):
        r = {'eax': 0, 'ecx': 1}[reg]
        a = CaveAsm(org)
        a.e('50 51 52 8b4e%02x 57' % players_off); a.call(IS_HUMAN_ID)  # al = is the ordering player the human?
        a.e('84c0 5a 59 58'); a.js('74', 'ai')                            # (the pops keep the flags of the test)
        a.e('83%02x%02x' % (0xf8 + r, HUMAN_QUEUE_CAP)); a.js('eb', 'test')  # cmp reg, HUMAN_QUEUE_CAP
        a.mark('ai'); a.e('3b%02x%02x' % (0x46 + 8 * r, cap_off))          # cmp reg, [esi+cap] (the original)
        a.mark('test'); a.e(jcc); a.imm(full - (a.here() + 4)); a.jmp(back)
        return a.done()
    caps27 = ((0x69a8df, 'eax', 0x34, 0x54, '0f84', 0x69a941, 0x69a8e4, '3b4654745d'),
              (0x698a53, 'ecx', 0x44, 0x5c, '0f84', 0x698add, 0x698a5c, '3b4e5c0f8481000000'),
              (0x6999e9, 'ecx', 0x44, 0x64, '0f83', 0x699a73, 0x6999f2, '3b4e640f8381000000'))
    for k, (site, reg, pl, cap, jcc, full, back, orig) in enumerate(caps27):
        org = c27 + 0x30 * k
        code = cap_cave(org, reg, pl, cap, jcc, full, back)
        assert len(code) <= 0x30
        put(org - EXE_BASE, code)
        put(site - EXE_BASE, jmp(site, org) + h('90') * (len(orig) // 2 - 5), h(orig))

    # 28) ESC works even when the game wrongly thinks Alt / Ctrl / Shift is held. The input layer keeps a modifier
    #     mask (0x9149f0, set/cleared per key by FUN_00415e60 / FUN_00415ec0, reset only when the window loses focus)
    #     and passes it with every key-down; a key control (UIC_TECLA, listener FUN_00564a10) fires only when the mask
    #     equals its .MKEYS exactly. When an Alt key-up never reaches the game (seen live: two Left-Alt slots at once)
    #     the mask stays 1 and ESC (.MKEYS [ ]) is silently ignored until Alt is pressed again or the window loses focus.
    #     The key-down compare at 0x564a6b now also accepts the key VK_ESCAPE when the control asks for no modifier,
    #     and passes it on with mask 0. Every Escape control in data/ and data1/ has .MKEYS [ ] (none binds Alt/Ctrl/
    #     Shift+Esc), and every other key keeps the exact match (the Ctrl+Alt+letter cheats, Shift+Tab). Key-up has no
    #     modifier compare, so the click on release works as before.
    c28 = 0x880f00                                       # int3 run 0x880eab-0x880fff, unused by patches 1-27
    cave_free(c28, 0x40)
    a = CaveAsm(c28)
    a.e('395150'); a.js('74', 'ok')                      # cmp [ecx+0x50],edx (the original exact match); je ok
    a.e('83fe1b'); a.js('75', 'no')                      # esi = the key (already == [ecx+0x4c]); not VK_ESCAPE -> no
    a.e('83795000'); a.js('75', 'no')                    # the control asks for a modifier itself -> no
    a.e('33d2')                                          # xor edx,edx: deliver it as a plain Escape
    a.mark('ok'); a.jmp(0x564a70)                        # match: set the key flag, send event 0x11
    a.mark('no'); a.jmp(0x564a9c)                        # no match (eax is still 0: returns false)
    code28 = a.done()
    assert len(code28) <= 0x40
    put(c28 - EXE_BASE, code28)
    put(0x564a6b - EXE_BASE, jmp(0x564a6b, c28), h('395150752c'))   # cmp [ecx+0x50],edx; jne 0x564a9c

    # 29) BATTLE STRENGTH (BATTLE_STRENGTH / BATTLE_STRENGTH_TYPE): the troops of a nation fight harder in real-time battles
    #     and in auto-resolve, whoever owns them. Battle stats are per troop type and rank (ModeloCombate.dt, shared by all
    #     nations; re_tools/engine_guide.md 3.9), so the factor is applied where damage is computed, never stored.
    #     Factor of a battalion = u8 table T29[troop type id = battalion+8] (factor x 16, 0 = none), built from the final
    #     .mng (troop record owner country + troop type name). A battle unit (Tropa, vtables 0x8b7534 / 0x8d5ac8 /
    #     0x8d5af4 / 0x8d5b20) finds its battalion like its own init does: FUN_00595890([unit+0x3cc]; [unit+0x20]).
    #     fa = attacker's factor, fd = defender's factor; 100 damage points = one man.
    #       a) FUN_00592a70 (fire, charge and single melee, and the battle AI's estimates): final damage x fa / fd, its cap
    #          'men x 100' x fa / 16 (cave at 0x592c14).
    #       b) FUN_004898b0 (melee against several units): base damage and the men cap x fa / 16 (0x489ada); each target's
    #          share x 16 / fd (0x489be4).
    #       c) artillery: kill counts at impact / explosion (FUN_004eef60 / FUN_004ef3b0, target max health x damage ratio):
    #          ratio x fa / fd (0x4ef1c9 / 0x4ef517). A round shot in flight (FUN_004eead0) kills every man within a radius
    #          of its path: per target unit q = 16 fa / fd ([Q29], set at 0x4eeb1b) scales the circle test r^2 (0x4eec32)
    #          and the path test r (0x4eedc0) by q / 16, so the expected kills scale by fa / fd.
    #     Land battles have no morale stat (no rout code; MORAL_FICTICIA is only a UI picture): fewer losses is the effect.
    #     Auto-resolve: FUN_006b72f0 builds one battalion's stats (FUN_006b68a0, 15 floats); its ranged / charge / melee
    #     damage and resistance (out[7], [8], [11]..[14]) and its power out[0] x factor (0x6b7360). Sides are sums of these,
    #     so the simulation FUN_006b6060, the difficulty / GODMODE table of patch 19 (applied later to the side sums), the
    #     AI's battle predictions and the army strength displays all see the same factor.
    if mng_path is None:
        mng_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'mod', 'Game', 'GameModes',
                                'DefModeloGestion.mng')
    m29 = Mng(open(mng_path, 'rb').read())
    cn29, tn29 = Mng.parse_enum(m29.table(1)), Mng.parse_enum(m29.table(5))
    T29_N = 0x400
    tbl29, used29, nat29 = bytearray(T29_N), set(), set()
    for r in split_records(m29.section(7), 'troop'):
        tid = struct.unpack_from('<I', r, 0)[0]
        key = (cn29.get(struct.unpack_from('<I', r, _owner_field(r, 23, 13))[0]), tn29.get(tid))
        f = BATTLE_STRENGTH_TYPE.get(key, BATTLE_STRENGTH.get(key[0], 1.0))
        if key in BATTLE_STRENGTH_TYPE:
            used29.add(key)
        if key[0] in BATTLE_STRENGTH:
            nat29.add(key[0])
        if f != 1.0:
            assert tid < T29_N and 1 <= round(f * 16) <= 255, (tid, key, f)
            tbl29[tid] = int(round(f * 16))
    assert used29 == set(BATTLE_STRENGTH_TYPE) and nat29 == set(BATTLE_STRENGTH), (used29, nat29)
    C29, T29, Q29 = 0x882100, 0x882400, 0x942f24          # int3 run 0x882095-0x882fff (patch 7 starts at 0x882800)
    cave_free(C29, T29 + T29_N - C29)
    a = CaveAsm(C29)
    a.mark('inv16'); a.imm(0x3d800000); a.mark('f16'); a.imm(0x41800000); a.e('cc' * 8)   # 0.0625f, 16.0f
    # fac_t: ecx = battle unit (or 0) -> eax = factor x 16; fac_b: ecx = battalion (or 0). Keeps ebx/esi/edi/ebp.
    a.mark('fac_t'); a.e('b810000000 85c9'); a.js('74', 'ret'); a.e('8b11')
    for vt in (0x8b7534, 0x8d5ac8, 0x8d5af4):
        a.e('81fa'); a.imm(vt); a.js('74', 'unit')
    a.e('81fa'); a.imm(0x8d5b20); a.js('75', 'ret')
    a.mark('unit'); a.e('8b91cc030000 85d2'); a.js('74', 'ret')                  # edx = campaign model
    a.e('ff7120 8bca'); a.call(0x595890); a.e('8bc8')                          # battalion = FUN_00595890(model; id)
    a.mark('fac_b'); a.e('b810000000 85c9'); a.js('74', 'ret')
    a.e('8b4908 81f9'); a.imm(T29_N); a.js('73', 'ret')                       # troop type id
    a.e('0fb689'); a.imm(T29); a.e('85c9'); a.js('74', 'ret'); a.e('8bc1')
    a.mark('ret'); a.e('c3')
    fac_t, fac_b = a.lab['fac_t'], a.lab['fac_b']
    # a) FUN_00592a70 @0x592c14: ecx = damage; [esp+0x58] attacker, [esp+0x5c] defender, [esp+0x64] men (ebx/esi/edi
    #    are popped right after, eax/esi/edx reloaded at 0x592c30)
    a.mark('r1'); a.e('8bd9 8b4c2458'); a.call(fac_t); a.e('8bf0 8b4c245c'); a.call(fac_t); a.e('8bf8')
    a.e('8bc3 3bf7'); a.js('74', 'r1c'); a.e('f7ee f7ff')                     # eax = damage x fa / fd
    a.mark('r1c'); a.e('8bc8 85c9'); a.js('7f', 'r1p'); a.e('33c9'); a.jmp(0x592c30)
    a.mark('r1p'); a.e('8b442464 6bc064 0fafc6 c1f804 3bc8'); a.js('7e', 'r1d'); a.e('8bc8')   # cap men x 100 x fa / 16
    a.mark('r1d'); a.jmp(0x592c30)
    # b) FUN_004898b0 @0x489ada: edi = attacker, ebx = 0, [esp+0x34] base damage, [esp+0x44] / esi = men (the cap)
    a.mark('r2a'); a.e('33f6 8b87ac000000 85c0'); a.js('74', 'r2n'); a.e('8bb7b0000000 2bf0 c1fe02')
    a.mark('r2n'); a.e('8bcf'); a.call(fac_t); a.e('83f810'); a.js('74', 'r2s')
    a.e('8bc8 8b442434 0fafc1 c1f804 89442434 0faff1 c1fe04')
    a.mark('r2s'); a.e('89742444'); a.jmp(0x489afd)
    #    @0x489be4: ebx = damage after the attack bonus, ecx = the target's defence share, [[esp+0x54]] = target
    a.mark('r2b'); a.e('8bc3 2bc1 50 8b4c2458 8b09'); a.call(fac_t); a.e('8bc8 58 83f910'); a.js('74', 'r2c')
    a.e('c1e004 99 f7f9')                                                     # eax = damage x 16 / fd
    a.mark('r2c'); a.e('85c0'); a.js('7f', 'r2p'); a.e('33c0'); a.jmp(0x489c00)
    a.mark('r2p'); a.e('8d1476 8d0cd6 03c9 03c9 3bc1'); a.js('7e', 'r2d'); a.e('8bc1')
    a.mark('r2d'); a.jmp(0x489c00)

    # c) kill counts: esi = projectile ([+0xb4] = the firing unit), target unit in ebp / edi, float damage ratio on the stack
    def kill_ratio(name, reg, ratio, fild, back):
        a.mark(name); a.e('85' + {'ebp': 'ed', 'edi': 'ff'}[reg]); a.js('74', name + 'o')
        a.e('8b8eb4000000'); a.call(fac_t); a.e('50 8b' + {'ebp': 'cd', 'edi': 'cf'}[reg]); a.call(fac_t); a.e('50')
        a.e('8b0424 3b442404'); a.js('74', name + 's')
        a.e('db442404 da3424 d84c24%02x d95c24%02x' % (ratio + 8, ratio + 8))  # ratio x fa / fd
        a.mark(name + 's'); a.e('83c408')
        a.mark(name + 'o'); a.e(fild); a.jmp(back)                            # displaced fild [unit+0x234]
    kill_ratio('r3', 'ebp', 0x70, 'db8534020000', 0x4ef1cf)
    kill_ratio('r4', 'edi', 0x14, 'db8734020000', 0x4ef51d)
    a.mark('s0'); a.e('8b8eb4000000'); a.call(fac_t); a.e('50 8bcd'); a.call(fac_t)   # FUN_004eead0: ebp = unit
    a.e('8bc8 58 c1e004 99 f7f9 85c0'); a.js('75', 's0n'); a.e('40')          # q = 16 fa / fd, at least 1
    a.mark('s0n'); a.e('a3'); a.imm(Q29); a.e('8bcd'); a.call(0x490680); a.jmp(0x4eeb22)
    a.mark('s1'); a.e('d98424c0000000 d88c24c0000000 833d'); a.imm(Q29); a.e('10'); a.js('74', 's1d')
    a.e('db05'); a.imm(Q29); a.e('d80d'); a.imm(a.lab['inv16']); a.e('dec9')  # r^2 x q / 16
    a.mark('s1d'); a.jmp(0x4eec40)
    a.mark('s2'); a.e('d9fa 833d'); a.imm(Q29); a.e('10'); a.js('74', 's2d')
    a.e('db05'); a.imm(Q29); a.e('d83d'); a.imm(a.lab['f16']); a.e('dec9')    # distance x 16 / q (= r x q / 16)
    a.mark('s2d'); a.e('d89c24c0000000'); a.jmp(0x4eedc9)
    # auto-resolve FUN_006b72f0 @0x6b7360: esi = battalion, [esp+0xbc] = its 15 stats
    a.mark('ar'); a.e('8bce'); a.call(fac_b); a.e('83f810'); a.js('74', 'aro')
    a.e('50 db0424 58 d80d'); a.imm(a.lab['inv16']); a.e('8b8424bc000000')    # st0 = factor; eax = stats
    for off in (0x00, 0x1c, 0x20, 0x2c, 0x30, 0x34, 0x38):
        a.e('d9c0 d848%02x d958%02x' % (off, off))
    a.e('ddd8')
    a.mark('aro'); a.e('5f 5e 81c4b0000000 c20800')                          # the displaced epilogue
    code29 = a.done()
    assert C29 + len(code29) <= T29
    put(C29 - EXE_BASE, code29)
    put(T29 - EXE_BASE, bytes(tbl29))
    for site, lab, orig in ((0x592c14, 'r1', '85c97f0433c9eb148b4424648d14408d04d003c003c03bc87e028bc8'),
                            (0x489ada, 'r2a', '8b87ac0000003bc3750833f689742444eb118b8fb00000002bc8c1f902894c24448bf1'),
                            (0x489be4, 'r2b', '8bc32bc185c07f0433c0eb108d14768d0cd603c903c93bc17e028bc1'),
                            (0x4ef1c9, 'r3', 'db8534020000'), (0x4ef517, 'r4', 'db8734020000'),
                            (0x4eeb1b, 's0', '8bcde85e1bfaff'), (0x4eec32, 's1', 'd98424c0000000d88c24c0000000'),
                            (0x4eedc0, 's2', 'd9fad89c24c0000000'), (0x6b7360, 'ar', '5f5e81c4b0000000')):
        put(site - EXE_BASE, jmp(site, a.lab[lab]) + h('90') * (len(orig) // 2 - 5), h(orig))

    # 30) Global Statistics (News Bulletin -> Economy) crashed when the HUMAN plays a nation other than the 5 empires
    #     (the AllNationsPlayable v1.2.2 site). On show, FUN_007a8f70 maps the viewing player ([this+0xd4] = the human,
    #     FUN_0065ae50 at window init) to its legend tab id with FUN_007a85c0 ('CBAU' 'CBPR' 'CBFR' 'CBRU' 'CBIN', 0 for
    #     everyone else; ret 4) and selects that tab in the tab control 'GCE1' (FUN_0076e9d0(id, 0), ret 8). No tab has
    #     id 0, so the search leaves esi = 0 -> crash at 0x76e9ff (mov eax,[esi]). The push of 'GCE1' at 0x7a8f9f (right
    #     after the mapping call, eax = tab id) now goes through a cave: id 0 skips the selection and leaves through the
    #     original epilogue 0x7a8fb7 (pop edi/esi/ebx; ret 4 - the stack is balanced there), and the tab control keeps
    #     its current tab (the first tab from load, FUN_0076e0b0, or on show, FUN_0076ecb0). The 5 empires (id != 0) run
    #     the original code. UI only: no AI, rule or save effect. No branch lands in 0x7a8fa0..0x7a8fa3.
    #     The other four AllNations sites need no patch in this exe (static RE 2026-10-21):
    #       - province dialog loops (right-click panel FUN_007f14e0 at 0x7f1532 / 0x7f1577, bars FUN_007f0f60 at
    #         0x7f0fba / 0x7f109a): their widget ids come from FUN_007f02b0 / FUN_007f0130, which patch 11 maps to the
    #         dummy widgets 'BTXX' / 'BPXX' for every non-empire, so FUN_005584e0 never returns 0 there;
    #       - turn-order map lookups at 0x6c0424 / 0x6c0755 (FUN_006c03e0 / FUN_006c0730, std::map [this+0x2c] filled
    #         from DefOrdenTurnos.sb by FUN_006c0ad0): patch 4 loads a block for every PLAYABLE nation and
    #         validate_build asserts each exists, so find(human) never returns end();
    #       - the 'imperial player' flag [player+0xF9] (FUN_00634e40 sets it from FUN_005d35d0 = 'name is in the Select
    #         Empire list'): patch 2 makes that list PLAYABLE, so every human-playable nation already has it; AllNations'
    #         call swap at 0x6c03fb (flag for the human only) would change nothing here.
    c30 = 0x881860                                       # reserved range 0x881860-0x881aff (coordinator, 2026-10-21)
    cave_free(c30, 0x20)
    a = CaveAsm(c30)
    a.e('85c0'); a.js('74', 'none')                      # test eax,eax (legend tab id of the viewing player); jz none
    a.e('68'); a.imm(0x47434531)                         # push 'GCE1' (the displaced instruction)
    a.jmp(0x7a8fa4)                                      # back: mov ecx,esi; mov edi,eax; FUN_005584e0; select the tab
    a.mark('none'); a.jmp(0x7a8fb7)                      # no tab for this nation: skip the selection
    code30 = a.done()
    assert len(code30) <= 0x20
    put(c30 - EXE_BASE, code30)
    put(0x7a8f9f - EXE_BASE, jmp(0x7a8f9f, c30), h('6831454347'))   # push 0x47434531

    # 31) fullscreen resolution whitelist (.rdata 0x8c878c, 6 x (u32 width, u32 height)). The D3D9 mode enumeration
    #     FUN_005eee00 keeps an adapter mode only if its size equals one of the 6 pairs (loop 'cmp eax,0x30' at 0x5eef65;
    #     the only reads are 0x5eef52 / 0x5eef5a); FUN_005ee740 / FUN_005ee850 dedupe the kept sizes into the list the
    #     Options 'SRES' slider shows (FUN_0041b4e0, label '%uX%u' by FUN_00419d10), and FUN_005edb00 accepts a
    #     fullscreen Config.sb SX/SY only if it is in that list (windowed mode is not filtered). The installed exe holds a
    #     broken hex edit (640x480, 3840x2160 x3, 3840x552960, 1600x1200: no 1920x1080). Replaced with FULLSCREEN_MODES;
    #     order does not matter (the mode lists are sorted). Pure data, no code change.
    assert len(FULLSCREEN_MODES) == 6 and all(320 <= w <= 8192 and 200 <= hh <= 8192 for w, hh in FULLSCREEN_MODES)
    put(0x8c878c - EXE_BASE, b''.join(struct.pack('<II', w, hh) for w, hh in FULLSCREEN_MODES),
        h('80020000e0010000' '000f000070080000' '000f000000700800' '000f000070080000' '000f000070080000' '40060000b0040000'))

    # ---- cheats round 3 (patches 32-39, panel page 'EM_6', buttons 'CH_P'..'CH_W'; make_map CHEAT_PAGES / CHEAT_TEXTS_4).
    #      All act for the local human only, except the cosmetic cow cavalry. Code in the int3 runs 0x895ba0-0x895fff (A)
    #      and 0x881c80-0x881f7f (B, overflow); LTEXT keys and ON/OFF pairs after round 2's in 0x88ad00-0x88afff, then in
    #      0x881f80-0x881fff (S) (all checked free with cave_free).
    #      Handler convention as in patch 18: thiscall(ecx = map UI) -> eax = LTEXT key (or 0); ebx/esi/edi/ebp kept.
    R3 = {'A': [0x895ba0, 0x896000], 'B': [0x881c80, 0x881f80], 'S': [0x881f80, 0x882000]}

    def r3_code(build):                                 # assemble build(a) into the first round-3 code run it fits
        for k in ('A', 'B'):
            org, end = R3[k]
            a = CaveAsm(org); build(a); code = a.done()
            if org + len(code) <= end:
                cave_free(org, len(code)); put(org - EXE_BASE, code)
                R3[k][0] = (org + len(code) + 15) & ~15
                return org, a.lab
        raise AssertionError('round-3 code caves are full')

    def r3_str(s):                                      # round 2's string run first (r2_str), then S
        bs = s.encode() + b'\0'
        if r2['str'] + len(bs) <= 0x88b000:
            return r2_str(s)
        va = R3['S'][0]
        assert va + len(bs) <= R3['S'][1], 'round-3 string space is full'
        cave_free(va, len(bs)); put(va - EXE_BASE, bs); R3['S'][0] += len(bs)
        return va

    def r3_pair(key):
        on_va, off_va = r3_str('LTEXT_UI_CHEAT_%s_ON' % key), r3_str('LTEXT_UI_CHEAT_%s_OFF' % key)
        pair = struct.pack('<II', on_va, off_va)
        va = (r2['str'] + 3) & ~3
        if va + 8 <= 0x88b000:
            r2['str'] = va + 8
        else:
            va = (R3['S'][0] + 3) & ~3
            assert va + 8 <= R3['S'][1], 'round-3 string space is full'
            R3['S'][0] = va + 8
        cave_free(va, 8); put(va - EXE_BASE, pair)
        return va

    def r3_toggle(letter, byte_va, key, pre=None):      # ON/OFF toggle of a byte; pre(a) runs first (ecx = map UI, keep it)
        pair = r3_pair(key)

        def build(a):
            if pre is not None:
                pre(a)
            a.e('ba'); a.imm(byte_va); a.e('b8'); a.imm(pair); a.jmp(toggle_byte18)
        r2_slot(letter, r3_code(build)[0])

    def r3_oneshot(letter, target, ok_key, fail_key):  # target(ecx = map UI) -> eax != 0: ok_key, else fail_key
        ok, fail = r3_str(ok_key), r3_str(fail_key)

        def build(a):
            a.call(target); a.e('85c0 b8'); a.imm(ok); a.js('75', 'r'); a.e('b8'); a.imm(fail); a.mark('r'); a.e('c3')
        r2_slot(letter, r3_code(build)[0])
    SET_CTOR, SET_DTOR, BATT_IDS, BATT_OF, ARMY_OF, LOC_OF = 0x6243d0, 0x4f7c90, 0x6889c0, 0x595890, 0x684f50, 0x5a7180
    HEAL_BATT, XP_GAIN, HUMAN_OF, IS_HUMAN_OBJ = 0x686240, 0x6863a0, 0x65ae50, 0x6345b0

    # 32) SUPER TROOPS (panel 'CH_P', toggle CHEAT_BATTLE): the human's battalions deal 3x damage and take 1/3, in
    #     real-time battles and in auto-resolve. Patch 29's factor of a battalion (fac_b; fac_t falls into it after
    #     finding a battle unit's campaign battalion) is multiplied by 3 (max 255 = x15.9) when the toggle is on and the
    #     battalion's owner ([b+0x14], FUN_00596aa0 reads it the same way; checked live: 194 battalions of the human
    #     carry its id there) equals CHEAT_HUMAN. Every damage formula of patch 29 uses fa / fd, so the human's side
    #     hits 3x harder and takes 1/3; auto-resolve scales the human battalions' power, damage and resistance by 3.
    #     CHEAT_HUMAN = [ui+0x160], refreshed by the patch 18 capture on every campaign-map event and by this toggle,
    #     so a game loaded with another nation never boosts the previous nation. Custom battles have no campaign
    #     battalion (fac_t returns 16 first): unaffected. The hook takes fac_b's first instruction ('mov eax,16').
    def build32(a):
        a.e('51 b810000000'); a.call(fac_b + 5); a.e('59')                  # eax = the patch 29 factor
        a.e('803d'); a.imm(CHEAT_BATTLE); a.e('00'); a.js('74', 'out')
        a.e('85c9'); a.js('74', 'out')
        a.e('8b5114 3b15'); a.imm(CHEAT_HUMAN); a.js('75', 'out')          # owner == the human?
        a.e('8d0440 3dff000000'); a.js('76', 'out'); a.e('b8ff000000')      # x3, at most 255
        a.mark('out'); a.e('c3')
    c32 = r3_code(build32)[0]
    put(fac_b - EXE_BASE, jmp(fac_b, c32), h('b810000000'))
    r3_toggle('P', CHEAT_BATTLE, 'SUPER', pre=lambda a: (a.e('8b8160010000 a3'), a.imm(CHEAT_HUMAN)))

    # 33) HEAL ALL ARMIES (panel 'CH_Q', one-shot): every battalion of the human (armies incl. their commanders, and
    #     garrisons) back to full strength for free: the ids come from FUN_006889c0(this = army manager [ui+0xa8]; pid,
    #     &set) ret 8 (set ctor FUN_006243d0(1) ret 4, dtor FUN_004f7c90; list head +0x24, node {id, next}), and each
    #     goes through the game's own heal FUN_00686240(this = army manager; id, free = 1) ret 8 (no check, no payment;
    #     full stats from FUN_006a6410), as the quest reward FUN_00650e40 does, followed by the army refresh vf+0x6c.
    #     FUN_00686240 dereferences the battalion, its army (army id [b+0x34]) or its garrison location (FUN_005a7180)
    #     without checks, so each is looked up first (FUN_00595890 / FUN_00684f50 / FUN_005a7180) and skipped if absent.
    key33 = r3_str('LTEXT_UI_CHEAT_HEAL_DONE')

    def batt_loop(a, body):                             # for each battalion id of the human: body(a), ebx = node, esi = manager
        a.e('53 56 57 55 83ec34')
        a.e('8bb960010000 8bb1a8000000 85f6'); a.jl('0f84', 'out')          # edi = human, esi = army manager
        a.e('8d0c24 6a01'); a.call(SET_CTOR)
        a.e('54 57 8bce'); a.call(BATT_IDS)                                 # FUN_006889c0(human, &set)
        a.e('8b5c2424')                                                     # ebx = first node
        a.mark('loop'); a.e('85db'); a.jl('0f84', 'done')
        a.e('ff33 8b4e0c'); a.call(BATT_OF); a.e('85c0'); a.jl('0f84', 'next')   # eax = battalion object
        body(a)
        a.mark('next'); a.e('8b5b04'); a.jl('e9', 'loop')
        a.mark('done'); a.e('8d0c24'); a.call(SET_DTOR)

    def heal_body(a):
        a.e('8b4034 85c0'); a.js('74', 'garr')
        a.e('50 8bce'); a.call(ARMY_OF); a.e('85c0'); a.jl('0f84', 'next'); a.e('8bf8')   # edi = its army
        a.e('6a01 ff33 8bce'); a.call(HEAL_BATT)
        a.e('8bcf 8b01 ff506c'); a.jl('e9', 'next')                       # army->vf 0x6c (refresh)
        a.mark('garr'); a.e('ff33 8b4e0c'); a.call(LOC_OF); a.e('85c0'); a.jl('0f84', 'next')
        a.e('6a01 ff33 8bce'); a.call(HEAL_BATT)

    def build33(a):
        batt_loop(a, heal_body)
        a.mark('out'); a.e('83c434 5d 5f 5e 5b b8'); a.imm(key33); a.e('c3')
    r2_slot('Q', r3_code(build33)[0])

    # 34) ELITE VETERANS (panel 'CH_R', one-shot): the same battalions get the top experience rank (4). The game's own
    #     experience award FUN_006863a0(this = army manager; kind 0 = battalion, id, level 2 = the biggest win) ret 0xc
    #     adds the rules' xp (3, thresholds 0/6/12/18/25 read live), moves at most one rank per call and refreshes the
    #     stats for the new rank (FUN_006a6410 + FUN_00592de0, men and health kept); it is called until [b+0x28] = 4,
    #     at most 16 times per battalion, then the army is refreshed (vf+0x6c).
    key34 = r3_str('LTEXT_UI_CHEAT_VETS_DONE')

    def vets_body(a):
        a.e('8bf8 bd10000000')                                              # edi = battalion, ebp = 16 tries
        a.mark('xp'); a.e('837f2804'); a.js('7d', 'ref')                    # rank 4: done
        a.e('6a02 ff33 6a00 8bce'); a.call(XP_GAIN); a.e('4d'); a.js('75', 'xp')
        a.mark('ref'); a.e('8b4734 85c0'); a.jl('0f84', 'next')
        a.e('50 8bce'); a.call(ARMY_OF); a.e('85c0'); a.jl('0f84', 'next')
        a.e('8bc8 8b10 ff526c')

    def build34(a):
        batt_loop(a, vets_body)
        a.mark('out'); a.e('83c434 5d 5f 5e 5b b8'); a.imm(key34); a.e('c3')
    r2_slot('R', r3_code(build34)[0])

    # 35) FULL INTELLIGENCE (panel 'CH_S', toggle CHEAT_INTEL): the intelligence level of an observer, FUN_006a05d0
    #     (land; this = manager, [this+0x9c] = players; observer pid, category) and FUN_006a0410 (sea; pid, zone), both
    #     ret 8, is 2 (full: spy network + foreign ministry / Fresnel lighthouse) for the human while the toggle is on.
    #     Their entries go through a cave that compares the observer with FUN_0065ae50(players) (the live human) and
    #     otherwise replays the displaced prologue. The vanilla bit 0x200 (debug map layers) is not touched.
    def intel_hook(site, disp, back):
        def build(a):
            a.e('803d'); a.imm(CHEAT_INTEL); a.e('00'); a.js('74', 'orig')
            a.e('51 8b899c000000'); a.call(HUMAN_OF); a.e('59')
            a.e('3b442404'); a.js('75', 'orig')
            a.e('b802000000 c20800')
            a.mark('orig'); a.e(disp); a.jmp(back)
        va = r3_code(build)[0]
        n = len(h(disp.replace(' ', '')))
        put(site - EXE_BASE, jmp(site, va) + h('90') * (n - 5), h(disp.replace(' ', '')))
    intel_hook(0x6a05d0, '83ec18 53 8b5c2420', 0x6a05d8)
    intel_hook(0x6a0410, '83ec08 53 55', 0x6a0415)
    r3_toggle('S', CHEAT_INTEL, 'INTEL')

    # 36) NO ARMY UPKEEP (panel 'CH_T', toggle CHEAT_UPKEEP): FUN_006389a0 (this = player, the turn's income) adds the
    #     upkeep of armies and fleets (FUN_0068a7d0) unless game-state bit 0x8 (no writer in the exe) is set; that test
    #     at 0x638a35 now also skips it while the toggle is on and the player is the human (FUN_006345b0(player)).
    def build36(a):
        a.e('8b4628 8b88d80a0000 f6c108'); a.js('75', 'skip')              # the original bit 0x8 (everyone)
        a.e('803d'); a.imm(CHEAT_UPKEEP); a.e('00'); a.js('74', 'pay')
        a.e('8bce'); a.call(IS_HUMAN_OBJ); a.e('84c0'); a.js('75', 'skip')
        a.mark('pay'); a.jmp(0x638a46)
        a.mark('skip'); a.jmp(0x638a57)
    c36 = r3_code(build36)[0]
    put(0x638a35 - EXE_BASE, jmp(0x638a35, c36) + h('90') * 12, h('8b46288b88d80a0000c1e903f6c1017511'))
    r3_toggle('T', CHEAT_UPKEEP, 'UPKEEP')

    # 37) FREE GENERAL (panel 'CH_U', one-shot): patch 23's spawn with an empty unit vector, i.e. FUN_0068b600(army
    #     manager; pid, &'MARISCAL', &{}, province) creates only the commander and his army, in the same province
    #     (home capital, another capital, any province with a free army slot).
    c37 = r3_code(lambda a: spawn_code(a, False))[0]
    r3_oneshot('U', c37, 'LTEXT_UI_CHEAT_GENERAL_DONE', 'LTEXT_UI_CHEAT_GENERAL_FAIL')

    # 38) FREE FLEET (panel 'CH_V', one-shot): four warships of the human nation's best class in one of its ports,
    #     joined into a new fleet when the port has room for one (else they wait in the port, as built ships do).
    #     Ship class: the ship defs of the army manager's ship service ([[ui+0xa8]+0x1c], list +0x14..+0x18) with
    #     nation [def+0x54] = FUN_00634f60(player) and the highest warship class [def+0x30] in 4..6 (FUN_005bd670's
    #     test; 6 = ship of the line, the dearest). Port: FUN_0063f720(province; pid) ret 4 = the province's port owned
    #     by the human, object FUN_0065ed80([ui+0xb8]; id) ret 4; provinces holding a capital first. Ships: the port's
    #     own builder FUN_00630880(port; pid, def, 0) ret 0xc (what the shipyard calls); fleet: FUN_006302e0(port; ship)
    #     ret 4 (room?) then FUN_00630810(port; ship, 0x9149dc) ret 8, as FUN_00630880(.., 1) does; the other ships
    #     join with fleet vf+0x2c(ship), as FUN_0068b6e0 does (fleet found by FUN_00684b60 in [mgr+0x80..0x84]).
    PORT_OF, SUB_OBJ, MAKE_SHIP, CAN_FLEET, MAKE_FLEET, FIND_IN = 0x63f720, 0x65ed80, 0x630880, 0x6302e0, 0x630810, 0x684b60

    def build38(a):     # fleet(ecx = map UI) -> eax = first ship id or 0
        # frame: [ebp-4] UI, [ebp-8] human, [ebp-0xc] port, [ebp-0x10] nation, [ebp-0x14] ship def, [ebp-0x18] result,
        #        [ebp-0x1c] pass, [ebp-0x2c] 4 ship ids, [ebp-0x30] iterator
        a.e('55 8bec 83ec30 53 56 57 894dfc 33c0 8945e8 8945ec')
        a.e('8b8160010000 8945f8 50 8b89c0000000'); a.call(FIND_PLAYER2)
        a.e('85c0'); a.jl('0f84', 'out')
        a.e('8bc8'); a.call(NATION_OF); a.e('8945f0')
        a.e('8b4dfc 8b89a8000000 8b491c 8b7114 8b7918 33db')               # ship defs [esi, edi); ebx = best class
        a.mark('dl'); a.e('3bf7'); a.js('73', 'dd')
        a.e('8b06 83c604 85c0'); a.js('74', 'dl')
        a.e('8b55f0 395054'); a.js('75', 'dl')                              # this nation
        a.e('8b5030 83fa04'); a.js('7c', 'dl'); a.e('83fa06'); a.js('7f', 'dl')   # warship class 4..6
        a.e('3bd3'); a.js('7e', 'dl'); a.e('8bda 8b00 8945ec'); a.js('eb', 'dl')  # better: keep its def id
        a.mark('dd'); a.e('837dec00'); a.jl('0f84', 'out')
        a.e('c745e401000000')                                               # pass 1: provinces with a capital; 0: any
        a.mark('pass'); a.e('8b45fc 8b80b8000000 8bb888000000')
        a.mark('pl'); a.e('8b45fc 8b80b8000000 3bb88c000000'); a.jl('0f83', 'pend')
        a.e('8b0f 83c704 85c9'); a.js('74', 'pl')
        a.e('8139'); a.imm(0x8c6da0); a.js('74', 'pl')                      # sea zone
        a.e('837de400'); a.js('74', 'any')
        a.e('83b98c00000000'); a.js('74', 'pl')
        a.mark('any'); a.e('ff75f8'); a.call(PORT_OF); a.e('85c0'); a.js('74', 'pl')
        a.e('50 8b4dfc 8b89b8000000'); a.call(SUB_OBJ); a.e('85c0'); a.js('75', 'found'); a.jl('e9', 'pl')
        a.mark('pend'); a.e('ff4de4'); a.jl('0f89', 'pass'); a.jl('e9', 'out')
        a.mark('found'); a.e('8945f4 33db')
        a.mark('sh'); a.e('8b4df4 6a00 ff75ec ff75f8'); a.call(MAKE_SHIP); a.e('89449dd4 43 83fb04'); a.js('72', 'sh')
        a.e('8b45d4 8945e8 85c0'); a.jl('0f84', 'out')
        a.e('50 8b4df4'); a.call(CAN_FLEET); a.e('84c0'); a.jl('0f84', 'out')
        a.e('68dc499100 ff75d4 8b4df4'); a.call(MAKE_FLEET); a.e('85c0'); a.jl('0f84', 'out')
        a.e('8b4dfc 8bb1a8000000 50 ffb684000000 ffb680000000 8d45d0 50'); a.call(FIND_IN); a.e('83c410')
        a.e('8b00 3b8684000000'); a.jl('0f84', 'out'); a.e('8b30 bb01000000')   # esi = the new fleet
        a.mark('add'); a.e('8b449dd4 85c0'); a.js('74', 'an'); a.e('50 8bce 8b16 ff522c')
        a.mark('an'); a.e('43 83fb04'); a.js('72', 'add')
        a.mark('out'); a.e('8b45e8 5f 5e 5b 8be5 5d c3')
    c38 = r3_code(build38)[0]
    r3_oneshot('V', c38, 'LTEXT_UI_CHEAT_FLEET_DONE', 'LTEXT_UI_CHEAT_FLEET_FAIL')

    # 39) COW CAVALRY (panel 'CH_W', toggle, cosmetic, every side): the credits code LASVAQUITASHACENMU (switchMooMode
    #     0x767cc0) toggles byte +0x28 of the game-options service (registry key 0x4a9840; also [GS+0x4e4], looked up at
    #     0x5a4017 when the campaign model is built; difficulty is its +0x44). The battle unit setup reads it at 0x4bf280
    #     ([unit setup+0x134] = the same service) and loads Models/Criaturas/Vaca for cavalry. The toggle flips that byte.
    pair39 = r3_pair('COWS')

    def build39(a):
        a.e('8b81d0000000 85c0'); a.js('74', 'z')
        a.e('8b90e4040000 85d2'); a.js('74', 'z')
        a.e('83c228 b8'); a.imm(pair39); a.jmp(toggle_byte18)
        a.mark('z'); a.e('33c0 c3')
    r2_slot('W', r3_code(build39)[0])

    # 40) PROVINCIAL MILITARY BUILDINGS (PROVINCIAL_MILITARY; data: make_map.provincial_military): the HUMAN may build
    #     the basic cuartel / barracks / stables / foundry in his NON-capital provinces, at PROVINCIAL_COST_MULT x the
    #     cost and PROVINCIAL_EXTRA_TURNS more turns. Capitals and the AI: original rules and prices.
    #     Building def (mng s9): +0xac location mask (int 4; 1/2 own capitals, 4 own non-capital, 8/0x10 foreign
    #     capitals), +0x38 prerequisite, +0x3c turns; the four basic records also carry PROVINCIAL_MASK (0x20, no
    #     original record uses it; the stats filter FUN_006aa130 only tests the single bits of FUN_0063e6f0 -> inert).
    #     The 'rule' = def mask & (4|0x20) == 0x20, the province has no capital ([FUN_0065e430(prov)+0x8c] == 0) and the
    #     player is human (FUN_0065ae90 player -> FUN_006345b0), checked by is_prov (thiscall ecx = production manager
    #     P: +0x30 building defs, +0x9c players, +0xa0 provinces; args pid, bld, prov; ret 0xc; eax 0/1).
    #     a) buildable list FUN_006ae570: non-capital filter 'test byte [def+0xac],4; jne keep' (0x6af295, stack at
    #        body level: [esp+0x14] = P, [esp+0xf8] = player id) -> also keep bit-0x20 buildings for a human player.
    #        All users (construction panel PCON 0x7e63b0, dialog 0x814f20/0x8166f0, AI picker FUN_00707260, Lua
    #        es_edificio_construible_en_provincia) go through it, so the AI never gets them.
    #     b) cost: every construction call of FUN_0069f800(P; &cost, pid, bld) ret 0xc gets the province through a
    #        stub and runs cost3 (the same call, then the 6 resource ints +4..+0x18 of the cost x MULT when the rule
    #        holds): order check FUN_00699b20(pid, bld, prov) 0x699b6b; head check FUN_00699c00 0x699c27, payment
    #        FUN_0069a670 0x69a6c4 and next-head payment FUN_0069a960 0x69aa23 (edi = queue item, +8 province);
    #        cancel refund FUN_0069a960 0x69a9b2 (ebx = model province node FUN_005a6020, +4 province id), so a refund
    #        equals what was paid. The affordability test FUN_006a42b0 and payment FUN_006352d0 (reason 1) get the
    #        3x cost, so patch 24 (Free) still makes it free and patch 21 (Finish all) pays the 3x price as usual.
    #     c) turns: the order FUN_0069a810 queues the item with [def+0x3c] (0x69a8f8: mov eax,[edx+0x3c]; push eax;
    #        push ebx; edi = pid, ebp = prov, ebx = bld, esi = construction manager, P = [esi+0x4c]) -> + EXTRA.
    #        The item counts its own turns (+0x10, FUN_0069b3d0), so patch 21 / Fast Build still finish it at once.
    #        The progress fraction FUN_00699d50(pid, bld, prov) divides by FUN_0069f8b0's def turns (0x699d76): +EXTRA too.
    #     d) construction dialog (vtable 0x8c82b0; [dlg+0xec] player, [dlg+0xf0] province = vf+0x94, [dlg+0x1a0] P): its
    #        text providers 0x815580 / 0x815640 / 0x815700 (cost +4 / +8 / +0x10) and 0x8157c0 (turns) lose the dialog
    #        pointer before the call, so their 'mov ecx,[ecx+0x1a0]' calls ui_ctx (saves [dlg+0xf0] in UI_PROV, keeps
    #        eax/edx/flags) and the cost / turns call goes through a stub that passes UI_PROV: the panel shows 3x / +2.
    #     e) troop order FUN_00698980: the centre lookup FUN_005a6dd0 may return 0 (bad centre id) and 0x698a50 read
    #        [eax+0x20]; the call at 0x698a4b now leaves through the 'queue full' exit 0x698add (al = 1) on 0. It
    #        falls through into patch 27's hook at 0x698a53 otherwise (no overlap).
    #     Code in this agent's reserved run 0x881880-0x881aff (after patch 30), scratch dword UI_PROV = 0x942f40 (BSS,
    #     runtime only). Statically verified (capstone, stack walks, test-exe diff); not yet tested in game.
    if PROVINCIAL_MILITARY:
        C40, C40_END, UI_PROV = 0x881880, 0x881b00, 0x942f40
        MUL40, EXT40, BIT40 = PROVINCIAL_COST_MULT, PROVINCIAL_EXTRA_TURNS, PROVINCIAL_MASK
        assert 1 <= MUL40 <= 127 and 0 <= EXT40 <= 127 and BIT40 in (0x20, 0x40, 0x80)
        GET_COST, GET_TURNS, FIND_PROV, FIND_PL, IS_HUM, FIND_CENTRE = \
            0x69f800, 0x69f8b0, 0x65e430, 0x65ae90, 0x6345b0, 0x5a6dd0
        MASK45 = 0x881560                                # patch 45's mask_ai (int3 gap 0x881559-0x8815ff)
        a = CaveAsm(C40)
        a.mark('isprov')                                 # is_prov(ecx = P; pid, bld, prov) ret 0xc -> eax 0/1
        a.e('56 8bf1 8b4e30 8b01 ff74240c ff5004')       # esi = P; def = [P+0x30]->vf4(bld)
        a.e('85c0'); a.js('74', 'no')
        a.e('8a80ac000000 24%02x 3c%02x' % (4 | BIT40, BIT40)); a.js('75', 'no')   # (mask & (4|bit)) == bit
        a.e('8b8ea0000000 ff742410'); a.call(FIND_PROV)  # province object (or 0)
        a.e('85c0'); a.js('74', 'no')
        a.e('83b88c00000000'); a.js('75', 'no')          # a capital in it: original rules
        if AI_PROVINCIAL:                                # patch 45: the rule holds for every player (the AI only
            a.e('b801000000'); a.js('eb', 'out')         # gets these buildings outside capitals through patch 44)
        else:
            a.e('8b8e9c000000 ff742408'); a.call(FIND_PL)    # player object (or 0)
            a.e('85c0'); a.js('74', 'no')
            a.e('8bc8'); a.call(IS_HUM); a.e('0fb6c0'); a.js('eb', 'out')   # human?
        a.mark('no'); a.e('33c0')
        a.mark('out'); a.e('5e c20c00')
        a.mark('cost3')                                  # cost3(ecx = P; prov, out, pid, bld) ret 0x10 -> eax = out
        a.e('56 8bf1 ff742414 ff742414 ff742414'); a.call(GET_COST)                 # (out, pid, bld)
        a.e('50 ff74240c ff74241c ff74241c 8bce'); a.jl('e8', 'isprov')             # (pid, bld, prov)
        a.e('85c0 58'); a.js('74', 'c_done')             # (pop keeps the flags of the test)
        a.e('6a06 59')                                   # the 6 resource ints +4..+0x18
        a.mark('c_mul'); a.e('6b1488%02x 891488 49' % MUL40); a.js('75', 'c_mul')
        a.mark('c_done'); a.e('5e c21000')
        a.mark('turns3')                                 # turns3(ecx = P; prov, pid, bld) ret 0xc -> eax = turns
        a.e('56 8bf1 ff742410 ff742410'); a.call(GET_TURNS)                         # (pid, bld)
        a.e('50 ff74240c ff742418 ff742418 8bce'); a.jl('e8', 'isprov')             # (pid, bld, prov)
        a.e('85c0 58'); a.js('74', 't_done'); a.e('83c0%02x' % EXT40)
        a.mark('t_done'); a.e('5e c20c00')
        # call-site stubs: [esp] = return address, the site's 3 args above it; the province goes in as a new FIRST
        # arg (pop the return, push the province, push the return back); cost3 / turns3 clean it with the rest
        a.mark('s_item'); a.e('58 ff7708 50'); a.jl('e9', 'cost3')          # edi = queue item, +8 province
        a.mark('s_node'); a.e('58 ff7304 50'); a.jl('e9', 'cost3')          # ebx = model province node, +4 id
        a.mark('s_order'); a.e('58 ff742444 50'); a.jl('e9', 'cost3')       # FUN_00699b20's 3rd argument
        a.mark('s_ui'); a.e('58 ff35'); a.imm(UI_PROV); a.e('50'); a.jl('e9', 'cost3')
        a.mark('s_uit'); a.e('58 ff35'); a.imm(UI_PROV); a.e('50'); a.jl('e9', 'turns3')
        a.mark('s_prog'); a.e('58 ff742424 50'); a.jl('e9', 'turns3')       # FUN_00699d50's 3rd argument
        a.mark('ui_ctx')                                 # for 'mov ecx,[ecx+0x1a0]' (ecx = dialog), called
        a.e('50 8b81f0000000 a3'); a.imm(UI_PROV); a.e('58 8b89a0010000 c3')
        a.mark('q_turns')                                # 0x69a8f8: the queued item's turns
        a.e('8b423c 50 55 53 57 8b4e4c'); a.jl('e8', 'isprov')
        a.e('85c0 58'); a.js('74', 'q_n'); a.e('83c0%02x' % EXT40)
        a.mark('q_n'); a.e('50 53'); a.jmp(0x69a8fd)    # push turns; push ebx (displaced)
        a.mark('mask')                                   # 0x6af295: eax = def
        a.e('f680ac00000004'); a.js('75', 'm_keep')      # bit 4: original non-capital building
        a.e('f680ac000000%02x' % BIT40); a.js('74', 'm_drop')
        a.e('8b4c2414 8b899c000000 ffb424f8000000'); a.call(FIND_PL)
        a.e('85c0'); a.js('74', 'm_drop'); a.e('8bc8'); a.call(IS_HUM)
        if AI_PROVINCIAL:                                # patch 45: an AI player goes on to mask_ai
            a.e('84c0'); a.js('75', 'm_keep'); a.jmp(MASK45)
        else:
            a.e('84c0'); a.js('74', 'm_drop')
        a.mark('m_keep'); a.jmp(0x6af30f)
        a.mark('m_drop'); a.jmp(0x6af29e)
        a.mark('guard')                                  # 0x698a4b: centre object or the 'queue full' exit
        a.call(FIND_CENTRE); a.e('85c0 0f84'); a.imm(0x698add - (a.here() + 4)); a.jmp(0x698a50)
        code40 = a.done(); L40 = a.lab
        assert C40 + len(code40) <= C40_END, hex(len(code40))
        cave_free(C40, len(code40))
        put(C40 - EXE_BASE, code40)

        def call_to(site, lab, old):                    # retarget a 'call rel32' (same length, same stack)
            put(site - EXE_BASE, b'\xe8' + struct.pack('<i', L40[lab] - (site + 5)), h(old))
        for site, lab, old in ((0x699b6b, 's_order', 'e8905c0000'), (0x699c27, 's_item', 'e8d45b0000'),
                               (0x69a6c4, 's_item', 'e837510000'), (0x69aa23, 's_item', 'e8d84d0000'),
                               (0x69a9b2, 's_node', 'e8494e0000'), (0x699d76, 's_prog', 'e8355b0000'),
                               (0x8155ad, 's_ui', 'e84ea2e8ff'), (0x81566d, 's_ui', 'e88ea1e8ff'),
                               (0x81572d, 's_ui', 'e8cea0e8ff'), (0x8157e8, 's_uit', 'e8c3a0e8ff')):
            call_to(site, lab, old)
        for site in (0x815591, 0x815651, 0x815711, 0x8157e0):   # mov ecx,[ecx+0x1a0] -> call ui_ctx; nop
            put(site - EXE_BASE, b'\xe8' + struct.pack('<i', L40['ui_ctx'] - (site + 5)) + h('90'), h('8b89a0010000'))
        put(0x69a8f8 - EXE_BASE, jmp(0x69a8f8, L40['q_turns']), h('8b423c5053'))
        put(0x6af295 - EXE_BASE, jmp(0x6af295, L40['mask']) + h('90') * 4, h('f680ac000000047571'))
        put(0x698a4b - EXE_BASE, jmp(0x698a4b, L40['guard']), h('e880e3f0ff'))

    # ---- 41-43) QUICK GAME FOR EVERY PLAYABLE NATION (user 2026-10-21: a new nation in Quick Game showed white troop
    #      buttons, the placeholder header 'FRANCIA' and no Select Empire text; data side: make_map.quick_game_ui).
    #      The Quick Game screens hard-code the five empires (static RE of the original exe, 2026-10-21):
    #        - army screen (dialog vtable 0x8dcf70, Show FUN_007d57a0): FUN_007d00e0 gives every troop-type button the
    #          texture handle at [dlg + 0x174 + country*4], a 5-slot table filled from FILE_INGLATERRA/FRANCIA/AUSTRIA/
    #          RUSIA/PRUSIA (FUN_007cf110, +0x178..+0x188 = country ids 1..5); any other country reads unrelated dialog
    #          fields -> no texture -> the WHITE buttons;
    #        - army / navy Show (FUN_007d57a0 / FUN_007d76c0) set the header 'WTIM' only when the country name is one
    #          of the five (LTEXT_PAIS_<name>), else the .MSG "FRANCIA" placeholder of UI_DefsSelectArmy/Navy.sb stays;
    #        - Select Empire rows (FUN_007ca610, Quick Game modes 1/2) take the info text only from the five hard-coded
    #          LTEXT_UI_MAINMENU_SI_INFO_<X>_QUICKGAME keys (0x7cb720..0x7cb8f9), else none -> the empty description.
    #      (The bought-troop cards and Auto-Buy are pure data: card key <COUNTRY>_<TYPE>_BTN_SOLTADO/PULSADO, built by
    #      FUN_007ce640 from the troop record's country; Auto-Buy blocks .PAIS by country, FUN_0075a090. Both are
    #      generated by make_map.quick_game_ui, which also writes the Plantilla<COUNTRY>.tga atlases used by 42.)
    #      41) header: both 5-name chains become 'edi = name; qg_title(name); continue at the chain end'. qg_title
    #          sprintf's LTEXT_PAIS_<country name> and sets 'WTIM' exactly as the original blocks do (FUN_00530800 ->
    #          FUN_00530f20 -> FUN_005584e0('WTIM') -> FUN_00562500(&text, -1, 0, 1)), so the five get the same key as
    #          before and every other country its own LTEXT_PAIS_ text. The chain's pending argument (push of the
    #          FUN_0052fb10 call at 0x7d5923 / 0x7d7843, popped by the chain's add esp,8) is popped by the stub.
    #      42) troop-type buttons: the three 'lea ebx,[ebp+country*4+0x174]' in FUN_007d00e0 call qg_file: countries
    #          1..5 keep their slot; any other gets the handle of 'Game/UI/MainMenu/Tropas/Botones/Plantilla<COUNTRY>.tga'
    #          (country name from the enum map [[dlg+0xc0]+0x18]+0x28 as Show reads it), cached for the last country in
    #          QG_CID / QG_FILE (BSS). Flags and all registers but ebx are kept (a 'je' after two of the sites tests
    #          the flags of the cmp before them).
    #      43) Select Empire info: the mode-0 block (info key of the player record, [esp+0x94]+0xc) now runs for every
    #          mode; mode != 0 then continues into the original five-key chain, which still replaces it for the five
    #          (France's block overwrites without a release: one leaked reference of an interned string, harmless).
    #      Code in the int3 run 0x883e80-0x883fff (after patch 24's reserved 0x883e00-0x883e7f), scratch dwords
    #      0x942fd0 / 0x942fd4. No branch from outside lands inside a replaced range (capstone scan of the functions).
    #      Statically verified (capstone listing, stack walk, sandbox patch of the original exe); not tested in game.
    QG, QG_END, QG_CID, QG_FILE = 0x883e80, 0x884000, 0x942fd0, 0x942fd4
    #      FIX 2026-10-22 (in-game test: header still 'FRANCIA', buttons still white): (a) the c_str helper is
    #      FUN_0052fcc0 (char*); FUN_0052fe00, used first, returns a std::string* (FUN_007ce640 feeds it to the string
    #      operator+ FUN_00403180), so sprintf printed garbage and both names were wrong; (b) Quick Game runs the BASE
    #      dialogs (army vtable 0x8dcf70 Show FUN_007d0560, navy 0x8dd130 Show FUN_007d1eb0; player = QG state
    #      +0xb0/+0x84 resp. +0xdc...), whose own 5-name chains (name in ebp) were not hooked: the derived classes
    #      0x8dd330 / 0x8dd408 (Show FUN_007d57a0 / FUN_007d76c0) belong to another mode. All four chains are hooked now.
    STR_C, SPRINTF, STR_NEW, STR_ADDREF, STR_REL, TEXT_OF, CTRL, SET_TEXT, MAP_FIND = \
        0x52fcc0, 0x40644d, 0x530800, 0x52fb10, 0x530890, 0x530f20, 0x5584e0, 0x562500, 0x5c0410
    a = CaveAsm(QG)
    a.mark('title')                                     # qg_title(ecx = army/navy dialog; name handle) ret 4
    a.e('55 56 57 8bf1 83ec44')                         # keep ebp/esi/edi; esi = dialog; buf [esp], text [esp+0x40]
    a.e('ff742454'); a.call(STR_C); a.e('83c404')       # eax = c_str(name)
    a.e('50 68'); fmt_at = [len(a.b)]; a.b += bytes(4)  # push 'LTEXT_PAIS_%s' (absolute, set below)
    a.e('8d4c2408 51'); a.call(SPRINTF); a.e('83c40c')  # sprintf(buf, fmt, name)
    a.e('6a01 6a00 6aff 8d44240c 50'); a.call(STR_NEW); a.e('83c404')     # key handle of buf
    a.e('50 8d542450 52'); a.call(TEXT_OF); a.e('83c408')                   # &text = TEXT_OF(&text, key)
    a.e('8be8 68'); a.imm(0x5754494d); a.e('8bce'); a.call(CTRL)            # control 'WTIM'
    a.e('55 8bc8'); a.call(SET_TEXT)                                         # (&text, -1, 0, 1) ret 0x10
    a.e('8b442440 85c0'); a.js('74', 't_rel'); a.e('50'); a.call(STR_REL); a.e('83c404')
    a.mark('t_rel'); a.e('83c444 5f 5e 5d c20400')
    a.mark('file')                                      # qg_file (ebp = army dialog) -> ebx = address of a handle
    a.e('9c 50 51 52 8b8514010000 8d9c8574010000 8d48ff 83f904'); a.jl('0f86', 'f_out')   # countries 1..5
    a.e('bb'); a.imm(QG_FILE); a.e('3b05'); a.imm(QG_CID); a.jl('0f84', 'f_out')          # cached
    a.e('81ec88000000 89842484000000')                  # buf [esp], iterator [esp+0x80], country [esp+0x84]
    a.e('8b8dc0000000 8b4918 83c128')                   # ecx = country enum map
    a.e('8d842484000000 50 8d842484000000 50'); a.call(MAP_FIND)    # find(&it, &country) ret 8
    a.e('8b842480000000 ff700c'); a.call(STR_C); a.e('83c404')      # eax = c_str(country name)
    a.e('50 68'); fmt_at.append(len(a.b)); a.b += bytes(4)
    a.e('8d4c2408 51'); a.call(SPRINTF); a.e('83c40c')
    a.e('54'); a.call(STR_NEW); a.e('83c404')            # new handle of buf
    a.e('8b0d'); a.imm(QG_FILE); a.e('a3'); a.imm(QG_FILE)
    a.e('8b842484000000 a3'); a.imm(QG_CID)
    a.e('85c9'); a.js('74', 'f_rel'); a.e('51'); a.call(STR_REL); a.e('83c404')   # release the previous handle
    a.mark('f_rel'); a.e('81c488000000 bb'); a.imm(QG_FILE)
    a.mark('f_out'); a.e('5a 59 58 9d c3')
    a.mark('fmt_t'); a.b += b'LTEXT_PAIS_%s\0'
    a.mark('fmt_f'); a.b += b'\\'.join([b'Game', b'UI', b'MainMenu', b'Tropas', b'Botones', b'Plantilla%s.tga\0'])  # as FILE_*
    code41 = bytearray(a.done()); L41 = a.lab
    for p, lab in zip(fmt_at, ('fmt_t', 'fmt_f')):
        struct.pack_into('<I', code41, p, L41[lab])
    assert QG + len(code41) <= QG_END, hex(len(code41))
    cave_free(QG, len(code41))
    put(QG - EXE_BASE, bytes(code41))
    for site, back, reg, old in (                       # reg: the register the chain keeps the name handle in
            (0x7d0654, 0x7d0881, '8be8', '68508c8b008be8e8a001d6ff83c4083be80f'),   # army Show (Quick Game, base)
            (0x7d1fb9, 0x7d21e6, '8be8', '68508c8b008be8e83be8d5ff83c4083be80f'),   # navy Show (Quick Game, base)
            (0x7d5929, 0x7d5b6a, '8bf8', '68508c8b008bf8e8cbaed5ff83c4083bf80f'),   # army Show (derived class)
            (0x7d7849, 0x7d7a8a, '8bf8', '68508c8b008bf8e8ab8fd5ff83c4083bf80f')):  # navy Show (derived class)
        stub = h('83c404' + reg + '50 8bce') + b'\xe8' + struct.pack('<i', L41['title'] - (site + 13))
        stub += jmp(site + len(stub), back)
        assert len(stub) == 18
        put(site - EXE_BASE, stub, h(old))
    for site, old in ((0x7d02bd, '8d9c8d74010000'), (0x7d02e9, '8d9c8574010000'), (0x7d032b, '8d9c9574010000')):
        put(site - EXE_BASE, b'\xe8' + struct.pack('<i', L41['file'] - (site + 5)) + h('9090'), h(old))
    se43 = (h('8b842494000000 8b480c 51') + b'\xe8' + struct.pack('<i', STR_ADDREF - (0x7cb701 + 5))
            + h('83c404 898424ec000000 33ed 39aeb0010000 7506') + jmp(0x7cb71a, 0x7cb8f9) + h('90'))
    assert len(se43) == 42
    put(0x7cb6f6 - EXE_BASE, se43, h('83beb001000000 7521 8b842494000000 8b480c 51 e80144d6ff 83c404 898424ec000000'
                                     ' 33ed e9d9010000'))

    # ---- 44-46) SMART AI PROVINCIAL BARRACKS (AI_PROVINCIAL, on top of patch 40; user 2026-10-21). The AI uses the
    #      ORIGINAL records (no new mng records): building unlocks are the per-player set [player+0x564] (FUN_00699ac0,
    #      filled by start objects / techs, one building per tech record, SAVED with the player), and the rules file
    #      DefReglasEdificios.sb, the icon keys, the texts, Incidencias.lua (IDX_CUARTEL_BASICO) and the s13 map spots
    #      all key the originals. Troops come from the buildings' troop lists (cuartel vf+0x3c FUN_0062f4c0: own list +
    #      the owner's other buildings in the province), so copies would train the same troops, but they would need new
    #      ids written into every AI's saved unlock set (a save that then crashes without the records). The originals in
    #      a non-capital province are exactly what the human's patch 40 already builds (tested in game).
    #      44) GATE, once per AI turn: brain state 1 (0x6f13a0 'call 0x6ecda0', esi = brain; ecx = esi) calls gate,
    #          which ends with 'jmp 0x6ecda0'. AI_PID = [brain+0x12c0]; AI_PROV = 0, then: T = target node [+0xd4] of the
    #          military minister's best objective FUN_007418a0(MIL+0x914) (MIL = brain+0x70c; none -> no province).
    #          Every land node (vector MIL+0x18c vf+0xc, 0xf0 B, +4 kind 0 = land, +0xc province; built one per
    #          province by FUN_00747e50) gets d = FUN_007117f0(MIL vf+0x60 = route table MIL+0x200; node, T, pid) =
    #          hops (READ only, no FUN_00727790 / FUN_00730cf0). With an AI-owned cuartel (FUN_0063f690(0, pid) on the
    #          province object): BASE = min d; non-capital ones count (CNT) and the nearest is EXP. Without one, in a
    #          non-capital province: a CUARTEL_BASICO of this AI in its building queue (model province +0x84, item +4
    #          pid, +0xc building, next +0x1c) counts too; else it is a candidate if d <= REACH, the AI owns it
    #          (FUN_00639e50) and its country's capital has an AI cuartel. The country is the model province record's
    #          +0xc (runtime COUNTRY id, as FUN_0063e610 reads it); the capital comes from safecap below. AI_PROV =
    #          the nearest candidate if CNT < MAX and it is >= SAVE hops nearer than BASE, else EXP if EXP is within
    #          REACH (so the barracks / stables / foundry can follow there), else 0.
    #      45) RULE: patch 40's mask cave (0x6af295) sends a non-human player to mask_ai: keep the bit-0x20 building only
    #          if pid == AI_PID, province ([esp+0xfc], FUN_006ae570's 2nd argument, never written) == AI_PROV and the
    #          AI holds RESERVE x the provincial price of its gold and 2nd resource (def +0x1c / +0x20 x MULT x
    #          RESERVE vs FUN_006345f0 resources +4 / +8). The picker FUN_00707260, Lua es_edificio_construible_* and
    #          the ECON minister all go through it. is_prov now holds for every player (the human's result is
    #          unchanged; the AI only reaches it here), so the AI pays MULT x and waits +EXTRA turns like the human. The
    #          ECON feasibility FUN_007052e0(out, prov, bld..) gets the province too (0x705332 -> s_econ -> cost3): it
    #          sees the 3x price. (Its preference FUN_00709770 prices before picking a province: 1x, left alone.)
    #      46) RECRUITMENT: FORMAR_BATALLON case 5 of FUN_006f10d0 (0x6f11a1..0x6f11b4: capital province of the country
    #          [order+0x1c] -> its first cuartel, any owner; esi = order, edi = brain, ebx = 0, [esp+0x10] = pid) ->
    #          rec. Without an objective the original lookup. Else, for each province of the country (FUN_00662120 on
    #          [brain+0x34]), evalp keeps the cuartel owned by the AI whose production centre (FUN_005a6dd0 on the model
    #          [provinces+0x34]) has fewer than 7 queued (the AI cap) and whose troop set (vf+0x3c into a set made with
    #          FUN_006243d0(1), looked up with FUN_00491310) holds the order's troop [order+0x18], in a province the AI
    #          owns; the best is the one FUN_00711cf0(MIL; best, this) does not keep (strictly nearer the objective by
    #          land or sea); nodes by a scan of the node vector (nodeof). None -> the original lookup, which may give 0
    #          like before (patch 40's guard at 0x698a4b ends such an order; an AI cuartel that is gone or captured has
    #          no centre object and is never returned by evalp).
    #      Code in static int3 gaps: gate 0x881300 (after patch 2's table, <= 0x881300), its node step 0x880f20 (after
    #      patch 28), mask_ai 0x881560 (between patches 4 and 5), evalp / nodeof 0x881420 (after patch 3's stubs), rec
    #      0x881a10 (after patch 40, this agent's run), shared tail 0x882f60 (gate decision, rec exit, s_econ; after
    #      patch 17's string), safecap / safeset 0x8810a0 (int3 padding after the original function ending 0x881092).
    #      Scratch dwords AI_PID 0x942f44, AI_PROV 0x942f48 (BSS, zero = no AI). No branch from
    #      outside lands in a replaced range (byte scan). Statically verified (capstone, stack walk, test-exe diff);
    #      not tested in game.
    #      FIX 2026-10-22 (crash c0000005 at 0x65e1e3 after End Turn, Qing, both builds): the node step passed
    #      FUN_0063ab00 (= the province's OWNER PLAYER id: model province +0x10 -> FUN_00595750 player data +4) to
    #      FUN_0065ecf0, which wants a runtime COUNTRY id: FUN_0065e1d0 -> FUN_005a5fa0 (model +0x48 list, rec +4, next
    #      +0x110) found nothing and 0x65e1e3 'mov esi,[eax+0x44]' read NULL. Now the node step keeps the model
    #      province record ([ebp-0x3c], free slot of the 0x40 frame; no record -> the province is skipped) and passes
    #      its +0xc. safecap(provinces mgr; country) ret 4 / safeset(mgr; country, &set, flag) ret 0xc check the
    #      country with FUN_005a5fa0 (model = mgr +0x34) and tail-jump to FUN_0065ecf0 / FUN_00662120 with the stack
    #      unchanged, else return 0 / leave the set empty. Patch 46 uses them too for the Lua order's country
    #      ([order+0x1c], the same id the original 0x6f11a1 passes unchecked): an unknown country now gives
    #      'no cuartel' (patch 40's 0x698a4b guard ends the order) instead of a crash. Node step stays 199 bytes.
    #      Verified statically: capstone listing, stack walk, emulator (scratchpad p44fix), test-exe diffs.
    if PROVINCIAL_MILITARY and AI_PROVINCIAL:
        AI_PID, AI_PROV = 0x942f44, 0x942f48
        NODE44, GATE44, SUB46, REC46, TAIL46, SAFE44 = 0x880f20, 0x881300, 0x881420, 0x881a10, 0x882f60, 0x8810a0
        CU_ID = {v: k for k, v in Mng.parse_enum(m29.table(7)).items()}['CUARTEL_BASICO']
        MAXN, REACH, SAVE = AI_PROVINCIAL_MAX, AI_PROVINCIAL_REACH, AI_PROVINCIAL_SAVE
        RES = AI_PROVINCIAL_RESERVE * PROVINCIAL_COST_MULT
        assert 1 <= MAXN <= 127 and 0 <= REACH <= 127 and 0 <= SAVE <= 127 and 1 <= RES <= 127 and CU_ID < 0x80
        assert C40 + len(code40) <= REC46, 'patch 40 grew into patch 46'
        FIND_CU, OWNS, CTRY_REC, CAP_PROV, BEST_OBJ, ROUTE, CMP_NODE, MPROV, OBJ_OF = \
            0x63f690, 0x639e50, 0x5a5fa0, 0x65ecf0, 0x7418a0, 0x7117f0, 0x711cf0, 0x5a6020, 0x65ed80
        SET_CTOR, SET_DTOR, SET_FIND, PROVSET, CU_ANY, RES_OF = 0x6243d0, 0x4f7c90, 0x491310, 0x662120, 0x63f6f0, 0x6345f0

        def jabs(a, op, target):                        # near jcc / jmp to an absolute address
            a.e(op); a.imm(target - (a.here() + 4))

        def place(org, end, a):
            code = a.done()
            assert org + len(code) <= end, (hex(org), hex(len(code)))
            cave_free(org, len(code))
            put(org - EXE_BASE, code)
            return a.lab
        # safecap / safeset (ecx = provinces mgr, args as FUN_0065ecf0 / FUN_00662120): only a known runtime country
        # reaches the original (tail jump, stack and ecx as at entry); else 0 / the caller's set stays empty
        a = CaveAsm(SAFE44)
        for lab, orig, ret in (('cap', CAP_PROV, 'c20400'), ('set', PROVSET, 'c20c00')):
            a.mark(lab); a.e('51 ff742408 8b4934'); a.call(CTRY_REC)   # country record (model = mgr +0x34) or 0
            a.e('59 85c0'); jabs(a, '0f85', orig); a.e(ret)
        LSF = place(SAFE44, 0x881100, a)
        # shared tail: 44's decision + exit (gate frame, ebp: -4 pid, -0x14 node index, -0x18 BASE, -0x1c CNT,
        # -0x20 best d, -0x24 its province, -0x28 EXP's d, -0x2c EXP), 46's exit, 45's s_econ
        a = CaveAsm(TAIL46)
        a.mark('after')
        a.e('837de4%02x' % MAXN); a.js('73', 'exist')    # CNT < MAX
        a.e('8b45dc 85c0'); a.js('74', 'exist')
        a.e('8b4de8 2b4de0'); a.js('72', 'exist'); a.e('83f9%02x' % SAVE); a.js('72', 'exist')   # BASE - d >= SAVE
        a.e('a3'); a.imm(AI_PROV); a.js('eb', 'done')
        a.mark('exist'); a.e('8b45d4 85c0'); a.js('74', 'done')    # else the nearest provincial cuartel near the front
        a.e('837dd8%02x' % REACH); a.js('77', 'done'); a.e('a3'); a.imm(AI_PROV)
        a.mark('done'); a.e('8be5 61'); a.jmp(0x6ecda0)
        a.mark('fin'); a.e('8d4db4'); a.call(SET_DTOR)  # rec: province set gone; a choice?
        a.e('8b45f8 85c0'); a.js('75', 'out')
        a.mark('van'); a.e('ff761c 8b4f34'); a.call(LSF['cap']); a.e('85c0'); a.js('74', 'out')   # the original lookup
        a.e('6a00 8bc8'); a.call(CU_ANY)
        a.mark('out'); a.e('8be5 5f 5e 5b 5d'); a.jmp(0x6f11b5)
        a.mark('s_econ'); a.e('58 ff742458 50'); a.jmp(L40['cost3'])   # FUN_007052e0's province ([esp+0x58])
        LT = place(TAIL46, 0x883000, a)
        # 44 node step (ebx = node, [ebp-0x30] province object, [ebp-0x34] d, [ebp-0x38] player object; it writes
        # [ebp-0x3c] = model province record), ret
        a = CaveAsm(NODE44)
        a.e('ff75fc 6a00 8b4dd0'); a.call(FIND_CU); a.e('85c0'); a.js('74', 'nocu')
        a.e('8b45cc 3b45e8 7303 8945e8')                 # an AI cuartel: BASE = min d
        a.e('8b4dd0 83b98c00000000'); a.js('75', 'r0')   # (capital)
        a.e('ff45e4 3b45d8'); a.js('73', 'r0')           # provincial: CNT++, the nearest -> EXD / EXP
        a.e('8945d8 8b430c 8945d4'); a.mark('r0'); a.e('c3')
        a.mark('nocu'); a.e('8b4dd0 83b98c00000000'); a.js('75', 'r0')
        a.e('ff730c 8b4e34 8b4934'); a.call(MPROV)      # model province (provinces object +0x34 = model)
        a.e('85c0'); a.js('74', 'r0')                    # no record: skip the province
        a.e('8945c4 8b8084000000')                       # keep the record; building queue head
        a.mark('qloop'); a.e('85c0'); a.js('74', 'qdone')
        a.e('8b5004 3b55fc'); a.js('75', 'qn')           # item +4 player
        a.e('83780c%02x' % CU_ID); a.js('75', 'qn')      # item +0xc building
        a.e('ff45e4 c3')                                 # a cuartel of this AI being built: counts, no candidate
        a.mark('qn'); a.e('8b401c'); a.js('eb', 'qloop')
        a.mark('qdone')
        a.e('8b45cc 83f8%02x' % REACH); a.js('77', 'ret')   # d <= REACH (no route = 0xffffffff fails)
        a.e('3b45e0'); a.js('73', 'ret')                 # nearer than the candidate so far
        a.e('ff730c 8b4dc8'); a.call(OWNS); a.e('84c0'); a.js('74', 'ret')    # the AI's province
        a.e('8b45c4 ff700c 8b4e34'); a.call(LSF['cap']); a.e('85c0'); a.js('74', 'ret')   # its country's capital ...
        a.e('ff75fc 6a00 8bc8'); a.call(FIND_CU); a.e('85c0'); a.js('74', 'ret')   # ... has an AI cuartel
        a.e('8b45cc 8945e0 8b430c 8945dc')               # best d, its province
        a.mark('ret'); a.e('c3')
        place(NODE44, 0x881000, a)
        # 44 gate
        a = CaveAsm(GATE44)
        a.e('60 8bec 83ec40')
        a.e('8b86c0120000 8945fc a3'); a.imm(AI_PID)
        a.e('c705'); a.imm(AI_PROV); a.imm(0)
        a.e('8dbe0c070000 8d8f14090000'); a.call(BEST_OBJ)   # edi = MIL; its best objective
        a.e('85c0'); jabs(a, '0f84', LT['done'])
        a.e('8b80d4000000 8945f8 8b07 8bcf ff5060 8945f4')   # T, route table
        a.e('8b8e14010000 8b899c000000 ff75fc'); a.call(FIND_PL)   # player ([ECON+0x9c] = P, P+0x9c players)
        a.e('85c0'); jabs(a, '0f84', LT['done'])
        a.e('8945c8 8d8f8c010000 8b01 ff500c 8b5804 8b4008 8945f0')   # ebx = first node, end
        a.e('33c0 8945ec 8945e4 8945dc 8945d4 48 8945e8 8945e0 8945d8')
        a.mark('loop'); a.e('3b5df0'); jabs(a, '0f83', LT['after'])
        a.e('837b0400'); a.js('75', 'next')              # land nodes only
        a.e('ff730c 8b4e34'); a.call(FIND_PROV); a.e('85c0'); a.js('74', 'next')
        a.e('8945d0 ff75fc ff75f8 ff75ec 8b4df4'); a.call(ROUTE); a.e('8945cc')   # d = hops(node, T, pid)
        a.call(NODE44)                                   # the node step
        a.mark('next'); a.e('81c3f0000000 ff45ec'); a.js('eb', 'loop')
        place(GATE44, 0x881400, a)
        # 45 mask_ai (stack at FUN_006ae570's body level: [esp+0x14] P, [esp+0xf8] pid, [esp+0xfc] province; edi =
        # the candidate's set node, [edi] = building id); exits 0x6af30f keep / 0x6af29e drop like patch 40
        a = CaveAsm(MASK45)
        a.e('8b8424f8000000 3b05'); a.imm(AI_PID); a.js('75', 'drop')
        a.e('8b8424fc000000 3b05'); a.imm(AI_PROV); a.js('75', 'drop')
        a.e('8b4c2414 8b899c000000 ffb424f8000000'); a.call(FIND_PL)
        a.e('85c0'); a.js('74', 'drop')
        a.e('8bc8'); a.call(RES_OF); a.e('50')           # its resources
        a.e('8b4c2418 8b4930 8b11 ff37 ff5204 59 85c0'); a.js('74', 'drop')   # the def again
        a.e('8b501c 6bd2%02x 3b5104' % RES); a.js('7f', 'drop')               # gold
        a.e('8b5020 6bd2%02x 3b5108' % RES); a.js('7f', 'drop')               # 2nd resource
        a.jmp(0x6af30f)
        a.mark('drop'); a.jmp(0x6af29e)
        place(MASK45, 0x881600, a)
        # 46 evalp (ecx = province object -> eax = usable AI cuartel id / 0) and nodeof (eax = province -> eax = land
        # node index / -1); rec frame: ebp -4 pid, -8 best id, -0xc its node, -0x10 set cursor, -0x14 player object,
        # -0x18 node, set of provinces at -0x4c, troop set at -0x80 (0x34 B each)
        a = CaveAsm(SUB46)
        a.mark('evalp')
        a.e('53 51 ff75fc 6a00'); a.call(FIND_CU); a.e('85c0'); a.js('74', 'e0')   # the AI's own cuartel
        a.e('8bd8 50 8b4f34 8b4934'); a.call(FIND_CENTRE); a.e('85c0'); a.js('74', 'e0')   # its production centre
        a.e('83782007'); a.js('73', 'e0')                # troop queue not full (the AI's cap 7)
        a.e('53 8b4f34'); a.call(OBJ_OF); a.e('85c0'); a.js('74', 'e0')
        a.e('50 6a01 8d4d80'); a.call(SET_CTOR)
        a.e('59 8d4580 50 8b11 ff523c')                 # building vf+0x3c(&set): the troops trained here
        a.e('33c0 807d8000'); a.js('74', 'e_d')
        a.e('ff7618 8d4d84'); a.call(SET_FIND)           # the order's troop among them?
        a.mark('e_d'); a.e('50 8d4d80'); a.call(SET_DTOR); a.e('58 85c0'); a.js('74', 'e0')
        a.e('8b0424 ffb07c000000 8b4dec'); a.call(OWNS); a.e('84c0'); a.js('74', 'e0')   # the AI's province
        a.e('8bc3 59 5b c3')
        a.mark('e0'); a.e('33c0 59 5b c3')
        a.mark('nodeof')
        a.e('53 56 8bd8 8d8f98080000 8b01 ff500c 8b7004 8b5008 33c0')   # node vector of MIL+0x18c
        a.mark('n_l'); a.e('3bf2'); a.js('73', 'n_f')
        a.e('837e0400'); a.js('75', 'n_n'); a.e('395e0c'); a.js('74', 'n_d')
        a.mark('n_n'); a.e('81c6f0000000 40'); a.js('eb', 'n_l')
        a.mark('n_f'); a.e('83c8ff')
        a.mark('n_d'); a.e('5e 5b c3')
        LS = place(SUB46, 0x881500, a)
        # 46 rec
        a = CaveAsm(REC46)
        a.e('8b442410 55 53 56 57 8bec 83c480 8945fc 33c0 8945f8 834df4ff')
        a.e('8d8f20100000'); a.call(BEST_OBJ); a.e('85c0'); jabs(a, '0f84', LT['van'])   # no objective: original
        a.e('8b8f14010000 8b899c000000 ff75fc'); a.call(FIND_PL); a.e('85c0'); jabs(a, '0f84', LT['van'])
        a.e('8945ec 6a01 8d4db4'); a.call(SET_CTOR)
        a.e('6a00 8d45b4 50 ff761c 8b4f34'); a.call(LSF['set'])   # the country's provinces
        a.e('807db400'); a.js('74', 'fin'); a.e('8b45d8')
        a.mark('lp'); a.e('85c0'); a.js('74', 'fin')
        a.e('8945f0 ff30 8b4f34'); a.call(FIND_PROV); a.e('85c0'); a.js('74', 'nx')
        a.e('8bc8'); a.call(LS['evalp']); a.e('85c0'); a.js('74', 'nx')
        a.e('8bd8 8b45f0 8b00'); a.call(LS['nodeof'])
        a.e('837df800'); a.js('74', 'take')              # the first usable one
        a.e('83f8ff'); a.js('74', 'nx')
        a.e('837df4ff'); a.js('74', 'take')
        a.e('8945e8 50 ff75f4 8d8f0c070000'); a.call(CMP_NODE)   # best at least as near? keep it
        a.e('84c0'); a.js('75', 'nx'); a.e('8b45e8')
        a.mark('take'); a.e('8945f4 895df8')
        a.mark('nx'); a.e('8b45f0 8b4004'); a.js('eb', 'lp')
        a.mark('fin'); a.jmp(LT['fin'])
        place(REC46, 0x881b00, a)
        # hooks
        put(0x6f13a0 - EXE_BASE, b'\xe8' + struct.pack('<i', GATE44 - (0x6f13a0 + 5)), h('e8fbb9ffff'))
        put(0x6f11a1 - EXE_BASE, jmp(0x6f11a1, REC46) + h('90') * 15, h('8b461c 8b4f34 50 e843dbf6ff 53 8bc8 e83be5f4ff'))
        put(0x705332 - EXE_BASE, b'\xe8' + struct.pack('<i', LT['s_econ'] - (0x705332 + 5)), h('e8c9a4f9ff'))

    # 47) SAHEL OFFICER NAMES (SAHEL_OWN_OFFICERS; texts: sahel_officer_texts / make_map.reskin_officer_texts). The Kazakh
    #     Khanate (JUG_HANNOVER) and the Sahel Kingdoms (JUG_SAJONIA) both named their officers from the Germanic pool:
    #     FUN_006577d0(this; &out, pid) ret 8 (thiscall) maps a player to a POOL NAME, 'JUG_GERMANICO' for both (the
    #     'JUG_SAJONIA' compare at 0x657850, string 0x8cd0fc; its only other use is the counter-slot map FUN_00657200 at
    #     0x65725d, left alone), else 'JUG_ARABE' / 'JUG_ITALIANO' / the player's own key (FUN_005977d0). Its callers: the
    #     officer-name builder FUN_00657eb0 (key 'LTEXT_GESTION_NOMBRE_MANDO_' + pool + n, call at 0x657f6a), the ship
    #     names (_BARCO_), the heirs (FUN_00696d80, LTEXT_HEREDERO_ + pool + _M_/_F_) and the DefInfoNombres loader
    #     FUN_00657b90 (sizes MANDO_/BARCO_ + pool, stored per counter slot: [obj+8] + 0x1b4 + slot * 0x2c, +4 NUM_NOMBRES,
    #     +8 NUM_TITULOS, +0xc title index, +0x10 name index). So only the officer names change, through a flag byte:
    #       hook A 0x657f6a  call 0x6577d0 -> call C47A (0x8815e0, int3 gap 0x8815d3-0x8815ff after patch 45's mask_ai):
    #                        FLAG47 = 1; push the 2 args again; call 0x6577d0 (ecx untouched = this); FLAG47 = 0;
    #                        ret 8 (same convention, eax = &out as before; mov byte keeps eax).
    #       hook B 0x657850  cmp [esi+0xc],eax; je 0x657860 (5 bytes) -> jmp C47B (0x882fe0, int3 gap 0x882fd8-0x882fff
    #                        after patch 46's shared tail): the same cmp; SAJONIA and FLAG47 == 0 -> 0x657860 (Germanic,
    #                        unchanged), else -> 0x657855 (no match: on to the own-key path that every new nation takes).
    #                        Registers, stack and refcounted strings (eax = the 'JUG_SAJONIA' string, released at
    #                        0x657865 on both paths) as in the original; the flags are not read after either target.
    #     The counter slot stays 0xd (shared with the Kazakhs), whose NUM_NOMBRES the loader takes from MANDO_JUG_GERMANICO
    #     (53, flag clear there), hence a 53-name Sahel pool. Scratch byte FLAG47 = 0x942f4c (BSS, zero at start). No
    #     branch or pointer lands inside 0x657851-0x657854 / 0x657f6b-0x657f6e (byte scan of .text). Save-safe: no format,
    #     id or record change; saved officers keep their names, new Sahel officers draw from the new keys. Statically
    #     verified (capstone, stack walk, test-exe diff); not tested in game.
    if SAHEL_OWN_OFFICERS:
        C47A, C47B, FLAG47, POOL_OF = 0x8815e0, 0x882fe0, 0x942f4c, 0x6577d0
        a = CaveAsm(C47A)
        a.e('c605'); a.imm(FLAG47); a.e('01')              # mov byte [FLAG47], 1
        a.e('ff742408 ff742408')                           # push pid; push &out (copies of the caller's 2 args)
        a.call(POOL_OF)                                    # thiscall, ret 8
        a.e('c605'); a.imm(FLAG47); a.e('00')              # mov byte [FLAG47], 0
        a.e('c20800')                                      # ret 8
        code = a.done()
        assert C47A + len(code) <= 0x881600, 'patch 47 cave A reaches patch 5'
        cave_free(C47A, len(code)); put(C47A - EXE_BASE, code)
        a = CaveAsm(C47B)
        a.e('39460c'); a.js('75', 'own')                   # cmp [esi+0xc], eax: not JUG_SAJONIA -> no match
        a.e('803d'); a.imm(FLAG47); a.e('00'); a.js('75', 'own')   # the officer-name builder asks: own key
        a.jmp(0x657860)                                    # JUG_SAJONIA otherwise: the Germanic pool, as before
        a.mark('own'); a.jmp(0x657855)
        code = a.done()
        assert C47B + len(code) <= 0x883000, 'patch 47 cave B reaches original code'
        cave_free(C47B, len(code)); put(C47B - EXE_BASE, code)
        put(0x657f6a - EXE_BASE, b'\xe8' + struct.pack('<i', C47A - (0x657f6a + 5)), h('e861f8ffff'))
        put(0x657850 - EXE_BASE, jmp(0x657850, C47B), h('39460c740b'))

    # 48) HISTORICAL EVENTS: the campaign sequence script runs in EVERY campaign (HISTORICAL_EVENTS, passed in by make_map;
    #     data: tools/historical_events.py, whose SecuenciaGestionMod.lua is UI_ModeloGestion.sb .SECUENCIA_TUTORIAL).
    #     Original (static RE + capstone, 2026-10-22): the campaign map UI (vtable 0x8c8490) creates its Lua manager
    #     UI_GAME_GESTION_LUA_MANAGER at 0x826a09 (vtable 0x8d67a8, [ui+0x2c0]; [mgr+0x2c0] = ui; [ui+0x2c4] = the script
    #     path std::string). The sequence is started only for the tutorial: FUN_00648830 (turn 1, game-mode flags
    #     [[mgr+0x38]+0x10] bit 2 = Lua 'tutorial_gestion_activo') and the map UI tick 0x81d5b0 (vtable slot +0x10, runs
    #     EVERY FRAME; one-shot flag [GS+0xad8] bit 0x2000, cleared there) call slot +0x28 (registrar 0x767720: 0x541f20
    #     loads the script with FUN_00533ce0(path, 0, force 0) and registers the generic natives, then the campaign ones)
    #     and slot +0x48 (slot +0x44 0x540de0: [mgr+0x81] = 1 'active', Lua inicia_secuencia()). An ACTIVE manager changes
    #     the normal campaign: FUN_00822c30 (0x822fcb / 0x823007) no longer selects the province on a map-object click,
    #     0x64a7ff skips 0x822690, patch 15's Shift+OK is off, FUN_00829ff0 posts MSG_GESTION_INICIO_TURNO only then.
    #     So this patch NEVER activates the manager (no slot +0x48/+0x44, no [[mgr+0x28]+0x58]); instead:
    #       a) 0x826a17 mov [esi+0x2c0],eax (new manager) -> call C48A: same store, ST48 = 1 (pending), REG48 = 0.
    #       b) 0x81d62a (the 0x2000 flag test, 14 bytes up to the je) -> jmp C48B: the same test; flag set -> ST48 = 0 and
    #          the original tutorial path 0x81d638 (eax = GS kept). Else, once (ST48 == 1 -> 0), not in a tutorial
    #          campaign (bit 2 above): registrar slot +0x28 (ecx = mgr, push &ui[0x2c4], ret 4); REG48 == mgr (C49R ran,
    #          so the script loaded and every native is bound to this manager; its al is the message-receiver result)
    #          -> ST48 = 2 and the Lua function inicia_secuencia() (LUACALL: 0x5327d0 + pcall 0x5337c0 + result dtor
    #          0x5007f0, as 0x540de0 / 0x7685c0 do) WITHOUT 'active'. Then 0x81d65c as the original je.
    #       c) 0x82a0e3 in FUN_00829ff0 (human begin-turn UI: mov edx,[ecx]; call [edx+0x50]; test al,al; je 0x82a150)
    #          -> jmp C48D: same call; active (tutorial) -> 0x82a0ec (original post); inactive and ST48 == 2: if another
    #          sequence re-bound the natives since (LAST48 != mgr, e.g. a battle intro while this map UI lived) the
    #          registrar runs again; LAST48 == REG48 == mgr -> LUACALL HIST_TURN_HOOK; then 0x82a150. bl, esi, ebp kept.
    #       d) 0x541f42: FUN_00533ce0's force argument 0 -> 1 in 0x541f20 (all sequence managers: campaign, battle intro,
    #          naval, menu). Without it a script already loaded in this session is not reloaded and the registrar stops
    #          BEFORE registering, so the natives stay bound to the previous (freed) manager: the 2nd campaign of a session
    #          (and the tutorial after a normal campaign) would call freed objects, and after (b) a battle intro on a map
    #          already seen would call the campaign manager. Every start now reloads its script and re-binds its natives
    #          to its own manager (a first load is unchanged; include_script always forced already).
    #       e) 0x541f5a (right after the successful load in 0x541f20: mov eax,[edi+0x38]; mov ecx,[eax+0x10]) -> jmp
    #          CL48: LAST48 = edi (the manager the generic natives are now bound to) + the 2 instructions, jmp 0x541f60.
    #     Scratch (BSS, 0 at start, not saved): ST48 = 0x942f50 byte (1 pending, 2 started), REG48 = 0x942f54 (manager
    #     of the last completed campaign registration, set by C49R), LAST48 = 0x942f58. Caves (static int3 gaps, all
    #     cave_free): R2 0x882098-0x8820ff (LUACALL, patch 49), R3 0x883678-0x8836ff (before patch 23: C48B, CL48),
    #     R4 0x882b80-0x882bff (after patch 14's reserved 0x40: C49R + REG), R5 0x882888-0x8828ff (after patch 9's fixed
    #     code: C48A, C48D), R1 0x881150-0x8811ff (after patch 2's fixed 0x50-byte code: patch 50 only); strings
    #     0x881ae8 (HIST_TURN_HOOK) and 0x8814df-0x8814ff (native names). No branch or pointer lands inside 0x826a18-
    #     0x826a1c, 0x81d62b-0x81d637, 0x82a0e4-0x82a0eb, 0x541f5b-0x541f5f (byte scan of .text, false hits checked).
    #     Save-safe: nothing is written to the save; the Lua keeps its own state per session. Statically verified
    #     (capstone, stack walk of every cave exit, test-exe diffs flag off = identical / on = only these ranges);
    #     not tested in game.
    # 49) Lua native get_turno_actual() -> [[[mgr+0x2c0]+0xd0]+0x178] (map UI -> GameState -> campaign turn, 1 = July
    #     1789; +0x178 is the counter FUN_00623530 increments at 0x623561, the GS that holds the +0xad8 flags). Thiscall
    #     this = manager, [esp+4] = &args, ret 4; fild + fstp float32 -> 0x532960 (push number) -> eax = 0x455820 result
    #     count, as get_zoom_step_size 0x53f390. Registered with nargs 0 (the dispatcher 0x533a10 rejects any argument,
    #     like get_camera_zoom), closure vtable 0x8de3b0 {+4 this = esi, +8 method, +0xc 0} -> 0x533bf0(closure, nargs,
    #     name): hook 0x767c1e (the call 0x532740 after the last campaign native, ingresa_recursos_en_jugador_local)
    #     -> call C49R: registers, then jmp 0x532740 (eax for 0x767c23). esi = manager there; ebx/edi untouched.
    # 50) Lua native firma_paz_entre(jugA, jugB) (HIST_PEACE_NATIVE): two player keys ('JUG_RUSIA'); each string arg
    #     (entry type 3, value [[entry]] = char*) is interned (0x530800) and compared with every player's key
    #     (FUN_00635e50, players [mgr+0x2a8] +0x24..+0x28, as FUN_0065ae10) -> id [player+0xf4], else -1 (no-op). Two
    #     different known players -> FUN_00692cc0(diplomacy [mgr+0x298] (registry 0x5de540, = [ui+0xf0] of patch 25);
    #     A, B) ret 8: the game's own peace (only if the two are at war; both ways, map refresh, news), also used by the
    #     universal-peace quest and armistices for AI pairs. nargs 2. Only the Lua events call it (EH_PERMITE_PAZ).
    if HISTORICAL_EVENTS:
        ST48, REG48, LAST48 = 0x942f50, 0x942f54, 0x942f58
        R1, R2, R3, R4, R5 = 0x881150, 0x882098, 0x883678, 0x882b80, 0x882888
        S_HOOK, S_TURNO, S_PAZ = 0x881ae8, 0x8814df, 0x8814f0
        LUA_MGR, LUA_FN, LUA_RUN, LUA_RES = 0x532740, 0x5327d0, 0x5337c0, 0x5007f0
        NEW, REG_FN, PUSH_NUM, N_RES, CLOS_VT = 0x405b12, 0x533bf0, 0x532960, 0x455820, 0x8de3b0
        INICIA = 0x8bacf4                                  # 'inicia_secuencia' (.rdata, used by 0x540de0)
        INTERN_S, RELEASE_S, KEY_OF, PEACE = 0x530800, 0x530890, 0x635e50, 0x692cc0

        def place48(org, end, a):
            code = a.done()
            assert org + len(code) <= end, ('patch 48-50 cave', hex(org), len(code))
            cave_free(org, len(code)); put(org - EXE_BASE, code)
            return a.lab

        def str48(va, end, s):
            bs = s.encode() + b'\0'
            assert va + len(bs) <= end, ('patch 48-50 string', s)
            cave_free(va, len(bs)); put(va - EXE_BASE, bs)
        str48(S_HOOK, 0x881b00, HIST_TURN_HOOK)            # gap 0x881ae8-0x881aff (patch 2's strings at 0x881b00)
        str48(S_TURNO, S_PAZ, 'get_turno_actual')          # gap 0x8814df-0x8814ff (patch 4 at 0x881500)
        if HIST_PEACE_NATIVE:
            str48(S_PAZ, 0x881500, 'firma_paz_entre')
        # R2: LUACALL (eax = name of a Lua global; called without arguments, results dropped), N49
        a = CaveAsm(R2)
        a.mark('luacall')
        a.e('83ec10 50'); a.call(LUA_MGR); a.e('8bc8'); a.call(LUA_FN)       # result buffer; 0x5327d0(name) ret 4
        a.e('54'); a.call(LUA_MGR); a.e('8bc8'); a.call(LUA_RUN)              # 0x5337c0(&result) ret 4 (lua_pcall)
        a.e('8bcc'); a.call(LUA_RES); a.e('83c410 c3')                        # result dtor (thiscall); free buffer
        a.mark('n49')
        a.e('8b81c0020000 8b80d0000000 db8078010000')                         # fild [[[mgr+0x2c0]+0xd0]+0x178]
        a.e('51 d91c24'); a.call(LUA_MGR); a.e('8bc8'); a.call(PUSH_NUM)      # float arg; 0x532960 ret 4
        a.call(LUA_MGR); a.e('8bc8'); a.call(N_RES); a.e('c20400')
        L2 = place48(R2, 0x882100, a)
        LUACALL, N49 = L2['luacall'], L2['n49']
        N50 = None
        if HIST_PEACE_NATIVE:          # R1: pid (ebx = arg entry, ebp = manager) -> eax = player id / -1, then N50
            a = CaveAsm(R1)
            a.mark('pid')
            a.e('83c8ff 837b1003'); a.js('75', 'ret')                         # not a string: -1
            a.e('8b0b ff31'); a.call(INTERN_S); a.e('59 85c0'); a.js('74', 'm1')   # handle (0 -> -1)
            a.e('50 56 6aff 8b8da8020000 8b7124')                             # [esp+8] handle, [esp] result; esi = it
            a.mark('loop')
            a.e('8b8da8020000 3b7128'); a.js('73', 'done')                    # end of the player vector
            a.e('8b0e'); a.call(KEY_OF); a.e('8b542408 3b10'); a.js('74', 'found')
            a.e('83c604'); a.js('eb', 'loop')
            a.mark('found'); a.e('8b0e 8b89f4000000 890c24')                  # result = [player+0xf4]
            a.mark('done'); a.e('58 5e 870424 50'); a.call(RELEASE_S); a.e('59 58')
            a.mark('ret'); a.e('c3')
            a.mark('m1'); a.e('48 c3')
            a.mark('n50')                                                     # thiscall(mgr; &args) ret 4
            a.e('53 56 57 55 8be9 8b442414 8b5804 85db'); a.js('74', 'pz_out')   # ebx = entry 0
            a.jl('e8', 'pid'); a.e('8bf8 83c318'); a.jl('e8', 'pid')          # edi = A, eax = B
            a.e('85ff'); a.js('7c', 'pz_out'); a.e('85c0'); a.js('7c', 'pz_out')
            a.e('3bc7'); a.js('74', 'pz_out')
            a.e('8b8d98020000 50 57'); a.call(PEACE)                          # diplomacy.FUN_00692cc0(A, B) ret 8
            a.mark('pz_out'); a.call(LUA_MGR); a.e('8bc8'); a.call(N_RES)
            a.e('5d 5f 5e 5b c20400')
            N50 = place48(R1, 0x881200, a)['n50']
        # R3: C48B (map UI tick), CL48 (0x541f20 right after a successful script load: LAST48 = that manager)
        a = CaveAsm(R3)
        a.e('8b88d80a0000 c1e90d f6c101'); a.js('74', 'mod')                 # the original 0x2000 test
        a.e('c605'); a.imm(ST48); a.e('00'); a.jmp(0x81d638)                  # tutorial resume: original path only
        a.mark('mod')
        a.e('803d'); a.imm(ST48); a.e('01'); a.js('75', 'out')                # once per new map UI
        a.e('c605'); a.imm(ST48); a.e('00')
        a.e('8b8fc0020000 8b5138 f6421004'); a.js('75', 'out')               # tutorial campaign: left to the game
        a.e('8b11 8d87c4020000 50 ff5228')                                    # registrar(&ui[0x2c4]) ret 4
        a.e('8b8fc0020000 3b0d'); a.imm(REG48); a.js('75', 'out')            # C49R ran for this manager?
        a.e('c605'); a.imm(ST48); a.e('02')
        a.e('b8'); a.imm(INICIA); a.call(LUACALL)                             # Lua inicia_secuencia(), inactive
        a.mark('out'); a.jmp(0x81d65c)
        a.mark('cl48')
        a.e('893d'); a.imm(LAST48); a.e('8b4738 8b4810'); a.jmp(0x541f60)    # + the 2 displaced instructions
        L3 = place48(R3, 0x883700, a)
        C48B, CL48 = R3, L3['cl48']
        # R4: C49R (registration of the new natives; REG48 = manager), REG(func, name, nargs) ret 0xc (esi = manager)
        a = CaveAsm(R4)
        a.e('8935'); a.imm(REG48)                                             # mov [REG48], esi
        a.e('6a00 68'); a.imm(S_TURNO); a.e('68'); a.imm(N49); a.jl('e8', 'reg')
        if HIST_PEACE_NATIVE:
            a.e('6a02 68'); a.imm(S_PAZ); a.e('68'); a.imm(N50); a.jl('e8', 'reg')
        a.jmp(LUA_MGR)                                                        # eax = Lua manager for 0x767c23
        a.mark('reg')
        a.e('6a10'); a.call(NEW); a.e('59 85c0'); a.js('74', 'z')            # closure (0x10 bytes)
        a.e('c700'); a.imm(CLOS_VT); a.e('897004 8b4c2404 894808 83600c00')
        a.mark('z'); a.e('ff742408 ff742410 50'); a.call(LUA_MGR); a.e('8bc8'); a.call(REG_FN)   # (closure, nargs, name)
        a.e('c20c00')
        place48(R4, 0x882c00, a)
        C49R = R4
        # R5: C48A (new manager), C48D (begin of the human turn)
        a = CaveAsm(R5)
        a.e('8986c0020000 c605'); a.imm(ST48); a.e('01 8325'); a.imm(REG48); a.e('00 c3')   # store; pending; REG48 = 0
        a.mark('c48d')
        a.e('8b11 ff5250 84c0'); a.js('74', 'inact'); a.jmp(0x82a0ec)        # active: the original post
        a.mark('inact')
        a.e('803d'); a.imm(ST48); a.e('02'); a.js('75', 'back')
        a.e('8b8ec0020000 3b0d'); a.imm(LAST48); a.js('75', 'rebind')        # another sequence re-bound the natives
        a.e('3b0d'); a.imm(REG48); a.js('74', 'go')
        a.mark('rebind'); a.e('8b11 8d86c4020000 50 ff5228')                 # registrar again (forced reload)
        a.e('8b8ec0020000 3b0d'); a.imm(LAST48); a.js('75', 'back')
        a.e('3b0d'); a.imm(REG48); a.js('75', 'back')
        a.mark('go'); a.e('b8'); a.imm(S_HOOK); a.call(LUACALL)               # Lua HIST_TURN_HOOK()
        a.mark('back'); a.jmp(0x82a150)
        L5 = place48(R5, 0x882900, a)
        C48A, C48D = R5, L5['c48d']
        # hooks
        put(0x826a17 - EXE_BASE, b'\xe8' + struct.pack('<i', C48A - (0x826a17 + 5)) + h('90'), h('8986c0020000'))
        put(0x81d62a - EXE_BASE, jmp(0x81d62a, C48B) + h('90') * 9, h('8b88d80a0000 c1e90d f6c101 7424'))
        put(0x82a0e3 - EXE_BASE, jmp(0x82a0e3, C48D) + h('90') * 4, h('8b11 ff5250 84c0 7464'))
        put(0x541f41 - EXE_BASE, h('6a01'), h('6a00'))                       # force = 1 (d)
        put(0x541f5a - EXE_BASE, jmp(0x541f5a, CL48) + h('90'), h('8b4738 8b4810'))
        put(0x767c1e - EXE_BASE, b'\xe8' + struct.pack('<i', C49R - (0x767c1e + 5)), h('e81dabdcff'))

    # 51) START CAMERA ON THE CAPITAL (CAPITAL_START_CAMERA). FUN_00623150 (AI_GESTION_CONTROL_BASE_PROC, state after
    #     the map is up): with .CAMARA_INICIAL TRUE (ModeloGestion.sb, flag [esi+0x348]) and a new campaign (bit 2 of
    #     [[esi+0x274]+0x10] clear) it compares the human's key (FUN_00635e50) with JUG_GRAN_BRETANYA, _FRANCIA, _AUSTRIA,
    #     _PRUSIA, _RUSIA and plays Gestion/Camaras/Camara<x>.V3D (FUN_0065f4d0); any other nation falls through to
    #     0x623397 (intro speech) with NO camera set, so it starts on a fixed default spot (seen 2026-10-23: Ottoman,
    #     Arabia, Persia, Ethiopia, Kazakhs, Turkestan, Japan over fog, east of their land). The flag-off / loaded-game
    #     path at 0x623370 centres on the capital: player (eax) -> FUN_00634430 (capital id, [country+0x408]) ->
    #     map [esi+0x25c].FUN_0065e1d0 -> FUN_0065e8b0(pos, 0); then 'test bl,bl / jne 0x6233e2' (bl = 0 here) and on
    #     into 0x623397, the same tail as before.
    #       hook 0x623349  call 0x402fe0; test bl,bl; je 0x623397 (9 bytes) -> jmp C51 + 4 nops
    #       C51 (0x883d00, int3 gap 0x883cdd-0x883d3f after patch 21's core, before patch 27 at 0x883d40):
    #            call 0x402fe0 (the JUG_RUSIA string release, ecx = &local as set at 0x62333e); test bl,bl;
    #            jne 0x623352 (Russia: its flight, unchanged); else player = FUN_0065ae90([esi+0x24c];
    #            FUN_0065ae50([esi+0x24c])) (pure lookups: the human's id, then its player, as at 0x6231de) and
    #            jmp 0x623370 (eax = player, bl = 0).
    #     ebx is callee-saved across 0x402fe0 (the original tests bl after it); the stack is at the function's base level at
    #     both 0x623349 and 0x623370. No branch or pointer lands inside 0x62334a-0x623351 (byte scan of .text). Only the
    #     new-campaign start of the other nations changes; save-safe. Statically verified (capstone); not tested in game.
    if CAPITAL_START_CAMERA:
        C51 = 0x883d00
        a = CaveAsm(C51)
        a.call(0x402fe0)                                   # release the interned 'JUG_RUSIA' (thiscall, ecx = &local)
        a.e('84db'); a.e('0f85'); a.b += struct.pack('<i', 0x623352 - (a.here() + 4))   # Russia -> its intro flight
        a.e('8b8e4c020000'); a.call(0x65ae50)              # eax = id of the human player
        a.e('8b8e4c020000 50'); a.call(0x65ae90)           # eax = that player (ret 4)
        a.jmp(0x623370)                                    # the original capital focus, then the intro speech
        code = a.done()
        assert C51 + len(code) <= 0x883d40, 'patch 51 cave reaches patch 27'
        cave_free(C51, len(code)); put(C51 - EXE_BASE, code)
        put(0x623349 - EXE_BASE, jmp(0x623349, C51) + h('90') * 4, h('e892fcddff 84db 7445'))
    open(dst_path, 'wb').write(d)
    return changes
