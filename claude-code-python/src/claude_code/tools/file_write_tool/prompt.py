FILE_WRITE_TOOL_NAME = "Write"

def get_write_tool_description() -> str:
    return (
        "Write a file to the local filesystem.\n\n"
        "Usage:\n"
        "- Use this to create new files or completely overwrite existing ones\n"
        "- The file_path must be an absolute path\n"
        "- For partial edits, prefer the Edit tool instead"
    )
