from zb_studio.image_fetch import drive_id,image_url,fetch_image
import pytest

def test_drive_share_link_id():
    assert drive_id('https://drive.google.com/file/d/abc_123-X/view?usp=sharing')=='abc_123-X'
    assert drive_id('https://drive.google.com/open?id=abc123')=='abc123'
    assert drive_id('https://drive.google.com/drive/folders/abc123') is None
    assert drive_id('https://evil.test/file/d/abc/view') is None

def test_image_formula():
    assert image_url('=IMAGE("https://example.com/a.png", 1)')=='https://example.com/a.png'

def test_drive_thumbnail_uses_image_endpoint(monkeypatch):
    import zb_studio.image_fetch as f
    seen=[]
    monkeypatch.setattr(f,'public_bytes',lambda url:seen.append(url) or b'png')
    assert fetch_image('https://drive.google.com/file/d/abc123/view')==b'png'
    assert seen==['https://drive.google.com/thumbnail?id=abc123&sz=w640']

def test_missing_image_is_explicit():
    with pytest.raises(ValueError,match='为空'):fetch_image('')
