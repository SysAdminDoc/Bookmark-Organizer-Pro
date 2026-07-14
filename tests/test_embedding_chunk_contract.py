"""Boundary and progress properties for citation-aware embedding chunks."""

from __future__ import annotations

import random

import pytest

from bookmark_organizer_pro.services.embeddings import EmbeddingService


@pytest.mark.parametrize(
    ("chunk_chars", "overlap"),
    [(0, 0), (-1, 0), (10, -1), (10, 10), (10, 11)],
)
def test_invalid_chunk_bounds_are_rejected(chunk_chars: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        EmbeddingService.chunk_text("content", chunk_chars=chunk_chars, overlap=overlap)


@pytest.mark.parametrize("chunk_chars,overlap", [(True, 0), (100, False), (12.5, 1)])
def test_chunk_bounds_must_be_integers(chunk_chars, overlap) -> None:
    with pytest.raises(TypeError):
        EmbeddingService.chunk_text("content", chunk_chars=chunk_chars, overlap=overlap)


def test_sentence_adjustment_never_exceeds_the_declared_ceiling() -> None:
    text = "A" * 105 + ". " + "B" * 200

    chunks = EmbeddingService.chunk_text(text, chunk_chars=100, overlap=20)

    assert all(chunk["char_end"] - chunk["char_start"] <= 100 for chunk in chunks)
    assert chunks[0]["char_end"] == 100


def test_randomized_chunks_advance_monotonically_and_cover_the_source() -> None:
    randomizer = random.Random(20260714)
    alphabet = "abc def. ghi jkl mno pqr stu vwx yz"

    for _ in range(300):
        length = randomizer.randint(1, 4000)
        chunk_chars = randomizer.randint(1, min(700, length + 50))
        overlap = randomizer.randint(0, chunk_chars - 1)
        text = "a" + "".join(randomizer.choice(alphabet) for _ in range(length - 1))

        chunks = EmbeddingService.chunk_text(
            text,
            chunk_chars=chunk_chars,
            overlap=overlap,
        )

        assert chunks
        assert chunks[0]["char_start"] == 0
        assert chunks[-1]["char_end"] == len(text)
        assert [chunk["id"] for chunk in chunks] == [
            f"c{index}" for index in range(len(chunks))
        ]
        for index, chunk in enumerate(chunks):
            start = chunk["char_start"]
            end = chunk["char_end"]
            assert 0 <= start < end <= len(text)
            assert end - start <= chunk_chars
            assert chunk["text"] == text[start:end]
            if index:
                previous = chunks[index - 1]
                assert start > previous["char_start"]
                assert end > previous["char_end"]
                assert start <= previous["char_end"]
