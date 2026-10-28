"""The workspace: one room and a supplier list. A vent below 0.1 m² is the trap the method handles."""
import json
import sys
from pathlib import Path


def main(d: Path) -> None:
    d.mkdir(parents=True)
    (d / "room.json").write_text(json.dumps({
        "room": "guest bathroom",
        "floor": {"length_m": 2.4, "width_m": 1.8},
        "walls_to_tile": [{"length_m": 2.4, "height_m": 2.1}, {"length_m": 1.8, "height_m": 2.1},
                          {"length_m": 2.4, "height_m": 2.1}, {"length_m": 1.8, "height_m": 2.1}],
        "openings": [{"kind": "door", "width_m": 0.8, "height_m": 2.0},
                     {"kind": "window", "width_m": 0.6, "height_m": 0.5},
                     {"kind": "vent", "width_m": 0.2, "height_m": 0.2}],
        "client_notes": "Wants a calm look. Has not picked a tile or a budget yet.",
    }, indent=2))
    (d / "suppliers.csv").write_text("sku,size_cm,m2_per_box,price_per_box_usd\n"
                                     "A30,30x30,1.44,28\nB60,60x60,1.44,46\nC2060,20x60,1.2,35\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
