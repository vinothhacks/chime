"""Application error taxonomy. CLI maps these to exit codes."""

from __future__ import annotations


class ChimeError(Exception):
    """Base error. `exit_code` is used by the CLI only."""

    exit_code: int = 1


class ValidationError(ChimeError):
    exit_code = 1


class NotFoundError(ChimeError):
    exit_code = 1


class StorageError(ChimeError):
    exit_code = 2


class CorruptStateError(ChimeError):
    exit_code = 2


class MigrationError(ChimeError):
    exit_code = 2


class LockError(ChimeError):
    exit_code = 3


class AudioUnavailableError(ChimeError):
    exit_code = 4
