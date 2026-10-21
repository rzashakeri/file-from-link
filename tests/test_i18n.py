import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("BOT_TOKEN", "dummy")
from app.i18n import STRINGS, t, fmt_label
from app.utils import FORMAT_ORDER
def test_same_keys_all_languages():
    langs = list(STRINGS.values())
    keys = set(langs[0].keys())
    for d in langs[1:]: assert set(d.keys()) == keys
def test_placeholders_format():
    for lang in STRINGS:
        t(lang, "queued", pos=2, jid="abc"); t(lang, "quality_question", url="https://x")
        t(lang, "downloading", pct=42); t(lang, "done", title="v"); t(lang, "failed", error="e")
        t(lang, "too_big", title="v", mb=80, hours=24, url="https://l")
        for k in FORMAT_ORDER: assert fmt_label(lang, k)
def test_fallback():
    assert t("xx-unknown", "no_url") == t("en", "no_url")
