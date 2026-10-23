"""횡성 1박 2일 일정표의 '사진' 칸에 장소 사진을 넣어 주는 스크립트.

사용법 (엑셀 파일과 같은 폴더에서):
    pip install openpyxl pillow
    python add_photos.py                 # → 횡성_한우_단풍_1박2일_사진포함.xlsx 생성
    python add_photos.py 다른이름.xlsx

사진은 photo_key(일정표 숨김 K열) 기준으로 이렇게 고릅니다.
  1) photos/<photo_key>.jpg / .jpeg / .png 파일이 있으면 그 사진 (직접 고른 사진으로 바꾸고 싶을 때)
  2) 없으면 위키미디어 공용(Wikimedia Commons, 자유 라이선스)에서 검색해 photos/에 내려받아 사용
     출처·라이선스는 사진 칸의 메모와 photos/<photo_key>.txt에 남깁니다.
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.utils import column_index_from_string
from openpyxl.utils.units import pixels_to_EMU
from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "횡성_한우_단풍_1박2일.xlsx"
OUT = SRC.with_name(SRC.stem + "_사진포함.xlsx")
PHOTO_DIR = HERE / "photos"
SHEET, PHOTO_COL, KEY_COL = "일정표", "H", "K"
PAD = 4  # 셀 테두리와 사진 사이 여백(px)

# photo_key → 위키미디어 공용 검색어 (앞에서부터 차례로 시도)
QUERIES = {
    "birch": ["미술관 자작나무숲", "Hoengseong birch", "Betula platyphylla forest autumn"],
    "hanwoo": ["Hoengseong hanu beef", "Hanwoo beef"],
    "hosugil": ["횡성호수길", "횡성호", "Hoengseong Dam"],
    "hanwoo_bbq": ["Korean barbecue Hoenggye hanu", "Hanwoo galbi"],
    "seomgang": ["섬강 횡성", "Seomgang River"],
    "haejang": ["Haejangguk", "해장국"],
    "guryongsa": ["Guryongsa Wonju", "Autumn in Chiak Mountain", "치악산 단풍"],
    "sanchae": ["Sanchae bibimbap", "산채비빔밥"],
    "pungsuwon": ["Pungsuwon Catholic Church", "풍수원성당"],
}
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "hoengseong-trip-photos/1.0 (personal travel itinerary script)"}


def get(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def commons_search(query):
    """검색 결과 중 첫 jpg/png의 (썸네일 URL, 출처 문구)를 돌려준다."""
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 5,
        "prop": "imageinfo", "iiprop": "url|mime|extmetadata", "iiurlwidth": 800,
        "iiextmetadatafilter": "Artist|LicenseShortName",
    }
    data = json.loads(get(API + "?" + urllib.parse.urlencode(params)))
    pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        if info.get("mime") in ("image/jpeg", "image/png") and info.get("thumburl"):
            meta = info.get("extmetadata", {})
            artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()
            lic = meta.get("LicenseShortName", {}).get("value", "")
            credit = f"{p['title'].removeprefix('File:')} — {artist or '작성자 미상'}, {lic} (Wikimedia Commons)"
            return info["thumburl"], credit, info.get("descriptionurl", "")
    return None


def find_photo(key):
    """(사진 경로, 출처 문구)를 돌려준다. 못 찾으면 (None, 사유)."""
    for ext in (".jpg", ".jpeg", ".png"):
        p = PHOTO_DIR / f"{key}{ext}"
        if p.exists():
            note = PHOTO_DIR / f"{key}.txt"
            return p, note.read_text(encoding="utf-8") if note.exists() else "직접 넣은 사진"
    PHOTO_DIR.mkdir(exist_ok=True)
    reason = "검색 결과 없음"
    for q in QUERIES.get(key, []):
        try:
            hit = commons_search(q)
            if not hit:
                continue
            url, credit, page = hit
            p = PHOTO_DIR / (f"{key}.png" if url.lower().endswith(".png") else f"{key}.jpg")
            p.write_bytes(get(url, timeout=60))
            (PHOTO_DIR / f"{key}.txt").write_text(f"{credit}\n{page}", encoding="utf-8")
            return p, f"{credit}\n{page}"
        except Exception as e:  # 네트워크 오류 등은 다음 검색어로
            reason = f"다운로드 실패: {e}"
    return None, reason


def cell_px(ws, col, row):
    width = ws.column_dimensions[col].width or 8.43
    height = ws.row_dimensions[row].height or 15
    return int(width * 7 + 5), int(height * 96 / 72)


def fitted(path, w, h):
    """셀 비율에 맞춰 가운데를 잘라내고 2배 해상도로 줄인 JPG 경로."""
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    im = ImageOps.fit(im, (w * 2, h * 2), Image.LANCZOS)
    out = PHOTO_DIR / "_cell" / f"{path.stem}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, quality=88)
    return out


def main():
    wb = load_workbook(SRC)
    ws = wb[SHEET]
    col_idx = column_index_from_string(PHOTO_COL)
    done, missing = [], []
    for row in range(1, ws.max_row + 1):
        key = ws[f"{KEY_COL}{row}"].value
        if not key or key == "photo_key":  # 빈 칸·헤더 건너뛰기
            continue
        place = ws[f"E{row}"].value
        path, credit = find_photo(key)
        if not path:
            missing.append(f"{place} ({key}): {credit}")
            continue
        w, h = cell_px(ws, PHOTO_COL, row)
        w, h = w - 2 * PAD, h - 2 * PAD
        img = XLImage(str(fitted(path, w, h)))
        img.anchor = OneCellAnchor(
            _from=AnchorMarker(col=col_idx - 1, colOff=pixels_to_EMU(PAD), row=row - 1, rowOff=pixels_to_EMU(PAD)),
            ext=XDRPositiveSize2D(pixels_to_EMU(w), pixels_to_EMU(h)),
        )
        ws.add_image(img)
        cell = ws[f"{PHOTO_COL}{row}"]
        cell.value, cell.hyperlink = None, None  # 안내 문구 대신 사진 (J열 '사진' 링크는 그대로)
        cell.comment = Comment(f"사진 출처: {credit}", "add_photos.py", width=320, height=90)
        done.append(place)

    wb.calculation.fullCalcOnLoad = True
    wb.save(OUT)
    print(f"사진 {len(done)}장 삽입 → {OUT.name}")
    for m in missing:
        print("  - 못 넣음:", m)
    if missing:
        print(f"  ※ 원하는 사진을 {PHOTO_DIR.name}/<photo_key>.jpg 로 저장하고 다시 실행하면 그 사진이 들어갑니다.")


if __name__ == "__main__":
    main()
