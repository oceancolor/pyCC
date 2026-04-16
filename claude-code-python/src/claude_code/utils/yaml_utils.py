"""YAML parsing wrapper. Ported from yaml.ts"""
from __future__ import annotations
import yaml as _yaml

def parse_yaml(input: str):
    return _yaml.safe_load(input)

def stringify_yaml(data, **kwargs) -> str:
    return _yaml.dump(data, **kwargs)
