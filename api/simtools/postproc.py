"""Post-processing figures for the UI."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

from pathlib import Path

import matplotlib.pyplot as plt

from agents.contracts import PlasmaResult


def plot_sweep(result: PlasmaResult, out_dir: str | Path = "plots") -> list[Path]:
    """Write Te, ne, and ion-flux versus bias figures and return their paths."""
    if not result.points:
        msg = "cannot plot an empty plasma sweep"
        raise ValueError(msg)
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)

    ordered = sorted(result.points, key=lambda point: point.bias_V)
    bias_v = [point.bias_V for point in ordered]
    plots = (
        ("te_vs_bias.png", "Electron temperature", [point.te_eV for point in ordered], "Te (eV)"),
        ("ne_vs_bias.png", "Electron density", [point.ne_m3 for point in ordered], "ne (m$^{-3}$)"),
        (
            "ion_flux_vs_bias.png",
            "Ion flux",
            [point.ion_flux_m2s for point in ordered],
            r"$\Gamma_i$ (m$^{-2}$ s$^{-1}$)",
        ),
    )
    paths: list[Path] = []
    for filename, title, values, ylabel in plots:
        figure, axis = plt.subplots(figsize=(6.4, 4.2), constrained_layout=True)
        axis.plot(bias_v, values, marker="o", linewidth=2)
        axis.set_title(title)
        axis.set_xlabel("Substrate bias (V)")
        axis.set_ylabel(ylabel)
        axis.grid(True, alpha=0.25)
        path = directory / filename
        figure.savefig(path, dpi=160)
        plt.close(figure)
        paths.append(path)
    return paths


def plot_etch_profile(result, out_dir: str | Path = "plots") -> Path:
    """Trench profile figure. W2."""
    raise NotImplementedError("etch plotting lands in W2")
