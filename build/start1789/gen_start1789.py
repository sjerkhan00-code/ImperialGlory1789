"""1789 start proposal: province economy (mng section 4 vals) and starting armies / fleets.

Reads (never writes) tools/, data/ and mod/. Writes only into build/start1789/:
  province_vals.json        {world_province_key: [14 vals]}   (vals[12], vals[13] = 0: set by nations.py / ports)
  province_vals_step1.json  {enum key: [14 vals]} for the 10 step-1 provinces (Persia ... Siberia)
  province_vals.md          table + justification + original ranges
  armies.json               {player key: [army records exactly as igmod.parse_players builds them]}
  armies_symbolic.json      same, with troop enum names instead of indices (rebuild-proof)
  fleets.json / dbgDefFlotasIniciales_1789.sb   starting fleets (file format of Gestion/dbgDefFlotasIniciales.sb)
  armies.md                 summary + comparison with the original starting armies

Run:  python build/start1789/gen_start1789.py
"""
import os, sys, json, re, unicodedata, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import igmod
import world_nations as WN
import make_map as MM          # import only (main() is guarded); used for WORLD_NAMES / PROVINCES

ORIG = os.path.join(ROOT, 'data', 'Game', 'GameModes', 'DefModeloGestion.mng')
MOD = os.path.join(ROOT, 'mod', 'Game', 'GameModes', 'DefModeloGestion.mng')

# ------------------------------------------------------------------ A. province economy
# vals = [gold, raw materials, food, population, science, commerce, 0,0,0,0,0,0, capital id, port id]
# (gold, raw, food, pop, commerce, science-if-capital, note)
P = {
    # --- Qing China
    'zhili':      (140, 120,  90, 110, 35, 500, 'Beijing: imperial capital, Grand Canal terminus, tribute grain of the empire'),
    'shaanxi':    ( 40,  90,  60,  60, 15, 0, 'Wei valley wheat, Shanxi bankers; loess hills, modest'),
    'sichuan':    ( 60, 130, 120,  90, 15, 0, 'Red Basin "land of abundance": rice, salt wells, repopulated by 1789'),
    'huguang':    ( 60, 110, 130, 100, 20, 0, '"When Huguang ripens the realm is fed": the rice bowl of China'),
    'jiangnan':   (130, 140, 120, 120, 55, 0, 'Richest region on earth: silk, cotton cloth, Yangzhou salt merchants, Suzhou/Hangzhou'),
    'fujian':     ( 70, 110,  60,  70, 45, 0, 'Tea, sugar, Amoy junk trade to Southeast Asia; little arable land'),
    'guangdong':  (110, 100,  90,  90, 55, 0, 'Canton system: sole port for European trade (tea, silk, porcelain for silver)'),
    'yunnan':     ( 50, 150,  50,  45, 12, 0, 'Copper mines minting the empire\'s cash, silver, tin; frontier'),
    'formosa':    ( 30,  70,  70,  30, 20, 0, 'Rice and sugar frontier; Lin Shuangwen revolt crushed 1788'),
    'manchuria':  ( 25, 120,  50,  20,  8, 0, 'Banner homeland closed to Han settlers: ginseng, furs, timber'),
    'innermong':  ( 20,  60,  30,  20, 10, 0, 'Banner pastures, Kalgan caravan trade'),
    'mongolia':   ( 15,  70,  25,  15,  8, 0, 'Khalkha herds and horses; Kyakhta border trade passes through'),
    'qinghai':    ( 10,  50,  20,  10,  5, 0, 'Kokonor pastures, sparse'),
    'tibet':      ( 20,  40,  15,  15,  8, 0, 'Lhasa under ambans; Gorkha invasion 1788-89; barley and wool'),
    'xinjiang':   ( 30,  60,  40,  30, 20, 0, 'Kashgar/Yarkand oases on the Silk Road, jade'),
    'dzungaria':  ( 15,  60,  30,  10,  8, 0, 'Ili military colony, depopulated after the 1750s wars'),
    'amur':       ( 10,  90,  15,   5,  5, 0, 'Forests and sable furs, almost empty'),
    'sakhalin':   (  5,  50,  10,   5,  3, 0, 'Ainu/Nivkh fishing and furs'),
    # --- Japan / Korea
    'honshu':     (150, 110, 100, 115, 40, 350, 'Edo (largest city in the world), Osaka rice exchange, Kyoto crafts'),
    'kyushu':     ( 60,  90,  80,  70, 35, 0, 'Satsuma, Nagasaki (Dutch/Chinese trade), Shikoku'),
    'ezo':        ( 10,  90,  20,   8, 10, 0, 'Matsumae fisheries and Ainu trade; Menashi-Kunashir revolt 1789'),
    'korea':      ( 70, 100,  90,  85, 20, 250, 'Joseon under Jeongjo: rice, ginseng, ~7 million people, closed borders'),
    # --- India
    'pune':       ( 90, 100,  70,  90, 25, 250, 'Peshwa\'s court; Deccan heartland of the Maratha Confederacy'),
    'delhi':      ( 50,  70,  60,  70, 25, 0, 'Mughal capital held by Scindia since 1784; wealth drained by wars'),
    'gujarat':    ( 90, 120,  60,  70, 50, 0, 'Surat and Ahmedabad: cotton textiles, indigo, Indian Ocean trade'),
    'malwa':      ( 50,  90,  70,  55, 25, 0, 'Holkar\'s Indore; opium and cotton'),
    'berar':      ( 40, 110,  70,  50, 12, 0, 'Bhonsle of Nagpur; cotton black soil'),
    'orissa':     ( 35,  70,  80,  45, 12, 0, 'Rice delta under the Nagpur Bhonsle'),
    'rajput':     ( 40,  60,  40,  50, 15, 0, 'Jaipur/Jodhpur/Udaipur states paying chauth; dry'),
    'mysore':     ( 85, 120,  75,  70, 25, 250, 'Tipu Sultan\'s modernised state: sandalwood, silk, state trade monopolies'),
    'hyderabad':  ( 90, 120,  70,  80, 25, 200, 'Nizam\'s Deccan; Golconda diamonds, large revenue'),
    'punjab':     ( 60,  90,  90,  70, 20, 150, 'Sikh misls; five-river wheat land, Lahore and Amritsar'),
    'nepal':      ( 25,  60,  40,  35, 12, 100, 'Gorkha kingdom, Kathmandu valley, trans-Himalayan trade'),
    'bengal':     (130, 130, 130, 120, 55, 0, 'Richest province of India: muslin, silk, rice, saltpetre; EIC revenue base'),
    'bihar':      ( 60, 120, 100,  80, 25, 0, 'Saltpetre for Europe\'s gunpowder, opium monopoly'),
    'bombay':     ( 50,  60,  35,  40, 45, 0, 'EIC island port, cotton trade to Canton'),
    'carnatic':   ( 70,  90,  80,  70, 45, 0, 'Madras/Coromandel: calico and chintz exports'),
    'circars':    ( 40,  70,  75,  50, 20, 0, 'Coastal rice strip ceded to the EIC 1766'),
    'awadh':      ( 80,  90, 110, 100, 25, 0, 'Nawab of Oudh, Lucknow; fertile and populous Ganges doab'),
    'assam':      ( 25,  90,  70,  30, 10, 100, 'Ahom kingdom weakened by the Moamoria rebellion; silk, timber'),
    'travancore': ( 50,  80,  50,  45, 40, 200, 'Pepper and cardamom monopoly, Dutch/English trade'),
    'sindh':      ( 35,  50,  60,  40, 20, 0, 'Talpur Mirs (1783), Indus irrigation'),
    'multan':     ( 30,  50,  60,  35, 15, 0, 'Durrani governorate on the Indus'),
    'ceylon':     ( 50,  90,  50,  35, 40, 0, 'VOC cinnamon monopoly, pearls, Trincomalee harbour'),
    # --- Afghanistan, Central Asia, Arabia
    'kabul':      ( 45,  70,  40,  50, 20, 150, 'Timur Shah\'s capital (from 1776), caravan hub'),
    'kandahar':   ( 30,  50,  35,  35, 15, 0, 'Old Durrani capital, irrigated oasis'),
    'peshawar':   ( 35,  50,  50,  45, 15, 0, 'Winter capital, fertile vale'),
    'baluch':     ( 10,  40,  15,  15,  8, 0, 'Khanate of Kalat, desert'),
    'kashmir':    ( 50,  80,  50,  40, 25, 0, 'Shawl weaving, saffron'),
    'kokand':     ( 35,  60,  50,  35, 20, 0, 'Fergana valley khanate, silk and cotton'),
    'semirechye': ( 10,  50,  25,  10,  8, 0, 'Kazakh Middle Horde pastures'),
    'hejaz':      ( 40,  25,  15,  25, 40, 0, 'Mecca/Medina pilgrimage, Jeddah transit trade'),
    'najd':       ( 10,  30,  15,  15,  8, 0, 'First Saudi state at Diriyah, desert oases'),
    'yemen':      ( 45,  50,  40,  40, 45, 150, 'Mocha coffee, terraced highlands; Zaydi imamate'),
    'muscat':     ( 60,  40,  25,  30, 50, 150, 'Omani maritime empire: Gulf and Indian Ocean shipping, dates'),
    'somalinord': ( 15,  40,  15,  15, 20, 0, 'Berbera and Zeila, livestock and frankincense'),
    'massawa':    ( 20,  30,  15,  15, 25, 0, 'Red Sea port, Ethiopian outlet'),
    # --- Southeast Asia
    'ava':        ( 60, 110,  90,  70, 20, 150, 'Konbaung Burma under Bodawpaya; Irrawaddy rice, rubies, teak'),
    'pegu':       ( 40,  90, 100,  45, 25, 0, 'Lower Burma rice and teak, Rangoon'),
    'arakan':     ( 20,  50,  50,  25, 10, 0, 'Conquered by Burma 1785'),
    'siam':       ( 70,  90, 100,  60, 35, 200, 'Rama I\'s new Bangkok; rice, junk trade with China'),
    'laos':       ( 15,  60,  40,  20,  5, 0, 'Vientiane/Luang Prabang under Siam, forest products'),
    'cambodia':   ( 20,  50,  60,  25, 10, 0, 'Tonle Sap fish and rice; Siamese vassal'),
    'annam':      ( 40,  70,  70,  60, 15, 200, 'Tay Son centre, Phu Xuan (Hue); Quang Trung'),
    'tonkin':     ( 50,  70, 100,  80, 20, 0, 'Red River delta, densely populated'),
    'cochin':     ( 45,  60, 110,  45, 25, 150, 'Mekong delta rice; Nguyen Anh retook Saigon 1788'),
    'malaya':     ( 40,  90,  30,  25, 40, 100, 'Johor-Riau: tin, Straits trade'),
    'aceh':       ( 40,  70,  35,  30, 35, 0, 'Pepper sultanate, half the world\'s pepper'),
    'borneonord': ( 25,  90,  25,  15, 25, 100, 'Brunei: camphor, sago, birds\' nests'),
    'mindanao':   ( 15,  60,  40,  20, 15, 0, 'Maguindanao/Sulu raiders, slaves and pearls'),
    'borneosor':  ( 25,  90,  25,  20, 15, 0, 'Banjarmasin pepper, gold and diamonds (VOC)'),
    'java':       (110, 110, 120, 110, 50, 0, 'Batavia, VOC heart: coffee, sugar, rice; very populous'),
    'sumatra':    ( 40,  80,  40,  30, 30, 0, 'Palembang tin, Bencoolen pepper'),
    'moluccas':   ( 70,  40,  25,  15, 50, 0, 'Spice Islands: cloves and nutmeg monopoly'),
    'celebes':    ( 30,  60,  45,  35, 25, 0, 'Makassar, Bugis traders'),
    'sunda':      ( 15,  40,  30,  25, 10, 0, 'Lesser Sundas, sandalwood, horses'),
    'timor':      ( 15,  40,  20,  15, 15, 0, 'Sandalwood; Portuguese Dili and Dutch Kupang'),
    'luzon':      ( 60,  80,  80,  60, 45, 0, 'Manila galleon (silver for silk), tobacco monopoly from 1782'),
    'visayas':    ( 25,  50,  60,  40, 15, 0, 'Cebu, Iloilo: rice and sugar'),
    'nguineavest':(  5,  50,  10,  10,  5, 0, 'Bird of paradise plumes, jungle'),
    'nguineaost': (  5,  40,  15,  10,  3, 25, 'Papuan villages, untouched by trade'),
    # --- Oceania
    'nsw':        (  5,  30,  10,   5,  3, 0, 'Penal colony founded Jan 1788; near famine in 1789'),
    'northaus':   (  3,  25,  10,   5,  2, 25, 'Arnhem Land; Macassan trepang visits'),
    'westaus':    (  2,  20,   5,   3,  1, 0, 'New Holland desert coast'),
    'southaus':   (  2,  20,   8,   4,  1, 0, 'Nuyts Land, arid'),
    'queensland': (  3,  30,  12,   6,  2, 0, 'Carpentaria, tropical coast'),
    'tasmania':   (  2,  30,   8,   3,  1, 0, 'Van Diemen\'s Land, forests'),
    'nznorth':    (  8,  60,  30,  15,  5, 50, 'Maori iwi, kumara gardens, kauri; whalers soon'),
    'nzsouth':    (  3,  50,  15,   5,  3, 0, 'Sparse Ngai Tahu settlement, greenstone'),
    # --- Siberia
    'tomsk':      ( 20,  90,  30,  20, 10, 0, 'Tobolsk: seat of Siberia, grain belt of western Siberia'),
    'yenisei':    ( 10,  80,  15,   8,  8, 0, 'Furs and taiga'),
    'irkutsk':    ( 20,  80,  20,  12, 30, 0, 'Kyakhta tea-for-fur trade with China'),
    'yakutsk':    ( 10,  70,   8,   5, 10, 0, 'Sable furs, mammoth ivory'),
    'okhotsk':    (  5,  50,  10,   3,  8, 0, 'Pacific port of Siberia, fur trade to Alaska'),
    'kamchatka':  (  5,  60,  10,   3, 10, 0, 'Petropavlovsk, sea otter'),
    'chukotka':   (  2,  30,   5,   2,  2, 0, 'Unsubdued Chukchi, tundra'),
    # --- West Africa / Sahara
    'senegal':    ( 30,  40,  30,  25, 30, 0, 'Saint-Louis and Goree: gum arabic, slave trade'),
    'sierra':     ( 10,  40,  25,  15, 15, 0, 'Province of Freedom (1787), Bunce Island'),
    'futa':       ( 20,  50,  50,  35, 15, 100, 'Futa Jallon almamate, cattle, Fulani scholars'),
    'segu':       ( 35,  50,  70,  45, 20, 100, 'Bambara empire on the Niger, grain and slaves'),
    'timbuktu':   ( 30,  30,  25,  20, 35, 0, 'Saharan entrepot: gold, salt, books'),
    'mossi':      ( 15,  40,  50,  35, 10, 50, 'Mossi kingdoms, horses and millet'),
    'ashanti':    ( 90,  70,  50,  45, 30, 100, 'Asante: gold fields, kola, the richest state of Guinea'),
    'ivory':      ( 60,  50,  40,  30, 40, 0, 'Gold Coast forts (Cape Coast, Elmina), gold and slave exports'),
    'oyo':        ( 40,  50,  70,  60, 30, 100, 'Oyo under Abiodun; cavalry empire, Dahomey tributary, Porto-Novo trade'),
    'hausa':      ( 50,  70,  70,  70, 35, 0, 'Kano/Katsina cotton cloth and leather, dense population'),
    'bornu':      ( 35,  50,  50,  45, 25, 150, 'Old Kanuri empire on Lake Chad, Islamic learning'),
    'air':        ( 10,  30,  10,   8, 15, 0, 'Agadez Tuareg sultanate, salt caravans'),
    'fezzan':     ( 10,  25,  10,   8, 20, 0, 'Murzuk, trans-Saharan slave route'),
    # --- Central / Southern / East Africa
    'cameroun':   ( 15,  70,  40,  30, 15, 0, 'Duala coast trade, forest'),
    'loango':     ( 20,  60,  35,  25, 30, 0, 'Loango Bay slaving port'),
    'kongo':      ( 25,  60,  50,  35, 20, 100, 'Kingdom of Kongo, fragmented by civil wars'),
    'angola':     ( 25,  50,  30,  20, 35, 0, 'Luanda: largest slave port of the Atlantic'),
    'ubangi':     (  5,  60,  30,  20,  5, 0, 'Rainforest, unknown to Europeans'),
    'lunda':      ( 25,  70,  40,  30, 15, 50, 'Mwata Yamvo empire, tribute and slave trade'),
    'luba':       ( 15,  70,  40,  30, 10, 0, 'Luba kingdom, iron and copper'),
    'kazembe':    ( 20,  70,  35,  25, 15, 0, 'Copperbelt, link to Mozambique'),
    'rozvi':      ( 40,  60,  40,  30, 15, 50, 'Changamire Rozvi, Zimbabwe gold'),
    'mozambique': ( 25,  50,  25,  15, 30, 0, 'Ivory and gold via Sena and Quelimane'),
    'swahili':    ( 40,  50,  30,  25, 45, 0, 'Zanzibar and Kilwa under Oman: ivory, slaves, cloves soon'),
    'somalisor':  ( 15,  40,  20,  15, 25, 0, 'Benadir ports, Mogadishu'),
    'madagascar': ( 25,  80,  70,  40, 20, 100, 'Merina unification under Andrianampoinimerina; rice'),
    'natal':      ( 10,  50,  50,  30,  5, 50, 'Nguni chiefdoms, cattle'),
    'kalahari':   (  5,  30,  20,  10,  5, 25, 'Tswana towns on the desert edge'),
    'namibia':    (  3,  30,  10,   5,  3, 0, 'Nama pastoralists'),
    'cape':       ( 25,  40,  50,  15, 35, 0, 'VOC refreshment station: wine, wheat, ~20,000 colonists'),
    'buganda':    ( 25,  60,  80,  45, 10, 50, 'Lakeside banana kingdom, canoe fleets'),
    'ethiopia':   ( 40,  80,  70,  60, 15, 150, 'Gondar in the Era of the Princes; highland grain'),
    'sennar':     ( 25,  50,  50,  30, 20, 100, 'Funj sultanate in decline, Blue Nile grain'),
    'nubia':      ( 10,  30,  25,  15, 10, 0, 'Dongola and the Nile cataracts'),
    'darfur':     ( 25,  50,  40,  30, 25, 100, 'Keira sultanate, Forty Days Road caravans to Egypt'),
    'wadai':      ( 15,  40,  30,  20, 15, 0, 'Sahelian sultanate, slave raids'),
    'bahrghazal': (  5,  60,  30,  15,  3, 0, 'Swamps and savanna, cattle peoples'),
    'upperegypt': ( 35,  50,  90,  50, 20, 0, 'Said: Nile grain, Mamluk beys'),
}
# the 10 step-1 provinces (make_map.PROVINCES 1..10); capitals keep their present vals[4] science
STEP1 = {
    'SAHARA_OCCIDENTAL': (5, 30, 10, 8, 15, 'Western Sahara: Berber caravans, almost empty'),
    'TUAT':       (10, 30, 15, 10, 20, 'Saharan oases, trans-Saharan crossroads (Sahara capital)'),
    'ARABIA':     (20, 40, 20, 25, 30, 'Central Arabia (Arabia capital): Wahhabi Najd and Gulf coast'),
    'OMAN':       (40, 40, 25, 25, 45, 'Inner Oman and the Gulf coast, dates and pearls'),
    'PERSIA':     (70, 90, 60, 70, 30, 'Iranian plateau: Shiraz/Isfahan, Zand-Qajar war; silk and carpets'),
    'KHORASAN':   (35, 70, 40, 35, 20, 'Mashhad, eastern marches, turquoise'),
    'TURKESTAN':  (40, 60, 50, 40, 25, 'Bukhara/Khiva oases, cotton and Silk Road'),
    'KAZAKHSTAN': (10, 70, 30, 15, 10, 'Kazakh steppe, horses and sheep'),
    'URAL':       (40, 150, 30, 25, 15, 'Ural ironworks: largest iron producer of the world in 1789'),
    'SIBERIA':    (15, 90, 20, 10, 10, 'West Siberian taiga, furs'),
}

FIELD = ['gold', 'raw materials', 'food', 'population', 'science', 'commerce']


def province_part():
    m = igmod.Mng(open(ORIG, 'rb').read())
    orig = [r for r in igmod.Mng.parse_provinces(m.section(4)) if not r['sea']]
    world = json.load(open(os.path.join(ROOT, 'build', 'world_provinces.json'), encoding='utf8'))
    assert set(world) == set(P), (set(world) ^ set(P))
    capital_of = {n[3][0]: n[0] for n in WN.NATIONS}
    owner = {}
    for n in WN.NATIONS:
        for k in n[3]:
            owner[k] = n[0]
    for k, w in world.items():
        owner.setdefault(k, WN.EXTRA_OWNER.get(k, MM.WORLD_OWNER.get(w['owner'], 'free')))
    out, out1 = {}, {}
    for k in sorted(P):
        g, r, f, p, c, sci, note = P[k]
        assert (sci > 0) == (k in capital_of), k
        out[k] = [g, r, f, p, sci, c, 0, 0, 0, 0, 0, 0, 0, 0]
    mm = igmod.Mng(open(MOD, 'rb').read())
    cur = {r['ltext'][len('LTEXT_PROVINCIA_'):]: r['vals'] for r in igmod.Mng.parse_provinces(mm.section(4))}
    for k, (g, r, f, p, c, note) in STEP1.items():
        sci = cur.get(k, [0] * 14)[4]
        out1[k] = [g, r, f, p, sci, c, 0, 0, 0, 0, 0, 0, 0, 0]
    def dump(d, fn):
        lines = [' %s: %s' % (json.dumps(k), json.dumps(d[k])) for k in d]
        open(os.path.join(HERE, fn), 'w').write('{\n' + ',\n'.join(lines) + '\n}\n')
    dump(dict(sorted(out.items())), 'province_vals.json')
    dump(out1, 'province_vals_step1.json')

    # ---- markdown
    def rng(i, rows):
        v = [x['vals'][i] for x in rows]
        return '%d-%d (median %d)' % (min(v), max(v), sorted(v)[len(v) // 2])
    ocs = igmod.Mng.parse_countries(m.section(3))
    cen = igmod.Mng.parse_enum(m.table(1))
    byidx = {x['idx']: x for x in orig}
    caps = [x for x in orig if x['vals'][12]]
    non = [x for x in orig if not x['vals'][12]]
    L = ['# 1789 province economy proposal', '',
         'Source of the decoding: re_tools (FUN_005c9b20, select-empire FUN_007ca610/FUN_007c9620, FUN_0064c760, '
         'FUN_00669b50). `vals` = two 6-int resource vectors (class "Riqueza", vtable + 6 ints) + capital id + port id:', '',
         '| idx | offset in def | meaning | evidence |', '|---|---|---|---|',
         '| 0 | +0x14 | gold (DINERO) | select-empire gold bar BMBD = sum(+0x14); FUN_0064c760 writes DINERO to vector +4 |',
         '| 1 | +0x18 | raw materials (MAT_PRIMAS) | bar BMBR = sum(+0x18); vector +8 |',
         '| 2 | +0x1c | food (COMIDA) | bar BMBC = sum(+0x1c); vector +0xc |',
         '| 3 | +0x20 | population (POBLACION) | bar BMBP = sum(+0x20); vector +0x10 |',
         '| 4 | +0x24 | science / research capacity (CIENCIA) | "scientific potential" star = sum(+0x24); province window WTCI hidden when 0; only capitals |',
         '| 5 | +0x28 | commerce points (6th Riqueza component) | internal commerce FUN_00669b50: gold = comp6 x VALOR_PUNTOS_COMERCIALES(1.0) x exploitation % (0/75/150/225 by Market/Roads/Stock Exchange); route value FUN_00670420 also uses +0x18 of country riqueza |',
         '| 6-11 | +0x30..+0x44 | second Riqueza vector (same 6 components); +0x2c is its vtable, never read from the file | loader reads slots 5..10 and 12..19, skips 11; always 0 in the original -> keep 0 |',
         '| 12 | +0x48 | capital id (enum table 3, section 5 record) | Inglaterra 1 = LONDRES, Letonia 3 = SANPETESBURGO; set by nations.py |',
         '| 13 | +0x4c | port id (enum table 4) | select-empire port count = provinces with +0x4c != 0; report_ports.md |',
         '', '## Original ranges (51 European/N-African land provinces)', '',
         '| field | 24 capitals | 27 other provinces |', '|---|---|---|']
    for i in range(6):
        L.append('| %d %s | %s | %s |' % (i, FIELD[i], rng(i, caps), rng(i, non)))
    tot = [sum(x['vals'][i] for x in orig) for i in range(6)]
    newtot = [sum(v[i] for v in out.values()) for i in range(6)]
    L += ['', 'Totals: original 51 provinces gold/raw/food/pop/sci/commerce = %s; proposed 134 world provinces = %s.' % (tot, newtot),
          'Original nation sums (gold/raw/food/pop/commerce, original map): ' + '; '.join(
              '%s %s' % (cen[c['idx']], '/'.join(str(sum(byidx[p]['vals'][i] for p in c['provs'] if p in byidx)) for i in (0, 1, 2, 3, 5)))
              for c in ocs if any(p in byidx for p in c['provs'])) + '.',
          'Proposed: values stay inside the original ranges; only the richest Asian cores reach European-capital level '
          '(gold up to 150 vs 195 for England; population 120 and food 130 slightly above the original maxima 110/125 for '
          'Jiangnan/Bengal/Huguang); deserts, tundra and Australia sit at the bottom (2-10).',
          '', '## Nation sums (gold/raw/food/pop/commerce)', '', '| nation | provinces | gold | raw | food | pop | commerce |', '|---|---|---|---|---|---|---|']
    by = collections.defaultdict(list)
    for k in out:
        by[owner[k]].append(k)
    for n in sorted(by, key=lambda n: -sum(out[k][0] for k in by[n])):
        s = [sum(out[k][i] for k in by[n]) for i in (0, 1, 2, 3, 5)]
        L.append('| %s | %d | %d | %d | %d | %d | %d |' % (n, len(by[n]), *s))
    L += ['', '## Proposed values', '',
          'vals[4] (science) is given for capitals only; vals[12]/vals[13] stay 0 here (nations.py sets the capital id, ports.py the port). '
          'If province_vals.json is used, nations.py should stop overwriting vals[4] with max(template, 200).', '',
          '| key | owner | gold | raw | food | pop | sci | trade | why |', '|---|---|---|---|---|---|---|---|---|']
    for k in sorted(out, key=lambda k: (owner[k], k)):
        v = out[k]
        L.append('| %s | %s | %d | %d | %d | %d | %s | %d | %s |' % (k, owner[k], v[0], v[1], v[2], v[3], v[4] or '', v[5], P[k][6]))
    L += ['', '## Step-1 provinces (province_vals_step1.json, keyed by enum key; science kept from the current build)', '',
          '| key | gold | raw | food | pop | sci | trade | why |', '|---|---|---|---|---|---|---|---|']
    for k, v in out1.items():
        L.append('| %s | %d | %d | %d | %d | %s | %d | %s |' % (k, v[0], v[1], v[2], v[3], v[4] or '', v[5], STEP1[k][5]))
    open(os.path.join(HERE, 'province_vals.md'), 'w', encoding='utf8').write('\n'.join(L) + '\n')
    return owner


# ------------------------------------------------------------------ B. armies and fleets
# player -> [(province world key or original mesh, officer type, [troop types])]; types are troop enum names
# (table 5) resolved inside the player's own country group (troop record field 14 = country id).
# Officer capacity (troop record field 13 / TiposTropas texts): TENIENTE (Captain) 3, CAPITAN (Colonel) 4,
# GENERAL 5, MARISCAL 6 troops. The officer is also the first entry of the units list (as in every original army).
ARMIES = {
    'JUG_QING': [
        ('zhili', 'CAPITAN', ['CAB_LANCERO', 'CAB_HUSAR', 'MILICIA', 'CANON'], 'Eight Banners of the capital'),
        ('sichuan', 'TENIENTE', ['MILICIA', 'TIRADOR'], 'Green Standard, veterans of the Jinchuan wars'),
        ('guangdong', 'TENIENTE', ['MILICIA', 'TIRADOR'], 'Liangguang army back from the Vietnam expedition (Dong Da, 1789)'),
        ('dzungaria', 'TENIENTE', ['CAB_HUSAR', 'CAB_LANCERO'], 'Ili banner garrison'),
    ],
    'JUG_JAPAN': [
        ('honshu', 'TENIENTE', ['TIRADOR', 'MILICIA', 'CAB_LANCERO'], 'Shogunal hatamoto: teppo ashigaru, yari, mounted samurai'),
        ('kyushu', 'TENIENTE', ['TIRADOR', 'MILICIA'], 'Satsuma and the Nagasaki guard'),
    ],
    'JUG_JOSEON': [('korea', 'TENIENTE', ['TIRADOR', 'MILICIA', 'CANON'], 'Five Army Camps of Hanseong')],
    'JUG_MARATHA': [
        ('pune', 'CAPITAN', ['CAB_ELITE', 'CAB_HUSAR', 'CAB_HUSAR', 'CANON'], 'Peshwa\'s household horse (huzurat) and bargirs'),
        ('delhi', 'TENIENTE', ['FUSILERO', 'FUSILERO', 'CANON'], 'Scindia\'s brigades drilled by de Boigne'),
        ('malwa', 'TENIENTE', ['CAB_HUSAR', 'CAB_HUSAR'], 'Holkar\'s light horse'),
    ],
    'JUG_MYSORE': [('mysore', 'CAPITAN', ['FUSILERO', 'FUSILERO', 'CAB_HUSAR', 'CANON'], 'Tipu\'s French-drilled infantry and silladar horse')],
    'JUG_HYDERABAD': [('hyderabad', 'TENIENTE', ['FUSILERO', 'CAB_HUSAR', 'MILICIA'], 'Nizam\'s army with Raymond\'s French corps')],
    'JUG_PUNJAB': [('punjab', 'TENIENTE', ['CAB_HUSAR', 'CAB_HUSAR', 'MILICIA'], 'Sikh misl cavalry (Dal Khalsa)')],
    'JUG_NEPAL': [('nepal', 'TENIENTE', ['TIRADOR', 'MILICIA'], 'Gorkha companies (invading Tibet 1788-89)')],
    'JUG_DURRANI': [
        ('kabul', 'TENIENTE', ['CAB_HUSAR', 'CAB_LANCERO', 'CAM_TIRADOR'], 'Durrani horse and zamburak camel guns'),
        ('peshawar', 'TENIENTE', ['CAB_HUSAR', 'TIRADOR'], 'Winter-capital army, jezailchis'),
    ],
    'JUG_BURMA': [
        ('ava', 'TENIENTE', ['MILICIA', 'TIRADOR', 'CANON'], 'Bodawpaya\'s royal army'),
        ('pegu', 'TENIENTE', ['MILICIA', 'TIRADOR'], 'Siam front (war of 1785-89)'),
    ],
    'JUG_SIAM': [('siam', 'TENIENTE', ['MILICIA', 'TIRADOR', 'CAB_HUSAR'], 'Rama I\'s army that repelled the Burmese 1785-86')],
    'JUG_VIETNAM': [
        ('annam', 'TENIENTE', ['MILICIA', 'TIRADOR', 'CANON'], 'Quang Trung\'s Tay Son army'),
        ('tonkin', 'TENIENTE', ['MILICIA', 'TIRADOR'], 'Victors of Dong Da (Jan 1789)'),
    ],
    'JUG_NGUYEN': [('cochin', 'TENIENTE', ['FUSILERO', 'MILICIA'], 'Nguyen Anh\'s army with French volunteers (Saigon 1788)')],
    'JUG_MALAYA': [('malaya', 'TENIENTE', ['MILICIA', 'TIRADOR'], 'Johor-Riau and Bugis levies')],
    'JUG_BRUNEI': [('borneonord', 'TENIENTE', ['MILICIA'], 'Sultan\'s levies')],
    'JUG_MAORI': [('nznorth', 'TENIENTE', ['MILICIA', 'MILICIA'], 'Taua war parties')],
    'JUG_ETHIOPIA': [('ethiopia', 'TENIENTE', ['MILICIA', 'CAB_LANCERO', 'TIRADOR'], 'Ras\' levies and highland horse')],
    'JUG_OMAN': [
        ('muscat', 'TENIENTE', ['MILICIA', 'CAM_LANCERO'], 'Al Busaid tribesmen and Baluchi mercenaries'),
        ('swahili', 'TENIENTE', ['MILICIA'], 'Zanzibar garrison'),
    ],
    'JUG_SENNAR': [('sennar', 'TENIENTE', ['CAB_LANCERO', 'MILICIA'], 'Funj armoured horse')],
    'JUG_DARFUR': [('darfur', 'TENIENTE', ['CAB_LANCERO', 'CAM_LANCERO', 'MILICIA'], 'Keira cavalry, conquerors of Kordofan 1785')],
    'JUG_BORNU': [('bornu', 'TENIENTE', ['CAB_LANCERO', 'MILICIA'], 'Kanuri quilted cavalry')],
    'JUG_SEGU': [('segu', 'TENIENTE', ['MILICIA', 'CAB_HUSAR'], 'Bambara tonjon')],
    'JUG_ASHANTI': [('ashanti', 'TENIENTE', ['TIRADOR', 'TIRADOR', 'MILICIA'], 'Asante musket armies')],
    'JUG_OYO': [('oyo', 'TENIENTE', ['CAB_LANCERO', 'CAB_HUSAR', 'MILICIA'], 'Oyo cavalry under Alaafin Abiodun')],
    'JUG_KONGO': [('kongo', 'TENIENTE', ['MILICIA', 'TIRADOR'], 'Musketeers of Mbanza Kongo')],
    'JUG_LUNDA': [('lunda', 'TENIENTE', ['MILICIA', 'MILICIA'], 'Mwata Yamvo\'s warriors')],
    'JUG_BUGANDA': [('buganda', 'TENIENTE', ['MILICIA'], 'Kabaka\'s levies')],
    'JUG_ROZVI': [('rozvi', 'TENIENTE', ['MILICIA'], 'Changamire warriors')],
    'JUG_MADAGASCAR': [('madagascar', 'TENIENTE', ['MILICIA', 'TIRADOR'], 'Merina musketeers')],
    'JUG_ABORIGINES': [('northaus', 'TENIENTE', ['MILICIA'], 'Clan warriors')],
    'JUG_YEMEN': [('yemen', 'TENIENTE', ['MILICIA', 'TIRADOR'], 'Zaydi tribal levies')],
    'JUG_NGUNI': [('natal', 'TENIENTE', ['MILICIA', 'MILICIA'], 'Nguni regiments (pre-Shaka)')],
    'JUG_BECHUANA': [('kalahari', 'TENIENTE', ['MILICIA'], 'Tswana mephato')],
    'JUG_AHOM': [('assam', 'TENIENTE', ['MILICIA'], 'Paik militia (Moamoria rebellion)')],
    'JUG_TRAVANCORE': [('travancore', 'TENIENTE', ['FUSILERO', 'MILICIA'], 'De Lannoy-trained battalions, Nedumkotta lines')],
    'JUG_FUTA': [('futa', 'TENIENTE', ['CAB_HUSAR', 'MILICIA'], 'Fulani horse')],
    'JUG_MOSSI': [('mossi', 'TENIENTE', ['CAB_LANCERO', 'MILICIA'], 'Mossi cavalry')],
    'JUG_PAPUA': [('nguineaost', 'TENIENTE', ['MILICIA'], 'Village warriors')],
}
# extra armies for players that already have their European armies (appended, not replacing)
COLONIAL = {
    'JUG_GRAN_BRETANYA': [
        ('bengal', 'TENIENTE', ['FUSILERO', 'CANON'], 'Bengal Army (Fort William)'),
        ('carnatic', 'TENIENTE', ['FUSILERO', 'CAB_DRAGON'], 'Madras Army (Fort St George)'),
        ('bombay', 'TENIENTE', ['FUSILERO'], 'Bombay Army'),
        ('nsw', 'TENIENTE', ['FUSILERO'], 'New South Wales Marine Corps'),
    ],
    'JUG_BATAVIA': [
        ('java', 'TENIENTE', ['FUSILERO', 'MILICIA'], 'VOC garrison of Batavia and native auxiliaries'),
        ('cape', 'TENIENTE', ['MILICIA'], 'Cape burgher commandos'),
        ('ceylon', 'TENIENTE', ['FUSILERO'], 'VOC Ceylon garrison (Colombo, Trincomalee)'),
    ],
    'JUG_PORTUGAL': [
        ('angola', 'TENIENTE', ['MILICIA'], 'Luanda garrison and guerra preta'),
        ('mozambique', 'TENIENTE', ['MILICIA'], 'Mozambique Island garrison'),
    ],
    'JUG_ESPANYA': [('luzon', 'TENIENTE', ['FUSILERO', 'MILICIA'], 'Regimiento del Rey, Manila')],
    'JUG_FRANCIA': [('senegal', 'TENIENTE', ['FUSILERO'], 'Bataillon d\'Afrique, Saint-Louis/Goree')],
    'JUG_RUSIA': [
        ('tomsk', 'TENIENTE', ['CAB_LANCERO', 'MILICIA'], 'Siberian Cossacks and line battalion, Tobolsk'),
        ('irkutsk', 'TENIENTE', ['MILICIA'], 'Irkutsk/Kyakhta garrison'),
        # 2026-10-23: Sweden took the 60-man capital garrison in turn 2; Russia was strong in 1789
        ('Letonia', 'CAPITAN', ['GRANADERO', 'FUSILERO', 'CANON'],
         'Guards and the Army of Finland (Musin-Pushkin) covering St Petersburg in the Russo-Swedish War 1788-90'),
        ('Kiev', 'CAPITAN', ['FUSILERO', 'CAB_LANCERO', 'CANON'],
         'Army of Ekaterinoslav (Potemkin, Suvorov) facing the Ottomans, Russo-Turkish War 1787-92'),
    ],
}
# fleets: player -> [(name, sea zone key of sea_zones.json, BARCO_INICIAL, [extra BARCOS])]
FLEETS = {
    'JUG_GRAN_BRETANYA': [('Fleet ING East Indies', 'coromandel', 'FRAGATA', ['CORBETA'], 'Royal Navy East Indies squadron, Madras'),
                          ('Fleet ING Bombay Marine', 'malabar', 'CORBETA', [], 'EIC Bombay Marine'),
                          ('Fleet ING Sirius', 'nsw', 'CORBETA', [], 'HMS Sirius of the First Fleet')],
    'JUG_BATAVIA': [('Fleet BAT Batavia', 'java', 'FRAGATA', ['CORBETA'], 'VOC and Dutch navy at Batavia')],
    'JUG_PORTUGAL': [('Fleet POR Luanda', 'angola', 'CORBETA', [], 'Angola station')],
    'JUG_ESPANYA': [('Fleet ESP Manila', 'scs_n', 'FRAGATA', [], 'Manila galleon escort')],
    'JUG_FRANCIA': [('Fleet FRA Indes', 'indian', 'CORBETA', [], 'Station des Indes (Ile de France)')],
    'JUG_RUSIA': [('Fleet RUS Okhotsk', 'okhotsk', 'CORBETA', [], 'Okhotsk flotilla (Billings expedition)')],
    'JUG_OMAN': [('Fleet OMA I', 'gulf', 'FRAGATA', ['CORBETA'], 'Omani navy, strongest native fleet of the Indian Ocean'),
                 ('Fleet OMA II', 'zanzibar', 'CORBETA', [], 'Zanzibar dhows')],
    'JUG_QING': [('Fleet QIN I', 'scs_n', 'CORBETA', [], 'Guangdong war junks'),
                 ('Fleet QIN II', 'formosa', 'CORBETA', [], 'Fujian fleet (Taiwan campaign 1787-88)')],
    'JUG_JAPAN': [('Fleet JAP I', 'japan_pac', 'CORBETA', [], 'Coastal guard boats (sakoku)')],
    'JUG_JOSEON': [('Fleet JOS I', 'japan_sea', 'CORBETA', [], 'Joseon navy, Busan')],
    'JUG_BURMA': [('Fleet BUR I', 'andaman', 'CORBETA', [], 'Irrawaddy war boats')],
    'JUG_SIAM': [('Fleet SIA I', 'siam', 'CORBETA', [], 'Royal junks of Bangkok')],
    'JUG_NGUYEN': [('Fleet NGU I', 'scs_s', 'CORBETA', [], 'Nguyen Anh\'s European-rigged ships')],
    'JUG_MALAYA': [('Fleet MAL I', 'malacca', 'CORBETA', [], 'Bugis/Johor prahus')],
}


def army_part(owner):
    mm = igmod.Mng(open(MOD, 'rb').read())
    penum = igmod.Mng.parse_enum(mm.table(0))
    tenum = igmod.Mng.parse_enum(mm.table(5))
    provs = igmod.Mng.parse_provinces(mm.section(4))
    by_mesh = {r['name']: r for r in provs}
    players = {penum[r['idx']]: r for r in igmod.parse_players(mm.section(2))}
    import struct
    group = collections.defaultdict(dict)        # country id -> troop enum name -> idx (first)
    for rec in igmod.split_records(mm.section(7), 'troop'):
        _, p = igmod.rec_strings(rec, 4)
        idx = struct.unpack_from('<I', rec, 0)[0]
        country = struct.unpack_from('<24I', rec, p)[14]
        group[country].setdefault(tenum[idx], idx)
    world = json.load(open(os.path.join(ROOT, 'build', 'world_provinces.json'), encoding='utf8'))

    def mesh_of(key):
        if key in by_mesh:
            return key
        disp = MM.WORLD_NAMES.get(world[key]['name'], world[key]['name'])
        disp = unicodedata.normalize('NFKD', disp).encode('ascii', 'ignore').decode()
        return 'W' + re.sub(r'[^A-Za-z]', '', disp)

    out, sym, problems = {}, {}, []
    for table, mode in ((ARMIES, 'replace'), (COLONIAL, 'append')):
        for pk, armies in table.items():
            pl = players[pk]
            g = group[pl['country']]
            lst, slst = [], []
            for prov, off, troops, label in armies:
                mesh = mesh_of(prov)
                if mesh not in by_mesh:
                    problems.append('%s: province %s -> %s not in build' % (pk, prov, mesh)); continue
                cap = {'TENIENTE': 3, 'CAPITAN': 4, 'GENERAL': 5, 'MARISCAL': 6}[off]
                assert len(troops) <= cap, (pk, prov)
                missing = [t for t in [off] + troops if t not in g]
                if missing:
                    problems.append('%s: types %s not in country %d' % (pk, missing, pl['country'])); continue
                if mode == 'append' and owner.get(prov) not in (pk[4:], None) and prov in owner:
                    problems.append('%s: %s is owned by %s' % (pk, prov, owner.get(prov)))
                units = [['', g[off], 0]] + [['', g[t], 0] for t in troops]
                lst.append(dict(province=prov, province_idx=by_mesh[mesh]['idx'], name='', officer_name='',
                                officer=g[off], zero=0, units=units))
                slst.append(dict(province=prov, mesh=mesh, officer=off, units=[off] + troops, note=label))
            if mode == 'append':
                base = [dict(province=next(r['name'] for r in provs if r['idx'] == a['province']), province_idx=a['province'],
                             name=a['name'], officer_name=a['officer_name'], officer=a['officer'], zero=a['zero'],
                             units=a['units']) for a in pl['armies']]
                lst = base + lst
                slst = [dict(existing=True, province=b['province'], units=[tenum[u[1]] for u in b['units']]) for b in base] + slst
            out[pk] = lst
            sym[pk] = dict(mode=mode, country=pl['country'], armies=slst)
    json.dump(out, open(os.path.join(HERE, 'armies.json'), 'w'), indent=1)
    json.dump(sym, open(os.path.join(HERE, 'armies_symbolic.json'), 'w'), indent=1)

    # fleets
    import unicodedata as U
    sea = json.load(open(os.path.join(ROOT, 'build', 'sea', 'sea_zones.json'), encoding='utf8'))
    penum2 = set(igmod.Mng.parse_enum(mm.table(2)).values())
    shipnames = set(igmod.Mng.parse_enum(mm.table(13)).values())
    fl, txt = {}, ['', '############################################################################################',
                   '# 1789 world: additional starting fleets (build/start1789/gen_start1789.py)',
                   '# Append these blocks / entries to Game/GameModes/Gestion/dbgDefFlotasIniciales.sb.',
                   '# Players that already have a block (GB, Spain, Portugal, France, Russia, Batavia) need the',
                   '# entries merged INTO their existing block (one block per JUG_ key).',
                   '############################################################################################']
    for pk, fleets in FLEETS.items():
        txt += ['', '.%s' % pk, '[']
        fl[pk] = []
        for name, zone, first, extra, label in fleets:
            disp = U.normalize('NFKD', sea[zone]['name']).encode('ascii', 'ignore').decode()
            ek = 'S_' + re.sub(r'[^A-Z]', '_', disp.upper()).strip('_')
            assert ek in penum2, ek
            assert first in shipnames and all(s in shipnames for s in extra)
            fl[pk].append(dict(NOMBRE=name, PROVINCIA=ek, BARCO_INICIAL=first, BARCOS=extra, note=label))
            txt += [' [ # %s' % label, '  .NOMBRE        "%s"' % name, '  .PROVINCIA     %s' % ek, '  .BARCO_INICIAL %s' % first]
            if extra:
                txt.append('  .BARCOS        [ %s ]' % ' '.join(extra))
            txt.append(' ]')
        txt.append(']')
    json.dump(fl, open(os.path.join(HERE, 'fleets.json'), 'w'), indent=1)
    open(os.path.join(HERE, 'dbgDefFlotasIniciales_1789.sb'), 'w', newline='\r\n').write('\n'.join(txt) + '\n')

    # markdown
    om = igmod.Mng(open(ORIG, 'rb').read())
    oen = igmod.Mng.parse_enum(om.table(0)); ot = igmod.Mng.parse_enum(om.table(5))
    opr = {r['idx']: r['name'] for r in igmod.Mng.parse_provinces(om.section(4))}
    L = ['# 1789 starting armies and fleets', '',
         '## Original starting armies (data/, for comparison)', '', '| player | armies (officer + troops) | troops |', '|---|---|---|']
    for r in igmod.parse_players(om.section(2)):
        s = '; '.join('%s: %s' % (opr[a['province']], '+'.join(ot[u[1]] for u in a['units'])) for a in r['armies'])
        L.append('| %s | %s | %d |' % (oen[r['idx']], s, sum(len(a['units']) - 1 for a in r['armies'])))
    L += ['', 'Great powers start with 3-5 troops (plus 2-3 Captains), minors with 1-3. The proposal keeps the same scale: '
          'Qing and the Marathas 9-10 (a large but obsolete army spread over a huge realm), Mysore 4, mid powers 3-5, '
          'small realms 1-2, colonial garrisons 1-2 troops per presidency.', '',
          '## Proposed armies', '', '| player | province | officer | troops | historical note |', '|---|---|---|---|---|']
    for pk, s in sym.items():
        for a in s['armies']:
            if a.get('existing'):
                continue
            L.append('| %s | %s | %s | %s | %s |' % (pk, a['province'], a['officer'], ', '.join(a['units'][1:]), a['note']))
    L += ['', '## Proposed fleets (dbgDefFlotasIniciales_1789.sb)', '', '| player | sea zone | first ship | extra ships | note |', '|---|---|---|---|---|']
    for pk, f in fl.items():
        for x in f:
            L.append('| %s | %s | %s | %s | %s |' % (pk, x['PROVINCIA'], x['BARCO_INICIAL'], ' '.join(x['BARCOS']), x['note']))
    if problems:
        L += ['', '## Problems', ''] + ['- ' + p for p in problems]
    open(os.path.join(HERE, 'armies.md'), 'w', encoding='utf8').write('\n'.join(L) + '\n')
    return problems


if __name__ == '__main__':
    owner = province_part()
    probs = army_part(owner)
    print('ok; problems:', probs)
