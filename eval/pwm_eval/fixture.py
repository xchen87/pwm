import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pwm.sources import SourceRecord
from pwm_eval.gold import Gold

SYNTHETIC_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic"


class Fixture(BaseModel):
    model_config = ConfigDict(frozen=True)

    sources: tuple[SourceRecord, ...]
    gold: Gold

    def source(self, source_id: str) -> SourceRecord:
        return next(s for s in self.sources if s.id == source_id)


def load_fixture(directory: Path = SYNTHETIC_DIR) -> Fixture:
    sources = json.loads((directory / "sources.json").read_text(encoding="utf-8"))
    gold = json.loads((directory / "gold.json").read_text(encoding="utf-8"))
    return Fixture(sources=sources, gold=gold)
