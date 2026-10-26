# The Differential: Diagnostic Microphones for Phonocardiography

Presented the way a differential should be: one complaint, five candidates,
each with findings, strengths, weaknesses, and a disposition. Every candidate
ships as a recording module in this repository (`better_stethoscope/recorders/`),
so the differential ends in runnable code, not just an opinion.

**Chief complaint.** Capture heart sounds — fundamentals at 20–150 Hz,
murmurs mostly 150–600 Hz, clicks and harmonics toward 2 kHz[14][15] — at
48 kHz / 24-bit on a Raspberry Pi, with quality good enough that a physician
can review the audio remotely and trust what they hear.

**History (requirements).**
* Flat or rising response through 20–100 Hz, where S1/S2 and the S3/S4
  gallops live;[14][16] sounds below 100 Hz are exactly the ones the human
  ear perceives worst, which is why they must be captured well.[16]
* Enough sensitivity that a chest-wall vibration becomes a usable signal
  without heroic gain.
* An interface the Pi can actually drive: USB (trivial), I2S (GPIO header),
  or line-in.
* A coupling scheme that seals an acoustic path from skin to sensor.

**Examination baseline (what commercial devices promise).** The Eko CORE 500
publishes a 20 Hz–2 kHz audio response with up to 40x amplification and 8x
active noise cancellation;[8][9] the Thinklabs One amplifies more than 100x
(>40 dB) through five bandpass filters onto a standard analog jack.[7][5]
Those are the targets a DIY front-end is measured against.

---

## Candidate 1 — Electret condenser capsule in stethoscope tubing

*Module: `electret`*

**Findings.** The dominant published DIY design: cut the stethoscope tube,
couple a ~5 cm length of ~6 mm inner-diameter tubing to the chestpiece stem,
insert a condenser capsule at the far end, and seal it — the sealed air
column is the acoustic coupling.[13] A peer-reviewed low-cost build used a
CMC-9745-44P electret capsule, an NE5532 op-amp stage, and a CM108B USB ADC
into a Raspberry Pi Zero 2 W, for a complete system around USD 25;[11] a
diaphragm-design study built a 3-D-printed, TPU-diaphragm electret
stethoscope for under USD 5, finding TPU the best of four materials for
noise suppression and signal fidelity;[12] the same coupling works with a
$7 USB lavalier microphone in place of a bare capsule.[22] These builds
record the S1/S2 band — 20–150 Hz — as their primary signal.[11][13][14]

**Strengths.** Genuine low-frequency reach (no published low corner the way
MEMS datasheets have); parts cost under a lunch; the donor chestpiece
carries Littmann-grade acoustics; a USB dongle supplies capsule bias power
directly.

**Weaknesses.** Modest capsule sensitivity — expect to run input gain near
maximum; no noise rejection, so room and handling noise pass straight
through; build variability (seal quality dominates).

**Disposition.** **The recommended DIY build.** Best value per decibel of
clinical fidelity; pairs with a Cardiology IV donor head.

---

## Candidate 2 — Piezo contact microphone (chest-wall vibration pickup)

*Module: `piezo`*

**Findings.** Piezo elements are capacitive: impedance rises as frequency
falls, so the sensor must work into high impedance — over 1 MΩ; a typical
50 kΩ line input forms an accidental ~200 Hz high-pass with typical
elements, and a 1.5 kΩ mic input a ~1 kHz high-pass that omits bass
entirely.[17] The fix is an impedance converter (buffer, DI box, or JFET
charge-amp),[17][19] available both as DIY circuits[19] and commercial
buffers. Bare discs also resonate between 2 and 6 kHz, lending a metallic
coloration.[17] Because they transduce vibration in solid material rather
than airborne sound, they inherently reject room noise.[17] A commercial
contact mic marketed for body sounds claims 8–2200 Hz bandwidth.[18]

**Strengths.** Structure-borne pickup ignores airborne room noise; nearly
unbreakable; tape-mountable for longer monitoring without a stethoscope head.

**Weaknesses.** The impedance trap is the single easiest way to silently
destroy the S1/S2 band — bass loss from a wrong input looks like a "thin
patient," not a wiring bug; resonance coloration; needs soldering or a DI
box.

**Disposition.** **Viable, with a mandatory buffer.** The easiest candidate
to build wrong; with a ≥1 MΩ buffer ahead of a line input it becomes a
respectable — and uniquely noise-proof — front-end.

---

## Candidate 3 — I2S MEMS microphone (INMP441 / SPH0645 / ICS-43434)

*Module: `mems_i2s`*

**Findings.** The INMP441 is a 24-bit digital-output MEMS mic with 61 dBA
SNR and a flat frequency response published as 60 Hz to 15 kHz; its low
corner (−3 dB point) is 60 Hz.[10] It speaks I2S directly to the Pi's PCM
peripheral — three data wires plus power — and the standard device-tree
overlay (`googlevoicehat-soundcard`) makes it appear as an ALSA capture
card;[20][21] where takes run quiet, the documented softvol "Boost" adds up
to +30 dB of capture gain.[20]

**Strengths.** All-digital path from diaphragm to disk: no analog pickup of
hum or USB noise; ~$5; 61 dBA SNR; no dongle; ideal for a sealed, compact
head.

**Weaknesses.** The published 60 Hz corner sits in the middle of the S1/S2
band (20–150 Hz):[10][14] everything below 60 Hz is rolled off, so S3/S4
gallops and the lowest fundamentals are attenuated; MEMS sensitivity is
fixed (softvol gain is digital, after the mic); the bare port still needs
tubing coupling for body sounds.

**Disposition.** **Best digital hygiene, weakest cardiac low-end.** Keep it
for rate, murmurs (150–600 Hz), and lung sounds; do not make it the primary
front-end when the clinical question is low-frequency gallops.

---

## Candidate 4 — Generic USB microphone / adapter

*Module: `usb_mic`*

**Findings.** Whatever USB mic or dongle is on hand enumerates through
PortAudio and records immediately; the classic hobbyist phonocardiogram
build is literally a $7 USB lavalier coupled into a stethoscope head with a
short tube.[22]

**Strengths.** Zero build; instant gratification; doubles as the ADC+power
layer for Candidate 1.

**Weaknesses.** Low-frequency response is unspecified and varies dongle to
dongle; gain staging is whatever the dongle's chipset provides; cheap units
inject USB-bus noise.

**Disposition.** **Fallback and bring-up path.** Use it to verify the
software end-to-end before the real front-end is built; keep it as the
match-anything module in the registry.

---

## Candidate 5 — Thinklabs One, line-level front-end (premium path)

*Module: `thinklabs`*

**Findings.** The One is an FDA-cleared digital stethoscope built around a
patented Electromagnetic Diaphragm, five bandpass filters, and more than
100x (>40 dB) of amplification, driving a 3 V peak-to-peak low-impedance
headphone output on a 4-conductor 3.5 mm jack.[7] Because it has a direct
analog audio output, "it operates as an external microphone for any system.
No SDK, special software, or API is required."[7] In practice: one cable
from the One's jack into a USB adapter's **line input** on the Pi, and the
recording chain is complete.

**Strengths.** Reference-grade transducer and preamp with volume-knob gain
staging; nothing to build; the S1/S2 low band is this device's design
center; recordings play back on ordinary headphones.

**Weaknesses.** Cost (roughly an order of magnitude above the DIY
candidates[unverified] — check current pricing); its on-device filters
should be left on the default so this pipeline receives the least-colored
signal.

**Disposition.** **The premium answer.** If a commercial front-end is on the
table, this is the one the Pi can ingest directly.

---

## Comparators seen on the market (not Pi front-ends)

* **Eko CORE 500** — 20 Hz–2 kHz response, 40x amplification, 8x active
  noise cancellation, 3-lead ECG, FDA-cleared AI features;[8][9] it couples
  over Bluetooth to Eko's app ecosystem rather than exposing an analog jack,
  so it cannot feed the Pi directly. Recordings exported from the Eko
  ecosystem can still be graded by this project's `analyze` command.
* **Littmann CORE Digital** — the analog-hybrid stethoscope pairing
  Littmann mechanics with Eko electronics (up to 40x amplification,
  connectivity to Eko software);[2] same closed-ecosystem caveat.

---

## Summary table

| Candidate | 20–100 Hz fidelity | Noise behavior | Coupling effort | Pi interface | Cost | Rank |
|---|---|---|---|---|---|---|
| Thinklabs One (`thinklabs`) | reference-grade | commercial preamp | none (line cable) | USB adapter line-in | ~$500 class | **1 — premium** |
| Electret in tubing (`electret`) | excellent (sealed column) | needs quiet room | cut + seal tube | CM108 dongle mic-in | ~$10–15 + donor scope | **1 — value** |
| Piezo + buffer (`piezo`) | good only with ≥1 MΩ buffer | rejects airborne noise | tape to chest | buffered interface line-in | ~$20–40 | **3 — conditional** |
| I2S MEMS (`mems_i2s`) | rolled off below 60 Hz | very low (digital path) | tubing over port | GPIO I2S + overlay | ~$5–10 | **4 — band-limited** |
| Generic USB (`usb_mic`) | unspecified | varies | tubing optional | USB | varies | **5 — bring-up** |

## Final assessment

For the stated complaint — physician-reviewable heart-sound recordings from
a Raspberry Pi — the differential resolves to:

1. **If a commercial device is acceptable:** Thinklabs One into line-in.
   One cable, reference quality, no engineering risk.[7]
2. **If this is a build:** electret capsule sealed into a Littmann Cardiology
   IV's tubing with a CM108 dongle — the peer-reviewed low-cost
   architecture,[11][13] at roughly 5% of the premium path's cost.
3. **Piezo only with a proper buffer** — the impedance trap is the
   diagnosis to rule out before trusting any piezo take.[17]
4. **MEMS with eyes open:** excellent murmur/lung capture, published 60 Hz
   low corner,[10] weakest for S3/S4 gallops.
5. **Generic USB for bring-up,** then retire it.

All five ship as modules behind one interface (`better_stethoscope devices`
lists what is plugged in); the quality gate grades every take the same way
regardless of front-end, so the differential can be re-argued empirically:
record the same patient through two candidates and compare spectrograms.

---

## Sources

[2] https://www.littmann.com/content/dam/public/language-masters/en/msb/document/2024/littmann-comparison-chart-ms-st-en-cmyk-print.pdf
[5] https://www.thinklabs.com/technical-specs
[7] https://www.eumaco.it/content/uploads/2017/08/Thinklabs-One-Brochure-lite3.2.pdf
[8] https://www.ekohealth.com/products/core-500-digital-stethoscope
[9] https://www.praxisdienst.com/be-en/produit/eko-core-500/ex-150457
[10] https://product.tdk.com/system/files/dam/doc/product/sw_piezo/mic/mems-mic/data_sheet/inmp441.pdf
[11] https://pmc.ncbi.nlm.nih.gov/articles/PMC10007545
[12] https://pmc.ncbi.nlm.nih.gov/articles/PMC12363398
[13] https://journals.physiology.org/doi/full/10.1152/advan.00073.2012
[14] https://www.mdpi.com/1424-8220/26/9/2580
[15] https://pmc.ncbi.nlm.nih.gov/articles/PMC6515005
[16] https://ia800603.us.archive.org/12/items/EvidenceBasedPhysicalDiagnosis/39AuscultationOfTheHeartGeneralPrinciples.pdf
[17] https://knowledge.lom.audio/research/contact-mics
[18] https://contactmicrophones.com/index.html
[19] https://zachpoff.com/resources/alex-rice-piezo-preamplifier
[20] https://cdn-learn.adafruit.com/downloads/pdf/adafruit-i2s-mems-microphone-breakout.pdf
[21] https://electricalflux.com/mcu-projects/i2s-mems-microphone-raspberry-pi-inmp441-setup
[22] https://www.nutsvolts.com/magazine/article/build-a-diy-heart-sound-analyzer-using-your-laptop
