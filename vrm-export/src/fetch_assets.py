#!/usr/bin/env python3
"""
fetch_assets.py — скачивает фотографии объявлений и вшивает их в отчёт.

    python3 fetch_assets.py

Всё. Ни pip, ни зависимостей — только стандартная библиотека Python.
Результат: report_offline.html, где все снимки лежат ВНУТРИ файла.

ПОЧЕМУ ЭТО НУЖНО
Отчёт собирается в облаке, у которого нет доступа к alonhadat.com.vn и
cdn.chotot.com — прокси эти домены режет. Поэтому в report.html фотографии
стоят ссылками, а просмотрщик в мобильном приложении внешние картинки не
грузит: вместо снимка видна подпись «Фото ↗».
Проверено 12.08.2026: тот же просмотрщик ОТЛИЧНО показывает картинки,
вшитые в файл через data:-URL. Значит достаточно один раз скачать снимки
на машине, где интернет до вьетнамских сайтов есть, — и отчёт станет
полноценным где угодно, хоть в самолёте.

ФЛАГИ
    --links       положить снимки в assets/ и сослаться на папку
                  (файл лёгкий, но таскать надо вместе с папкой)
    --max 1400    ужать до N пикселей по ширине, если стоит Pillow
    --report ...  другой входной файл вместо report.html
"""
import argparse
import base64
import io
import json
import mimetypes
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:                       # необязательно: без Pillow просто не ужимаем
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

HERE = Path(__file__).parent
MANIFEST = HERE / "photos_manifest.json"
REPORT = HERE / "report.html"
ASSETS = HERE / "assets"
TIMEOUT = 25

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def fetch(url, referer):
    """Referer ставим на страницу объявления — многие хосты режут хотлинк
    именно по нему, и запрос «как будто из галереи» проходит."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "image/avif,image/webp,image/jpeg,image/png,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        "Referer": referer,
    })
    # Некоторые вьетнамские хосты отдают неполную цепочку сертификатов;
    # проверка тут ничего не защищает — картинки и так публичные.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
        ctype = r.headers.get("Content-Type", "")
        if not ctype.startswith("image/"):
            raise ValueError(f"отдали не картинку, а {ctype or 'ничего'}")
        return r.read(), ctype


def shrink(data, ctype, max_w):
    if not HAVE_PIL or not max_w:
        return data, ctype
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
        if im.mode in ("RGBA", "P", "LA"):
            im = im.convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82, optimize=True, progressive=True)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return data, ctype


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--links", action="store_true",
                    help="снимки в папку assets/ вместо вшивания в файл")
    ap.add_argument("--max", type=int, default=1400,
                    help="ужать по ширине, если стоит Pillow (0 — не жать)")
    ap.add_argument("--report", default=str(REPORT))
    args = ap.parse_args()

    if not MANIFEST.exists():
        sys.exit(f"Рядом нет {MANIFEST.name} — он лежит в архиве вместе с отчётом")
    report_path = Path(args.report)
    if not report_path.exists():
        sys.exit(f"Нет файла {report_path}")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    html = report_path.read_text(encoding="utf-8")
    total = sum(len(e["photos"]) for e in manifest)
    if not total:
        sys.exit("В манифесте нет ни одной фотографии — скачивать нечего")

    if args.links:
        ASSETS.mkdir(exist_ok=True)
    if not HAVE_PIL:
        print("Pillow не найден — снимки пойдут в исходном размере.")
        print("Хотите файл полегче:  pip install pillow\n")

    repl, done, failed = {}, 0, []
    for entry in manifest:
        for n, url in enumerate(entry["photos"]):
            label = f'{entry["id"]}_{n}'
            try:
                data, ctype = fetch(url, entry["listing_url"])
                data, ctype = shrink(data, ctype, args.max)
            except Exception as e:
                failed.append((label, str(e)[:70]))
                print(f"  ✗ {label}: {e}")
                continue
            if args.links:
                ext = (mimetypes.guess_extension(ctype.split(";")[0]) or ".jpg").replace(".jpe", ".jpg")
                (ASSETS / f"{label}{ext}").write_bytes(data)
                repl[url] = f"assets/{label}{ext}"
            else:
                repl[url] = f"data:{ctype};base64," + base64.b64encode(data).decode("ascii")
            done += 1
            print(f"  ✓ {label}  ({len(data)//1024} КБ)")

    if not done:
        sys.exit("\nНи одной картинки не скачалось. Откройте любую ссылку из "
                 "photos_manifest.json в браузере: если и там не открывается — "
                 "хост закрыл доступ, и дело не в скрипте.")

    # Длинные URL меняем первыми, чтобы короткий не съел кусок длинного
    for url in sorted(repl, key=len, reverse=True):
        html = html.replace(url, repl[url])

    out = report_path.with_name("report_local.html" if args.links else "report_offline.html")
    out.write_text(html, encoding="utf-8")
    size = out.stat().st_size / 1024 / 1024

    print(f"\nСкачано {done} из {total}" + (f", не вышло {len(failed)}" if failed else ""))
    print(f"Готово: {out.name}  ({size:.1f} МБ)")
    if args.links:
        print("Держите файл рядом с папкой assets/, иначе фото не найдутся.")
    else:
        print("Это один самодостаточный файл — киньте его на телефон, "
              "фотографии будут видны прямо в подборке.")


if __name__ == "__main__":
    main()
