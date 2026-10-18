"""Record a demo GIF of the running web UI with Playwright.

Usage:  python scripts/record_demo.py --url http://127.0.0.1:8000 --out docs/demo.gif

The scenario below drives the real UI against the running server. If the page
shows no real results, the script exits with an error instead of writing a
GIF, so an empty or broken demo is never committed.
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import Page, sync_playwright

WIDTH, HEIGHT = 1200, 760
OUT_WIDTH = 900


class Recorder:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.frames: list[list] = []  # [image, duration_ms]

    def snap(self, ms: int = 100) -> None:
        png = self.page.screenshot(type="png")
        img = Image.open(io.BytesIO(png)).convert("RGB")
        img = img.resize((OUT_WIDTH, round(img.height * OUT_WIDTH / img.width)), Image.LANCZOS)
        if self.frames and ImageChops.difference(img, self.frames[-1][0]).getbbox() is None:
            self.frames[-1][1] += ms  # identical frame: extend the previous one
        else:
            self.frames.append([img, ms])

    def hold(self, seconds: float, every: float = 0.35) -> None:
        end = time.time() + seconds
        while time.time() < end:
            self.snap(int(every * 1000))
            time.sleep(every)

    def type(self, selector: str, text: str) -> None:
        self.page.click(selector)
        for ch in text:
            self.page.type(selector, ch)
            self.snap(70)

    def save(self, path: Path) -> None:
        if len(self.frames) < 2:
            raise SystemExit("too few frames captured")
        # One shared palette for every frame avoids colour shifts and partial-frame artifacts.
        w, h = self.frames[0][0].size
        sample = Image.new("RGB", (w, h * min(len(self.frames), 6)))
        step = max(1, len(self.frames) // 6)
        for k, f in enumerate(self.frames[::step][:6]):
            sample.paste(f[0], (0, h * k))
        palette = sample.quantize(colors=192, method=Image.Quantize.MEDIANCUT)
        imgs = [f[0].quantize(palette=palette, dither=Image.Dither.NONE) for f in self.frames]
        durations = [max(40, min(f[1], 4000)) for f in self.frames]
        durations[-1] = 2500  # linger on the final frame
        path.parent.mkdir(parents=True, exist_ok=True)
        imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=durations, loop=0,
                     optimize=False, disposal=1)
        print(f"wrote {path} ({len(imgs)} frames, {path.stat().st_size // 1024} KiB)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default="docs/demo.gif")
    a = ap.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, color_scheme="light")
        rec = Recorder(page)
        try:
            scenario(page, rec, a.url.rstrip("/"))  # noqa: F821 - defined below per project
        except Exception as e:
            page.screenshot(path="demo-failure.png")
            print(f"demo scenario failed: {e}", file=sys.stderr)
            raise SystemExit(1) from e
        finally:
            browser.close()
        rec.save(Path(a.out))


def scenario(page: Page, rec: Recorder, url: str) -> None:
    page.goto(url + "/")
    page.wait_for_selector("input[name=q]")
    rec.hold(0.8)
    rec.type("input[name=q]", "open source search engine")
    page.check("input[name=answer]")
    rec.snap(400)
    page.press("input[name=q]", "Enter")
    rec.hold(0.6, every=0.2)
    page.wait_for_selector("#out .r", timeout=30000)
    n = page.locator("#out .r").count()
    if n < 3:
        raise RuntimeError(f"only {n} results came back; engines may be blocked")
    rec.hold(2.5)
    page.mouse.wheel(0, 500)
    rec.hold(1.5)
    page.mouse.wheel(0, 500)
    rec.hold(1.5)


if __name__ == "__main__":
    main()
