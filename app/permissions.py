import json


def ask_user_permission(tool_name: str, arguments: dict) -> bool:
    """CLI prompt to grant or reject tool execution."""
    print("\n" + "=" * 50)
    print(f"⚠️  PERMISSION REQUIRED: The agent wants to execute `{tool_name}`")
    print("Arguments:")
    print(json.dumps(arguments, indent=2))
    print("=" * 50)

    #loop until user provides valid input
    while True:
        choice = input("Allow this action? [y/N]: ").strip().lower()
        if choice in ("y", "yes"):
            return True
        if choice in ("", "n", "no"):
            return False
        print("Please enter 'y' for yes or 'n' for no.")
