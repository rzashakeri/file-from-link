import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("BOT_TOKEN", "dummy")
from app.i18n import LANGUAGES, STRINGS, t, fmt_label
from app.utils import FORMAT_ORDER
def test_same_keys_all_languages():
    assert list(LANGUAGES) == ["en", "fa", "ru", "ar", "zh"]
    assert set(STRINGS) == set(LANGUAGES)
    keys = set(STRINGS["en"].keys())
    for lang, d in STRINGS.items(): assert set(d.keys()) == keys, lang
def test_no_empty_translations():
    for lang, d in STRINGS.items():
        for key, value in d.items(): assert value.strip(), (lang, key)
def test_language_labels_are_localized():
    for lang in STRINGS:
        assert t(lang, "language_button") and t(lang, "language_set")
    assert len({STRINGS[l]["language_set"] for l in STRINGS}) == len(STRINGS)
def test_placeholders_format():
    for lang in STRINGS:
        t(lang, "queued", pos=2, jid="abc"); t(lang, "quality_question", url="https://x")
        t(lang, "downloading", pct=42); t(lang, "done", title="v"); t(lang, "failed", error="e")
        t(lang, "too_big", title="v", mb=80, hours=24, url="https://l")
        t(lang, "direct_link", url="https://l")
        t(lang, "stats", users=1, jobs=2, today=3, done=4, failed=5, storage="1 MB")
        t(lang, "broadcast_confirm", n=1); t(lang, "broadcast_started", n=1)
        t(lang, "broadcast_progress", ok=1, blocked=2, failed=3, n=6)
        t(lang, "broadcast_done", ok=1, blocked=2, failed=3)
        for k in FORMAT_ORDER: assert fmt_label(lang, k)
def test_fallback():
    assert t("xx-unknown", "no_url") == t("en", "no_url")
