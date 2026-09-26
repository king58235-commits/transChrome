# Live-session translation regression set (2026-09-26, RTX 4070 Ti, HARDWARE_PRESET="high").
# Source: one live YouTube session (hololive members' chat/game stream, with a
# short baseball-game segment at the start). Every translation unit the
# production pipeline produced in that session is included, in order — good
# ones too, so a decoding change can be checked for regressions, not only fixes.
#
# Fields:
#   ja           the exact text sent to the translator ([TRANSLATION BUFFER] text=)
#   baseline_zh  the exact production output for it ([ZH-TW]), with the config at
#                the time: MADLAD-400 3B int8_float16 on CUDA, beam_size=4,
#                no_repeat_ngram_size=3, <2zh> + OpenCC s2twp. Re-running the
#                same config offline should reproduce it; if not, fix that first.
#   ref          hand-written rough reference (meaning/tone only, not literary)
#   issue        what was wrong with baseline_zh:
#                  ok        acceptable
#                  padding   adds content the Japanese doesn't have
#                  duplicate says the same thing twice in different words
#                  loop      repetition loop
#                  mistrans  wrong meaning
#                  name      proper noun (member name) mangled
#                  fragment  input is a short piece with no context
#   stt_uncertain  ja itself looks misrecognized; exclude when judging the
#                  translator alone. ja_likely gives the probable real speech.
#
# No audio for this session was kept, so this set can only test the
# translation side (decoding settings, name glossary), not STT or buffering.

LIVE_DATASET = [
    # ---- Baseball segment ----
    {"id": "L00", "ja": "集計", "baseline_zh": "集中計算。",
     "ref": "（統計；前後文不明）", "issue": ["fragment", "mistrans"], "stt_uncertain": True},
    {"id": "L01", "ja": "ああ", "baseline_zh": "哦，是的，我很喜歡它。",
     "ref": "啊", "issue": ["padding"], "stt_uncertain": False},
    {"id": "L02", "ja": "ここまでにやんだの福田", "baseline_zh": "到目前為止做的福田福田。",
     "ref": "到目前為止擊出2支安打的福田", "issue": ["mistrans", "duplicate"], "stt_uncertain": True,
     "ja_likely": "ここまで2安打の福田"},
    {"id": "L03", "ja": "これは", "baseline_zh": "這是這樣的,這是這麼回事。",
     "ref": "這是", "issue": ["fragment", "padding", "duplicate"], "stt_uncertain": False},
    {"id": "L04", "ja": "台出しを", "baseline_zh": "臺出來臺出去。",
     "ref": "（語意不明）", "issue": ["fragment", "mistrans"], "stt_uncertain": True},
    {"id": "L05", "ja": "ヨフィーの代打", "baseline_zh": "約菲的代打。",
     "ref": "代打 Iofi", "issue": ["name"], "stt_uncertain": True, "ja_likely": "イオフィの代打"},
    {"id": "L06", "ja": "イオフィン出番だよ", "baseline_zh": "現在是伊奧芬的時候了",
     "ref": "輪到 Iofi 上場了喔", "issue": ["name"], "stt_uncertain": True, "ja_likely": "イオフィ、出番だよ"},
    {"id": "L07", "ja": "ファイトーミート積極転がせや第9",
     "baseline_zh": " 2001年，第9屆金馬獎最佳男主角，獲得第9名。",
     "ref": "加油！確實擊球！積極點，打成滾地球啊（第9…）", "issue": ["mistrans", "padding"], "stt_uncertain": False},
    {"id": "L08", "ja": "頑張ろうよフィ", "baseline_zh": "讓我們努力吧，菲。",
     "ref": "加油啊（Io）fi", "issue": ["name"], "stt_uncertain": True},
    {"id": "L09", "ja": "さあ次の投球投げましたボール", "baseline_zh": "現在,下一輪投球,我扔了球。",
     "ref": "好，下一球，投出去了，壞球", "issue": ["mistrans"], "stt_uncertain": False},
    {"id": "L10", "ja": "第3球場", "baseline_zh": "第3球場球場。",
     "ref": "第3球", "issue": ["duplicate"], "stt_uncertain": True, "ja_likely": "第3球"},
    {"id": "L11", "ja": "うわぁ!", "baseline_zh": "哇哦!",
     "ref": "哇！", "issue": ["ok"], "stt_uncertain": False},
    {"id": "L12", "ja": "頑張ろう、ヨフィ、代打丸", "baseline_zh": "讓我們努力,約菲,代打丸。",
     "ref": "加油，Iofi，代打…", "issue": ["name"], "stt_uncertain": True},

    # ---- Chat: collab announcement ----
    {"id": "L13", "ja": "期間があって", "baseline_zh": "過了一段時間，她們就分手了。",
     "ref": "有一段期間", "issue": ["fragment", "padding"], "stt_uncertain": False},
    {"id": "L14", "ja": "で", "baseline_zh": "並且在 的情況下。",
     "ref": "然後", "issue": ["fragment", "mistrans"], "stt_uncertain": False},
    {"id": "L15", "ja": "1か月後に解禁です誰とコラボするんだ", "baseline_zh": "1個月後解禁，我要和誰合作呢？",
     "ref": "一個月後解禁，是要跟誰合作呢", "issue": ["ok"], "stt_uncertain": False},
    {"id": "L16", "ja": "初コラボ", "baseline_zh": "首次合作，首次協作。",
     "ref": "第一次合作", "issue": ["duplicate"], "stt_uncertain": False},
    {"id": "L17", "ja": "ワクワクワクっていう時間が", "baseline_zh": "這是令人興奮的時刻。",
     "ref": "那段興奮期待的時間", "issue": ["ok"], "stt_uncertain": False},
    {"id": "L18", "ja": "あったよね", "baseline_zh": "是的，我們有過這樣的經歷。",
     "ref": "有過對吧", "issue": ["padding"], "stt_uncertain": False},
    {"id": "L19", "ja": "こっちもそうだけど多分", "baseline_zh": "這裡也是如此，但也許是這樣。",
     "ref": "我這邊也是，不過大概", "issue": ["ok"], "stt_uncertain": False},
    {"id": "L20", "ja": "リスナーさん的にも誰とコラブするんだろうって",
     "baseline_zh": "從聽眾的角度來看，他們也很想知道與誰合作。",
     "ref": "對聽眾來說也會想「是要跟誰合作呢」", "issue": ["ok"], "stt_uncertain": False},
    {"id": "L21", "ja": "綿名は", "baseline_zh": "棉名是棉花的名字。",
     "ref": "綿芽是", "issue": ["name", "padding"], "stt_uncertain": True, "ja_likely": "わためは"},
    {"id": "L22", "ja": "はあちゃまの予定だったんだけどね",
     "baseline_zh": "雖然我本來打算讓哈阿姐姐來，但是，不管怎麼說，我還是很高興。",
     "ref": "本來預定是跟はあちゃま（赤井心）的啦", "issue": ["name", "padding"], "stt_uncertain": False},

    # ---- Chat: ARK stream memories ----
    {"id": "L23", "ja": "あの0時にちょうどアークだったかなアーク配信をソロでやってて",
     "baseline_zh": "在那個0點的時候，或許正好是Arc的時刻，我獨自做Arc的配信，做Ark配信。",
     "ref": "那個，0點的時候我剛好在…是ARK吧，一個人在開ARK直播", "issue": ["duplicate"], "stt_uncertain": False},
    {"id": "L24", "ja": "そこでゼロ時過ぎたから", "baseline_zh": "所以零時過去了，因為零時已經過去。",
     "ref": "那時過了0點，所以", "issue": ["duplicate"], "stt_uncertain": False},
    {"id": "L25", "ja": "フブちゃんとまつりちゃんが声をかけてくれて",
     "baseline_zh": "胡佛和馬斯特里給我打了個電話，說我來了。",
     "ref": "吹雪和祭來找我搭話", "issue": ["name", "padding"], "stt_uncertain": False},
    {"id": "L26", "ja": "突発で", "baseline_zh": "突然和突然地發生。",
     "ref": "臨時起意地", "issue": ["fragment", "duplicate"], "stt_uncertain": False},
    {"id": "L27", "ja": "ちょっと冒険行こうっていう", "baseline_zh": "就像是去冒險一樣。",
     "ref": "說要不要去冒險一下", "issue": ["mistrans"], "stt_uncertain": False},
    {"id": "L28", "ja": "流れになりまして", "baseline_zh": "請允許我繼續發言，我已經準備好了。",
     "ref": "就變成了這樣的發展", "issue": ["mistrans", "padding"], "stt_uncertain": False},
    {"id": "L29", "ja": "だから初めてわあ", "baseline_zh": "所以這是第一次啊啊啊呀啊啊哦啊啊噢啊啊喔啊啊",
     "ref": "所以第一次，哇", "issue": ["loop"], "stt_uncertain": False},
    {"id": "L30", "ja": "ホグちゃんとまつりちゃん", "baseline_zh": "霍格和馬修莉。",
     "ref": "吹雪和祭", "issue": ["name"], "stt_uncertain": True, "ja_likely": "フブちゃんとまつりちゃん"},
    {"id": "L31", "ja": "なんだけどあなた", "baseline_zh": "但是，你卻是這樣的，你是這麼的可愛。",
     "ref": "不過啊，那個", "issue": ["padding"], "stt_uncertain": True, "ja_likely": "なんだけどあの"},
    {"id": "L32", "ja": "ハンジャマ", "baseline_zh": "漢賈馬（Hanjama）",
     "ref": "はあちゃま（赤井心）", "issue": ["name"], "stt_uncertain": True, "ja_likely": "はあちゃま"},
    {"id": "L33", "ja": "みんな一騎生", "baseline_zh": "所有人都一騎生。",
     "ref": "大家都是一期生", "issue": ["mistrans"], "stt_uncertain": True, "ja_likely": "みんな一期生"},
    {"id": "L34", "ja": "そうだったでもめっちゃ緊張して何もしゃべれなかったんだよ",
     "baseline_zh": "是的，但我太緊張了，什麼都說不出來。",
     "ref": "對啊，不過我超緊張，什麼都說不出來", "issue": ["ok"], "stt_uncertain": False},
    {"id": "L35", "ja": "堂々持ってイカだ乗ってただけ", "baseline_zh": "我只不過是自豪地拿著它，騎著章魚而已。",
     "ref": "只是抬頭挺胸地坐在木筏上而已", "issue": ["mistrans"], "stt_uncertain": True,
     "ja_likely": "堂々持ってイカダ乗ってただけ"},
    {"id": "L36", "ja": "何をしゃべれなかった緊張しちゃって", "baseline_zh": "我沒辦法說什麼，因為我太緊張了。",
     "ref": "什麼都說不出來，太緊張了", "issue": ["ok"], "stt_uncertain": False},
    {"id": "L37", "ja": "吹雪先輩と松井先輩だぞ", "baseline_zh": "是吹雪先生和松井先生",
     "ref": "是吹雪前輩和祭前輩耶", "issue": ["name", "mistrans"], "stt_uncertain": True,
     "ja_likely": "吹雪先輩とまつり先輩だぞ"},
    {"id": "L38", "ja": "何も準備できてない", "baseline_zh": "沒有準備任何東西。",
     "ref": "什麼都沒準備好", "issue": ["ok"], "stt_uncertain": False},
    {"id": "L39", "ja": "堂々持ってこのイカダ乗ってくれればいいから",
     "baseline_zh": "只要你們勇敢地拿著這條魷魚，騎在這條烏賊身上，就可以了。",
     "ref": "只要抬頭挺胸坐上這艘木筏就好了", "issue": ["mistrans", "duplicate"], "stt_uncertain": False},
    {"id": "L40", "ja": "分かりました", "baseline_zh": "好了，我明白了。",
     "ref": "我知道了", "issue": ["ok"], "stt_uncertain": False},
    {"id": "L41", "ja": "本当に持ってることしかしてないけど",
     "baseline_zh": "我只真正擁有我所擁有的東西，但我卻只擁有自己所擁有的一切。",
     "ref": "雖然真的就只是拿著而已", "issue": ["mistrans", "duplicate"], "stt_uncertain": False},
    {"id": "L42", "ja": "大丈夫なんでしょうか", "baseline_zh": "請問你們沒事吧？",
     "ref": "這樣沒問題嗎", "issue": ["ok"], "stt_uncertain": False},
    {"id": "L43", "ja": "堂々餅だった", "baseline_zh": "曾經是堂堂正正的蛋糕。",
     "ref": "就只是抬頭挺胸拿著", "issue": ["mistrans"], "stt_uncertain": True, "ja_likely": "堂々持ちだった"},
    {"id": "L44", "ja": "懐かしいな", "baseline_zh": "真的很想念你們的時光。",
     "ref": "好懷念啊", "issue": ["padding"], "stt_uncertain": False},
    {"id": "L45", "ja": "何やってたんだっけななんか堂々おとりにしてなんかしようとしてたんだよね",
     "baseline_zh": "是的，你正在做什麼呢？ 你正在試圖做些什麼，而不管你在幹什麼。",
     "ref": "當時在做什麼來著…好像是大大方方地當誘餌，想做些什麼吧", "issue": ["mistrans", "duplicate"],
     "stt_uncertain": False},
    {"id": "L46", "ja": "バリオニクスなっけ", "baseline_zh": "巴里奧尼克不是重子嗎？",
     "ref": "是重爪龍（Baryonyx）來著？", "issue": ["mistrans"], "stt_uncertain": True,
     "ja_likely": "バリオニクスだっけ"},
    {"id": "L47", "ja": "なんかテーマしようとしてたんだっけな", "baseline_zh": "我只是想要找個主題。",
     "ref": "好像是想要馴服牠來著", "issue": ["mistrans"], "stt_uncertain": True,
     "ja_likely": "なんかテイムしようとしてたんだっけな"},
    {"id": "L48", "ja": "そうや昔は吹雪先輩だったしハート先輩だったし",
     "baseline_zh": "過去有吹雪先生、心先生和吹雪老師。",
     "ref": "對耶，以前是吹雪前輩，還有はあと（心）前輩", "issue": ["name", "padding"], "stt_uncertain": False},
    {"id": "L49", "ja": "まつり先輩だった", "baseline_zh": "曾經是大學時代的同學，是大會的老師。",
     "ref": "還有祭前輩", "issue": ["name", "padding", "mistrans"], "stt_uncertain": False},
    {"id": "L50", "ja": "懐かしい今その音があるかな", "baseline_zh": "想念現在是否有那種聲音的聲音嗎?",
     "ref": "好懷念，現在還有那個聲音嗎", "issue": ["duplicate"], "stt_uncertain": False},
    {"id": "L51", "ja": "残ってたら逃げるかも", "baseline_zh": "如果他們留下來，他們可能會逃跑。",
     "ref": "如果還留著的話，說不定會逃走", "issue": ["ok"], "stt_uncertain": False},
    {"id": "L52", "ja": "懐かしいね", "baseline_zh": "很想念, 很難忘, 太想念了。",
     "ref": "好懷念呢", "issue": ["duplicate", "padding"], "stt_uncertain": False},
    {"id": "L53", "ja": "綿がおとりだった説", "baseline_zh": "據說棉花是它們的食物。",
     "ref": "綿芽其實是誘餌的說法", "issue": ["name", "mistrans"], "stt_uncertain": True,
     "ja_likely": "わためがおとりだった説"},
    {"id": "L54", "ja": "でもなんか転やわんやになったような気がする",
     "baseline_zh": "但我覺得自己好像已經變得不那麼活躍了。",
     "ref": "不過總覺得好像變得手忙腳亂的", "issue": ["mistrans"], "stt_uncertain": True,
     "ja_likely": "でもなんかてんやわんやになったような気がする"},
    {"id": "L55", "ja": "衝撃の事実", "baseline_zh": "這是一個令人震驚的事實。",
     "ref": "衝擊的事實", "issue": ["ok"], "stt_uncertain": False},
    {"id": "L56", "ja": "どうなるんだ", "baseline_zh": "會發生什麼?",
     "ref": "會變成怎樣呢", "issue": ["ok"], "stt_uncertain": False},

    # ---- Chat: worried about a junior ----
    {"id": "L57", "ja": "でも京子ちゃん", "baseline_zh": "但京子姐姐，我很喜歡你。",
     "ref": "不過京子醬", "issue": ["padding"], "stt_uncertain": False},
    {"id": "L58", "ja": "心配だね", "baseline_zh": "你很擔心，你很擔憂。",
     "ref": "真讓人擔心呢", "issue": ["duplicate", "mistrans"], "stt_uncertain": False},
    {"id": "L59", "ja": "心配なっちゃうななんか", "baseline_zh": "我擔心我會擔心什麼，我擔心會擔憂什麼。",
     "ref": "總覺得會擔心起來呢", "issue": ["duplicate"], "stt_uncertain": False},
    {"id": "L60", "ja": "毎日2回行動", "baseline_zh": "每天行動兩次，每次行動20分鐘。",
     "ref": "每天行動兩次", "issue": ["padding"], "stt_uncertain": False},
    {"id": "L61", "ja": "そんな大きい声出して大丈夫", "baseline_zh": "發出那麼大聲的聲音沒關係。",
     "ref": "發出那麼大的聲音沒問題嗎", "issue": ["mistrans"], "stt_uncertain": False},
    {"id": "L62", "ja": "全部やっちゃわない?", "baseline_zh": "為什麼不全部完成呢?",
     "ref": "要不要乾脆全部做掉？", "issue": ["ok"], "stt_uncertain": False},
    {"id": "L63", "ja": "大体みんな喉やっちゃうから", "baseline_zh": "大多數人都會因為喉嚨發癢而放棄。",
     "ref": "因為大家大多會把喉嚨搞壞", "issue": ["mistrans"], "stt_uncertain": False},
    {"id": "L64", "ja": "心配だね", "baseline_zh": "你很擔心，你很擔憂。",
     "ref": "真讓人擔心呢", "issue": ["duplicate", "mistrans"], "stt_uncertain": False},
    {"id": "L65", "ja": "無理はしないでほしいけどね", "baseline_zh": "不過我希望你們不要強迫我。",
     "ref": "不過希望你不要勉強自己", "issue": ["mistrans"], "stt_uncertain": False},
    {"id": "L66", "ja": "ファラちゃんになれるかどうかね", "baseline_zh": "我不知道她是否能成為法拉。",
     "ref": "能不能變成…醬那樣呢", "issue": ["ok"], "stt_uncertain": True},
    {"id": "L67", "ja": "すごいな", "baseline_zh": "真是太棒了，這麼多年來，我從來沒有見過這樣的東西。",
     "ref": "好厲害啊", "issue": ["padding"], "stt_uncertain": False},
    {"id": "L68", "ja": "フグちゃんがそこカエル化してたの?カエルか?",
     "baseline_zh": "福格在那裡變成青蛙了嗎? 青蛙嗎?",
     "ref": "吹雪在那邊變成青蛙了？青蛙嗎？", "issue": ["name"], "stt_uncertain": True,
     "ja_likely": "フブちゃんがそこカエル化してたの?カエルか?"},
    {"id": "L69", "ja": "なんでなんで", "baseline_zh": "為什麼，為什麼？",
     "ref": "為什麼為什麼", "issue": ["ok"], "stt_uncertain": False},
]

if __name__ == "__main__":
    from collections import Counter
    print(f"Total entries: {len(LIVE_DATASET)}")
    print(f"stt_uncertain: {sum(d['stt_uncertain'] for d in LIVE_DATASET)}")
    print(Counter(i for d in LIVE_DATASET for i in d["issue"]))
