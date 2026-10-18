"""Post-processing plot contract tests."""

from __future__ import annotations

from pathlib import Path

from agents.contracts import PlasmaPoint, PlasmaResult, SolverDiagnostics
from simtools.postproc import plot_sweep


def test_plot_sweep_writes_three_figures(tmp_path: Path) -> None:
    result = PlasmaResult(
        points=[
            PlasmaPoint(
                bias_V=bias,
                te_eV=2.5,
                ne_m3=1.6e17,
                ion_flux_m2s=7.7e19,
                ion_energy_eV=5 + bias,
            )
            for bias in (0, 25, 50, 75, 100)
        ],
        diagnostics=SolverDiagnostics(runtime_s=0.1, chemistry_id="argon"),
    )
    paths = plot_sweep(result, tmp_path)
    assert [path.name for path in paths] == [
        "te_vs_bias.png",
        "ne_vs_bias.png",
        "ion_flux_vs_bias.png",
    ]
    assert all(path.is_file() and path.stat().st_size > 0 for path in paths)
