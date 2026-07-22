"""Happy-path behavior for the OpenAI voice-search utilities."""
import asyncio

import pytest

from website.voice_search import JsonObject, VoiceSearchResult, execute_web_search


class SearchResponse:
    """Successful Responses API payload used at the HTTP boundary."""

    status_code: int = 200

    def json(self) -> JsonObject:
        """Return one assistant answer with a visible URL citation."""
        return {
            'output': [{
                'type': 'message',
                'content': [{
                    'type': 'output_text',
                    'text': 'The City Museum stays open until 8 PM tonight.',
                    'annotations': [{
                        'type': 'url_citation',
                        'title': 'City Museum hours',
                        'url': 'https://museum.example/hours',
                    }],
                }],
            }],
        }


def test_web_search_returns_answer_sources_and_realtime_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful web search is ready for display and voice continuation."""
    def fake_post(
        url: str,
        headers: dict[str, str],
        json: JsonObject,
        timeout: int,
    ) -> SearchResponse:
        """Return a deterministic OpenAI web-search response."""
        assert url.endswith('/v1/responses')
        assert headers['Authorization'] == 'Bearer test-key'
        assert json['tools'] == [{'type': 'web_search'}]
        assert timeout == 30
        return SearchResponse()

    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setattr('website.voice_search.requests.post', fake_post)

    result: VoiceSearchResult = asyncio.run(
        execute_web_search('What time does the City Museum close?')
    )
    events: list[JsonObject] = result.realtime_events('call-123')

    assert result.to_dict() == {
        'answer': 'The City Museum stays open until 8 PM tonight.',
        'sources': [{
            'title': 'City Museum hours',
            'url': 'https://museum.example/hours',
        }],
    }
    assert events[0]['item']['call_id'] == 'call-123'
    assert events[1] == {'type': 'response.create'}
