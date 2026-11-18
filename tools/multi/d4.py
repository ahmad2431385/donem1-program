"""Dönem 4 Türkçe: B, C, D grupları (ikili B1, dörtlü B1-1) — rotasyon ve haftalık grup programları."""
from .d45 import build_common, students4


def build(src):
    data, st, stats, warn = build_common(4, src, students4)
    need = {"students": 200, "events": 3000, "groups": 3}
    return data, st, stats, need, warn
