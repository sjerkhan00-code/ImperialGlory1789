"""Scripted historical events of the 1789 campaign (2026-10-22). PREPARED, NOT ENABLED: make_map.HISTORICAL_EVENTS = False.

What the build writes when the switch is True (make_map calls install(); with False nothing here runs and the build is
byte-identical to before):
  Game/LuaScripts/Secuencias/SecuenciaGestionMod.lua   entry script; replaces the .SECUENCIA_TUTORIAL path in
        Game/UI/ModeloGestion/UI_ModeloGestion.sb. In a tutorial campaign it hands over to the ORIGINAL tutorial script
        (SecuenciaTutorialGestion.lua, unchanged); in every other campaign it starts the events.
  Game/LuaScripts/Secuencias/EventosHistoricos1789.lua data-driven events (rendered from EVENTS below).
  LTEXT_EH_<ID>_T / _X / LTEXT_EH_OK in Texto/<lang>/Management/TextUIGestionMapa.sb for all 8 languages.

Why the sequence script and not mainAI.lua / Iniciativas.lua (static RE 2026-10-22, see the report in
.claude/knowledge/ig-data-designer.md "Scripted historical events"):
  - The sequence natives are NOT registered in a normal campaign of the original exe (FUN_00759290 is only a generic UI
    child pass). The registrar is 0x767720 = vtable slot +0x28 of UI_GAME_GESTION_LUA_MANAGER (object [mapUI+0x2c0],
    created for every campaign at 0x826a09); it loads the script named by UI_DATA .SECUENCIA_TUTORIAL, and the original exe
    runs it only in the tutorial (GameState flag 0x2000). mainAI.lua (loaded by FUN_006cf490 with the AI natives) would
    call nil globals and a Lua error in its chunk could break the AI scripts.
  - The original exe has NO native for the current turn or date. The campaign turn is [GameState+0x178] (1 turn = 1 month,
    turn 1 = July 1789, DefCalendarioRevolucionario.sb).

Exe support (nations.py patches 48-50, applied ONLY with HISTORICAL_EVENTS = True; adapted 2026-10-22):
  48  the campaign map UI loads this entry script once per campaign (never in a tutorial campaign) and calls the Lua function
      inicia_secuencia() with the sequence manager left INACTIVE; then it calls the Lua global nations.HIST_TURN_HOOK
      (= eh_inicio_turno, no arguments) at the start of every human turn. on_event NEVER fires in this mode (inactive
      manager): everything is driven from eh_inicio_turno(). A tutorial campaign still starts the sequence the old way,
      through the same .SECUENCIA_TUTORIAL path, so this script hands over to the original tutorial script there.
  49  get_turno_actual() (0 args) = the campaign turn number.
  50  firma_paz_entre(jugA, jugB) (2 args, player keys) = the game's own peace (FUN_00692cc0; only if the two are at war).
open_messagebox with an INACTIVE manager is untested: that is the first thing to look at in game (EH_MENSAJES = false
turns the boxes off and keeps the rest running).

Turn n starts in month (1789-07 + n - 1): Aug 1789 = 2, Jan 1790 = 7, Jan 1791 = 19, Jan 1792 = 31, Jan 1793 = 43.

Save safety: Lua only; no mng record, id or enum touched. Idempotence: an event fires only when the saved campaign turn equals
its turn exactly, at the start of the human's turn (eh_inicio_turno), and at most once per Lua session (EH_DISPARADOS). A save
loaded in a later turn never replays earlier events. Peace (firma_paz_entre) is also idempotent by game state: it does
nothing unless the two nations are at war. Effects (pact, peace, armies, resources) are OFF by default (EH_PERMITE_*); only
the messages are active. Open question: whether the hook also runs when a save is loaded (then a message would show
twice; harmless for messages, not for armies/resources): EH_IGNORA_PRIMERO = true skips the first call after activation.
  pacts  crea_proteccion_mutua_entre(a, b, turns) = an alliance (treaty type 5); it cannot end a war.
  peace  firma_paz_entre(a, b): ends the Russia-Sweden, Austria-Ottoman and Russia-Ottoman wars of the 1789 start.
"""
import os
import re
import sys

SEQ_DIR = 'Game/LuaScripts/Secuencias/'
ENTRY_LUA = SEQ_DIR + 'SecuenciaGestionMod.lua'
EVENTS_LUA = SEQ_DIR + 'EventosHistoricos1789.lua'
UI_REL = 'Game/UI/ModeloGestion/UI_ModeloGestion.sb'
TEXT_REL = 'Management/TextUIGestionMapa.sb'      # loaded by every campaign (ModeloGestion.sb); the cheat texts live there too
BS = chr(92)
ORIG_SCRIPT = BS.join(('Game', 'LuaScripts', 'Secuencias', 'SecuenciaTutorialGestion.lua'))
NEW_SCRIPT = BS.join(('Game', 'LuaScripts', 'Secuencias', 'SecuenciaGestionMod.lua'))
LANGS = ['english', 'spanish', 'French', 'German', 'Italian', 'Polish', 'Czech', 'Russian']
FIRST_MONTH = (1789, 7)          # turn 1 (DefCalendarioRevolucionario.sb .FECHA_INICIO, .TURNO .MESES 1)
TITLE_MAX, BODY_MAX = 40, 300    # characters; the longest original tutorial / messagebox bodies are of this size


def turn_of(year, month):
    """Campaign turn that starts in the given month (turn 1 = July 1789)."""
    return (year - FIRST_MONTH[0]) * 12 + (month - FIRST_MONTH[1]) + 1


# id, date (year, month), optional effects. Effects stay OFF in the Lua (EH_PERMITE_*) until tested in game.
#   pacts  = [(player key, player key, turns)]   crea_proteccion_mutua_entre: a real alliance (treaty type 5)
#   peace  = [(player key, player key)]          firma_paz_entre (exe patch 50): the game's own peace, only if they are at war
#   armies = [(province key, rank, troop, ...)]  crea_ficha for the province owner; resources = (money, food, raw, men) for the human
EVENTS = [
    dict(id='BASTILLA', date=(1789, 8)),
    dict(id='MYSORE_WAR', date=(1789, 12)),
    dict(id='PRUSSIA_POLAND', date=(1790, 3), pacts=[('JUG_PRUSIA', 'JUG_POLONIA', 36)]),
    dict(id='WERELOE', date=(1790, 8), peace=[('JUG_RUSIA', 'JUG_SUECIA')]),
    dict(id='CONSTITUTION', date=(1791, 5)),
    dict(id='SISTOVA', date=(1791, 8), peace=[('JUG_AUSTRIA', 'JUG_OTOMANO')]),
    dict(id='JASSY', date=(1792, 1), peace=[('JUG_RUSIA', 'JUG_OTOMANO')]),
    dict(id='SERINGAPATAM', date=(1792, 3)),
    dict(id='FRENCH_WAR', date=(1792, 4)),
    dict(id='POLISH_WAR', date=(1792, 5)),
    dict(id='PARTITION2', date=(1793, 1)),
]

OK = dict(english='OK', spanish='Aceptar', French='OK', German='OK', Italian='OK', Polish='OK', Czech='OK', Russian='ОК')

# (title, body) per language. Latin1 files (english, spanish, French, German, Italian): Latin-1 characters only.
# Russian: no 'yo' and no dashes (the original Russian texts use neither). No double quotes, backslashes or percent signs.
TEXT = {
    'english': dict(
        BASTILLA=("The Bastille has fallen",
                  "On 14 July the people of Paris stormed the Bastille. In August the National Assembly ends feudal privilege "
                  "and proclaims the Rights of Man. The courts of Europe watch France with alarm."),
        MYSORE_WAR=("Tipu Sultan strikes Travancore",
                    "On 29 December Tipu Sultan of Mysore attacks the Lines of Travancore, an ally of the East India Company. "
                    "The Third Anglo-Mysore War begins; the Marathas and the Nizam will soon side with Britain."),
        PRUSSIA_POLAND=("Prussia and Poland ally",
                        "On 29 March Prussia and the Polish Commonwealth sign a defensive alliance. Frederick William II promises "
                        "to shield the Poles from Russian pressure, hoping to win Danzig and Thorn in return."),
        WERELOE=("Peace of Wereloe",
                 "On 14 August Sweden and Russia end their war at Wereloe, on the Kymi river. Borders stay as before the war: "
                 "Gustav III has not won back the lands lost to Russia."),
        CONSTITUTION=("The Constitution of 3 May",
                      "The Polish Sejm adopts Europe's first modern written constitution: a hereditary monarchy, rights for the "
                      "burghers and no more liberum veto. Catherine II sees a danger on her border; Poland has few friends."),
        SISTOVA=("Peace of Sistova",
                 "On 4 August Austria and the Ottoman Empire make peace at Sistova. Leopold II gives back nearly all his "
                 "conquests, for he needs a free hand against revolutionary France."),
        JASSY=("Treaty of Jassy",
               "On 9 January Russia and the Ottoman Empire sign the Treaty of Jassy. Russia keeps Ochakov and the steppe up to "
               "the Dniester, and the Sultan accepts the loss of Crimea. The war of 1787 is over."),
        SERINGAPATAM=("Treaty of Seringapatam",
                      "On 18 March Tipu Sultan signs peace before the walls of his capital. He gives up half of Mysore to Britain "
                      "and her allies and hands over two sons as hostages. The Third Anglo-Mysore War is over."),
        FRENCH_WAR=("France declares war",
                    "On 20 April revolutionary France declares war on Austria. Prussia will soon stand at Austria's side. "
                    "The French army is in disorder, but the Revolution will fight for its life."),
        POLISH_WAR=("Russia invades Poland",
                    "On 18 May a Russian army crosses the border to crush the Constitution of 3 May, called in by the magnates "
                    "of the Targowica Confederation. Prussia refuses to honour its alliance with Poland."),
        PARTITION2=("Second Partition of Poland",
                    "On 23 January Russia and Prussia agree to carve up Poland again. Russia takes the east, Prussia takes "
                    "Danzig, Thorn and Greater Poland. Austria, busy with France, gets nothing."),
    ),
    'spanish': dict(
        BASTILLA=("Cae la Bastilla",
                  "El 14 de julio el pueblo de París asaltó la Bastilla. En agosto la Asamblea Nacional suprime los privilegios "
                  "feudales y proclama los Derechos del Hombre. Las cortes de Europa miran a Francia con alarma."),
        MYSORE_WAR=("Tipu Sultán ataca Travancore",
                    "El 29 de diciembre Tipu Sultán de Mysore ataca las Líneas de Travancore, aliado de la Compañía de las Indias "
                    "Orientales. Empieza la Tercera Guerra Anglo-Mysore; los maratas y el Nizam pronto apoyarán a Gran Bretaña."),
        PRUSSIA_POLAND=("Alianza de Prusia y Polonia",
                        "El 29 de marzo Prusia y la República polaca firman una alianza defensiva. Federico Guillermo II promete "
                        "proteger a Polonia de la presión rusa, con la esperanza de ganar Danzig y Thorn a cambio."),
        WERELOE=("Paz de Wereloe",
                 "El 14 de agosto Suecia y Rusia ponen fin a su guerra en Wereloe, junto al río Kymi. Las fronteras quedan como "
                 "antes de la guerra: Gustavo III no ha recuperado las tierras perdidas ante Rusia."),
        CONSTITUTION=("La Constitución del 3 de mayo",
                      "La Dieta polaca adopta la primera constitución escrita moderna de Europa: monarquía hereditaria, derechos "
                      "para los burgueses y fin del liberum veto. Catalina II ve un peligro en su frontera; Polonia tiene pocos amigos."),
        SISTOVA=("Paz de Sistova",
                 "El 4 de agosto Austria y el Imperio otomano firman la paz en Sistova. Leopoldo II devuelve casi todas sus "
                 "conquistas, pues necesita las manos libres frente a la Francia revolucionaria."),
        JASSY=("Tratado de Jassy",
               "El 9 de enero Rusia y el Imperio otomano firman el Tratado de Jassy. Rusia conserva Ochakov y la estepa hasta el "
               "Dniéster, y el sultán acepta la pérdida de Crimea. La guerra de 1787 ha terminado."),
        SERINGAPATAM=("Tratado de Seringapatam",
                      "El 18 de marzo Tipu Sultán firma la paz ante los muros de su capital. Cede la mitad de Mysore a Gran Bretaña "
                      "y sus aliados y entrega a dos hijos como rehenes. La Tercera Guerra Anglo-Mysore ha terminado."),
        FRENCH_WAR=("Francia declara la guerra",
                    "El 20 de abril la Francia revolucionaria declara la guerra a Austria. Prusia no tardará en ponerse al lado de "
                    "Austria. El ejército francés está desorganizado, pero la Revolución luchará por su vida."),
        POLISH_WAR=("Rusia invade Polonia",
                    "El 18 de mayo un ejército ruso cruza la frontera para aplastar la Constitución del 3 de mayo, llamado por los "
                    "magnates de la Confederación de Targowica. Prusia se niega a cumplir su alianza con Polonia."),
        PARTITION2=("Segundo reparto de Polonia",
                    "El 23 de enero Rusia y Prusia acuerdan repartirse Polonia de nuevo. Rusia toma el este; Prusia, Danzig, Thorn "
                    "y la Gran Polonia. Austria, ocupada con Francia, no recibe nada."),
    ),
    'French': dict(
        BASTILLA=("La Bastille est tombée",
                  "Le 14 juillet, le peuple de Paris prend la Bastille. En août, l'Assemblée nationale abolit les privilèges "
                  "féodaux et proclame les droits de l'homme. Les cours d'Europe observent la France avec effroi."),
        MYSORE_WAR=("Tipû Sultan attaque le Travancore",
                    "Le 29 décembre, Tipû Sultan de Mysore attaque les lignes du Travancore, allié de la Compagnie des Indes "
                    "orientales. La troisième guerre du Mysore commence ; les Marathes et le Nizam se rangeront bientôt du côté "
                    "de la Grande-Bretagne."),
        PRUSSIA_POLAND=("Alliance prusso-polonaise",
                        "Le 29 mars, la Prusse et la République polonaise signent une alliance défensive. Frédéric-Guillaume II "
                        "promet de protéger la Pologne de la pression russe, en espérant obtenir Dantzig et Thorn en retour."),
        WERELOE=("Paix de Wereloe",
                 "Le 14 août, la Suède et la Russie mettent fin à leur guerre à Wereloe, sur la rivière Kymi. Les frontières "
                 "restent celles d'avant la guerre : Gustave III n'a pas repris les terres perdues au profit de la Russie."),
        CONSTITUTION=("La Constitution du 3 mai",
                      "La Diète polonaise adopte la première constitution écrite moderne d'Europe : monarchie héréditaire, droits "
                      "pour les bourgeois et fin du liberum veto. Catherine II y voit un danger à sa frontière ; la Pologne a peu d'amis."),
        SISTOVA=("Paix de Sistova",
                 "Le 4 août, l'Autriche et l'Empire ottoman font la paix à Sistova. Léopold II rend presque toutes ses conquêtes, "
                 "car il veut avoir les mains libres face à la France révolutionnaire."),
        JASSY=("Traité de Jassy",
               "Le 9 janvier, la Russie et l'Empire ottoman signent le traité de Jassy. La Russie garde Otchakov et la steppe "
               "jusqu'au Dniestr, et le sultan accepte la perte de la Crimée. La guerre de 1787 est terminée."),
        SERINGAPATAM=("Traité de Seringapatam",
                      "Le 18 mars, Tipû Sultan signe la paix devant les murs de sa capitale. Il cède la moitié du Mysore à la "
                      "Grande-Bretagne et à ses alliés et livre deux de ses fils en otage. La troisième guerre du Mysore est finie."),
        FRENCH_WAR=("La France déclare la guerre",
                    "Le 20 avril, la France révolutionnaire déclare la guerre à l'Autriche. La Prusse se rangera bientôt aux côtés "
                    "de l'Autriche. L'armée française est en désordre, mais la Révolution se battra pour sa survie."),
        POLISH_WAR=("La Russie envahit la Pologne",
                    "Le 18 mai, une armée russe franchit la frontière pour écraser la Constitution du 3 mai, appelée par les "
                    "magnats de la Confédération de Targowica. La Prusse refuse d'honorer son alliance avec la Pologne."),
        PARTITION2=("Deuxième partage de la Pologne",
                    "Le 23 janvier, la Russie et la Prusse conviennent de dépecer à nouveau la Pologne. La Russie prend l'est ; "
                    "la Prusse, Dantzig, Thorn et la Grande-Pologne. L'Autriche, occupée par la France, n'obtient rien."),
    ),
    'German': dict(
        BASTILLA=("Die Bastille ist gefallen",
                  "Am 14. Juli stürmte das Volk von Paris die Bastille. Im August schafft die Nationalversammlung die "
                  "Feudalrechte ab und verkündet die Menschenrechte. Die Höfe Europas blicken mit Sorge auf Frankreich."),
        MYSORE_WAR=("Tipu Sultan greift Travancore an",
                    "Am 29. Dezember greift Tipu Sultan von Mysore die Linien von Travancore an, einen Verbündeten der "
                    "Ostindien-Kompanie. Der Dritte Mysore-Krieg beginnt; Marathen und Nizam stellen sich bald auf Englands Seite."),
        PRUSSIA_POLAND=("Bündnis Preußen-Polen",
                        "Am 29. März schließen Preußen und die polnische Adelsrepublik ein Verteidigungsbündnis. Friedrich "
                        "Wilhelm II. verspricht, Polen vor dem russischen Druck zu schützen, und hofft dafür auf Danzig und Thorn."),
        WERELOE=("Friede von Wereloe",
                 "Am 14. August beenden Schweden und Russland ihren Krieg bei Wereloe am Fluss Kymi. Die Grenzen bleiben wie "
                 "vor dem Krieg: Gustav III. hat die an Russland verlorenen Gebiete nicht zurückgewonnen."),
        CONSTITUTION=("Die Verfassung vom 3. Mai",
                      "Der polnische Sejm beschließt die erste moderne geschriebene Verfassung Europas: erbliche Monarchie, "
                      "Rechte für Bürger und kein Liberum Veto mehr. Katharina II. sieht eine Gefahr an ihrer Grenze; Polen hat wenige Freunde."),
        SISTOVA=("Friede von Sistowa",
                 "Am 4. August schließen Österreich und das Osmanische Reich in Sistowa Frieden. Leopold II. gibt fast alle "
                 "Eroberungen zurück, denn er braucht freie Hand gegenüber dem revolutionären Frankreich."),
        JASSY=("Friede von Jassy",
               "Am 9. Januar unterzeichnen Russland und das Osmanische Reich den Frieden von Jassy. Russland behält Otschakow "
               "und die Steppe bis zum Dnjestr, und der Sultan erkennt den Verlust der Krim an. Der Krieg von 1787 ist beendet."),
        SERINGAPATAM=("Friede von Seringapatam",
                      "Am 18. März schließt Tipu Sultan vor den Mauern seiner Hauptstadt Frieden. Er tritt die Hälfte von Mysore "
                      "an Großbritannien und seine Verbündeten ab und stellt zwei Söhne als Geiseln. Der Dritte Mysore-Krieg ist zu Ende."),
        FRENCH_WAR=("Frankreich erklärt den Krieg",
                    "Am 20. April erklärt das revolutionäre Frankreich Österreich den Krieg. Preußen wird bald an Österreichs "
                    "Seite stehen. Das französische Heer ist in Unordnung, doch die Revolution kämpft um ihr Leben."),
        POLISH_WAR=("Russland marschiert in Polen ein",
                    "Am 18. Mai überschreitet ein russisches Heer die Grenze, um die Verfassung vom 3. Mai zu zerschlagen, gerufen "
                    "von den Magnaten der Konföderation von Targowica. Preußen verweigert die Erfüllung seines Bündnisses mit Polen."),
        PARTITION2=("Zweite Teilung Polens",
                    "Am 23. Januar einigen sich Russland und Preußen, Polen erneut aufzuteilen. Russland nimmt den Osten, Preußen "
                    "Danzig, Thorn und Großpolen. Österreich, durch Frankreich gebunden, geht leer aus."),
    ),
    'Italian': dict(
        BASTILLA=("La Bastiglia è caduta",
                  "Il 14 luglio il popolo di Parigi prende la Bastiglia. In agosto l'Assemblea nazionale abolisce i privilegi "
                  "feudali e proclama i diritti dell'uomo. Le corti d'Europa guardano alla Francia con timore."),
        MYSORE_WAR=("Tipu Sultan attacca il Travancore",
                    "Il 29 dicembre Tipu Sultan del Mysore attacca le Linee del Travancore, alleato della Compagnia delle Indie "
                    "Orientali. Comincia la terza guerra del Mysore; i Maratha e il Nizam si schiereranno presto con la Gran Bretagna."),
        PRUSSIA_POLAND=("Alleanza tra Prussia e Polonia",
                        "Il 29 marzo la Prussia e la Repubblica polacca firmano un'alleanza difensiva. Federico Guglielmo II "
                        "promette di proteggere la Polonia dalla pressione russa, sperando in cambio in Danzica e Thorn."),
        WERELOE=("Pace di Wereloe",
                 "Il 14 agosto Svezia e Russia pongono fine alla guerra a Wereloe, sul fiume Kymi. I confini restano quelli di "
                 "prima: Gustavo III non ha riconquistato le terre perdute a favore della Russia."),
        CONSTITUTION=("La Costituzione del 3 maggio",
                      "La Dieta polacca adotta la prima costituzione scritta moderna d'Europa: monarchia ereditaria, diritti ai "
                      "borghesi e fine del liberum veto. Caterina II vede un pericolo ai suoi confini; la Polonia ha pochi amici."),
        SISTOVA=("Pace di Sistova",
                 "Il 4 agosto l'Austria e l'Impero ottomano fanno la pace a Sistova. Leopoldo II restituisce quasi tutte le "
                 "conquiste, perché vuole avere le mani libere di fronte alla Francia rivoluzionaria."),
        JASSY=("Trattato di Jassy",
               "Il 9 gennaio Russia e Impero ottomano firmano il trattato di Jassy. La Russia tiene Ocakov e la steppa fino al "
               "Dnestr, e il sultano accetta la perdita della Crimea. La guerra del 1787 è finita."),
        SERINGAPATAM=("Trattato di Seringapatam",
                      "Il 18 marzo Tipu Sultan firma la pace davanti alle mura della sua capitale. Cede metà del Mysore alla Gran "
                      "Bretagna e ai suoi alleati e consegna due figli come ostaggi. La terza guerra del Mysore è finita."),
        FRENCH_WAR=("La Francia dichiara guerra",
                    "Il 20 aprile la Francia rivoluzionaria dichiara guerra all'Austria. La Prussia si schiererà presto al fianco "
                    "dell'Austria. L'esercito francese è in disordine, ma la Rivoluzione lotterà per la propria vita."),
        POLISH_WAR=("La Russia invade la Polonia",
                    "Il 18 maggio un esercito russo varca il confine per schiacciare la Costituzione del 3 maggio, chiamato dai "
                    "magnati della Confederazione di Targowica. La Prussia rifiuta di onorare l'alleanza con la Polonia."),
        PARTITION2=("Seconda spartizione della Polonia",
                    "Il 23 gennaio Russia e Prussia concordano di spartirsi di nuovo la Polonia. La Russia prende l'est; la "
                    "Prussia, Danzica, Thorn e la Grande Polonia. L'Austria, impegnata con la Francia, non ottiene nulla."),
    ),
    'Polish': dict(
        BASTILLA=("Bastylia padła",
                  "14 lipca lud Paryża zdobył Bastylię. W sierpniu Zgromadzenie Narodowe znosi przywileje feudalne i ogłasza "
                  "Prawa Człowieka. Dwory Europy patrzą na Francję z niepokojem."),
        MYSORE_WAR=("Tipu Sultan uderza na Trawankur",
                    "29 grudnia Tipu Sultan z Mysore atakuje linie Trawankuru, sojusznika Kompanii Wschodnioindyjskiej. Zaczyna "
                    "się trzecia wojna z Mysore; Marathowie i Nizam wkrótce staną po stronie Wielkiej Brytanii."),
        PRUSSIA_POLAND=("Sojusz Prus z Polską",
                        "29 marca Prusy i Rzeczpospolita zawierają sojusz obronny. Fryderyk Wilhelm II obiecuje chronić Polskę "
                        "przed naciskiem Rosji, licząc w zamian na Gdańsk i Toruń."),
        WERELOE=("Pokój w Wereloe",
                 "14 sierpnia Szwecja i Rosja kończą wojnę w Wereloe nad rzeką Kymi. Granice pozostają takie jak przed wojną: "
                 "Gustaw III nie odzyskał ziem utraconych na rzecz Rosji."),
        CONSTITUTION=("Konstytucja 3 maja",
                      "Sejm przyjmuje pierwszą nowoczesną spisaną konstytucję Europy: monarchię dziedziczną, prawa dla mieszczan "
                      "i koniec liberum veto. Katarzyna II widzi zagrożenie przy swojej granicy; Polska ma mało przyjaciół."),
        SISTOVA=("Pokój w Swisztowie",
                 "4 sierpnia Austria i Imperium Osmańskie zawierają pokój w Swisztowie. Leopold II oddaje niemal wszystkie "
                 "zdobycze, bo potrzebuje wolnych rąk wobec rewolucyjnej Francji."),
        JASSY=("Traktat jasski",
               "9 stycznia Rosja i Imperium Osmańskie podpisują traktat jasski. Rosja zatrzymuje Oczaków i step aż po Dniestr, "
               "a sułtan uznaje utratę Krymu. Wojna z 1787 roku dobiegła końca."),
        SERINGAPATAM=("Traktat w Seringapatam",
                      "18 marca Tipu Sultan zawiera pokój pod murami swojej stolicy. Oddaje połowę Mysore Wielkiej Brytanii i jej "
                      "sojusznikom i wydaje dwóch synów jako zakładników. Trzecia wojna z Mysore dobiegła końca."),
        FRENCH_WAR=("Francja wypowiada wojnę",
                    "20 kwietnia rewolucyjna Francja wypowiada wojnę Austrii. Prusy wkrótce staną u boku Austrii. Armia "
                    "francuska jest w rozsypce, lecz Rewolucja będzie walczyć o życie."),
        POLISH_WAR=("Rosja najeżdża Polskę",
                    "18 maja armia rosyjska przekracza granicę, by zdławić Konstytucję 3 maja, wezwana przez magnatów "
                    "konfederacji targowickiej. Prusy odmawiają wypełnienia sojuszu z Polską."),
        PARTITION2=("Drugi rozbiór Polski",
                    "23 stycznia Rosja i Prusy uzgadniają ponowny podział Polski. Rosja bierze wschód, Prusy Gdańsk, Toruń "
                    "i Wielkopolskę. Austria, zajęta Francją, nie dostaje nic."),
    ),
    'Czech': dict(
        BASTILLA=("Bastila padla",
                  "Dne 14. července lid Paříže dobyl Bastilu. V srpnu Národní shromáždění zrušilo feudální výsady a vyhlásilo "
                  "Práva člověka. Evropské dvory sledují Francii s obavami."),
        MYSORE_WAR=("Tipu Sultan napadá Travankor",
                    "Dne 29. prosince Tipu Sultan z Maisúru napadá linie Travankoru, spojence Východoindické společnosti. Začíná "
                    "třetí maisúrská válka; Maráthové a nizám se brzy postaví na stranu Británie."),
        PRUSSIA_POLAND=("Spojenectví Pruska a Polska",
                        "Dne 29. března uzavírají Prusko a polská Rzeczpospolita obranné spojenectví. Fridrich Vilém II. slibuje "
                        "chránit Polsko před ruským tlakem a doufá za to v Gdaňsk a Toruň."),
        WERELOE=("Mír ve Wereloe",
                 "Dne 14. srpna ukončují Švédsko a Rusko válku ve Wereloe u řeky Kymi. Hranice zůstávají jako před válkou: "
                 "Gustav III. nezískal zpět země ztracené ve prospěch Ruska."),
        CONSTITUTION=("Ústava z 3. května",
                      "Polský sejm přijímá první moderní psanou ústavu Evropy: dědičnou monarchii, práva pro měšťany a konec "
                      "liberum veta. Kateřina II. vidí nebezpečí na své hranici; Polsko má málo přátel."),
        SISTOVA=("Mír ve Svištově",
                 "Dne 4. srpna uzavírají Rakousko a Osmanská říše mír ve Svištově. Leopold II. vrací téměř všechny výboje, "
                 "protože potřebuje volné ruce proti revoluční Francii."),
        JASSY=("Jasský mír",
               "Dne 9. ledna podepisují Rusko a Osmanská říše Jasský mír. Rusko si ponechává Očakov a step až k Dněstru "
               "a sultán uznává ztrátu Krymu. Válka z roku 1787 je u konce."),
        SERINGAPATAM=("Mír v Seringapatamu",
                      "Dne 18. března uzavírá Tipu Sultan mír pod hradbami svého hlavního města. Odstupuje polovinu Maisúru "
                      "Británii a jejím spojencům a vydává dva syny jako rukojmí. Třetí maisúrská válka skončila."),
        FRENCH_WAR=("Francie vyhlašuje válku",
                    "Dne 20. dubna revoluční Francie vyhlašuje válku Rakousku. Prusko se brzy postaví po boku Rakouska. "
                    "Francouzská armáda je v rozvratu, ale revoluce bude bojovat o holý život."),
        POLISH_WAR=("Rusko napadá Polsko",
                    "Dne 18. května ruská armáda překračuje hranici, aby rozdrtila ústavu z 3. května, přivolána magnáty "
                    "targovické konfederace. Prusko odmítá dostát své smlouvě s Polskem."),
        PARTITION2=("Druhé dělení Polska",
                    "Dne 23. ledna se Rusko a Prusko dohodnou na novém rozdělení Polska. Rusko bere východ, Prusko Gdaňsk, "
                    "Toruň a Velkopolsko. Rakousko, zaměstnané Francií, nedostane nic."),
    ),
    'Russian': dict(
        BASTILLA=("Пала Бастилия",
                  "14 июля парижане взяли штурмом Бастилию. В августе Национальное собрание отменило феодальные привилегии "
                  "и провозгласило права человека. Дворы Европы с тревогой следят за Францией."),
        MYSORE_WAR=("Типу Султан напал на Траванкур",
                    "29 декабря Типу Султан Майсурский напал на линии Траванкура, союзника Ост-Индской компании. Началась "
                    "третья англо-майсурская война; маратхи и низам вскоре встанут на сторону Британии."),
        PRUSSIA_POLAND=("Союз Пруссии и Польши",
                        "29 марта Пруссия и Речь Посполитая заключили оборонительный союз. Фридрих Вильгельм II обещает защитить "
                        "Польшу от давления России, надеясь получить взамен Данциг и Торунь."),
        WERELOE=("Верельский мир",
                 "14 августа Швеция и Россия закончили войну миром в Вереле на реке Кюмень. Границы остались прежними: "
                 "Густав III не вернул земли, потерянные в пользу России."),
        CONSTITUTION=("Конституция 3 мая",
                      "Сейм принимает первую в Европе современную писаную конституцию: наследственную монархию, права горожан "
                      "и отмену либерум вето. Екатерина II видит опасность у своей границы; у Польши мало друзей."),
        SISTOVA=("Систовский мир",
                 "4 августа Австрия и Османская империя заключили мир в Систове. Леопольд II возвращает почти все завоевания: "
                 "ему нужны свободные руки против революционной Франции."),
        JASSY=("Ясский мир",
               "9 января Россия и Османская империя подписали Ясский мир. Россия сохраняет Очаков и степь до Днестра, "
               "а султан признает потерю Крыма. Война 1787 года окончена."),
        SERINGAPATAM=("Договор в Серингапатаме",
                      "18 марта Типу Султан заключил мир под стенами своей столицы. Он уступает половину Майсура Британии и ее "
                      "союзникам и отдает двух сыновей в заложники. Третья англо-майсурская война окончена."),
        FRENCH_WAR=("Франция объявляет войну",
                    "20 апреля революционная Франция объявила войну Австрии. Пруссия скоро встанет на сторону Австрии. "
                    "Французская армия в расстройстве, но революция будет бороться за жизнь."),
        POLISH_WAR=("Россия вторглась в Польшу",
                    "18 мая русская армия перешла границу, чтобы раздавить Конституцию 3 мая; ее призвали магнаты Тарговицкой "
                    "конфедерации. Пруссия отказывается выполнять союз с Польшей."),
        PARTITION2=("Второй раздел Польши",
                    "23 января Россия и Пруссия договорились снова разделить Польшу. Россия берет восток, Пруссия получает "
                    "Данциг, Торунь и Великую Польшу. Австрия, занятая Францией, не получает ничего."),
    ),
}


# ------------------------------------------------------------------------------------------------ keys and texts
def key_title(eid): return 'LTEXT_EH_%s_T' % eid
def key_body(eid): return 'LTEXT_EH_%s_X' % eid
KEY_OK = 'LTEXT_EH_OK'


def text_entries(lang):
    """[(key, value)] to append to TEXT_REL of this language."""
    ents = []
    for e in EVENTS:
        t, x = TEXT[lang][e['id']]
        ents += [(key_title(e['id']), t), (key_body(e['id']), x)]
    ents.append((KEY_OK, OK[lang]))
    return ents


# ------------------------------------------------------------------------------------------------ Lua
CRLF = '\r\n'


def _lua_str(s):
    assert re.fullmatch(r'[A-Za-z0-9_ .-]*', s), s
    return '"%s"' % s


def lua_events_table():
    rows = []
    for e in EVENTS:
        f = ['id = %s' % _lua_str(e['id']), 'turno = %d' % turn_of(*e['date']),
             'fecha = %s' % _lua_str('%04d-%02d' % e['date']),
             'titulo = %s' % _lua_str(key_title(e['id'])), 'texto = %s' % _lua_str(key_body(e['id']))]
        if e.get('pacts'):
            f.append('pactos = { %s }' % ', '.join('{ %s, %s, %d }' % (_lua_str(a), _lua_str(b), n) for a, b, n in e['pacts']))
        if e.get('peace'):
            f.append('paz = { %s }' % ', '.join('{ %s, %s }' % (_lua_str(a), _lua_str(b)) for a, b in e['peace']))
        if e.get('armies'):
            f.append('ejercitos = { %s }' % ', '.join('{ %s }' % ', '.join(_lua_str(x) for x in a) for a in e['armies']))
        if e.get('resources'):
            f.append('recursos = { %s }' % ', '.join(str(int(x)) for x in e['resources']))
        rows.append('  { %s }' % ', '.join(f))
    return 'EH_EVENTOS = {' + CRLF + (',' + CRLF).join(rows) + CRLF + '}' + CRLF


EVENTS_LUA_HEAD = r"""-- EventosHistoricos1789.lua: scripted historical events of the Imperial Glory 1789 mod.
-- GENERATED by tools/historical_events.py (make_map.HISTORICAL_EVENTS); edit the data there, not this file.
--
-- Included by SecuenciaGestionMod.lua (inicia_secuencia), which the exe (patch 48) runs once per campaign map UI with the
-- sequence manager INACTIVE; the exe then calls eh_inicio_turno() at the start of every human turn. on_event never fires
-- in this mode, so nothing here uses it. Every native is checked before use (a missing one just skips that part); the
-- dialect is the game's Lua 5.0: no # operator, no pairs/ipairs (numeric for + table.getn), no string library calls.
--
-- Clock: get_turno_actual() (exe patch 49) is the campaign turn. Without it NOTHING fires (eh_turno() returns nil).
--
-- Idempotence: an event fires only when the saved campaign turn equals its turno at the start of the human's turn,
-- and once per Lua session (EH_DISPARADOS). A save loaded later never replays earlier events. firma_paz_entre does
-- nothing unless the two nations are at war.
-- Lua errors only show in the debug output (ERROR EN SCRIPT); they cannot corrupt a save: nothing here is saved.

EH_VERSION = 2

-- switches (effects stay off until tested in game)
EH_DEBUG = false
EH_MENSAJES = true             -- show the event message box (open_messagebox with an inactive manager is untested)
EH_ID_CAJA = 1789              -- id of the message box
EH_PERMITE_PACTOS = false      -- crea_proteccion_mutua_entre: a real alliance between two nations
EH_PERMITE_PAZ = false         -- firma_paz_entre (exe patch 50): the game's own peace, only if the two are at war
EH_PERMITE_EJERCITOS = false   -- crea_ficha: free army for the owner of a province
EH_PERMITE_RECURSOS = false    -- ingresa_recursos_en_jugador_local: money, food, raw, men for the human
EH_IGNORA_PRIMERO = false      -- true = skip the first turn-start call after activation (use it if loading a save
                               -- turns out to run the hook again; false if the first call is a real new turn)

-- one entry per event: turno (1 turn = 1 month, turn 1 = July 1789), titulo / texto = LTEXT keys, optional cond (function
-- returning true/false), pactos = { { "JUG_A", "JUG_B", turns } }, paz = { { "JUG_A", "JUG_B" } },
-- ejercitos = { { "PROVINCE", "RANK", "TROOP", ... } }, recursos = { money, food, raw, men }
"""

EVENTS_LUA_BODY = r"""
-- debug line to the exe's debug output (OutputDebugString, readable with DebugView): _ALERT is the engine's own raw function
function eh_log(texto)
  if EH_DEBUG and _ALERT ~= nil then
    _ALERT("EH: "..texto.."\n")
  end
end

-- current campaign turn, or nil when it cannot be known (then nothing fires)
function eh_turno()
  if get_turno_actual ~= nil then
    return get_turno_actual()
  end
  return nil
end

function eh_pactos(lista)
  if (not EH_PERMITE_PACTOS) or crea_proteccion_mutua_entre == nil then
    return
  end
  for i = 1, table.getn(lista) do
    local p = lista[i]
    crea_proteccion_mutua_entre(p[1], p[2], p[3])
  end
end

function eh_paz(lista)
  if (not EH_PERMITE_PAZ) or firma_paz_entre == nil then
    return
  end
  for i = 1, table.getn(lista) do
    local p = lista[i]
    firma_paz_entre(p[1], p[2])
  end
end

function eh_ejercitos(lista)
  if (not EH_PERMITE_EJERCITOS) or crea_ficha == nil then
    return
  end
  for i = 1, table.getn(lista) do
    local e = lista[i]
    local n = table.getn(e)
    if n == 3 then
      crea_ficha(TAM_EJERCITO, e[1], e[2], e[3])
    elseif n == 4 then
      crea_ficha(TAM_EJERCITO, e[1], e[2], e[3], e[4])
    elseif n == 5 then
      crea_ficha(TAM_EJERCITO, e[1], e[2], e[3], e[4], e[5])
    end
  end
end

function eh_recursos(r)
  if (not EH_PERMITE_RECURSOS) or ingresa_recursos_en_jugador_local == nil then
    return
  end
  ingresa_recursos_en_jugador_local(r[1], r[2], r[3], r[4])
end

function eh_dispara(ev)
  eh_log("evento "..ev.id)
  if EH_MENSAJES and ev.titulo ~= nil and open_messagebox ~= nil then
    open_messagebox(EH_ID_CAJA, ev.titulo, ev.texto, TMB_NORMAL, "LTEXT_EH_OK")
  end
  if ev.pactos ~= nil then
    eh_pactos(ev.pactos)
  end
  if ev.paz ~= nil then
    eh_paz(ev.paz)
  end
  if ev.ejercitos ~= nil then
    eh_ejercitos(ev.ejercitos)
  end
  if ev.recursos ~= nil then
    eh_recursos(ev.recursos)
  end
end

-- called by the exe (patch 48, nations.HIST_TURN_HOOK) at the start of every turn of the human player
function eh_inicio_turno()
  if EH_DISPARADOS == nil then
    EH_DISPARADOS = {}
    EH_PRIMERO = false
  end
  if EH_PRIMERO then
    EH_PRIMERO = false
    if EH_IGNORA_PRIMERO then
      return
    end
  end
  local turno = eh_turno()
  if turno == nil then
    return
  end
  for i = 1, table.getn(EH_EVENTOS) do
    local ev = EH_EVENTOS[i]
    if ev.turno == turno and EH_DISPARADOS[ev.id] ~= turno then
      if ev.cond == nil or ev.cond() then
        EH_DISPARADOS[ev.id] = turno
        eh_dispara(ev)
      end
    end
  end
end

-- called once per campaign by inicia_secuencia (SecuenciaGestionMod.lua)
function eh_inicia()
  EH_DISPARADOS = {}
  EH_PRIMERO = true
  if get_turno_actual == nil then
    eh_log("get_turno_actual missing, no events")
    return
  end
  if EH_DEBUG then
    eh_log("events ready, turn "..get_turno_actual())
  end
end
"""

ENTRY_LUA_SRC = r"""-- SecuenciaGestionMod.lua: entry script of the campaign sequence (UI_ModeloGestion.sb .SECUENCIA_TUTORIAL).
-- GENERATED by tools/historical_events.py (make_map.HISTORICAL_EVENTS).
--
-- The engine loads this script (every start; exe patch 48 forces the reload) and calls inicia_secuencia() once per map UI:
--   tutorial campaign  -> the sequence runs the old way (manager active): the ORIGINAL SecuenciaTutorialGestion.lua is
--                         included and its inicia_secuencia is run; this script's inicia_secuencia is put back afterwards
--   any other campaign -> (manager INACTIVE) EventosHistoricos1789.lua is included and eh_inicia() resets its state; the exe
--                         then calls eh_inicio_turno() at every human turn start (on_event never fires in this mode)

function eh_arranca_tutorial()
  local mio = inicia_secuencia
  include_script("Secuencias\\SecuenciaTutorialGestion.lua")
  if inicia_secuencia ~= mio then
    EH_TUTORIAL_INICIA = inicia_secuencia
    inicia_secuencia = mio
  end
  if EH_TUTORIAL_INICIA ~= nil then
    EH_TUTORIAL_INICIA()
  end
end

function inicia_secuencia()
  if tutorial_gestion_activo then
    eh_arranca_tutorial()
    return
  end
  include_script("Secuencias\\EventosHistoricos1789.lua")
  if eh_inicia ~= nil then
    eh_inicia()
  end
end
"""


def events_lua():
    return (EVENTS_LUA_HEAD.replace('\n', CRLF) + lua_events_table() + EVENTS_LUA_BODY.replace('\n', CRLF))


def entry_lua():
    return ENTRY_LUA_SRC.replace('\n', CRLF)


def check_lua(src):
    """Rough Lua syntax check without an interpreter (none installed): block balance of function/if/for/while/do/repeat,
    parentheses, braces, brackets, strings and comments. Returns a list of problems."""
    probs, stack, i, n, line = [], [], 0, len(src), 1
    pairs = {')': '(', '}': '{', ']': '['}
    toks = []
    while i < n:
        c = src[i]
        if c == '\n':
            line += 1; i += 1
        elif c in ' \t\r':
            i += 1
        elif src.startswith('--', i):
            if src.startswith('--[[', i):
                j = src.find(']]', i)
                if j < 0:
                    probs.append('unterminated block comment'); break
                line += src.count('\n', i, j); i = j + 2
            else:
                j = src.find('\n', i); i = n if j < 0 else j
        elif c in '"\'':
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == '\\': j += 1
                if src[j] == '\n': probs.append('line %d: string with newline' % line); break
                j += 1
            i = j + 1
        elif c.isalpha() or c == '_':
            j = i
            while j < n and (src[j].isalnum() or src[j] == '_'): j += 1
            toks.append((src[i:j], line)); i = j
        elif c in '([{':
            toks.append((c, line)); i += 1
        elif c in ')]}':
            toks.append((c, line)); i += 1
        else:
            i += 1
    blocks, brk = [], []
    for t, ln in toks:
        if t in ('function', 'if'):
            blocks.append(t)
        elif t in ('for', 'while'):
            blocks.append('loop')
        elif t == 'do':
            if blocks and blocks[-1] == 'loop': blocks[-1] = 'block'
            else: blocks.append('block')
        elif t == 'repeat':
            blocks.append('repeat')
        elif t == 'until':
            if not blocks or blocks.pop() != 'repeat': probs.append('line %d: until without repeat' % ln)
        elif t == 'end':
            if not blocks or blocks[-1] == 'repeat' or blocks[-1] == 'loop':
                probs.append('line %d: end without block' % ln)
            else:
                blocks.pop()
        elif t in '([{':
            brk.append((t, ln))
        elif t in ')]}':
            if not brk or brk.pop()[0] != pairs[t]: probs.append('line %d: unbalanced %s' % (ln, t))
    if blocks: probs.append('%d unclosed blocks: %s' % (len(blocks), blocks))
    if brk: probs.append('unclosed brackets %s' % brk)
    return probs


# ------------------------------------------------------------------------------------------------ build step
def _enc_ok(txt, u16):
    return u16 or all(ord(ch) < 256 for ch in txt)


def install(mod, langs, src_text, read, out, text_add_entries, mod_or_src):
    """make_map build step (only when HISTORICAL_EVENTS): Lua files, the UI script path, the texts of all 8 languages."""
    check_data()
    bad = check_contract(events_lua(), entry_lua())
    assert not bad, bad
    for rel, txt in ((ENTRY_LUA, entry_lua()), (EVENTS_LUA, events_lua())):
        assert not check_lua(txt), (rel, check_lua(txt))
        out(rel, txt.encode('latin1'))
    ui = mod_or_src(UI_REL).decode('latin1')
    assert ui.count(ORIG_SCRIPT) == 1 and NEW_SCRIPT not in ui, 'UI_ModeloGestion.sb: .SECUENCIA_TUTORIAL path not found once'
    out(UI_REL, ui.replace(ORIG_SCRIPT, NEW_SCRIPT).encode('latin1'))
    assert set(langs) == set(LANGS), langs
    for lang in langs:
        p = os.path.join(mod, 'Texto', lang, TEXT_REL)
        raw = open(p, 'rb').read() if os.path.exists(p) else read(src_text(lang, TEXT_REL))
        u16 = raw[:2] == b'\xff\xfe'
        txt = raw[2:].decode('utf-16-le') if u16 else raw.decode('latin1')
        assert KEY_OK not in txt, (lang, 'event texts already present')
        ents = text_entries(lang)
        for k, v in ents:
            assert '"' not in v and BS not in v and '%' not in v and _enc_ok(v, u16), (lang, k, v)
        out('Texto/%s/%s' % (lang, TEXT_REL), text_add_entries(raw, ents))


def check_data():
    """Self-checks of EVENTS / TEXT (also run by the build step and by validate_build)."""
    ids = [e['id'] for e in EVENTS]
    assert len(ids) == len(set(ids)), 'duplicate event ids'
    turns = [turn_of(*e['date']) for e in EVENTS]
    assert turns == sorted(set(turns)), ('event turns must be unique and ascending', turns)   # one message box per turn
    assert turn_of(1789, 7) == 1 and turn_of(1790, 1) == 7 and turn_of(1793, 1) == 43
    for lang in LANGS:
        assert set(TEXT[lang]) == set(ids), (lang, set(ids) ^ set(TEXT[lang]))
        for eid, (t, x) in TEXT[lang].items():
            assert 0 < len(t) <= TITLE_MAX and 0 < len(x) <= BODY_MAX, (lang, eid, len(t), len(x))
            assert '"' not in t + x and BS not in t + x and '%' not in t + x, (lang, eid)
            if lang in ('english', 'spanish', 'French', 'German', 'Italian'):
                (t + x).encode('latin1')
            if lang == 'english':
                (t + x).encode('ascii')
            if lang == 'Russian':
                assert 'ё' not in t + x and '—' not in t + x, (lang, eid)   # no yo / em dash in the original font
    for lang in LANGS:
        assert lang in OK


HOOK = 'eh_inicio_turno'      # must equal nations.HIST_TURN_HOOK (exe patch 48 calls this Lua global at every human turn start)
NATIVES_OK = {'get_turno_actual', 'firma_paz_entre', 'open_messagebox', 'crea_proteccion_mutua_entre', 'crea_ficha',
              'ingresa_recursos_en_jugador_local', 'include_script', '_ALERT'}   # natives the exe provides in this mode
LUA_KEYWORDS = {'if', 'elseif', 'for', 'while', 'function', 'and', 'or', 'not', 'return', 'until', 'in', 'then', 'do', 'local'}
FORBIDDEN = ('on_event', 'limpia_eventos', 'MSG_GESTION', 'tipo_mensaje', 'crea_tregua_entre', 'EH_RELOJ', 'EH_CONTADOR')


def check_contract(events_src, entry_src):
    """The Lua against the exe patches 48-50: the hook and entry functions exist, nothing depends on on_event (it never fires
    with the inactive manager), and every call is an own function or one of NATIVES_OK. Returns a list of problems."""
    probs = []
    for src_, what, fn in ((events_src, 'events', HOOK), (events_src, 'events', 'eh_inicia'), (entry_src, 'entry', 'inicia_secuencia')):
        if not re.search(r'^function %s\(' % fn, src_, re.M):
            probs.append('%s Lua lacks function %s()' % (what, fn))
    for what, src_ in (('events', events_src), ('entry', entry_src)):
        body = re.sub(r'--[^\r\n]*', '', src_)
        body = re.sub(r'"[^"\r\n]*"', '""', body)
        for tok in FORBIDDEN:
            if tok in body:
                probs.append('%s Lua uses %s (dead with the inactive manager / patches 48-50)' % (what, tok))
        own = set(re.findall(r'\bfunction\s+(\w+)', body))
        for name in re.findall(r'\b([A-Za-z_][\w.]*)\s*\(', body):
            if (name in LUA_KEYWORDS or name in own or name in NATIVES_OK or name == 'table.getn' or '.' in name
                    or name.startswith(('EH_', 'eh_'))):
                continue
            probs.append('%s Lua calls unknown %s()' % (what, name))
    return probs


def validate_tree(mod, fails, warns):
    """validate_build check: the built tree (mod/) holds consistent event files, texts and UI path."""
    def rd(rel): return open(os.path.join(mod, rel), 'rb').read()
    try:
        check_data()
    except AssertionError as ex:
        fails.append(('historical events: data self-check', repr(ex)))
    for pr in check_contract(rd(EVENTS_LUA).decode('latin1'), rd(ENTRY_LUA).decode('latin1')):
        fails.append(('historical events: Lua contract with exe patches 48-50', pr))
    try:
        import nations as NT
        if getattr(NT, 'HIST_TURN_HOOK', None) != HOOK:
            fails.append(('historical events: nations.HIST_TURN_HOOK != %s' % HOOK, getattr(NT, 'HIST_TURN_HOOK', None)))
    except Exception as ex:
        warns.append('historical events: nations.py not importable (%r), hook name not compared' % (ex,))
    for rel in (ENTRY_LUA, EVENTS_LUA):
        txt = rd(rel).decode('latin1')
        for pr in check_lua(txt):
            fails.append(('historical events: Lua ' + rel, pr))
        if '\r\n' not in txt or any(ord(ch) > 127 for ch in txt):
            fails.append(('historical events: Lua must be ASCII with CRLF', rel))
    if rd(EVENTS_LUA).decode('latin1') != events_lua() or rd(ENTRY_LUA).decode('latin1') != entry_lua():
        fails.append(('historical events: Lua in the tree differs from tools/historical_events.py (stale build)',))
    ui = rd(UI_REL).decode('latin1')
    if NEW_SCRIPT not in ui or ORIG_SCRIPT in ui:
        fails.append(('historical events: .SECUENCIA_TUTORIAL does not point at SecuenciaGestionMod.lua',))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    orig = [os.path.join(root, d, 'Game', 'LuaScripts', 'Secuencias', 'SecuenciaTutorialGestion.lua') for d in ('data1', 'data')]
    if not any(os.path.exists(p) for p in orig):
        warns.append('historical events: original tutorial script not found in data/ (cannot be included)')
    keys = [k for e in EVENTS for k in (key_title(e['id']), key_body(e['id']))] + [KEY_OK]
    for lang in LANGS:
        p = os.path.join(mod, 'Texto', lang, TEXT_REL)
        raw = open(p, 'rb').read()
        t = raw[2:].decode('utf-16-le') if raw[:2] == b'\xff\xfe' else raw.decode('latin1')
        vals = dict(re.findall(r'\.(LTEXT_EH_\w+)\s+"([^"]*)"', t))
        miss = [k for k in keys if not vals.get(k)]
        if miss:
            fails.append(('historical events: text keys missing or blank in ' + lang, miss))
        if lang != 'english':
            same = [k for k in keys[:-1] if vals.get(k) == dict(text_entries('english')).get(k)]
            if same:
                warns.append('historical events: %s text identical to English: %s' % (lang, same[:3]))


if __name__ == '__main__':
    check_data()
    print('data self-check OK: %d events, %d languages' % (len(EVENTS), len(LANGS)))
    for e in EVENTS:
        print('  turn %2d  %04d-%02d  %s' % (turn_of(*e['date']), e['date'][0], e['date'][1], e['id']))
    for rel, txt in ((ENTRY_LUA, entry_lua()), (EVENTS_LUA, events_lua())):
        pr = check_lua(txt)
        print('Lua check %s: %s' % (rel, pr or 'balanced'))
    print('Lua contract with exe patches 48-50:', check_contract(events_lua(), entry_lua()) or 'OK')
    if len(sys.argv) > 1 and sys.argv[1] == '--preview':     # writes the rendered Lua next to the build logs (not into mod/)
        d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'build', 'historical_events')
        os.makedirs(d, exist_ok=True)
        for rel, txt in ((ENTRY_LUA, entry_lua()), (EVENTS_LUA, events_lua())):
            open(os.path.join(d, os.path.basename(rel)), 'wb').write(txt.encode('latin1'))
        print('preview written to', d)
