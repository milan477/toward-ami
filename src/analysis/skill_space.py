"""Continuous skill-space map of focused music-understanding skills.

Axes
----
x (0-3): Cognitive Processing Spectrum — Perceptual → Inferential → Affective → Contextual
y (0-1): Signal Scope — Tone → Time, with a thin SPEECH band at the very top.
         Speech is treated as its own narrow region (lyrics / sung words),
         separate from the temporal (Time) axis of the music itself.

Skills are broken into precisely focused units (e.g. pitch vs. melody, tempo vs.
rhythmic pattern) rather than broad tasks. Non-music sound-scene skills from the
raw benchmark taxonomies (material/tool-surface/causal sound, etc.) are dropped.
"""

from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patheffects as pe

OUT = Path(__file__).resolve().parents[2] / "paper" / "figures"

x_min, x_max = 0.0, 3.0
y_min, y_max = 0.0, 1.0
SPEECH_FLOOR = 0.86          # everything above this is the thin speech band

# ----------------------------
# Canvas
# ----------------------------
fig, ax = plt.subplots(figsize=(16, 9))

# ----------------------------
# Embellished background color field (vivid HSV)
# hue: red → blue across the cognitive spectrum; value: bright (tone) → deep (time)
# The speech band is desaturated + deepened so it reads as its own region.
# ----------------------------
nx, ny = 600, 400
X, Y = np.meshgrid(np.linspace(x_min, x_max, nx), np.linspace(y_min, y_max, ny))

H = 0.03 + (X / 3.0) * 0.60                 # 0.03 (red) → 0.63 (blue/violet)
S = 0.82 - 0.15 * np.sin(np.pi * X / 3.0)   # slightly richer at the ends
V = 0.97 - 0.42 * (Y / SPEECH_FLOOR).clip(0, 1)

speech = Y >= SPEECH_FLOOR
S = np.where(speech, S * 0.28, S)           # desaturate the speech band
V = np.where(speech, 0.40, V)               # and deepen it

background = mcolors.hsv_to_rgb(np.dstack([H, S, V]))
ax.imshow(background, origin="lower", extent=[x_min, x_max, y_min, y_max],
          aspect="auto", zorder=0, interpolation="bilinear")

# speech-band divider + label
ax.axhline(SPEECH_FLOOR, color="white", lw=1.2, ls=(0, (6, 4)), alpha=0.7, zorder=1)
ax.text(x_max - 0.02, (SPEECH_FLOOR + 1.0) / 2, "SPEECH", ha="right", va="center",
        fontsize=13, fontweight="bold", color="white", alpha=0.85, zorder=1)

# ----------------------------
# Focused skills:  (name, x, y)
# ----------------------------
skills = [
    # ---- Perceptual · low-level acoustic (Tone → Time) ----
    ("Pitch Identification", 0.10, 0.06),
    ("Melody Identification", 0.30, 0.12),
    ("Polyphonic Pitch Estimation", 0.14, 0.20),
    ("Timbre Perception", 0.12, 0.34),
    ("Instrument Identification", 0.40, 0.28),
    ("Dynamics / Loudness Perception", 0.28, 0.44),
    ("Spatial / Stereo Perception", 0.12, 0.52),
    ("Source Separation", 0.50, 0.56),
    ("Onset Detection", 0.28, 0.62),
    ("Beat Tracking", 0.14, 0.70),
    ("Tempo Estimation", 0.33, 0.76),
    ("Downbeat Tracking", 0.52, 0.71),

    # ---- Inferential · trained analysis ----
    ("Key Detection", 0.64, 0.14),
    ("Melodic Contour / Motif Analysis", 0.70, 0.24),
    ("Chord Recognition", 0.66, 0.34),
    ("Harmonic Progression Analysis", 0.92, 0.42),
    ("Automatic Music Transcription", 0.78, 0.50),
    ("Structural Segmentation / Form", 1.05, 0.60),
    ("Meter / Time-Signature Analysis", 0.80, 0.68),
    ("Rhythmic Pattern Analysis", 1.05, 0.77),
    ("Query by Humming", 1.18, 0.32),
    ("Cover Song Identification", 1.26, 0.22),
    ("Score–Performance Alignment", 1.32, 0.66),

    # ---- Affective · subjective (labels flip left into open middle) ----
    ("Mood / Emotion Recognition", 1.66, 0.40),
    ("Expressive / Aesthetic Character", 1.86, 0.54),

    # ---- Contextual · world knowledge & retrieval (labels flip left) ----
    ("Cross-Modal Retrieval", 2.40, 0.16),
    ("Music Recommendation", 2.80, 0.24),
    ("Music Similarity & Retrieval", 2.14, 0.30),
    ("Artist Identification", 2.60, 0.32),
    ("Music Question Answering", 2.97, 0.40),
    ("Genre Classification", 2.28, 0.44),
    ("Music Captioning / Description", 2.88, 0.50),
    ("Style / Era Recognition", 2.54, 0.57),
    ("Music Auto-Tagging", 2.30, 0.63),
    ("Musicological Knowledge", 2.72, 0.69),

    # ---- SPEECH band (thin, top) ----
    ("Singing-Voice Detection", 0.30, 0.90),
    ("Lyrics Transcription", 0.62, 0.93),
    ("Lyrics Alignment", 0.98, 0.90),
    ("Lyrical Content Analysis", 2.80, 0.93),
]

# Skills removed as non-music sound-scene tasks (kept here for the record):
DROPPED = [
    "Material Sound Recognition", "Tool–Surface Detection", "Causal Inference from Sound",
    "Audio Perspective Inference", "Auditory Quantity Estimation", "Rhythm-to-Word Mapping",
]

_halo = [pe.withStroke(linewidth=2.2, foreground="black")]

for name, px, py in skills:
    ax.scatter(px, py, s=130, facecolor="white", edgecolor="black",
               linewidth=1.3, zorder=5)
    if px > 2.35:
        ax.text(px - 0.035, py, name, ha="right", va="center", color="white",
                fontsize=8.8, fontweight="bold", zorder=6, path_effects=_halo)
    else:
        ax.text(px + 0.035, py, name, ha="left", va="center", color="white",
                fontsize=8.8, fontweight="bold", zorder=6, path_effects=_halo)

# ----------------------------
# Axes & labels
# ----------------------------
ax.set_xlim(x_min, x_max)
ax.set_ylim(y_min, y_max)
ax.set_xticks([0, 1, 2, 3])
ax.set_xticklabels(["Perceptual", "Inferential", "Affective", "Contextual"], fontsize=11)
ax.set_yticks([0.0, 0.43, 0.75, 0.93])
ax.set_yticklabels(["Tone", "Mixed", "Time", "Speech"], fontsize=11)
ax.set_xlabel("Cognitive Processing Spectrum", fontsize=13)
ax.set_ylabel("Signal Scope:  Tone → Time  |  Speech", fontsize=13)
ax.set_title("Focused Music-Understanding Skill Space", fontsize=15)
ax.grid(False)
plt.tight_layout()

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"skill_space.{ext}", dpi=150, bbox_inches="tight")
    print(f"Saved skill_space.pdf / .png to {OUT}  ({len(skills)} skills, "
          f"{len(DROPPED)} dropped)")
