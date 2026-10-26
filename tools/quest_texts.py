"""Quest texts re-themed to the 1789 campaign (TEXT ONLY).

Six of the 16 quests carry names of a later age: Simon Bolivar, Railway, World Fair, 100,000 Sons of St. Louis (all after
1810), Treaty of Amiens (1802) and Universal Declaration of Human Rights (the title of 1948; the 1789 text is the
Declaration of the Rights of Man). Only their LTEXT texts change. The .mng enum table 9 and section 11 records (16 quests,
text keys LTEXT_<Q> / LTEXT_DESC_<Q> / LTEXT_REC_<Q>), Gestion/Quest/DefQuest.sb (requirements, rewards, message keys), the
notification ids and the UI pools stay exactly as they are, so a running campaign (which stores quest state by record id)
is not affected. The keys keep their old (Spanish) spelling: only the displayed words change.

                      old name                              new name (reward unchanged)
  SIMON_BOLIVAR       Simon Bolivar                         Army Reform           (basic infantry upgraded)
  FERROCARRIL         Railway                               Steam                 (Saw Mill in every territory)
  EXPOSICION_UNIVERSAL World Fair                           Exposition            (+1.5 sympathy per turn)
  100.000_HIJOS       100,000 Sons of St. Louis             Army of Conde         (two Marshals with six units)
  PAZ_AMIENS          Treaty of Amiens                      Treaty of Jassy       (Advanced Military Academies)
  DECLARACION_...     Universal Declaration of Human Rights Declaration of the Rights of Man

Kept (period fits the 1789-1815 campaign, no better 1785-1800 stand-in needed): Cartography, Constitution, Encyclopaedia,
Rosetta Stone (1799), Metric System (1795/99), Agrarian Revolution, Medical Revolution, Ruler of the Seas, and the two
Napoleonic quests Emperor Proclamation (1804) and Continental Blockade (1806): the mod's own Era II is 'The Continental
System' and their unlock techs are Era II techs.

Rules every text here obeys (checked by check()): the same %s / %d placeholders in the same order, and no longer than the
original English text of the same key (the quest name slots, descriptions and notifications keep their size).

make_map.quest_texts() writes the English text into Management/TextQuests.sb of all 8 languages (as nations.texts_new does
for the build's other new texts); Russian replaces it from build/i18n/ru_quests.json through apply_translations().
The 'Also activates the <quest> Quest.' lines of the tech descriptions live in techtree.DESCS (English) and ru_quests.json
(Russian); TECH_QUEST lists the names they must carry (check_techtree).
"""
import re

QUEST_REL = 'Management/TextQuests.sb'

TEXTS = {
    # ---- EXPOSICION_UNIVERSAL: "World Fair" -> "Exposition" (the first national exposition of industry, Paris 1798)
    'LTEXT_EXPOSICION_UNIVERSAL': 'Exposition',
    'LTEXT_DESC_EXPOSICION_UNIVERSAL':
        'If we unite our nation in the common task of staging a great Exposition of our industry and arts, our reputation '
        'among other countries will increase enormously while it lasts.',
    'LTEXT_QUEST_COBRO_EXPOSICION':
        'Our reward for the Exposition Quest has been collected, Sir. From this day forward, Sympathy for our Empire across '
        'all countries (neutral and Empires) will increase one and a half points each turn, for an entire year (12 turns).',
    'LTEXT_QUEST_AJENO_EXPOINTERNACIONAL':
        '%s has completed the Exposition Quest. Sympathy for its Empire will increase in all countries for a entire year.',
    # ---- SIMON_BOLIVAR: "Simon Bolivar" -> "Army Reform" (the reforms of the 1790s: new drill, tactics and officers' schools)
    'LTEXT_SIMON_BOLIVAR': 'Army Reform',
    'LTEXT_DESC_SIMON_BOLIVAR':
        'Our generals urge a reform of the army, My Lord! If we agree to fund new drill and tactics, they will provide us '
        'with warfare techniques which will greatly aid the development of our armies.',
    'LTEXT_QUEST_COBRO_SIMON_BOLIVAR':
        'Our reward for the Army Reform Quest has been collected, Sir. All our basic Infantry have been upgraded to their '
        'immediately superior regiments and their numbers restored to full complement, at no cost.',
    'LTEXT_QUEST_AJENO_SIMONBOLIVAR':
        '%s has completed the Army Reform Quest. All its basic Infantry regiments have been upgraded to their immediately '
        'superior regiments, and their numbers restored to full complement.',
    # ---- 100.000_HIJOS: "100,000 Sons of St. Louis" (1823) -> "Army of Conde" (the royalist emigre army, 1792)
    'LTEXT_100000_HIJOS_SAN_LUIS': 'Army of Condé',
    'LTEXT_DESC_100000_HIJOS_SAN_LUIS':
        'My Lord, upon petitioning the help of the royalist émigrés of Condé, we will mobilise reactionary '
        'forces across Europe and all servants loyal to our regime will stand beside us. This Quest is exclusive to '
        'Absolute Monarchies.',
    'LTEXT_QUEST_COBRO_100000_HIJOS':
        'Our reward for the Army of Condé has been collected, Sir. We have received two Marshals, each commanding six '
        'units, at no cost. Make good use of these new troops...',
    'LTEXT_QUEST_AJENO_100000HIJOS':
        '%s has completed the Army of Condé Quest. It has received two Marshals, each with six units under their '
        'command.',
    # ---- FERROCARRIL: "Railway" (1825) -> "Steam" (Watt's engines turning mills and forges, 1780s-90s; the reward is a Saw Mill)
    'LTEXT_FERROCARRIL': 'Steam',
    'LTEXT_DESC_QUEST_FERROCARRIL':
        'Steam engines will soon turn the wheels of our mills and forges, Sir! Let us put the engines of James Watt to work '
        'in every town of our great nation. The output of timber and goods across our Empire will increase dramatically '
        'and our industrial methods will be transformed.',
    'LTEXT_QUEST_COBRO_FERROCARRIL':
        'Our reward for the Steam Quest has been collected, Sir. A Saw Mill has now been constructed in the following '
        'territories: %s.',
    'LTEXT_QUEST_AJENO_FERROCARRIL':
        '%s has completed the Steam Quest. As a consequence, Saw Mills have been built in all its territories.',
    # ---- PAZ_AMIENS: "Treaty of Amiens" (1802) -> "Treaty of Jassy" (Russia and the Ottomans, 9 Jan 1792)
    'LTEXT_PAZ_AMIENS': 'Treaty of Jassy',
    'LTEXT_DESC_PAZ_AMIENS':
        'If we manoeuvre other nations to sign the Treaty of Jassy we will be able to strengthen our military infrastructure '
        'during this time of peace, so that we may be well prepared for future wars.',
    'LTEXT_QUEST_COBRO_PAZAMIENS':
        'Our reward for the Treaty of Jassy Quest has been collected, Sir. An Advanced Military Academy has been '
        'constructed in the following territories: %s.',
    'LTEXT_QUEST_AJENO_PAZAMIENS':
        '%s has completed the Treaty of Jassy Quest. As a consequence, Advanced Military Academies have been built in all '
        'its capitals.',
    # ---- DECLARACION_DERECHOS_HUMANOS: "Universal Declaration of Human Rights" (1948) -> the 1789 Declaration
    'LTEXT_DECLARACION_DERECHOS_HUMANOS': 'Declaration of the Rights of Man',
    'LTEXT_DESC_DECLARACION_DERECHOS_HUMANOS':
        "On being the first nation to publish the Declaration of the Rights of Man, other Empires' subjects will become "
        'conscious of their importance as citizens and revolt against their rulers. This Quest is exclusive to Republics.',
    'LTEXT_QUEST_COBRO_DECDERHUMANOS':
        'Our reward for the Declaration of the Rights of Man Quest has been collected, Sir. We have freed the following '
        'countries from slavery: %s.',
    'LTEXT_QUEST_AJENO_DERECHOSHUMANOS':
        '%s has completed the Declaration of the Rights of Man Quest, and each Empire has lost possession of one country. '
        'We have lost %s!',
    'LTEXT_QUEST_AJENO_DERECHOSHUMANOS_SINPAIS':
        '%s has completed the Declaration of the Rights of Man Quest and each Empire has lost possession of one country. '
        'As we had no neutral countries, our Empire was unaffected.',
}

# tech description key -> the quest name its 'Also activates the ... Quest.' line must carry (techtree.DESCS, English)
TECH_QUEST = {
    'LTEXT_DESC_EDUCACION_BASICA': 'Steam',
    'LTEXT_DESC_MANIOBRAS_MILITARES': 'Exposition',
    'LTEXT_DESC_INSTRUCCION_OFICIALES': 'Treaty of Jassy',
    'LTEXT_DESC_CABALLERIA_AVANZADA': 'Army Reform',
    'LTEXT_DESC_SINDICALISMO': 'Declaration of the Rights of Man',
    'LTEXT_DESC_ILUSTRACION': 'Army of Condé',
}
OLD_NAMES = ('Bolivar', 'Railway', 'World Fair', 'St. Louis', 'Amiens', 'Universal Declaration', 'Human Rights')


def placeholders(s):
    return re.findall(r'%[sd]', s)


def apply(raw):
    """TextQuests.sb bytes (any language) -> bytes with the new texts; encoding and line ends are kept."""
    import igmod
    new, found = igmod.text_set_values(raw, TEXTS)
    missing = set(TEXTS) - found
    assert not missing, ('quest text keys missing in the file', sorted(missing))
    return new


def check(old):
    """old = {key: original English text}. Asserts the rules of the module docstring; returns {key: (old len, new len)}."""
    assert set(old) >= set(TEXTS), sorted(set(TEXTS) - set(old))
    res = {}
    for k, v in TEXTS.items():
        assert '"' not in v and '\n' not in v, k
        assert placeholders(v) == placeholders(old[k]), (k, 'placeholders differ', placeholders(old[k]), placeholders(v))
        assert len(v) <= len(old[k]), (k, 'longer than the original', len(v), len(old[k]))
        assert not any(w in v for w in OLD_NAMES), (k, 'still names the old quest')
        res[k] = (len(old[k]), len(v))
    return res


def check_techtree(descs):
    """descs = techtree.DESCS: every listed tech line names the new quest and none of the old names."""
    for k, name in TECH_QUEST.items():
        v = descs[k]
        assert ('Also activates the %s Quest.' % name in v) or ('Also activates the %s.' % name in v), (k, name)
        assert not any(w in v for w in OLD_NAMES), (k, 'still names the old quest')
