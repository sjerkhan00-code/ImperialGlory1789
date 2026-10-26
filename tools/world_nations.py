"""AI nations of the bigger map, as they stood in 1789.

Every land province needs an owner with a player (the game builds an AI object per land province), so the small
realms are grouped into the historical powers of their region. Provinces are proposal ids (world_provinces.json);
the first one holds the capital.
"""
import flags as FL
from flags import rect, circle, star, crescent, rays, poly

# key, name, adjective, provinces (capital first), capital name, template nation, map colour, culture, info
NATIONS = [
    ('QING', 'Qing China', 'Chinese', ['zhili', 'shaanxi', 'sichuan', 'huguang', 'jiangnan', 'fujian', 'guangdong', 'yunnan',
     'formosa', 'manchuria', 'innermong', 'mongolia', 'qinghai', 'tibet', 'xinjiang', 'dzungaria', 'amur', 'sakhalin'], 'Beijing', 'OTOMANO', '#e2b33a', 'cn',
     'The Qianlong Emperor rules the largest and richest empire on earth from Beijing. Its armies are vast but old-fashioned, '
     'and only Canton is open to European trade.'),
    ('JAPAN', 'Japan', 'Japanese', ['honshu', 'kyushu', 'ezo'], 'Edo', 'TUNEZ', '#f2f2f2', 'jp',
     'The Tokugawa shogun keeps Japan closed to the world. Only the Dutch may trade, at Nagasaki. Its samurai have not '
     'fought a war in nearly two hundred years.'),
    ('JOSEON', 'Joseon', 'Korean', ['korea'], 'Hanseong', 'TUNEZ', '#4a6fb0', 'kr',
     'The Joseon kingdom of Korea, a loyal tributary of China, guards its peninsula and keeps foreigners out.'),
    # 'Maratha Empire', not 'Maratha Confederacy': the longer name overflowed the Select Empire banner (14 chars max)
    ('MARATHA', 'Maratha Empire', 'Maratha', ['pune', 'delhi', 'gujarat', 'malwa', 'berar', 'orissa', 'rajput'], 'Pune',
     'EGIPTO', '#e3762b', 'in',
     'The Peshwa at Pune leads the great Maratha chiefs, the strongest native power in India. They hold Delhi and the '
     'Mughal emperor, but the British watch from Bengal and Bombay.'),
    ('MYSORE', 'Mysore', 'Mysorean', ['mysore'], 'Seringapatam', 'EGIPTO', '#2f8f6a', 'in',
     'Tipu Sultan, the Tiger of Mysore, has French officers, war rockets and a burning hatred of the East India Company.'),
    ('HYDERABAD', 'Hyderabad', 'Hyderabadi', ['hyderabad'], 'Hyderabad', 'EGIPTO', '#c9a93a', 'in',
     'The Nizam of Hyderabad, richest of the Indian princes, balances between the Marathas, Mysore and the British.'),
    ('PUNJAB', 'Sikh Confederacy', 'Sikh', ['punjab'], 'Lahore', 'EGIPTO', '#ef8f2a', 'in',
     'The Sikh misls rule the land of the five rivers. A young chief named Ranjit Singh will soon unite them.'),
    ('NEPAL', 'Nepal', 'Nepalese', ['nepal'], 'Kathmandu', 'EGIPTO', '#a8323a', 'in',
     'The Gorkha kings have united the Himalayan valleys and push their borders east and west.'),
    ('DURRANI', 'Durrani Empire', 'Afghan', ['kabul', 'kandahar', 'peshawar', 'multan', 'baluch', 'kashmir', 'sindh'], 'Kabul', 'OTOMANO', '#5d8c3a', 'ar',
     'Timur Shah rules the Afghan empire of Ahmad Shah Durrani, from Kashmir to the Arabian Sea.'),
    ('BURMA', 'Burma', 'Burmese', ['ava', 'pegu', 'arakan'], 'Amarapura', 'TUNEZ', '#b8c84a', 'se',
     'King Bodawpaya of the Konbaung dynasty has conquered Arakan and dreams of more.'),
    ('SIAM', 'Siam', 'Siamese', ['siam', 'laos', 'cambodia'], 'Bangkok', 'TUNEZ', '#d13c3c', 'se',
     'King Rama I has built a new capital at Bangkok and made Laos and Cambodia his vassals.'),
    ('VIETNAM', 'Dai Viet', 'Vietnamese', ['annam', 'tonkin'], 'Phu Xuan', 'TUNEZ', '#e8c547', 'se',
     'The Tay Son brothers have overthrown the old lords of Vietnam, while the Nguyen prince seeks French help.'),
    ('MALAYA', 'Malay Sultanates', 'Malay', ['malaya', 'aceh'], 'Johor', 'MARRUECOS', '#3a8c8c', 'se',
     'The sultans of Johor and Aceh control the Strait of Malacca, the gate between the Indian Ocean and China.'),
    ('BRUNEI', 'Brunei and Sulu', 'Bruneian', ['borneonord', 'mindanao'], 'Brunei', 'MARRUECOS', '#8a6d3a', 'se',
     'The sultans of Brunei and Sulu rule the coasts of Borneo and the southern Philippines, home of feared sea raiders.'),
    ('MAORI', 'Aotearoa', 'Maori', ['nznorth', 'nzsouth'], 'Kororareka', 'MARRUECOS', '#3a3a3a', 'mi',
     'The Maori tribes of Aotearoa have seen only a few European ships. Their war canoes and hill forts are formidable.'),
    ('ETHIOPIA', 'Ethiopia', 'Ethiopian', ['ethiopia'], 'Gondar', 'EGIPTO', '#4f9a3c', 'af',
     'The ancient Christian empire of Ethiopia is ruled in name by the emperor at Gondar and in fact by its warlords.'),
    ('OMAN', 'Oman and Zanzibar', 'Omani', ['muscat', 'swahili', 'somalisor'], 'Muscat', 'TRIPOLITANIA', '#c0392b', 'ar',
     'From Muscat the Al Bu Said sultans rule Oman and, through their governors at Zanzibar and Kilwa, the Swahili coast. '
     'Only Mombasa under the Mazrui defies them.'),
    ('SENNAR', 'Sennar', 'Funj', ['sennar', 'nubia'], 'Sennar', 'TRIPOLITANIA', '#3c3c5a', 'af',
     'The Funj sultanate of Sennar controls the Blue and White Niles south of Egypt.'),
    ('DARFUR', 'Darfur', 'Fur', ['darfur', 'wadai', 'bahrghazal'], 'El Fasher', 'TRIPOLITANIA', '#6a8a3a', 'af',
     'The sultans of Darfur and Wadai command the caravan roads between the Nile and Lake Chad.'),
    ('BORNU', 'Bornu', 'Bornuan', ['bornu', 'hausa'], 'Birni Ngazargamu', 'MARRUECOS', '#7a9a4a', 'af',
     'The thousand-year-old empire of Bornu and the Hausa cities trade across the Sahara.'),
    ('SEGU', 'Segu', 'Bambara', ['segu', 'timbuktu'], 'Segu', 'MARRUECOS', '#9a6a3a', 'af',
     'The Bambara kings of Segu rule the middle Niger and take tribute from Timbuktu.'),
    ('ASHANTI', 'Ashanti', 'Ashanti', ['ashanti', 'ivory'], 'Kumasi', 'MARRUECOS', '#d9a520', 'af',
     'The Asantehene rules a rich and well-organised kingdom of gold, with a strong army and the Golden Stool.'),
    ('OYO', 'Oyo', 'Oyo', ['oyo'], 'Oyo-Ile', 'MARRUECOS', '#b5452f', 'af',
     'The Oyo empire and its cavalry dominate the Yoruba lands; Dahomey pays it tribute.'),
    ('KONGO', 'Kongo', 'Kongo', ['kongo', 'loango', 'ubangi', 'cameroun'], 'Mbanza Kongo', 'MARRUECOS', '#a33a5a', 'af',
     'The old Christian kingdom of Kongo and the coastal realms trade with Portuguese and Dutch ships.'),
    ('LUNDA', 'Lunda', 'Lunda', ['lunda', 'luba', 'kazembe'], 'Musumba', 'MARRUECOS', '#5a7a9a', 'af',
     'The Mwata Yamvo of Lunda and the Luba kings rule the heart of Africa.'),
    ('BUGANDA', 'Buganda', 'Ganda', ['buganda'], 'Mengo', 'MARRUECOS', '#3a6aa0', 'af',
     'The Kabaka of Buganda rules a strong kingdom on the shores of Lake Victoria.'),
    ('ROZVI', 'Rozvi', 'Rozvi', ['rozvi'], 'Danangombe', 'MARRUECOS', '#8a5a2a', 'af',
     'The Rozvi Mambos hold the gold country between the Zambezi and the Limpopo.'),
    ('MADAGASCAR', 'Madagascar', 'Malagasy', ['madagascar'], 'Ambohimanga', 'MARRUECOS', '#c8c8a0', 'af',
     'King Andrianampoinimerina is uniting the Merina highlands of Madagascar.'),
    # added after the 1789 audit (re_tools/report_history.md); appended so the older folder numbers stay the same
    ('ABORIGINES', 'Aboriginal Nations', 'Aboriginal', ['northaus', 'westaus', 'southaus', 'queensland', 'tasmania'], 'Uluru',
     'MARRUECOS', '#a0522d', 'au', 'Hundreds of Aboriginal nations have lived on this continent for more than forty thousand years. '
     'In 1788 a British fleet founded a penal colony at Sydney Cove; the rest of the land is still theirs.'),
    ('YEMEN', 'Yemen', 'Yemeni', ['yemen', 'somalinord'], 'Sanaa', 'TRIPOLITANIA', '#6b8e23', 'ar',
     'The Zaydi imams of Sanaa rule the highlands of Yemen. The coffee of Mocha is drunk all over the world.'),
    ('NGUNI', 'Nguni Chiefdoms', 'Nguni', ['natal'], 'Ondini', 'MARRUECOS', '#7a3a2a', 'af',
     'The Mthethwa, Ndwandwe, Swazi and Xhosa chiefdoms between the mountains and the Indian Ocean grow in strength.'),
    ('BECHUANA', 'Tswana Chiefdoms', 'Tswana', ['kalahari', 'namibia'], 'Lattakoo', 'MARRUECOS', '#b08a4a', 'af',
     'Tswana towns at the edge of the Kalahari, and the Nama and Herero herders beyond, trade cattle, copper and ivory.'),
    ('AHOM', 'Ahom Kingdom', 'Ahom', ['assam'], 'Rangpur', 'EGIPTO', '#6a8f3a', 'in',
     'The six-hundred-year-old Ahom kingdom of Assam is torn by the Moamoria rebellion.'),
    ('TRAVANCORE', 'Travancore', 'Travancorean', ['travancore'], 'Padmanabhapuram', 'EGIPTO', '#c84a4a', 'in',
     'The Raja of Travancore, ally of the East India Company, guards his fortified lines against Tipu Sultan.'),
    ('NGUYEN', 'Nguyen Lords', 'Nguyen', ['cochin'], 'Gia Dinh', 'TUNEZ', '#d8b02a', 'se',
     'Prince Nguyen Anh has retaken Saigon from the Tay Son and seeks French help to win back all of Vietnam.'),
    ('FUTA', 'Futa Jallon', 'Fula', ['futa'], 'Timbo', 'MARRUECOS', '#e0d8b0', 'af',
     'The almamys of Futa Jallon rule a Muslim theocracy in the highlands where the Niger and the Senegal rise.'),
    ('MOSSI', 'Mossi Kingdoms', 'Mossi', ['mossi'], 'Ouagadougou', 'MARRUECOS', '#b86a2a', 'af',
     'The Mogho Naba of Ouagadougou and the kings of Yatenga have kept their horsemen free for centuries.'),
    ('PAPUA', 'Papua', 'Papuan', ['nguineaost'], 'Hanuabada', 'MARRUECOS', '#4a6a3a', 'au',
     'The peoples of eastern New Guinea have seen hardly any European ships.'),
]
# provinces that go to an existing country instead of staying free
EXTRA_OWNER = {'awadh': 'GRAN_BRETANYA', 'sunda': 'BATAVIA', 'nguineavest': 'BATAVIA', 'borneosor': 'BATAVIA',
               'air': 'SAJONIA', 'upperegypt': 'EGIPTO', 'fezzan': 'TRIPOLITANIA'}
EXTRA_TO_NATION = {'kokand': 'TURKESTAN', 'najd': 'ARABIA'}

MODELS = {'OTOMANO': '07Otomano', 'EGIPTO': '08Egipto', 'MARRUECOS': '22Marruecos', 'TUNEZ': '23Tunez',
          'TRIPOLITANIA': '24Tripolitania'}

GIVEN = {
    'cn': ['Fuk\'anggan', 'Heshen', 'Agui', 'Hailancha', 'Mingliang', 'Li Shiyao', 'Sun Shiyi', 'Fu Kang', 'Zhaohui', 'Wang Jie',
           'Liu Yong', 'Ji Yun', 'He Lin', 'E Hui', 'Ledeng', 'Yang Yuchun', 'Yang Fang', 'Chang Ling', 'Qing Gui', 'Bao Ning'],
    'jp': ['Matsudaira Sadanobu', 'Tanuma Okitsugu', 'Date Shigemura', 'Shimazu Shigehide', 'Hosokawa Shigekata', 'Mori Haruchika',
           'Ii Naohide', 'Sakai Tadazumi', 'Abe Masatomo', 'Honda Tadakazu', 'Toda Ujinori', 'Ogasawara Tadahiro',
           'Uesugi Harunori', 'Nabeshima Harushige', 'Kuroda Harutaka', 'Ikeda Harumasa', 'Asano Shigeakira', 'Hachisuka Haruaki',
           'Tsugaru Nobuharu', 'Matsumae Michihiro'],
    'kr': ['Yi San', 'Chae Je-gong', 'Kim Jong-su', 'Yun Si-dong', 'Pak Che-ga', 'Jeong Yak-yong', 'Kim Jo-sun', 'Hong Guk-yeong',
           'Yi Byeong-mo', 'Seo Yu-rin', 'Sim Hwan-ji', 'Kim Gwan-ju', 'Yi Si-su', 'Han Yong-gu', 'Kang Se-hwang', 'Jo Jin-gwan'],
    'in': ['Mahadji Scindia', 'Tukoji Holkar', 'Nana Phadnavis', 'Haripant Phadke', 'Parashuram Bhau', 'Daulat Rao', 'Yashwant Rao',
           'Raghuji Bhonsle', 'Ranjit Singh', 'Mahan Singh', 'Purnaiya', 'Sayyid Saheb', 'Mir Alam', 'Raja Ram', 'Bahadur Shah',
           'Damaji Gaekwad', 'Ahilyabai', 'Tipu Sultan', 'Haidar Ali', 'Kamar ud-Din', 'Amrit Rao', 'Balaji Rao', 'Jaswant Singh',
           'Prithvi Narayan'],
    'se': ['Bodawpaya', 'Maha Thiha', 'Thado Minsaw', 'Chaophraya Chakri', 'Maha Sura Singhanat', 'Nguyen Hue', 'Nguyen Nhac',
           'Nguyen Lu', 'Tran Quang Dieu', 'Bui Thi Xuan', 'Vo Van Dung', 'Le Van Duyet', 'Abdul Jalil', 'Mahmud Shah',
           'Alauddin', 'Muhammad Kanzul Alam', 'Azim ud-Din', 'Datu Kudarat', 'Raja Haji', 'Sultan Omar'],
    'ar': ['Timur Shah', 'Zaman Shah', 'Payinda Khan', 'Madad Khan', 'Fateh Khan', 'Shah Wali Khan', 'Said bin Sultan',
           'Hamad bin Said', 'Sultan bin Ahmad', 'Saif bin Ali', 'Badr bin Saif', 'Hilal bin Ahmad', 'Mir Fateh Ali', 'Nasir Khan',
           'Mahmud Shah', 'Shuja ul-Mulk', 'Ali Khan', 'Abdullah Khan', 'Rahmat Khan', 'Yusuf Khan'],
    'af': ['Osei Kwame', 'Osei Bonsu', 'Opoku Ware', 'Abiodun', 'Awole', 'Kpengla', 'Mansong Diarra', 'Ngolo Diarra',
           'Ali Dunamami', 'Ahmad Alimi', 'Abd al-Rahman', 'Muhammad Tayrab', 'Adlan', 'Badi VI', 'Tekle Giyorgis', 'Ras Mikael',
           'Mwata Yamvo', 'Ilunga Sungu', 'Kabaka Junju', 'Changamire Dombo', 'Andrianampoinimerina', 'Hongi Hika', 'Te Rauparaha',
           'Pedro V', 'Kanyembo', 'Kazembe Lukwesa', 'Zwide', 'Dingiswayo'],
}
SHIPS = {
    'cn': ['Dragon', 'Phoenix', 'Jade Wave', 'Golden Junk', 'Pearl River', 'Eastern Sea', 'Heaven\'s Order', 'Lotus', 'Crane', 'Tiger'],
    'jp': ['Tenchi Maru', 'Fuji Maru', 'Kaze Maru', 'Nami Maru', 'Taka Maru', 'Ryu Maru', 'Sakura Maru', 'Kame Maru', 'Asahi Maru', 'Tsuru Maru'],
    'kr': ['Geobukseon', 'Panokseon', 'Haedong', 'Hanbada', 'Cheonji', 'Baekdu', 'Mugunghwa', 'Chungmu', 'Gyeongbok', 'Halla'],
    'in': ['Ganga', 'Ghurab', 'Shivaji', 'Sindhu', 'Tiger of Mysore', 'Bhavani', 'Maratha Star', 'Deccan', 'Konkan', 'Narmada'],
    'se': ['Garuda', 'Naga', 'Irrawaddy', 'Mekong', 'Chao Phraya', 'Lancang', 'Kris', 'Lanong', 'Sea Raider', 'Monsoon'],
    'ar': ['Dhow of Muscat', 'Al-Rahmani', 'Shah Allam', 'Sultani', 'Zanzibar', 'Al-Badr', 'Sea of Oman', 'Hormuz', 'Najm', 'Saif'],
    'af': ['Great Canoe', 'River King', 'Lake Spirit', 'Niger', 'Zambezi', 'Golden Stool', 'Leopard', 'Lion of Kongo', 'Waka', 'Monsoon'],
}
GIVEN['au'] = ['Bennelong', 'Pemulwuy', 'Arabanoo', 'Colebee', 'Barangaroo', 'Yemmerrawanne', 'Bungaree', 'Nanbaree',
               'Boorong', 'Daringa', 'Patyegarang', 'Gnung-a Gnung-a', 'Tedbury', 'Musquito', 'Bidgee Bidgee', 'Yuranigh']
GIVEN['mi'] = ['Hongi Hika', 'Te Rauparaha', 'Te Pahi', 'Titore', 'Te Morenga', 'Pomare', 'Tareha', 'Te Wherowhero',
               'Te Rangihaeata', 'Patuone', 'Waka Nene', 'Kawiti', 'Te Waharoa', 'Korokoro', 'Ruatara', 'Te Hapuku']
SHIPS['au'] = ['Nawi', 'Bark Canoe', 'Red Ochre', 'Southern Cross', 'Emu', 'Brolga', 'Wattle', 'Warrigal', 'Dreaming', 'Kangaroo']
SHIPS['mi'] = ['Tainui', 'Te Arawa', 'Mataatua', 'Aotea', 'Tokomaru', 'Takitimu', 'Kurahaupo', 'Horouta', 'Tinana', 'Waka Taua']
HEIR = {'au': ('Barangaroo', 'Yemmerrawanne'), 'mi': ('Princess Rangi', 'Prince Ruatara'), 'cn': ('Hexiao', 'Yongyan'), 'jp': ('Kazunomiya', 'Ienari'), 'kr': ('Princess Hyeon', 'Yi Gong'),
        'in': ('Lakshmibai', 'Madhav Rao'), 'se': ('Princess Ngoc', 'Prince Chakri'), 'ar': ('Princess Aisha', 'Mahmud'),
        'af': ('Princess Ama', 'Prince Kwaku')}


def _flag(key, col):
    """Simple period-inspired banners."""
    c = col
    D = {
        'QING': [rect(0, 0, 1, 1, '#f2c12e'), circle(0.68, 0.30, 0.10, '#d13c3c'), poly([(0.15, 0.70), (0.35, 0.45), (0.55, 0.62),
                 (0.78, 0.40), (0.82, 0.52), (0.58, 0.76), (0.36, 0.60), (0.20, 0.80)], '#2a4a9a')],
        'JAPAN': [rect(0, 0, 1, 1, '#f7f7f2'), circle(0.5, 0.5, 0.26, '#c8102e')],
        'JOSEON': [rect(0, 0, 1, 1, '#f7f7f2'), circle(0.5, 0.5, 0.24, '#c8102e'), poly([(0.26, 0.5), (0.74, 0.5), (0.74, 0.62),
                   (0.5, 0.74), (0.26, 0.62)], '#2a4a9a')],
        'MARATHA': [rect(0, 0, 1, 1, '#ef7d1a'), poly([(0.75, 0), (1, 0), (1, 1), (0.75, 1), (0.88, 0.5)], '#f7f7f2')],
        'MYSORE': [rect(0, 0, 1, 1, '#2f8f4a')] + [rect(0.1 + 0.16 * k, 0.15, 0.17 + 0.16 * k, 0.85, '#e0a020') for k in range(5)],
        'HYDERABAD': [rect(0, 0, 1, 1, '#e8c547'), circle(0.5, 0.5, 0.18, '#f7f7f2')],
        'PUNJAB': [rect(0, 0, 1, 1, '#ef8f2a'), circle(0.5, 0.5, 0.2, '#2a3a8a'), rect(0.48, 0.2, 0.52, 0.8, '#2a3a8a')],
        'NEPAL': [rect(0, 0, 1, 1, '#a8323a'), circle(0.35, 0.35, 0.12, '#f7f7f2'), circle(0.35, 0.72, 0.12, '#f7f7f2')],
        'DURRANI': [rect(0, 0, 1, 1, '#2f6a2a'), crescent(0.45, 0.5, 0.22, 0.09, '#f7f7f2'), star(0.62, 0.5, 0.09, '#f7f7f2')],
        'BURMA': [rect(0, 0, 1, 1, '#f7f7f2'), circle(0.5, 0.5, 0.2, '#e0a020'), poly([(0.4, 0.55), (0.5, 0.3), (0.6, 0.55)], '#2a6a3a')],
        'SIAM': [rect(0, 0, 1, 1, '#c8102e')],
        'VIETNAM': [rect(0, 0, 1, 1, '#e8c547'), rect(0, 0.4, 1, 0.6, '#c8102e')],
        'MALAYA': [rect(0, 0, 1, 0.5, '#e8c547'), rect(0, 0.5, 1, 1, '#1a1a1a')],
        'BRUNEI': [rect(0, 0, 1, 1, '#e8c547'), poly([(0, 0.3), (1, 0.6), (1, 0.75), (0, 0.45)], '#f7f7f2'),
                   poly([(0, 0.45), (1, 0.75), (1, 0.9), (0, 0.6)], '#1a1a1a')],
        'MAORI': [rect(0, 0, 1, 1, '#1a1a1a'), rect(0, 0, 0.5, 0.5, '#c8102e'), circle(0.5, 0.5, 0.15, '#f7f7f2')],
        'ETHIOPIA': [rect(0, 0, 1, 0.34, '#2f8f2a'), rect(0, 0.34, 1, 0.67, '#f2c12e'), rect(0, 0.67, 1, 1, '#c8102e')],
        'OMAN': [rect(0, 0, 1, 1, '#c8102e')],
        'SENNAR': [rect(0, 0, 1, 1, '#1a1a2a'), crescent(0.5, 0.5, 0.22, 0.09, '#e8c547')],
        'DARFUR': [rect(0, 0, 1, 1, '#4f7a2a'), crescent(0.5, 0.5, 0.22, 0.09, '#f7f7f2')],
        'BORNU': [rect(0, 0, 1, 1, '#3a7a3a'), rect(0, 0.42, 1, 0.58, '#f7f7f2')],
        'SEGU': [rect(0, 0, 1, 1, '#8a5a2a'), poly([(0.5, 0.15), (0.8, 0.85), (0.2, 0.85)], '#e8d8a0')],
        'ASHANTI': [rect(0, 0, 1, 0.34, '#e0a020'), rect(0, 0.34, 1, 0.67, '#2f6a2a'), rect(0, 0.67, 1, 1, '#1a1a1a'),
                    rect(0.38, 0.4, 0.62, 0.6, '#e0a020')],
        'OYO': [rect(0, 0, 1, 1, '#b5452f'), circle(0.5, 0.5, 0.2, '#e8d8a0')],
        'KONGO': [rect(0, 0, 1, 1, '#a33a3a'), rect(0.44, 0.15, 0.56, 0.85, '#f7f7f2'), rect(0.28, 0.38, 0.72, 0.5, '#f7f7f2')],
        'LUNDA': [rect(0, 0, 1, 1, '#3a6a8a'), star(0.5, 0.5, 0.2, '#e8c547')],
        'BUGANDA': [rect(0, 0, 1, 1, '#2a5aa0'), circle(0.5, 0.5, 0.18, '#f7f7f2'), rect(0, 0.85, 1, 1, '#e8c547')],
        'ROZVI': [rect(0, 0, 1, 1, '#7a4a20'), rays(0.5, 0.5, 0.12, 0.24, 12, 0.2, '#e8c547'), circle(0.5, 0.5, 0.12, '#e8c547')],
        'MADAGASCAR': [rect(0, 0, 0.35, 1, '#f7f7f2'), rect(0.35, 0, 1, 0.5, '#c8102e'), rect(0.35, 0.5, 1, 1, '#2f8f2a')],
        'ABORIGINES': [rect(0, 0, 1, 1, '#a0522d'), circle(0.5, 0.5, 0.16, '#f2e6c8'), rect(0, 0.82, 1, 1, '#1a1a1a')],
        'YEMEN': [rect(0, 0, 1, 1, '#c8102e'), rect(0, 0.4, 1, 0.6, '#f7f7f2')],
        'NGUNI': [rect(0, 0, 1, 1, '#7a3a2a'), poly([(0.5, 0.1), (0.62, 0.5), (0.5, 0.9), (0.38, 0.5)], '#f2e6c8')],
        'BECHUANA': [rect(0, 0, 1, 1, '#b08a4a'), circle(0.5, 0.5, 0.2, '#3a2a1a')],
        'AHOM': [rect(0, 0, 1, 1, '#6a8f3a'), circle(0.5, 0.5, 0.18, '#e8c547')],
        'TRAVANCORE': [rect(0, 0, 1, 1, '#c84a4a'), star(0.5, 0.5, 0.2, '#f7f7f2')],
        'NGUYEN': [rect(0, 0, 1, 1, '#d8b02a'), circle(0.5, 0.5, 0.2, '#c8102e')],
        'FUTA': [rect(0, 0, 1, 1, '#f7f7f2'), crescent(0.5, 0.5, 0.22, 0.09, '#2f6a2a')],
        'MOSSI': [rect(0, 0, 1, 1, '#b86a2a'), rect(0, 0, 1, 0.2, '#1a1a1a'), rect(0, 0.8, 1, 1, '#1a1a1a')],
        'PAPUA': [rect(0, 0, 1, 1, '#4a6a3a'), poly([(0, 1), (1, 0), (1, 1)], '#1a1a1a')],
        'INDEPENDENT': [rect(0, 0, 1, 1, c), rect(0, 0.42, 1, 0.58, '#e8dcc0'), rect(0.42, 0, 0.58, 1, '#e8dcc0')],   # region banner
    }
    return D.get(key, [rect(0, 0, 1, 1, c)])


# only great powers play (user's decision, playtest 2026-10-16); the land of the small nations goes to one shared
# owner without AI planning (nations.AI_SKIP) and can still be conquered
MERGED = ['HYDERABAD', 'PUNJAB', 'NEPAL', 'MALAYA', 'BRUNEI', 'MAORI', 'SENNAR', 'DARFUR', 'BORNU', 'SEGU', 'ASHANTI',
          'OYO', 'KONGO', 'LUNDA', 'BUGANDA', 'ROZVI', 'MADAGASCAR', 'ABORIGINES', 'YEMEN', 'NGUNI', 'BECHUANA', 'AHOM',
          'TRAVANCORE', 'NGUYEN', 'FUTA', 'MOSSI', 'PAPUA',
          'JOSEON', 'BURMA', 'SIAM', 'VIETNAM', 'MYSORE', 'DURRANI', 'OMAN']   # 2026-10-17: fewer AI players
# the merged land is split into regional owners, each with its own capital (taking one capital must not hand over
# half the world); none of them plans an AI turn (nations.AI_SKIP). Two regions use the freed original slots of
# Saxony (the Sahel) and Moldavia (southern Africa) instead of new players.
# map colour of each regional owner (country record RGB via nations.bgr3, UIDefs_IdentificadoresColorPaises, and the
# field of the region banner). Until 2026-10-21 all seven shared '#6b6455', so neighbouring regions read as one (review
# V3). Muted, darkish hues in the style of the original palette (Austria #7e6b2c, Russia #4e6743, Moldavia #57637d),
# each at least dE76 ~20 from every neighbour's colour (land neighbours of the 01:47 build):
REGION_COLOUR = {'INDEPENDENT': '#3e6f6c',   # Eastern Kingdoms: teal (Qing yellow, Princes olive, British brick)
                 'PRINCES': '#6e7042',       # Indian Princes: olive (Maratha / Persia orange, Turkestan violet)
                 'SHEIKHS': '#80543e',       # Arabian Sheikhdoms: sienna (Arabia rose, Ethiopia green, Nile blue)
                 'NILE': '#526a94',          # Nile Kingdoms: slate blue (Egypt / Ottoman greys, Sahel ochre)
                 'PACIFIC': '#5b7452',       # Pacific Peoples: sage (British brick, Dutch grey)
                 'MOLDAVIA': '#7d5068',      # Southern Kingdoms (Moldavia's slot): dusty rose
                 'SAJONIA': '#8a7036'}       # Sahel Kingdoms (Saxony's slot): ochre (French blue, Moroccan grey)
IND_INFO = ('Kingdoms, sultanates, chiefdoms and free peoples that answer to no great power. They defend their land, '
            'but they do not seek conquest.')
REGIONS = [   # key, name, adjective, merged nations (first one's first province = capital), capital, culture
    ('INDEPENDENT', 'Eastern Kingdoms', 'Eastern', ['JOSEON', 'BURMA', 'SIAM', 'VIETNAM', 'NGUYEN', 'MALAYA', 'BRUNEI'], 'Hanseong', 'kr'),
    ('PRINCES', 'Indian Princes', 'Indian', ['HYDERABAD', 'PUNJAB', 'NEPAL', 'MYSORE', 'TRAVANCORE', 'AHOM', 'DURRANI'], 'Hyderabad', 'in'),
    ('SHEIKHS', 'Arabian Sheikhdoms', 'Arabian', ['OMAN', 'YEMEN'], 'Muscat', 'ar'),
    ('NILE', 'Nile Kingdoms', 'Nilotic', ['SENNAR', 'DARFUR', 'BUGANDA'], 'Sennar', 'af'),
    ('PACIFIC', 'Pacific Peoples', 'Pacific', ['MAORI', 'ABORIGINES', 'PAPUA'], 'Kororareka', 'mi'),
]
REGION_FOLDER = {'INDEPENDENT': 66, 'PRINCES': 68, 'SHEIKHS': 69, 'NILE': 70, 'PACIFIC': 71}   # 67 = Chechenya
RESKIN_REGIONS = {'SAJONIA': ['SEGU', 'ASHANTI', 'OYO', 'FUTA', 'MOSSI', 'BORNU'],
                  'MOLDAVIA': ['ROZVI', 'KONGO', 'LUNDA', 'NGUNI', 'BECHUANA', 'MADAGASCAR']}
_prov_of = {n[0]: n[3] for n in NATIONS}
assert sorted(sum([r[3] for r in REGIONS], []) + sum(RESKIN_REGIONS.values(), [])) == sorted(MERGED)
for _k, _name, _adj, _ns, _cap, _cult in REGIONS:
    _tpl = {'PRINCES': 'EGIPTO', 'SHEIKHS': 'TRIPOLITANIA', 'NILE': 'TRIPOLITANIA'}.get(_k, 'MARRUECOS')   # as the merged nations had
    NATIONS.append((_k, _name, _adj, [p for n in _ns for p in _prov_of[n]], _cap, _tpl, REGION_COLOUR[_k], _cult, IND_INFO))
RESKIN_REGION_PROVS = {c: [p for n in ns for p in _prov_of[n]] for c, ns in RESKIN_REGIONS.items()}
for _c, _ps in RESKIN_REGION_PROVS.items():
    for _p in _ps:
        EXTRA_OWNER[_p] = _c
REGION_KEYS = [r[0] for r in REGIONS]


# starting treasury of the great powers that stay (gold, raw materials, food, population, 0); Russia has 1750/3750/500/2400
START = {'QING': [2600, 3000, 600, 2800, 0], 'MARATHA': [2000, 1800, 400, 2000, 0], 'JAPAN': [1600, 1800, 450, 1800, 0],
         'ETHIOPIA': [1000, 1100, 250, 1300, 0]}


def install(nations_module, first_folder=28):
    """Add the nations to nations.py's tables and flags.py's designs/colours."""
    NT = nations_module
    for k, (key, name, adj, provs, cap, tpl, col, cult, info) in enumerate(NATIONS):
        if key in MERGED:
            continue                                    # folder numbers of the others stay the same
        g = GIVEN[cult]
        officers = [(g[i % len(g)] + ('' if i < len(g) else ' the Younger' if i < 2 * len(g) else ' of %s' % cap)) for i in range(48)]
        s = SHIPS[cult]
        ships = [(s[i % len(s)] + ('' if i < len(s) else ' %d' % (i // len(s) + 1))) for i in range(55)]
        NT.NEW_NATIONS.append(dict(key=key, name=name, adjective=adj, world_provinces=provs, provinces=[], capital_prov=None,
                                   capital_key='CAP_' + key, capital=cap, template=tpl, template_player='JUG_' + tpl,
                                   models=MODELS[tpl], folder='%02d%s' % (REGION_FOLDER.get(key, first_folder + k), key.title()),
                                   units='DefUnidadesArabes.sb', start=list(START.get(key, [700, 900, 150, 1100, 0])), info=info, ai_only=True))
        NT.OFFICERS[key] = officers
        NT.SHIP_WORDS[key] = ships
        NT.HEIRS[key] = HEIR[cult]
        FL.DESIGNS[key] = _flag('INDEPENDENT' if key in REGION_KEYS else key, col)
        FL.COLOURS[key] = col
    # the two regions in the Moldavia / Saxony slots (nations.RESKIN_PLAYABLE designs REGION_MOLDAVIA / REGION_SAJONIA)
    for key in RESKIN_REGIONS:
        FL.DESIGNS['REGION_' + key] = _flag('INDEPENDENT', REGION_COLOUR[key])
        FL.COLOURS['REGION_' + key] = REGION_COLOUR[key]
