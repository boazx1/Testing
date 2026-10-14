#!/usr/bin/env python3
"""Maakt automatisch een TikTok-style tribute edit van losse clips.

Mappen (zet je bestanden hierin, op volgorde van bestandsnaam):
  clips/1_leuk/   leuke momenten van Pangi   -> kleur, snel op de beat, zoom + flits
  clips/2_dood/   hoe hij doodging           -> zwart-wit, vertraagd
  clips/3_rouw/   mensen die rouwen (Knol..) -> zwart-wit, langer in beeld
  muziek/         optioneel: 1 liedje (mp3/m4a/wav)

Alle clips worden gedempt. Zonder liedje wordt de video stil gemaakt, zodat je
het geluid er in TikTok/CapCut zelf onder zet; geef dan het tempo op met --bpm.

Gebruik:
  python3 maak_edit.py                       # met liedje uit muziek/
  python3 maak_edit.py --bpm 80              # zonder liedje, knippen op 80 BPM
  python3 maak_edit.py --eindtekst ""        # helemaal geen tekst
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

W, H, FPS = 1080, 1920, 30
FONT = "/usr/share/fonts/opentype/inter/Inter-Light.otf"
ROOT = Path(__file__).resolve().parent
TMP = ROOT / "tmp_edit"
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac"}
X264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS)]


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
    return lag / fps


def bestanden(map_, ext):
    p = ROOT / map_
    return sorted(f for f in p.iterdir() if f.suffix.lower() in ext) if p.exists() else []


def tijden_uit(clip):
    """Leest tijden uit een bestandsnaam als "naam@12-21.5-28.mp4"."""
    return [float(x) for x in clip.stem.split("@", 1)[1].split("-")] if "@" in clip.stem else []


def segment(bron, start, lengte, uit, zw=False, traag=1.0, zoom=0.0, flits=False,
            fade_in=0.0, fade_out=0.0):
    """Knipt een stuk uit een clip: verticaal met wazige achtergrond, zonder geluid."""
    kleur = ",hue=s=0,eq=contrast=1.12:brightness=-0.03" if zw else ",eq=saturation=1.15:contrast=1.05"
    # langzame zoom-in over de hele lengte van het stuk
    z = f"(1+{zoom}*t/{lengte:.3f})"
    fg = (f"scale={W}:-2,setsar=1,scale=w='trunc({W}*{z}/2)*2':h=-2:eval=frame,"
          f"crop=w={W}:h='min(ih,{W}*9/16)':x='(iw-ow)/2':y='(ih-oh)/2'{kleur}")
    bg = f"scale=-2:{H},crop={W}:{H},boxblur=25:2{kleur},eq=brightness=-0.15"
    vf = (f"[0:v]setpts={1 / traag}*(PTS-STARTPTS),fps={FPS},split[a][b];[a]{bg}[bg];[b]{fg}[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2,vignette=PI/5")
    if flits:
        vf += ",fade=t=in:d=0.12:color=white"
    if fade_in:
        vf += f",fade=t=in:d={fade_in}"
    if fade_out:
        vf += f",fade=t=out:st={lengte - fade_out:.3f}:d={fade_out}"
    vf += ",format=yuv420p[v]"
    run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{lengte * traag:.3f}", "-i", str(bron),
         "-filter_complex", vf, "-map", "[v]", "-an", "-t", f"{lengte:.3f}", *X264, str(uit)])


def einde(tekst, lengte, uit):
    """Zwart eindscherm, eventueel met kleine tekst."""
    vf = f"fade=t=in:d=1,fade=t=out:st={lengte - 1}:d=1,format=yuv420p"
    if tekst:
        t = tekst.replace("'", "’").replace(":", "\\:")
        vf = (f"drawtext=fontfile={FONT}:text='{t}':fontsize=64:fontcolor=white:"
              f"x=(w-text_w)/2:y=(h-text_h)/2," + vf)
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={lengte}",
         "-vf", vf, *X264, str(uit)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bpm", type=float, help="tempo als er geen liedje in muziek/ staat")
    ap.add_argument("--eindtekst", default="rust zacht Pangi", help='"" = geen tekst')
    args = ap.parse_args()

    liedjes = bestanden("muziek", AUDIO_EXT)
    leuk = bestanden("clips/1_leuk", VIDEO_EXT)
    dood = bestanden("clips/2_dood", VIDEO_EXT)
    rouw = bestanden("clips/3_rouw", VIDEO_EXT)
    if not (leuk or dood or rouw):
        sys.exit("Zet clips in clips/1_leuk, clips/2_dood en/of clips/3_rouw")
    liedje = liedjes[0] if liedjes else None
    if liedje:
        beat = beat_lengte(liedje)
        print(f"Liedje: {liedje.name}  (~{60 / beat:.0f} BPM)")
    else:
        beat = 60 / (args.bpm or 80)
        print(f"Geen liedje: stille video, knippen op {60 / beat:.0f} BPM")
    # knip per 2 beats bij snelle nummers, anders per beat; een stuk is 2-4 'tikken'
    tik = beat * 2 if beat < 0.45 else beat

    TMP.mkdir(exist_ok=True)
    stukken = []

    def nieuw():
        p = TMP / f"{len(stukken) + 1:03d}.mp4"
        stukken.append(p)
        return p

    # Leuke clips: kort en snel, max 2 stukken per clip, wit flitsje op elke knip
    for n, clip in enumerate(leuk):
        d = duur(clip)
        lengte = tik * (4 if n % 3 == 0 else 2)
        while lengte > d and lengte > tik:
            lengte -= tik
        starts = [0.0] if d < lengte * 3 else [d * 0.2, d * 0.6]
        for s in starts:
            segment(clip, s, min(lengte, d - s), nieuw(), zoom=0.08, flits=True)

    # Dood. Tijden in de bestandsnaam: "naam@12-21.5-28.mp4" = vanaf 12 s in kleur,
    # vanaf 21.5 s (het moment van de dood) vertraagd en zwart-wit, tot 28 s.
    # Zonder tijden: eerste 12 s, helemaal zwart-wit en vertraagd.
    for clip in dood:
        tijden = tijden_uit(clip)
        if len(tijden) == 3:
            begin, moment, eind = tijden
            segment(clip, begin, moment - begin, nieuw(), zoom=0.1, fade_in=0.5)
            segment(clip, moment, (eind - moment) / 0.5, nieuw(), zw=True, traag=0.5,
                    zoom=0.15, flits=True, fade_out=1.0)
        else:
            begin, eind = tijden if len(tijden) == 2 else (0.0, min(duur(clip), 12.0))
            segment(clip, begin, (eind - begin) / 0.7, nieuw(), zw=True, traag=0.7,
                    zoom=0.12, fade_in=0.8)

    # Rouw: zwart-wit, zachte overgangen. "naam@15-38.mp4" = stuk van 15 tot 38 s,
    # zonder tijden de eerste 8 s.
    for clip in rouw:
        tijden = tijden_uit(clip)
        begin, eind = tijden if len(tijden) == 2 else (0.0, min(duur(clip), 8.0))
        segment(clip, begin, eind - begin, nieuw(), zw=True, zoom=0.06, fade_in=0.4, fade_out=0.8)

    einde(args.eindtekst, 4.0 if args.eindtekst else 2.0, nieuw())

    lijst = TMP / "lijst.txt"
    lijst.write_text("".join(f"file '{s.name}'\n" for s in stukken))
    beeld = TMP / "beeld.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lijst), "-c", "copy", str(beeld)])

    totaal = duur(beeld)
    uit = ROOT / "pangi_edit.mp4"
    if liedje:
        if duur(liedje) < totaal:
            print("Let op: liedje is korter dan de video; het einde is stil.")
        audio = ["-i", str(liedje), "-af",
                 f"afade=t=in:d=0.3,afade=t=out:st={max(0, totaal - 4):.2f}:d=4,apad"]
    else:
        audio = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    run(["ffmpeg", "-y", "-i", str(beeld), *audio, "-map", "0:v", "-map", "1:a",
         "-t", f"{totaal:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(uit)])
    print(f"Klaar: {uit.name}  ({totaal:.0f} seconden, {len(stukken)} stukken)")


if __name__ == "__main__":
    main()
