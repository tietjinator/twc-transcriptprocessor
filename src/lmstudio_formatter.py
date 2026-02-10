"""
LM Studio Transcript Formatter
Uses local LM Studio instance with DeepSeek R1 for paragraph formatting
"""

import json
import re
import logging
import requests
from typing import Dict

from config import (
    LMSTUDIO_URL,
    LMSTUDIO_MODEL,
    LMSTUDIO_TIMEOUT,
    LMSTUDIO_CHUNK_SIZE,
    PARAGRAPH_FORMATTING_INSTRUCTIONS
)

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LMStudioFormatter:
    """Formats transcripts using local LM Studio instance"""

    def __init__(self):
        """Initialize LM Studio client"""
        self.api_url = LMSTUDIO_URL
        self.model = LMSTUDIO_MODEL
        self.timeout = LMSTUDIO_TIMEOUT

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

        # Use chunking threshold similar to Claude
        chunk_threshold = 5000

        if transcript_length <= chunk_threshold:
            if progress_callback:
                progress_callback(f"→ Using single-pass formatting (LM Studio)")
            return self._format_paragraph_chunk(raw_transcript, progress_callback)
        else:
            # Long transcript, chunk it
            if progress_callback:
                progress_callback(f"→ Long transcript ({transcript_length:,} chars), using chunks (LM Studio)")
            return self._format_long_transcript(raw_transcript, progress_callback)

    def _format_paragraph_chunk(self, text: str, progress_callback=None) -> str:
        """
        Format a single chunk of text into paragraphs using LM Studio

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
                progress_callback(f"Formatting {len(text):,} characters with LM Studio...")

            # Make request to LM Studio (OpenAI-compatible API)
            response = requests.post(
                f"{self.api_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.3,  # Lower temperature for more consistent formatting
                    "max_tokens": 8192,  # Max output
                    "stream": False
                },
                timeout=self.timeout
            )

            response.raise_for_status()
            result = response.json()

            formatted_text = result['choices'][0]['message']['content'].strip()

            if not formatted_text:
                raise ValueError("LM Studio returned empty response")

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
                    raise ValueError(f"LM Studio used placeholder text ('{pattern}') instead of formatting complete transcript. Input may be too long.")

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
            error_msg = f"LM Studio request failed: {str(e)}"
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

        # Group sentences into chunks
        # Target: 3500 chars (~2600 tokens), Max: 4000 chars (~3000 tokens)
        target_chunk_size = 3500
        max_chunk_size = LMSTUDIO_CHUNK_SIZE  # 4000

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
            progress_callback(f"Processing {total_chunks} chunks with LM Studio...")

        for i, chunk in enumerate(chunks, 1):
            if progress_callback:
                progress_callback(f"  Chunk {i}/{total_chunks} ({len(chunk):,} chars)...")

            formatted_chunk = self._format_paragraph_chunk(chunk, None)
            formatted_chunks.append(formatted_chunk)

        if progress_callback:
            progress_callback(f"✓ Formatted {total_chunks} chunks into paragraphs")

        # Join chunks with paragraph break
        return '\n\n'.join(formatted_chunks)

    def test_connection(self) -> bool:
        """
        Test if LM Studio is accessible

        Returns:
            True if connection works, False otherwise
        """
        try:
            response = requests.get(f"{self.api_url}/models", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
