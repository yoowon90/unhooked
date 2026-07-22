"""OpenAI Realtime session and web-search helpers for a voice client."""
import asyncio
import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

import requests

JsonValue: TypeAlias = (
    str | int | float | bool | None | list['JsonValue'] | dict[str, 'JsonValue']
)
JsonObject: TypeAlias = dict[str, JsonValue]

REALTIME_SECRETS_URL: str = 'https://api.openai.com/v1/realtime/client_secrets'
RESPONSES_URL: str = 'https://api.openai.com/v1/responses'
MAX_ATTEMPTS: int = 2


class VoiceSearchError(RuntimeError):
    """Base error for Realtime voice-search failures."""


class OpenAIConfigurationError(VoiceSearchError):
    """Raised when the server lacks OpenAI credentials."""


class TransientOpenAIError(VoiceSearchError):
    """Raised when an OpenAI request should be attempted again."""


@dataclass(frozen=True)
class SearchSource:
    """One cited source returned by OpenAI web search."""

    title: str
    url: str

    def to_dict(self) -> dict[str, str]:
        """Return the source as JSON data."""
        return {'title': self.title, 'url': self.url}


@dataclass(frozen=True)
class VoiceSearchResult:
    """Spoken answer text and its visible web sources."""

    answer: str
    sources: list[SearchSource]

    def to_dict(self) -> JsonObject:
        """Return an API-ready result payload."""
        result: JsonObject = {
            'answer': self.answer,
            'sources': [source.to_dict() for source in self.sources],
        }
        return result

    def realtime_events(self, call_id: str) -> list[JsonObject]:
        """Build events that return tool output and continue the voice response."""
        return _tool_events(call_id, json.dumps(self.to_dict()))


def _api_key() -> str:
    """Return the configured server-side OpenAI API key."""
    api_key: str | None = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise OpenAIConfigurationError('OPENAI_API_KEY is not configured')
    return api_key


async def _retry(request_call: Callable[[], JsonObject]) -> JsonObject:
    """Run one OpenAI request with a short retry for transient responses."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return await asyncio.to_thread(request_call)
        except TransientOpenAIError:
            if attempt == MAX_ATTEMPTS:
                raise
            await asyncio.sleep(0.1 * attempt)
    raise VoiceSearchError('OpenAI retry loop ended unexpectedly')


async def create_realtime_session(user_id: str) -> JsonObject:
    """Create an ephemeral Realtime client secret for one authenticated user.

    Args:
        user_id: Internal user identifier used to derive a safety identifier.

    Returns:
        OpenAI's ephemeral client-secret response.
    """
    safety_identifier: str = hashlib.sha256(user_id.encode()).hexdigest()

    def request_session() -> JsonObject:
        """Send one Realtime client-secret request."""
        headers: dict[str, str] = {
            'Authorization': f'Bearer {_api_key()}',
            'Content-Type': 'application/json',
            'OpenAI-Safety-Identifier': safety_identifier,
        }
        response: requests.Response = requests.post(
            REALTIME_SECRETS_URL,
            headers=headers,
            json={
                'session': {
                    'type': 'realtime',
                    'model': 'gpt-realtime-2.1',
                    'audio': {'output': {'voice': 'marin'}},
                    'tools': [_search_tool()],
                    'tool_choice': 'auto',
                },
            },
            timeout=30,
        )
        if response.status_code != 200:
            raise TransientOpenAIError(
                f'OpenAI returned HTTP {response.status_code} while creating a session'
            )
        try:
            payload: JsonObject = response.json()
        except ValueError as error:
            raise VoiceSearchError('OpenAI returned invalid session JSON') from error
        return payload

    return await _retry(request_session)


async def execute_web_search(query: str) -> VoiceSearchResult:
    """Run an OpenAI web search and return its answer and visible sources."""
    def request_search() -> JsonObject:
        """Send one Responses API web-search request."""
        headers: dict[str, str] = {
            'Authorization': f'Bearer {_api_key()}',
            'Content-Type': 'application/json',
        }
        response: requests.Response = requests.post(
            RESPONSES_URL,
            headers=headers,
            json={
                'model': 'gpt-5.5',
                'tools': [{'type': 'web_search'}],
                'input': query,
                'include': ['web_search_call.action.sources'],
            },
            timeout=30,
        )
        if response.status_code != 200:
            raise TransientOpenAIError(
                f'OpenAI returned HTTP {response.status_code} while searching'
            )
        try:
            payload: JsonObject = response.json()
        except ValueError as error:
            raise VoiceSearchError('OpenAI returned invalid search JSON') from error
        return payload

    response_payload: JsonObject = await _retry(request_search)
    answer: str = _extract_answer(response_payload)
    sources: list[SearchSource] = extract_sources(response_payload)
    return VoiceSearchResult(answer=answer, sources=sources)


def _extract_answer(payload: JsonObject) -> str:
    """Find assistant output text across Responses API output items."""
    output_value: JsonValue = payload.get('output')
    if not isinstance(output_value, list):
        raise VoiceSearchError('OpenAI search response has no output list')
    for item in output_value:
        if not isinstance(item, dict) or item.get('type') != 'message':
            continue
        content_value: JsonValue = item.get('content')
        if not isinstance(content_value, list):
            continue
        for content in content_value:
            if isinstance(content, dict) and content.get('type') == 'output_text':
                text_value: JsonValue = content.get('text')
                if isinstance(text_value, str) and text_value.strip():
                    return text_value.strip()
    raise VoiceSearchError('OpenAI search response has no answer text')


def extract_sources(payload: JsonObject) -> list[SearchSource]:
    """Extract unique web-search citations from an OpenAI response."""
    sources: list[SearchSource] = []
    try:
        output_value: JsonValue = payload['output']
        if not isinstance(output_value, list):
            raise TypeError('output must be a list')
        for item in output_value:
            if not isinstance(item, dict) or item.get('type') != 'message':
                continue
            content_value: JsonValue = item.get('content')
            if not isinstance(content_value, list):
                continue
            for content in content_value:
                if not isinstance(content, dict):
                    continue
                annotations_value: JsonValue = content.get('annotations')
                if not isinstance(annotations_value, list):
                    continue
                for annotation in annotations_value:
                    if not isinstance(annotation, dict):
                        continue
                    title_value: JsonValue = annotation.get('title')
                    url_value: JsonValue = annotation.get('url')
                    if isinstance(title_value, str) and isinstance(url_value, str):
                        sources.append(SearchSource(title_value, url_value))
    except Exception as error:
        print(f'Could not extract voice-search sources: {error}')
        return []

    unique_urls: set[str] = set()
    unique_sources: list[SearchSource] = []
    for source in sources:
        if source.url not in unique_urls:
            unique_urls.add(source.url)
            unique_sources.append(source)
    return unique_sources


def _search_tool() -> JsonObject:
    """Return the Realtime function-tool definition for web search."""
    return {
        'type': 'function',
        'name': 'search_web',
        'description': 'Search the live web for the user and cite useful sources.',
        'parameters': {
            'type': 'object',
            'properties': {
                'query': {
                    'type': 'string',
                    'description': 'The concise web-search query.',
                },
            },
            'required': ['query'],
            'additionalProperties': False,
        },
    }


def _tool_events(call_id: str, output: str) -> list[JsonObject]:
    """Build the standard tool-output and response-continuation events."""
    return [
        {
            'type': 'conversation.item.create',
            'item': {
                'type': 'function_call_output',
                'call_id': call_id,
                'output': output,
            },
        },
        {'type': 'response.create'},
    ]


async def build_failure_events(call_id: str, message: str) -> list[JsonObject]:
    """Build a tool failure output for a Realtime client."""
    await asyncio.sleep(0)
    return _tool_events(call_id, json.dumps({'error': message}))
