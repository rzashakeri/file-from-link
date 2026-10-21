import os, sys, time, pathlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("BOT_TOKEN", "dummy")
def test_sweep_removes_only_expired(tmp_path=None):
    import tempfile
    from unittest import mock
    d = pathlib.Path(tempfile.mkdtemp())
    old = d/"oldtoken"; old.mkdir(); (old/"v.mp4").write_bytes(b"x")
    new = d/"newtoken"; new.mkdir(); (new/"v.mp4").write_bytes(b"x")
    past = time.time() - 25*3600
    os.utime(old, (past, past))
    with mock.patch("app.cleanup.PUBLIC_DIR", d):
        from app.cleanup import sweep_public
        assert sweep_public(24) == 1
    assert not old.exists() and new.exists()
