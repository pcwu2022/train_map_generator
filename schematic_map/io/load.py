import json
from pathlib import Path
from .validate import validate_graph


def load_graph(path):
    return validate_graph(json.loads(Path(path).read_text(encoding='utf-8')))
