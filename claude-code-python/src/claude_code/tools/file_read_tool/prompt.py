"""FileReadTool prompt constants. Ported from FileReadTool/prompt.ts"""
FILE_READ_TOOL_NAME = "Read"
FILE_UNCHANGED_STUB = (
    "File unchanged since last read. The content from the earlier Read tool_result "
    "in this conversation is still current — refer to that instead of re-reading."
)
MAX_LINES_TO_READ = 2000
DESCRIPTION = "Read a file from the local filesystem."
LINE_FORMAT_INSTRUCTION = "- Results are returned using cat -n format, with line numbers starting at 1"
OFFSET_INSTRUCTION_DEFAULT = (
    "- You can optionally specify a line offset and limit (especially handy for long files), "
    "but it's recommended to read the whole file by not providing these parameters"
)
