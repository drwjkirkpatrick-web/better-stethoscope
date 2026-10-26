# Raspberry Pi Setup Guide

Everything needed to go from a bare Raspberry Pi OS (Bookworm) install to a
working, quality-gated heart-sound recorder. Tested design targets: Pi 4,
Pi 5, and Pi Zero 2 W (any board with a 40-pin header; USB front-ends also
work on Zero-class boards, the I2S module needs the GPIO header).

## 1. OS packages and install

```bash
sudo apt update
sudo apt install -y libportaudio2     # required by sounddevice
sudo apt install -y alsa-utils        # arecord / alsamixer for gain + tests

git clone https://github.com/drwjkirkpatrick-web/better-stethoscope.git
cd better-stethoscope
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Verify the software pipeline with no hardware at all:

```bash
.venv/bin/python -m better_stethoscope demo
```

Expected: `install OK: DSP + quality gate verified` and a ~72 bpm verdict on
the synthetic train.

## 2. Pick your front-end

Five modules ship with the project (full trade-off analysis in
[microphone-differential.md](microphone-differential.md)):

| Module | Hardware | Build cost | Low-freq (20–100 Hz) | Difficulty |
|---|---|---|---|---|
| `electret` | electret capsule in stethoscope tubing + CM108 USB dongle | ~$10–15 + donor scope | excellent | low |
| `thinklabs` | Thinklabs One -> 3.5 mm -> USB adapter LINE IN | ~$500 (One) + $8 | excellent (commercial grade) | trivial |
| `piezo` | piezo disc + high-Z buffer -> interface line-in | ~$20–40 | good ONLY if buffered | medium |
| `mems_i2s` | INMP441/SPH0645 on GPIO I2S | ~$5–10 | fair (60 Hz corner) | medium |
| `usb_mic` | any USB mic/adapter (fallback) | varies | varies | trivial |

### 2a. Electret-in-tubing build (recommended DIY path)

Parts: any acoustic stethoscope to donate (Littmann Cardiology IV
recommended — see [research-acoustic-stethoscope.md](research-acoustic-stethoscope.md)),
a small electret capsule (a $2 lavalier capsule or bare CMC-9745-44P-style
capsule), a C-Media CM108(B) USB sound dongle, ~5 cm of tubing that fits the
stethoscope stem (often the scope's own cut tube works).

1. Cut the tubing about 5 cm from the chestpiece stem. Published builds use
   a ~5 cm length of ~6 mm inner-diameter tubing between the stem and the
   capsule.[13]
2. Insert the capsule into the free end of the tube; heat the tube gently or
   seal with silicone so the capsule is airtight at the tube mouth — the
   sealed air column IS the acoustic coupling.[11][13] The same approach works
   with a $7 USB lavalier microphone instead of a bare capsule.[22]
3. Plug the dongle into the Pi, then set capture gain:
   `alsamixer` -> F4 (capture) -> raise to ~2/3 (start near max if quiet).
4. Test: `arecord -D plughw:1,0 -f S32_LE -r 48000 -c1 -t wav test.wav`

If takes are too quiet even at max gain, published builds add an op-amp
stage (e.g., NE5532) between capsule and ADC — that is the $25 total
system a peer-reviewed build used with a Pi Zero 2 W.[11]

### 2b. Thinklabs One (premium path)

Connect the One's 3.5 mm output to a USB adapter's **LINE IN** (not the mic
input — the One already amplifies >100x and outputs ~3 V peak-to-peak into a
low-impedance headphone driver).[7] Set the One's volume to 2–4 on its 1–10
scale, watch the `monitor` bar, and adjust so peaks land between roughly
−25 and −12 dBFS.

### 2c. Piezo contact mic (the impedance trap)

A bare piezo disc into an ordinary input sounds tinny and loses the entire
S1/S2 band: piezo elements need to work into high impedance (>1 MΩ); a
typical 50 kΩ line input forms an accidental ~200 Hz high-pass and a 1.5 kΩ
mic input a ~1 kHz high-pass.[17] ALWAYS put a buffer / DI box / JFET
charge-amp between disc and input.[17][19] Tape the (shielded) disc flat to
the chest with medical tape; expect some 2–6 kHz metallic coloration from
disc resonance.[17]

### 2d. I2S MEMS (INMP441 / SPH0645 / ICS-43434)

Wire the mic module to the Pi's header (values from the Adafruit I2S
guide[20]; same mapping documented for the INMP441[21]):

| Mic pin | Pi pin | GPIO |
|---|---|---|
| 3V | pin 1 | 3.3 V |
| GND | pin 6 | GND |
| BCLK/SCK | pin 12 | GPIO 18 |
| LRCL/WS | pin 35 | GPIO 19 |
| DOUT/SD | pin 38 | GPIO 20 |
| L/R | pin 6 | GND (left channel) |

Enable the overlay:

```
# /boot/firmware/config.txt   (Bookworm; older OS: /boot/config.txt)
dtparam=i2s=on
dtoverlay=googlevoicehat-soundcard
```

Reboot, confirm with `arecord -l` (expect `snd_rpi_i2s_card`), then:

```bash
arecord -D plughw:1,0 -c1 -r 48000 -f S32_LE -t wav test.wav
```

Know the limitation: the INMP441's flat band starts at 60 Hz (its published
−3 dB low corner), so S1/S2 fundamentals below 60 Hz are attenuated — fine
for rate and murmurs, weakest of the five for low-frequency fidelity.[10]
For quiet subjects, the Adafruit softvol recipe adds a "Boost" capture
control of up to +30 dB on this card.[20]

## 3. First real recording session

```bash
.venv/bin/python -m better_stethoscope devices     # confirm module + device
.venv/bin/python -m better_stethoscope monitor     # live meter + bpm; set placement
.venv/bin/python -m better_stethoscope session --label chart-114
```

The guided session walks the five classic positions (aortic -> pulmonic ->
Erb's point -> tricuspid -> mitral), records 15 s per position, prints the
quality verdict after each take, and finally writes:

```
recordings/2026-08-26_101530/            session directory (WAV masters live here)
    20260826_101530_mitral.wav
    ...
    metadata.json / SUMMARY.txt
recordings/2026-08-26_101530_physician_packet.zip   <- send this
```

Single take instead of full session:

```bash
.venv/bin/python -m better_stethoscope record --position mitral --seconds 20
```

Post-hoc analysis of any WAV (including files exported from other devices):

```bash
.venv/bin/python -m better_stethoscope analyze recording.wav --figures
```

## 4. Recording hygiene (cheap, high-yield)

* Run the Pi on battery (power bank) — wall warts inject hum and whine.
* Quiet room, patient still, cable off the patient's skin and clothing.
* Firm chestpiece contact for a sealed diaphragm; watch `monitor` and aim
  for −25 to −12 dBFS peaks.
* 15–20 s per position; longer takes give the rhythm estimate confidence.
* Never put patient audio in email — use the patient portal or an encrypted
  drive; the packet zip is ready as-is.

## 5. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `sounddevice` import error | missing PortAudio | `sudo apt install libportaudio2` |
| no devices in `devices` | dongle in wrong port / overlay missing | replug; check `arecord -l`; re-check `config.txt` |
| takes always "quiet" | gain staging | raise alsamixer capture; electret: near max |
| takes clipped | gain too hot | back off OS gain or the One's volume knob |
| constant hum | mains/USB power | battery power; try the 60 Hz notch in filters |
| MEMS signal noisy/harsh | L/R pin floating | tie L/R to GND (left channel) [20][21] |

---

## Sources

[7] https://www.eumaco.it/content/uploads/2017/08/Thinklabs-One-Brochure-lite3.2.pdf
[10] https://product.tdk.com/system/files/dam/doc/product/sw_piezo/mic/mems-mic/data_sheet/inmp441.pdf
[11] https://pmc.ncbi.nlm.nih.gov/articles/PMC10007545
[13] https://journals.physiology.org/doi/full/10.1152/advan.00073.2012
[17] https://knowledge.lom.audio/research/contact-mics
[19] https://zachpoff.com/resources/alex-rice-piezo-preamplifier
[20] https://cdn-learn.adafruit.com/downloads/pdf/adafruit-i2s-mems-microphone-breakout.pdf
[21] https://electricalflux.com/mcu-projects/i2s-mems-microphone-raspberry-pi-inmp441-setup
[22] https://www.nutsvolts.com/magazine/article/build-a-diy-heart-sound-analyzer-using-your-laptop
