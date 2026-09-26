import importlib.util
import logging
import os
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
        for pkg in ("cublas", "cudnn", "cuda_nvrtc"):
            bin_dir = os.path.join(base, pkg, "bin")
            if os.path.isdir(bin_dir):
                dirs.append(bin_dir)
                os.add_dll_directory(bin_dir)
    if dirs:
        os.environ["PATH"] = os.pathsep.join(dirs) + os.pathsep + os.environ.get("PATH", "")


_register_nvidia_dll_dirs()

import ctranslate2
import opencc
import sentencepiece as spm

import glossary
from config import (
    OPENCC_CONFIG,
    TRANSLATION_BEAM_SIZE,
    TRANSLATION_COMPUTE_TYPE_CPU,
    TRANSLATION_COMPUTE_TYPE_GPU,
    TRANSLATION_DEVICE,
    TRANSLATION_LENGTH_PENALTY,
    TRANSLATION_MODEL_REPO,
    TRANSLATION_NO_REPEAT_NGRAM_SIZE,
    TRANSLATION_TGT_TOKEN,
)

logger = logging.getLogger("translator")

_translator = None
_sp = None
_converter = None


def _run(translator, sp, text: str) -> str:
    source = sp.encode(f"{TRANSLATION_TGT_TOKEN} {text}", out_type=str)
    results = translator.translate_batch(
        [source],
        beam_size=TRANSLATION_BEAM_SIZE,
        no_repeat_ngram_size=TRANSLATION_NO_REPEAT_NGRAM_SIZE,
        length_penalty=TRANSLATION_LENGTH_PENALTY,
    )
    return sp.decode(results[0].hypotheses[0])


def load_model():
    """Load the MADLAD translator + tokenizer + OpenCC converter, on the
    device fixed by config.TRANSLATION_DEVICE (set via HARDWARE_PRESET — see
    config.py). No automatic device fallback here: the preset is an explicit
    choice, so if the configured device can't actually be used (e.g.
    TRANSLATION_DEVICE="cuda" but the cuBLAS/cuDNN runtime is missing), that
    must be a loud startup failure, not a silent downgrade to a different
    device — same "no silent fallback" principle already applied to STT model
    selection. Safe to skip calling this (translate() then just returns ""
    for every call) so a translation setup failure never prevents the
    Japanese STT pipeline from running — see translate()'s docstring."""
    global _translator, _sp, _converter
    from huggingface_hub import snapshot_download

    logger.info("Loading translation model '%s' on %s", TRANSLATION_MODEL_REPO, TRANSLATION_DEVICE)
    model_dir = snapshot_download(TRANSLATION_MODEL_REPO)
    _sp = spm.SentencePieceProcessor()
    _sp.load(os.path.join(model_dir, "spiece.model"))
    _converter = opencc.OpenCC(OPENCC_CONFIG)

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
    Returns TranslationResult(raw=<MADLAD Simplified output>, final=<after
    OpenCC>) — both kept for debug logging (see server.py). Never raises:
    returns TranslationResult("", "") if the model isn't loaded or
    translation fails, so a translation problem never breaks the Japanese STT
    pipeline that calls this. Only meant for finalized text, not partial
    previews — the caller (server.py) is responsible for only calling this on
    finals that also pass its quality gate."""
    if _translator is None:
        logger.warning("translate() called before load_model() (or load_model failed); skipping")
        return TranslationResult("", "")
    if not japanese_text.strip():
        return TranslationResult("", "")
    fixed = glossary.filler(japanese_text)
    if fixed is not None:
        logger.info("[FILLER] %s -> %s", japanese_text, fixed)
        return TranslationResult(fixed, fixed)
    try:
        source_text = glossary.apply(japanese_text)
        if source_text != japanese_text:
            logger.info("[GLOSSARY] %s -> %s", japanese_text, source_text)
        zh_hans = _run(_translator, _sp, source_text)
        zh_tw = _converter.convert(zh_hans)
        return TranslationResult(zh_hans, zh_tw)
    except Exception:
        logger.exception("Translation failed for: %r", japanese_text)
        return TranslationResult("", "")
