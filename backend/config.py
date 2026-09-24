HOST = "127.0.0.1"
PORT = 8765

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2  # PCM16

WHISPER_MODEL_SIZE = "small"
WHISPER_LANGUAGE = "ja"

# Streaming: while a sentence is still being spoken, periodically re-transcribe
# the whole open segment and show it as a correctable "partial" preview.
# Finalize (commit and clear) at a natural pause, so a segment lands close to
# a whole sentence instead of being cut mid-word at an arbitrary boundary.
MIN_CHUNK_SECONDS = 1.0  # never finalize before this much audio, even if silent
MAX_CHUNK_SECONDS = 8.0  # force a finalize after this much regardless of VAD, so
# uninterrupted speech doesn't grow latency unboundedly
SILENCE_TRIGGER_MS = 300  # trailing silence needed to count as "a pause happened"

PARTIAL_MIN_SECONDS = 0.5  # don't bother transcribing a shorter open segment
PARTIAL_INTERVAL_SECONDS = 0.75  # how often to refresh the partial preview

# Safety net: a chunk with no clear speech can occasionally make Whisper's
# decoder loop far longer than normal (see transcriber.py). Give up and move on
# rather than blocking all future transcription for the rest of the session.
TRANSCRIBE_TIMEOUT_SECONDS = 12
