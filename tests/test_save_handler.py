import pytest
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from save_handler import parse_llm_json

def test_parse_llm_json():
    # Test valid JSON
    valid_json = '{"progress": "Done", "lessons": "None", "scratchpad": "", "memory": ""}'
    res = parse_llm_json(valid_json)
    assert res["progress"] == "Done"
    
    # Test JSON wrapped in markdown ticks
    markdown_json = '```json\n{"progress": "Parsed", "lessons": "None", "scratchpad": "", "memory": ""}\n```'
    res = parse_llm_json(markdown_json)
    assert res["progress"] == "Parsed"
    
    # Test JSON with text around it
    messy_json = 'Here is your output:\n```\n{"progress": "Cleaned", "lessons": "None", "scratchpad": "", "memory": ""}\n```\nHope it helps.'
    res = parse_llm_json(messy_json)
    assert res["progress"] == "Cleaned"
    
    # Test invalid JSON returns None
    invalid = "This is not json at all."
    assert parse_llm_json(invalid) is None
