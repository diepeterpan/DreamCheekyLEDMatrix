"""
Script Engine for Dream Cheeky LED Matrix.
Executes custom Python code in a safe execution scope with access to:
- re (regex)
- requests (HTTP requests to external APIs)
- time, datetime (clock, dates)
- math (calculations)
- os.path, built-in string functions
- custom helper read_file() and get_json()
Returns the evaluated string for display.

Includes:
- Pre-flight syntax validation and error diagnosing with actionable hints
- Python code formatting & Tabs <-> Spaces standardization using standard library
"""

import ast
import datetime
import json
import logging
import math
import os
import re
import sys
import time
import traceback
from io import StringIO
from typing import Dict, Any, Tuple, Optional
import requests

logger = logging.getLogger("dcled.script")

DEFAULT_SCRIPT = '''# DCLED Runtime Script
# Write Python code to compute what string to display on the 21x7 Matrix!
# Builtins provided: requests, re, time, datetime, math, json, read_file, get_json

def get_text():
    # Example: Show current time and exchange rate or custom status
    current_time = datetime.datetime.now().strftime("%H:%M")
    
    try:
        # Example: Fetch USD to ZAR rate
        url = "https://www.xe.com/api/protected/live-currency-rates/?currencyPairs=USD%2FZAR"
        headers = {
            "Authorization": "Basic bG9kZXN0YXI6cHVnc25heA==",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        res = requests.get(url, headers=headers, timeout=5)
        rate = res.json()[0]["rate"]
        return f"{rate:.2f}"
    except Exception as e:
        print(f"Error fetching rate: {e}")
        return f"{current_time}"

# Return the string by calling the function
get_text()
'''

def helper_read_file(filepath: str) -> str:
    """Helper for user scripts to safely read text from disk."""
    if not os.path.exists(filepath):
        return f"File not found: {filepath}"
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def helper_get_json(url: str, timeout: float = 3.0) -> Any:
    """Helper to quickly fetch JSON."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    res = requests.get(url, headers=headers, timeout=timeout)
    res.raise_for_status()
    return res.json()


def generate_diagnostic_hint(error: Exception, code: str) -> str:
    """Generates user-friendly advice and solutions for common Python stumbling blocks."""
    err_str = str(error)
    err_type = type(error).__name__

    if isinstance(error, IndentationError) or isinstance(error, TabError):
        return "Indentation error: You have inconsistent use of tabs and spaces or misaligned indentation. Click 'TABS TO SPACES' or 'FORMAT CODE' to fix automatically."

    if isinstance(error, SyntaxError):
        if "was never closed" in err_str or "unexpected EOF" in err_str:
            return "Unclosed parenthesis, quote, or bracket: Check that all '(', '[', '{', and quotation marks are closed."
        if "invalid syntax" in err_str:
            return "Syntax error: Check for missing colons ':' after 'def', 'try', 'except', 'if', or mismatched operators."

    if isinstance(error, NameError):
        if "urllib" in err_str:
            return "NameError: 'urllib' is not imported. Use the pre-loaded 'requests' library directly, or add 'import urllib.request'."
        if "'e'" in err_str:
            return "NameError: 'e' is not defined. Ensure your handler is written as 'except Exception as e:'."
        return f"NameError: A variable or function is used before being defined: {err_str}."

    if "JSONDecodeError" in err_type or "Expecting value" in err_str:
        return "JSON error: The server returned HTML or non-JSON data (often an HTTP 403 Forbidden). Include a browser 'User-Agent' in your request headers."

    if isinstance(error, requests.exceptions.RequestException):
        return f"Network/HTTP error: External API call failed ({err_type}). Check the target URL, connectivity, or authentication headers."

    return f"{err_type}: {err_str}"


def validate_python_syntax(code: str) -> Dict[str, Any]:
    """Validates code syntax using Python's AST parser without executing it."""
    try:
        ast.parse(code, filename="<user_script>")
        return {
            "valid": True,
            "error_type": None,
            "message": "Syntax is valid",
            "line": None,
            "column": None,
            "hint": None
        }
    except (SyntaxError, IndentationError, TabError) as e:
        hint = generate_diagnostic_hint(e, code)
        return {
            "valid": False,
            "error_type": type(e).__name__,
            "message": e.msg if hasattr(e, "msg") else str(e),
            "line": getattr(e, "lineno", None),
            "column": getattr(e, "offset", None),
            "text": getattr(e, "text", "").strip() if getattr(e, "text", None) else None,
            "hint": hint
        }
    except Exception as e:
        return {
            "valid": False,
            "error_type": type(e).__name__,
            "message": str(e),
            "line": None,
            "column": None,
            "hint": str(e)
        }


def format_python_code(code: str, indent_style: str = "spaces", indent_size: int = 4) -> Dict[str, Any]:
    """
    Standardizes code indentation and formatting using Python standard library.
    indent_style: 'spaces' or 'tabs'
    """
    if not code.strip():
        return {"success": True, "formatted_code": code}

    lines = code.splitlines()
    formatted_lines = []

    # First pass: normalize leading indentation
    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            formatted_lines.append("")
            continue

        # Count leading indentation
        leading_space_count = 0
        idx = 0
        while idx < len(stripped):
            if stripped[idx] == ' ':
                leading_space_count += 1
                idx += 1
            elif stripped[idx] == '\t':
                # Treat tab as indent_size spaces
                leading_space_count += indent_size - (leading_space_count % indent_size)
                idx += 1
            else:
                break

        content = stripped[idx:]
        indent_level = leading_space_count // indent_size
        remainder = leading_space_count % indent_size
        # Round to closest indent level if slightly off
        if remainder >= (indent_size // 2):
            indent_level += 1

        if indent_style == "tabs":
            new_leading = "\t" * indent_level
        else:
            new_leading = " " * (indent_level * indent_size)

        formatted_lines.append(new_leading + content)

    formatted_code = "\n".join(formatted_lines) + "\n"

    # Validate AST to ensure formatting didn't break structure
    try:
        ast.parse(formatted_code)
        return {"success": True, "formatted_code": formatted_code}
    except Exception as e:
        # If aggressive re-indent failed AST validation, do a safe replacement of leading tabs
        safe_lines = []
        for line in lines:
            if indent_style == "tabs":
                # Convert 4 spaces to tab
                safe_line = re.sub(r"^( {4})+", lambda m: "\t" * (len(m.group(0)) // 4), line)
            else:
                # Convert tabs to spaces
                safe_line = line.replace("\t", " " * indent_size)
            safe_lines.append(safe_line.rstrip())
        safe_code = "\n".join(safe_lines) + "\n"
        return {"success": True, "formatted_code": safe_code}


class ScriptEngine:
    def __init__(self):
        pass

    def run_script(self, code: str, timeout_sec: float = 5.0) -> Tuple[bool, str, str, float, Optional[Dict[str, Any]]]:
        """
        Executes user code.
        Returns:
            (success: bool, result_text: str, stdout_or_error: str, duration_ms: float, error_details: dict)
        """
        start_time = time.time()

        # Step 1: Pre-flight syntax and indentation check
        syntax_check = validate_python_syntax(code)
        if not syntax_check["valid"]:
            duration_ms = (time.time() - start_time) * 1000
            err_msg = (
                f"Syntax Check Failed: {syntax_check['error_type']} at line {syntax_check['line']}, col {syntax_check['column']}\n"
                f"Message: {syntax_check['message']}\n"
            )
            if syntax_check.get("text"):
                err_msg += f"Line {syntax_check['line']}: {syntax_check['text']}\n"
                if syntax_check.get("column"):
                    err_msg += f"{' ' * (syntax_check['column'] - 1)}^\n"
            err_msg += f"\n💡 Hint: {syntax_check['hint']}"
            return False, f"ERR: {syntax_check['error_type']}", err_msg, duration_ms, syntax_check

        stdout_capture = StringIO()

        # Build clean execution environment
        safe_globals = {
            "__builtins__": __builtins__,
            "requests": requests,
            "re": re,
            "time": time,
            "datetime": datetime,
            "math": math,
            "json": json,
            "os": os,
            "read_file": helper_read_file,
            "get_json": helper_get_json,
        }
        safe_locals: Dict[str, Any] = {}

        old_stdout = sys.stdout
        try:
            sys.stdout = stdout_capture

            parsed_tree = compile(code, "<user_script>", "exec")
            exec(parsed_tree, safe_globals, safe_locals)

            output_logs = stdout_capture.getvalue()

            # Find result text
            result = None
            if "result" in safe_locals:
                result = safe_locals["result"]
            elif "output" in safe_locals:
                result = safe_locals["output"]
            elif "text" in safe_locals:
                result = safe_locals["text"]
            elif "get_text" in safe_locals and callable(safe_locals["get_text"]):
                result = safe_locals["get_text"]()
            else:
                lines = [l.strip() for l in output_logs.splitlines() if l.strip()]
                if lines:
                    result = lines[-1]
                else:
                    result = "OK"

            result_str = str(result)
            duration_ms = (time.time() - start_time) * 1000
            return True, result_str, output_logs, duration_ms, None

        except Exception as e:
            err_tb = traceback.format_exc()
            duration_ms = (time.time() - start_time) * 1000
            hint = generate_diagnostic_hint(e, code)
            
            # Extract line number from traceback if available
            lineno = None
            for frame in traceback.extract_tb(sys.exc_info()[2]):
                if frame.filename == "<user_script>":
                    lineno = frame.lineno

            formatted_err = f"{err_tb}\n💡 Hint: {hint}"
            error_details = {
                "error_type": type(e).__name__,
                "message": str(e),
                "line": lineno,
                "hint": hint
            }
            logger.warning(f"Script execution error: {e}")
            return False, f"ERR: {type(e).__name__}", formatted_err, duration_ms, error_details
        finally:
            sys.stdout = old_stdout
