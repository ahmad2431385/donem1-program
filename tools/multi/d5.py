"""Dönem 5 Türkçe: B–G grupları (ikili ve üçlü alt gruplar) — haftalık grup programları."""
from .d45 import build_common, students5


def build(src):
    data, st, stats, warn = build_common(5, src, students5)
    need = {"students": 200, "events": 5000, "groups": 6}
    return data, st, stats, need, warn
