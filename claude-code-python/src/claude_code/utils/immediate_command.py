"""Immediate command feature flag. Ported from immediateCommand.ts"""
from __future__ import annotations
import os

def should_inference_config_command_be_immediate() -> bool:
    return os.environ.get('USER_TYPE') == 'ant'
