#!/bin/bash
cd "$(dirname "$0")"
echo "설교 쇼츠 도구에 필요한 프로그램을 설치합니다..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python이 없습니다. https://www.python.org/downloads/ 에서 설치한 뒤 다시 실행해 주세요."
  read -p "엔터를 누르면 창이 닫힙니다."; exit 1
fi
python3 -m pip install --upgrade --user pillow imageio-ffmpeg yt-dlp \
  || python3 -m pip install --upgrade pillow imageio-ffmpeg yt-dlp
echo
python3 shorts.py 점검
echo
read -p "엔터를 누르면 창이 닫힙니다."
