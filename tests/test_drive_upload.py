import importlib.util, os, sys, tempfile, types
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

def _load():
    spec = importlib.util.spec_from_file_location(
        "drive_upload", REPO / "ops" / "drive_upload.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class _FakeCall:
    def __init__(self, result): self._result = result
    def execute(self): return self._result

class _FakeFiles:
    def __init__(self, store): self.store = store
    def create(self, body=None, media_body=None, fields=None):
        self.store["create"] = {"body": body, "fields": fields}
        return _FakeCall({"id": "drive-file-1"})
    def list(self, q=None, fields=None, pageSize=None):
        self.store["list"] = {"q": q}
        return _FakeCall({"files": self.store.get("list_result", [])})
    def update(self, fileId=None, body=None):
        self.store.setdefault("updates", []).append(
            {"fileId": fileId, "body": body})
        return _FakeCall({})

class _FakeService:
    def __init__(self, store):
        self._files = _FakeFiles(store)
        self.store = store
    def files(self): return self._files

def _stub_google(store):
    google = types.ModuleType("google")
    oauth2 = types.ModuleType("google.oauth2")
    sa = types.ModuleType("google.oauth2.service_account")
    class _Creds:
        @staticmethod
        def from_service_account_file(path, scopes=None):
            store["creds_path"] = path
            return object()
    sa.Credentials = _Creds
    oauth2.service_account = sa
    creds_mod = types.ModuleType("google.oauth2.credentials")
    class _UserCreds:
        @staticmethod
        def from_authorized_user_file(path, scopes=None):
            store["user_token_path"] = path
            store["user_token_scopes"] = scopes
            return object()
    creds_mod.Credentials = _UserCreds
    oauth2.credentials = creds_mod
    gapiclient = types.ModuleType("googleapiclient")
    discovery = types.ModuleType("googleapiclient.discovery")
    discovery.build = lambda *a, **k: _FakeService(store)
    gapiclient.discovery = discovery
    http_mod = types.ModuleType("googleapiclient.http")
    class _Media:
        def __init__(self, *a, **k): store["media"] = (a, k)
    http_mod.MediaFileUpload = _Media
    gapiclient.http = http_mod
    sys.modules.update({
        "google": google, "google.oauth2": oauth2,
        "google.oauth2.service_account": sa,
        "google.oauth2.credentials": creds_mod,
        "googleapiclient": gapiclient,
        "googleapiclient.discovery": discovery,
        "googleapiclient.http": http_mod})

def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")

def test_missing_credentials_returns_2():
    mod = _load()
    mod.KEY_PATH = Path("/nonexistent/drive-sa.json")
    mod.USER_TOKEN_PATH = Path("/nonexistent/drive-user-token.json")
    assert mod.main(["drive_upload.py", "/tmp/x.tar.gz", "abc"]) == 2

def test_missing_folder_returns_2():
    mod = _load()
    with tempfile.TemporaryDirectory() as tmp:
        mod.KEY_PATH = Path(tmp) / "sa.json"
        mod.KEY_PATH.write_text("{}")
        mod.USER_TOKEN_PATH = Path(tmp) / "no-token.json"
        mod.FOLDER_ID_PATH = Path(tmp) / "no-folder-id.txt"
        os.environ.pop("FFL_DRIVE_FOLDER_ID", None)
        assert mod.main(["drive_upload.py", "/tmp/x.tar.gz", "abc"]) == 2

def test_select_prune():
    mod = _load()
    files = [{"id": f"f{i}", "name": f"a-{i}.tar.gz",
              "modifiedTime": _iso(age)}
             for i, age in enumerate([10, 9, 8, 6.5, 6, 5, 4, 3, 2, 1])]
    doomed = mod.select_prune(files, 7)
    assert [f["id"] for f in doomed] == ["f0", "f1", "f2"]

def test_upload_and_prune_with_fake_service():
    mod = _load()
    store = {}
    _stub_google(store)
    with tempfile.TemporaryDirectory() as tmp:
        key = Path(tmp) / "sa.json"
        key.write_text("{}")
        archive = Path(tmp) / "file-from-link-backup-20261111-0030.tar.gz"
        archive.write_bytes(b"fake-archive")
        store["list_result"] = [
            {"id": "old1", "name": "file-from-link-backup-20261101-0030.tar.gz",
             "modifiedTime": _iso(10)},
            {"id": "new1", "name": "file-from-link-backup-20261110-0030.tar.gz",
             "modifiedTime": _iso(1)},
        ]
        mod.KEY_PATH = key
        mod.USER_TOKEN_PATH = Path(tmp) / "no-token.json"
        os.environ["FFL_DRIVE_FOLDER_ID"] = "folder-123"
        try:
            assert mod.main(["drive_upload.py", str(archive), "deadbeef"]) == 0
        finally:
            os.environ.pop("FFL_DRIVE_FOLDER_ID", None)
        body = store["create"]["body"]
        assert body["name"] == archive.name
        assert body["parents"] == ["folder-123"]
        assert body["description"] == "sha256:deadbeef"
        assert store["creds_path"] == str(key)
        trashed = [u["fileId"] for u in store.get("updates", [])]
        assert trashed == ["old1"]

def test_user_token_preferred_over_service_account():
    mod = _load()
    store = {}
    _stub_google(store)
    with tempfile.TemporaryDirectory() as tmp:
        token = Path(tmp) / "token.json"
        token.write_text("{}")
        key = Path(tmp) / "sa.json"
        key.write_text("{}")
        archive = Path(tmp) / "file-from-link-backup-20261111-0030.tar.gz"
        archive.write_bytes(b"fake-archive")
        store["list_result"] = []
        mod.USER_TOKEN_PATH = token
        mod.KEY_PATH = key
        os.environ["FFL_DRIVE_FOLDER_ID"] = "folder-123"
        try:
            assert mod.main(["drive_upload.py", str(archive), "deadbeef"]) == 0
        finally:
            os.environ.pop("FFL_DRIVE_FOLDER_ID", None)
        assert store["user_token_path"] == str(token)
        assert store["user_token_scopes"] == [
            "https://www.googleapis.com/auth/drive.file"]
        assert "creds_path" not in store  # SA path not used
        assert store["create"]["body"]["description"] == "sha256:deadbeef"
