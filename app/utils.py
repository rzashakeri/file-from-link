import re
URL_RE = re.compile(r"https?://[^\s<>()\[\]{}]+", re.I)
def extract_urls(text: str) -> list[str]:
    return [u.rstrip(".,;:!?") for u in URL_RE.findall(text or "")]
FORMAT_ORDER = ["best", "720", "480", "audio"]
FORMATS = {
  "best": "bv*+ba/best",
  "720": "bv*[height<=720]+ba/b[height<=720]/bv*+ba/best",
  "480": "bv*[height<=480]+ba/b[height<=480]/bv*+ba/best",
  "audio": "ba/bestaudio/best",
}
def format_selector(choice: str) -> str:
    return FORMATS.get(choice, FORMATS["best"])
