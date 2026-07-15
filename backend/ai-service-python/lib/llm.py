"""
lib/llm.py — English → Mexican Spanish via Anthropic Claude.

Provider is swappable through the environment: set MODEL (and the matching
API key) in `.env`. FAIL LOUD: a provider failure propagates to the caller,
which returns a 502 — this module never returns the untranslated input.
"""
import os

from anthropic import AsyncAnthropic

MODEL_DEFAULT = os.getenv("MODEL", "claude-sonnet-4-6")

_client: AsyncAnthropic | None = None

SYSTEM_PROMPT = (
    "You are a professional translator localizing website content from English into "
    "Mexican Spanish (es-MX) — the natural register used on consumer and e-commerce "
    "sites in Mexico.\n"
    "Rules:\n"
    "- Return ONLY the translation. No preamble, no explanations, no notes, no "
    "wrapping quotes.\n"
    "- Use Mexican vocabulary and grammar: 'computadora' not 'ordenador', 'carrito' "
    "not 'cesta', 'ustedes' never 'vosotros'. Avoid Castilian (Spain) forms entirely.\n"
    "- Preserve EXACTLY as written: numbers, prices ($49.99), percentages, "
    "product/model/SKU codes (e.g. SKU-4471, XZ-200), URLs, email addresses, "
    "brand names, and template placeholders.\n"
    "- Mirror the source's capitalization style and end punctuation: a Title Case "
    "heading stays a heading, an ALL-CAPS label stays ALL-CAPS, do not add a "
    "final period where the source has none.\n"
    "- Short UI strings are interface labels — translate them the way Mexican "
    "websites label them: 'Add to cart' → 'Agregar al carrito', 'Sign in' → "
    "'Iniciar sesión', 'Checkout' → 'Pagar'.\n"
    "- If the text is untranslatable (a bare number or code) or is already "
    "Spanish, return it unchanged."
)


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        # Reads ANTHROPIC_API_KEY from the environment; the SDK retries
        # 429s/5xx twice with backoff, which protects the benchmark error rate.
        _client = AsyncAnthropic()
    return _client


def _clean(s: str) -> str:
    """Strip whitespace and symmetric wrapping quotes the model may add."""
    s = s.strip()
    for open_q, close_q in (('"', '"'), ("“", "”"), ("'", "'")):
        if len(s) >= 2 and s[0] == open_q and s[-1] == close_q:
            inner = s[1:-1]
            if open_q not in inner and close_q not in inner:
                return inner.strip()
    return s


async def translate_text(text: str, target: str = "es-MX", model: str = MODEL_DEFAULT) -> str:
    """Return `text` translated into Mexican Spanish.

    Raises on any provider failure so the caller can return a 502 — never
    falls back to returning the input as if it were translated.
    """
    msg = await _get_client().messages.create(
        model=model,
        max_tokens=min(4096, max(256, len(text))),
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Translate to Mexican Spanish (target: {target}):\n{text}",
            }
        ],
    )
    return _clean(msg.content[0].text)
