import io

import pytest
from PIL import Image

from app.services.asset_library import _make_thumbnail, _process_image


def _png_bytes(size=(80, 60)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, color=(200, 30, 30)).save(output, format="PNG")
    return output.getvalue()


def test_process_image_valid_png():
    data = _png_bytes()
    processed, image_format, width, height = _process_image("image/png", data)

    assert image_format == "PNG"
    assert width == 80
    assert height == 60
    assert processed


def test_process_image_rejects_wrong_type():
    with pytest.raises(ValueError):
        _process_image("text/plain", b"not an image")


def test_process_image_rejects_invalid_content():
    with pytest.raises(ValueError):
        _process_image("image/png", b"invalid image bytes")


def test_make_thumbnail():
    processed, image_format, _width, _height = _process_image(
        "image/png",
        _png_bytes((1200, 900)),
    )
    thumbnail = _make_thumbnail(processed, image_format)

    assert thumbnail
    output = io.BytesIO(thumbnail)
    thumb = Image.open(output)
    assert thumb.size <= (400, 400)
