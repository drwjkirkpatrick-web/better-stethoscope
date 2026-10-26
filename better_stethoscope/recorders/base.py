"""BaseRecorder: the contract every microphone module implements.

Each front-end (USB mic, DIY electret, piezo contact mic, I2S MEMS,
Thinklabs One line-in) lives in its own module next to this file and
subclasses BaseRecorder. The subclass provides:

* identity     -- ``slug``, ``display_name``, ``description``, wiring notes
                  and gain advice (shown by ``better-stethoscope devices``)
* discovery    -- ``device_match`` substrings used to pick its devices out
                  of the PortAudio device list
* streaming    -- ``_iter_blocks()``, a generator yielding 1-D float32
                  numpy blocks (usually by calling ``self._callback_blocks()``)

Everything hard -- device resolution, the record loop, progress callbacks,
stream teardown -- lives here once, so a new microphone is ~60 lines of
docs plus a little wiring.

NOTE: ``sounddevice`` (PortAudio) is imported *lazily inside methods*, so
importing the package never fails on a machine without audio hardware --
that is what lets the whole test suite run on any box, and lets tests
substitute a fake backend via ``sys.modules``.
"""

from __future__ import annotations

import queue
from abc import ABC, abstractmethod
from typing import Callable, Generator, Optional

import numpy as np


class BaseRecorder(ABC):
    """Abstract microphone front-end.

    Concrete modules define the class attributes and implement
    ``_iter_blocks()``; everything else is inherited behavior.
    """

    # ---- identity (overridden by each module) ---------------------------
    slug: str = ""                       # CLI key, e.g. "electret"
    display_name: str = ""               # human-readable name
    description: str = ""                # 1-2 sentences: what this front-end is
    hardware_notes: str = ""             # multi-line wiring/coupling notes
    gain_advice: str = ""                # how to set gain for this front-end
    device_match: tuple[str, ...] = ()   # name substrings for auto-discovery
    # NOTE: empty device_match means "match any input device" -- used by the
    # most generic module (usb_mic) as the fallback of last resort.

    # ---- instance config -------------------------------------------------
    def __init__(
        self,
        device_index: Optional[int] = None,
        sample_rate: int = 48000,
        channels: int = 1,
        blocksize: int = 1024,
        dtype: str = "float32",
    ) -> None:
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = channels
        self.blocksize = blocksize
        self.dtype = dtype

    # ---- backend plumbing -------------------------------------------------
    @staticmethod
    def backend_status() -> tuple[bool, str]:
        """(ok, message) -- is the sounddevice/PortAudio backend importable?

        On a fresh Pi this returns False until ``sudo apt install
        libportaudio2`` has been run; the CLI reports it instead of crashing.
        """
        try:
            import sounddevice as sd  # noqa: PLC0415 (lazy on purpose)

            return True, f"sounddevice {getattr(sd, '__version__', '?')} OK"
        except Exception as exc:  # pragma: no cover - hardware-dependent
            return False, f"{type(exc).__name__}: {exc}"

    @classmethod
    def _matches(cls, device_name: str) -> bool:
        """Does this device name look like one of ours?"""
        if not cls.device_match:
            return True
        low = device_name.lower()
        return any(token in low for token in cls.device_match)

    @classmethod
    def discover(cls) -> list[dict]:
        """Input devices matching this module's hints.

        Returns ``[{"index", "name", "module", "display_name"}]``. On any
        backend problem returns ``[]`` (the CLI prints ``errors()`` instead).
        """
        ok, _ = cls.backend_status()
        if not ok:
            return []
        import sounddevice as sd  # noqa: PLC0415 (lazy on purpose)

        found: list[dict] = []
        for i, dev in enumerate(sd.query_devices()):
            name = str(dev.get("name", ""))
            if dev.get("max_input_channels", 0) < 1:
                continue
            if not cls._matches(name):
                continue
            found.append(
                {"index": i, "name": name, "module": cls.slug, "display_name": cls.display_name}
            )
        return found

    def resolve_device(self) -> Optional[int]:
        """Which PortAudio device index to open?

        Order: explicit constructor arg > first discovery match > system
        default input. Tests exercise the first two with a fake backend.
        """
        if self.device_index is not None:
            return self.device_index
        found = self.discover()
        if found:
            return int(found[0]["index"])
        ok, _ = self.backend_status()
        if not ok:
            return None
        import sounddevice as sd  # noqa: PLC0415 (lazy on purpose)

        default = sd.default.device
        if isinstance(default, (list, tuple)):
            return int(default[0])
        return int(default)

    # ---- streaming ---------------------------------------------------------
    @abstractmethod
    def _iter_blocks(self) -> Generator[np.ndarray, None, None]:
        """Yield 1-D float32 blocks of audio forever (or until closed).

        Implementations open their stream lazily on first ``next()`` and
        must release it when the generator is ``close()``d -- the ``with``
        inside ``_callback_blocks()`` below does that automatically.
        """

    def _callback_blocks(
        self, extra_stream_kwargs: Optional[dict] = None
    ) -> Generator[np.ndarray, None, None]:
        """Canonical PortAudio capture loop shared by sounddevice modules.

        Pattern: callback thread pushes numpy copies into a queue; the
        consumer generator pulls them. This is the pattern the sounddevice
        docs themselves recommend -- it decouples the audio callback from
        whatever the consumer is doing (disk writes, analysis) so the
        callback never blocks and never drops frames.
        """
        import sounddevice as sd  # noqa: PLC0415 (lazy on purpose)

        device = self.resolve_device()
        if device is None:
            raise RuntimeError(
                f"[{self.slug}] no input device found -- plug in the mic / "
                "check `better-stethoscope devices`."
            )
        blocks: "queue.Queue[np.ndarray]" = queue.Queue()

        def _callback(indata, frames, time_info, status) -> None:
            arr = np.asarray(indata)
            if arr.ndim > 1:
                arr = arr[:, 0]  # first channel -> mono
            blocks.put(np.array(arr, dtype=np.float32, copy=True))

        kwargs = dict(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            device=device,
            blocksize=self.blocksize,
            callback=_callback,
        )
        if extra_stream_kwargs:
            kwargs.update(extra_stream_kwargs)
        with sd.InputStream(**kwargs):
            while True:
                yield blocks.get()

    # ---- recording -----------------------------------------------------
    def record(
        self, seconds: float, on_progress: Optional[Callable[[float], None]] = None
    ) -> np.ndarray:
        """Capture exactly ``seconds`` of audio as a 1-D float32 array.

        ``on_progress(fraction)`` fires per block for progress bars.
        Raises RuntimeError when the stream delivers nothing -- a dead
        channel should fail loudly, not record silence.
        """
        need = max(1, int(round(seconds * self.sample_rate)))
        parts: list[np.ndarray] = []
        got = 0
        gen = self._iter_blocks()
        try:
            for block in gen:
                chunk = np.asarray(block, dtype=np.float32).ravel()
                parts.append(chunk)
                got += chunk.size
                if on_progress is not None:
                    on_progress(min(1.0, got / need))
                if got >= need:
                    break
        finally:
            gen.close()  # runs the generator's ``with``-teardown: closes the stream
        if got == 0:
            raise RuntimeError(f"[{self.slug}] stream produced no audio (dead channel?)")
        audio = np.concatenate(parts) if len(parts) > 1 else parts[0]
        return audio[:need]

    def iter_blocks(self, max_seconds: Optional[float] = None) -> Generator[np.ndarray, None, None]:
        """Infinite block iterator (for the live ``monitor`` command).

        Stops after ``max_seconds`` if given; otherwise the caller breaks
        (e.g. Ctrl+C) and the final ``gen.close()`` below tears the stream
        down deterministically.
        """
        limit = None if max_seconds is None else int(max_seconds * self.sample_rate)
        got = 0
        gen = self._iter_blocks()
        try:
            for block in gen:
                got += np.asarray(block).size
                yield np.asarray(block, dtype=np.float32).ravel()
                if limit is not None and got >= limit:
                    break
        finally:
            gen.close()

    # ---- presentation ----------------------------------------------------
    @classmethod
    def describe(cls) -> dict:
        """Identity dict for ``better-stethoscope devices`` output."""
        return {
            "slug": cls.slug,
            "display_name": cls.display_name,
            "description": cls.description,
            "hardware_notes": cls.hardware_notes,
            "gain_advice": cls.gain_advice,
        }