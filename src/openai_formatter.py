"""
OpenAI GPT-4o mini Transcript Formatter
Uses OpenAI API for paragraph formatting
"""

import json
import re
import logging
import requests
from typing import Dict
import os
from pathlib import Path

from config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_TIMEOUT,
    OPENAI_4O_MINI_CHUNK_THRESHOLD,
    OPENAI_4O_MINI_CHUNK_SIZE,
    OPENAI_5_NANO_CHUNK_THRESHOLD,
    OPENAI_5_NANO_CHUNK_SIZE,
    PARAGRAPH_FORMATTING_INSTRUCTIONS,
    TRANSCRIPT_CLEANUP_INSTRUCTIONS
)

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OpenAIFormatter:
    """Formats transcripts using OpenAI API (GPT-4o mini or GPT-5 nano)"""

    def __init__(self, model=None):
        """
        Initialize OpenAI client

        Args:
            model: Optional model name (e.g., "gpt-4o-mini", "gpt-5-nano"). Defaults to config.OPENAI_MODEL
        """
        self.api_key = OPENAI_API_KEY
        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY env var or add "
                "\"openai_api_key\" to ~/TranscriptProcessor/config/credentials.json."
            )
        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.responses_url = "https://api.openai.com/v1/responses"
        self.model = (model or OPENAI_MODEL or "").strip()
        self.timeout = OPENAI_TIMEOUT

        # Set chunk sizes based on model (GPT-5 nano has 8x larger output than 4o mini)
        if "gpt-5-nano" in self.model:
            self.chunk_threshold = OPENAI_5_NANO_CHUNK_THRESHOLD
            self.chunk_size = OPENAI_5_NANO_CHUNK_SIZE
            self.max_tokens = 128000  # GPT-5 nano supports 128K output
        else:  # gpt-4o-mini or other
            self.chunk_threshold = OPENAI_4O_MINI_CHUNK_THRESHOLD
            self.chunk_size = OPENAI_4O_MINI_CHUNK_SIZE
            self.max_tokens = 16384  # GPT-4o mini supports 16K output
        # Use Responses API for GPT-5 models (recommended by OpenAI)
        model_lower = self.model.lower()
        self.use_responses_api = model_lower.startswith("gpt-5") or "gpt-5" in model_lower

    @staticmethod
    def _build_responses_input(system_text: str, user_text: str) -> list:
        """Build Responses API input items with explicit text parts."""
        return [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_text}]
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_text}]
            }
        ]

    @staticmethod
    def _format_http_error(e: requests.exceptions.RequestException) -> str:
        """Return a helpful error string including response body when available."""
        response = getattr(e, "response", None)
        if response is not None:
            try:
                body = response.text.strip()
            except Exception:
                body = ""
            if body:
                return f"{str(e)} | Response: {body}"
        return str(e)

    @staticmethod
    def _estimate_output_tokens(text: str, multiplier: float = 1.3, floor: int = 2048) -> int:
        """Estimate output tokens based on word count."""
        words = len(text.split())
        # Rough: 1 token ~= 0.75 words => tokens ~= words / 0.75
        estimated = int((words / 0.75) * multiplier)
        return max(floor, estimated)

    @staticmethod
    def _count_words(text: str) -> int:
        return len(text.split())

    def format_into_paragraphs(self, raw_transcript: str, progress_callback=None) -> str:
        """
        Format raw transcript into logical paragraphs with improved punctuation

        Automatically chooses between single-pass or chunked processing based on length.

        Args:
            raw_transcript: Raw transcript text from Whisper
            progress_callback: Optional callback for progress updates

        Returns:
            Formatted transcript with paragraph breaks and punctuation

        Raises:
            RuntimeError: If formatting fails
        """
        transcript_length = len(raw_transcript)

        if progress_callback:
            progress_callback(f"Input transcript: {transcript_length:,} characters")

        # Check if single-pass is possible based on model output limits
        if transcript_length <= self.chunk_threshold:
            if progress_callback:
                model_name = "GPT-5 nano" if "gpt-5-nano" in self.model else "GPT-4o mini"
                progress_callback(f"→ Using single-pass formatting ({model_name})")
            return self._format_paragraph_chunk(raw_transcript, progress_callback)
        else:
            # Long transcript, chunk it
            if progress_callback:
                model_name = "GPT-5 nano" if "gpt-5-nano" in self.model else "GPT-4o mini"
                progress_callback(f"→ Long transcript ({transcript_length:,} chars), using chunks ({model_name})")
            return self._format_long_transcript(raw_transcript, progress_callback)

    def _extract_responses_text(self, result: dict) -> str:
        """
        Extract text from Responses API payload.
        Tries common fields to be robust across API changes.
        """
        def _coerce_text(value):
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                if isinstance(value.get("text"), str):
                    return value["text"]
                if isinstance(value.get("value"), str):
                    return value["value"]
                if isinstance(value.get("content"), str):
                    return value["content"]
            return None

        if isinstance(result, dict):
            status = result.get("status")
            if status and status != "completed":
                incomplete = result.get("incomplete_details")
                raise ValueError(f"OpenAI response status={status}. Incomplete: {incomplete}")

            # Common shortcut field
            output_text = result.get("output_text")
            if isinstance(output_text, str):
                return output_text
            if isinstance(output_text, list):
                joined = "".join([t for t in output_text if isinstance(t, str)])
                if joined:
                    return joined

            # Some responses include a top-level "text"
            top_text = result.get("text")
            if isinstance(top_text, str):
                return top_text
            if isinstance(top_text, dict):
                text_value = _coerce_text(top_text)
                if text_value:
                    return text_value
            if isinstance(top_text, list):
                collected_top = []
                for item in top_text:
                    text_value = _coerce_text(item)
                    if text_value:
                        collected_top.append(text_value)
                if collected_top:
                    return "".join(collected_top)

            output_items = result.get("output", [])
            collected = []
            if isinstance(output_items, list):
                for item in output_items:
                    if not isinstance(item, dict):
                        continue

                    # Sometimes output items are direct text
                    if item.get("type") in ("output_text", "text") and "text" in item:
                        text_value = _coerce_text(item.get("text"))
                        if text_value:
                            collected.append(text_value)
                            continue

                    content = item.get("content", [])
                    if isinstance(content, str):
                        collected.append(content)
                        continue
                    if not isinstance(content, list):
                        continue

                    for part in content:
                        if not isinstance(part, dict):
                            continue
                        part_type = part.get("type")
                        if part_type in ("output_text", "text", "output_text_delta"):
                            text_value = _coerce_text(part.get("text"))
                            if text_value:
                                collected.append(text_value)

            if collected:
                return "".join(collected)

            # Fallback if API returns chat-like structure
            choices = result.get("choices")
            if isinstance(choices, list) and choices:
                message = choices[0].get("message", {})
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content

        if isinstance(result, dict) and isinstance(result.get("error"), dict):
            err = result["error"]
            message = err.get("message") or str(err)
            raise ValueError(f"OpenAI response error: {message}")

        top_keys = list(result.keys()) if isinstance(result, dict) else type(result)
        raise ValueError(f"OpenAI response did not include output text. Keys: {top_keys}")

    def _maybe_dump_response(self, result: dict, tag: str) -> None:
        """Optionally dump the raw response for debugging."""
        if os.getenv("OPENAI_DEBUG_RESPONSES") != "1":
            return
        try:
            log_dir = Path.home() / "Library" / "Logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            out_path = log_dir / f"TranscriptProcessor-OpenAI-{tag}.json"
            out_path.write_text(json.dumps(result, indent=2))
        except Exception:
            pass

    @staticmethod
    def _is_max_output_incomplete(err: Exception) -> bool:
        msg = str(err)
        return "status=incomplete" in msg and "max_output_tokens" in msg

    def _format_paragraph_chunk(self, text: str, progress_callback=None) -> str:
        """
        Format a single chunk of text into paragraphs using OpenAI

        Args:
            text: Text to format
            progress_callback: Optional callback for progress updates

        Returns:
            Formatted text with paragraph breaks

        Raises:
            RuntimeError: If formatting fails
        """
        prompt = f"""{PARAGRAPH_FORMATTING_INSTRUCTIONS}

---

Raw transcript to format:

{text}

---

Return ONLY the formatted transcript text with paragraph breaks. No explanations."""

        try:
            if progress_callback:
                model_name = "GPT-5 nano" if "gpt-5-nano" in self.model else "GPT-4o mini"
                progress_callback(f"Formatting {len(text):,} characters with {model_name}...")

            if self.use_responses_api:
                if progress_callback:
                    progress_callback(f"OpenAI request via Responses API (model: {self.model})")
                # Estimate output tokens to avoid oversizing and timeouts
                word_count = self._count_words(text)
                max_output = min(self.max_tokens, self._estimate_output_tokens(text, multiplier=2.2, floor=12000))
                if progress_callback:
                    progress_callback(f"Formatting size: {word_count:,} words → max_output_tokens {max_output:,}")
                system_text = (
                    "You are a precise transcript formatter. You ONLY add punctuation and paragraph breaks. "
                    "You NEVER change, add, or remove words. Output ONLY the formatted transcript with no explanations or commentary."
                )
                for attempt in range(3):
                    request_json = {
                        "model": self.model,
                        "input": self._build_responses_input(system_text, prompt),
                        "max_output_tokens": max_output
                    }

                    try:
                        response = requests.post(
                            self.responses_url,
                            headers={
                                "Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json"
                            },
                            json=request_json,
                            timeout=max(self.timeout, 240)
                        )
                        response.raise_for_status()
                        result = response.json()
                        self._maybe_dump_response(result, "formatting")
                        formatted_text = self._extract_responses_text(result).strip()
                        break
                    except requests.exceptions.ReadTimeout:
                        if attempt == 2:
                            raise
                        continue
                    except ValueError as e:
                        if self._is_max_output_incomplete(e) and max_output < self.max_tokens:
                            max_output = min(self.max_tokens, max_output * 2)
                            if progress_callback:
                                progress_callback(f"Retrying formatting with higher max_output_tokens: {max_output}")
                            continue
                        raise
            else:
                if progress_callback:
                    progress_callback(f"OpenAI request via Chat Completions (model: {self.model})")
                request_json = {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a precise transcript formatter. You ONLY add punctuation and paragraph breaks. You NEVER change, add, or remove words. Output ONLY the formatted transcript with no explanations or commentary."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.1  # Very low temperature for consistency
                }

                request_json["max_tokens"] = self.max_tokens

                response = requests.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json=request_json,
                    timeout=self.timeout
                )
                response.raise_for_status()
                result = response.json()
                formatted_text = result['choices'][0]['message']['content'].strip()

            if not formatted_text:
                raise ValueError("OpenAI returned empty response")

            # Detect if model used placeholders instead of actual content
            placeholder_patterns = [
                "[The formatting continues",
                "[The transcript continues",
                "[Text continues",
                "continues in this manner",
                "continues with this pattern"
            ]

            for pattern in placeholder_patterns:
                if pattern in formatted_text:
                    raise ValueError(f"OpenAI used placeholder text ('{pattern}') instead of formatting complete transcript. Input may be too long.")

            # Verify output length is reasonable (should be similar to input)
            input_length = len(text)
            output_length = len(formatted_text)
            ratio = output_length / input_length if input_length > 0 else 0

            # Output should be 70%-150% of input (accounting for added punctuation)
            if ratio < 0.7 or ratio > 1.5:
                if progress_callback:
                    progress_callback(f"⚠️  Warning: Output length unusual (input: {input_length:,}, output: {output_length:,}, ratio: {ratio:.2f})")

            return formatted_text

        except requests.exceptions.RequestException as e:
            error_msg = f"OpenAI request failed: {self._format_http_error(e)}"
            if progress_callback:
                progress_callback(f"✗ {error_msg}")
            raise RuntimeError(error_msg)

        except Exception as e:
            error_msg = f"Paragraph formatting failed: {str(e)}"
            if progress_callback:
                progress_callback(f"✗ {error_msg}")
            raise RuntimeError(error_msg)

    def _format_long_transcript(self, text: str, progress_callback=None) -> str:
        """
        Format a long transcript by processing in chunks

        Args:
            text: Full transcript text
            progress_callback: Optional callback for progress updates

        Returns:
            Complete formatted transcript
        """
        # Split into sentences to avoid breaking mid-sentence
        sentences = re.split(r'([.!?]+\s+)', text)

        # Rebuild sentences
        full_sentences = []
        for i in range(0, len(sentences) - 1, 2):
            sentence = sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else '')
            full_sentences.append(sentence)

        # Add any remaining fragment
        if len(sentences) % 2 == 1:
            full_sentences.append(sentences[-1])

        # Group sentences into chunks based on model capacity
        # GPT-5 nano: 128K output tokens (~512K chars), GPT-4o mini: 16K output tokens (~64K chars)
        # Use 80% of chunk_size as target, chunk_size as max
        target_chunk_size = int(self.chunk_size * 0.8)
        max_chunk_size = self.chunk_size

        chunks = []
        current_chunk = []
        current_length = 0

        for sentence in full_sentences:
            sentence_length = len(sentence)

            # If adding this sentence would exceed target, close current chunk
            if current_chunk and current_length + sentence_length > target_chunk_size:
                chunks.append(''.join(current_chunk))
                current_chunk = []
                current_length = 0

            # Handle edge case: single sentence longer than max_chunk_size
            if sentence_length > max_chunk_size:
                # If we have accumulated text, save it first
                if current_chunk:
                    chunks.append(''.join(current_chunk))
                    current_chunk = []
                    current_length = 0

                # Split long sentence at word boundaries
                words = sentence.split()
                temp_chunk = []
                temp_length = 0

                for word in words:
                    word_with_space = word + ' '
                    word_length = len(word_with_space)

                    if temp_length + word_length > max_chunk_size and temp_chunk:
                        chunks.append(''.join(temp_chunk).strip())
                        temp_chunk = []
                        temp_length = 0

                    temp_chunk.append(word_with_space)
                    temp_length += word_length

                # Add remaining words as a new sentence start
                if temp_chunk:
                    current_chunk = temp_chunk
                    current_length = temp_length
            else:
                # Normal case: add sentence to current chunk
                current_chunk.append(sentence)
                current_length += sentence_length

        # Add any remaining text as final chunk
        if current_chunk:
            chunks.append(''.join(current_chunk))

        # Process each chunk
        formatted_chunks = []
        total_chunks = len(chunks)

        if progress_callback:
            model_name = "GPT-5 nano" if "gpt-5-nano" in self.model else "GPT-4o mini"
            progress_callback(f"Processing {total_chunks} chunks with {model_name}...")

        for i, chunk in enumerate(chunks, 1):
            if progress_callback:
                progress_callback(f"  Chunk {i}/{total_chunks} ({len(chunk):,} chars)...")

            formatted_chunk = self._format_paragraph_chunk(chunk, None)
            formatted_chunks.append(formatted_chunk)

        if progress_callback:
            progress_callback(f"✓ Formatted {total_chunks} chunks into paragraphs")

        # Join chunks with paragraph break
        return '\n\n'.join(formatted_chunks)

    def analyze_transcript(self, raw_transcript: str, filename: str = "", progress_callback=None) -> Dict:
        """
        Analyze raw transcript using OpenAI GPT-4o mini to extract metadata

        Args:
            raw_transcript: Raw transcript text from Whisper
            filename: Original filename for context
            progress_callback: Optional callback for progress updates

        Returns:
            Dict with transcript metadata:
            {
                "summary": str,
                "broad_keywords": list,
                "specific_keywords": list,
                "scripture_references": list,
                "context_notes": str,
                "speaker_name": str
            }

        Raises:
            RuntimeError: If analysis fails
        """
        if progress_callback:
            model_name = "GPT-5 nano" if "gpt-5-nano" in self.model else "GPT-4o mini"
            progress_callback(f"Analyzing transcript with {model_name}...")

        # Create prompt
        prompt = f"""{TRANSCRIPT_CLEANUP_INSTRUCTIONS}

---

TRANSCRIPT TO ANALYZE:

{raw_transcript}

---

Return ONLY the JSON metadata. No explanations or commentary."""

        try:
            if self.use_responses_api:
                if progress_callback:
                    progress_callback(f"OpenAI request via Responses API (model: {self.model})")
                system_text = (
                    "You are a precise transcript analyzer. You extract metadata from transcripts and return ONLY "
                    "valid JSON with no additional commentary."
                )
                word_count = self._count_words(raw_transcript)
                max_output = min(self.max_tokens, self._estimate_output_tokens(raw_transcript, multiplier=0.5, floor=4096))
                if progress_callback:
                    progress_callback(f"Metadata size: {word_count:,} words → max_output_tokens {max_output:,}")
                for attempt in range(3):
                    request_json = {
                        "model": self.model,
                        "input": self._build_responses_input(system_text, prompt),
                        "max_output_tokens": max_output
                    }

                    response = requests.post(
                        self.responses_url,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        },
                        json=request_json,
                        timeout=max(self.timeout, 180)
                    )
                    response.raise_for_status()
                    result = response.json()
                    self._maybe_dump_response(result, "metadata")
                    try:
                        content = self._extract_responses_text(result).strip()
                        break
                    except ValueError as e:
                        if self._is_max_output_incomplete(e) and max_output < self.max_tokens:
                            max_output = min(self.max_tokens, max_output * 2)
                            if progress_callback:
                                progress_callback(f"Retrying metadata with higher max_output_tokens: {max_output}")
                            continue
                        raise
            else:
                if progress_callback:
                    progress_callback(f"OpenAI request via Chat Completions (model: {self.model})")
                # Build request JSON
                request_json = {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a precise transcript analyzer. You extract metadata from transcripts and return ONLY valid JSON with no additional commentary."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.1
                }

                request_json["max_tokens"] = 4096  # Metadata is small

                response = requests.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json=request_json,
                    timeout=self.timeout
                )
                response.raise_for_status()
                result = response.json()
                # Extract content
                content = result['choices'][0]['message']['content'].strip()

            # Parse JSON (handle markdown code blocks if present)
            if content.startswith("```"):
                content = re.sub(r'^```(?:json)?\n', '', content)
                content = re.sub(r'\n```$', '', content)

            metadata = json.loads(content)

            # Validate required fields
            required_fields = ['summary', 'broad_keywords', 'specific_keywords',
                             'scripture_references', 'context_notes', 'speaker_name']
            for field in required_fields:
                if field not in metadata:
                    raise ValueError(f"Missing required field: {field}")

            if progress_callback:
                progress_callback(f"✓ Metadata extracted: {metadata['speaker_name']}")

            return metadata

        except requests.exceptions.RequestException as e:
            error_msg = f"OpenAI request failed: {self._format_http_error(e)}"
            if progress_callback:
                progress_callback(f"✗ {error_msg}")
            raise RuntimeError(error_msg)

        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse metadata JSON: {str(e)}"
            if progress_callback:
                progress_callback(f"✗ {error_msg}")
            raise RuntimeError(error_msg)

        except Exception as e:
            error_msg = f"Metadata analysis failed: {str(e)}"
            if progress_callback:
                progress_callback(f"✗ {error_msg}")
            raise RuntimeError(error_msg)

    def test_connection(self) -> bool:
        """
        Test if OpenAI API is accessible

        Returns:
            True if connection works, False otherwise
        """
        try:
            if self.use_responses_api:
                request_json = {
                    "model": self.model,
                    "input": self._build_responses_input("You are a helpful assistant.", "Hi"),
                    "max_output_tokens": 5
                }
                response = requests.post(
                    self.responses_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json=request_json,
                    timeout=5
                )
            else:
                response = requests.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": "Hi"}],
                        "max_tokens": 5
                    },
                    timeout=5
                )
            return response.status_code == 200
        except Exception:
            return False
