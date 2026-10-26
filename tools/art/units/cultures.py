"""Per-nation unit textures, officer figures, ship ensigns and per-culture unit files for the 1789 world map.

Everything is derived from the game's own paintings: a recipe per nation gives the colours of coat, skirt, trousers,
sash, headgear, skin and an optional insignia/pattern; retex.py recolours the template nation's textures island by
island (UV islands of the shared models), keeping the painted shading.  Nothing is installed here: build_all()
writes a tree that mirrors the game paths under an output root, and make_map.py copies it into the mod.

    python tools/art/units/cultures.py [out_root]      # default build/units/out, plus build/units/all_cultures.png

Exports for tools/nations.py / make_map.py:
    UNIT_FILE_OF   {country key: 'DefUnidadesAsia.sb' | 'DefUnidadesIndia.sb' | 'DefUnidadesAfrica.sb' |
                    'DefUnidadesPacific.sb' | 'DefUnidadesCaucaso.sb' | 'DefUnidadesOriente.sb' | 'DefUnidadesArabes.sb' |
                    'DefUnidadesStandard.sb' | 'DefUnidadesJapon.sb' | 'DefUnidadesQing.sb' | 'DefUnidadesReinos.sb' |
                    'DefUnidadesKazajo.sb' | 'DefUnidadesSahel.sb' | 'DefUnidadesSur.sb'}
    SIGNATURE      {country key: (troop type, recipe)} the signature elite units' uniforms
    build_all(out_root, nations=None) -> list of written files (relative to out_root)
"""
import math, os, re, struct, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.abspath(os.path.join(HERE, '..', '..'))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE); sys.path.insert(0, TOOLS)
import retex as R
import uvdump
import tga as TGA
import nations as NT          # also installs world_nations into flags.DESIGNS
import flags as FL

DATA = os.path.join(ROOT, 'data')
BASE = os.path.join(DATA, 'Models', '00EjercitoBase')
FIG = os.path.join(DATA, 'Game', 'GameModes', 'Gestion', 'Figuras')
BAT = os.path.join(DATA, 'Game', 'GameModes', 'Batalla')
FONT_CJK = r'C:\Windows\Fonts\YuGothB.ttc'
S = 256

# ------------------------------------------------------------------ models behind each texture name
INF = os.path.join(BASE, 'Infanteria'); CAB = os.path.join(BASE, 'Caballeria')
def _m(d, n):
    return os.path.join(d, n, n + '.V3D')
# Arab-culture sets (Otomano/Egipto/Marruecos/Tunez/Tripolitania folders)
ARAB_TEX = {'Infanteria/Fusilero': _m(INF, 'GenericoA3'), 'Infanteria/Miliciano': _m(INF, 'GenericoH2'),
            'Infanteria/Tirador': _m(INF, 'GenericoA4'), 'Caballeria/Husar': _m(CAB, 'GenericoE2'),
            'Caballeria/Lancero': _m(CAB, 'GenericoG2'), 'Caballeria/LanceroCam': _m(CAB, 'GenericoG3'),
            'Caballeria/TiradorCam': _m(CAB, 'GenericoA4'), 'Caballeria/Mameluko': _m(CAB, 'GenericoD4')}
# Standard set (the European minors)
STD_TEX = {'Infanteria/Fusilero': _m(INF, 'GenericoA'), 'Infanteria/Tirador': _m(INF, 'GenericoA'),
           'Infanteria/Cazador': _m(INF, 'GenericoA'), 'Infanteria/Granadero': _m(INF, 'GenericoB'),
           'Infanteria/Elite': _m(INF, 'GenericoD'), 'Infanteria/Miliciano': _m(INF, 'GenericoH'),
           'Caballeria/Husar': _m(CAB, 'GenericoE'), 'Caballeria/Dragon': _m(CAB, 'GenericoF'),
           'Caballeria/Lancero': _m(CAB, 'GenericoG'), 'Caballeria/CCoracero': _m(CAB, 'GenericoC')}
# paintings of the extra troop types (tools/nations.py EXTRA_TROOPS) that a template folder lacks: the folder they are
# taken from (riders recoloured to the recipe, mounts copied). Portugal's dark coats take the dark recipes best;
# Denmark's dragoon horse has the crimson shabraque; the Mameluke is Egypt's.
EXTRA_TEX_SRC = {'Infanteria/Cazador': '12Portugal', 'Infanteria/Granadero': '12Portugal', 'Infanteria/Elite': '12Portugal',
                 'Caballeria/Dragon': '12Portugal', 'Caballeria/DragonCaballo': '10Dinamarca',
                 'Caballeria/CCoracero': '12Portugal', 'Caballeria/CCoraceroCaballo': '12Portugal',
                 'Caballeria/Mameluko': '08Egipto', 'Caballeria/MamelukoCaballo': '08Egipto'}
KEEP_METAL = {'Caballeria/CCoracero'}    # the cuirass keeps its steel (not taken for a light sash / belt)
MOUNT_OF = {'Caballeria/Husar': 'Caballeria/HusarCaballo', 'Caballeria/Lancero': 'Caballeria/LanceroCaballo',
            'Caballeria/LanceroCam': 'Caballeria/LanceroCamCamello', 'Caballeria/TiradorCam': 'Caballeria/TiradorCamCamello',
            'Caballeria/Mameluko': 'Caballeria/MamelukoCaballo', 'Caballeria/Dragon': 'Caballeria/DragonCaballo',
            'Caballeria/CCoracero': 'Caballeria/CCoraceroCaballo'}
# insignia anchors (texture px) per model: (front chest, back) - see build/units/probe_A3_torso.png
INSIGNIA_AT = {'GenericoA3': ((76, 212, 11), (50, 150, 13))}

# ------------------------------------------------------------------ colours
W = (232, 226, 212); BLK = (44, 44, 56); IND = (40, 50, 100); RED = (176, 38, 36); SAF = (228, 124, 30)
GOLD = (206, 164, 60); DKB = (30, 34, 58); WHT = (238, 234, 224); BRN = (96, 64, 40); OCH = (172, 118, 56)
SK_ASIA = (222, 188, 152); SK_SEA = (190, 148, 108); SK_IND = (150, 102, 62); SK_AFR = (84, 54, 34)
SK_SAHEL = (112, 72, 44); SK_PAC = (120, 82, 52); SK_ARAB = (168, 122, 86)
JP_INDIGO = (44, 54, 92); JP_HAKAMA = (78, 82, 96); JP_RED = (168, 40, 36); JP_LACQUER = (30, 28, 32)
QG_RED = (150, 42, 36); QG_BLUE = (48, 62, 122); QG_NAVY = (48, 52, 74); QG_WHITE = (214, 208, 192); QG_YELLOW = (206, 166, 58)
# Eastern Kingdoms (Joseon, Siam, Burma, Vietnam): madder red, Joseon blue, gold silk, undyed white hemp, black hats
EK_RED = (152, 44, 36); EK_BLUE = (50, 64, 118); EK_GOLD = (204, 158, 58); EK_CREAM = (224, 216, 194); EK_BLACK = (30, 28, 32)
# Southern Kingdoms (Nguni, Sotho-Tswana, Rozvi): tanned hide, dark hide, red beadwork, cowhide and leopard skins
SA_HIDE = (150, 104, 62); SA_DARK = (74, 52, 36); SA_RED = (170, 48, 36); SA_FUR = (40, 32, 28)
SA_COW = ('spots', (228, 220, 202), (72, 48, 32), 5.0, 0.36); SA_LEO = ('spots', (198, 152, 72), (44, 32, 22), 1.6, 0.26)


def _st(coat, skirt=None, trousers=None, sash=W, hat=None, hat_top=None, skin=None, face=None, insignia=None,
        pattern=None, skirt_pattern=None, disc=None, units='DefUnidadesArabes.sb', coat_contrast=1.1, sash_split=None,
        crown=None, card_skin=None, arms=None):
    """sash_split: None = belts / sash split off the coat when the coat is dark (the default rule in retex),
    False = never (a light shirt under a dark coat, e.g. the Spanish guerrilla body, stays part of the coat).
    face: 'asian' = clean-shaven lighter face (beard pulled to the skin); None with skin = skin retinted, hair kept.
    crown: colour of the HAT_BOX region (the hat's crown) instead of the hat colour.
    pattern: stripes (colours, period, angle) or a hide ('spots', base, spot colour, blotch size px, spot share).
    card_skin: True = the unit cards and portraits retint the painting's skin to `skin` too (painted.py).
    arms: colour of the sleeves (default the coat; the skin colour = bare arms under a cape)."""
    return dict(coat=coat, skirt=skirt or coat, trousers=trousers or coat, sash=sash, hat=hat or coat,
                hat_top=hat_top or hat or coat, skin=skin, face=face, insignia=insignia, pattern=pattern,
                skirt_pattern=skirt_pattern, disc=disc or sash, units=units, coat_contrast=coat_contrast,
                sash_split=sash_split, crown=crown, card_skin=card_skin, arms=arms)


def _stripes(cols, period, angle):
    return (cols, period, angle)


ASIA, INDIA, AFRICA, PACIFIC, ARAB, STD = ('DefUnidadesAsia.sb', 'DefUnidadesIndia.sb', 'DefUnidadesAfrica.sb',
                                            'DefUnidadesPacific.sb', 'DefUnidadesArabes.sb', 'DefUnidadesStandard.sb')
# the Arab file, but the elite horse on the Mameluke body: the Arab/Standard files point CAB_ELITE to
# Models\00EjercitoBase\Caballeria\Elite\, which the game does not have (only Egypt and Poland own that troop)
CAUCASUS = 'DefUnidadesCaucaso.sb'
# Persia, Arabia, Turkestan: the Arab file (camels kept) with working elite blocks for their signature units:
# ELITE on the Arab marksman body (GenericoA4), CAB_ELITE on the Mameluke body (GenericoD4), own textures
ORIENTE = 'DefUnidadesOriente.sb'
# Japan: its own file on the bodies without turbans (2026-10-21, user: "Japan's troops look Arabic"): musket infantry
# and the Hatamoto on the Spanish guerrilla body (GenericoD3: head cloth, jacket, breeches), the militia on the
# European militia body (GenericoH: bare head), the horse on the Mameluke body (GenericoD4: a round brimmed hat, read
# as a lacquered jingasa), the lancers on the Arab lancer body (GenericoG2: the hood, black, read as kabuto and neck
# guard), the gun crews (Artillero, a GenericoA layout) on a texture of their own. Textures: OWN_TEX.
JAPON = 'DefUnidadesJapon.sb'
# Qing China (2026-10-21, the same follow-up): Green Standard musketeers and the banner Firearms Division on the
# guerrilla body (head cloth) with the round soldier's badge (bing) on chest and back, braves (yong) on the militia
# body, horse on the Arab hussar body (its hat, black with a red top, reads as the Qing hat), lancers on the Arab
# lancer body (helmet with neck guard, the round rattan shield), the Manchu Bannermen on the Mameluke body (the round
# Qing winter hat, red crown), gun crews on their own texture. Banner colours per troop (TROOP_RECIPES, SIGNATURE).
QING_FILE = 'DefUnidadesQing.sb'
# the Eastern Kingdoms (INDEPENDENT: Joseon, Siam, Burma, Vietnam, Malaya; 2026-10-21, user: "they still have the Arab
# look"): one coherent style apart from Qing and Japan - light hemp trousers and coloured head cloths (gold, red) on the
# guerrilla body instead of their dark ones, white-clad levy (militia body), Joseon horse on the Mameluke body (its round
# brimmed hat black, read as the gat / jeonrip, red top), lancers on the Arab lancer body (black or gilt helmet). The
# camel types ride horses (CAM_TIRADOR on the Mameluke body, CAM_LANCERO on the lancer body: texts unchanged).
EASTERN = 'DefUnidadesReinos.sb'
# Kazakh Khanate (HANNOVER) and Sahel Kingdoms (SAJONIA): the Arab file with the three European-bodied troops moved to
# steppe / Sahel bodies (2026-10-21): GRANADERO on the long-robed marksman body (GenericoA4), CAB_DRAGON on the Mameluke
# body (GenericoD4), CAB_CORACERO on the Arab lancer body (GenericoG2: helmet with neck guard, round shield). Their other
# troops keep the template textures as before (OWN_ADDS).
KAZAKH_FILE = 'DefUnidadesKazajo.sb'
SAHEL_FILE = 'DefUnidadesSahel.sb'
# Southern Kingdoms (MOLDAVIA; was the European Standard file): hide-clad musketeers on the guerrilla body (tanned hide,
# cowhide, leopard skin; dark fur head bands), the militia body with its club (a knobkerrie), horse on the Arab hussar
# (fur cap, white plume), Mameluke (brimmed hat: the frontier horsemen) and lancer bodies (shield and spear)
SOUTH_FILE = 'DefUnidadesSur.sb'

RECIPES = {
    # --- East Asia (Asia unit file: no camels, D4 'Mameluke' body for the elite horse)
    # Green Standard musketeers: red padded jacket with the white bing (soldier) badge, dark blue border and trousers,
    # black head cloth. The other troops: TROOP_RECIPES (banner colours); the Manchu Bannermen: SIGNATURE
    'QING': _st(QG_RED, trousers=QG_NAVY, sash=QG_BLUE, hat=(32, 32, 38), skin=SK_ASIA, face='asian',
                insignia=('glyph', '\u5175', WHT, (20, 20, 24), QG_BLUE), units=QING_FILE, sash_split=False),
    # Tokugawa ashigaru musketeers (teppo-gumi): indigo jacket with the white clan mon on chest and back, grey-indigo
    # hakama, dark head cloth, red sash (the sashimono colour). The other troops: TROOP_RECIPES; the Hatamoto: SIGNATURE
    'JAPAN': _st(JP_INDIGO, trousers=JP_HAKAMA, sash=JP_RED, hat=(34, 36, 46), skin=SK_ASIA, face='asian',
                 insignia=('mon', WHT, None), units=JAPON, sash_split=False),
    'JOSEON': _st((62, 78, 136), trousers=WHT, sash=(190, 40, 40), hat=BLK, hat_top=(190, 40, 40), skin=SK_ASIA, face='asian',
                  insignia=('disc', (190, 40, 40), (20, 20, 24)), units=ASIA),
    'VIETNAM': _st((156, 46, 36), trousers=(130, 120, 106), sash=GOLD, hat=(96, 58, 34), skin=SK_SEA, face='asian', units=ASIA),
    'NGUYEN': _st((206, 162, 44), trousers=(110, 100, 94), sash=RED, hat=BLK, skin=SK_SEA, face='asian', units=ASIA),
    # --- South-East Asia (Asia file)
    'BURMA': _st((160, 48, 34), skirt=(196, 156, 40), trousers=(196, 156, 40), sash=WHT, hat=(190, 40, 40), skin=SK_SEA,
                 face='asian', units=ASIA),
    'SIAM': _st((190, 40, 40), skirt=IND, trousers=IND, sash=WHT, hat=BLK, skin=SK_SEA, face='asian', units=ASIA),
    'MALAYA': _st((64, 64, 100), skirt=(140, 50, 96), trousers=(64, 64, 100), sash=GOLD, hat=(64, 64, 100), skin=SK_SEA, face='asian',
                  skirt_pattern=_stripes([(120, 40, 80), (120, 40, 80), GOLD], 5, 0.0), units=ASIA),
    'BRUNEI': _st((200, 150, 40), skirt=(64, 64, 100), trousers=(64, 64, 100), sash=RED, hat=(160, 120, 30), skin=SK_SEA,
                  face='asian', units=ASIA),
    # --- India (India file: Mameluke-body hussar, camels kept)
    'MARATHA': _st(SAF, skirt=(228, 216, 190), trousers=(228, 216, 190), sash=WHT, hat=SAF, skin=SK_IND, units=INDIA),
    'MYSORE': _st((210, 148, 44), skirt=(210, 148, 44), trousers=WHT, sash=WHT, hat=(190, 40, 40), skin=SK_IND,
                  pattern=_stripes([(200, 140, 40)] * 3 + [(40, 30, 20)], 5, 0.6), units=INDIA),
    'HYDERABAD': _st((208, 176, 60), skirt=(60, 110, 70), trousers=WHT, sash=(60, 110, 70), hat=WHT, skin=SK_IND, units=INDIA),
    'PUNJAB': _st((40, 60, 130), trousers=(228, 216, 190), sash=SAF, hat=SAF, skin=SK_IND, units=INDIA),
    'NEPAL': _st((150, 40, 40), trousers=WHT, sash=WHT, hat=BLK, skin=SK_IND, units=INDIA),
    'TRAVANCORE': _st((200, 40, 40), trousers=WHT, sash=WHT, hat=WHT, skin=(120, 75, 45), units=INDIA),
    'AHOM': _st((170, 110, 40), trousers=WHT, sash=(200, 40, 40), hat=WHT, skin=SK_IND, units=INDIA),
    # --- Central / West Asia and Arabia (Arab file, recolours)
    'DURRANI': _st((124, 104, 84), skirt=(150, 130, 108), trousers=(200, 190, 170), sash=RED, hat=WHT, skin=SK_ARAB),
    'PERSIA': _st((160, 36, 46), skirt=(60, 68, 120), trousers=(60, 68, 120), sash=GOLD, hat=(60, 48, 44), skin=SK_ARAB,
                  units=ORIENTE),
    'TURKESTAN': _st((40, 90, 120), trousers=(200, 190, 170), sash=RED, hat=WHT, skin=SK_ARAB,
                     pattern=_stripes([(40, 90, 120), (40, 90, 120), (170, 120, 40)], 6, 1.5708), units=ORIENTE),
    'KAZAKHSTAN': _st((140, 94, 56), trousers=(110, 90, 70), sash=RED, hat=(200, 190, 170), hat_top=(60, 50, 40), skin=SK_ARAB,
                      units=KAZAKH_FILE),
    'SAHARA': _st((56, 64, 130), sash=WHT, hat=(40, 45, 90), skin=SK_SAHEL),
    'ARABIA': _st(WHT, sash=(120, 80, 40), hat=WHT, skin=SK_ARAB, units=ORIENTE),
    'OMAN': _st(WHT, sash=(150, 40, 40), hat=(200, 60, 30), skin=SK_ARAB),
    'YEMEN': _st((60, 70, 110), trousers=WHT, sash=GOLD, hat=WHT, skin=SK_ARAB),
    # --- Africa (Africa file: no camels; the Sahel keeps the Arab file with camels)
    'ETHIOPIA': _st(WHT, sash=(200, 40, 40), hat=WHT, skin=(90, 60, 40), units=AFRICA),
    'SENNAR': _st(WHT, sash=(40, 40, 40), hat=WHT, skin=SK_SAHEL),
    'DARFUR': _st((200, 170, 120), sash=(120, 40, 40), hat=WHT, skin=SK_SAHEL),
    'BORNU': _st(IND, skirt=WHT, trousers=WHT, sash=GOLD, hat=WHT, skin=SK_SAHEL),
    'SEGU': _st(OCH, trousers=(200, 180, 140), sash=WHT, hat=(60, 40, 30), skin=SK_AFR,
                pattern=_stripes([OCH, OCH, (60, 40, 30)], 4, 0.8), units=AFRICA),
    'ASHANTI': _st(GOLD, trousers=(190, 150, 70), sash=WHT, hat=(26, 22, 20), hat_top=(150, 40, 30), skin=(92, 58, 36),
                   pattern=_stripes([GOLD, GOLD, (30, 90, 50), (190, 40, 30), GOLD, (20, 20, 20)], 4, 0.3), units=AFRICA),
    'OYO': _st((190, 60, 40), skirt=WHT, trousers=WHT, sash=IND, hat=IND, skin=(75, 50, 32), units=AFRICA),
    'KONGO': _st((220, 210, 190), trousers=(160, 110, 56), sash=RED, hat=(40, 30, 20), skin=SK_AFR,
                 pattern=_stripes([(220, 210, 190), (220, 210, 190), (120, 80, 40)], 4, 0.0), units=AFRICA),
    'LUNDA': _st((170, 50, 50), trousers=(170, 130, 80), sash=WHT, hat=(40, 30, 20), skin=SK_AFR, units=AFRICA),
    'BUGANDA': _st((190, 150, 90), sash=(150, 40, 40), hat=(40, 30, 20), skin=SK_AFR, units=AFRICA),
    'ROZVI': _st((120, 78, 44), trousers=(180, 140, 90), sash=GOLD, hat=(40, 30, 20), skin=SK_AFR, units=AFRICA),
    'MADAGASCAR': _st(WHT, sash=(200, 40, 40), hat=(40, 30, 20), skin=(110, 75, 50),
                      pattern=_stripes([WHT, WHT, (200, 40, 40)], 6, 0.0), units=AFRICA),
    'FUTA': _st(WHT, sash=IND, hat=WHT, skin=SK_SAHEL, units=AFRICA),
    'MOSSI': _st(IND, trousers=WHT, sash=RED, hat=(200, 40, 40), skin=SK_AFR,
                 pattern=_stripes([IND, IND, WHT], 5, 0.0), units=AFRICA),
    'NGUNI': _st((150, 104, 62), sash=WHT, hat=(40, 30, 20), hat_top=(200, 40, 40), skin=SK_AFR, units=AFRICA),
    'BECHUANA': _st((150, 110, 70), sash=GOLD, hat=(40, 30, 20), skin=SK_SAHEL, units=AFRICA),
    # --- Pacific (Pacific file: no camels, no Mameluke body)
    'MAORI': _st((140, 96, 48), trousers=(170, 130, 80), sash=(40, 30, 20), hat=(40, 30, 20), hat_top=(200, 40, 40), skin=SK_PAC,
                 pattern=_stripes([(120, 80, 40), (120, 80, 40), (40, 30, 20)], 3, 1.5708), units=PACIFIC),
    'ABORIGINES': _st((150, 100, 60), trousers=(190, 150, 100), sash=WHT, hat=(40, 30, 20), skin=SK_AFR, units=PACIFIC),
    'PAPUA': _st((130, 86, 50), sash=(200, 40, 40), hat=(200, 40, 40), hat_top=(230, 200, 60), skin=SK_AFR, units=PACIFIC),
    # --- Caucasus: Sheikh Mansur's mountaineers (cherkeska with gazyri, papakha)
    'CHECHNYA': _st((64, 58, 54), trousers=(66, 62, 64), sash=(176, 38, 36), hat=(52, 44, 40), hat_top=(52, 44, 40),
                    skin=(196, 154, 122), insignia=('gazyri', (222, 218, 206), (60, 50, 44)), coat_contrast=1.0,
                    units=CAUCASUS),
    # --- merged small realms: neutral, undyed cloth
    # INDEPENDENT holds the Eastern Kingdoms (Korea, Burma, Siam, Vietnam, Malaya, Brunei): its own file (EASTERN), the
    # cloned CAM_* records (template Morocco; ids kept for save games) ride horses (review V2, 2026-10-21).
    # Musketeers: madder-red jacket, white hemp trousers, gold sash, Joseon-blue head cloth. Others: TROOP_RECIPES
    'INDEPENDENT': _st(EK_RED, trousers=EK_CREAM, sash=EK_GOLD, hat=EK_BLUE, skin=SK_SEA, face='asian', units=EASTERN,
                       sash_split=False),
    # the other regions of the independent peoples (tools/world_nations.REGIONS): same undyed cloth, regional unit sets
    'PRINCES': _st((154, 142, 120), trousers=(196, 186, 166), sash=WHT, hat=(128, 116, 98), skin=SK_IND, units=INDIA),
    'SHEIKHS': _st((154, 142, 120), trousers=(196, 186, 166), sash=WHT, hat=(128, 116, 98), skin=SK_ARAB),
    'NILE': _st((154, 142, 120), trousers=(196, 186, 166), sash=WHT, hat=(128, 116, 98), skin=SK_AFR, units=AFRICA),
    'PACIFIC': _st((154, 142, 120), trousers=(196, 186, 166), sash=WHT, hat=(128, 116, 98), skin=SK_PAC, units=PACIFIC),
    'IND_SAHEL': _st((154, 142, 120), trousers=(196, 186, 166), sash=WHT, hat=(128, 116, 98), skin=SK_SAHEL, units=SAHEL_FILE),
    # Southern Kingdoms musketeers: cowhide cape over bare arms and legs, red beadwork belt, leopard-skin head band
    # (umqhele). Others: TROOP_RECIPES
    'IND_SOUTH': _st((228, 220, 202), trousers=SK_AFR, sash=SA_RED, hat=(198, 152, 72), skin=SK_AFR, pattern=SA_COW,
                     arms=SK_AFR, units=SOUTH_FILE, sash_split=False, card_skin=True),
    # --- reskin on the European set
    'SIBERIA': _st((70, 100, 70), trousers=(200, 196, 190), sash=WHT, hat=BLK, units=STD),
}

# reskins: country key -> (design/recipe key, model folder, figure folder, template models folder)
RESKINS = {'MOLDAVIA': ('IND_SOUTH', '21Moldavia', '21Moldavia', '21Moldavia'),
           'SAJONIA': ('IND_SAHEL', '19Sajonia', '19Sajonia', '22Marruecos'),
           'HANNOVER': ('KAZAKHSTAN', '17Hannover', '17Hanover', '22Marruecos')}

# signature elite units of the new great powers (tools/nations.py EXTRA_TROOPS / EXTRA_TROOP_TEXT, 2026-10-21):
# country -> (troop type, the elite's own uniform recipe), applied to the textures of that troop's block in the
# nation's unit file. Muted, painted colours like the line troops, but a clearly different livery.
SIGNATURE = {
    # Manchu Bannermen: the Plain Yellow Banner (Upper Three Banners), dark blue trim, black hat with red crest
    # (2026-10-21: on the Mameluke body, the round winter hat black with the red crown; crown = HAT_BOX colour)
    'QING': ('CAB_ELITE', _st(QG_YELLOW, trousers=(60, 64, 96), sash=(52, 60, 110), hat=BLK, hat_top=(190, 40, 40),
                              skin=SK_ASIA, face='asian', units=QING_FILE, crown=(176, 38, 36))),
    # Hatamoto Samurai: black haori, dark red hakama, gold mon on chest and back, black head cloth, gold sash
    'JAPAN': ('ELITE', _st((38, 36, 42), trousers=(120, 36, 32), sash=GOLD, hat=(26, 26, 30), skin=SK_ASIA, face='asian',
                           insignia=('mon', GOLD, None), units=JAPON, sash_split=False)),
    # Huzurat Horse: crimson coat, cream jama, gold sash, saffron turban
    'MARATHA': ('CAB_ELITE', _st((132, 30, 40), skirt=(228, 216, 190), trousers=(228, 216, 190), sash=GOLD, hat=SAF,
                                 skin=SK_IND, units=INDIA)),
    # Jazayerchi Musketeers: dark blue coat over red, gold sash, black lambskin kolah
    'PERSIA': ('ELITE', _st((42, 54, 106), skirt=(150, 32, 40), trousers=(150, 32, 40), sash=GOLD, hat=(36, 30, 30),
                            skin=SK_ARAB, units=ORIENTE)),
    # Oromo Horsemen: tawny cape, white trousers, red sash, dark hair
    'ETHIOPIA': ('CAB_ELITE', _st((170, 120, 58), trousers=WHT, sash=(190, 40, 40), hat=(52, 40, 30), skin=(90, 60, 40),
                                  units=AFRICA)),
    # Najdi Horsemen: dark brown bisht over the white thobe, gold sash, white headcloth
    'ARABIA': ('CAB_ELITE', _st((86, 60, 40), skirt=WHT, trousers=WHT, sash=GOLD, hat=WHT, skin=SK_ARAB, units=ORIENTE)),
    # Turkmen Horse: crimson khalat, dark trousers, black sheepskin telpek
    'TURKESTAN': ('CAB_ELITE', _st((140, 34, 34), trousers=(70, 56, 46), sash=GOLD, hat=(40, 34, 32), skin=SK_ARAB,
                                   units=ORIENTE)),
}
# other troops with a uniform of their own (units and cards): (country, troop) -> recipe. 'ARTILLERO' = the gun crews
TROOP_RECIPES = {
    # teppo marksmen in brown (cha), indigo hakama
    ('JAPAN', 'TIRADOR'): _st((90, 66, 46), trousers=(58, 62, 80), sash=JP_RED, hat=JP_LACQUER, skin=SK_ASIA, face='asian',
                              insignia=('mon', WHT, None), units=JAPON, sash_split=False),
    # peasant levy: faded indigo cotton, undyed trousers, straw-coloured straps, bare black hair
    ('JAPAN', 'MILICIA'): _st((72, 86, 114), trousers=(100, 88, 70), sash=(196, 186, 156), hat=(30, 28, 30), skin=SK_ASIA,
                              units=JAPON),
    # mounted samurai: indigo, cream under-sleeves, black lacquered jingasa with a gold top
    ('JAPAN', 'CAB_HUSAR'): _st(JP_INDIGO, trousers=JP_HAKAMA, sash=(196, 190, 172), hat=JP_LACQUER, hat_top=GOLD,
                                skin=SK_ASIA, face='asian', insignia=('mon', WHT, None), units=JAPON),
    # yari horsemen: red-laced armour colour, black lacquered helmet and neck guard
    ('JAPAN', 'CAB_LANCERO'): _st((88, 34, 32), trousers=JP_HAKAMA, sash=GOLD, hat=JP_LACQUER, skin=SK_ASIA,
                                  face='asian', insignia=('mon', GOLD, None), units=JAPON),
    # gunners: indigo, black lacquered hat with a gold front, plain straps
    ('JAPAN', 'ARTILLERO'): _st(JP_INDIGO, trousers=(64, 68, 84), sash=(120, 110, 96), hat=JP_LACQUER, hat_top=GOLD,
                                skin=SK_ASIA, face='asian', insignia=('mon', WHT, None), units=JAPON),
    # Qing (the Eight Banners' colours): banner Firearms Division musketeers in Plain Blue, white bing badge
    ('QING', 'TIRADOR'): _st(QG_BLUE, trousers=QG_NAVY, sash=QG_RED, hat=(32, 32, 38), skin=SK_ASIA, face='asian',
                             insignia=('glyph', '兵', WHT, (20, 20, 24), QG_RED), units=QING_FILE, sash_split=False),
    # braves (yong): faded blue cotton, undyed trousers, the yong badge, bare black hair
    ('QING', 'MILICIA'): _st((64, 76, 104), trousers=(100, 88, 70), sash=(196, 186, 156), hat=(30, 28, 30), skin=SK_ASIA,
                             insignia=('glyph', '勇', WHT, (20, 20, 24), (150, 42, 36)), units=QING_FILE),
    # Bordered White horse: white coat with red trim, black hat with the red top
    # (disc: the red-painted parts of the Ottoman textures - the hussar's sabre, the lancer's robe)
    ('QING', 'CAB_HUSAR'): _st(QG_WHITE, trousers=QG_NAVY, sash=QG_RED, hat=BLK, hat_top=(176, 38, 36), skin=SK_ASIA,
                               face='asian', units=QING_FILE, sash_split=False, disc=(140, 140, 146)),
    # Plain Red lancers: red coat and rattan shield, black helmet with neck guard
    ('QING', 'CAB_LANCERO'): _st(QG_RED, trousers=QG_NAVY, sash=GOLD, hat=BLK, skin=SK_ASIA, face='asian', units=QING_FILE,
                                 sash_split=False, disc=QG_RED),
    # Hanjun banner gunners in Plain White, black hat with the red top, the bing badge
    ('QING', 'ARTILLERO'): _st(QG_WHITE, trousers=QG_NAVY, sash=QG_RED, hat=BLK, hat_top=(176, 38, 36), skin=SK_ASIA,
                               face='asian', insignia=('glyph', '兵', WHT, (20, 20, 24), QG_RED), units=QING_FILE,
                               sash_split=False),
    # Eastern Kingdoms (EASTERN). Marksmen: Joseon blue jacket, white hemp trousers, red sash and red head cloth
    ('INDEPENDENT', 'TIRADOR'): _st(EK_BLUE, trousers=EK_CREAM, sash=EK_RED, hat=EK_RED, skin=SK_SEA, face='asian',
                                    units=EASTERN, sash_split=False),
    # levy in undyed white hemp (the 'white-clad' commoners), straw-coloured straps, bare black hair
    ('INDEPENDENT', 'MILICIA'): _st((214, 206, 184), trousers=(158, 140, 110), sash=(132, 104, 74), hat=(30, 28, 30),
                                    skin=SK_SEA, units=EASTERN),
    # gunners: Joseon blue, black hat with a red top
    ('INDEPENDENT', 'ARTILLERO'): _st(EK_BLUE, trousers=EK_CREAM, sash=EK_RED, hat=EK_BLACK, hat_top=EK_RED, skin=SK_SEA,
                                      face='asian', units=EASTERN, sash_split=False),
    # Joseon horse: red officer's coat (cheollik), blue trousers, black brimmed hat (gat / jeonrip) with the red tassel
    ('INDEPENDENT', 'CAB_HUSAR'): _st(EK_RED, trousers=EK_BLUE, sash=EK_RED, hat=EK_BLACK, hat_top=EK_RED, skin=SK_SEA,
                                      face='asian', units=EASTERN),
    # mounted marksmen: earthy brown coat, white trousers, gold sash, black brimmed hat with a gold top
    ('INDEPENDENT', 'CAM_TIRADOR'): _st((112, 70, 44), trousers=EK_CREAM, sash=EK_GOLD, hat=EK_BLACK, hat_top=EK_GOLD,
                                        skin=SK_SEA, face='asian', units=EASTERN),
    # lancers: Joseon blue, black helmet and neck guard, red shield (face None: the asian face would pull the dark
    # helmet round the face to the skin colour)
    ('INDEPENDENT', 'CAB_LANCERO'): _st(EK_BLUE, trousers=EK_CREAM, sash=EK_GOLD, hat=EK_BLACK, skin=SK_SEA,
                                        units=EASTERN, sash_split=False, disc=EK_RED),
    # heavy lancers (Siamese / Burmese horse guard): madder red, gilt helmet and neck guard, gold shield
    ('INDEPENDENT', 'CAM_LANCERO'): _st(EK_RED, trousers=(70, 56, 50), sash=EK_GOLD, hat=EK_GOLD, skin=SK_SEA,
                                        units=EASTERN, sash_split=False, disc=EK_GOLD),
    # Kazakh Khanate (KAZAKH_FILE): guard musketeers in a long madder-brown chapan, brown fur malakhai hood, brass belts
    ('HANNOVER', 'GRANADERO'): _st((112, 60, 42), trousers=(88, 74, 58), sash=(176, 138, 66), hat=(70, 52, 38),
                                   skin=SK_ARAB, units=KAZAKH_FILE),
    # steppe horse: camel-tan chapan, round borik with the fur brim and the red felt crown
    ('HANNOVER', 'CAB_DRAGON'): _st((152, 114, 70), trousers=(86, 70, 54), sash=(128, 92, 58), hat=(80, 60, 42),
                                    skin=SK_ARAB, units=KAZAKH_FILE, crown=(150, 40, 36)),
    # armoured batyrs: dark rust coat, iron helmet and mail neck guard, leather shield
    ('HANNOVER', 'CAB_CORACERO'): _st((100, 56, 40), trousers=(70, 58, 48), sash=(170, 130, 64), hat=(116, 118, 122),
                                      skin=SK_ARAB, units=KAZAKH_FILE, sash_split=False, disc=(116, 78, 46)),
    # Sahel Kingdoms (SAHEL_FILE): indigo boubou and indigo veil-turban (tagelmust), white trousers
    ('SAJONIA', 'GRANADERO'): _st((46, 56, 104), trousers=(232, 226, 210), sash=WHT, hat=(34, 42, 80), skin=SK_SAHEL,
                                  units=SAHEL_FILE),
    # Hausa / Fulani horse: light cotton robe, indigo trousers, white turban round the red cap
    ('SAJONIA', 'CAB_DRAGON'): _st((226, 218, 198), trousers=(44, 54, 100), sash=(44, 54, 100), hat=(236, 230, 216),
                                   skin=SK_SAHEL, units=SAHEL_FILE, crown=(156, 40, 36)),
    # Bornu heavy horse: quilted cotton coat (lifidi), indigo trousers, iron helmet and neck guard, red shield
    ('SAJONIA', 'CAB_CORACERO'): _st((200, 176, 124), trousers=(44, 54, 100), sash=(44, 54, 100), hat=(104, 104, 110),
                                     skin=SK_SAHEL, units=SAHEL_FILE, sash_split=False, disc=(156, 40, 36)),
    # Southern Kingdoms (SOUTH_FILE). Marksmen: tanned hide cape over bare arms, hide breeches, red beadwork head band
    ('MOLDAVIA', 'TIRADOR'): _st((172, 124, 74), trousers=SA_HIDE, sash=SA_RED, hat=SA_RED, skin=SK_AFR, arms=SK_AFR,
                                 units=SOUTH_FILE, sash_split=False, card_skin=True),
    # chief's guard in leopard skin over bare arms and legs, white beadwork belt, white feather head-dress
    ('MOLDAVIA', 'GRANADERO'): _st((198, 152, 72), trousers=SK_AFR, sash=(226, 218, 200), hat=(226, 218, 200), skin=SK_AFR,
                                   pattern=SA_LEO, arms=SK_AFR, units=SOUTH_FILE, sash_split=False, card_skin=True),
    # warriors with the knobkerrie: tanned hide cloak over bare arms, dark hide below, bare black hair
    ('MOLDAVIA', 'MILICIA'): _st(SA_HIDE, trousers=(86, 60, 40), sash=(196, 178, 136), hat=(26, 22, 20), skin=SK_AFR,
                                 arms=SK_AFR, units=SOUTH_FILE, card_skin=True),
    # gunners: tanned hide, dark fur cap with a red top
    ('MOLDAVIA', 'ARTILLERO'): _st(SA_HIDE, trousers=SA_DARK, sash=SA_RED, hat=SA_FUR, hat_top=SA_RED, skin=SK_AFR,
                                   units=SOUTH_FILE, sash_split=False),
    # horse: tanned hide, cap of dark fur with a leopard-skin crown (disc: the hussar's sabre)
    ('MOLDAVIA', 'CAB_HUSAR'): _st(SA_HIDE, trousers=SA_DARK, sash=SA_RED, hat=SA_FUR, hat_top=(198, 152, 72), skin=SK_AFR,
                                   units=SOUTH_FILE, sash_split=False, disc=(140, 140, 146), card_skin=True),
    # frontier horsemen (mounted gunmen): dark leather coat, cord trousers, brown brimmed felt hat
    ('MOLDAVIA', 'CAB_DRAGON'): _st(SA_DARK, trousers=(140, 116, 82), sash=(140, 116, 82), hat=(92, 66, 44), skin=SK_AFR,
                                    units=SOUTH_FILE, card_skin=True),
    # shield and spear: tanned hide, fur head-dress, cowhide shield
    ('MOLDAVIA', 'CAB_LANCERO'): _st(SA_HIDE, trousers=SA_DARK, sash=SA_RED, hat=SA_FUR, skin=SK_AFR, units=SOUTH_FILE,
                                     sash_split=False, disc=(226, 218, 200), card_skin=True),
    # heavy horse: leopard-skin cape, fur head-dress, dark shield
    ('MOLDAVIA', 'CAB_CORACERO'): _st((198, 152, 72), trousers=SA_DARK, sash=SA_RED, hat=SA_FUR, skin=SK_AFR,
                                      pattern=SA_LEO, units=SOUTH_FILE, sash_split=False, disc=(96, 62, 40), card_skin=True),
}


def troop_recipe(country, troop, st=None):
    """The uniform of one troop: the signature elite's (SIGNATURE), a troop's own (TROOP_RECIPES), else st / the nation's."""
    sig = SIGNATURE.get(country)
    if sig and sig[0] == troop:
        return sig[1]
    return TROOP_RECIPES.get((country, troop)) or st or RECIPES[country]


# unit files with a texture plan of their own (no template folder textures): file -> {texture name: (source texture
# under data/Models, body the source is painted for (None = copied), troop whose uniform it gets)}. Every texture the
# file's blocks name for the nation's troops is here or in the template folder that make_map copies (Japan 23Tunez).
ART_CREW = os.path.join(BASE, 'Artilleria', 'Canon', 'Artillero', 'Artillero.V3D')     # all crews share its layout
OWN_TEX = {JAPON: {
    'Infanteria/Fusilero': ('06Espana/Infanteria/Elite', _m(INF, 'GenericoD3'), 'FUSILERO'),
    'Infanteria/Tirador': ('06Espana/Infanteria/Elite', _m(INF, 'GenericoD3'), 'TIRADOR'),
    'Infanteria/Elite': ('06Espana/Infanteria/Elite', _m(INF, 'GenericoD3'), 'ELITE'),
    'Infanteria/Miliciano1': ('06Espana/Infanteria/Miliciano1', _m(INF, 'GenericoH'), 'MILICIA'),
    'Infanteria/Miliciano2': ('06Espana/Infanteria/Miliciano2', _m(INF, 'GenericoH'), 'MILICIA'),
    'Infanteria/Miliciano3': ('06Espana/Infanteria/Miliciano3', _m(INF, 'GenericoH'), 'MILICIA'),
    'Infanteria/Artillero': ('12Portugal/Infanteria/Fusilero', ART_CREW, 'ARTILLERO'),
    'Caballeria/MamelukoCaballo': ('08Egipto/Caballeria/MamelukoCaballo', None, None),
    'Caballeria/Mameluko': ('08Egipto/Caballeria/Mameluko', _m(CAB, 'GenericoD4'), 'CAB_HUSAR'),
    'Caballeria/Lancero': ('23Tunez/Caballeria/Lancero', _m(CAB, 'GenericoG2'), 'CAB_LANCERO'),
}, QING_FILE: {                 # template folder 07Otomano (HusarCaballo, LanceroCaballo come from there)
    'Infanteria/Fusilero': ('06Espana/Infanteria/Elite', _m(INF, 'GenericoD3'), 'FUSILERO'),
    'Infanteria/Tirador': ('06Espana/Infanteria/Elite', _m(INF, 'GenericoD3'), 'TIRADOR'),
    'Infanteria/Miliciano1': ('06Espana/Infanteria/Miliciano1', _m(INF, 'GenericoH'), 'MILICIA'),
    'Infanteria/Miliciano2': ('06Espana/Infanteria/Miliciano2', _m(INF, 'GenericoH'), 'MILICIA'),
    'Infanteria/Miliciano3': ('06Espana/Infanteria/Miliciano3', _m(INF, 'GenericoH'), 'MILICIA'),
    'Infanteria/Artillero': ('12Portugal/Infanteria/Fusilero', ART_CREW, 'ARTILLERO'),
    'Caballeria/Husar': ('07Otomano/Caballeria/Husar', _m(CAB, 'GenericoE2'), 'CAB_HUSAR'),
    'Caballeria/Lancero': ('07Otomano/Caballeria/Lancero', _m(CAB, 'GenericoG2'), 'CAB_LANCERO'),
    'Caballeria/MamelukoCaballo': ('08Egipto/Caballeria/MamelukoCaballo', None, None),
    'Caballeria/Mameluko': ('08Egipto/Caballeria/Mameluko', _m(CAB, 'GenericoD4'), 'CAB_ELITE'),
}, EASTERN: {                   # template folder 22Marruecos (copied by make_map); these override its names
    'Infanteria/Fusilero': ('06Espana/Infanteria/Elite', _m(INF, 'GenericoD3'), 'FUSILERO'),
    'Infanteria/Tirador': ('06Espana/Infanteria/Elite', _m(INF, 'GenericoD3'), 'TIRADOR'),
    'Infanteria/Miliciano1': ('06Espana/Infanteria/Miliciano1', _m(INF, 'GenericoH'), 'MILICIA'),
    'Infanteria/Miliciano2': ('06Espana/Infanteria/Miliciano2', _m(INF, 'GenericoH'), 'MILICIA'),
    'Infanteria/Miliciano3': ('06Espana/Infanteria/Miliciano3', _m(INF, 'GenericoH'), 'MILICIA'),
    'Infanteria/Artillero': ('12Portugal/Infanteria/Fusilero', ART_CREW, 'ARTILLERO'),
    'Caballeria/MamelukoCaballo': ('08Egipto/Caballeria/MamelukoCaballo', None, None),
    'Caballeria/Mameluko': ('08Egipto/Caballeria/Mameluko', _m(CAB, 'GenericoD4'), 'CAB_HUSAR'),
    'Caballeria/TiradorCam': ('08Egipto/Caballeria/Mameluko', _m(CAB, 'GenericoD4'), 'CAM_TIRADOR'),
    'Caballeria/LanceroCaballo': ('07Otomano/Caballeria/LanceroCaballo', None, None),
    'Caballeria/Lancero': ('07Otomano/Caballeria/Lancero', _m(CAB, 'GenericoG2'), 'CAB_LANCERO'),
    'Caballeria/LanceroCam': ('07Otomano/Caballeria/Lancero', _m(CAB, 'GenericoG2'), 'CAM_LANCERO'),
}, SOUTH_FILE: {                # model folder 21Moldavia (its European originals are overridden by these names)
    'Infanteria/Fusilero': ('06Espana/Infanteria/Elite', _m(INF, 'GenericoD3'), 'FUSILERO'),
    'Infanteria/Tirador': ('06Espana/Infanteria/Elite', _m(INF, 'GenericoD3'), 'TIRADOR'),
    'Infanteria/Granadero': ('06Espana/Infanteria/Elite', _m(INF, 'GenericoD3'), 'GRANADERO'),
    'Infanteria/Miliciano1': ('06Espana/Infanteria/Miliciano1', _m(INF, 'GenericoH'), 'MILICIA'),
    'Infanteria/Miliciano2': ('06Espana/Infanteria/Miliciano2', _m(INF, 'GenericoH'), 'MILICIA'),
    'Infanteria/Miliciano3': ('06Espana/Infanteria/Miliciano3', _m(INF, 'GenericoH'), 'MILICIA'),
    'Infanteria/Artillero': ('12Portugal/Infanteria/Fusilero', ART_CREW, 'ARTILLERO'),
    'Caballeria/HusarCaballo': ('07Otomano/Caballeria/HusarCaballo', None, None),
    'Caballeria/Husar': ('07Otomano/Caballeria/Husar', _m(CAB, 'GenericoE2'), 'CAB_HUSAR'),
    'Caballeria/DragonCaballo': ('08Egipto/Caballeria/MamelukoCaballo', None, None),
    'Caballeria/Dragon': ('08Egipto/Caballeria/Mameluko', _m(CAB, 'GenericoD4'), 'CAB_DRAGON'),
    'Caballeria/LanceroCaballo': ('07Otomano/Caballeria/LanceroCaballo', None, None),
    'Caballeria/Lancero': ('07Otomano/Caballeria/Lancero', _m(CAB, 'GenericoG2'), 'CAB_LANCERO'),
    'Caballeria/CCoraceroCaballo': ('22Marruecos/Caballeria/LanceroCaballo', None, None),
    'Caballeria/CCoracero': ('22Marruecos/Caballeria/Lancero', _m(CAB, 'GenericoG2'), 'CAB_CORACERO'),
}}
# the Kazakh and Sahel files: textures of the three moved troops, ADDED to the template textures (22Marruecos) that the
# other troops keep (OWN_ADDS); the names are those of the European originals in 17Hannover / 19Sajonia, overridden
for _f in (KAZAKH_FILE, SAHEL_FILE):
    OWN_TEX[_f] = {
        'Infanteria/Granadero': ('22Marruecos/Infanteria/Tirador', _m(INF, 'GenericoA4'), 'GRANADERO'),
        'Caballeria/DragonCaballo': ('08Egipto/Caballeria/MamelukoCaballo', None, None),
        'Caballeria/Dragon': ('08Egipto/Caballeria/Mameluko', _m(CAB, 'GenericoD4'), 'CAB_DRAGON'),
        'Caballeria/CCoraceroCaballo': ('22Marruecos/Caballeria/LanceroCaballo', None, None),
        'Caballeria/CCoracero': ('22Marruecos/Caballeria/Lancero', _m(CAB, 'GenericoG2'), 'CAB_CORACERO')}
OWN_ADDS = {KAZAKH_FILE, SAHEL_FILE}
# bodies whose part split must ignore the weapon when it measures heights (the lance raises the top: the hood of
# GenericoG2 would count as a skirt); only for the OWN_TEX plans, the other nations' textures stay as they were
EXACT_PARTS = {'GenericoG2'}
# texture boxes that are headgear although their brown passes for skin (the crown of the Mameluke hat, 08Egipto
# Mameluko.dds top left): the OWN_TEX plans paint them in the hat colour
HAT_BOX = {'GenericoD4': (0, 0, 96, 62)}
# bare heads whose brown hair passes for skin: skin only from this brightness up, so the hair takes the hat colour
# (black) in the OWN_TEX plans (the Spanish militia textures on GenericoH)
SKIN_MIN_V = {'GenericoH': 0.5}
# texture boxes kept as painted (OWN_TEX plans): the raised sabre of GenericoE2 sits as high as the hat, so the
# height split calls it hat_top (it would take the hat's red top)
KEEP_BOX = {'GenericoE2': (86, 0, 100, 70)}
# the same per unit file (so the earlier plans stay as they are): the musket of the guerrilla body (the thin UV strip at
# the top of 06Espana Elite.dds, classed 'arms', would take the coat colour) keeps its painted wood and steel
KEEP_FILE = {EASTERN: {'GenericoD3': (0, 0, 146, 12)}, SOUTH_FILE: {'GenericoD3': (0, 0, 146, 12)}}

# unit-file elite blocks whose textures build_nation paints for EVERY nation of that file (the signature recipe for
# the nation's own signature troop, else the nation's recipe), so each path the block names exists in each folder
ELITE_BLOCKS = {ASIA: ('ELITE', 'CAB_ELITE'), INDIA: ('CAB_ELITE',), AFRICA: ('CAB_ELITE',), ORIENTE: ('ELITE', 'CAB_ELITE')}
# body of such a block -> the Arab-set textures painted for it (UV layout of that body; mount first, the man last)
ELITE_SRC = {'GenericoC': ('Caballeria/MamelukoCaballo', 'Caballeria/Mameluko'),      # Egypt's own elite: C + Mameluke
             'GenericoD4': ('Caballeria/MamelukoCaballo', 'Caballeria/Mameluko'),
             'GenericoE2': ('Caballeria/HusarCaballo', 'Caballeria/Husar'),
             'GenericoA3': ('Infanteria/Fusilero',), 'GenericoA4': ('Infanteria/Tirador',)}


def nation_list():
    """[(country key, recipe key, model folder, figure folder, template models folder)] for every nation with a recipe."""
    out = []
    for nn in NT.NEW_NATIONS:
        if nn['key'] in RECIPES:
            out.append((nn['key'], nn['key'], nn['folder'], nn['folder'], nn['models']))
    for c, (rk, mf, ff, tf) in RESKINS.items():
        out.append((c, rk, mf, ff, tf))
    return out


UNIT_FILE_OF = {}
for _c, _rk, _mf, _ff, _tf in nation_list():
    UNIT_FILE_OF[_c] = RECIPES[_rk]['units']


# ------------------------------------------------------------------ helpers
def _rows(img):
    img = img.convert('RGBA')
    w, h = img.size; b = img.tobytes()
    return [bytearray(b[y * w * 4:(y + 1) * w * 4]) for y in range(h)]


def save_dds(path, img, mips=True):
    """DXT1; mips like the unit textures (9 levels at 256), or none like the figure textures."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    arr = np.asarray(img.convert('RGB'), dtype=np.uint8)
    if mips:
        TGA.write_dds_dxt1_mips_np(path, arr)
    else:
        h, w = arr.shape[:2]
        hdr = bytearray(128); hdr[0:4] = b'DDS '
        struct.pack_into('<7I', hdr, 4, 124, 0x81007, h, w, w * h // 2, 0, 0)
        struct.pack_into('<2I', hdr, 76, 32, 4); hdr[84:88] = b'DXT1'
        struct.pack_into('<I', hdr, 108, 0x1000)
        open(path, 'wb').write(bytes(hdr) + TGA._dxt1_np(arr))


def _parts(model, rider=False, exact=False):
    """Islands of one mesh classified by relative rest height. rider=True picks the rider of a cavalry model.
    exact: heights measured on the large islands only (a lance or its tip does not raise the top)."""
    items = R.islands(model)
    names = [i['mesh'] for i in items]
    mesh = next(n for n in names if not n.startswith(('Caballo', 'Camello')))   # the man, not the mount
    items = [i for i in items if i['mesh'] == mesh and i['n'] >= 3]
    thin = lambda i: i['bbox'][2] - i['bbox'][0] < 22 and i['bbox'][3] - i['bbox'][1] > 90      # a shaft (as below)
    rng = [i for i in items if i['area'] >= 1500 and not thin(i)] if exact else items
    ylo = min(i['ymin'] for i in rng); yhi = max(i['ymax'] for i in rng)
    rel = lambda i: (i['cy'] - ylo) / (yhi - ylo or 1)
    parts = {}
    torso = items[0]
    parts['torso'] = [torso['mask']]
    for i in items[1:]:
        r = rel(i)
        if i['bbox'][2] - i['bbox'][0] < 22 and i['bbox'][3] - i['bbox'][1] > 90:
            k = 'weapon'
        elif r > 0.72 and i['area'] > 3000:
            k = 'head'
        elif r > 0.78:
            k = 'hat_top'
        elif r < 0.12 and i['area'] < 1500:
            k = 'feet'
        elif r < 0.2 and i['area'] < 2500:
            k = 'shoes'
        elif r < 0.5 and i['area'] > 4000:
            k = 'legs'
        elif i['area'] > 4000:
            k = 'skirt'
        elif r < 0.3:
            k = 'shoes'
        else:
            k = 'arms'
        parts.setdefault(k, []).append(i['mask'])
    return {k: R.union(v) for k, v in parts.items()}, mesh


_PARTS = {}
def parts(model, rider=False, exact=False):
    k = (model, rider, exact)
    if k not in _PARTS:
        _PARTS[k] = _parts(model, rider, exact)
    return _PARTS[k]


def _skin(img, mask, head=False, min_frac=0.0):
    """Skin-coloured pixels under mask; beige cloth folds are excluded by the stricter saturation limits.
    min_frac: return an empty mask when skin covers less than this share (a coat that merely has warm folds)."""
    if head:
        m = R.hsv_mask(img, mask, h=(5, 24), s=(0.42, 0.9), v=(0.2, 0.9))     # faces: hue 5-24; turbans/beige robes 24-40
    else:
        m = R.hsv_mask(img, mask, h=(5, 24), s=(0.42, 0.85), v=(0.2, 0.85))
    if min_frac:
        area = sum(1 for v in mask.getdata() if v) or 1
        if sum(1 for v in m.getdata() if v) < min_frac * area:
            return Image.new('L', (S, S), 0)
    return m


def _minus(a, b):
    return Image.composite(Image.new('L', (S, S), 0), a, b)


def face_asian(img, head, hat, skin_col):
    """Clean-shaven, lighter face: skin pixels retinted, dark beard pixels pulled towards the skin colour."""
    skin = _skin(img, head, head=True)
    face = Image.composite(skin.filter(ImageFilter.MaxFilter(15)), Image.new('L', (S, S), 0), head)   # face + beard + hair
    img = R.tint(img, skin, skin_col, contrast=0.9)
    beard = R.hsv_mask(img, face, s=(0, 0.6), v=(0.08, 0.42))
    beard = _minus(beard, R.union([skin], grow=0))
    return R.tint(img, beard, tuple(int(c * 0.78) for c in skin_col), contrast=0.6, mix=0.75)


# round marks (a mon) painted as they are seen on the figure: the UV layouts of these bodies are stretched and turned,
# so a disc drawn in the texture would not look round. body (model file name) -> [(yaw, x, y, r)]: the view (0 front,
# pi back), the centre beside the body axis (x, share of the figure's height, + = to the viewer's right) and below the
# head top (y), the radius (share of the height). The figure = the man (riders: the visible rider above the mount).
MON_AT = {'GenericoD3': [(0.0, 0.0, 0.25, 0.034), (math.pi, 0.0, 0.22, 0.042)],
          'Artillero': [(0.0, -0.045, 0.27, 0.026)],                # the back is the knapsack
          'GenericoD4': [(math.pi, 0.0, 0.30, 0.055)],
          'GenericoG2': [(math.pi, 0.0, 0.50, 0.06)],
          'GenericoH': [(0.0, 0.0, 0.30, 0.034), (math.pi, 0.0, 0.26, 0.042)]}
_DECAL = {}


def decal_samples(model, yaw, fx, fy, fr, size=1600):
    """(texel u, texel v, x, y) of the screen pixels of a disc on the figure (MON_AT entry): an unlit render with a
    UV-coded texture gives the texel under each pixel; x, y in -1..1 across the disc (y down)."""
    from scipy import ndimage
    key = (model, yaw, fx, fy, fr)
    if key not in _DECAL:
        yy, xx = np.mgrid[0:S, 0:S]
        code = Image.fromarray(np.stack([xx, yy, np.full_like(xx, 255)], -1).astype(np.uint8))
        nm = len([m for m in uvdump.meshes(model) if m['uv'] and m['tris'] and m['pos'] and len(m['pos']) == len(m['uv'])])
        texs = [Image.new('RGB', (S, S), 0)] * (nm - 1) + [code]          # the mount black, the man coded
        a = np.asarray(R.render(model, texs, size=(size, size), yaw=yaw, pitch=0.0, ss=1, ambient=1.0, diffuse=0.0,
                                bg=(0, 0, 0))).astype(np.int64)
        man = a[..., 2] > 250
        core = ndimage.binary_opening(man, np.ones((9, 9), bool))         # without lances and muskets
        ys, xs = np.nonzero(core)
        top, h = ys.min(), ys.max() - ys.min()
        band = core[top + int(0.2 * h):top + int(0.4 * h)]
        cx, cy, r = float(np.median(np.nonzero(band)[1])) + fx * h, top + fy * h, fr * h
        gy, gx = np.mgrid[int(cy - r) - 1:int(cy + r) + 2, int(cx - r) - 1:int(cx + r) + 2]
        dx, dy = (gx + 0.5 - cx) / r, (gy + 0.5 - cy) / r
        ok = (dx * dx + dy * dy <= 1.0) & man[gy, gx]
        _DECAL[key] = (a[gy, gx, 0][ok], a[gy, gx, 1][ok], dx[ok], dy[ok])
    return _DECAL[key]


def mon_pattern(x, y):
    """A plain mon in -1..1: 1 = the light ring and three leaves (a mitsuba), 2 = the field inside the ring."""
    out = np.where(np.hypot(x, y) <= 0.78, 2, 1)
    for ang in (-90, 30, 150):
        c, s = math.cos(math.radians(ang)) * 0.37, math.sin(math.radians(ang)) * 0.37
        out = np.where(np.hypot(x - c, y - s) <= 0.26, 1, out)
    return out


_GLYPH = {}
def glyph_pattern(text):
    """A round badge in -1..1 with a character (the Qing bing / yong badge): 1 = the disc, 2 = the strokes, 3 = the rim."""
    if text not in _GLYPH:
        from PIL import ImageFont
        m = Image.new('L', (128, 128), 0)
        ImageDraw.Draw(m).text((64, 66), text, font=ImageFont.truetype(FONT_CJK, 104), fill=255, anchor='mm')
        _GLYPH[text] = np.asarray(m) > 110
    g = _GLYPH[text]

    def pat(x, y):
        ix = np.clip(((x / 0.6 + 1) * 64).astype(int), 0, 127); iy = np.clip(((y / 0.6 + 1) * 64).astype(int), 0, 127)
        inside = (np.abs(x) < 0.6) & (np.abs(y) < 0.6)
        out = np.where(np.hypot(x, y) > 0.84, 3, 1)
        return np.where(inside & g[iy, ix], 2, out)
    return pat


def mon_decal(img, model, allowed, pattern, colours, scale=1.0):
    """Paint the mark of MON_AT[body] onto a texture: pattern(x, y) -> codes, colours = [(code, colour or None =
    the cloth)] in painting order, shaded like the cloth under it; only texels in `allowed` (L mask: the coat) take
    it. scale: the radius times this, the top edge kept (a head cloth's tail hangs above the back mark)."""
    from scipy import ndimage
    arr = np.asarray(img.convert('RGB'), np.float32).copy()
    lum = arr @ np.array([0.299, 0.587, 0.114], np.float32)
    al = np.asarray(allowed) > 0
    colours = [(code, col) for code, col in colours if col is not None]
    for (yaw, fx, fy, fr) in MON_AT[os.path.splitext(os.path.basename(model))[0]]:
        u, v, x, y = decal_samples(model, yaw, fx, fy + (scale - 1) * fr, fr * scale)
        ok = al[v, u]
        if ok.mean() < 0.6:                    # mostly off the coat from this side (a sleeve or a strap in front)
            continue
        u, v, val = u[ok], v[ok], pattern(x[ok], y[ok])
        n = np.zeros((S, S)); fr_ = {code: np.zeros((S, S)) for code, _ in colours}
        np.add.at(n, (v, u), 1)
        for code, f in fr_.items():
            np.add.at(f, (v, u), val == code)
        hit = n > 0
        for f in fr_.values():
            f /= np.maximum(n, 1)
        hole = ndimage.binary_closing(hit) & ~hit & al     # texels between the samples
        if hole.any():
            k = np.ones((3, 3)) / 9.0
            w = ndimage.convolve(hit.astype(float), k) + 1e-6
            for f in fr_.values():
                f[hole] = (ndimage.convolve(f, k) / w)[hole]
        mark = hit | hole
        m = float(lum[mark].mean())
        shade = np.clip(lum / max(m, 1.0), 0.6, 1.35) ** 0.6
        for code, col in colours:
            frac = fr_[code]
            c = np.array(col, np.float32)[None, None, :] * shade[..., None]
            arr = arr * (1 - frac[..., None]) + c * frac[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def spots(img, mask, base, spot, size, share, mix=0.85, seed=1789):
    """A hide under mask (cowhide patches, leopard spots): smooth noise in texture space, its top `share` the spot
    colour, the rest the base colour, both modulated by the painted shading (as R.stripes). The UV islands cut the
    blotches at their seams, which a hide does not mind. Deterministic (fixed seed)."""
    from scipy import ndimage
    a = np.asarray(img.convert('RGB'), np.float32)
    n = ndimage.gaussian_filter(np.random.RandomState(seed).rand(S, S), size, mode='wrap')
    sp = n > np.quantile(n, 1 - share)
    pal = np.where(sp[..., None], np.array(spot, np.float32), np.array(base, np.float32))
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    m = np.asarray(mask, np.float32) / 255.0
    b = float((lum * m).sum() / max(m.sum(), 1)) or 128.0
    out = np.clip(pal * (lum / b)[..., None], 0, 255)
    w = (m * mix)[..., None]
    return Image.fromarray((out * w + a * (1 - w)).astype(np.uint8))


def retex(model, src, st, rider=False, keep_light=False, exact=False, hat_box=None, skin_min_v=None):
    """Apply a recipe to one unit texture (PIL RGB) of the given model.
    keep_light: light grey parts of the torso (a cuirass) keep their own colour instead of becoming sash or coat.
    exact: part split with heights of the large islands only (_parts). hat_box: texture box that is all headgear.
    skin_min_v: face skin only from this HSV brightness up (darker hair becomes headgear / hair colour)."""
    P, mesh = parts(model, rider, exact)
    img = src.convert('RGB')
    torso, head = P['torso'], P.get('head', Image.new('L', (S, S), 0))
    hat_top = P.get('hat_top', Image.new('L', (S, S), 0))
    skin_t = _skin(img, torso, min_frac=0.2); skin_h = _skin(img, head, head=True)
    if hat_box:
        skin_h = _minus(skin_h, R.box_mask(*hat_box))
    if skin_min_v:
        skin_h = Image.composite(skin_h, Image.new('L', (S, S), 0), R.hsv_mask(img, head, v=(skin_min_v, 1), feather=0))
    skin_a = _skin(img, P['arms']) if 'arms' in P else Image.new('L', (S, S), 0)
    light = R.hsv_mask(img, torso, s=(0, 0.33), v=(0.6, 1), feather=0)
    light = Image.composite(light.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5)), Image.new('L', (S, S), 0), torso)
    tor_area = sum(1 for v in torso.getdata() if v) or 1
    lum = np.asarray(img, np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    coat_lum = float(lum[np.asarray(torso) > 0].mean())
    # belts/sash are split off only on dark coats; white robes (Egipto/Marruecos) are recoloured whole
    sash_ok = (coat_lum < 90 and sum(1 for v in light.getdata() if v) < 0.45 * tor_area and not keep_light
               and st.get('sash_split') is not False)
    disc = R.hsv_mask(img, torso, h=(340, 20), s=(0.45, 1), v=(0.25, 1))
    cut = [skin_t, disc] + ([light] if sash_ok or keep_light else [])
    coat = _minus(torso, R.union(cut, grow=0))
    hat = _minus(head, skin_h)
    # cloth
    if st['pattern'] and st['pattern'][0] == 'spots':
        img = spots(img, coat, *st['pattern'][1:])
    elif st['pattern']:
        cols, per, ang = st['pattern']
        img = R.stripes(img, coat, cols, per, angle=ang, mix=0.8)
    else:
        img = R.tint(img, coat, st['coat'], contrast=st['coat_contrast'])
    if 'skirt' in P:
        if st['skirt_pattern']:
            cols, per, ang = st['skirt_pattern']
            img = R.stripes(img, P['skirt'], cols, per, angle=ang, mix=0.8)
        else:
            img = R.tint(img, P['skirt'], st['skirt'], contrast=1.1)
    if 'arms' in P:
        img = R.tint(img, _minus(P['arms'], skin_a), st.get('arms') or st['coat'])
    if sash_ok:
        img = R.tint(img, light, st['sash'])
    img = R.tint(img, disc, st['disc'])
    if 'legs' in P:
        img = R.tint(img, P['legs'], st['trousers'], contrast=1.1)
    if 'shoes' in P:
        img = R.tint(img, P['shoes'], tuple(int(c * 0.5) for c in st['trousers']))
    # head
    img = R.tint(img, hat, st['hat'], contrast=1.2)
    img = R.tint(img, hat_top, st['hat_top'], contrast=1.1)
    if hat_box and st.get('crown'):
        img = R.tint(img, Image.composite(R.box_mask(*hat_box), Image.new('L', (S, S), 0), head), st['crown'], contrast=1.1)
    if st['face'] == 'asian':
        img = face_asian(img, head, hat, st['skin'] or SK_ASIA)
    elif st['skin']:
        img = R.tint(img, R.union([skin_h], grow=0), st['skin'], contrast=1.05)
    if st['skin']:
        img = R.tint(img, R.union([skin_t, skin_a], grow=0), st['skin'], contrast=1.05)
    # insignia on the coat (fusilier only; the mon of the bodies in MON_AT is painted as seen on the figure)
    ins = st['insignia']
    if ins and ins[0] in ('mon', 'glyph') and os.path.splitext(os.path.basename(model))[0] in MON_AT:
        coat_m = _minus(R.union([torso] + ([P['skirt']] if 'skirt' in P else []), grow=0), skin_t)
        if ins[0] == 'mon':
            img = mon_decal(img, model, coat_m, mon_pattern, [(2, ins[2]), (1, ins[1])])
        else:                       # a round badge with a character, larger than a mon
            _, text, fill, ink, ring = ins
            img = mon_decal(img, model, coat_m, glyph_pattern(text), [(1, fill), (3, ring), (2, ink)], scale=1.25)
    elif ins and mesh in INSIGNIA_AT:
        for (x, y, r) in INSIGNIA_AT[mesh]:
            if ins[0] == 'glyph':
                _, text, fill, ink, ring = ins
                img = R.disc(img, (x, y), r, fill=fill, outline=ring, width=2)
                img = R.glyph(img, text, FONT_CJK, int(r * 1.5), (x, y + 1), fill=ink)
            elif ins[0] == 'mon':
                _, gold, dark = ins
                img = R.disc(img, (x, y), r, fill=gold); img = R.disc(img, (x, y), r - 4, fill=dark)
                img = R.disc(img, (x, y), r - 7, fill=gold)
            elif ins[0] == 'disc':
                _, fill, ring = ins
                img = R.disc(img, (x, y), r, fill=fill, outline=ring, width=2)
            elif ins[0] == 'gazyri' and (x, y, r) == INSIGNIA_AT[mesh][0]:
                # two rows of cartridge tubes on the chest, either side of the coat opening
                _, tube, shadow = ins
                dr = ImageDraw.Draw(img)
                for side in (-1, 1):
                    for k in range(5):
                        bx = x + side * (6 + k * 5)
                        dr.rectangle([bx - 1, y - 16, bx + 1, y - 2], fill=shadow)
                        dr.rectangle([bx - 1, y - 16, bx, y - 4], fill=tube)
                        dr.rectangle([bx - 2, y - 17, bx + 2, y - 15], fill=tube)
    return img


# ------------------------------------------------------------------ campaign officer figures
FIG_FILES = ['Capitan', 'Teniente', 'General', 'Mariscal']
FIG_COPY = ['CaballoGeneral', 'CaballoMariscal']


def retex_figure(src, st):
    """Recolour a 00Generico officer texture: blue coat -> nation coat, red facings -> sash colour, skin."""
    img = src.convert('RGB')
    allm = Image.new('L', (S, S), 255)
    blue = R.hsv_mask(img, allm, h=(195, 255), s=(0.3, 1), v=(0.12, 1))
    red = R.hsv_mask(img, allm, h=(340, 15), s=(0.5, 1), v=(0.25, 1))
    img = R.tint(img, blue, st['coat'], contrast=1.1)
    img = R.tint(img, red, st['sash'])
    if st['skin']:
        img = R.tint(img, _skin(img, allm), st['skin'], contrast=1.05)
    return img


# ------------------------------------------------------------------ ship ensigns
_FLAGBOX = {}
def flag_boxes(ship):
    """Where the nation flag is painted in a hull texture: boxes where two template nations' hulls differ."""
    if ship not in _FLAGBOX:
        a = np.asarray(uvdump.load_tex(os.path.join(DATA, 'Models', '07Otomano', 'Barcos', ship + '.tga')).convert('RGB'), int)
        b = np.asarray(uvdump.load_tex(os.path.join(DATA, 'Models', '10Dinamarca', 'Barcos', ship + '.tga')).convert('RGB'), int)
        diff = (np.abs(a - b).sum(2) > 60)
        # coarse 32 px cells, then connected boxes
        cells = diff.reshape(32, 32, 32, 32).mean((1, 3)) > 0.2
        boxes = []
        seen = np.zeros_like(cells)
        for cy in range(32):
            for cx in range(32):
                if cells[cy, cx] and not seen[cy, cx]:
                    stack = [(cy, cx)]; seen[cy, cx] = True; pts = []
                    while stack:
                        y, x = stack.pop(); pts.append((y, x))
                        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            ny, nx = y + dy, x + dx
                            if 0 <= ny < 32 and 0 <= nx < 32 and cells[ny, nx] and not seen[ny, nx]:
                                seen[ny, nx] = True; stack.append((ny, nx))
                    ys = [p[0] for p in pts]; xs = [p[1] for p in pts]
                    sub = diff[min(ys) * 32:(max(ys) + 1) * 32, min(xs) * 32:(max(xs) + 1) * 32]
                    yy, xx = np.nonzero(sub)
                    boxes.append((min(xs) * 32 + xx.min(), min(ys) * 32 + yy.min(), min(xs) * 32 + xx.max() + 1, min(ys) * 32 + yy.max() + 1))
        _FLAGBOX[ship] = [b for b in boxes if (b[2] - b[0]) * (b[3] - b[1]) > 2000]
    return _FLAGBOX[ship]


def retex_hull(src, design):
    img = src.convert('RGB')
    arr = np.asarray(img).astype(np.float32)
    for (x0, y0, x1, y1) in flag_boxes_current:
        w, h = x1 - x0, y1 - y0
        flag = np.asarray(Image.frombytes('RGBA', (w, h), b''.join(bytes(r) for r in FL.render(design, w, h, ss=2))).convert('RGB'), np.float32)
        patch = arr[y0:y1, x0:x1]
        lum = (patch[..., 0] * 0.299 + patch[..., 1] * 0.587 + patch[..., 2] * 0.114) / 150.0
        arr[y0:y1, x0:x1] = np.clip(flag * np.clip(lum, 0.35, 1.25)[..., None], 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


flag_boxes_current = []


# ------------------------------------------------------------------ per-culture unit files
def _swap(txt, unit, grx, tex=None, tex2=None):
    m = re.search(r'^\.%s\b.*?\n\]' % unit, txt, re.M | re.S)
    blk = m.group()
    blk = re.sub(r'\.GRX "[^"]*"', '.GRX "Models\\\\00EjercitoBase\\\\%s\\\\%s\\\\%s.V3D"' % (grx[0], grx[1], grx[1]), blk)
    blk = re.sub(r'\.ANM "[^"]*"', '.ANM "Models\\\\00EjercitoBase\\\\%s\\\\%s\\\\%s_ANM.sb"' % (grx[0], grx[1], grx[1]), blk)
    if tex:
        blk = re.sub(r'\.TEX "[^"]*"', '.TEX "%s"' % tex.replace('\\', '\\\\'), blk)
    if tex2:
        blk = re.sub(r'\.TEX2 "[^"]*"', '.TEX2 "%s"' % tex2.replace('\\', '\\\\'), blk)
    return txt[:m.start()] + blk + txt[m.end():]


def unit_files():
    """{file name: text} for the new per-culture unit definition files."""
    arabes = open(os.path.join(BAT, 'DefUnidadesArabes.sb'), 'rb').read().decode('latin1')
    egipto = open(os.path.join(BAT, 'DefUnidadesEgipto.sb'), 'rb').read().decode('latin1')
    hdr = lambda t, name: t.replace('<<<< STANDARD >>>>', '<<<< %s >>>>  (generated by tools/art/units/cultures.py)' % name, 1)
    # no camels: the camel troops ride horses (hussar / lancer bodies and textures)
    nocam = _swap(arabes, 'CAM_TIRADOR', ('Caballeria', 'GenericoE2'), 'Caballeria\\HusarCaballo.dds', 'Caballeria\\Husar.dds')
    nocam = _swap(nocam, 'CAM_LANCERO', ('Caballeria', 'GenericoG2'), 'Caballeria\\LanceroCaballo.dds', 'Caballeria\\Lancero.dds')
    caucaso = _swap(nocam, 'CAB_ELITE', ('Caballeria', 'GenericoD4'), 'Caballeria\\MamelukoCaballo.dds', 'Caballeria\\Mameluko.dds')
    pacific = _swap(nocam, 'CAB_ELITE', ('Caballeria', 'GenericoE2'), 'Caballeria\\HusarCaballo.dds', 'Caballeria\\Husar.dds')
    # signature elites (SIGNATURE, ELITE_BLOCKS): blocks of their own, so the elite never shares the line troops' textures.
    # Asia: Japan's samurai on the Arab fusilier body (Chechnya's Caucasus file keeps the European guard body).
    elite = ('Caballeria\\Elite\\Caballo.dds', 'Caballeria\\Elite\\Elite.dds')
    asia = _swap(caucaso, 'ELITE', ('Infanteria', 'GenericoA3'), 'Infanteria\\Elite.dds')
    africa = _swap(pacific, 'CAB_ELITE', ('Caballeria', 'GenericoE2'), *elite)       # Ethiopia's Oromo horse
    india = _swap(egipto, 'CAB_ELITE', ('Caballeria', 'GenericoC'), *elite)          # the Maratha Huzurat horse
    oriente = _swap(_swap(arabes, 'ELITE', ('Infanteria', 'GenericoA4'), 'Infanteria\\Elite.dds'),
                    'CAB_ELITE', ('Caballeria', 'GenericoD4'), *elite)
    # Japan and Qing (JAPON, QING_FILE, OWN_TEX): no turbans; the gun crews (all on the Artillero layout) get a texture
    # of their own
    def no_turbans(txt):
        txt = _swap(txt, 'MILICIA', ('Infanteria', 'GenericoH'))
        for troop, tex in (('FUSILERO', 'Fusilero'), ('TIRADOR', 'Tirador'), ('ELITE', 'Elite')):
            txt = _swap(txt, troop, ('Infanteria', 'GenericoD3'), 'Infanteria\\%s.dds' % tex)
        for crew in ('ARTILLERO', 'ARTILLERO_DR', 'ARTILLERO_IZ', 'ARTILLERO_MORTERO', 'CANCABALLOS_ARTILLERO',
                     'CANCABALLOS_ARTILLERO_DR', 'CANCABALLOS_ARTILLERO_IZ'):
            m = re.search(r'^\.%s\b.*?\n\]' % crew, txt, re.M | re.S)
            txt = txt[:m.start()] + m.group().replace('"Infanteria\\Fusilero.dds"', '"Infanteria\\Artillero.dds"') + txt[m.end():]
        return txt
    japon = _swap(no_turbans(caucaso), 'CAB_HUSAR', ('Caballeria', 'GenericoD4'), 'Caballeria\\MamelukoCaballo.dds',
                  'Caballeria\\Mameluko.dds')
    qing = no_turbans(caucaso)          # hussars on E2, lancers on G2, the Bannermen (CAB_ELITE) on D4 as before
    # the Eastern Kingdoms (EASTERN): as Japan's, plus the camel types on horse bodies with textures of their own
    reinos = _swap(no_turbans(caucaso), 'CAB_HUSAR', ('Caballeria', 'GenericoD4'), 'Caballeria\\MamelukoCaballo.dds',
                   'Caballeria\\Mameluko.dds')
    reinos = _swap(reinos, 'CAM_TIRADOR', ('Caballeria', 'GenericoD4'), 'Caballeria\\MamelukoCaballo.dds',
                   'Caballeria\\TiradorCam.dds')
    reinos = _swap(reinos, 'CAM_LANCERO', ('Caballeria', 'GenericoG2'), 'Caballeria\\LanceroCaballo.dds',
                   'Caballeria\\LanceroCam.dds')
    # Kazakh / Sahel (KAZAKH_FILE, SAHEL_FILE): the Arab file with grenadiers, dragoons and cuirassiers off the European
    # bodies; Southern Kingdoms (SOUTH_FILE): no turbans, grenadiers on the guerrilla body too
    def moved(txt, gren_body):
        txt = _swap(txt, 'GRANADERO', ('Infanteria', gren_body), 'Infanteria\\Granadero.dds')
        txt = _swap(txt, 'CAB_DRAGON', ('Caballeria', 'GenericoD4'), 'Caballeria\\DragonCaballo.dds', 'Caballeria\\Dragon.dds')
        return _swap(txt, 'CAB_CORACERO', ('Caballeria', 'GenericoG2'), 'Caballeria\\CCoraceroCaballo.dds',
                     'Caballeria\\CCoracero.dds')
    return {'DefUnidadesAsia.sb': hdr(asia, 'ASIA'), 'DefUnidadesIndia.sb': hdr(india, 'INDIA'),
            'DefUnidadesAfrica.sb': hdr(africa, 'AFRICA'), 'DefUnidadesPacific.sb': hdr(pacific, 'PACIFIC'),
            CAUCASUS: hdr(caucaso, 'CAUCASUS'), ORIENTE: hdr(oriente, 'ORIENTE'), JAPON: hdr(japon, 'JAPON'),
            QING_FILE: hdr(qing, 'QING'), EASTERN: hdr(reinos, 'EASTERN KINGDOMS'),
            KAZAKH_FILE: hdr(moved(arabes, 'GenericoA4'), 'KAZAKH'), SAHEL_FILE: hdr(moved(arabes, 'GenericoA4'), 'SAHEL'),
            SOUTH_FILE: hdr(moved(no_turbans(caucaso), 'GenericoD3'), 'SOUTHERN KINGDOMS')}


def unit_text(fname):
    """Text of a unit definition file: one generated here, else the game's own."""
    gen = unit_files()
    return gen[fname] if fname in gen else open(os.path.join(BAT, fname), 'rb').read().decode('latin1')


def unit_textures(txt, troop):
    """(model .V3D abs path, [texture names like 'Caballeria/Dragon': mount first]) of a troop block of a unit file."""
    m = re.search(r'^\.%s\b.*?\n\]' % troop, txt, re.M | re.S)
    if not m:
        return None
    grx = re.search(r'\.GRX\s+"([^"]+)"', m.group())
    texs = [t.replace('\\', '/')[:-4] for t in re.findall(r'\.(?:TEX|TEX2|RANDOMTEX)\s+"([^"]+)"', m.group())]
    return os.path.join(DATA, grx.group(1).replace('\\', os.sep)), texs


# ------------------------------------------------------------------ build
def _template_textures(tfolder):
    """(relative name without extension, abs path) of every unit texture in a template Models folder."""
    out = []
    for sub in ('Infanteria', 'Caballeria'):
        d = os.path.join(DATA, 'Models', tfolder, sub)
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith('.dds'):
                out.append((sub + '/' + fn[:-4], os.path.join(d, fn)))
    return out


def build_nation(out_root, country, rkey, mfolder, ffolder, tfolder, written, render_pair=None):
    st = RECIPES[rkey]
    texmap = STD_TEX if st['units'] == STD else ARAB_TEX
    texs = _template_textures(tfolder)
    names = {n for n, _ in texs}
    own = OWN_TEX.get(st['units'])
    if own and st['units'] in OWN_ADDS:     # own textures for some troops, the template's for the others
        texs = [(n, p) for n, p in texs if n not in own]; names |= set(own)
    elif own:                   # a unit file with its own texture plan: no template textures, elite or extra paintings
        texs, names = [], set(own)
    # Mameluke body needed by the Asia/India files when the template folder lacks it
    if st['units'] in (ASIA, INDIA) and 'Caballeria/Mameluko' not in names:
        eg = os.path.join(DATA, 'Models', '08Egipto', 'Caballeria')
        texs += [('Caballeria/Mameluko', os.path.join(eg, 'Mameluko.dds')), ('Caballeria/MamelukoCaballo', os.path.join(eg, 'MamelukoCaballo.dds'))]
    if st['units'] in (ASIA, AFRICA, PACIFIC):          # the horse troops that replace the camels need horse+rider textures
        for n in ('Caballeria/Husar', 'Caballeria/HusarCaballo', 'Caballeria/Lancero', 'Caballeria/LanceroCaballo'):
            if n not in names:
                ot = os.path.join(DATA, 'Models', '07Otomano', n.replace('/', os.sep) + '.dds')
                texs.append((n, ot))
    # elite blocks of the unit file (ELITE_BLOCKS): painted below from the Arab-set texture of the block's body
    # (ELITE_SRC), in the signature recipe (SIGNATURE) for the nation's own signature troop, else in its recipe;
    # mounts copied. These names leave the template / extra-troop passes.
    elite_tex = {}                                      # texture name -> (source texture name, recipe or None = copy)
    if st['units'] in ELITE_BLOCKS:
        utxt = unit_text(st['units'])
        sig = SIGNATURE.get(country)
        for troop in ELITE_BLOCKS[st['units']]:
            model, tnames = unit_textures(utxt, troop)
            srcs = ELITE_SRC[os.path.splitext(os.path.basename(model))[0]]
            assert len(srcs) == len(tnames), (country, troop, model, tnames)
            est = sig[1] if sig and sig[0] == troop else st
            for k, (n, s) in enumerate(zip(tnames, srcs)):
                elite_tex[n] = (s, est if k == len(tnames) - 1 else None)
        texs = [(n, p) for n, p in texs if n not in elite_tex]
    # extra troop types of the nation (tools/nations.py EXTRA_TROOPS): the paintings its unit file asks for that the
    # template folder lacks, on the body that file gives them (EXTRA_TEX_SRC); riders recoloured, mounts copied
    extra_model = {}
    if NT.EXTRA_TROOPS.get(country):
        utxt = unit_text(st['units'])
        for troop, _ in NT.EXTRA_TROOPS[country]:
            model, tnames = unit_textures(utxt, troop)
            for k, n in enumerate(tnames):
                if n in names or n in extra_model or n in elite_tex:
                    continue
                texs.append((n, os.path.join(DATA, 'Models', EXTRA_TEX_SRC[n], n.replace('/', os.sep) + '.dds')))
                extra_model[n] = model if k == len(tnames) - 1 else None        # the last texture is the man
                names.add(n)
    texmap = dict(texmap, **{n: mdl for n, mdl in extra_model.items() if mdl})
    firsts = {}
    for name, path in texs:
        base = re.sub(r'\d$', '', name)
        rel = 'Models/%s/%s.dds' % (mfolder, name)
        dst = os.path.join(out_root, rel.replace('/', os.sep))
        src = uvdump.load_tex(path)
        if base in texmap:
            model = texmap[base]
            img = retex(model, src, st, rider=base.startswith('Caballeria/'), keep_light=base in KEEP_METAL)
            save_dds(dst, img)
            firsts.setdefault(base, (model, img))
        elif base in MOUNT_OF.values() or name in ('Caballeria/Tirador',):
            if tfolder == mfolder or os.path.dirname(path).startswith(os.path.join(DATA, 'Models', tfolder)) and tfolder in {n['models'] for n in NT.NEW_NATIONS if n['folder'] == mfolder}:
                continue                                        # the template copy made by make_map is fine
            save_dds(dst, src)                                  # borrowed mount texture (Mameluke horse / Ottoman horse)
        written.append(rel)
    for n, (s, est) in elite_tex.items():
        path = next(p for p in (os.path.join(DATA, 'Models', f, s.replace('/', os.sep) + '.dds')
                                for f in (tfolder, '08Egipto', '07Otomano')) if os.path.exists(p))
        rel = 'Models/%s/%s.dds' % (mfolder, n)
        dst = os.path.join(out_root, rel.replace('/', os.sep))
        src = uvdump.load_tex(path)
        save_dds(dst, src if est is None else retex(ARAB_TEX[s], src, est, rider=s.startswith('Caballeria/')))
        written.append(rel)
    for n, (s, model, troop) in (own or {}).items():
        rel = 'Models/%s/%s.dds' % (mfolder, n)
        img = uvdump.load_tex(os.path.join(DATA, 'Models', s.replace('/', os.sep) + '.dds'))
        if model:
            body = os.path.splitext(os.path.basename(model))[0]
            img = retex(model, img, troop_recipe(country, troop, st), rider=n.startswith('Caballeria/'),
                        exact=body in EXACT_PARTS, hat_box=HAT_BOX.get(body), skin_min_v=SKIN_MIN_V.get(body))
            for box in (KEEP_BOX.get(body), KEEP_FILE.get(st['units'], {}).get(body)):
                if box:
                    src = uvdump.load_tex(os.path.join(DATA, 'Models', s.replace('/', os.sep) + '.dds')).convert('RGB')
                    img.paste(src.crop(box), box[:2])
            firsts.setdefault(re.sub(r'\d$', '', n), (model, img))
        save_dds(os.path.join(out_root, rel.replace('/', os.sep)), img)
        written.append(rel)
    # officer figures
    for fn in FIG_FILES:
        src = uvdump.load_tex(os.path.join(FIG, '00Generico', fn + '.tga'))
        rel = 'Game/GameModes/Gestion/Figuras/%s/%s.tga' % (ffolder, fn)
        save_dds(os.path.join(out_root, rel.replace('/', os.sep)), retex_figure(src, st), mips=False)
        written.append(rel)
    for fn in FIG_COPY:
        src = uvdump.load_tex(os.path.join(FIG, '00Generico', fn + '.tga'))
        rel = 'Game/GameModes/Gestion/Figuras/%s/%s.tga' % (ffolder, fn)
        save_dds(os.path.join(out_root, rel.replace('/', os.sep)), src, mips=False)
        written.append(rel)
    # ship hulls with the nation's flag
    design = FL.DESIGNS.get(rkey) or FL.DESIGNS.get(country)
    if design:
        global flag_boxes_current
        for ship in ('Navio', 'Fragata', 'Corbeta'):
            flag_boxes_current = flag_boxes(ship)
            src = uvdump.load_tex(os.path.join(DATA, 'Models', tfolder, 'Barcos', ship + '.tga'))
            rel = 'Models/%s/Barcos/%s.tga' % (mfolder, ship)
            save_dds(os.path.join(out_root, rel.replace('/', os.sep)), retex_hull(src, design))
            written.append(rel)
    # renders for the contact sheet: one infantry + one cavalry
    if render_pair is not None:
        cav = firsts.get('Caballeria/Husar')
        tiles = []
        for key in ('Infanteria/Fusilero', 'Infanteria/Miliciano'):
            inf = firsts.get(key)
            if inf:
                tiles.append(R.render(inf[0], [inf[1]], size=(110, 230), yaw=0.55, pitch=0.26))
        if cav:
            mount = MOUNT_OF['Caballeria/Husar']
            mpath = os.path.join(DATA, 'Models', tfolder, mount.replace('/', os.sep) + '.dds')
            if not os.path.exists(mpath):
                mpath = os.path.join(DATA, 'Models', '07Otomano', mount.replace('/', os.sep) + '.dds')
            tiles.append(R.render(cav[0], [uvdump.load_tex(mpath), cav[1]], size=(170, 230), yaw=0.55, pitch=0.26))
        render_pair[country] = tiles


def build_all(out_root, nations=None, sheet=None):
    """Write every generated file under out_root (game-relative paths). nations: list of country keys or None."""
    written = []
    renders = {}
    for country, rkey, mf, ff, tf in nation_list():
        if nations and country not in nations and rkey not in nations:
            continue
        build_nation(out_root, country, rkey, mf, ff, tf, written, renders)
        print('  %-12s (%s) %s' % (country, rkey, mf))
    for fn, txt in unit_files().items():
        rel = 'Game/GameModes/Batalla/' + fn
        p = os.path.join(out_root, rel.replace('/', os.sep)); os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'wb').write(txt.encode('latin1'))
        written.append(rel)
    if sheet and renders:
        cols = 5; cw, ch = 410, 252
        keys = list(renders)
        rows = (len(keys) + cols - 1) // cols
        img = Image.new('RGB', (cols * cw, rows * ch), (24, 24, 26)); dr = ImageDraw.Draw(img)
        for i, k in enumerate(keys):
            x, y = (i % cols) * cw, (i // cols) * ch
            dr.text((x + 4, y + 3), '%s  [%s]' % (k, UNIT_FILE_OF[k].replace('DefUnidades', '').replace('.sb', '')), fill=(255, 255, 0))
            xx = x + 4
            for t in renders[k]:
                img.paste(t, (xx, y + 18)); xx += t.width + 4
        img.save(sheet)
    return written


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build', 'units', 'out')
    only = sys.argv[2:] or None
    files = build_all(out, only, sheet=os.path.join(ROOT, 'build', 'units', 'all_cultures.png'))
    print(len(files), 'files written under', out)
