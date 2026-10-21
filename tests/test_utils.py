from app.utils import extract_urls, format_selector, FORMATS
def test_extract():
    assert extract_urls("ببین https://youtu.be/abc123 و این https://x.com/a/status/1.") == ["https://youtu.be/abc123", "https://x.com/a/status/1"]
    assert extract_urls("بدون لینک") == []
def test_formats():
    for k in FORMATS: assert format_selector(k)
    assert "height<=720" in format_selector("720")
    assert format_selector("???") == format_selector("best")
