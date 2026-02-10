"""
Claude Haiku Transcript Formatter
"""

import json
import os
import re
import logging
from typing import Dict
from anthropic import Anthropic

# Set up logging
logging.basicConfig(
    filename=os.path.expanduser('~/Library/Logs/TranscriptProcessor-Dev.log'),
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
from config import (
    CLAUDE_MODEL_FORMATTING,
    CLAUDE_MODEL_METADATA,
    CLAUDE_MAX_TOKENS_FORMATTING,
    CLAUDE_MAX_TOKENS_METADATA,
    CLAUDE_CHUNK_THRESHOLD,
    CLAUDE_CHUNK_SIZE,
    TRANSCRIPT_CLEANUP_INSTRUCTIONS,
    PARAGRAPH_FORMATTING_INSTRUCTIONS
)


class ClaudeFormatter:
    """Formats transcripts using Claude Haiku API"""

    @staticmethod
    def _validate_and_fix_metadata(result: Dict) -> Dict:
        """
        Validate and fix common formatting issues in metadata

        Args:
            result: Parsed JSON result from Claude

        Returns:
            Corrected result dictionary
        """
        logger.debug("_validate_and_fix_metadata() called")

        # Fix summary: remove leading punctuation and whitespace
        if 'summary' in result and result['summary']:
            summary = result['summary']
            logger.debug(f"Original summary starts with: {repr(summary[:30])}")
            # Strip leading punctuation and whitespace
            summary = summary.lstrip('. \t\n')
            # Ensure it starts with capital letter
            if summary and summary[0].islower():
                summary = summary[0].upper() + summary[1:]
            logger.debug(f"Fixed summary starts with: {repr(summary[:30])}")
            result['summary'] = summary

        # Fix context_notes: ensure it starts with "This transcript" or "This recording"
        if 'context_notes' in result and result['context_notes']:
            context = result['context_notes']
            logger.debug(f"Original context_notes starts with: {repr(context[:50])}")
            # Strip leading whitespace
            context = context.lstrip(' \t\n')
            # If it doesn't start with "This", add it
            if not context.startswith('This'):
                # If it starts with lowercase like "is a broadcast", prepend "This transcript "
                if context and context[0].islower():
                    context = 'This transcript ' + context
                else:
                    context = 'This transcript is ' + context
            # Ensure first letter is capitalized
            if context and context[0].islower():
                context = context[0].upper() + context[1:]
            logger.debug(f"Fixed context_notes starts with: {repr(context[:50])}")
            result['context_notes'] = context

        # Clean up any Unicode issues in all text fields
        for field in ['summary', 'context_notes', 'speaker_name']:
            if field in result and isinstance(result[field], str):
                # Replace common Unicode issues with standard ASCII
                text = result[field]
                text = text.replace('â€"', '--')  # Em dash garbage
                text = text.replace('â€™', "'")   # Apostrophe garbage
                text = text.replace('â€œ', '"')   # Left quote garbage
                text = text.replace('â€', '"')    # Right quote garbage
                text = text.replace('\u2014', '--')  # Real em dash
                text = text.replace('\u2013', '-')   # En dash
                text = text.replace('\u2019', "'")   # Right single quote
                text = text.replace('\u201c', '"')   # Left double quote
                text = text.replace('\u201d', '"')   # Right double quote
                result[field] = text

        # Remove scripture references from keywords (they belong ONLY in scripture_references)
        import re
        scripture_pattern = re.compile(r'^(?:'
            r'(?:1|2|3|I|II|III)?\s*(?:Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth|'
            r'Samuel|Kings|Chronicles|Ezra|Nehemiah|Esther|Job|Psalm|Psalms|Proverbs|Ecclesiastes|'
            r'Song of Solomon|Isaiah|Jeremiah|Lamentations|Ezekiel|Daniel|Hosea|Joel|Amos|Obadiah|Jonah|'
            r'Micah|Nahum|Habakkuk|Zephaniah|Haggai|Zechariah|Malachi|Matthew|Mark|Luke|John|Acts|'
            r'Romans|Corinthians|Galatians|Ephesians|Philippians|Colossians|Thessalonians|Timothy|Titus|'
            r'Philemon|Hebrews|James|Peter|Jude|Revelation)'
            r'(?:\s+\d+)?(?::\d+)?(?:-\d+)?'  # Optional chapter:verse-verse
            r'|(?:Gen|Ex|Lev|Num|Deut|Josh|Judg|Ruth|Sam|Kgs|Chr|Neh|Esth|Ps|Prov|Eccl|Isa|Jer|Lam|Ezek|Dan|'
            r'Hos|Joel|Amos|Obad|Jon|Mic|Nah|Hab|Zeph|Hag|Zech|Mal|Matt|Mk|Lk|Jn|Rom|Cor|Gal|Eph|Phil|Col|'
            r'Thess|Tim|Tit|Phlm|Heb|Jas|Pet|Rev)\.?\s*\d+'  # Abbreviated forms
            r')$', re.IGNORECASE)

        for keyword_field in ['broad_keywords', 'specific_keywords']:
            if keyword_field in result and isinstance(result[keyword_field], list):
                original_count = len(result[keyword_field])
                # Filter out anything that looks like a scripture reference
                cleaned = [kw for kw in result[keyword_field] if not scripture_pattern.match(kw.strip())]
                if len(cleaned) < original_count:
                    logger.debug(f"Removed {original_count - len(cleaned)} scripture refs from {keyword_field}")
                result[keyword_field] = cleaned

        return result

    def __init__(self, api_key: str = None):
        """
        Initialize Claude API client

        Args:
            api_key: Anthropic API key (or uses ANTHROPIC_API_KEY env var)
        """
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("Anthropic API key required. Set ANTHROPIC_API_KEY or provide api_key parameter.")

        self.client = Anthropic(api_key=self.api_key)
        self.model_formatting = CLAUDE_MODEL_FORMATTING  # Haiku 3.5 for cheaper formatting
        self.model_metadata = CLAUDE_MODEL_METADATA  # Haiku 4.5 for better metadata analysis

    @staticmethod
    def _calculate_optimal_max_tokens(text: str, is_formatting: bool = True) -> int:
        """
        Calculate optimal max_tokens based on input text length

        Args:
            text: Input text to analyze
            is_formatting: True for paragraph formatting, False for metadata extraction

        Returns:
            Optimal max_tokens value
        """
        # Estimate tokens (rough: 1 token ≈ 0.75 words ≈ 4 characters)
        estimated_input_tokens = len(text) // 4

        if is_formatting:
            # Paragraph formatting with Haiku 3.5: output similar to input length, add 50% buffer
            # for punctuation and formatting variations
            optimal_tokens = int(estimated_input_tokens * 1.5)
            # Clamp between reasonable bounds (min 2K, max 8K for Haiku 3.5)
            return max(2048, min(optimal_tokens, CLAUDE_MAX_TOKENS_FORMATTING))
        else:
            # Metadata extraction: scales slightly with length but always small
            if len(text) < 5000:  # Short transcript (< 5K chars)
                return 2048
            elif len(text) < 15000:  # Medium transcript (5K-15K chars)
                return 3072
            else:  # Long transcript (15K+ chars)
                return CLAUDE_MAX_TOKENS_METADATA

    def analyze_transcript(self, raw_transcript: str, filename: str = "", progress_callback=None) -> Dict:
        """
        Analyze raw transcript using Claude Haiku to extract metadata

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
            progress_callback("Analyzing transcript with Claude Haiku...")

        # Create prompt
        prompt = f"""{TRANSCRIPT_CLEANUP_INSTRUCTIONS}

---

Original filename: {filename}

Raw transcript to analyze:

{raw_transcript}

---

Please analyze this transcript and return ONLY valid JSON with the metadata."""

        try:
            # Calculate optimal max_tokens based on input length
            optimal_max_tokens = self._calculate_optimal_max_tokens(raw_transcript, is_formatting=False)

            if progress_callback:
                progress_callback(f"Using {optimal_max_tokens:,} max_tokens for metadata extraction")

            # Use streaming to handle large outputs without timeout
            # Use Haiku 4.5 for better metadata analysis
            response_text = ""
            with self.client.messages.stream(
                model=self.model_metadata,
                max_tokens=optimal_max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            ) as stream:
                for text_chunk in stream.text_stream:
                    response_text += text_chunk

            # Parse JSON response
            # Try to find JSON in the response (in case Claude adds explanation)
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1

            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in Claude response")

            json_str = response_text[json_start:json_end]
            result = json.loads(json_str)

            # Validate required fields
            required_fields = ['summary', 'broad_keywords', 'specific_keywords',
                               'scripture_references', 'context_notes', 'speaker_name']

            for field in required_fields:
                if field not in result:
                    raise ValueError(f"Missing required field: {field}")

            # Validate and fix formatting issues
            result = self._validate_and_fix_metadata(result)

            if progress_callback:
                progress_callback(f"✓ Analyzed by Claude (Speaker: {result['speaker_name']})")

            return result

        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse Claude response as JSON: {str(e)}"
            if progress_callback:
                progress_callback(f"✗ {error_msg}")
            raise RuntimeError(error_msg)

        except Exception as e:
            error_msg = f"Claude analysis failed: {str(e)}"
            if progress_callback:
                progress_callback(f"✗ {error_msg}")
            raise RuntimeError(error_msg)

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

        # With Haiku 3.5's 8K output limit, we need to chunk transcripts > ~18K chars
        # (~4500 words = ~30 minutes of speech)
        if transcript_length <= CLAUDE_CHUNK_THRESHOLD:
            if progress_callback:
                progress_callback(f"→ Using single-pass formatting (streaming)")
            return self._format_paragraph_chunk(raw_transcript, progress_callback)
        else:
            # Long transcript, chunk it for Haiku 3.5's 8K token output limit
            if progress_callback:
                progress_callback(f"→ Long transcript ({transcript_length:,} chars), using chunks")
            return self._format_long_transcript(raw_transcript, progress_callback)

    def _format_paragraph_chunk(self, text: str, progress_callback=None) -> str:
        """
        Format a single chunk of text into paragraphs using streaming

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
            # Calculate optimal max_tokens based on input length
            optimal_max_tokens = self._calculate_optimal_max_tokens(text, is_formatting=True)

            if progress_callback:
                progress_callback(f"Using {optimal_max_tokens:,} max_tokens for {len(text):,} character transcript")

            # Use streaming to handle large outputs without timeout
            # Use Haiku 3.5 for cheaper paragraph formatting
            formatted_text = ""
            with self.client.messages.stream(
                model=self.model_formatting,
                max_tokens=optimal_max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            ) as stream:
                for text_chunk in stream.text_stream:
                    formatted_text += text_chunk

            formatted_text = formatted_text.strip()

            if not formatted_text:
                raise ValueError("Claude returned empty response")

            # Detect if Claude used placeholders instead of actual content
            placeholder_patterns = [
                "[The formatting continues",
                "[The transcript continues",
                "[Text continues",
                "continues in this manner",
                "continues with this pattern"
            ]

            for pattern in placeholder_patterns:
                if pattern in formatted_text:
                    raise ValueError(f"Claude used placeholder text ('{pattern}') instead of formatting complete transcript. Input may be too long.")

            # Verify output length is reasonable (should be similar to input)
            input_length = len(text)
            output_length = len(formatted_text)
            ratio = output_length / input_length if input_length > 0 else 0

            # Output should be 70%-150% of input (accounting for added punctuation)
            if ratio < 0.7 or ratio > 1.5:
                if progress_callback:
                    progress_callback(f"⚠️  Warning: Output length unusual (input: {input_length:,}, output: {output_length:,}, ratio: {ratio:.2f})")

            return formatted_text

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

        # Group sentences into chunks (for Haiku 3.5's 8K token output limit)
        # Target: 3500 chars (~2600 tokens), Max: 4000 chars (~3000 tokens)
        # This ensures output stays well under 8K token limit with buffer for formatting
        target_chunk_size = 3500
        max_chunk_size = CLAUDE_CHUNK_SIZE  # 4000 - absolute maximum

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
            progress_callback(f"Processing {total_chunks} chunks...")

        for i, chunk in enumerate(chunks, 1):
            if progress_callback:
                progress_callback(f"  Chunk {i}/{total_chunks} ({len(chunk):,} chars)...")

            formatted_chunk = self._format_paragraph_chunk(chunk, None)
            formatted_chunks.append(formatted_chunk)

        if progress_callback:
            progress_callback(f"✓ Formatted {total_chunks} chunks into paragraphs")

        # Join chunks with paragraph break
        return '\n\n'.join(formatted_chunks)

    def test_api_key(self) -> bool:
        """
        Test if API key is valid

        Returns:
            True if API key works, False otherwise
        """
        try:
            # Try a minimal API call with the formatting model
            response = self.client.messages.create(
                model=self.model_formatting,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            return True
        except Exception:
            return False
