import ast
from pathlib import Path
from typing import Dict, Any

from app.config import PROJECT_ROOT


def resolve_path(file_path: str) -> Path:
    path = (PROJECT_ROOT / file_path).resolve()
    if not path.is_relative_to(PROJECT_ROOT):
        raise ValueError(
            f"Access denied: {file_path} is outside the project directory."
        )
    return path


def read_file(file_path: str) -> Dict[str, Any]:
    if not file_path:
        raise RuntimeError("file_path argument is required for Read function")

    try:
        path = resolve_path(file_path)

        if not path.is_file():
            return {"success": False, "message": f"{file_path} does not exist."}
        with open(path, "r", encoding="utf-8") as f:
            result = f.read()
        return {"success": True, "message": result}
    except ValueError as e:
        return {"success": False, "message": str(e)}
    except Exception as e:
        return {
            "success": False,
            "message": f"Error reading file {file_path}: {str(e)}",
        }


def write_file(file_path: str, content: str) -> Dict[str, Any]:
    try:
        path = resolve_path(file_path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            return {"success": True, "message": f"Successfully wrote {file_path}"}
    except ValueError as e:
        return {"success": False, "message": str(e)}
    except Exception as e:
        return {
            "success": False,
            "message": f"Error writing file {file_path}: {str(e)}",
        }


def find_function_in_file(file_path: str, function_name: str) -> Dict[str, Any]:
    file_content = read_file(file_path)
    if not file_content.get("success"):
        return {
            "success": False,
            "message": file_content.get("message", "Unknown error reading file."),
        }

    source_text = file_content.get("message", "")
    tree = ast.parse(source_text)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            source = ast.get_source_segment(source_text, node)
            return {
                "success": True,
                "message": source,
            }
    return {
        "success": False,
        "message": f"Function '{function_name}' not found in {file_path}.",
    }


def patch_file(file_path: str, search_block: str, replacement_block: str) -> Dict[str, Any]:
    try:
        path = resolve_path(file_path=file_path)
        if not path.exists():
            return {"success": False, "message": f"{file_path} does not exist."}
        content = read_file(file_path=file_path)
        if not content.get("success"):
            return {
                "success": False,
                "message": content.get("message", "Unknown error reading file."),
            }
        normalized_content = content["message"].replace("\r\n", "\n")
        normalized_search = search_block.replace("\r\n", "\n")
        normalized_replacement = replacement_block.replace("\r\n", "\n")

        match_count = normalized_content.count(normalized_search)
        if match_count == 0:
            return {
                "success": False,
                "message": f"Search block not found in {file_path}.",
            }
        if match_count > 1:
            return {
                "success": False,
                "message": f"Search block found {match_count} times in {file_path}. resolve it first before patching.",
            }
        new_content = normalized_content.replace(normalized_search, normalized_replacement)
        write_result = write_file(file_path=file_path, content=new_content)
        if not write_result.get("success"):
            return {
                "success": False,
                "message": write_result.get("message", "Unknown error writing file."),
            }
        return {
            "success": True,
            "message": "File patched successfully",
        }
    except ValueError as e:
        return {"success": False, "message": str(e)}
