#!/usr/bin/env python3
""" McDonald's table pet custom state set runner: reuse the hatch-pet deterministic pipeline,
   injecting the desktop pet's exclusive 9-state animation contract (replacing Codex's default state set).

   Usage: python tools/prepare_mcd_run.py
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_SCRIPTS = Path(r"C:\Users\<你的用户名>\.workbuddy\skills\hatch-pet\scripts")
sys.path.insert(0, str(SKILL_SCRIPTS))

import prepare_pet_run as prep  # noqa: E402

# ---------------------------------------------------------------- Desktop pet state set
# The atlas remains 8 columns x 9 rows, 192x208 cells, fully compatible with the downstream deterministic pipeline.
ROWS = [
    ("idle", 0, 6, "calm resting, breathing and blinking loop"),
    ("eating", 1, 8, "generic no-prop eating motion; food sprite is composited by the player"),
    ("drinking", 2, 6, "generic no-prop straw-sipping motion; drink sprite is composited by the player"),
    ("sleeping", 3, 8, "stretch then curl up and sleep with slow breathing"),
    ("litter", 4, 8, "crouch and rake-bury motion; litter box composited by the player"),
    ("happy", 5, 6, "celebration for a successful order"),
    ("sad", 6, 6, "disappointed reaction for a cancelled order"),
    ("running-right", 7, 8, "side-view walking loop facing right"),
    ("running-left", 8, 8, "side-view walking loop facing left (mirrored from running-right)"),
]

STATE_PROMPTS = {
    "idle": (
        "Calm low-distraction resting loop: subtle breathing, tiny blink, slight head/body bob, "
        "very small tail sway. The Santa hat stays perfectly still on the head."
    ),
    "eating": (
        "Generic eating loop with NO food visible anywhere: the head dips slightly toward an invisible "
        "bite point just in front of the mouth, mouth opens, cheeks chew side to side, throat gulps, "
        "then a brief satisfied eye-close. Head and mouth anchor position must stay consistent across "
        "all frames so a food sprite can be overlaid at the mouth during playback."
    ),
    "drinking": (
        "Straw-sipping loop with NO cup and NO straw visible anywhere: head tilts slightly down toward "
        "an invisible sip point, cheeks draw in gently, a small swallow bob in the throat, then a "
        "refreshed eye-close. Mouth anchor position consistent across all frames so a drink sprite can "
        "be overlaid during playback."
    ),
    "sleeping": (
        "Sleepy loop: one long luxurious stretch with front paws extended and back arched, then curling "
        "down into a round cozy sleeping ball with closed eyes, then slow visible breathing rise and "
        "fall while asleep. Snoring is conveyed only through the breathing motion."
    ),
    "litter": (
        "Litter-burying motion loop with NO litter box, NO sand and NO particles visible: crouching low "
        "beside an invisible spot, one front paw scooping toward the body and raking beside it, a short "
        "pause, then a second raking motion, head looking down toward the digging spot. The digging "
        "spot stays anchored at the same position across frames so a litter box sprite can be placed "
        "there during playback."
    ),
    "happy": (
        "Celebration loop: both front paws raised up, a small happy bounce, bright eyes and a cheerful "
        "open mouth, like celebrating a successful order."
    ),
    "sad": (
        "Disappointed loop: ears droop, head lowers, body slumps slightly, eyes look down, like an "
        "order was cancelled. Keep it cute and gentle, never dramatic."
    ),
    "running-right": (
        "Side-view walking loop facing and traveling to the right: alternating front and back paw steps "
        "with clearly visible cadence, relaxed tail sway, steady body height."
    ),
    "running-left": (
        "Side-view walking loop facing and traveling to the left: alternating front and back paw steps "
        "with clearly visible cadence, relaxed tail sway, steady body height."
    ),
}

STATE_REQUIREMENTS = {
    "idle": [
        "CRITICAL: idle is the low-distraction baseline state and the first frame is also used as the reduced-motion static pet.",
        "Use only subtle idle motion: gentle breathing, a tiny blink, a slight head or body bob, or a very small tail sway.",
        "Keep the pet essentially in the same pose, facing direction, silhouette, markings, palette and hat across all 6 frames.",
        "Idle variation must stay calm but still read as animation; do not repeat effectively identical copies across the loop.",
        "Do not show eating, drinking, walking, sleeping, digging, celebrating, or any item interaction or new prop.",
        "Feet and body anchor remain planted; the first and last frames should be very close visually.",
    ],
    "eating": [
        "CRITICAL: absolutely NO food, no burger, no fries, no drink, no cup, no straw, no plate, no crumbs, no particles anywhere in any frame.",
        "The eating motion is performed toward an invisible bite point just in front of the mouth.",
        "Keep the head angle, mouth anchor position and body position consistent across all frames.",
        "Show eating through mouth opening, cheek chewing, throat gulp and satisfied eye-close only.",
        "No detached effects, no sparkle, no motion marks, no hearts, no music notes.",
    ],
    "drinking": [
        "CRITICAL: absolutely NO cup, no straw, no can, no glass, no liquid, no droplets anywhere in any frame.",
        "The sipping motion is performed toward an invisible sip point just in front of the mouth.",
        "Keep the head angle, mouth anchor position and body position consistent across all frames.",
        "Show drinking through cheek draw-in, swallow bob and refreshed eye-close only.",
        "No detached effects, no sparkle, no motion marks, no hearts, no music notes.",
    ],
    "sleeping": [
        "CRITICAL: no Z-Z-Z letters, no text, no speech bubbles, no thought bubbles, no music notes anywhere.",
        "Snoring and sleep are conveyed only through closed eyes and slow body breathing rise and fall.",
        "The stretch phase and the curled sleeping phase must keep the same palette, markings and hat.",
        "No pillow, no blanket, no bed, no new props.",
    ],
    "litter": [
        "CRITICAL: no litter box, no sand, no grains, no particles, no droppings, no smell waves anywhere in any frame.",
        "Show only the cat's own crouching and front-paw scooping and raking motions beside an invisible spot.",
        "Keep the invisible digging spot anchored at the same ground position across all frames.",
        "Keep the motion comedic and cute, never gross or explicit.",
        "No detached dust clouds or smell marks.",
    ],
    "happy": [
        "Show celebration through raised paws, a small bounce and a bright open-mouth smile only.",
        "No confetti, no stars, no sparkles, no floating symbols, no motion arcs.",
        "Keep the hat, markings and silhouette identical to the canonical base.",
    ],
    "sad": [
        "Show disappointment through drooping ears, lowered head, slumped body and downward eyes only.",
        "Small attached tears at the eye corner are allowed only if opaque and overlapping the face; no falling droplets.",
        "No rain clouds, no detached symbols, no slumped posture so extreme that the silhouette breaks.",
    ],
    "running-right": [
        "Side view facing right with alternating paw steps; the cadence must visibly alternate across the loop.",
        "Do not draw speed lines, dust clouds, floor shadows, motion trails or detached motion effects.",
        "Do not show the pet facing left or standing still.",
    ],
    "running-left": [
        "Side view facing left with alternating paw steps; the cadence must visibly alternate across the loop.",
        "Do not draw speed lines, dust clouds, floor shadows, motion trails or detached motion effects.",
        "Do not show the pet facing right or standing still.",
    ],
}


def main() -> None:
    prep.ROWS = ROWS
    prep.STATE_PROMPTS = STATE_PROMPTS
    prep.STATE_REQUIREMENTS = STATE_REQUIREMENTS

    project = Path(__file__).resolve().parent.parent
    reference = Path(
        r"C:\Users\<你的用户名>\.workbuddy\clipboard-images\clipboard-2026-10-09T07-42-24-833Z-110f5bc5.png"
    )

    sys.argv = [
        "prepare_pet_run.py",
        "--pet-name", "麦麦猫",
        "--pet-id", "mcd-maimai",
        "--display-name", "麦麦猫",
        "--description",
        "A chunky orange-and-white tabby cat in a tiny red Santa hat who lives inside the McDonald's "
        "ordering assistant: it eats whatever you order, gets a little rounder after each meal, and "
        "celebrates, naps and buries its business on command.",
        "--reference", str(reference),
        "--output-dir", str(project / "run"),
        "--style-preset", "3d-toy",
        "--style-notes",
        "glossy vinyl 3D toy figure look with soft baked-in shading and no cast shadows; chubby rounded "
        "proportions; orange tabby body with white muzzle, chest and paws; tiny red Santa hat with white "
        "trim kept in every frame; big round amber eyes; same identity, palette and materials across all rows",
        "--force",
    ]

    prep.main()


if __name__ == "__main__":
    main()
