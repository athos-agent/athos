"""Control: which pieces this session may load. Until the user chooses, every piece is enabled (relevance still
decides what is injected)."""

from __future__ import annotations

from athos import store


def filter_pieces(pieces: list[store.Piece], cwd: str | None = None) -> list[store.Piece]:
    return pieces
