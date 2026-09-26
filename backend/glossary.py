"""Name/term glossary applied to Japanese text right before translation.

MADLAD transliterates member names phonetically into random Chinese names
(フブちゃん -> 胡佛, まつりちゃん -> 馬斯特里). Replacing them in the Japanese input with the fixed Chinese (or English) form
works because MADLAD copies Han characters and Latin text through as-is.

MEMBERS and TERMS only hold correctly spelled forms. STT misrecognitions go in
STT_FIXES below, and only ones seen repeatedly in real logs whose wrong form
is not an ordinary word in that position (one-off errors like ホグちゃん,
ハンジャマ stay out: mapping them would start rewriting unrelated words).

Display names were picked by translating each one in fixed test sentences and
keeping the form MADLAD leaves intact: kanji that mean something get
translated (天音彼方 -> "天音那邊", 癒月巧可 -> "治療月巧可", 綿芽 -> "棉花芽"),
so those members use a shorter form or a Latin name instead (天音, 巧可,
Towa). Check a new display name the same way before adding it. When the
wanted display name gets translated but another form doesn't, feed MADLAD
the stable form and swap it back with OUTPUT_FIXES (角卷 -> 綿芽).

Edit freely: each member entry is (forms, zh). A form ending in "~" is a
base that is also an ordinary Japanese word (まつり = festival, そら = sky),
so it is only replaced when an honorific follows (まつりちゃん, まつり先輩).
"""
import re

# Honorific that may follow a name -> what it becomes after the name.
# 先輩/先生 stay Japanese: as 前輩/老師 MADLAD reads "吹雪前輩" as "吹雪的前輩".
HONORIFICS = {"ちゃん": "", "さん": "", "くん": "", "様": "", "さま": "", "先輩": "先輩", "先生": "先生"}

# Kotoba often writes a name in katakana even when the member's name is
# hiragana (ワタメ, ボタン, コヨ in live logs), so common names also have their
# katakana spelling. Katakana forms that are also ordinary words (チョコ,
# コロネ, アクア, ソラ...) only match before an honorific, like other "~" forms.
MEMBERS = [
    # ---- JP 0th gen ----
    (["ときのそら", "そら~", "ソラ~"], "時乃空"),
    (["ロボ子"], "蘿蔔子"),
    (["さくらみこ", "みこち", "ミコち", "みこ~", "ミコ~"], "櫻巫女"),
    (["星街すいせい", "すいせい~", "スイセイ~", "すいちゃん", "スイちゃん"], "星街彗星"),
    (["AZKi", "あずき~"], "AZKi"),
    # ---- JP 1st gen ----
    (["夜空メル", "メル~"], "夜空梅露"),
    (["アキ・ローゼンタール", "アキロゼ", "アキ~"], "亞綺"),
    (["はあちゃま"], "哈洽馬"),
    (["赤井はあと", "はあと~", "ハート~"], "赤井心"),
    (["白上フブキ", "フブキ", "白上", "フブ~"], "吹雪"),
    (["夏色まつり", "まつり~", "マツリ~"], "夏色祭"),
    # ---- JP 2nd gen ----
    (["湊あくあ", "あくたん", "あくあ", "アクア~"], "阿庫婭"),
    (["紫咲シオン", "シオン"], "紫咲詩音"),
    (["百鬼あやめ", "あやめ~", "アヤメ~"], "百鬼"),
    (["お嬢"], "大小姐"),
    (["癒月ちょこ", "ちょこ~", "チョコ~"], "巧可"),
    (["大空スバル", "スバル"], "大空昴"),
    # ---- JP GAMERS ----
    (["大神ミオ", "ミオしゃ", "ミオシャ", "ミオ"], "大神澪"),
    (["猫又おかゆ", "おかゆん", "おかゆ~", "オカユ~"], "貓又小粥"),
    (["戌神ころね", "ころさん", "ころね", "コロさん", "コロネ~"], "戌神沁音"),
    # ---- JP 3rd gen ----
    (["兎田ぺこら", "ぺこーら", "ぺこら", "ぺこちゃん", "ペコーラ", "ペコラ", "ペコちゃん"], "佩克拉"),
    (["不知火フレア", "フレア~", "フーたん"], "不知火芙蕾雅"),
    (["白銀ノエル", "ノエル"], "白銀諾艾爾"),
    (["団長"], "團長"),
    (["宝鐘マリン", "マリン"], "瑪琳"),
    (["潤羽るしあ", "るしあ"], "潤羽露西婭"),
    # ---- JP 4th gen ----
    (["天音かなた", "かなたん", "かなた~", "カナタ~"], "天音"),
    (["桐生ココ", "ココ会長", "ココ~"], "桐生可可"),
    (["角巻わため", "わためぇ", "わため", "ワタメ"], "角卷"),  # shown as 綿芽, see OUTPUT_FIXES
    (["常闇トワ", "トワち", "トワチ", "トワ~", "とわ~"], "Towa"),
    (["姫森ルーナ", "ルーナ"], "姬森璐娜"),
    # ---- JP 5th gen ----
    (["雪花ラミィ", "ラミィ"], "雪花菈米"),
    (["桃鈴ねね", "ねねち", "ネネち", "ねね~", "ネネ~"], "桃鈴音音"),
    (["獅白ぼたん", "ししろん", "ぼたん~", "ボタン~"], "獅白牡丹"),
    (["尾丸ポルカ", "ポルカ"], "尾丸波爾卡"),
    # ---- JP holoX ----
    (["ラプラス・ダークネス", "ラプラス", "ラプ~"], "拉普拉斯"),
    (["ルイ姉"], "琉衣姐"),
    (["鷹嶺ルイ", "ルイ~"], "鷹嶺琉衣"),
    (["博衣こより", "こより", "コヨリ", "こよ~", "コヨ~"], "博衣小夜璃"),
    (["沙花叉クロヱ", "沙花叉", "クロヱ", "クロエ~"], "沙花叉克蘿耶"),
    (["風真いろは", "いろは~", "イロハ~"], "風真伊呂波"),
    # ---- JP ReGLOSS ----
    # Short/common readings use ~ so they are only replaced before an honorific.
    (["火威青", "青~", "あお~"], "Ao"),
    (["音乃瀬奏", "奏~", "かなで~"], "Kanade"),
    (["一条莉々華", "莉々華"], "一條莉莉華"),
    (["儒烏風亭らでん", "らでん"], "Raden"),
    (["轟はじめ", "はじめ~", "番長"], "轟一"),
    # ---- JP FLOW GLOW ----
    (["響咲リオナ", "リオナ"], "Riona"),
    (["虎金妃笑虎", "ニコ~"], "Niko"),
    (["水宮枢", "すう~", "スウ~"], "Su"),
    (["輪堂千速", "ちはや~", "チハヤ~"], "Chihaya"),
    (["綺々羅々ヴィヴィ", "ヴィヴィ"], "Vivi"),
    # ---- JP ASOBI MAWARI TAI ----
    (["百灯キョーコ", "キョーコ~"], "Kyoko"),
    (["熱千めら", "めら~"], "Mela"),
    (["鈴鳴つづり", "つづり~"], "Tsuzuri"),
    (["宙科そぴあ", "そぴあ~"], "Sopia"),
    # ---- holoAN ----
    (["井月みちる", "みちる~"], "Michiru"),
    (["花園さやか", "さやか~"], "Sayaka"),
    (["風白ゆき", "ゆき~"], "Yuki"),
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
    # hololive / group names
    "ホロライブ": "hololive",
    "ホロメン": "holo成員",
    "リグロス": "ReGLOSS",
    "フロウグロウ": "FLOW GLOW",
    "ホロアナ": "holoAN",
    "アソビ★まわり隊": "ASOBI★MAWARI-TAI!",
    "アソビまわり隊": "ASOBI★MAWARI-TAI!",

    # stream / channel vocabulary -- keep this list conservative.
    "雑談配信": "閒聊直播",
    "ゲリラ配信": "突發直播",
    "緊急配信": "緊急直播",
    "朝活配信": "晨間直播",
    "耐久配信": "耐久直播",
    "生配信": "直播",
    "配信者": "實況主",
    "配信": "直播",
    "雑談": "閒聊",
    "プレミア公開": "首播",
    "切り抜き": "精華剪輯",
    "アーカイブ": "直播存檔",
    "タイムスタンプ": "時間戳",
    "概要欄": "說明欄",
    "コメント欄": "留言區",
    "チャット欄": "聊天室",
    "チャンネル登録": "訂閱頻道",
    "登録者数": "訂閱人數",
    "収益化": "營利化",
    "モデレーター": "管理員",
    "ネタバレ": "劇透",

    # membership / support
    "メンシ": "頻道會員",
    "メン限": "會員限定",
    "スパチャ": "SC",
    "同接": "同時觀看人數",

    # music / content
    "歌ってみた": "翻唱",
    "歌みた": "翻唱",
    "オリジナル曲": "原創曲",
    "オリ曲": "原創曲",
    "カバー曲": "翻唱曲",

    # roles / common hololive-specific terms
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
    # A nickname ending in ち (みこち, トワち) must not eat the ち of ちゃん:
    # みこちゃん is みこ + ちゃん, not みこち + "ゃん".
    alts = "|".join(re.escape(f) + ("(?!ゃ)" if f.endswith("ち") else "")
                    for f in sorted(zh_by_form, key=len, reverse=True))
    hons = "|".join(re.escape(h) for h in sorted(HONORIFICS, key=len, reverse=True))
    name_re = re.compile(f"({alts})({hons})?")
    term_re = re.compile("|".join(re.escape(t) for t in sorted(TERMS, key=len, reverse=True)))
    return zh_by_form, needs_honorific, name_re, term_re


_ZH_BY_FORM, _NEEDS_HONORIFIC, _NAME_RE, _TERM_RE = _build()


# A katakana-only name inside a longer katakana word is part of that word, not
# the name (ルーナ in ルーナイト, the fan name).
_KATAKANA_FORM_RE = re.compile(r"[ァ-ヶー・]+")
_KATAKANA_CHAR_RE = re.compile(r"[ァ-ヶー]")


def _replace_name(m):
    form, hon = m.group(1), m.group(2)
    if hon is None and form in _NEEDS_HONORIFIC:
        return m.group(0)
    if _KATAKANA_FORM_RE.fullmatch(form):
        before = m.string[m.start() - 1:m.start()]
        after = "" if hon else m.string[m.end(1):m.end(1) + 1]
        if _KATAKANA_CHAR_RE.fullmatch(before or " ") or _KATAKANA_CHAR_RE.fullmatch(after or " "):
            return m.group(0)
    return _ZH_BY_FORM[form] + (HONORIFICS[hon] if hon else "")


# "N期生" (Nth generation) -> "N期成員": left alone MADLAD reads 4期生 as
# "四年級的學生" (4th-grade student).
_GENERATION_RE = re.compile(r"([0-9０-９一二三四五六七八九]+)期生")


# Recurring Kotoba misrecognitions -> the intended word, applied before the
# name lookup so a corrected name then gets its display name. Each entry is
# (regex, replacement) with the evidence next to it; the lookahead keeps
# ordinary uses (また目の前, また目が覚めた) untouched.
STT_FIXES = [
    (r"また目(?![のがをにでも覚])", "わため"),  # 2026-09-26 live: また目何の王様? / また目は / また目将軍
    (r"渡目|綿目", "わため"),  # replays of 09-26 recordings (not words)
    (r"渡辺", "わため"),  # 2026-09-26 live: すまん!渡辺! / 渡辺将軍; a real surname, remove if it bites
]
_STT_FIX_RES = [(re.compile(p), r) for p, r in STT_FIXES]


def fix_stt(text: str) -> str:
    for pattern, replacement in _STT_FIX_RES:
        text = pattern.sub(replacement, text)
    return text


# Chinese output -> intended display name, applied after OpenCC. わため goes
# into MADLAD as 角卷 and is shown as 綿芽: fed 綿芽 directly, MADLAD read it
# as "cotton sprout" in 6 of 20 test sentences (わためが来た -> "棉花已經長出芽
# 來了"), 角卷 came through in 20 of 20. OpenCC sometimes writes it 角捲.
OUTPUT_FIXES = {"角卷": "綿芽", "角捲": "綿芽"}


def fix_output(text: str) -> str:
    for wrong, right in OUTPUT_FIXES.items():
        text = text.replace(wrong, right)
    return text


def apply(text: str, replace_names: bool = True) -> str:
    """Pre-process Japanese text for the translator. replace_names=False
    keeps member names as spoken, for Sakura, which gets them as glossary
    entries instead (name_entries), see translator.translate."""
    text = fix_stt(text)
    if replace_names:
        text = _NAME_RE.sub(_replace_name, text)
    text = _GENERATION_RE.sub(lambda m: m.group(1) + "期成員", text)
    return _TERM_RE.sub(lambda m: TERMS[m.group(0)], text)


def name_entries(text: str):
    """(name as written in text, display name) for each member name found,
    by the same matching rules as apply. For Sakura's glossary prompt: fed the
    Chinese name inside the Japanese text, Sakura translated it as a word
    (白上フブキ -> "暴風雪", 角卷 -> "捲成一團"); given as a glossary entry
    with the Japanese left as spoken, 240 of 259 test sentences came out with
    the right name vs 203 (benchmark/test_sakura_names.py). Display names go
    through OUTPUT_FIXES, so わため is listed as 綿芽 directly."""
    entries = []
    for m in _NAME_RE.finditer(fix_stt(text)):
        if _replace_name(m) != m.group(0):
            entry = (m.group(0), fix_output(_ZH_BY_FORM[m.group(1)]))
            if entry not in entries:
                entries.append(entry)
    return entries


# Whole utterances that get a fixed translation instead of going to MADLAD.
# Alone, short interjections and reactions give MADLAD nothing to translate,
# so it may invent a sentence. Only an exact whole-utterance match (ignoring
# punctuation) uses this; anything longer still goes to MADLAD.
#
# Keep this table stricter than TERMS: only add utterances whose standalone
# meaning is stable. やばい stays out (praise or alarm depending on tone).
# 大丈夫, さすがに, で, なんか and 逆に are context-dependent too, but alone
# MADLAD turned them into invented sentences in live logs (さすがに -> "事實上，
# 這一切都是為了你。", で -> "並且在 的情況下。"), so they get a neutral
# rendering that is at worst slightly off rather than made up.
FIXED_UTTERANCES = {
    # interjections / fillers
    "ああ": "啊", "あー": "啊", "あぁ": "啊",
    "うわ": "哇", "うわー": "哇", "うわぁ": "哇", "わあ": "哇", "わー": "哇", "わぁ": "哇",
    "え": "欸", "えっ": "欸", "えー": "欸", "えぇ": "欸",
    "おお": "喔", "おー": "喔", "おっ": "喔", "おぉ": "喔",
    "へえ": "喔", "へー": "喔", "ほう": "喔", "ふん": "哼",
    "うん": "嗯", "うんうん": "嗯嗯", "ううん": "不", "うーん": "嗯……",
    "はい": "好", "まあ": "嗯……", "あの": "那個", "で": "然後", "なんか": "那個……",
    "えっと": "呃", "えーと": "呃", "えーっと": "呃", "えっとですね": "呃……", "あれ": "咦", "ん": "嗯",

    # thanks / apologies
    "ありがとう": "謝謝", "ありがとうね": "謝謝", "ありがとうございます": "謝謝",
    "ありがとうございました": "謝謝",
    "ごめん": "抱歉", "ごめんね": "抱歉", "ごめんなさい": "對不起",
    # すみません can apologize, get attention or half-thank; 不好意思 fits all three
    "すみません": "不好意思", "すいません": "不好意思",

    # short reactions with stable meaning
    "すごい": "好厲害", "すごいな": "好厲害", "すごいね": "好厲害", "本当にすごい": "真的好厲害",
    "懐かしい": "好懷念", "懐かしいな": "好懷念啊", "懐かしいね": "好懷念呢",
    "かわいい": "好可愛", "可愛い": "好可愛",
    "恥ずかしい": "好害羞", "寂しい": "好寂寞", "寂しいよ": "好寂寞喔",
    "心配だね": "真讓人擔心", "楽しみ": "好期待", "楽しみだね": "好期待呢", "嬉しい": "好開心", "楽しい": "好開心", "面白い": "好有趣",
    "さすが": "不愧是", "さすがに": "果然", "大丈夫": "沒事",
    "なるほど": "原來如此", "そうだね": "對啊", "そうだよね": "對吧", "そうそう": "對對",
    "本当": "真的", "本当に": "真的", "ほんと": "真的",
    "分かりました": "我知道了", "わかりました": "我知道了", "了解": "了解",

    # greetings / fixed social phrases
    "おめでとう": "恭喜", "お疲れ様": "辛苦了", "おつかれ": "辛苦了", "おつ": "辛苦了",
    "よろしく": "請多指教", "よろしくお願いします": "請多指教",
    "おはよう": "早安", "こんにちは": "你好", "こんばんは": "晚上好", "おやすみ": "晚安",
    "ただいま": "我回來了", "おかえり": "歡迎回來", "いらっしゃい": "歡迎",

    # other context-stable short utterances
    "やった": "太好了", "よし": "好", "ストップ": "停",
    "そして": "然後", "さらに": "而且", "確かに": "確實", "なんでなんで": "為什麼為什麼", "逆に": "反而",
    "待って": "等一下", "ちょっと待って": "等一下",
    "やめて": "不要", "だめ": "不行", "ダメ": "不行",
    "もちろん": "當然",
    "頑張って": "加油", "がんばって": "加油",
    "おいしい": "好吃", "美味しい": "好吃",
    "怖い": "好可怕", "眠い": "好睏", "暑い": "好熱", "寒い": "好冷",
    "最高": "太棒了", "ナイス": "Nice",
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
