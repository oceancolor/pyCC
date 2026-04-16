GREP_TOOL_NAME = "Grep"

def get_description() -> str:
    return (
        "A powerful search tool built on ripgrep (falls back to Python re).\n\n"
        "Usage:\n"
        "- Supports full regex syntax (e.g., \"log.*Error\", \"function\\s+\\w+\")\n"
        "- Filter files with glob parameter (e.g., \"*.js\", \"**/*.tsx\")\n"
        "- Output modes: \"content\" shows matching lines, \"files_with_matches\" shows only file paths (default), \"count\" shows match counts"
    )
