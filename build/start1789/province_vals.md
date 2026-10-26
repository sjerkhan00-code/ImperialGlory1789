# 1789 province economy proposal

Source of the decoding: re_tools (FUN_005c9b20, select-empire FUN_007ca610/FUN_007c9620, FUN_0064c760, FUN_00669b50). `vals` = two 6-int resource vectors (class "Riqueza", vtable + 6 ints) + capital id + port id:

| idx | offset in def | meaning | evidence |
|---|---|---|---|
| 0 | +0x14 | gold (DINERO) | select-empire gold bar BMBD = sum(+0x14); FUN_0064c760 writes DINERO to vector +4 |
| 1 | +0x18 | raw materials (MAT_PRIMAS) | bar BMBR = sum(+0x18); vector +8 |
| 2 | +0x1c | food (COMIDA) | bar BMBC = sum(+0x1c); vector +0xc |
| 3 | +0x20 | population (POBLACION) | bar BMBP = sum(+0x20); vector +0x10 |
| 4 | +0x24 | science / research capacity (CIENCIA) | "scientific potential" star = sum(+0x24); province window WTCI hidden when 0; only capitals |
| 5 | +0x28 | commerce points (6th Riqueza component) | internal commerce FUN_00669b50: gold = comp6 x VALOR_PUNTOS_COMERCIALES(1.0) x exploitation % (0/75/150/225 by Market/Roads/Stock Exchange); route value FUN_00670420 also uses +0x18 of country riqueza |
| 6-11 | +0x30..+0x44 | second Riqueza vector (same 6 components); +0x2c is its vtable, never read from the file | loader reads slots 5..10 and 12..19, skips 11; always 0 in the original -> keep 0 |
| 12 | +0x48 | capital id (enum table 3, section 5 record) | Inglaterra 1 = LONDRES, Letonia 3 = SANPETESBURGO; set by nations.py |
| 13 | +0x4c | port id (enum table 4) | select-empire port count = provinces with +0x4c != 0; report_ports.md |

## Original ranges (51 European/N-African land provinces)

| field | 24 capitals | 27 other provinces |
|---|---|---|
| 0 gold | 10-195 (median 45) | 20-65 (median 40) |
| 1 raw materials | 40-300 (median 75) | 25-190 (median 95) |
| 2 food | 30-100 (median 62) | 15-125 (median 37) |
| 3 population | 25-110 (median 40) | 10-50 (median 25) |
| 4 science | 150-760 (median 250) | 0-0 (median 0) |
| 5 commerce | 12-55 (median 25) | 7-30 (median 12) |

Totals: original 51 provinces gold/raw/food/pop/sci/commerce = [2860, 4755, 2539, 2075, 7510, 1092]; proposed 134 world provinces = [4743, 8875, 6346, 4918, 5175, 2742].
Original nation sums (gold/raw/food/pop/commerce, original map): GRAN_BRETANYA 330/550/200/160/71; FRANCIA 320/575/230/180/64; AUSTRIA 310/610/275/205/56; RUSIA 300/635/225/200/56; PRUSIA 305/590/275/150/52; ESPANYA 160/235/162/165/52; OTOMANO 105/165/90/105/48; EGIPTO 65/120/55/65/70; DOS_SICILIAS 60/85/67/70/50; DINAMARCA 50/115/69/50/45; SUECIA 65/90/60/50/45; PORTUGAL 60/125/69/60/50; LOMBARDIA 95/75/82/75/50; PIAMONTE 45/95/55/50/35; EPAPALES 75/90/62/40/23; RHELVETICA 100/45/65/40/20; HANNOVER 40/110/62/40/35; BATAVIA 100/50/60/50/40; SAJONIA 45/80/62/50/25; POLONIA 85/55/62/50/30; MOLDAVIA 80/50/60/40/20; MARRUECOS 30/70/65/110/45; TUNEZ 25/80/65/35/55; TRIPOLITANIA 10/60/62/35/55.
Proposed: values stay inside the original ranges; only the richest Asian cores reach European-capital level (gold up to 150 vs 195 for England; population 120 and food 130 slightly above the original maxima 110/125 for Jiangnan/Bengal/Huguang); deserts, tundra and Australia sit at the bottom (2-10).

## Nation sums (gold/raw/food/pop/commerce)

| nation | provinces | gold | raw | food | pop | commerce |
|---|---|---|---|---|---|---|
| QING | 18 | 840 | 1620 | 1025 | 845 | 347 |
| GRAN_BRETANYA | 8 | 445 | 630 | 565 | 480 | 233 |
| MARATHA | 7 | 395 | 620 | 450 | 430 | 164 |
| BATAVIA | 9 | 370 | 600 | 395 | 295 | 260 |
| DURRANI | 7 | 235 | 390 | 310 | 260 | 118 |
| JAPAN | 3 | 220 | 290 | 200 | 193 | 85 |
| ASHANTI | 2 | 150 | 120 | 90 | 75 | 70 |
| BURMA | 3 | 120 | 250 | 240 | 140 | 55 |
| OMAN | 3 | 115 | 130 | 75 | 70 | 120 |
| SIAM | 3 | 105 | 200 | 200 | 105 | 50 |
| VIETNAM | 2 | 90 | 140 | 170 | 140 | 35 |
| HYDERABAD | 1 | 90 | 120 | 70 | 80 | 25 |
| BORNU | 2 | 85 | 120 | 120 | 115 | 60 |
| ESPANYA | 2 | 85 | 130 | 140 | 100 | 60 |
| MYSORE | 1 | 85 | 120 | 75 | 70 | 25 |
| MALAYA | 2 | 80 | 160 | 65 | 55 | 75 |
| RUSIA | 7 | 72 | 460 | 98 | 53 | 78 |
| JOSEON | 1 | 70 | 100 | 90 | 85 | 20 |
| PORTUGAL | 3 | 65 | 140 | 75 | 50 | 80 |
| KONGO | 4 | 65 | 250 | 155 | 110 | 70 |
| SEGU | 2 | 65 | 80 | 95 | 65 | 55 |
| OTOMANO | 2 | 60 | 55 | 30 | 40 | 65 |
| LUNDA | 3 | 60 | 210 | 115 | 85 | 40 |
| PUNJAB | 1 | 60 | 90 | 90 | 70 | 20 |
| YEMEN | 2 | 60 | 90 | 55 | 55 | 65 |
| TRAVANCORE | 1 | 50 | 80 | 50 | 45 | 40 |
| DARFUR | 3 | 45 | 150 | 100 | 65 | 43 |
| NGUYEN | 1 | 45 | 60 | 110 | 45 | 25 |
| free | 2 | 45 | 90 | 65 | 50 | 28 |
| BRUNEI | 2 | 40 | 150 | 65 | 35 | 40 |
| ETHIOPIA | 1 | 40 | 80 | 70 | 60 | 15 |
| OYO | 1 | 40 | 50 | 70 | 60 | 30 |
| ROZVI | 1 | 40 | 60 | 40 | 30 | 15 |
| SENNAR | 2 | 35 | 80 | 75 | 45 | 30 |
| EGIPTO | 1 | 35 | 50 | 90 | 50 | 20 |
| FRANCIA | 1 | 30 | 40 | 30 | 25 | 30 |
| AHOM | 1 | 25 | 90 | 70 | 30 | 10 |
| BUGANDA | 1 | 25 | 60 | 80 | 45 | 10 |
| MADAGASCAR | 1 | 25 | 80 | 70 | 40 | 20 |
| NEPAL | 1 | 25 | 60 | 40 | 35 | 12 |
| FUTA | 1 | 20 | 50 | 50 | 35 | 15 |
| MOSSI | 1 | 15 | 40 | 50 | 35 | 10 |
| ABORIGINES | 5 | 12 | 125 | 43 | 21 | 7 |
| MAORI | 2 | 11 | 110 | 45 | 20 | 8 |
| SAJONIA | 1 | 10 | 30 | 10 | 8 | 15 |
| TRIPOLITANIA | 1 | 10 | 25 | 10 | 8 | 20 |
| NGUNI | 1 | 10 | 50 | 50 | 30 | 5 |
| HANNOVER | 1 | 10 | 50 | 25 | 10 | 8 |
| BECHUANA | 2 | 8 | 60 | 30 | 15 | 8 |
| PAPUA | 1 | 5 | 40 | 15 | 10 | 3 |

## Proposed values

vals[4] (science) is given for capitals only; vals[12]/vals[13] stay 0 here (nations.py sets the capital id, ports.py the port). If province_vals.json is used, nations.py should stop overwriting vals[4] with max(template, 200).

| key | owner | gold | raw | food | pop | sci | trade | why |
|---|---|---|---|---|---|---|---|---|
| northaus | ABORIGINES | 3 | 25 | 10 | 5 | 25 | 2 | Arnhem Land; Macassan trepang visits |
| queensland | ABORIGINES | 3 | 30 | 12 | 6 |  | 2 | Carpentaria, tropical coast |
| southaus | ABORIGINES | 2 | 20 | 8 | 4 |  | 1 | Nuyts Land, arid |
| tasmania | ABORIGINES | 2 | 30 | 8 | 3 |  | 1 | Van Diemen's Land, forests |
| westaus | ABORIGINES | 2 | 20 | 5 | 3 |  | 1 | New Holland desert coast |
| assam | AHOM | 25 | 90 | 70 | 30 | 100 | 10 | Ahom kingdom weakened by the Moamoria rebellion; silk, timber |
| ashanti | ASHANTI | 90 | 70 | 50 | 45 | 100 | 30 | Asante: gold fields, kola, the richest state of Guinea |
| ivory | ASHANTI | 60 | 50 | 40 | 30 |  | 40 | Gold Coast forts (Cape Coast, Elmina), gold and slave exports |
| borneosor | BATAVIA | 25 | 90 | 25 | 20 |  | 15 | Banjarmasin pepper, gold and diamonds (VOC) |
| cape | BATAVIA | 25 | 40 | 50 | 15 |  | 35 | VOC refreshment station: wine, wheat, ~20,000 colonists |
| celebes | BATAVIA | 30 | 60 | 45 | 35 |  | 25 | Makassar, Bugis traders |
| ceylon | BATAVIA | 50 | 90 | 50 | 35 |  | 40 | VOC cinnamon monopoly, pearls, Trincomalee harbour |
| java | BATAVIA | 110 | 110 | 120 | 110 |  | 50 | Batavia, VOC heart: coffee, sugar, rice; very populous |
| moluccas | BATAVIA | 70 | 40 | 25 | 15 |  | 50 | Spice Islands: cloves and nutmeg monopoly |
| nguineavest | BATAVIA | 5 | 50 | 10 | 10 |  | 5 | Bird of paradise plumes, jungle |
| sumatra | BATAVIA | 40 | 80 | 40 | 30 |  | 30 | Palembang tin, Bencoolen pepper |
| sunda | BATAVIA | 15 | 40 | 30 | 25 |  | 10 | Lesser Sundas, sandalwood, horses |
| kalahari | BECHUANA | 5 | 30 | 20 | 10 | 25 | 5 | Tswana towns on the desert edge |
| namibia | BECHUANA | 3 | 30 | 10 | 5 |  | 3 | Nama pastoralists |
| bornu | BORNU | 35 | 50 | 50 | 45 | 150 | 25 | Old Kanuri empire on Lake Chad, Islamic learning |
| hausa | BORNU | 50 | 70 | 70 | 70 |  | 35 | Kano/Katsina cotton cloth and leather, dense population |
| borneonord | BRUNEI | 25 | 90 | 25 | 15 | 100 | 25 | Brunei: camphor, sago, birds' nests |
| mindanao | BRUNEI | 15 | 60 | 40 | 20 |  | 15 | Maguindanao/Sulu raiders, slaves and pearls |
| buganda | BUGANDA | 25 | 60 | 80 | 45 | 50 | 10 | Lakeside banana kingdom, canoe fleets |
| arakan | BURMA | 20 | 50 | 50 | 25 |  | 10 | Conquered by Burma 1785 |
| ava | BURMA | 60 | 110 | 90 | 70 | 150 | 20 | Konbaung Burma under Bodawpaya; Irrawaddy rice, rubies, teak |
| pegu | BURMA | 40 | 90 | 100 | 45 |  | 25 | Lower Burma rice and teak, Rangoon |
| bahrghazal | DARFUR | 5 | 60 | 30 | 15 |  | 3 | Swamps and savanna, cattle peoples |
| darfur | DARFUR | 25 | 50 | 40 | 30 | 100 | 25 | Keira sultanate, Forty Days Road caravans to Egypt |
| wadai | DARFUR | 15 | 40 | 30 | 20 |  | 15 | Sahelian sultanate, slave raids |
| baluch | DURRANI | 10 | 40 | 15 | 15 |  | 8 | Khanate of Kalat, desert |
| kabul | DURRANI | 45 | 70 | 40 | 50 | 150 | 20 | Timur Shah's capital (from 1776), caravan hub |
| kandahar | DURRANI | 30 | 50 | 35 | 35 |  | 15 | Old Durrani capital, irrigated oasis |
| kashmir | DURRANI | 50 | 80 | 50 | 40 |  | 25 | Shawl weaving, saffron |
| multan | DURRANI | 30 | 50 | 60 | 35 |  | 15 | Durrani governorate on the Indus |
| peshawar | DURRANI | 35 | 50 | 50 | 45 |  | 15 | Winter capital, fertile vale |
| sindh | DURRANI | 35 | 50 | 60 | 40 |  | 20 | Talpur Mirs (1783), Indus irrigation |
| upperegypt | EGIPTO | 35 | 50 | 90 | 50 |  | 20 | Said: Nile grain, Mamluk beys |
| luzon | ESPANYA | 60 | 80 | 80 | 60 |  | 45 | Manila galleon (silver for silk), tobacco monopoly from 1782 |
| visayas | ESPANYA | 25 | 50 | 60 | 40 |  | 15 | Cebu, Iloilo: rice and sugar |
| ethiopia | ETHIOPIA | 40 | 80 | 70 | 60 | 150 | 15 | Gondar in the Era of the Princes; highland grain |
| senegal | FRANCIA | 30 | 40 | 30 | 25 |  | 30 | Saint-Louis and Goree: gum arabic, slave trade |
| futa | FUTA | 20 | 50 | 50 | 35 | 100 | 15 | Futa Jallon almamate, cattle, Fulani scholars |
| awadh | GRAN_BRETANYA | 80 | 90 | 110 | 100 |  | 25 | Nawab of Oudh, Lucknow; fertile and populous Ganges doab |
| bengal | GRAN_BRETANYA | 130 | 130 | 130 | 120 |  | 55 | Richest province of India: muslin, silk, rice, saltpetre; EIC revenue base |
| bihar | GRAN_BRETANYA | 60 | 120 | 100 | 80 |  | 25 | Saltpetre for Europe's gunpowder, opium monopoly |
| bombay | GRAN_BRETANYA | 50 | 60 | 35 | 40 |  | 45 | EIC island port, cotton trade to Canton |
| carnatic | GRAN_BRETANYA | 70 | 90 | 80 | 70 |  | 45 | Madras/Coromandel: calico and chintz exports |
| circars | GRAN_BRETANYA | 40 | 70 | 75 | 50 |  | 20 | Coastal rice strip ceded to the EIC 1766 |
| nsw | GRAN_BRETANYA | 5 | 30 | 10 | 5 |  | 3 | Penal colony founded Jan 1788; near famine in 1789 |
| sierra | GRAN_BRETANYA | 10 | 40 | 25 | 15 |  | 15 | Province of Freedom (1787), Bunce Island |
| semirechye | HANNOVER | 10 | 50 | 25 | 10 |  | 8 | Kazakh Middle Horde pastures |
| hyderabad | HYDERABAD | 90 | 120 | 70 | 80 | 200 | 25 | Nizam's Deccan; Golconda diamonds, large revenue |
| ezo | JAPAN | 10 | 90 | 20 | 8 |  | 10 | Matsumae fisheries and Ainu trade; Menashi-Kunashir revolt 1789 |
| honshu | JAPAN | 150 | 110 | 100 | 115 | 350 | 40 | Edo (largest city in the world), Osaka rice exchange, Kyoto crafts |
| kyushu | JAPAN | 60 | 90 | 80 | 70 |  | 35 | Satsuma, Nagasaki (Dutch/Chinese trade), Shikoku |
| korea | JOSEON | 70 | 100 | 90 | 85 | 250 | 20 | Joseon under Jeongjo: rice, ginseng, ~7 million people, closed borders |
| cameroun | KONGO | 15 | 70 | 40 | 30 |  | 15 | Duala coast trade, forest |
| kongo | KONGO | 25 | 60 | 50 | 35 | 100 | 20 | Kingdom of Kongo, fragmented by civil wars |
| loango | KONGO | 20 | 60 | 35 | 25 |  | 30 | Loango Bay slaving port |
| ubangi | KONGO | 5 | 60 | 30 | 20 |  | 5 | Rainforest, unknown to Europeans |
| kazembe | LUNDA | 20 | 70 | 35 | 25 |  | 15 | Copperbelt, link to Mozambique |
| luba | LUNDA | 15 | 70 | 40 | 30 |  | 10 | Luba kingdom, iron and copper |
| lunda | LUNDA | 25 | 70 | 40 | 30 | 50 | 15 | Mwata Yamvo empire, tribute and slave trade |
| madagascar | MADAGASCAR | 25 | 80 | 70 | 40 | 100 | 20 | Merina unification under Andrianampoinimerina; rice |
| aceh | MALAYA | 40 | 70 | 35 | 30 |  | 35 | Pepper sultanate, half the world's pepper |
| malaya | MALAYA | 40 | 90 | 30 | 25 | 100 | 40 | Johor-Riau: tin, Straits trade |
| nznorth | MAORI | 8 | 60 | 30 | 15 | 50 | 5 | Maori iwi, kumara gardens, kauri; whalers soon |
| nzsouth | MAORI | 3 | 50 | 15 | 5 |  | 3 | Sparse Ngai Tahu settlement, greenstone |
| berar | MARATHA | 40 | 110 | 70 | 50 |  | 12 | Bhonsle of Nagpur; cotton black soil |
| delhi | MARATHA | 50 | 70 | 60 | 70 |  | 25 | Mughal capital held by Scindia since 1784; wealth drained by wars |
| gujarat | MARATHA | 90 | 120 | 60 | 70 |  | 50 | Surat and Ahmedabad: cotton textiles, indigo, Indian Ocean trade |
| malwa | MARATHA | 50 | 90 | 70 | 55 |  | 25 | Holkar's Indore; opium and cotton |
| orissa | MARATHA | 35 | 70 | 80 | 45 |  | 12 | Rice delta under the Nagpur Bhonsle |
| pune | MARATHA | 90 | 100 | 70 | 90 | 250 | 25 | Peshwa's court; Deccan heartland of the Maratha Confederacy |
| rajput | MARATHA | 40 | 60 | 40 | 50 |  | 15 | Jaipur/Jodhpur/Udaipur states paying chauth; dry |
| mossi | MOSSI | 15 | 40 | 50 | 35 | 50 | 10 | Mossi kingdoms, horses and millet |
| mysore | MYSORE | 85 | 120 | 75 | 70 | 250 | 25 | Tipu Sultan's modernised state: sandalwood, silk, state trade monopolies |
| nepal | NEPAL | 25 | 60 | 40 | 35 | 100 | 12 | Gorkha kingdom, Kathmandu valley, trans-Himalayan trade |
| natal | NGUNI | 10 | 50 | 50 | 30 | 50 | 5 | Nguni chiefdoms, cattle |
| cochin | NGUYEN | 45 | 60 | 110 | 45 | 150 | 25 | Mekong delta rice; Nguyen Anh retook Saigon 1788 |
| muscat | OMAN | 60 | 40 | 25 | 30 | 150 | 50 | Omani maritime empire: Gulf and Indian Ocean shipping, dates |
| somalisor | OMAN | 15 | 40 | 20 | 15 |  | 25 | Benadir ports, Mogadishu |
| swahili | OMAN | 40 | 50 | 30 | 25 |  | 45 | Zanzibar and Kilwa under Oman: ivory, slaves, cloves soon |
| hejaz | OTOMANO | 40 | 25 | 15 | 25 |  | 40 | Mecca/Medina pilgrimage, Jeddah transit trade |
| massawa | OTOMANO | 20 | 30 | 15 | 15 |  | 25 | Red Sea port, Ethiopian outlet |
| oyo | OYO | 40 | 50 | 70 | 60 | 100 | 30 | Oyo under Abiodun; cavalry empire, Dahomey tributary, Porto-Novo trade |
| nguineaost | PAPUA | 5 | 40 | 15 | 10 | 25 | 3 | Papuan villages, untouched by trade |
| angola | PORTUGAL | 25 | 50 | 30 | 20 |  | 35 | Luanda: largest slave port of the Atlantic |
| mozambique | PORTUGAL | 25 | 50 | 25 | 15 |  | 30 | Ivory and gold via Sena and Quelimane |
| timor | PORTUGAL | 15 | 40 | 20 | 15 |  | 15 | Sandalwood; Portuguese Dili and Dutch Kupang |
| punjab | PUNJAB | 60 | 90 | 90 | 70 | 150 | 20 | Sikh misls; five-river wheat land, Lahore and Amritsar |
| amur | QING | 10 | 90 | 15 | 5 |  | 5 | Forests and sable furs, almost empty |
| dzungaria | QING | 15 | 60 | 30 | 10 |  | 8 | Ili military colony, depopulated after the 1750s wars |
| formosa | QING | 30 | 70 | 70 | 30 |  | 20 | Rice and sugar frontier; Lin Shuangwen revolt crushed 1788 |
| fujian | QING | 70 | 110 | 60 | 70 |  | 45 | Tea, sugar, Amoy junk trade to Southeast Asia; little arable land |
| guangdong | QING | 110 | 100 | 90 | 90 |  | 55 | Canton system: sole port for European trade (tea, silk, porcelain for silver) |
| huguang | QING | 60 | 110 | 130 | 100 |  | 20 | "When Huguang ripens the realm is fed": the rice bowl of China |
| innermong | QING | 20 | 60 | 30 | 20 |  | 10 | Banner pastures, Kalgan caravan trade |
| jiangnan | QING | 130 | 140 | 120 | 120 |  | 55 | Richest region on earth: silk, cotton cloth, Yangzhou salt merchants, Suzhou/Hangzhou |
| manchuria | QING | 25 | 120 | 50 | 20 |  | 8 | Banner homeland closed to Han settlers: ginseng, furs, timber |
| mongolia | QING | 15 | 70 | 25 | 15 |  | 8 | Khalkha herds and horses; Kyakhta border trade passes through |
| qinghai | QING | 10 | 50 | 20 | 10 |  | 5 | Kokonor pastures, sparse |
| sakhalin | QING | 5 | 50 | 10 | 5 |  | 3 | Ainu/Nivkh fishing and furs |
| shaanxi | QING | 40 | 90 | 60 | 60 |  | 15 | Wei valley wheat, Shanxi bankers; loess hills, modest |
| sichuan | QING | 60 | 130 | 120 | 90 |  | 15 | Red Basin "land of abundance": rice, salt wells, repopulated by 1789 |
| tibet | QING | 20 | 40 | 15 | 15 |  | 8 | Lhasa under ambans; Gorkha invasion 1788-89; barley and wool |
| xinjiang | QING | 30 | 60 | 40 | 30 |  | 20 | Kashgar/Yarkand oases on the Silk Road, jade |
| yunnan | QING | 50 | 150 | 50 | 45 |  | 12 | Copper mines minting the empire's cash, silver, tin; frontier |
| zhili | QING | 140 | 120 | 90 | 110 | 500 | 35 | Beijing: imperial capital, Grand Canal terminus, tribute grain of the empire |
| rozvi | ROZVI | 40 | 60 | 40 | 30 | 50 | 15 | Changamire Rozvi, Zimbabwe gold |
| chukotka | RUSIA | 2 | 30 | 5 | 2 |  | 2 | Unsubdued Chukchi, tundra |
| irkutsk | RUSIA | 20 | 80 | 20 | 12 |  | 30 | Kyakhta tea-for-fur trade with China |
| kamchatka | RUSIA | 5 | 60 | 10 | 3 |  | 10 | Petropavlovsk, sea otter |
| okhotsk | RUSIA | 5 | 50 | 10 | 3 |  | 8 | Pacific port of Siberia, fur trade to Alaska |
| tomsk | RUSIA | 20 | 90 | 30 | 20 |  | 10 | Tobolsk: seat of Siberia, grain belt of western Siberia |
| yakutsk | RUSIA | 10 | 70 | 8 | 5 |  | 10 | Sable furs, mammoth ivory |
| yenisei | RUSIA | 10 | 80 | 15 | 8 |  | 8 | Furs and taiga |
| air | SAJONIA | 10 | 30 | 10 | 8 |  | 15 | Agadez Tuareg sultanate, salt caravans |
| segu | SEGU | 35 | 50 | 70 | 45 | 100 | 20 | Bambara empire on the Niger, grain and slaves |
| timbuktu | SEGU | 30 | 30 | 25 | 20 |  | 35 | Saharan entrepot: gold, salt, books |
| nubia | SENNAR | 10 | 30 | 25 | 15 |  | 10 | Dongola and the Nile cataracts |
| sennar | SENNAR | 25 | 50 | 50 | 30 | 100 | 20 | Funj sultanate in decline, Blue Nile grain |
| cambodia | SIAM | 20 | 50 | 60 | 25 |  | 10 | Tonle Sap fish and rice; Siamese vassal |
| laos | SIAM | 15 | 60 | 40 | 20 |  | 5 | Vientiane/Luang Prabang under Siam, forest products |
| siam | SIAM | 70 | 90 | 100 | 60 | 200 | 35 | Rama I's new Bangkok; rice, junk trade with China |
| travancore | TRAVANCORE | 50 | 80 | 50 | 45 | 200 | 40 | Pepper and cardamom monopoly, Dutch/English trade |
| fezzan | TRIPOLITANIA | 10 | 25 | 10 | 8 |  | 20 | Murzuk, trans-Saharan slave route |
| annam | VIETNAM | 40 | 70 | 70 | 60 | 200 | 15 | Tay Son centre, Phu Xuan (Hue); Quang Trung |
| tonkin | VIETNAM | 50 | 70 | 100 | 80 |  | 20 | Red River delta, densely populated |
| somalinord | YEMEN | 15 | 40 | 15 | 15 |  | 20 | Berbera and Zeila, livestock and frankincense |
| yemen | YEMEN | 45 | 50 | 40 | 40 | 150 | 45 | Mocha coffee, terraced highlands; Zaydi imamate |
| kokand | free | 35 | 60 | 50 | 35 |  | 20 | Fergana valley khanate, silk and cotton |
| najd | free | 10 | 30 | 15 | 15 |  | 8 | First Saudi state at Diriyah, desert oases |

## Step-1 provinces (province_vals_step1.json, keyed by enum key; science kept from the current build)

| key | gold | raw | food | pop | sci | trade | why |
|---|---|---|---|---|---|---|---|
| SAHARA_OCCIDENTAL | 5 | 30 | 10 | 8 |  | 15 | Western Sahara: Berber caravans, almost empty |
| TUAT | 10 | 30 | 15 | 10 | 250 | 20 | Saharan oases, trans-Saharan crossroads (Sahara capital) |
| ARABIA | 20 | 40 | 20 | 25 | 200 | 30 | Central Arabia (Arabia capital): Wahhabi Najd and Gulf coast |
| OMAN | 40 | 40 | 25 | 25 |  | 45 | Inner Oman and the Gulf coast, dates and pearls |
| PERSIA | 70 | 90 | 60 | 70 | 200 | 30 | Iranian plateau: Shiraz/Isfahan, Zand-Qajar war; silk and carpets |
| KHORASAN | 35 | 70 | 40 | 35 |  | 20 | Mashhad, eastern marches, turquoise |
| TURKESTAN | 40 | 60 | 50 | 40 | 250 | 25 | Bukhara/Khiva oases, cotton and Silk Road |
| KAZAKHSTAN | 10 | 70 | 30 | 15 | 250 | 10 | Kazakh steppe, horses and sheep |
| URAL | 40 | 150 | 30 | 25 | 200 | 15 | Ural ironworks: largest iron producer of the world in 1789 |
| SIBERIA | 15 | 90 | 20 | 10 |  | 10 | West Siberian taiga, furs |
