The method, in this order. Each stage goes in `plan.json` under `stages` (the names below) once it is done.

1. `measure_floor`: floor area = length × width.
2. `measure_walls`: wall area = sum of length × height of every wall in `walls_to_tile`.
3. `subtract_openings`: subtract every opening (doors, windows) from the walls, EXCEPT openings smaller than 0.1 m²
   (vents, sockets): those are tiled over, never subtracted.
4. `add_waste`: total = (floor + net walls) × 1.10 (10% for cuts and breakage).
5. `options_per_supplier`: for every row in `suppliers.csv`, boxes = ceil(total ÷ m2_per_box).
6. `cost_per_option`: cost = boxes × price_per_box_usd.
7. `open_decisions`: the tile, its color and the budget are the client's decisions. Never choose them: list them as
   open decisions unless room.json says the client already decided.
8. `plan_written`: write `PLAN.md` for the client and `plan.json` with: `stages`, `floor_m2`, `walls_net_m2`,
   `total_with_waste_m2` (two decimals), `options` (list of `{"sku", "boxes", "cost_usd"}`) and `open_decisions`
   (list of strings). No `chosen_*` keys.
