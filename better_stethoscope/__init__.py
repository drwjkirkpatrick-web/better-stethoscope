"""better-stethoscope: high-quality heart-sound recording for Raspberry Pi.

The package turns a Raspberry Pi into a phonocardiogram (PCG) recorder:

* ``better_stethoscope.recorders``  -- one module per candidate microphone
  front-end (USB mic, DIY electret-in-tubing, piezo contact mic, I2S MEMS,
  Thinklabs One line-in), all sharing a common BaseRecorder contract.
* ``filters`` / ``quality``        -- the DSP core: band-pass filtering tuned
  to the 20-2000 Hz heart-sound band, envelope extraction, BPM estimation,
  and an automatic "is this take usable?" quality gate.
* ``session`` / ``report``         -- guided 5-position auscultation sessions,
  saved as 24-bit WAV + FLAC with spectrograms, packaged into a zip that is
  ready to send to a physician for review.
* ``cli``                          -- ``python -m better_stethoscope`` drives
  everything from the terminal.

NOTE: This is a research/telehealth aid, not a medical device. A licensed
physician must review every recording; the software never diagnoses.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]