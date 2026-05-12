"""
files_api.py - Files API client for managing files.

Port of TypeScript filesApi.ts.
"""

import logging
import os
from typing import Any, BinaryIO, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

FILES_API_URL = 'https://api.anthropic.com/v1/files'


async def upload_file_to_files_api(
    client: Any,
    file_data: Union[bytes, BinaryIO],
    filename: str,
    mime_type: str = 'application/octet-stream',
) -> Dict[str, Any]:
    """
    Upload a file to the Anthropic Files API.

    Args:
        client: Anthropic API client
        file_data: File content as bytes or file-like object
        filename: Name of the file
        mime_type: MIME type of the file

    Returns:
        File metadata dict with 'id', 'filename', etc.

    Raises:
        Exception: If upload fails.
    """
    try:
        if hasattr(client, 'beta') and hasattr(client.beta, 'files'):
            result = await client.beta.files.upload(
                file=(filename, file_data, mime_type),
            )
            return result.model_dump() if hasattr(result, 'model_dump') else dict(result)

        # Fallback via HTTP
        import httpx
        from ...utils.auth import get_api_key

        api_key = get_api_key()
        if not api_key:
            raise ValueError('No API key configured')

        if isinstance(file_data, bytes):
            content = file_data
        else:
            content = file_data.read()

        async with httpx.AsyncClient() as http:
            response = await http.post(
                FILES_API_URL,
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'anthropic-beta': 'files-api-2025-04-14',
                },
                files={'file': (filename, content, mime_type)},
            )
            response.raise_for_status()
            return response.json()

    except Exception as e:
        logger.error(f'Files API upload failed: {e}')
        raise


async def delete_file_from_files_api(
    client: Any,
    file_id: str,
) -> bool:
    """
    Delete a file from the Anthropic Files API.

    Args:
        client: Anthropic API client
        file_id: The file ID to delete

    Returns:
        True if deleted successfully.
    """
    try:
        if hasattr(client, 'beta') and hasattr(client.beta, 'files'):
            await client.beta.files.delete(file_id)
            return True

        # Fallback via HTTP
        import httpx
        from ...utils.auth import get_api_key

        api_key = get_api_key()
        if not api_key:
            raise ValueError('No API key configured')

        async with httpx.AsyncClient() as http:
            response = await http.delete(
                f'{FILES_API_URL}/{file_id}',
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'anthropic-beta': 'files-api-2025-04-14',
                },
            )
            return response.status_code in (200, 204)

    except Exception as e:
        logger.error(f'Files API delete failed for {file_id}: {e}')
        return False


async def list_files_from_files_api(client: Any) -> List[Dict[str, Any]]:
    """
    List all files in the Anthropic Files API.

    Args:
        client: Anthropic API client

    Returns:
        List of file metadata dicts.
    """
    try:
        if hasattr(client, 'beta') and hasattr(client.beta, 'files'):
            files_page = await client.beta.files.list()
            if hasattr(files_page, 'data'):
                return [
                    f.model_dump() if hasattr(f, 'model_dump') else dict(f)
                    for f in files_page.data
                ]

        # Fallback via HTTP
        import httpx
        from ...utils.auth import get_api_key

        api_key = get_api_key()
        if not api_key:
            return []

        async with httpx.AsyncClient() as http:
            response = await http.get(
                FILES_API_URL,
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'anthropic-beta': 'files-api-2025-04-14',
                },
            )
            response.raise_for_status()
            return response.json().get('data', [])

    except Exception as e:
        logger.error(f'Files API list failed: {e}')
        return []
