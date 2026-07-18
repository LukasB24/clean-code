"""Distill the pretrained WordLlama backbone into the vendored embedding asset.

Reads the ``l2_supercat_256`` static token embeddings that ship inside the
``wordllama`` PyPI wheel (no network access needed), embeds every whole-word
token of its vocabulary, PCA-reduces the vectors, int8-quantizes them, and
writes ``src/cleancode/semantics/embeddings.npz``.

This script is a build-time tool: ``wordllama`` (and its transitive
``tokenizers``/``safetensors`` dependencies) are needed only here, never in
the linter's runtime environment. Run it from a throwaway virtualenv:

    pip install wordllama numpy
    python tools/distill_backbone.py

The output is deterministic for a given wordllama version: the token
vocabulary is sorted, PCA uses numpy's deterministic SVD with a fixed sign
convention, and quantization is a pure function of the projected vectors.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import numpy as np

OUTPUT = Path(__file__).parent.parent / "src" / "cleancode" / "semantics" / "embeddings.npz"
TARGET_DIM = 128
_WORD_TOKEN = re.compile(r"^▁([a-z]{2,})$")

# Software/rationale vocabulary that isn't a single whole-word token in the
# backbone's BPE vocabulary. These are embedded through the backbone's own
# subword composition, so they get real pretrained vectors, not guesses.
# Inflected forms don't belong here — the runtime stems them to a base form.
SUPPLEMENT = """
    maximize minimize optimize memoize vectorize quantize normalize serialize
    deserialize tokenize parallelize amortize preallocate prefetch precompute
    recompute reuse debounce throttle decrement backoff retry timeout timezone
    tolerance epsilon rounding truncation overflow underflow precision sentinel
    invariant idempotent deterministic reproducible concurrency reentrant
    deadlock throughput latency checksum endianness allocation batching
    pagination striping locality contiguous vectorized hotspot bottleneck
    profiling benchmark heuristic fallback quirk workaround upstream downstream
    backward compatibility deprecation refactoring subclass superclass
    metaclass docstring linter formatter parser lexer tokenizer recursion
    iteration comprehension generator coroutine callback closure decorator
    singleton namespace whitespace substring concatenate interpolation slicing
    indexing hashable mutable immutable iterable iterator getter setter mutex
    semaphore caching lookup lazily eagerly middleware schema migration
    rollback transaction atomicity consistency replication sharding partition
    chunking buffering streaming pipelining tuple dict bool int str kwargs
    enum dataclass numpy json yaml toml sql api url http utf ascii unicode
    regex glob boolean thundering herd exponential
""".split()


def _load_backbone():
    """Load WordLlama purely from the files bundled in its wheel.

    The wheel ships the tokenizer config under ``tokenizers/`` but the loader
    looks in ``tokenizer/`` (singular) and falls back to downloading from
    Hugging Face; copying the bundled file into the expected directory keeps
    the whole distillation offline.
    """
    import wordllama
    from wordllama import WordLlama

    package_dir = Path(wordllama.__file__).parent
    expected = package_dir / "tokenizer"
    expected.mkdir(exist_ok=True)
    bundled = package_dir / "tokenizers" / "l2_supercat_tokenizer_config.json"
    if not (expected / bundled.name).exists():
        shutil.copy(bundled, expected / bundled.name)
    return WordLlama.load(disable_download=True)


def _word_vocabulary(model) -> list[str]:
    """Lowercase whole-word tokens of the backbone's BPE vocabulary.

    A leading ``▁`` marks a token that starts a word; keeping only fully
    alphabetic lowercase ones (length >= 2) yields the plain-English word
    list the runtime table is keyed by. Capitalized variants are redundant —
    the runtime lowercases before lookup.
    """
    vocab = model.tokenizer.get_vocab()
    words = {match.group(1) for token in vocab if (match := _WORD_TOKEN.match(token))}
    return sorted(words | set(SUPPLEMENT))


def _pca_project(vectors: np.ndarray, dim: int) -> np.ndarray:
    centered = vectors - vectors.mean(axis=0, keepdims=True)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    components = vt[:dim]
    # Fix each component's sign so the SVD's sign ambiguity can't make two
    # runs disagree: largest-magnitude coefficient is always positive.
    signs = np.sign(components[np.arange(dim), np.abs(components).argmax(axis=1)])
    return centered @ (components * signs[:, None]).T


def _quantize_rows(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    scales = np.abs(vectors).max(axis=1) / 127.0
    scales[scales == 0] = 1.0
    quantized = np.round(vectors / scales[:, None]).astype(np.int8)
    return quantized, scales.astype(np.float32)


def main() -> None:
    model = _load_backbone()
    words = _word_vocabulary(model)
    print(f"embedding {len(words)} whole-word tokens...")
    vectors = model.embed(words).astype(np.float64)

    kept = np.linalg.norm(vectors, axis=1) > 0
    words = [word for word, keep in zip(words, kept) if keep]
    vectors = _pca_project(vectors[kept], TARGET_DIM)
    quantized, scales = _quantize_rows(vectors)

    meta = {"backbone": "wordllama/l2_supercat_256", "dim": TARGET_DIM, "version": 1}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUTPUT,
        vocab=np.array(words),
        vectors=quantized,
        scales=scales,
        meta=json.dumps(meta),
    )
    size_mb = OUTPUT.stat().st_size / 1e6
    print(f"wrote {OUTPUT} ({len(words)} words x {TARGET_DIM} dims, {size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
