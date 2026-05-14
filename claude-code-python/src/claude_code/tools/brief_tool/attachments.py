"""BriefTool attachment validation. Ported from BriefTool/attachments.ts"""
from __future__ import annotations
import os
import re
from typing import Optional

IMAGE_EXTENSION_REGEX = re.compile(r"\.(png|jpg|jpeg|gif|webp|svg|bmp|ico)$", re.IGNORECASE)


class ResolvedAttachment:
    def __init__(self, path: str, size: int, is_image: bool, file_uuid: Optional[str] = None):
        self.path = path
        self.size = size
        self.is_image = is_image
        self.file_uuid = file_uuid

    def to_dict(self) -> dict:
        result: dict = {"path": self.path, "size": self.size, "isImage": self.is_image}
        if self.file_uuid is not None:
            result["fileUuid"] = self.file_uuid
        return result


def validate_attachment_paths(raw_paths: list[str]) -> dict:
    """Validate a list of attachment file paths.

    Returns a dict with 'result' (bool) and optional 'message'/'errorCode'.
    """
    for raw_path in raw_paths:
        full_path = os.path.expanduser(raw_path)
        if not os.path.isabs(full_path):
            cwd = os.getcwd()
            full_path = os.path.join(cwd, raw_path)
        if not os.path.exists(full_path):
            return {
                "result": False,
                "message": f'Attachment "{raw_path}" does not exist.',
                "errorCode": 1,
            }
        if not os.path.isfile(full_path):
            return {
                "result": False,
                "message": f'Attachment "{raw_path}" is not a regular file.',
                "errorCode": 1,
            }
    return {"result": True}


async def resolve_attachments(raw_paths: list[str]) -> list[ResolvedAttachment]:
    """Resolve attachment paths to ResolvedAttachment objects."""
    resolved = []
    for raw_path in raw_paths:
        full_path = os.path.expanduser(raw_path)
        if not os.path.isabs(full_path):
            full_path = os.path.join(os.getcwd(), raw_path)
        try:
            size = os.path.getsize(full_path)
        except OSError:
            size = 0
        is_image = bool(IMAGE_EXTENSION_REGEX.search(raw_path))
        resolved.append(ResolvedAttachment(path=full_path, size=size, is_image=is_image))
    return resolved
