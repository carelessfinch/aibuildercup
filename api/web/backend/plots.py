"""Dependency-free SVG figures used by the mock research flow.

W1/W2's matplotlib post-processing can replace these artifacts without an API
change: the UI consumes plot URLs and does not care which renderer produced them.
"""

from __future__ import annotations

from agents.contracts import PlasmaPoint


def _line_path(points: list[PlasmaPoint], x_values: list[float], y_values: list[float]) -> str:
    if not points:
        return ""
    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)
    x_span = (x_max - x_min) or 1.0
    y_span = (y_max - y_min) or 1.0
    coordinates = []
    for x_value, y_value in zip(x_values, y_values, strict=True):
        x = 78 + (x_value - x_min) / x_span * 492
        y = 294 - (y_value - y_min) / y_span * 224
        coordinates.append(f"{x:.1f},{y:.1f}")
    return " ".join(coordinates)


def _chart_svg(title: str, points: list[PlasmaPoint], values: list[float], unit: str) -> bytes:
    x_values = [point.bias_V for point in points]
    line = _line_path(points, x_values, values)
    dots = []
    if points:
        x_min, x_max = min(x_values), max(x_values)
        y_min, y_max = min(values), max(values)
        x_span = (x_max - x_min) or 1.0
        y_span = (y_max - y_min) or 1.0
        for x_value, y_value in zip(x_values, values, strict=True):
            x = 78 + (x_value - x_min) / x_span * 492
            y = 294 - (y_value - y_min) / y_span * 224
            dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="#0f766e" />')
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 380"
  role="img" aria-label="{title}">
  <rect width="640" height="380" fill="#f7faf8"/>
  <text x="34" y="43" fill="#15242b"
    font-family="Fraunces, Georgia, serif" font-size="27" font-weight="600">{title}</text>
  <text x="34" y="70" fill="#556862"
    font-family="Inter, system-ui, sans-serif" font-size="14">
    Substrate bias sweep · demo data</text>
  <line x1="78" y1="294" x2="570" y2="294" stroke="#95a8a1" stroke-width="1.5"/>
  <line x1="78" y1="70" x2="78" y2="294" stroke="#95a8a1" stroke-width="1.5"/>
  <polyline points="{line}" fill="none" stroke="#0f766e" stroke-width="3.5" stroke-linecap="round"/>
  {''.join(dots)}
  <text x="324" y="339" text-anchor="middle" fill="#556862"
    font-family="Inter, system-ui, sans-serif" font-size="14">Bias (V)</text>
  <text x="40" y="182" text-anchor="middle" transform="rotate(-90 40 182)"
    fill="#556862" font-family="Inter, system-ui, sans-serif" font-size="14">{unit}</text>
</svg>"""
    return svg.encode("utf-8")


def create_demo_plots(points: list[PlasmaPoint]) -> dict[str, tuple[str, bytes]]:
    return {
        "electron-density.svg": (
            "image/svg+xml",
            _chart_svg("Electron density", points, [point.ne_m3 for point in points], "n_e (m^-3)"),
        ),
        "electron-temperature.svg": (
            "image/svg+xml",
            _chart_svg(
                "Electron temperature",
                points,
                [point.te_eV for point in points],
                "T_e (eV)",
            ),
        ),
        "ion-flux.svg": (
            "image/svg+xml",
            _chart_svg(
                "Ion flux",
                points,
                [point.ion_flux_m2s for point in points],
                "Bohm flux (m^-2 s^-1)",
            ),
        ),
    }
