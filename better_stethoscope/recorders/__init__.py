"""Recorder module registry: lazy, forgiving, self-reporting.

Every microphone front-end is a module in this package with a BaseRecorder
subclass. The registry imports them lazily and tolerates any that are
missing or broken (development machine without the hardware, sounddevice
unavailable, a half-written module mid-edit): ``available()`` returns what
works and ``errors()`` says why the rest did not.

WHY lazy imports: the Pi image may lack libportaudio2, or a new module may
be mid-development. The CLI must still run, list what it can, and explain
what it cannot.
"""

from __future__ import annotations

from importlib import import_module
from typing import Optional

from .base import BaseRecorder

# Ordered list of front-end modules. The generic usb_mic is last among the
# specific matches in CLI listings (it matches almost anything).
MODULE_NAMES = (
    "thinklabs",   # commercial digital stethoscope -> line-in
    "electret",    # DIY capsule-in-tubing (the $5 build)
    "piezo",       # contact mic through a high-Z buffer
    "mems_i2s",    # INMP441/SPH0645 on the Pi's I2S bus
    "usb_mic",     # generic fallback: any USB mic/adapter
)

_cache: dict[str, type[BaseRecorder]] = {}
_errors: dict[str, str] = {}


def _find_recorder_class(module) -> Optional[type]:
    """The BaseRecorder subclass *defined in* this module (not imported)."""
    for obj in vars(module).values():
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseRecorder)
            and obj is not BaseRecorder
            and obj.__module__ == module.__name__
        ):
            return obj
    return None


def available() -> dict[str, type[BaseRecorder]]:
    """slug -> class for every module that imports cleanly.

    Modules that failed before are retried on each call -- cheap, and it
    means a module written after the process started starts working without
    a restart.
    """
    for name in MODULE_NAMES:
        if name in _cache:
            continue
        try:
            module = import_module(f".{name}", __package__)
            cls = _find_recorder_class(module)
            if cls is None:
                _errors[name] = "module defines no BaseRecorder subclass"
                continue
            if not getattr(cls, "slug", ""):
                _errors[name] = "recorder class has an empty slug"
                continue
            _cache[name] = cls
            _errors.pop(name, None)
        except Exception as exc:  # noqa: BLE001 - report, don't crash
            _errors[name] = f"{type(exc).__name__}: {exc}"
    return dict(_cache)


def errors() -> dict[str, str]:
    """module -> why it is unavailable (empty when everything loaded)."""
    available()  # refresh
    return dict(_errors)


def get(slug: str) -> type[BaseRecorder]:
    """Look up a recorder class by slug; KeyError names the valid slugs."""
    classes = available()
    if slug in classes:
        return classes[slug]
    raise KeyError(
        f"unknown recorder module '{slug}'. Available: {', '.join(sorted(classes)) or '(none)'}"
    )


def all_devices() -> list[dict]:
    """Every discovered device across every available module, merged.

    The generic module's fallback match-all entries go last so specific
    front-ends are presented first for the same hardware.
    """
    devices: list[dict] = []
    for slug, cls in available().items():
        for dev in cls.discover():
            devices.append(dev)
    return devices