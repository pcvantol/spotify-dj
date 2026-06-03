from __future__ import annotations

import io
import math
import wave

SAMPLE_RATE = 16000

def simple_tone_wav(duration_s: float = 0.35, frequency: float = 440.0) -> bytes:
    frames = int(duration_s * SAMPLE_RATE)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        for i in range(frames):
            sample = int(0.18 * 32767 * math.sin(2 * math.pi * frequency * i / SAMPLE_RATE))
            wf.writeframesraw(sample.to_bytes(2, "little", signed=True))
    return buf.getvalue()
