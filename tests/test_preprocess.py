from PIL import Image, ImageDraw, ImageFilter, ImageFont

from usefultext.preprocess import downscale, rotate, rotated_size, sharpness_score, write_preview


def _text_page(w=1200, h=1600):
    img = Image.new("L", (w, h), 245)
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=36)
    for i in range(20):
        d.text(
            (100, 100 + i * 60), "The iceberg had been there for many years.", fill=20, font=font
        )
    return img.convert("RGB")


def test_sharpness_drops_with_blur_and_ignores_text_amount():
    sharp = _text_page()
    blurred = sharp.filter(ImageFilter.GaussianBlur(3))
    sparse = Image.new("RGB", sharp.size, (245, 245, 245))
    sparse.paste(sharp.crop((0, 0, 1200, 400)), (0, 0))  # same crispness, a third of the text
    s_sharp, s_blur, s_sparse = (sharpness_score(i) for i in (sharp, blurred, sparse))
    assert s_sharp > 2 * s_blur
    assert abs(s_sparse - s_sharp) / s_sharp < 0.25


def test_downscale_and_rotate():
    img = Image.new("RGB", (4000, 3000))
    small, scale = downscale(img, 2500)
    assert small.size == (2500, 1875) and abs(scale - 0.625) < 1e-9
    assert downscale(small, 2500)[1] == 1.0
    assert rotate(small, 90).size == rotated_size(small.size, 90) == (1875, 2500)
    assert rotate(small, 180).size == (2500, 1875)


def test_write_preview_is_upright_and_small(tmp_path):
    img = Image.new("RGB", (300, 200), "white")
    path = tmp_path / "previews" / "p1.jpg"
    size = write_preview(img, path, rotation=90, long_edge=150, quality=70)
    assert size == (100, 150) and path.exists()
    with Image.open(path) as saved:
        assert saved.size == (100, 150)
