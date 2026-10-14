#!/usr/bin/env python3
"""Maakt automatisch een tribute edit van losse clips + een liedje.

Mappen (zet je bestanden hierin, op volgorde van bestandsnaam):
  clips/1_leuk/   leuke momenten van Pangi   -> kleur, kort geknipt op de beat
  clips/2_dood/   hoe hij doodging           -> zwart-wit, vertraagd
  clips/3_rouw/   mensen die rouwen (Knol..) -> zwart-wit, langer in beeld
  muziek/         precies 1 liedje (mp3/m4a/wav)

Alle clips worden gedempt; alleen het liedje is te horen.
Gebruik: python3 maak_edit.py   ->  pangi_edit.mp4
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

W, H, FPS = 1080, 1920, 30
FONT = "/usr/share/fonts/opentype/inter/Inter-Light.otf"
BOLD = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
ROOT = Path(__file__).resolve().parent
TMP = ROOT / "tmp_edit"
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac"}


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def duur(pad):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(pad)],
        check=True, capture_output=True, text=True).stdout
    return float(json.loads(out)["format"]["duration"])


def beat_lengte(liedje):
    """Schat de tijd tussen twee beats (s) uit de energie van het liedje."""
    sr = 11025
    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(liedje), "-t", "90", "-ac", "1", "-ar", str(sr),
         "-f", "f32le", "-"], check=True, capture_output=True).stdout
    x = np.frombuffer(pcm, dtype=np.float32)
    hop = 256
    n = len(x) // hop
    if n < 100:
        return 0.5
    energie = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    onset = np.maximum(np.diff(energie), 0)
    onset -= onset.mean()
    ac = np.correlate(onset, onset, "full")[len(onset) - 1:]
    fps = sr / hop
    lo, hi = int(fps * 60 / 180), int(fps * 60 / 60)  # 60-180 BPM
    lag = lo + int(np.argmax(ac[lo:hi]))
    beat = lag / fps
    while beat < 0.4:  # snelle nummers: knip op elke 2e beat
        beat *= 2
    return beat


def bestanden(map_, ext):
    p = ROOT / map_
    return sorted(f for f in p.iterdir() if f.suffix.lower() in ext) if p.exists() else []


def tekst(t, font, size, y="(h-text_h)/2"):
    t = t.replace("'", "’").replace(":", "\\:")
    return (f"drawtext=fontfile={font}:text='{t}':fontsize={size}:fontcolor=white:"
            f"x=(w-text_w)/2:y={y}:shadowcolor=black@0.6:shadowx=3:shadowy=3")


def segment(bron, start, lengte, uit, zw=False, traag=1.0, onderschrift=None):
    """Knipt een stuk uit een clip, verticaal met wazige achtergrond, zonder geluid."""
    bronlengte = lengte * traag
    kleur = ",hue=s=0,eq=contrast=1.1:brightness=-0.03" if zw else ",eq=saturation=1.1"
    fg = f"scale={W}:-2,setsar=1{kleur}"
    bg = f"scale=-2:{H},crop={W}:{H},boxblur=25:2{kleur},eq=brightness=-0.15"
    vf = (f"[0:v]setpts={1 / traag}*(PTS-STARTPTS),split[a][b];[a]{bg}[bg];[b]{fg}[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS},vignette=PI/5")
    if onderschrift:
        vf += "," + tekst(onderschrift, FONT, 58, "h-420")
    vf += f",fade=t=in:d=0.15,fade=t=out:st={lengte - 0.15}:d=0.15,format=yuv420p[v]"
    run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{bronlengte:.3f}", "-i", str(bron),
         "-filter_complex", vf, "-map", "[v]", "-an", "-t", f"{lengte:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), str(uit)])


def kaart(regels, lengte, uit):
    """Zwart tekstscherm. regels = [(tekst, font, grootte, y), ...]"""
    vf = ",".join(tekst(*r) for r in regels)
    vf += f",fade=t=in:d=0.8,fade=t=out:st={lengte - 0.8}:d=0.8,format=yuv420p"
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x0a0a0a:s={W}x{H}:r={FPS}:d={lengte}",
         "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(uit)])


def main():
    liedjes = bestanden("muziek", AUDIO_EXT)
    leuk = bestanden("clips/1_leuk", VIDEO_EXT)
    dood = bestanden("clips/2_dood", VIDEO_EXT)
    rouw = bestanden("clips/3_rouw", VIDEO_EXT)
    if not liedjes or not (leuk or dood or rouw):
        sys.exit("Zet 1 liedje in muziek/ en clips in clips/1_leuk, clips/2_dood, clips/3_rouw")
    liedje = liedjes[0]
    beat = beat_lengte(liedje)
    print(f"Liedje: {liedje.name}  (~{60 / beat:.0f} BPM, knip elke {beat:.2f}s)")

    TMP.mkdir(exist_ok=True)
    stukken, i = [], 0

    def nieuw():
        nonlocal i
        i += 1
        return TMP / f"{i:03d}.mp4"

    # Intro: 4 beats-ish
    p = nieuw()
    kaart([("CREATOR SMP 4", FONT, 64, "(h-text_h)/2-70"), ("PANGI", BOLD, 170, "(h-text_h)/2+50")],
          max(3.0, round(4.0 / beat) * beat), p)
    stukken.append(p)

    # Leuke clips: elke clip 4-8 beats, max 2 stukken per clip (begin en midden)
    for n, clip in enumerate(leuk):
        d = duur(clip)
        lengte = beat * (8 if n % 3 == 0 else 4)
        while lengte > d and lengte > beat:
            lengte -= beat
        starts = [0.0] if d < lengte * 3 else [d * 0.15, d * 0.55]
        for s in starts:
            p = nieuw()
            segment(clip, s, min(lengte, d - s), p)
            stukken.append(p)

    # Overgang naar het verdrietige deel
    if dood or rouw:
        p = nieuw()
        kaart([("maar toen...", FONT, 80, "(h-text_h)/2")], max(2.5, round(3 / beat) * beat), p)
        stukken.append(p)

    # Dood: hele clip (max 12 s bron), zwart-wit en vertraagd
    for clip in dood:
        d = min(duur(clip), 12.0)
        p = nieuw()
        segment(clip, 0, d / 0.7, p, zw=True, traag=0.7)
        stukken.append(p)

    # Rouw: zwart-wit, max 8 s per clip, met naam van het bestand als onderschrift
    for clip in rouw:
        d = min(duur(clip), 8.0)
        naam = clip.stem.split("_", 1)[-1].replace("_", " ") if "_" in clip.stem else None
        p = nieuw()
        segment(clip, 0, d, p, zw=True, onderschrift=naam)
        stukken.append(p)

    # Einde
    p = nieuw()
    kaart([("rust zacht", FONT, 80, "(h-text_h)/2-50"), ("Pangi", BOLD, 110, "(h-text_h)/2+70")], 5.0, p)
    stukken.append(p)

    lijst = TMP / "lijst.txt"
    lijst.write_text("".join(f"file '{s.name}'\n" for s in stukken))
    beeld = TMP / "beeld.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lijst), "-c", "copy", str(beeld)])

    totaal = duur(beeld)
    lied = duur(liedje)
    if lied < totaal:
        print(f"Let op: liedje ({lied:.0f}s) is korter dan de video ({totaal:.0f}s); het einde is stil.")
    uit = ROOT / "pangi_edit.mp4"
    run(["ffmpeg", "-y", "-i", str(beeld), "-i", str(liedje), "-map", "0:v", "-map", "1:a",
         "-af", f"afade=t=in:d=0.5,afade=t=out:st={max(0, totaal - 4):.2f}:d=4,apad",
         "-t", f"{totaal:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(uit)])
    print(f"Klaar: {uit.name}  ({totaal:.0f} seconden, {len(stukken)} stukken)")


if __name__ == "__main__":
    main()
