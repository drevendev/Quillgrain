import copy
from pathlib import Path
import pytest
from quillgrain.io import read_json, write_json


@pytest.fixture
def pack():
    return copy.deepcopy(read_json(Path(__file__).resolve().parents[1] / "examples/synthetic/common/voice.json"))


@pytest.fixture
def save(tmp_path):
    def persist(pack, name="pack"):
        path = tmp_path / name
        write_json(path / "voice.json", pack)
        return path
    return persist
