import subprocess

from app.config import PROJECT_ROOT


def execute_command(command):
    try:
        result = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=100,
        )
        return {
            "stderr": result.stderr,
            "stdout": result.stdout,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "stderr": f"Command timed out after 100 seconds: {command}",
            "stdout": "",
            "returncode": -1,
        }
    except FileNotFoundError:
        return {
            "stderr": "bash not found on PATH. Ensure Git Bash or WSL is installed.",
            "stdout": "",
            "returncode": -1,
        }
    except Exception as e:
        return {
            "stderr": f"Error executing command: {str(e)}",
            "stdout": "",
            "returncode": -1,
        }
