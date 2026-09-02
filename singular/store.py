from pathlib import Path
import json
from .models import WorldModel

class JsonWorldStore:
    def __init__(self, path='data/world_model.json'):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, world: WorldModel) -> None:
        self.path.write_text(world.model_dump_json(indent=2), encoding='utf-8')

    def load(self) -> WorldModel:
        if not self.path.exists():
            return WorldModel()
        return WorldModel.model_validate_json(self.path.read_text(encoding='utf-8'))
