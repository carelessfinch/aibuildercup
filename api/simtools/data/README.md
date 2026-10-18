# simtools data

## Chemistry YAML (`simtools.chemistry/1`)

One schema for every chemistry (argon and CF4/O2). `status: ready` requires
every reaction to carry a rate; `status: stub` files load but engines must
refuse to run them. See `simtools/chemistry.py`.

- `chemistry_ar_lieberman.yaml` — working argon chemistry for M1 (decision K1).
- `chemistry_cf4o2_kimura2006.yaml` — stub; fill in the Kimura & Noto
  reaction set + LxCat cross sections by end of 10 Oct.

## Validation CSV

`validation_comsol_cf4o2.csv` columns:

`curve_id, x_name, x_value, x_unit, y_name, y_value, y_unit, tolerance_pct, kind, citation, notes`

- `kind = experiment` — measurements from **Kimura & Noto (2006)**; these are
  the calibration loop's measured targets (decision K2).
- `kind = model` — the COMSOL 2D-axisymmetric reference curves, used only as a
  cross-model check. Digitise **wafer- or volume-averaged** values and widen
  the tolerance bands accordingly, stating the averaging in `citation`/`notes`
  (decision K3).

Rows land by end of 10 Oct (K1). Tolerance bands are the eval gates, not the
calibration tolerances.
