"""Claude looks at each kept piece and tags it, reusing the hoard's own vocabulary."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Protocol

import anthropic

from . import config
from .store import FACETS

# List prices per million tokens (input, output), as of October 2026.
PRICES = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00), "claude-haiku-5-5": (0.10, 0.50)}

SYSTEM = """You catalogue art for one person's private collection. They have just chosen to keep \
this piece. They draw, and will come back to the collection to find pieces to sketch from, so \
the tags must let them browse it by period, movement, region, medium, technique and subject.

Take dates, maker and materials from the museum record; it is right more often than the eye. \
Use the image for what the record leaves out: what the piece shows, how it was made, and the \
school or movement it belongs to.

Reuse a tag from the existing vocabulary whenever one fits, spelled exactly as it is there. \
Coin a new tag only when none fits. Tags are short (one to three words), in sentence case, in \
British English.

- period: the era, one tag. A dynasty or named period where one applies ("Edo period", \
"Ming dynasty"), otherwise the century ("17th century").
- movement: the school, style or movement ("Ukiyo-e", "Dutch Golden Age", "Impressionism", \
"Rococo"). Leave empty when none honestly applies.
- region: where it was made, by modern country or a broad region ("Japan", "Netherlands", \
"Persia").
- medium: the materials, one to three ("Oil paint", "Ink", "Watercolour", "Woodblock print", \
"Albumen print", "Silk").
- technique: how it was made or handled, one to three ("Etching", "Impasto", "Wash", \
"Cross-hatching", "Chiaroscuro", "Flat colour").
- subject: what it shows, one to four ("Landscape", "Portrait", "Birds", "Still life", \
"Interior", "Mythology").
- note: at most two sentences for someone about to sketch this. Say what makes the picture \
work: the composition, the light, the line or the value structure. Be concrete. No praise words."""

TAG_LIST = {"type": "array", "items": {"type": "string"}}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {**{facet: TAG_LIST for facet in FACETS}, "note": {"type": "string"}},
    "required": [*FACETS, "note"],
    "additionalProperties": False,
}


class TagError(Exception):
    """Tagging did not produce tags. The message is shown in the app."""


@dataclass(frozen=True)
class Tags:
    tags: dict[str, list[str]]
    note: str
    model: str
    cost_usd: float | None


class Tagger(Protocol):
    async def tag(self, meta: dict, jpeg: bytes, vocabulary: dict[str, list[str]]) -> Tags: ...


def describe_record(meta: dict) -> str:
    fields = [
        ("Title", meta.get("title")),
        ("Artist", meta.get("artist")),
        ("Artist details", meta.get("artist_bio")),
        ("Culture", meta.get("culture")),
        ("Period", meta.get("period")),
        ("Date", meta.get("date")),
        ("Medium", meta.get("medium")),
        ("Dimensions", meta.get("dimensions")),
        ("Classification", meta.get("classification")),
        ("Department", meta.get("department")),
        ("Collection", meta.get("credit_line") if meta.get("source") == "wikidata" else None),
    ]
    return "\n".join(f"{name}: {value}" for name, value in fields if value)


def build_prompt(meta: dict, vocabulary: dict[str, list[str]]) -> str:
    vocab = "\n".join(
        f"{facet}: {', '.join(values) if values else '(none yet)'}" for facet, values in vocabulary.items()
    )
    return f"Museum record:\n{describe_record(meta)}\n\nExisting vocabulary:\n{vocab}"


def cost(model: str, usage) -> float | None:
    price = PRICES.get(model)
    if not price:
        return None
    return round((usage.input_tokens * price[0] + usage.output_tokens * price[1]) / 1_000_000, 5)


class ClaudeTagger:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None, model: str = config.TAG_MODEL):
        self.client = client or anthropic.AsyncAnthropic()
        self.model = model

    async def tag(self, meta: dict, jpeg: bytes, vocabulary: dict[str, list[str]]) -> Tags:
        image = base64.standard_b64encode(jpeg).decode("ascii")
        try:
            response = await self.client.beta.messages.create(
                model=self.model,
                max_tokens=8000,
                # A declined request is re-run on Anthropic's recommended fallback model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                thinking={"type": "adaptive"},
                output_config={
                    "effort": config.TAG_EFFORT,
                    "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
                },
                system=SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image}},
                            {"type": "text", "text": build_prompt(meta, vocabulary)},
                        ],
                    }
                ],
            )
        except anthropic.AuthenticationError as e:
            raise TagError("The Anthropic API key was refused. Check ANTHROPIC_API_KEY on the Pi.") from e
        except anthropic.RateLimitError as e:
            raise TagError("Claude is rate limiting. Try again in a minute.") from e
        except anthropic.APIStatusError as e:
            raise TagError(f"Claude returned an error ({e.status_code}).") from e
        except anthropic.APIConnectionError as e:
            raise TagError("Couldn't reach Claude. Is the Pi online?") from e

        if response.stop_reason == "refusal":
            raise TagError("Claude declined to tag this piece.")
        if response.stop_reason == "max_tokens":
            raise TagError("Claude's answer was cut short.")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise TagError("Claude returned no tags.")
        data = json.loads(text)
        return Tags(
            tags={facet: [str(v) for v in data.get(facet, [])] for facet in FACETS},
            note=str(data.get("note", "")).strip(),
            model=response.model,
            cost_usd=cost(response.model, response.usage),
        )
