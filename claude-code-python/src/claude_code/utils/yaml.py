"""YAML parsing wrapper. Ported from utils/yaml.ts"""
from __future__ import annotations
import yaml as _yaml

def parse_yaml(input_str: str):
    return _yaml.safe_load(input_str)

def dump_yaml(obj) -> str:
    return _yaml.dump(obj, allow_unicode=True)
