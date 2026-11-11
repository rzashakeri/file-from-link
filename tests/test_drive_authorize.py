import importlib.util, json, os, stat, sys, tempfile, types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class _FakeFlow:
    def __init__(self, store):
        self.store = store
        self.redirect_uri = None
        self.credentials = types.SimpleNamespace(refresh_token="refresh-xyz")
    def authorization_url(self, prompt=None, access_type=None):
        self.store["auth_url_args"] = (prompt, access_type)
        return ("https://accounts.google.com/o/oauth2/auth?client_id=CLIENTID&x=1", None)
    def fetch_token(self, code=None):
        self.store["code"] = code

def _stub_oauthlib(store):
    pkg = types.ModuleType("google_auth_oauthlib")
    flow_mod = types.ModuleType("google_auth_oauthlib.flow")
    class _InstalledAppFlow:
        @staticmethod
        def from_client_config(config, scopes):
            store["client_config"] = config
            store["scopes"] = scopes
            return _FakeFlow(store)
    flow_mod.InstalledAppFlow = _InstalledAppFlow
    pkg.flow = flow_mod
    sys.modules.update({"google_auth_oauthlib": pkg,
                        "google_auth_oauthlib.flow": flow_mod})

def test_missing_client_config_returns_2():
    mod = _load("drive_authorize", "ops/drive_authorize.py")
    mod.CLIENT_PATH = Path("/nonexistent/oauth-client.json")
    assert mod.main(["drive_authorize.py", "--auth-url"]) == 2
    assert mod.main(["drive_authorize.py", "--code", "abc"]) == 2
    assert mod.main(["drive_authorize.py"]) == 2

def test_auth_url_and_exchange_with_fake_flow():
    mod = _load("drive_authorize", "ops/drive_authorize.py")
    store = {}
    _stub_oauthlib(store)
    with tempfile.TemporaryDirectory() as tmp:
        client = Path(tmp) / "client.json"
        client.write_text(json.dumps(
            {"client_id": "CLIENTID", "client_secret": "SECRET"}))
        token = Path(tmp) / "token.json"
        mod.CLIENT_PATH = client
        mod.TOKEN_PATH = token
        url = mod.auth_url()
        assert url.startswith("https://accounts.google.com/o/oauth2/auth")
        assert "CLIENTID" in url
        assert store["auth_url_args"] == ("consent", "offline")
        assert store["client_config"]["installed"]["client_id"] == "CLIENTID"
        assert store["client_config"]["installed"]["redirect_uris"] == [
            "http://localhost:8080/"]
        assert store["scopes"] == ["https://www.googleapis.com/auth/drive.file"]
        path = mod.exchange("CODE-123")
        assert path == token
        assert store["code"] == "CODE-123"
        saved = json.loads(token.read_text())
        assert saved == {"client_id": "CLIENTID", "client_secret": "SECRET",
                         "refresh_token": "refresh-xyz",
                         "type": "authorized_user"}
        assert stat.S_IMODE(token.stat().st_mode) == 0o600
