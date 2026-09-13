import os, sys, time, base64
from pathlib import Path
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")
print("=== CI Perchance Live Diagnostics ===")

# Add project root
sys.path.insert(0, os.getcwd())

from cloud_generator.image_engines.perchance_engine import _get_browser_page, find_chromium_path, _crop_fill

print(f"Detected Chromium Binary: {find_chromium_path()}")
print(f"DISPLAY env var: {os.environ.get('DISPLAY')}")

os.makedirs("debug_output", exist_ok=True)

try:
    page = _get_browser_page()
    print("Browser page initialized!")
    tab = page.new_tab("https://perchance.org/ai-text-to-image-generator")
    print(f"Navigated to Perchance. Tab title: {tab.title}, URL: {tab.url}")
    time.sleep(4)

    tab.get_screenshot(path="debug_output/01_initial_tab.png")
    print("Saved 01_initial_tab.png")

    iframes = tab.eles("tag:iframe")
    print(f"Total top-level iframes: {len(iframes)}")
    for i, ifr in enumerate(iframes):
        try:
            f = tab.get_frame(ifr)
            print(f"  Iframe {i}: url={f.url}")
        except Exception as e:
            print(f"  Iframe {i} error: {e}")

    gen_frame = tab.get_frame("@src:ai-text-to-image-generator")
    print(f"gen_frame found: {bool(gen_frame)}")

    if not gen_frame:
        print("FATAL: gen_frame not found!")
        sys.exit(1)

    gen_frame.get_screenshot(path="debug_output/02_gen_frame.png")
    print("Saved 02_gen_frame.png")

    # Set style & shape
    gen_frame.run_js("""
        let selects = document.querySelectorAll('select');
        if (selects.length >= 2) {
            selects[0].value = 'ref:optionKeyName:Painted Anime';
            selects[0].dispatchEvent(new Event('change', { bubbles: true }));
            selects[1].value = '512x768';
            selects[1].dispatchEvent(new Event('change', { bubbles: true }));
        }
    """)

    tas = gen_frame.eles("tag:textarea")
    print(f"Textareas in gen_frame: {len(tas)}")
    prompt = "Breathtaking scenic mountain landscape, Studio Ghibli background art aesthetic, lush green hills, soft morning sunlight, wide angle vista"
    tas[-1].input(prompt, clear=True)

    btn = gen_frame.ele("#generateButtonEl") or gen_frame.ele("text=✨ generate")
    print(f"Generate button found: {bool(btn)}")
    btn.click()
    print("Clicked generate! Polling nested iframes...")

    result_bytes = None
    for sec in range(30):
        time.sleep(1)
        nested = gen_frame.eles("tag:iframe")
        print(f"Sec {sec+1}: {len(nested)} nested iframes in gen_frame")
        for i, nf in enumerate(nested):
            try:
                n_fr = gen_frame.get_frame(nf)
                print(f"   Nested {i} URL: {n_fr.url[:80]}")
                n_fr.get_screenshot(path=f"debug_output/nested_{i}_sec{sec+1}.png")
                
                # Check for Turnstile checkbox if present and auto-click it
                turnstile_res = n_fr.run_js("""
                    try {
                        let cb = document.querySelector('input[type="checkbox"], .ctp-checkbox-label, [name="cf-turnstile-response"]');
                        if (cb) {
                            cb.click();
                            return 'clicked_turnstile';
                        }
                    } catch(e) {}
                    return null;
                """)
                if turnstile_res:
                    print(f"   Nested {i} Turnstile detected & clicked!")

                img = n_fr.ele("#resultImgEl")
                if img:
                    src = img.attr("src") or ""
                    print(f"   Nested {i} has #resultImgEl! src prefix: {src[:40]}")
                    if src.startswith("data:image/"):
                        b64 = src.split(",", 1)[1]
                        result_bytes = base64.b64decode(b64)
                        break
            except Exception as e:
                print(f"   Nested {i} inspection error: {e}")
        if result_bytes:
            print(f"SUCCESS: Image extracted at sec {sec+1}!")
            break

    if result_bytes:
        out_path = "debug_output/final_image.png"
        with open(out_path, "wb") as f:
            f.write(result_bytes)
        img = Image.open(out_path)
        cropped = _crop_fill(img, 1080, 1920)
        cropped.save("debug_output/final_image_1080x1920.png", "PNG")
        print(f"Saved final image: {len(result_bytes)} bytes!")
        sys.exit(0)
    else:
        print("FAILED: No image extracted after 30s")
        sys.exit(1)

except Exception as e:
    print(f"Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
