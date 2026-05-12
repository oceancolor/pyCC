"""
elicitation_handler.py - Handle MCP elicitation requests.

Port of TypeScript elicitationHandler.ts.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ElicitationHandler:
    """Handler for MCP elicitation requests."""

    def __init__(
        self,
        request_input: Callable[[str, Dict[str, Any]], Any],
    ):
        """
        Initialize the elicitation handler.

        Args:
            request_input: Async function to request input from the user.
                Called with (message, schema) and returns user input.
        """
        self._request_input = request_input
        self._pending_requests: Dict[str, Any] = {}

    async def handle_elicitation(
        self,
        elicitation_request: Dict[str, Any],
        server_name: str,
    ) -> Dict[str, Any]:
        """
        Handle a single elicitation request.

        Args:
            elicitation_request: The elicitation request dict with
                'message' and 'requestedSchema' keys
            server_name: Name of the MCP server making the request

        Returns:
            Dict with 'action' ('accept', 'decline', 'cancel') and
            optional 'content' with the user's response.
        """
        message = elicitation_request.get('message', '')
        schema = elicitation_request.get('requestedSchema', {})

        logger.debug(f'[MCP] elicitation from {server_name}: {message[:100]}')

        try:
            # Request input from the user
            result = await self._request_input(message, schema)

            if result is None:
                return {'action': 'cancel'}

            if result is False:
                return {'action': 'decline'}

            return {
                'action': 'accept',
                'content': result,
            }

        except asyncio.CancelledError:
            return {'action': 'cancel'}
        except Exception as e:
            logger.warning(f'[MCP] elicitation error from {server_name}: {e}')
            return {'action': 'cancel'}


def create_elicitation_handler(
    request_input: Callable[[str, Dict[str, Any]], Any],
) -> ElicitationHandler:
    """
    Create an elicitation handler.

    Args:
        request_input: Async function to request input from the user

    Returns:
        ElicitationHandler instance.
    """
    return ElicitationHandler(request_input)
