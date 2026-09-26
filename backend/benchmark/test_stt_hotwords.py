"""Does faster-whisper's `hotwords` hint fix member-name misrecognitions
(わため -> 渡辺, トワ様 -> 父様) without inserting names that weren't said?

Splits a recorded session into speech chunks with the production pause
detection (SILENCE_TRIGGER_MS, max MAX_CHUNK_SECONDS), roughly what the live
pipeline finalizes, then transcribes every chunk with the production final
settings once per hotword variant. Offline and not real-time, so it runs in
a fraction of the recording length. Does NOT touch the production pipeline.

Result on recordings/session_20260926_154412.wav (75 chunks), 2026-09-26:
not adopted. "gen4" fixed the one name error (渡目 -> ワタメ) but cut other
sentences in half and inserted stray English ("I", "to") in 10+ chunks;
"jp_all" (longer hint) made every chunk come out empty. Kotoba (distilled
Whisper) doesn't cope with prompt conditioning here.

Usage (from backend/):
    venv\\Scripts\\python.exe benchmark\\test_stt_hotwords.py <wav>
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")

import wave

import numpy as np

import transcriber  # registers the NVIDIA DLL dirs before faster_whisper loads
from config import MAX_CHUNK_SECONDS, SAMPLE_RATE, WHISPER_LANGUAGE
from faster_whisper.vad import get_speech_timestamps

GEN4 = "角巻わため わため 天音かなた 桐生ココ 常闇トワ 姫森ルーナ ホロライブ 4期生"
JP_ALL = GEN4 + (" 白上フブキ 夏色まつり 赤井はあと はあちゃま 宝鐘マリン 兎田ぺこら 白銀ノエル"
                 " 不知火フレア 湊あくあ 紫咲シオン 百鬼あやめ 癒月ちょこ 大空スバル 大神ミオ 猫又おかゆ"
                 " 戌神ころね さくらみこ 星街すいせい ときのそら 雪花ラミィ 桃鈴ねね 獅白ぼたん 尾丸ポルカ")
VARIANTS = {"none": None, "gen4": GEN4, "jp_all": JP_ALL}

# Known misrecognitions of names said in the recorded sessions, and correct forms.
WRONG = ["渡辺", "渡部", "渡目", "渡り", "父様", "トワチ", "アヨン"]
RIGHT = ["わため", "角巻", "トワ", "ココ", "かなた", "ルーナ", "4期生"]


def chunks(audio):
    segs = get_speech_timestamps(audio, transcriber._silence_vad_options, sampling_rate=SAMPLE_RATE)
    max_len = int(MAX_CHUNK_SECONDS * SAMPLE_RATE)
    pad = int(0.2 * SAMPLE_RATE)
    for s in segs:
        start, end = max(0, s["start"] - pad), min(len(audio), s["end"] + pad)
        for a in range(start, end, max_len):
            yield audio[a:min(end, a + max_len)]


def main():
    wav = wave.open(sys.argv[1], "rb")
    audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    model = transcriber.load_model()
    parts = [c for c in chunks(audio) if len(c) >= SAMPLE_RATE // 2]
    print(f"{len(parts)} speech chunks")

    results = {}
    for name, hot in VARIANTS.items():
        texts = []
        for c in parts:
            segments, _ = model.transcribe(c, language=WHISPER_LANGUAGE, hotwords=hot, **transcriber.FINAL_KWARGS)
            texts.append("".join(s.text for s in segments).strip())
        results[name] = texts
        joined = "\n".join(texts)
        wrong = {w: joined.count(w) for w in WRONG if joined.count(w)}
        right = {w: joined.count(w) for w in RIGHT if joined.count(w)}
        print(f"\n== {name}: wrong={wrong} right={right} empty={sum(not t for t in texts)}")

    print("\n== chunks that differ from 'none'")
    for i, base in enumerate(results["none"]):
        others = {k: v[i] for k, v in results.items() if k != "none" and v[i] != base}
        if others:
            print(f"[{i}] none  : {base}")
            for k, v in others.items():
                print(f"    {k:6s}: {v}")


if __name__ == "__main__":
    main()
