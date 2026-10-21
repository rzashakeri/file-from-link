import re
URL_RE = re.compile(r"https?://[^\s<>()\[\]{}]+", re.I)
def extract_urls(text: str) -> list[str]:
    return [u.rstrip(".,;:!?") for u in URL_RE.findall(text or "")]
FORMAT_ORDER = ["best", "720", "480", "audio"]
FORMATS = {
  "best": "bv*+ba/best",
  "720": "bv*[height<=720]+ba/best[height<=720]/best",
  "480": "bv*[height<=480]+ba/best[height<=480]/best",
  "audio": "ba/best",
}
def format_selector(choice: str) -> str:
    return FORMATS.get(choice, FORMATS["best"])
