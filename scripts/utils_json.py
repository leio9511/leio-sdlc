import json
import re

def extract_and_parse_json(text: str) -> dict:
    """
    Extracts and parses a JSON object from a given text string.
    Handles text that may be wrapped in markdown code blocks or contain surrounding text.
    """
    # Try to find a JSON block enclosed in ```json ... ``` or ``` ... ```
    pattern = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
    match = pattern.search(text)
    
    if match:
        json_str = match.group(1)
    else:
        # If no markdown block is found, assume the text might just be the JSON (possibly with leading/trailing whitespace)
        # We can try to find the outermost braces
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and start <= end:
            json_str = text[start:end+1]
        else:
            json_str = text

    try:
        return json.loads(json_str.strip())
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not extract valid JSON. Parse error: {e}")
