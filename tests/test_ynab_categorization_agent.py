"""
Tests for YNAB Categorization Agent Definition

ZERO MOCKS POLICY: All tests use real systems only.
- Real agent file: agents/ynab-categorization-agent.md
- Real YAML parsing: Python yaml.safe_load()
- Real file I/O: Direct file reads

NO mocking, stubbing, or simulation permitted.
"""

import yaml
from pathlib import Path

# Test constants
AGENT_FILE_PATH = Path("agents/ynab-categorization-agent.md")
REQUIRED_FRONTMATTER_FIELDS = ["name", "description", "tools", "model"]
REQUIRED_TOOLS = ["Read", "Write", "Task", "WebSearch"]
EXPECTED_MODEL = "sonnet"
MAX_DESCRIPTION_LENGTH = 200


def test_agent_file_exists():
    """Test that agent definition file exists at expected location."""
    assert AGENT_FILE_PATH.exists(), f"Agent file not found at {AGENT_FILE_PATH}"
    assert AGENT_FILE_PATH.is_file(), f"Agent path {AGENT_FILE_PATH} is not a file"


def test_agent_frontmatter_parsable():
    """Test that YAML frontmatter is valid and parsable."""
    with open(AGENT_FILE_PATH, 'r') as f:
        content = f.read()
    
    # Extract YAML frontmatter (between --- delimiters)
    assert content.startswith('---'), "Agent file must start with YAML frontmatter delimiter"
    
    frontmatter_end = content.find('---', 3)
    assert frontmatter_end > 0, "Agent file must have closing YAML frontmatter delimiter"
    
    frontmatter_text = content[3:frontmatter_end].strip()
    
    # Parse YAML (will raise exception if invalid)
    frontmatter = yaml.safe_load(frontmatter_text)
    
    assert isinstance(frontmatter, dict), "Frontmatter must parse to a dictionary"
    assert len(frontmatter) > 0, "Frontmatter must not be empty"


def test_agent_required_fields_present():
    """Test that all required frontmatter fields are present."""
    with open(AGENT_FILE_PATH, 'r') as f:
        content = f.read()
    
    frontmatter_end = content.find('---', 3)
    frontmatter_text = content[3:frontmatter_end].strip()
    frontmatter = yaml.safe_load(frontmatter_text)
    
    for field in REQUIRED_FRONTMATTER_FIELDS:
        assert field in frontmatter, f"Required field '{field}' missing from frontmatter"
        assert frontmatter[field], f"Required field '{field}' is empty"


def test_agent_name_matches_filename():
    """Test that agent name matches filename (without extension)."""
    with open(AGENT_FILE_PATH, 'r') as f:
        content = f.read()
    
    frontmatter_end = content.find('---', 3)
    frontmatter_text = content[3:frontmatter_end].strip()
    frontmatter = yaml.safe_load(frontmatter_text)
    
    expected_name = AGENT_FILE_PATH.stem  # filename without .md extension
    actual_name = frontmatter.get('name')
    
    assert actual_name == expected_name, \
        f"Agent name '{actual_name}' must match filename '{expected_name}'"


def test_agent_description_length():
    """Test that description is ≤200 characters."""
    with open(AGENT_FILE_PATH, 'r') as f:
        content = f.read()
    
    frontmatter_end = content.find('---', 3)
    frontmatter_text = content[3:frontmatter_end].strip()
    frontmatter = yaml.safe_load(frontmatter_text)
    
    description = frontmatter.get('description', '')
    
    assert len(description) <= MAX_DESCRIPTION_LENGTH, \
        f"Description length {len(description)} exceeds maximum {MAX_DESCRIPTION_LENGTH}"


def test_agent_tools_include_required():
    """Test that tools list includes all required tools."""
    with open(AGENT_FILE_PATH, 'r') as f:
        content = f.read()
    
    frontmatter_end = content.find('---', 3)
    frontmatter_text = content[3:frontmatter_end].strip()
    frontmatter = yaml.safe_load(frontmatter_text)
    
    tools = frontmatter.get('tools', [])
    
    assert isinstance(tools, list), "Tools must be a list"
    
    for required_tool in REQUIRED_TOOLS:
        assert required_tool in tools, \
            f"Required tool '{required_tool}' missing from tools list"


def test_agent_model_is_sonnet():
    """Test that model selection is 'sonnet'."""
    with open(AGENT_FILE_PATH, 'r') as f:
        content = f.read()
    
    frontmatter_end = content.find('---', 3)
    frontmatter_text = content[3:frontmatter_end].strip()
    frontmatter = yaml.safe_load(frontmatter_text)
    
    model = frontmatter.get('model')
    
    assert model == EXPECTED_MODEL, \
        f"Model must be '{EXPECTED_MODEL}', found '{model}'"


def test_agent_body_has_required_sections():
    """Test that agent body contains required documentation sections."""
    with open(AGENT_FILE_PATH, 'r') as f:
        content = f.read()
    
    # Extract agent body (after second --- delimiter)
    frontmatter_end = content.find('---', 3)
    agent_body = content[frontmatter_end + 3:].strip()
    
    required_sections = [
        "Role & Capabilities",
        "3-Tier Decision Logic",
        "Tier 1:",
        "Tier 2:",
        "Tier 3:",
        "Split Transaction Handling",
        "Learning Mechanism",
        "Error Handling",
        "Integration Points",
        "Configuration"
    ]
    
    for section in required_sections:
        assert section in agent_body, \
            f"Required section '{section}' not found in agent body"


def test_agent_no_placeholder_content():
    """Test that agent definition has no TBD/TODO/placeholder content."""
    with open(AGENT_FILE_PATH, 'r') as f:
        content = f.read()
    
    placeholders = ["TBD", "TODO", "FIXME", "XXX", "PLACEHOLDER", "to be determined"]
    
    for placeholder in placeholders:
        assert placeholder.lower() not in content.lower(), \
            f"Placeholder content '{placeholder}' found in agent definition"


def test_agent_json_schemas_valid():
    """Test that JSON schema examples in agent definition are valid JSON."""
    import json
    import re
    
    with open(AGENT_FILE_PATH, 'r') as f:
        content = f.read()
    
    # Extract JSON code blocks (between ```json and ```)
    json_blocks = re.findall(r'```json\s*(.*?)\s*```', content, re.DOTALL)
    
    assert len(json_blocks) > 0, "Agent definition must contain JSON schema examples"
    
    for i, json_text in enumerate(json_blocks):
        try:
            json.loads(json_text)
        except json.JSONDecodeError as e:
            raise AssertionError(f"JSON block {i+1} is invalid: {e}")


def test_agent_zero_mocks_mandate_present():
    """Test that agent definition explicitly mandates ZERO MOCKS testing."""
    with open(AGENT_FILE_PATH, 'r') as f:
        content = f.read()
    
    # Check for ZERO MOCKS or NO MOCKS mandate
    assert "ZERO MOCKS" in content or "NO MOCKS" in content or "Real systems" in content, \
        "Agent definition must explicitly mandate ZERO MOCKS testing"
    
    # Check for prohibited practices
    prohibited_terms = ["Mock", "Stub", "Fake", "Simulate"]
    found_prohibition = False
    for term in prohibited_terms:
        if f"❌" in content and term in content:
            found_prohibition = True
            break
    
    assert found_prohibition, \
        "Agent definition must list prohibited mocking practices"
