#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
설교 쇼츠 만들기 도구

필요한 것: Python 3.9 이상, 그리고 `pip install pillow imageio-ffmpeg yt-dlp`
(설치_맥.command / 설치_윈도우.bat 를 실행하면 자동으로 설치됩니다.)

사용법
  python shorts.py                         메뉴 방식으로 실행
  python shorts.py 점검                     설치·글꼴·로고 상태 점검
  python shorts.py 대본  <유튜브주소> <회차폴더이름>
  python shorts.py 미리보기 <회차폴더>
  python shorts.py 만들기  <회차폴더>
"""
import argparse, array, json, math, os, re, shutil, struct, subprocess, sys, tempfile, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1080, 1920, 30
VERSION = '1.2'

# ---------------------------------------------------------------- 공통
class 오류(Exception):
    pass

def 알림(msg):
    print(msg, flush=True)

def 시간초(v):
    """'38:02.15', '1:02:03.5', 2282.15 모두 초로 바꿉니다."""
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if re.fullmatch(r'-?\d+(\.\d+)?', s):
        return float(s)
    parts = s.split(':')
    if not 2 <= len(parts) <= 3 or not all(re.fullmatch(r'\d+(\.\d+)?', p) for p in parts):
        raise 오류(f'시간 형식을 읽을 수 없습니다: "{v}"  (예: 38:02.15)')
    t = 0.0
    for p in parts:
        t = t * 60 + float(p)
    return t

def 시간글(t):
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f'{int(h)}:{int(m):02d}:{s:05.2f}' if h >= 1 else f'{int(m):02d}:{s:05.2f}'

def ffmpeg_경로():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        p = shutil.which('ffmpeg')
        if p:
            return p
    raise 오류('FFmpeg를 찾을 수 없습니다. 설치 파일(설치_맥.command / 설치_윈도우.bat)을 먼저 실행해 주세요.')

def ytdlp용_ffmpeg(ff):
    """yt-dlp가 알아볼 수 있도록 'ffmpeg' 라는 이름으로 준비합니다."""
    if os.path.splitext(os.path.basename(ff))[0].lower() == 'ffmpeg':
        return ff
    d = os.path.join(HERE, '_ffmpeg')
    dst = os.path.join(d, 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(ff):
        os.makedirs(d, exist_ok=True)
        try:
            if os.path.exists(dst):
                os.remove(dst)
            os.link(ff, dst)
        except Exception:
            shutil.copy2(ff, dst)
        os.chmod(dst, 0o755)
    # yt-dlp는 부분 다운로드 가능 여부를 PATH에서만 확인하므로 PATH에도 추가합니다
    if d not in os.environ.get('PATH', '').split(os.pathsep):
        os.environ['PATH'] = d + os.pathsep + os.environ.get('PATH', '')
    return dst

def 실행(cmd, 설명=''):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        raise 오류(f'{설명} 실패\n' + r.stderr[-2500:])
    return r

def 읽기json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise 오류(f'{os.path.basename(path)} 파일의 형식이 잘못되었습니다 ({e.lineno}번째 줄 부근). 쉼표·따옴표·괄호를 확인해 주세요.')

def 쓰기json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def 경로(p, base=HERE):
    if not p:
        return ''
    p = os.path.expanduser(str(p))
    return p if os.path.isabs(p) else os.path.join(base, p)

# ---------------------------------------------------------------- 설정
기본설정 = {
    '교회이름': '우리교회',
    '설교자': '',
    '글꼴': '글꼴/',
    '로고': '로고.png',
    '배경음악': '',
    '배경음악_크기_LU': -13,
    '최종음량_LUFS': -16,
    '끝_페이드_초': 1.5,
    '배경음악_끝_페이드_초': 2.5,
    '단어사이_공백_줄이기': True,
    '공백_기준_dB': -30,
    '공백_최소_초': 0.20,
    '화면자르기': {'x': 440, 'y': 100, '너비': 760},
    '색': {'제목': '#86F07A', '제목테두리': '#0E3B12', '자막': '#FFFFFF', '교회이름': '#FFFFFF'},
    '배치': {
        '제목_y': 'auto', '제목_크기': 76,
        '성경_y': 284, '성경_크기': 70,
        '영상_y': 345, '영상_높이': 960,
        '자막_y': 1388, '자막_크기': 64, '자막_줄간격': 1.25,
        '교회이름_x': 596, '교회이름_y': 1638, '교회이름_크기': 44, '교회이름_자간': 0.12,
        '설교자_x': 596, '설교자_y': 1721, '설교자_크기': 44,
        '로고_x': 296, '로고_y': 1694.6, '로고_배율': 0.565,
    },
}

def 합치기(기본, 사용자):
    out = dict(기본)
    for k, v in (사용자 or {}).items():
        out[k] = 합치기(기본[k], v) if isinstance(v, dict) and isinstance(기본.get(k), dict) else v
    return out

def 설정_읽기():
    p = os.path.join(HERE, '설정.json')
    return 합치기(기본설정, 읽기json(p) if os.path.exists(p) else {})

def 글꼴_찾기(설정):
    p = 경로(설정.get('글꼴'))
    if p and os.path.isfile(p):
        return p
    if p and os.path.isdir(p):
        for f in sorted(os.listdir(p)):
            if f.lower().endswith(('.ttf', '.otf', '.ttc')):
                return os.path.join(p, f)
    for c in [os.path.join(HERE, '_기본글꼴', 'NanumGothic-Bold.ttf'),
              'C:/Windows/Fonts/malgunbd.ttf', 'C:/Windows/Fonts/malgun.ttf',
              '/System/Library/Fonts/AppleSDGothicNeo.ttc', '/Library/Fonts/NanumGothicBold.ttf',
              '/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf']:
        if os.path.exists(c):
            알림(f'  [안내] 「글꼴」 폴더에 글꼴이 없어 기본 글꼴({os.path.basename(c)})로 만듭니다.')
            return c
    raise 오류('사용할 수 있는 한글 글꼴이 없습니다. 「글꼴」 폴더에 .ttf 또는 .otf 글꼴을 넣어 주세요.')

# ---------------------------------------------------------------- 글자 그림 (Pillow)
def _pil():
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
        return Image, ImageDraw, ImageFilter, ImageFont
    except ImportError:
        raise 오류('Pillow가 설치되어 있지 않습니다. 설치 파일을 먼저 실행해 주세요.')

def 글자_그리기(canvas, text, xy, font_path, size, fill, stroke=0, stroke_fill=None, shadow=False, tracking=0.0, spacing=1.25):
    Image, ImageDraw, ImageFilter, ImageFont = _pil()
    font = ImageFont.truetype(font_path, size)
    lines = text.split('\n')
    lh = size * spacing
    y0 = xy[1] - lh * (len(lines) - 1) / 2

    def draw_on(img, dx, dy, color, sw, sf):
        d = ImageDraw.Draw(img)
        for i, line in enumerate(lines):
            y = y0 + i * lh + dy
            if tracking:
                widths = [font.getlength(ch) for ch in line]
                total = sum(widths) + tracking * size * (len(line) - 1)
                x = xy[0] - total / 2 + dx
                for ch, w in zip(line, widths):
                    d.text((x, y), ch, font=font, fill=color, anchor='lm', stroke_width=sw, stroke_fill=sf)
                    x += w + tracking * size
            else:
                d.text((xy[0] + dx, y), line, font=font, fill=color, anchor='mm', stroke_width=sw, stroke_fill=sf)

    if shadow:
        sh = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw_on(sh, 3, 4, (0, 0, 0, 170), stroke, (0, 0, 0, 170))
        canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(3)))
    draw_on(canvas, 0, 0, fill, stroke, stroke_fill)

def 고정화면_만들기(설정, 회차, font, out_png):
    """제목·성경·교회이름·설교자·로고를 담은 투명 PNG"""
    Image, *_ = _pil()
    L, C = 설정['배치'], 설정['색']
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    제목 = 회차.get('제목', '')
    ty = L['제목_y']
    if ty in (None, '', 'auto'):
        ty = 145 if '\n' in 제목 else 192   # 두 줄 제목은 조금 위로
    글자_그리기(im, 제목, (W / 2, float(ty)), font, L['제목_크기'], C['제목'], 3, C['제목테두리'], True)
    if 회차.get('성경'):
        글자_그리기(im, 회차['성경'], (W / 2, L['성경_y']), font, L['성경_크기'], C['제목'], 3, C['제목테두리'], True)
    logo = 경로(설정.get('로고'))
    has_logo = bool(logo and os.path.exists(logo))
    교회 = 회차.get('교회이름', 설정['교회이름'])
    if 교회:
        글자_그리기(im, 교회, (L['교회이름_x'] if has_logo else W / 2, L['교회이름_y']), font, L['교회이름_크기'], C['교회이름'], tracking=L['교회이름_자간'])
    설교자 = 회차.get('설교자', 설정.get('설교자', ''))
    if 설교자:
        글자_그리기(im, 설교자, (L['설교자_x'] if has_logo else W / 2, L['설교자_y']), font, L['설교자_크기'], C['교회이름'])
    if has_logo:
        lg = Image.open(logo).convert('RGBA')
        s = L['로고_배율']
        lg = lg.resize((max(1, round(lg.width * s)), max(1, round(lg.height * s))), Image.LANCZOS)
        im.alpha_composite(lg, (round(L['로고_x'] - lg.width / 2), round(L['로고_y'] - lg.height / 2)))
    im.save(out_png)

def 자막그림_만들기(설정, font, text, out_png):
    Image, *_ = _pil()
    L = 설정['배치']
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    글자_그리기(im, text, (W / 2, L['자막_y']), font, L['자막_크기'], 설정['색']['자막'], spacing=L['자막_줄간격'])
    im.save(out_png)

# ---------------------------------------------------------------- 유튜브
def _ytdlp():
    try:
        import yt_dlp
        return yt_dlp
    except ImportError:
        raise 오류('yt-dlp가 설치되어 있지 않습니다. 설치 파일을 먼저 실행해 주세요.')

def 대본_받기(url, 폴더):
    yt_dlp = _ytdlp()
    os.makedirs(폴더, exist_ok=True)
    알림('유튜브에서 자동 자막을 받는 중입니다...')
    opts = {'skip_download': True, 'writeautomaticsub': True, 'writesubtitles': True,
            'subtitleslangs': ['ko', 'ko-orig'], 'subtitlesformat': 'json3', 'quiet': True, 'no_warnings': True, 'noprogress': True,
            'outtmpl': os.path.join(폴더, '_자막.%(ext)s')}
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as e:
        raise 오류('유튜브 정보를 가져오지 못했습니다. 주소와 공개 설정(공개/일부공개)을 확인해 주세요.\n  (상세: ' + str(e)[-300:] + ')')
    cands = [f for f in os.listdir(폴더) if f.startswith('_자막') and f.endswith('.json3')]
    if not cands:
        raise 오류('이 영상에서 한국어 자막을 찾지 못했습니다. 업로드 직후라면 YouTube 자동 자막이 생길 때까지(보통 몇 시간) 기다렸다가 다시 시도해 주세요.')
    cands.sort(key=lambda f: (not f.endswith('.ko.json3'), f))  # 한국어 자막 우선
    data = 읽기json(os.path.join(폴더, cands[0]))
    words, lines = [], []
    for ev in data.get('events', []):
        segs = ev.get('segs')
        if not segs:
            continue
        t0 = ev.get('tStartMs', 0)
        text = ''.join(s.get('utf8', '') for s in segs).replace('\n', ' ').strip()
        if text:
            lines.append((t0 / 1000, text))
        for s in segs:
            w = s.get('utf8', '').strip()
            if w:
                words.append(((t0 + s.get('tOffsetMs', 0)) / 1000, w))
    with open(os.path.join(폴더, '대본.txt'), 'w', encoding='utf-8') as f:
        f.write(f'# {info.get("title", "")}\n# {url}\n# 시간은 원본 영상 기준입니다.\n\n')
        for t, x in lines:
            f.write(f'[{시간글(t)}] {x}\n')
    with open(os.path.join(폴더, '단어시간.txt'), 'w', encoding='utf-8') as f:
        f.write('# 단어별 시작 시간 (정확한 컷 지점을 정할 때 사용)\n')
        for t, x in words:
            f.write(f'{시간글(t)}\t{x}\n')
    ep = os.path.join(폴더, '회차.json')
    if not os.path.exists(ep):
        쓰기json(ep, {
            '제목': '여기에 쇼츠 제목',
            '성경': '예: 행 5:33-42',
            '영상': {'유튜브': url},
            '구간': [
                {'시작': '00:00.00', '끝': '00:05.00',
                 '자막': [['00:00.00', '첫 번째 자막'], ['00:02.50', '두 번째 자막']]}
            ]
        })
    알림(f'완료: 대본.txt, 단어시간.txt, 회차.json 을 만들었습니다.\n  폴더: {폴더}')
    return 폴더

def 스트림길이(ff, f, kind):
    r = subprocess.run([ff, '-hide_banner', '-v', 'error', '-i', f, '-map', f'0:{kind}:0', '-c', 'copy', '-f', 'null', '-', '-progress', 'pipe:1'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    v = re.findall(r'out_time_us=(\d+)', r.stdout)
    return int(v[-1]) / 1e6 if v and v[-1].isdigit() else 0.0

def _조각받기(url, a, b, headers):
    last = None
    for i in range(3):
        try:
            req = urllib.request.Request(f'{url}&range={a}-{b}', headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(1 + i)
    raise last

def _sidx(head):
    """DASH 파일 앞부분에서 sidx(조각 목록)를 읽어 [(시작초, 끝초, 바이트시작, 바이트끝)] 을 돌려줍니다."""
    p, s = 0, None
    while p + 8 <= len(head):
        size, typ = struct.unpack('>I4s', head[p:p + 8])
        hdr = 8
        if size == 1:
            size = struct.unpack('>Q', head[p + 8:p + 16])[0]
            hdr = 16
        if typ == b'sidx':
            s = (p, size, hdr)
            break
        if size < 8:
            break
        p += size
    if not s or s[0] + s[1] > len(head):
        return None
    off0, size, hdr = s
    b = head[off0:off0 + size]
    q = hdr
    ver = b[q]
    q += 8
    ts = struct.unpack('>I', b[q:q + 4])[0]
    q += 4
    if ver == 0:
        ept, first = struct.unpack('>II', b[q:q + 8]); q += 8
    else:
        ept, first = struct.unpack('>QQ', b[q:q + 16]); q += 16
    q += 2
    count = struct.unpack('>H', b[q:q + 2])[0]
    q += 2
    off, t, refs = off0 + size + first, ept, []
    for _ in range(count):
        rs, dur = struct.unpack('>II', b[q:q + 8])
        rs &= 0x7fffffff
        refs.append((t / ts, (t + dur) / ts, off, off + rs - 1))
        off += rs; t += dur; q += 12
    return off0 - 1, refs

def _트랙받기(fmt, T0, T1, path):
    h = fmt.get('http_headers') or {}
    head = _조각받기(fmt['url'], 0, 262143, h)
    ix = _sidx(head)
    if not ix:
        raise 오류('조각 정보(sidx)를 찾지 못했습니다.')
    init_end, refs = ix
    sel = [r for r in refs if r[1] > T0 and r[0] < T1]
    if not sel:
        raise 오류('구간에 해당하는 조각이 없습니다.')
    a, b = sel[0][2], sel[-1][3]
    with open(path, 'wb') as f:
        f.write(head[:init_end + 1])
        x = a
        while x <= b:
            y = min(b, x + 9_000_000 - 1)
            f.write(_조각받기(fmt['url'], x, y, h))
            x = y + 1
    return sel[0][0], sel[-1][1]

def 구간_빠르게_받기(url, 원본폴더, 시작, 끝, ff):
    """필요한 부분만 고화질로 받습니다. 성공하면 (파일, 실제시작, 실제끝)"""
    yt_dlp = _ytdlp()
    opts = {'quiet': True, 'no_warnings': True, 'noprogress': True,
            'format': 'bv*[height<=1080][ext=mp4][protocol=https]+ba[ext=m4a][protocol=https]'}
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=False)
    fmts = info.get('requested_formats') or []
    if len(fmts) != 2:
        raise 오류('영상·소리 형식을 찾지 못했습니다.')
    out = os.path.join(원본폴더, f'part_{int(시작)}_{int(math.ceil(끝))}.mp4')
    vf, af = out + '.v.mp4', out + '.a.m4a'
    try:
        vs, ve = _트랙받기(fmts[0], 시작, 끝, vf)
        a_s, ae = _트랙받기(fmts[1], min(시작, vs), 끝, af)
        off = max(vs, a_s)
        실행([ff, '-hide_banner', '-y', '-ss', f'{off - vs:.6f}', '-i', vf, '-ss', f'{off - a_s:.6f}', '-i', af,
             '-map', '0:v:0', '-map', '1:a:0', '-c', 'copy', '-movflags', '+faststart', out], '영상 합치기')
    finally:
        for p in (vf, af):
            if os.path.exists(p):
                os.remove(p)
    return out, off, min(ve, ae)

def 구간_내려받기(url, 원본폴더, 시작, 끝, ff):
    """(파일, 파일의 원본기준 시작초, 끝초)"""
    os.makedirs(원본폴더, exist_ok=True)
    알림(f'  영상 구간 내려받는 중: {시간글(시작)} ~ {시간글(끝)}')
    try:
        return 구간_빠르게_받기(url, 원본폴더, 시작, 끝, ff)
    except Exception as e:
        알림(f'  [안내] 빠른 내려받기가 안 되어 다른 방법으로 받습니다. ({str(e)[:120]})')
    f = 구간_내려받기_ytdlp(url, 원본폴더, 시작, 끝, ff)
    return f, 시작, 끝

def 구간_내려받기_ytdlp(url, 원본폴더, 시작, 끝, ff, 시도=1):
    yt_dlp = _ytdlp()
    os.makedirs(원본폴더, exist_ok=True)
    이름 = f'part_{int(시작)}_{int(math.ceil(끝))}'
    out = os.path.join(원본폴더, 이름 + '.mp4')
    opts = {'format': 'bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/b',
            'merge_output_format': 'mp4', 'outtmpl': os.path.join(원본폴더, 이름 + '.%(ext)s'),
            'download_ranges': yt_dlp.utils.download_range_func(None, [(시작, 끝)]),
            'force_keyframes_at_cuts': False, 'ffmpeg_location': ytdlp용_ffmpeg(ff), 'quiet': True, 'no_warnings': True,
            'noprogress': True}
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([url])
    except yt_dlp.utils.DownloadError as e:
        raise 오류('유튜브에서 영상을 받지 못했습니다. 주소와 공개 설정(공개/일부공개)을 확인하고, 계속 안 되면 설치 파일을 다시 실행해 yt-dlp를 최신으로 바꿔 주세요.\n  (상세: ' + str(e)[-300:] + ')')
    if not os.path.exists(out):
        found = [f for f in os.listdir(원본폴더) if f.startswith(이름)]
        if not found:
            raise 오류('영상 구간을 내려받지 못했습니다. 인터넷 연결과 영상 공개 설정(공개 또는 일부공개)을 확인해 주세요.')
        out = os.path.join(원본폴더, found[0])
    # 소리만 있고 영상이 중간에 끊기는 경우가 있어 영상 길이를 확인합니다
    need = 끝 - 시작
    vlen, alen = 스트림길이(ff, out, 'v'), 스트림길이(ff, out, 'a')
    if vlen < need - 1.0 or alen < need - 1.0:
        os.remove(out)
        if 시도 < 3:
            알림(f'  내려받은 영상이 덜 받아졌습니다(영상 {vlen:.1f}초 / 필요 {need:.1f}초). 다시 받습니다...')
            return 구간_내려받기_ytdlp(url, 원본폴더, 시작, 끝, ff, 시도 + 1)
        raise 오류('영상을 끝까지 내려받지 못했습니다. 잠시 후 다시 시도해 주세요.')
    return out

# ---------------------------------------------------------------- 회차 읽기·검사
def 회차_읽기(폴더, 설정):
    p = os.path.join(폴더, '회차.json')
    if not os.path.exists(p):
        raise 오류(f'회차.json 이 없습니다: {p}')
    E = 읽기json(p)
    if not E.get('구간'):
        raise 오류('회차.json 에 "구간"이 없습니다.')
    pieces = []
    for i, g in enumerate(E['구간'], 1):
        a, b = 시간초(g['시작']), 시간초(g['끝'])
        if b - a < 0.3:
            raise 오류(f'{i}번째 구간의 끝이 시작보다 빠르거나 너무 짧습니다 ({g["시작"]} ~ {g["끝"]}).')
        subs = []
        for s in g.get('자막', []):
            if not (isinstance(s, (list, tuple)) and len(s) == 2):
                raise 오류(f'{i}번째 구간의 자막 형식이 잘못되었습니다. ["시간", "자막"] 형태여야 합니다: {s}')
            t = 시간초(s[0])
            if not (a - 0.6 <= t <= b):
                raise 오류(f'{i}번째 구간의 자막 시간 {s[0]} 이 구간({g["시작"]} ~ {g["끝"]}) 밖에 있습니다.')
            subs.append([max(a, t), str(s[1])])
        for x, y in zip(subs, subs[1:]):
            if y[0] - x[0] < 0.2:
                raise 오류(f'{i}번째 구간의 자막 시간 순서가 잘못되었거나 너무 촘촘합니다: "{x[1]}" → "{y[1]}"')
        if subs and b - subs[-1][0] < 0.2:
            raise 오류(f'{i}번째 구간의 마지막 자막 "{subs[-1][1]}" 이 표시될 시간이 없습니다.')
        pieces.append({'a': a, 'b': b, 'subs': subs})
    crop = E.get('화면자르기') or 설정['화면자르기']
    return E, pieces, crop

def 원본_준비(폴더, E, pieces, ff):
    """구간에 필요한 원본 영상 파일 목록 [(파일, 시작오프셋, 끝)]"""
    src = E.get('영상', {})
    if src.get('파일'):
        f = 경로(src['파일'], 폴더)
        if not os.path.exists(f):
            raise 오류(f'영상 파일이 없습니다: {f}')
        return [(f, 0.0, 1e9)]
    url = src.get('유튜브')
    if not url:
        raise 오류('회차.json 의 "영상"에 "유튜브" 주소나 "파일" 경로를 넣어 주세요.')
    원본폴더 = os.path.join(폴더, '_원본')
    목록p = os.path.join(원본폴더, '목록.json')
    목록 = 읽기json(목록p) if os.path.exists(목록p) else []
    def 덮음(a, b):
        for m in 목록:
            if m['시작'] <= a - 0.5 and b + 0.5 <= m['끝'] and os.path.exists(os.path.join(원본폴더, m['파일'])):
                return True
        return False
    # 가까운 구간끼리 묶어서 필요한 부분만 내려받기
    need = sorted((p['a'], p['b']) for p in pieces if not 덮음(p['a'], p['b']))
    groups = []
    for a, b in need:
        if groups and a - groups[-1][1] < 90:
            groups[-1][1] = max(groups[-1][1], b)
        else:
            groups.append([a, b])
    for a, b in groups:
        s, e = max(0.0, math.floor(a - 3)), math.ceil(b + 3)
        f, s, e = 구간_내려받기(url, 원본폴더, s, e, ff)
        목록.append({'파일': os.path.basename(f), '시작': s, '끝': e})
        쓰기json(목록p, 목록)
    return [(os.path.join(원본폴더, m['파일']), m['시작'], m['끝']) for m in 목록]

def 원본_고르기(srcs, a, b):
    for i, (f, s, e) in enumerate(srcs):
        if s <= a - 0.05 and b <= e:
            return i
    raise 오류(f'{시간글(a)} ~ {시간글(b)} 구간의 원본 영상을 찾지 못했습니다.')

def 영상정보(ff, f):
    r = subprocess.run([ff, '-hide_banner', '-i', f], capture_output=True, text=True, encoding='utf-8', errors='replace')
    m = re.search(r'Video:.*?(\d{3,5})x(\d{3,5})', r.stderr)
    if not m:
        raise 오류(f'영상 정보를 읽을 수 없습니다: {f}')
    return int(m.group(1)), int(m.group(2))

def 자르기_계산(crop, sw, sh, 설정):
    L = 설정['배치']
    x = float(crop.get('x', crop.get('x0', 0)))
    y = float(crop.get('y', crop.get('y0', 0)))
    w = float(crop.get('너비', crop.get('x1', sw) - x if 'x1' in crop else sw))
    h = w * L['영상_높이'] / W
    # 원본이 1080p가 아니면 비율대로 맞춤 (설정은 1920x1080 기준 좌표)
    k = sw / 1920.0
    x, y, w, h = x * k, y * k, w * k, h * k
    if x < 0 or y < 0 or x + w > sw + 1 or y + h > sh + 1:
        raise 오류(f'화면자르기 범위가 원본 영상({sw}x{sh}) 밖으로 나갑니다. x·y·너비 값을 줄여 주세요.')
    return int(round(x)), int(round(y)), int(round(w)) // 2 * 2, int(round(h)) // 2 * 2

# ---------------------------------------------------------------- 오디오 보조
def 음량_LUFS(ff, f, ss=None, t=None):
    cmd = [ff, '-hide_banner', '-nostats']
    if ss is not None:
        cmd += ['-ss', f'{ss:.3f}', '-t', f'{t:.3f}']
    cmd += ['-i', f, '-vn', '-af', 'ebur128', '-f', 'null', '-']
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    v = re.findall(r'I:\s+(-?[\d.]+) LUFS', r.stderr)
    return float(v[-1]) if v else -70.0

def 조용한곳으로(ff, f, off, t, lo, hi):
    """t 근처(lo~hi 초 범위)에서 가장 조용한 10ms 지점으로 컷을 옮깁니다."""
    ss = max(0.0, t + lo - off)
    raw = subprocess.run([ff, '-v', 'error', '-ss', f'{ss:.3f}', '-t', f'{hi - lo + 0.02:.3f}', '-i', f, '-vn', '-ac', '1',
                          '-ar', '8000', '-f', 's16le', '-'], capture_output=True).stdout
    a = array.array('h', raw)
    n = 80
    if len(a) < n * 2:
        return t
    env = [sum(x * x for x in a[i:i + n]) for i in range(0, len(a) - n, n)]
    best = min(range(len(env)), key=lambda i: env[i])
    return off + ss + best * 0.01

def 무음찾기(ff, f, off, a, b, noise, mingap):
    r = subprocess.run([ff, '-hide_banner', '-nostats', '-ss', f'{a - off:.3f}', '-t', f'{b - a:.3f}', '-i', f, '-vn',
                        '-af', f'silencedetect=noise={noise}dB:d={mingap}', '-f', 'null', '-'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    out, cur = [], None
    for line in r.stderr.splitlines():
        m = re.search(r'silence_start: (-?[\d.]+)', line)
        if m:
            cur = max(0.0, float(m.group(1)))
        m = re.search(r'silence_end: ([\d.]+)', line)
        if m and cur is not None:
            out.append((a + cur, a + float(m.group(1))))
            cur = None
    if cur is not None:
        out.append((a + cur, b))
    return out

def 공백_줄이기(ff, srcs, pieces, 설정):
    """각 구간 안의 무음을 0.12초 정도만 남기고 잘라 냅니다. 자막은 새 컷에 맞춰 옮깁니다."""
    noise = float(설정.get('공백_기준_dB', -30))
    mingap = float(설정.get('공백_최소_초', 0.20))
    PA, PB = 0.05, 0.07          # 말 끝 뒤 / 말 시작 앞에 남길 여유
    new = []
    for p in pieces:
        a, b = p['a'], p['b']
        f, off, _ = srcs[원본_고르기(srcs, a, b)]
        keeps, s = [], a
        for s0, s1 in 무음찾기(ff, f, off, a, b, noise, mingap):
            if s0 <= a + 0.02:
                s = max(s, s1 - PB); continue
            if s1 >= b - 0.02:
                b = min(b, s0 + PA); continue
            c0, c1 = s0 + PA, s1 - PB
            if c1 - c0 < 0.05:
                continue
            keeps.append([s, c0]); s = c1
        keeps.append([s, b])
        keeps = [k for k in keeps if k[1] - k[0] >= 0.30] or [[p['a'], p['b']]]
        subs = p['subs']
        for ka, kb in keeps:
            lst = []
            cur = [x for t, x in subs if t <= ka + 1e-6]
            if cur:
                lst.append([ka, cur[-1]])
            for t, x in subs:
                if ka + 1e-6 < t < kb:
                    if lst and t - lst[-1][0] < 0.25:
                        lst[-1] = [lst[-1][0], x]
                    else:
                        lst.append([max(ka, t), x])
            while len(lst) > 1 and kb - lst[-1][0] < 0.22:
                lst.pop()
            new.append({'a': ka, 'b': kb, 'subs': lst})
    return new

def _따옴표(p):
    return p.replace(chr(92), '/').replace("'", "'\\''")

# ---------------------------------------------------------------- 만들기
def 만들기(폴더, 미리보기만=False):
    설정 = 설정_읽기()
    ff = ffmpeg_경로()
    font = 글꼴_찾기(설정)
    E, pieces, crop = 회차_읽기(폴더, 설정)
    srcs = 원본_준비(폴더, E, pieces, ff)
    작업 = os.path.join(폴더, '_작업')
    os.makedirs(작업, exist_ok=True)

    # 단어 사이 무음을 짧게 줄여 말이 빠르게 이어지게 합니다
    if E.get('단어사이_공백_줄이기', 설정.get('단어사이_공백_줄이기', True)):
        before = sum(p['b'] - p['a'] for p in pieces)
        pieces = 공백_줄이기(ff, srcs, pieces, 설정)
        after = sum(p['b'] - p['a'] for p in pieces)
        if before - after > 0.05:
            알림(f'  단어 사이 공백 {before - after:.1f}초를 줄였습니다.')

    # 컷 지점 다듬기 + 프레임 단위로 길이 맞추기 (음성과 화면이 어긋나지 않게)
    for p in pieces:
        p['src'] = 원본_고르기(srcs, p['a'], p['b'])
        f, off, _ = srcs[p['src']]
        if E.get('컷지점_자동다듬기', False):
            p['a'] = 조용한곳으로(ff, f, off, p['a'], -0.15, 0.04)
            p['b'] = 조용한곳으로(ff, f, off, p['b'], -0.12, 0.06)
        n = max(1, round((p['b'] - p['a']) * FPS))
        p['b'] = p['a'] + n / FPS
        p['n'] = n
    total_frames = sum(p['n'] for p in pieces)
    total = total_frames / FPS

    # 자막 시간표
    subs, t0 = [], 0.0
    for p in pieces:
        ends = [s[0] for s in p['subs'][1:]] + [p['b']]
        for (st, txt), en in zip(p['subs'], ends):
            a = round((t0 + st - p['a']) * FPS) / FPS
            b = round((t0 + en - p['a']) * FPS) / FPS
            subs.append([a, b, txt])
        t0 += p['n'] / FPS
    # 컷이 나뉘어도 같은 자막이 이어지면 하나로 합칩니다
    merged = []
    for a, b, txt in subs:
        if merged and merged[-1][2] == txt and abs(merged[-1][1] - a) < 1e-6:
            merged[-1][1] = b
        else:
            merged.append([a, b, txt])
    subs = merged

    고정 = os.path.join(작업, '고정화면.png')
    고정화면_만들기(설정, E, font, 고정)
    sw, sh = 영상정보(ff, srcs[0][0])
    cx, cy, cw, ch = 자르기_계산(crop, sw, sh, 설정)
    L = 설정['배치']

    if 미리보기만:
        return 미리보기_그림(폴더, 설정, E, font, pieces, srcs, subs, 고정, (cx, cy, cw, ch), ff)

    알림(f'구간 {len(pieces)}개, 자막 {len(subs)}개, 길이 {total:.1f}초로 만듭니다.')
    # 자막 그림과 시간표(concat 목록)
    blank = os.path.join(작업, '자막_빈칸.png')
    _pil()[0].new('RGBA', (W, H), (0, 0, 0, 0)).save(blank)
    lst, cur = [], 0.0
    for i, (a, b, txt) in enumerate(subs):
        if a > cur + 1e-6:
            lst.append((blank, a - cur))
        png = os.path.join(작업, f'자막_{i:03d}.png')
        자막그림_만들기(설정, font, txt, png)
        lst.append((png, b - a))
        cur = b
    if total > cur + 1e-6:
        lst.append((blank, total - cur))
    concat = os.path.join(작업, '자막목록.txt')
    with open(concat, 'w', encoding='utf-8') as f:
        f.write('ffconcat version 1.0\n')
        for png, d in lst:
            f.write(f"file '{_따옴표(png)}'\nduration {d:.6f}\n")
        f.write(f"file '{_따옴표(lst[-1][0])}'\n")

    # ---- 1) 화면 (음성 없이)
    fade = float(설정.get('끝_페이드_초', 1.5))
    inputs, fc = [], []
    # 구간마다 원본을 따로 열고 정확한 위치로 이동합니다 (긴 원본을 처음부터 읽지 않음)
    for k, p in enumerate(pieces):
        f, off, _ = srcs[p['src']]
        inputs += ['-ss', f"{p['a'] - off:.6f}", '-t', f"{p['n'] / FPS + 0.5:.6f}", '-i', f]
    ni = len(pieces)
    inputs += ['-loop', '1', '-framerate', str(FPS), '-i', 고정]
    inputs += ['-f', 'concat', '-safe', '0', '-i', concat]
    for k, p in enumerate(pieces):
        fc.append(f"[{k}:v]setpts=PTS-STARTPTS,fps={FPS},trim=end_frame={p['n']},setpts=PTS-STARTPTS,"
                  f"crop={cw}:{ch}:{cx}:{cy},scale={W}:{L['영상_높이']}:flags=lanczos,setsar=1[v{k}]")
    fc.append(''.join(f'[v{k}]' for k in range(len(pieces))) + f'concat=n={len(pieces)}:v=1:a=0[vid]')
    fc.append(f'color=c=black:s={W}x{H}:r={FPS}:d={total + 1:.3f}[bg]')
    fc.append(f"[bg][vid]overlay=0:{L['영상_y']}:shortest=1[b1]")
    fc.append(f'[b1][{ni}:v]overlay=0:0:shortest=1[b2]')
    fc.append(f'[{ni + 1}:v]fps={FPS},format=rgba[sub]')
    fc.append(f'[b2][sub]overlay=0:0:eof_action=pass[b3]')
    vf_end = f',fade=t=out:st={max(0, (total_frames - 2) / FPS - fade):.6f}:d={fade}' if fade > 0 else ''  # 마지막 프레임은 완전히 검정
    fc.append(f'[b3]trim=end_frame={total_frames}{vf_end},format=yuv420p[vout]')
    fcfile = os.path.join(작업, '화면필터.txt')
    with open(fcfile, 'w', encoding='utf-8') as f:
        f.write(';\n'.join(fc))
    화면 = os.path.join(작업, '화면.mp4')
    알림('1/3 화면을 만드는 중입니다... (몇 분 걸릴 수 있습니다)')
    실행([ff, '-hide_banner', '-y', *inputs, '-filter_complex_script', fcfile, '-map', '[vout]', '-an',
         '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-r', str(FPS), 화면], '화면 만들기')

    # ---- 2) 음성
    알림('2/3 소리를 정리하는 중입니다...')
    af, ain = [], []
    for k, p in enumerate(pieces):
        f, off, _ = srcs[p['src']]
        d = p['n'] / FPS
        ain += ['-ss', f"{p['a'] - off:.6f}", '-t', f'{d + 0.5:.6f}', '-i', f]
        af.append(f"[{k}:a]asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,apad,atrim=end={d:.6f},asetpts=PTS-STARTPTS,"
                  f"afade=t=in:d=0.012,afade=t=out:st={max(0, d - 0.012):.6f}:d=0.012[a{k}]")
    af.append(''.join(f'[a{k}]' for k in range(len(pieces))) + f'concat=n={len(pieces)}:v=0:a=1[aout]')
    음성 = os.path.join(작업, '음성.wav')
    afile = os.path.join(작업, '음성필터.txt')
    with open(afile, 'w', encoding='utf-8') as f:
        f.write(';\n'.join(af))
    실행([ff, '-hide_banner', '-y', *ain, '-filter_complex_script', afile,
         '-map', '[aout]', '-c:a', 'pcm_s16le', 음성], '음성 정리')

    bgm = 경로(E.get('배경음악', 설정.get('배경음악')))
    섞음 = os.path.join(작업, '섞음.wav')
    if bgm and os.path.exists(bgm):
        sp, bl = 음량_LUFS(ff, 음성), 음량_LUFS(ff, bgm)
        gain = sp + float(설정['배경음악_크기_LU']) - bl
        bf = float(설정['배경음악_끝_페이드_초'])
        알림(f'  배경음악을 목소리보다 {-float(설정["배경음악_크기_LU"]):.0f} LU 작게 넣습니다.')
        실행([ff, '-hide_banner', '-y', '-i', 음성, '-stream_loop', '-1', '-i', bgm, '-filter_complex',
             f'[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=end={total:.6f},volume={gain:.2f}dB,'
             f'afade=t=out:st={max(0, total - bf):.6f}:d={bf}[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[o]',
             '-map', '[o]', '-c:a', 'pcm_s16le', 섞음], '배경음악 섞기')
    else:
        if bgm:
            알림(f'  [안내] 배경음악 파일을 찾지 못해 배경음악 없이 만듭니다: {bgm}')
        shutil.copy(음성, 섞음)

    target = float(설정['최종음량_LUFS'])
    r = subprocess.run([ff, '-hide_banner', '-i', 섞음, '-af', f'loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    m = json.loads(r.stderr[r.stderr.rfind('{'):r.stderr.rfind('}') + 1])
    ln = (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    afade = f',afade=t=out:st={max(0, (total_frames - 2) / FPS - fade):.6f}:d={fade}' if fade > 0 else ''

    # ---- 3) 합치기
    알림('3/3 화면과 소리를 합치는 중입니다...')
    완성폴더 = os.path.join(폴더, '완성')
    os.makedirs(완성폴더, exist_ok=True)
    이름 = re.sub(r'\s+', ' ', E.get('파일이름') or E.get('제목') or '쇼츠')
    이름 = re.sub(r'[\\/:*?"<>|]', '', 이름).strip() or '쇼츠'
    out = os.path.join(완성폴더, f'{이름}.mp4')
    실행([ff, '-hide_banner', '-y', '-i', 화면, '-i', 섞음, '-filter_complex', f'[1:a]{ln},aresample=48000{afade},atrim=end={total:.6f}[a]',
         '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k', '-movflags', '+faststart', '-shortest', out], '합치기')

    srt = os.path.join(완성폴더, f'{이름}.srt')
    with open(srt, 'w', encoding='utf-8') as f:
        def ts(t):
            ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); mi, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
            return f'{h:02d}:{mi:02d}:{s:02d},{ms:03d}'
        for i, (a, b, txt) in enumerate(subs, 1):
            f.write(f'{i}\n{ts(a)} --> {ts(b - 0.02)}\n{txt}\n\n')

    # 검사: 길이와 끝까지 읽히는지
    r = subprocess.run([ff, '-hide_banner', '-i', out], capture_output=True, text=True, encoding='utf-8', errors='replace')
    m = re.search(r'Duration: (\d+):(\d+):([\d.]+)', r.stderr)
    got = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0
    if abs(got - total) > 0.2:
        raise 오류(f'완성 영상 길이({got:.2f}초)가 예상({total:.2f}초)과 다릅니다. 원본 영상이 손상되었을 수 있습니다.')
    r = subprocess.run([ff, '-v', 'error', '-i', out, '-f', 'null', '-'], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.stderr.strip():
        알림('[주의] 완성 파일 검사 중 경고가 있었습니다:\n' + r.stderr[-800:])
    알림(f'\n완성! {total:.1f}초\n  영상: {out}\n  자막: {srt}')
    return out

def 미리보기_그림(폴더, 설정, E, font, pieces, srcs, subs, 고정, crop, ff):
    Image, ImageDraw, *_ = _pil()
    cx, cy, cw, ch = crop
    L = 설정['배치']
    out_dir = os.path.join(폴더, '미리보기')
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(폴더, '_작업', '_frame.png')
    picks = [pieces[0], pieces[len(pieces) // 2], pieces[-1]]
    t0s, t = [], 0.0
    for p in pieces:
        t0s.append(t); t += p['n'] / FPS
    made = []
    for idx, p in enumerate(picks, 1):
        k = pieces.index(p)
        mid = p['a'] + (p['b'] - p['a']) / 2
        f, off, _ = srcs[p['src']]
        실행([ff, '-v', 'error', '-y', '-ss', f'{mid - off:.3f}', '-i', f, '-frames:v', '1', tmp], '화면 추출')
        src = Image.open(tmp).convert('RGB')
        if idx == 1:
            g = src.copy(); d = ImageDraw.Draw(g)
            d.rectangle([cx, cy, cx + cw, cy + ch], outline=(255, 40, 40), width=5)
            d.text((cx + 10, cy + 10), '쇼츠에 들어가는 영역', fill=(255, 40, 40), font=_pil()[3].truetype(font, 36))
            g.save(os.path.join(out_dir, '원본_자르기영역.png'))
        band = src.crop((cx, cy, cx + cw, cy + ch)).resize((W, L['영상_높이']), Image.LANCZOS)
        im = Image.new('RGBA', (W, H), (0, 0, 0, 255))
        im.paste(band, (0, L['영상_y']))
        im.alpha_composite(Image.open(고정))
        tl = t0s[k] + (mid - p['a'])
        txt = next((s[2] for s in subs if s[0] <= tl < s[1]), '')
        if txt:
            sub = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            글자_그리기(sub, txt, (W / 2, L['자막_y']), font, L['자막_크기'], 설정['색']['자막'], spacing=L['자막_줄간격'])
            im.alpha_composite(sub)
        pth = os.path.join(out_dir, f'미리보기_{idx}.png')
        im.convert('RGB').save(pth)
        made.append(pth)
    알림('미리보기 그림을 만들었습니다:\n  ' + '\n  '.join(made + [os.path.join(out_dir, '원본_자르기영역.png')]))
    return made

# ---------------------------------------------------------------- 점검
def 점검():
    ok = True
    알림(f'설교 쇼츠 도구 v{VERSION} 점검')
    알림(f'  Python {sys.version.split()[0]}  ' + ('OK' if sys.version_info >= (3, 9) else '→ 3.9 이상이 필요합니다'))
    for mod, name in [('PIL', 'Pillow'), ('imageio_ffmpeg', 'imageio-ffmpeg'), ('yt_dlp', 'yt-dlp')]:
        try:
            __import__(mod); 알림(f'  {name}: OK')
        except ImportError:
            ok = False; 알림(f'  {name}: 없음 → 설치 파일을 실행해 주세요')
    try:
        알림(f'  FFmpeg: OK ({os.path.basename(ffmpeg_경로())})')
    except 오류 as e:
        ok = False; 알림(f'  FFmpeg: {e}')
    설정 = 설정_읽기()
    try:
        알림(f'  글꼴: {os.path.basename(글꼴_찾기(설정))}')
    except 오류 as e:
        ok = False; 알림(f'  글꼴: {e}')
    logo = 경로(설정.get('로고'))
    알림(f'  로고: ' + (os.path.basename(logo) if logo and os.path.exists(logo) else '없음 (로고 없이 만듭니다)'))
    bgm = 경로(설정.get('배경음악'))
    알림(f'  배경음악: ' + (os.path.basename(bgm) if bgm and os.path.exists(bgm) else '없음 (배경음악 없이 만듭니다)'))
    알림('  모두 준비되었습니다.' if ok else '  위의 항목을 해결한 뒤 다시 실행해 주세요.')
    return ok

# ---------------------------------------------------------------- 메뉴
def 회차폴더(이름):
    p = os.path.expanduser(이름)
    if os.path.isabs(p) or os.path.exists(p):
        return os.path.abspath(p)
    return os.path.join(HERE, '회차', 이름)

def 메뉴():
    알림('\n=== 설교 쇼츠 만들기 ===')
    알림('1. 대본 받기 (유튜브 주소 입력)\n2. 미리보기 그림 만들기\n3. 쇼츠 영상 만들기\n4. 설치 점검\n0. 끝내기')
    c = input('번호를 입력하세요: ').strip()
    if c == '1':
        url = input('설교 영상 유튜브 주소: ').strip()
        name = input('회차 폴더 이름 (예: 2026-10-23_그이름을위하여): ').strip()
        대본_받기(url, 회차폴더(name))
        알림('\n다음 단계: 「AI편집요청문.txt」와 대본.txt·단어시간.txt를 AI에게 주고 받은 내용을 회차.json 에 저장하세요.')
    elif c in ('2', '3'):
        base = os.path.join(HERE, '회차')
        names = sorted([d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]) if os.path.isdir(base) else []
        for i, n in enumerate(names, 1):
            알림(f'  {i}. {n}')
        s = input('회차 번호 또는 폴더 이름: ').strip()
        folder = os.path.join(base, names[int(s) - 1]) if s.isdigit() and 0 < int(s) <= len(names) else 회차폴더(s)
        만들기(folder, 미리보기만=(c == '2'))
    elif c == '4':
        점검()

def main():
    if len(sys.argv) == 1:
        try:
            메뉴()
        except 오류 as e:
            알림(f'\n[문제] {e}')
        except KeyboardInterrupt:
            pass
        if sys.stdin and sys.stdin.isatty():
            input('\n엔터를 누르면 창이 닫힙니다.')
        return
    ap = argparse.ArgumentParser(description='설교 쇼츠 만들기 도구')
    sp = ap.add_subparsers(dest='cmd')
    sp.add_parser('점검')
    p1 = sp.add_parser('대본'); p1.add_argument('url'); p1.add_argument('folder')
    p2 = sp.add_parser('미리보기'); p2.add_argument('folder')
    p3 = sp.add_parser('만들기'); p3.add_argument('folder')
    a = ap.parse_args()
    try:
        if a.cmd == '점검':
            sys.exit(0 if 점검() else 1)
        elif a.cmd == '대본':
            대본_받기(a.url, 회차폴더(a.folder))
        elif a.cmd in ('미리보기', '만들기'):
            만들기(회차폴더(a.folder), 미리보기만=(a.cmd == '미리보기'))
        else:
            ap.print_help()
    except 오류 as e:
        알림(f'\n[문제] {e}')
        sys.exit(1)

if __name__ == '__main__':
    main()
