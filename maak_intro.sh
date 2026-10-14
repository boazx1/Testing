#!/usr/bin/env bash
# Maakt een rustige zwart-wit intro (15 s, 1080x1920 verticaal) voor de Pangi tribute edit.
# Gebruik: ./maak_intro.sh [liedje.mp3]
#   Zonder liedje: stille video, je zet het lied er zelf onder in CapCut.
#   Met liedje: het lied wordt eronder gezet (eerste 15 s, fade-out).
set -euo pipefail
FONT=/usr/share/fonts/opentype/inter/Inter-Light.otf
BOLD=/usr/share/fonts/opentype/inter/Inter-Bold.otf
OUT=pangi_intro.mp4

# Tekst die op tijd in en uit fade: txt <tekst> <font> <grootte> <start> <eind> <y>
txt() {
  local a="if(lt(t,$4),0,if(lt(t,$4+1),t-$4,if(lt(t,$5-1),1,if(lt(t,$5),$5-t,0))))"
  printf "drawtext=fontfile=%s:text='%s':fontsize=%s:fontcolor=white:x=(w-text_w)/2:y=%s:alpha='%s'" "$2" "$1" "$3" "$6" "$a"
}

VF="noise=alls=5:allf=t,vignette=PI/4"
VF+=",$(txt 'CREATOR SMP 4' "$FONT" 70 0.5 4.5 '(h-text_h)/2')"
VF+=",$(txt 'PANGI' "$BOLD" 180 5 10 '(h-text_h)/2-60')"
VF+=",$(txt 'je wordt gemist' "$FONT" 60 6.5 10 '(h-text_h)/2+120')"
VF+=",$(txt 'rust zacht' "$FONT" 80 10.5 15 '(h-text_h)/2')"
VF+=",fade=t=in:st=0:d=1,fade=t=out:st=14:d=1,format=yuv420p"

if [[ $# -ge 1 ]]; then
  ffmpeg -y -f lavfi -i "color=c=0x0a0a0a:s=1080x1920:r=30:d=15" -i "$1" \
    -vf "$VF" -af "afade=t=in:d=1,afade=t=out:st=13:d=2" -t 15 \
    -c:v libx264 -crf 26 -c:a aac -b:a 192k -shortest "$OUT"
else
  ffmpeg -y -f lavfi -i "color=c=0x0a0a0a:s=1080x1920:r=30:d=15" \
    -f lavfi -i anullsrc=r=44100:cl=stereo \
    -vf "$VF" -t 15 -c:v libx264 -crf 26 -c:a aac -shortest "$OUT"
fi
echo "Klaar: $OUT"
