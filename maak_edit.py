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
  python3 maak_edit.py --piek 99.25          # drop van het liedje op de dood laten vallen
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

W, H, FPS = 1080, 1920, 30
FONT = "/usr/share/fonts/opentype/inter/Inter-Light.otf"
ONDERTITEL_FONT = "/usr/share/fonts/opentype/inter/Inter-Black.otf"
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


def beat_lengte(liedje, vanaf=0.0):
    """Schat de tijd tussen twee beats (s) uit de energie van het liedje."""
    sr = 11025
    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{vanaf:.2f}", "-i", str(liedje), "-t", "90", "-ac", "1", "-ar", str(sr),
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


def heeft_audio(pad):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                          "stream=index", "-of", "csv=p=0", str(pad)], capture_output=True, text=True)
    return bool(out.stdout.strip())


def geluid_stuk(bron, start, lengte, uit, volume=0.0):
    """Schrijft het geluid van een stuk als .wav (stilte als volume 0 is), precies `lengte` lang."""
    stil = ["-f", "lavfi", "-t", f"{lengte:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
    if volume > 0 and bron and heeft_audio(bron):
        af = (f"[0:a]aresample=44100,aformat=channel_layouts=stereo,volume={volume},"
              f"afade=t=in:d=0.2,afade=t=out:st={max(0, lengte - 0.3):.3f}:d=0.3,"
              f"apad,atrim=0:{lengte:.3f}[a]")
        cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{lengte:.3f}", "-i", str(bron),
               "-filter_complex", af, "-map", "[a]"]
    else:
        cmd = ["ffmpeg", "-y", *stil]
    run([*cmd, "-c:a", "pcm_s16le", str(uit)])


def lees_srt(pad):
    """Leest een .srt-bestand: [(begin, eind, tekst), ...] in seconden van de clip."""
    def sec(t):
        u, m, rest = t.strip().replace(",", ".").split(":")
        return int(u) * 3600 + int(m) * 60 + float(rest)
    cues = []
    for blok in pad.read_text(encoding="utf-8").strip().split("\n\n"):
        regels = [r for r in blok.strip().splitlines() if r.strip()]
        tijd = next((i for i, r in enumerate(regels) if "-->" in r), None)
        if tijd is None:
            continue
        a, b = regels[tijd].split("-->")
        cues.append((sec(a), sec(b), " ".join(regels[tijd + 1:]).strip()))
    return cues


def ondertitel_filters(bron, start, lengte, traag, uit):
    """TikTok-ondertitels uit "<clip>.srt" (als dat bestaat), onder het filmpje in beeld."""
    srt = bron.with_name(bron.stem + ".srt")
    if not srt.exists():
        return ""
    filters = []
    for i, (a, b, tekst) in enumerate(lees_srt(srt)):
        a, b = (a - start) / traag, (b - start) / traag
        if b <= 0 or a >= lengte or not tekst:
            continue
        a, b = max(0.0, a), min(lengte, b)
        tf = uit.with_name(f"{uit.stem}_tekst{i}.txt")
        tf.write_text(tekst, encoding="utf-8")
        filters.append(
            f"drawtext=fontfile={ONDERTITEL_FONT}:textfile={tf}:fontsize=78:fontcolor=white:"
            f"borderw=7:bordercolor=black@0.9:shadowcolor=black@0.5:shadowx=4:shadowy=4:"
            f"x=(w-text_w)/2:y=h*0.70:enable='between(t,{a:.3f},{b:.3f})':"
            f"alpha='min(1,(t-{a:.3f})/0.08)'")
    return "," + ",".join(filters) if filters else ""


def segment(bron, start, lengte, uit, zw=False, traag=1.0, zoom=0.0, flits=False,
            fade_in=0.0, fade_out=0.0, volume=0.0, audio_bron=None):
    """Knipt een stuk uit een clip: verticaal met wazige achtergrond.
    Het originele geluid komt (op `volume`) in een losse .wav naast het stuk;
    `audio_bron` vervangt het geluid, bijv. alleen de stem."""
    kleur = ",hue=s=0,eq=contrast=1.12:brightness=-0.03" if zw else ",eq=saturation=1.15:contrast=1.05"
    # langzame zoom-in over de hele lengte van het stuk
    z = f"(1+{zoom}*t/{lengte:.3f})"
    fg = (f"scale={W}:-2,setsar=1,scale=w='trunc({W}*{z}/2)*2':h=-2:eval=frame,"
          f"crop=w={W}:h='min(ih,{W}*9/16)':x='(iw-ow)/2':y='(ih-oh)/2'{kleur}")
    bg = f"scale=-2:{H},crop={W}:{H},boxblur=25:2{kleur},eq=brightness=-0.15"
    vf = (f"[0:v]setpts={1 / traag}*(PTS-STARTPTS),fps={FPS},split[a][b];[a]{bg}[bg];[b]{fg}[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2,vignette=PI/5")
    vf += ondertitel_filters(bron, start, lengte, traag, uit)
    if flits:
        vf += ",fade=t=in:d=0.12:color=white"
    if fade_in:
        vf += f",fade=t=in:d={fade_in}"
    if fade_out:
        vf += f",fade=t=out:st={lengte - fade_out:.3f}:d={fade_out}"
    vf += ",format=yuv420p[v]"
    run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{lengte * traag:.3f}", "-i", str(bron),
         "-filter_complex", vf, "-map", "[v]", "-an", "-t", f"{lengte:.3f}", *X264, str(uit)])
    lengte = duur(uit)
    geluid_stuk(audio_bron or bron, start, lengte, uit.with_suffix(".wav"),
                volume if traag == 1.0 else 0.0)


def einde(tekst, lengte, uit):
    """Zwart eindscherm, eventueel met kleine tekst."""
    vf = f"fade=t=in:d=1,fade=t=out:st={lengte - 1}:d=1,format=yuv420p"
    if tekst:
        t = tekst.replace("'", "’").replace(":", "\\:")
        vf = (f"drawtext=fontfile={FONT}:text='{t}':fontsize=64:fontcolor=white:"
              f"x=(w-text_w)/2:y=(h-text_h)/2," + vf)
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={lengte}",
         "-vf", vf, *X264, str(uit)])
    geluid_stuk(None, 0, duur(uit), uit.with_suffix(".wav"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bpm", type=float, help="tempo als er geen liedje in muziek/ staat")
    ap.add_argument("--eindtekst", default="rust zacht Pangi", help='"" = geen tekst')
    ap.add_argument("--clipgeluid", type=float, default=0.8,
                    help="volume van het originele geluid bij leuke clips (0 = uit)")
    ap.add_argument("--piek", type=float,
                    help="tijd (s) in het liedje die precies op het moment van de dood moet vallen")
    args = ap.parse_args()

    liedjes = bestanden("muziek", AUDIO_EXT)
    leuk = bestanden("clips/1_leuk", VIDEO_EXT)
    dood = bestanden("clips/2_dood", VIDEO_EXT)
    rouw = bestanden("clips/3_rouw", VIDEO_EXT)
    if not (leuk or dood or rouw):
        sys.exit("Zet clips in clips/1_leuk, clips/2_dood en/of clips/3_rouw")
    liedje = liedjes[0] if liedjes else None
    if liedje:
        beat = beat_lengte(liedje, max(0.0, (args.piek or 0) - 60))
        print(f"Liedje: {liedje.name}  (~{60 / beat:.0f} BPM)")
    else:
        beat = 60 / (args.bpm or 80)
        print(f"Geen liedje: stille video, knippen op {60 / beat:.0f} BPM")
    # knip per 2 beats bij snelle nummers, anders per beat; een stuk is 2-4 'tikken'
    tik = beat * 2 if beat < 0.45 else beat

    TMP.mkdir(exist_ok=True)
    stukken = []
    muziek_vol = []  # volume van het liedje per stuk (zachter als er clipgeluid is)
    dood_moment = None

    def nieuw(lied=1.0):
        p = TMP / f"{len(stukken) + 1:03d}.mp4"
        stukken.append(p)
        muziek_vol.append(lied)
        return p

    leuk_lied = 0.45 if args.clipgeluid > 0 else 1.0

    # Leuke clips: kort en snel, max 2 stukken per clip, wit flitsje op elke knip.
    # "naam@23-30.5.mp4" = precies dat stuk (lengte afgerond op de beat).
    # "_luid" in de naam = eigen geluid harder en liedje zachter (voor een moment dat je moet horen).
    for n, clip in enumerate(leuk):
        d = duur(clip)
        tijden = tijden_uit(clip)
        luid = "_luid" in clip.stem
        lied_vol, clip_vol = (0.2, args.clipgeluid * 1.1) if luid else (leuk_lied, args.clipgeluid)
        if len(tijden) == 2:
            begin, eind = tijden
            # eind ligt vast (nooit voorbij het gekozen eind knippen); voor de beat beginnen we iets eerder
            lengte = max(tik, math.ceil((eind - begin) / tik - 0.01) * tik)
            begin = max(0.0, eind - lengte)
            segment(clip, begin, min(lengte, d - begin), nieuw(lied_vol), zoom=0.08, flits=True,
                    volume=clip_vol)
            continue
        lengte = tik * (4 if n % 3 == 0 else 2)
        while lengte > d and lengte > tik:
            lengte -= tik
        starts = [0.0] if d < lengte * 3 else [d * 0.2, d * 0.6]
        for s in starts:
            segment(clip, s, min(lengte, d - s), nieuw(lied_vol), zoom=0.08, flits=True,
                    volume=clip_vol)

    # Dood. Tijden in de bestandsnaam: "naam@12-21.5-28.mp4" = vanaf 12 s in kleur,
    # vanaf 21.5 s (het moment van de dood) vertraagd en zwart-wit, tot 28 s.
    # Zonder tijden: eerste 12 s, helemaal zwart-wit en vertraagd.
    for clip in dood:
        tijden = tijden_uit(clip)
        if len(tijden) == 3:
            begin, moment, eind = tijden
            segment(clip, begin, moment - begin, nieuw(), zoom=0.1, fade_in=0.5)
            dood_moment = sum(duur(x) for x in stukken)
            segment(clip, moment, (eind - moment) / 0.5, nieuw(), zw=True, traag=0.5,
                    zoom=0.15, flits=True, fade_out=1.0)
        else:
            begin, eind = tijden if len(tijden) == 2 else (0.0, min(duur(clip), 12.0))
            segment(clip, begin, (eind - begin) / 0.7, nieuw(), zw=True, traag=0.7,
                    zoom=0.12, fade_in=0.8)

    # Rouw: zwart-wit, zachte overgangen. "naam@15-38.mp4" = stuk van 15 tot 38 s,
    # zonder tijden de eerste 8 s. Ligt er een "<naam>.stem.wav" naast (alleen de stem,
    # zonder muziek), dan is die stem goed te horen en gaat het liedje zachter.
    for clip in rouw:
        tijden = tijden_uit(clip)
        begin, eind = tijden if len(tijden) == 2 else (0.0, min(duur(clip), 8.0))
        stem = clip.with_name(clip.stem + ".stem.wav")
        if stem.exists():
            segment(clip, begin, eind - begin, nieuw(0.25), zw=True, zoom=0.06, fade_in=0.4,
                    fade_out=0.8, volume=2.0, audio_bron=stem)
        else:
            segment(clip, begin, eind - begin, nieuw(), zw=True, zoom=0.06, fade_in=0.4,
                    fade_out=0.8)

    einde(args.eindtekst, 4.0 if args.eindtekst else 2.0, nieuw())

    lijst = TMP / "lijst.txt"
    lijst.write_text("".join(f"file '{s.name}'\n" for s in stukken))
    beeld = TMP / "beeld.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lijst), "-c", "copy", str(beeld)])
    lijst_wav = TMP / "lijst_wav.txt"
    lijst_wav.write_text("".join(f"file '{s.with_suffix('.wav').name}'\n" for s in stukken))
    clipgeluid = TMP / "clipgeluid.wav"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lijst_wav), "-c", "copy",
         str(clipgeluid)])

    # volume van het liedje per stuk, met zachte overgangen van 0.3 s
    t, vol_expr = 0.0, "1"
    for s, v in zip(stukken, muziek_vol):
        d = duur(s)
        if v != 1.0:
            ramp = f"min(1,min(t-{t:.3f},{t + d:.3f}-t)/0.3)"
            vol_expr = f"if(between(t,{t:.3f},{t + d:.3f}),1-(1-{v})*{ramp},{vol_expr})"
        t += d

    totaal = duur(beeld)
    uit = ROOT / "pangi_edit.mp4"
    if liedje:
        if duur(liedje) < totaal:
            print("Let op: liedje is korter dan de video; het einde is stil.")
        lied_start = 0.0
        if args.piek is not None and dood_moment is not None:
            lied_start = max(0.0, args.piek - dood_moment)
            print(f"Liedje start op {lied_start:.1f}s, piek valt op {dood_moment:.1f}s in de video")
        lied = ["-ss", f"{lied_start:.3f}", "-i", str(liedje)]
    else:
        lied = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    af = (f"[1:a]aresample=44100,aformat=channel_layouts=stereo,apad,"
          f"volume=eval=frame:volume='{vol_expr}',"
          f"afade=t=in:d=0.3,afade=t=out:st={max(0, totaal - 4):.2f}:d=4[m];"
          f"[2:a]aresample=44100,aformat=channel_layouts=stereo,apad[c];"
          f"[m][c]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[a]")
    run(["ffmpeg", "-y", "-i", str(beeld), *lied, "-i", str(clipgeluid),
         "-filter_complex", af, "-map", "0:v", "-map", "[a]",
         "-t", f"{totaal:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(uit)])
    print(f"Klaar: {uit.name}  ({totaal:.0f} seconden, {len(stukken)} stukken)")


if __name__ == "__main__":
    main()
