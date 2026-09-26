"""Name/term glossary applied to Japanese text right before translation.

MADLAD transliterates member names phonetically into random Chinese names
(フブちゃん -> 胡佛, まつりちゃん -> 馬斯特里). Replacing them in the Japanese input with the fixed Chinese (or English) form
works because MADLAD copies Han characters and Latin text through as-is.

Only correctly spelled forms belong here. STT misrecognitions (ホグちゃん,
ハンジャマ) are an STT problem; mapping them here would start rewriting
unrelated words.

Display names were picked by translating each one in fixed test sentences and
keeping the form MADLAD leaves intact: kanji that mean something get
translated (天音彼方 -> "天音那邊", 癒月巧可 -> "治療月巧可", 綿芽 -> "棉花發芽"),
so those members use a shorter form or a Latin name instead (天音, 巧可,
角卷, Towa). Check a new display name the same way before adding it.

Edit freely: each member entry is (forms, zh). A form ending in "~" is a
base that is also an ordinary Japanese word (まつり = festival, そら = sky),
so it is only replaced when an honorific follows (まつりちゃん, まつり先輩).
"""
import re

# Honorific that may follow a name -> what it becomes after the name.
# 先輩/先生 stay Japanese: as 前輩/老師 MADLAD reads "吹雪前輩" as "吹雪的前輩".
HONORIFICS = {"ちゃん": "", "さん": "", "くん": "", "様": "", "さま": "", "先輩": "先輩", "先生": "先生"}

MEMBERS = [
    # ---- JP 0th gen ----
    (["ときのそら", "そら~"], "時乃空"),
    (["ロボ子"], "蘿蔔子"),
    (["さくらみこ", "みこち", "みこ~"], "櫻巫女"),
    (["星街すいせい", "すいせい~", "すいちゃん"], "星街彗星"),
    (["AZKi", "あずき~"], "AZKi"),
    # ---- JP 1st gen ----
    (["夜空メル", "メル~"], "夜空梅露"),
    (["アキ・ローゼンタール", "アキロゼ", "アキ~"], "亞綺"),
    (["はあちゃま"], "哈洽馬"),
    (["赤井はあと", "はあと~", "ハート~"], "赤井心"),
    (["白上フブキ", "フブキ", "白上", "フブ~"], "吹雪"),
    (["夏色まつり", "まつり~"], "夏色祭"),
    # ---- JP 2nd gen ----
    (["湊あくあ", "あくたん", "あくあ"], "阿庫婭"),
    (["紫咲シオン", "シオン"], "紫咲詩音"),
    (["百鬼あやめ", "あやめ~"], "百鬼"),
    (["お嬢"], "大小姐"),
    (["癒月ちょこ", "ちょこ~"], "巧可"),
    (["大空スバル", "スバル"], "大空昴"),
    # ---- JP GAMERS ----
    (["大神ミオ", "ミオしゃ", "ミオシャ", "ミオ"], "大神澪"),
    (["猫又おかゆ", "おかゆん", "おかゆ~"], "貓又小粥"),
    (["戌神ころね", "ころさん", "ころね"], "戌神沁音"),
    # ---- JP 3rd gen ----
    (["兎田ぺこら", "ぺこーら", "ぺこら", "ぺこちゃん"], "佩克拉"),
    (["不知火フレア", "フレア~", "フーたん"], "不知火芙蕾雅"),
    (["白銀ノエル", "ノエル"], "白銀諾艾爾"),
    (["団長"], "團長"),
    (["宝鐘マリン", "マリン"], "瑪琳"),
    (["潤羽るしあ", "るしあ"], "潤羽露西婭"),
    # ---- JP 4th gen ----
    (["天音かなた", "かなたん", "かなた~"], "天音"),
    (["桐生ココ", "ココ会長", "ココ~"], "桐生可可"),
    (["角巻わため", "わためぇ", "わため", "ワタメ"], "角卷"),
    (["常闇トワ", "トワち", "トワチ", "トワ~", "とわ~"], "Towa"),
    (["姫森ルーナ", "ルーナ"], "姬森璐娜"),
    # ---- JP 5th gen ----
    (["雪花ラミィ", "ラミィ"], "雪花菈米"),
    (["桃鈴ねね", "ねねち", "ねね~"], "桃鈴音音"),
    (["獅白ぼたん", "ししろん", "ぼたん~"], "獅白牡丹"),
    (["尾丸ポルカ", "ポルカ"], "尾丸波爾卡"),
    # ---- JP holoX ----
    (["ラプラス・ダークネス", "ラプラス", "ラプ~"], "拉普拉斯"),
    (["ルイ姉"], "琉衣姐"),
    (["鷹嶺ルイ", "ルイ~"], "鷹嶺琉衣"),
    (["博衣こより", "こより", "こよ~"], "博衣小夜璃"),
    (["沙花叉クロヱ", "沙花叉", "クロヱ", "クロエ~"], "沙花叉克蘿耶"),
    (["風真いろは", "いろは~"], "風真伊呂波"),
    # ---- JP ReGLOSS / FLOW GLOW (kanji names pass through MADLAD as-is) ----
    (["一条莉々華", "莉々華"], "一條莉莉華"),
    (["轟はじめ", "はじめ~", "番長"], "轟一"),
    (["綺々羅々ヴィヴィ", "ヴィヴィ"], "Vivi"),
    # ---- ID ----
    (["アユンダ・リス", "リス~"], "Risu"),
    (["ムーナ"], "Moona"),
    (["アイラニ・イオフィフティーン", "イオフィ"], "Iofi"),
    (["クレイジー・オリー", "オリー"], "Ollie"),
    (["アーニャ"], "Anya"),
    (["レイネ"], "Reine"),
    (["ゼータ"], "Zeta"),
    (["カエラ"], "Kaela"),
    (["こぼ・かなえる", "こぼ~", "コボ~"], "Kobo"),
    # ---- EN ----
    (["森カリオペ", "カリオペ", "カリ~"], "Calli"),
    (["小鳥遊キアラ", "キアラ"], "Kiara"),
    (["一伊那尓栖", "イナニス", "イナ~"], "Ina"),
    (["がうる・ぐら", "ぐら~", "グラ~"], "Gura"),
    (["ワトソン・アメリア", "アメリア", "アメ~"], "Amelia"),
    (["IRyS", "アイリス~"], "IRyS"),
    (["セレス・ファウナ", "ファウナ"], "Fauna"),
    (["オーロ・クロニー", "クロニー"], "Kronii"),
    (["七詩ムメイ", "ムメイ"], "Mumei"),
    (["ハコス・ベールズ", "ベールズ"], "Baelz"),
    (["シオリ・ノヴェラ", "シオリ~"], "Shiori"),
    (["古石ビジュー", "ビジュー"], "Bijou"),
    (["ネリッサ・レイヴンクロフト", "ネリッサ"], "Nerissa"),
    (["フワモコ"], "FUWAMOCO"),
    (["フワワ"], "Fuwawa"),
    (["モココ"], "Mococo"),
    (["エリザベス・ローズ・ブラッドフレイム", "リズ~"], "Liz"),
    (["ジジ・ムリン", "ジジ~"], "Gigi"),
    (["セシリア・イマーグリーン", "セシリア"], "Cecilia"),
    (["ラオーラ・パンテーラ", "ラオーラ"], "Raora"),
]

# Common stream vocabulary. Only terms that translated better replaced than
# left alone are kept; コラボ->連動, 歌枠->歌回, 凸待ち, 箱推し and 先輩->前輩
# all made the output worse (連動 is itself a Japanese word, 歌回 became
# "唱歌回去"), so MADLAD handles those itself; 箱押し/箱推し too.
TERMS = {
    "ホロライブ": "hololive",
    "ホロメン": "holo成員",
    "生配信": "直播",
    "配信": "直播",
    "切り抜き": "精華剪輯",
    "スパチャ": "SC",
    "メン限": "會員限定",
    "同接": "同時觀看人數",
    "会長": "會長",  # left as-is MADLAD made it "董事會主席"
    "マネちゃん": "經紀人",
    "マネージャー": "經紀人",
    "クソコラ": "惡搞圖",
    "リスナーさん": "聽眾",
    "リスナー": "聽眾",
}


def _build():
    zh_by_form, needs_honorific = {}, set()
    for forms, zh in MEMBERS:
        for form in forms:
            base = form.rstrip("~")
            zh_by_form[base] = zh
            if form.endswith("~"):
                needs_honorific.add(base)
    alts = "|".join(re.escape(f) for f in sorted(zh_by_form, key=len, reverse=True))
    hons = "|".join(re.escape(h) for h in sorted(HONORIFICS, key=len, reverse=True))
    name_re = re.compile(f"({alts})({hons})?")
    term_re = re.compile("|".join(re.escape(t) for t in sorted(TERMS, key=len, reverse=True)))
    return zh_by_form, needs_honorific, name_re, term_re


_ZH_BY_FORM, _NEEDS_HONORIFIC, _NAME_RE, _TERM_RE = _build()


def _replace_name(m):
    form, hon = m.group(1), m.group(2)
    if hon is None and form in _NEEDS_HONORIFIC:
        return m.group(0)
    return _ZH_BY_FORM[form] + (HONORIFICS[hon] if hon else "")


# "N期生" (Nth generation) -> "N期成員": left alone MADLAD reads 4期生 as
# "四年級的學生" (4th-grade student).
_GENERATION_RE = re.compile(r"([0-9０-９一二三四五六七八九]+)期生")


def apply(text: str) -> str:
    text = _NAME_RE.sub(_replace_name, text)
    text = _GENERATION_RE.sub(lambda m: m.group(1) + "期成員", text)
    return _TERM_RE.sub(lambda m: TERMS[m.group(0)], text)


# Whole utterances that get a fixed translation instead of going to MADLAD.
# Alone, short interjections and reactions give MADLAD nothing to translate,
# so it invents a sentence (ああ -> "哦，是的，我很喜歡它。", さすがに -> "事實上，
# 這一切都是為了你。", ありがとうございます -> "感謝您傳送編修。"). Only an exact
# match of the whole utterance (ignoring punctuation) uses this; anything
# longer still goes to MADLAD, so add only phrases whose meaning doesn't
# depend on context (no やばい: praise or alarm depending on tone).
FIXED_UTTERANCES = {
    # interjections / fillers
    "ああ": "啊", "あー": "啊", "あぁ": "啊",
    "うわ": "哇", "うわー": "哇", "うわぁ": "哇", "わあ": "哇", "わー": "哇", "わぁ": "哇",
    "え": "欸", "えっ": "欸", "えー": "欸", "えぇ": "欸",
    "おお": "喔", "おー": "喔", "おっ": "喔", "おぉ": "喔",
    "へえ": "欸", "へー": "欸", "ほう": "喔", "ふん": "哼",
    "うん": "嗯", "うんうん": "嗯嗯", "ううん": "不是", "うーん": "嗯……",
    "はい": "好", "で": "然後", "まあ": "嗯", "あの": "那個", "なんか": "那個……",
    "えっと": "呃", "えーと": "呃", "えーっと": "呃", "あれ": "咦", "ん": "嗯",
    # short reactions
    "ありがとう": "謝謝", "ありがとうね": "謝謝", "ありがとうございます": "謝謝",
    "ありがとうございました": "謝謝",
    "ごめん": "抱歉", "ごめんね": "抱歉", "ごめんなさい": "對不起",
    "すごい": "好厲害", "すごいな": "好厲害", "すごいね": "好厲害", "本当にすごい": "真的好厲害",
    "懐かしい": "好懷念", "懐かしいな": "好懷念啊", "懐かしいね": "好懷念呢",
    "かわいい": "好可愛", "可愛い": "好可愛",
    "恥ずかしい": "好害羞", "寂しい": "好寂寞", "寂しいよ": "好寂寞喔",
    "心配だね": "真讓人擔心", "嬉しい": "好開心", "楽しい": "好開心", "面白い": "好有趣",
    "大丈夫": "沒事", "さすが": "不愧是", "さすがに": "果然",
    "なるほど": "原來如此", "そうだね": "對啊", "そうだよね": "對吧", "そうそう": "對對",
    "本当": "真的", "本当に": "真的", "ほんと": "真的",
    "分かりました": "我知道了", "わかりました": "我知道了", "了解": "了解",
    "おめでとう": "恭喜", "お疲れ様": "辛苦了", "おつかれ": "辛苦了",
    "よろしく": "請多指教", "よろしくお願いします": "請多指教",
    "おはよう": "早安", "こんにちは": "你好", "こんばんは": "晚上好", "おやすみ": "晚安",
    "ただいま": "我回來了", "おかえり": "歡迎回來", "いらっしゃい": "歡迎",
    "やった": "太好了", "よし": "好", "逆に": "反而", "なんでなんで": "為什麼為什麼",
}
_FIXED_STRIP_RE = re.compile(r"[\s、。,.!?！？…~〜]+")


def fixed(text: str):
    """Fixed translation if the whole utterance is in FIXED_UTTERANCES, else
    None. Keeps a trailing ? or ! so "え?" becomes "欸？"."""
    zh = FIXED_UTTERANCES.get(_FIXED_STRIP_RE.sub("", text))
    if zh is None:
        return None
    tail = text.rstrip()[-1:]
    if tail in ("?", "？"):
        return zh + "？"
    if tail in ("!", "！"):
        return zh + "！"
    return zh
