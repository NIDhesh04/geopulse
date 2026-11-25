"""
GeoPulse Experimental Benchmark Package
"""

__all__ = ["ExperimentalBenchmark", "generate_all_figures"]


def __getattr__(name: str):
    if name == "ExperimentalBenchmark":
        from src.experiments.benchmark_runner import ExperimentalBenchmark
        return ExperimentalBenchmark
    if name == "generate_all_figures":
        from src.experiments.visualizations import generate_all_figures
        return generate_all_figures
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
