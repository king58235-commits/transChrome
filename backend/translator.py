import importlib.util
import logging
import os
import re
import sys
from collections import namedtuple

TranslationResult = namedtuple("TranslationResult", ["raw", "final"])


def _register_nvidia_dll_dirs():
    # Same fix as transcriber.py's helper of the same name — duplicated rather
    # than imported so this module has no dependency on transcriber.py at all
    # (Whisper STT and translation must stay decoupled). Harmless to run twice
    # if both modules are imported in the same process.
    if sys.platform != "win32":
        return
    spec = importlib.util.find_spec("nvidia")
    if spec is None or not spec.submodule_search_locations:
        return
    dirs = []
    for base in spec.submodule_search_locations:
        for pkg in ("cublas", "cudnn", "cuda_nvrtc", "cuda_runtime"):
            bin_dir = os.path.join(base, pkg, "bin")
            if os.path.isdir(bin_dir):
                dirs.append(bin_dir)
                os.add_dll_directory(bin_dir)
    if dirs:
        # The PATH change is also inherited by sakura.py's llama-server.exe,
        # which loads cudart/cuBLAS from these same pip-installed wheels.
        os.environ["PATH"] = os.pathsep.join(dirs) + os.pathsep + os.environ.get("PATH", "")


_register_nvidia_dll_dirs()

import ctranslate2
import opencc
import sentencepiece as spm

import glossary
import sakura
from config import (
    OPENCC_CONFIG,
    TRANSLATION_BACKEND,
    TRANSLATION_BEAM_SIZE,
    TRANSLATION_COMPUTE_TYPE_CPU,
    TRANSLATION_COMPUTE_TYPE_GPU,
    TRANSLATION_DEVICE,
    TRANSLATION_DROP_REPEATED_CLAUSES,
    TRANSLATION_LENGTH_PENALTY,
    TRANSLATION_MODEL_REPO,
    TRANSLATION_NO_REPEAT_NGRAM_SIZE,
    TRANSLATION_TGT_TOKEN,
)

logger = logging.getLogger("translator")

# "sakura" or "madlad" (legacy), see config.TRANSLATION_BACKEND. A module
# variable so a MADLAD-only benchmark can switch it before load_model().
BACKEND = TRANSLATION_BACKEND

_loaded = False
_translator = None  # MADLAD only
_sp = None  # MADLAD only
_converter = None
_to_simplified = None  # glossary entries for Sakura, which writes Simplified


def _run(translator, sp, text: str) -> str:
    source = sp.encode(f"{TRANSLATION_TGT_TOKEN} {text}", out_type=str)
    results = translator.translate_batch(
        [source],
        beam_size=TRANSLATION_BEAM_SIZE,
        no_repeat_ngram_size=TRANSLATION_NO_REPEAT_NGRAM_SIZE,
        length_penalty=TRANSLATION_LENGTH_PENALTY,
    )
    return sp.decode(results[0].hypotheses[0])


# MADLAD often says the same thing twice in different words ("我太緊張了，
# 我很緊張。", "因為我們沒辦法一起合作，因為我們不能一起合作。"). A later clause
# is dropped when nearly all its characters already appeared earlier: 80%+
# overlap, or 60%+ where the new characters are only function words (很, 而且,
# 在...). The function-word condition is what keeps real parallel clauses like
# "我喜歡貓，我喜歡狗" (new character 狗 is content). Calibrated on the live and
# original benchmark sets plus the second live session, see
# benchmark/madlad_decoding_sweep.md.
_CLAUSE_SPLIT_RE = re.compile(r"([，,；;、]\s*)")
_CONTENT_CHAR_RE = re.compile(r"[一-鿿぀-ヿA-Za-z0-9]")
_FUNCTION_CHARS = set("很太也都還又就了的是在得著過呢吧啊嗎呀哦喔而且和與或者最真非常點些個這那麼樣")


# MADLAD also lists alternatives separated by spaces ("停下來 停住 停止",
# "樂器大河 音樂大河"). Chinese doesn't put spaces between characters, so a
# space between two Han characters marks such a list: a segment sharing half
# or more of its characters with what was kept before it is dropped. Segments
# with little overlap stay ("他說 我不知道").
_CJK_SPACE_RE = re.compile(r"(?<=[一-鿿])\s+(?=[一-鿿])")


def _drop_space_alternatives(text: str) -> str:
    segments = _CJK_SPACE_RE.split(text)
    if len(segments) == 1:
        return text
    kept, seen = [], set()
    for segment in segments:
        chars = set(_CONTENT_CHAR_RE.findall(segment))
        if kept and chars and len(chars & seen) / len(chars) >= 0.5:
            continue
        kept.append(segment)
        seen |= chars
    return " ".join(kept) if len(kept) < len(segments) else text


def drop_repeated_clauses(text: str) -> str:
    text = _drop_space_alternatives(text)
    parts = _CLAUSE_SPLIT_RE.split(text)
    clauses, separators = parts[0::2], parts[1::2] + [""]
    kept, seen = [], set()
    for clause, sep in zip(clauses, separators):
        chars = set(_CONTENT_CHAR_RE.findall(clause))
        if kept and len(chars) >= 2:
            overlap = len(chars & seen) / len(chars)
            if overlap >= 0.8 or (overlap >= 0.6 and chars - seen <= _FUNCTION_CHARS):
                continue
        kept.append(clause + sep)
        seen |= chars
    if len(kept) == len(clauses):
        return text
    result = "".join(kept).rstrip("，,；;、 ")
    end = text.rstrip()[-1:]
    if end in "。？！?!" and not result.endswith(end):
        result += end
    return result


# Japanese endings that leave a sentence open (…て, …けど, …のに, …と, …を):
# the next unit most likely finishes it. Particles like は/が/の/って were
# tried too and joined unrelated sentences more often than not. えっと is a
# filler, not an open と; a question (…?) is complete.
_CONTINUATION_RE = re.compile(r"(て|けど|けれど|のに|ので|たら|ば|と|を|に|も)$")
_TRAILING_RE = re.compile(r"[\s、。,.…~〜ー]+$")


def continues(japanese_text: str) -> bool:
    """True if the text ends mid-sentence (see _CONTINUATION_RE)."""
    text = _TRAILING_RE.sub("", japanese_text)
    if text.endswith(("?", "？", "えっと")) or glossary.fixed(japanese_text) is not None:
        return False
    return bool(_CONTINUATION_RE.search(text))


def load_model():
    """Load the configured backend plus the OpenCC converter. Sakura starts
    its llama-server once here (sakura.start); MADLAD is loaded in-process by
    _load_madlad. Safe to skip calling this (translate() then just returns ""
    for every call) so a translation setup failure never prevents the
    Japanese STT pipeline from running — see translate()'s docstring."""
    global _loaded, _converter, _to_simplified
    _converter = opencc.OpenCC(OPENCC_CONFIG)
    _to_simplified = opencc.OpenCC("t2s")
    if BACKEND == "sakura":
        sakura.start()
    elif BACKEND == "madlad":
        _load_madlad()
    else:
        raise ValueError(f"Unknown TRANSLATION_BACKEND {BACKEND!r} in config.py (valid: sakura, madlad)")
    _loaded = True


def _load_madlad():
    """Legacy backend. Load the MADLAD translator + tokenizer + OpenCC converter, on the
    device fixed by config.TRANSLATION_DEVICE (set via HARDWARE_PRESET — see
    config.py). No automatic device fallback here: the preset is an explicit
    choice, so if the configured device can't actually be used (e.g.
    TRANSLATION_DEVICE="cuda" but the cuBLAS/cuDNN runtime is missing), that
    must be a loud startup failure, not a silent downgrade to a different
    device — same "no silent fallback" principle already applied to STT model
    selection."""
    global _translator, _sp
    from huggingface_hub import snapshot_download

    logger.info("Loading translation model '%s' on %s", TRANSLATION_MODEL_REPO, TRANSLATION_DEVICE)
    model_dir = snapshot_download(TRANSLATION_MODEL_REPO)
    _sp = spm.SentencePieceProcessor()
    _sp.load(os.path.join(model_dir, "spiece.model"))

    compute_type = (
        TRANSLATION_COMPUTE_TYPE_GPU if TRANSLATION_DEVICE == "cuda" else TRANSLATION_COMPUTE_TYPE_CPU
    )
    _translator = ctranslate2.Translator(model_dir, device=TRANSLATION_DEVICE, compute_type=compute_type)
    _run(_translator, _sp, "テスト")  # warm-up + surface any runtime issue now, not on first real call
    logger.info(
        "Translation model '%s' loaded on %s (%s)", TRANSLATION_MODEL_REPO, TRANSLATION_DEVICE, compute_type
    )
    return _translator


def translate(japanese_text: str) -> TranslationResult:
    """Translate finalized Japanese text to Taiwan Traditional Chinese.
    Returns TranslationResult(raw=<model's Simplified output>, final=<after
    OpenCC>) — both kept for debug logging (see server.py). Never raises:
    returns TranslationResult("", "") if the model isn't loaded or
    translation fails, so a translation problem never breaks the Japanese STT
    pipeline that calls this. Only meant for finalized text, not partial
    previews — the caller (server.py) is responsible for only calling this on
    finals that also pass its quality gate."""
    if not _loaded:
        logger.warning("translate() called before load_model() (or load_model failed); skipping")
        return TranslationResult("", "")
    if not japanese_text.strip():
        return TranslationResult("", "")
    fixed = glossary.fixed(japanese_text)
    if fixed is not None:
        logger.info("[FIXED] %s -> %s", japanese_text, fixed)
        return TranslationResult(fixed, fixed)
    try:
        if BACKEND == "sakura":
            # Member names stay as spoken and go in as glossary entries.
            source_text = glossary.apply(japanese_text, replace_names=False)
            names = [(src, _to_simplified.convert(dst)) for src, dst in glossary.name_entries(japanese_text)]
        else:
            source_text, names = glossary.apply(japanese_text), []
        if source_text != japanese_text:
            logger.info("[GLOSSARY] %s -> %s", japanese_text, source_text)
        if names:
            logger.info("[NAMES] %s", ", ".join(f"{src}->{dst}" for src, dst in names))
        if BACKEND == "sakura":
            zh_hans = sakura.generate(source_text, names)
        else:
            zh_hans = _run(_translator, _sp, source_text)
        zh_tw = glossary.fix_output(_converter.convert(zh_hans))
        if BACKEND == "madlad" and TRANSLATION_DROP_REPEATED_CLAUSES:
            deduped = drop_repeated_clauses(zh_tw)
            if deduped != zh_tw:
                logger.info("[DEDUP] %s -> %s", zh_tw, deduped)
                zh_tw = deduped
        return TranslationResult(zh_hans, zh_tw)
    except Exception:
        logger.exception("Translation failed for: %r", japanese_text)
        return TranslationResult("", "")
