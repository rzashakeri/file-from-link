import importlib.util, json, os, stat, sys, tempfile, types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class _FakeFlow:
    def __init__(self, store, code_verifier=None):
        self.store = store
        self.redirect_uri = None
        self.code_verifier = code_verifier
        self.credentials = types.SimpleNamespace(refresh_token="refresh-xyz")
    def authorization_url(self, prompt=None, access_type=None, **kwargs):
        self.store["auth_url_args"] = (prompt, access_type)
        self.store["auth_url_kwargs"] = kwargs
        return ("https://accounts.google.com/o/oauth2/auth?client_id=CLIENTID&x=1", None)
    def fetch_token(self, code=None, **kwargs):
        self.store["code"] = code
        self.store["fetch_kwargs"] = kwargs

def _stub_oauthlib(store):
    pkg = types.ModuleType("google_auth_oauthlib")
    flow_mod = types.ModuleType("google_auth_oauthlib.flow")
    class _InstalledAppFlow:
        @staticmethod
        def from_client_config(config, scopes, **kwargs):
            store["client_config"] = config
            store["scopes"] = scopes
            store["flow_kwargs"] = kwargs
            return _FakeFlow(store, code_verifier=kwargs.get("code_verifier"))
    flow_mod.InstalledAppFlow = _InstalledAppFlow
    pkg.flow = flow_mod
    sys.modules.update({"google_auth_oauthlib": pkg,
                        "google_auth_oauthlib.flow": flow_mod})

def _setup_tmp(mod, store, tmp):
    client = Path(tmp) / "client.json"
    client.write_text(json.dumps(
        {"client_id": "CLIENTID", "client_secret": "SECRET"}))
    mod.CLIENT_PATH = client
    mod.TOKEN_PATH = Path(tmp) / "token.json"
    mod.VERIFIER_PATH = Path(tmp) / "verifier.txt"
    mod.CHALLENGE_PATH = Path(tmp) / "challenge.txt"
    return client

def test_missing_client_config_returns_2():
    mod = _load("drive_authorize", "ops/drive_authorize.py")
    mod.CLIENT_PATH = Path("/nonexistent/oauth-client.json")
    assert mod.main(["drive_authorize.py", "--auth-url"]) == 2
    assert mod.main(["drive_authorize.py", "--code", "abc"]) == 2
    assert mod.main(["drive_authorize.py"]) == 2

def test_exchange_without_verifier_returns_2():
    mod = _load("drive_authorize", "ops/drive_authorize.py")
    store = {}
    _stub_oauthlib(store)
    with tempfile.TemporaryDirectory() as tmp:
        _setup_tmp(mod, store, tmp)
        assert mod.main(["drive_authorize.py", "--code", "abc"]) == 2
        assert "code" not in store

def test_code_challenge_is_rfc7636_s256():
    mod = _load("drive_authorize", "ops/drive_authorize.py")
    # RFC 7636 Appendix B example
    assert mod.code_challenge(
        "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == (
        "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
    verifier = mod.new_verifier()
    assert 43 <= len(verifier) <= 128
    assert all(c.isalnum() or c in "-._~" for c in verifier)

def test_auth_url_saves_verifier_and_challenge_and_exchange_uses_it():
    mod = _load("drive_authorize", "ops/drive_authorize.py")
    store = {}
    _stub_oauthlib(store)
    with tempfile.TemporaryDirectory() as tmp:
        _setup_tmp(mod, store, tmp)
        url = mod.auth_url()
        assert url.startswith("https://accounts.google.com/o/oauth2/auth")
        assert "CLIENTID" in url
        assert store["auth_url_args"] == ("consent", "offline")
        assert store["client_config"]["installed"]["client_id"] == "CLIENTID"
        assert store["client_config"]["installed"]["redirect_uris"] == [
            "http://localhost:8080/"]
        assert store["scopes"] == ["https://www.googleapis.com/auth/drive.file"]
        # verifier + challenge persisted (mode 600) by the --auth-url step,
        # and the challenge is the S256 of the saved verifier
        verifier = mod.VERIFIER_PATH.read_text()
        challenge = mod.CHALLENGE_PATH.read_text()
        assert challenge == mod.code_challenge(verifier)
        assert stat.S_IMODE(mod.VERIFIER_PATH.stat().st_mode) == 0o600
        assert stat.S_IMODE(mod.CHALLENGE_PATH.stat().st_mode) == 0o600
        # the explicit verifier/challenge reach the flow (not the lib's own)
        assert store["auth_url_kwargs"]["code_challenge"] == challenge
        assert store["auth_url_kwargs"]["code_challenge_method"] == "S256"
        assert store["flow_kwargs"]["code_verifier"] == verifier
        path = mod.exchange("CODE-123")
        assert path == mod.TOKEN_PATH
        assert store["code"] == "CODE-123"
        # the --code step passes the SAME verifier back to the flow
        assert store["flow_kwargs"]["code_verifier"] == verifier
        saved = json.loads(mod.TOKEN_PATH.read_text())
        assert saved == {"client_id": "CLIENTID", "client_secret": "SECRET",
                         "refresh_token": "refresh-xyz",
                         "type": "authorized_user"}
        assert stat.S_IMODE(mod.TOKEN_PATH.stat().st_mode) == 0o600

def test_exchange_with_mismatched_verifier_refuses_without_fetch():
    mod = _load("drive_authorize", "ops/drive_authorize.py")
    store = {}
    _stub_oauthlib(store)
    with tempfile.TemporaryDirectory() as tmp:
        _setup_tmp(mod, store, tmp)
        mod.auth_url()
        # tamper: verifier no longer matches the saved challenge
        mod.VERIFIER_PATH.write_text(mod.new_verifier())
        assert mod.main(["drive_authorize.py", "--code", "CODE-123"]) == 2
        assert "code" not in store  # fetch_token never called: code unspent
