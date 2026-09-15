from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


def write_beep(
    path: Path, *, seconds: float = 0.35, freq: float = 880.0, rate: int = 44100
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(rate * seconds)
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        fade = int(rate * 0.02)
        for index in range(n):
            envelope = 1.0
            if index < fade:
                envelope = index / fade
            elif index > n - fade:
                envelope = (n - index) / fade
            sample = int(0.4 * 32767 * envelope * math.sin(2 * math.pi * freq * index / rate))
            frames.extend(struct.pack("<h", sample))
        handle.writeframes(bytes(frames))


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "src" / "chime" / "resources" / "beep.wav"
    write_beep(target)
    print(target)
