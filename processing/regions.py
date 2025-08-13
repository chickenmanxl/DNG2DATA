from dataclasses import dataclass
from typing import Any, Dict, List
import json


@dataclass
class Region:
    """Generic measurement region."""
    id: int
    shape: str  # 'rect', 'circle', 'polygon'
    params: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "shape": self.shape, "params": self.params}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Region":
        return Region(id=data["id"], shape=data["shape"], params=data["params"])


def load_template(path: str) -> List[Region]:
    """Load regions from a JSON template file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Region.from_dict(d) for d in data]


def save_template(path: str, regions: List[Region]) -> None:
    """Save regions to a JSON template file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump([r.to_dict() for r in regions], f, indent=2)