from __future__ import annotations

from chime.sound import backend_args, detect_backend


def test_backend_args_are_list_not_shell() -> None:
    args = backend_args("ffplay", "beep.wav")
    assert args[0] == "ffplay"
    assert "-nodisp" in args
    assert all(isinstance(item, str) for item in args)


def test_detect_backend_returns_string() -> None:
    name = detect_backend()
    assert isinstance(name, str)
    assert name
