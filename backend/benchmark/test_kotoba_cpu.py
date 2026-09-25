"""Kotoba-whisper forced onto CPU (int8), replayed against test_clip.wav
using the same VAD-triggered finalize logic as production (see
benchmark/run_model.py), for modes C/D of the hardware compatibility matrix.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")

import time
import wave

import numpy as np
import psutil
from faster_whisper import WhisperModel
from faster_whisper.vad import VadOptions, get_speech_timestamps

from config import MAX_CHUNK_SECONDS, MIN_CHUNK_SECONDS, PARTIAL_MIN_SECONDS, SAMPLE_RATE, SILENCE_TRIGGER_MS

BYTES_PER_SECOND = SAMPLE_RATE * 2
CHUNK_BYTES = int(SAMPLE_RATE * 0.25) * 2
FINAL_KWARGS = dict(beam_size=5, condition_on_previous_text=False, vad_filter=True)
_vad_options = VadOptions(min_silence_duration_ms=SILENCE_TRIGGER_MS, speech_pad_ms=0)


def has_trailing_silence(pcm16_bytes):
    audio = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    segments = get_speech_timestamps(audio, _vad_options, sampling_rate=SAMPLE_RATE)
    if not segments:
        return True
    trailing_samples = len(audio) - segments[-1]["end"]
    return (trailing_samples / SAMPLE_RATE * 1000) >= SILENCE_TRIGGER_MS


proc = psutil.Process()
proc.cpu_percent()

print("Loading Kotoba-whisper on CPU (int8)...")
t0 = time.monotonic()
model = WhisperModel("kotoba-tech/kotoba-whisper-v2.0-faster", device="cpu", compute_type="int8")
load_time = time.monotonic() - t0
ram_mb = proc.memory_info().rss / 1e6
print(f"Loaded in {load_time:.1f}s. RAM: {ram_mb:.0f} MB")

wav = wave.open("benchmark/test_clip.wav", "rb")
all_bytes = wav.readframes(wav.getnframes())
wav.close()
audio_duration = len(all_bytes) / BYTES_PER_SECOND

buffer = bytearray()
infer_times = []
cpu_samples = []
pos = 0
n = len(all_bytes)


def finalize(pcm_bytes):
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    t1 = time.monotonic()
    segs, _info = model.transcribe(audio, language="ja", **FINAL_KWARGS)
    text = "".join(s.text for s in segs).strip()
    elapsed = time.monotonic() - t1
    infer_times.append(elapsed)
    cpu_samples.append(proc.cpu_percent())
    if text:
        print(f"  [{elapsed*1000:.0f}ms] {text[:40]}")


while pos < n:
    chunk = all_bytes[pos:pos + CHUNK_BYTES]
    pos += CHUNK_BYTES
    buffer.extend(chunk)
    duration = len(buffer) / BYTES_PER_SECOND
    if duration < PARTIAL_MIN_SECONDS:
        continue
    should_finalize = duration >= MAX_CHUNK_SECONDS
    if not should_finalize and duration >= MIN_CHUNK_SECONDS:
        should_finalize = has_trailing_silence(bytes(buffer))
    if should_finalize:
        finalize(bytes(buffer))
        buffer.clear()

if len(buffer) / BYTES_PER_SECOND >= PARTIAL_MIN_SECONDS:
    finalize(bytes(buffer))

total_infer = sum(infer_times)
rtf = total_infer / audio_duration
ram_final = proc.memory_info().rss / 1e6
infer_sorted = sorted(infer_times)
n2 = len(infer_sorted)
print(f"\n=== Kotoba-whisper CPU summary ===")
print(f"Load time: {load_time:.1f}s, RAM after load: {ram_mb:.0f} MB, RAM final: {ram_final:.0f} MB")
print(f"Audio duration: {audio_duration:.1f}s, segments: {n2}")
print(f"Total inference time: {total_infer:.1f}s, realtime factor: {rtf:.3f}")
print(f"Avg inference latency: {sum(infer_times)/n2*1000:.0f}ms")
print(f"P50: {infer_sorted[n2//2]*1000:.0f}ms, P95: {infer_sorted[min(int(n2*0.95), n2-1)]*1000:.0f}ms")
print(f"Avg CPU%%: {sum(cpu_samples)/len(cpu_samples):.0f}%, Peak: {max(cpu_samples):.0f}%")
