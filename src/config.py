"""
Configuration for Transcript Processor
"""

import os
import json
from pathlib import Path

# Config file location
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_CONFIG_FILE = PROJECT_ROOT / "config" / "credentials.json"
HOME_CONFIG_FILE = Path.home() / "TranscriptProcessor" / "config" / "credentials.json"

def load_api_key():
    """Load Anthropic API key from config file or environment"""
    # First try config file
    if PROJECT_CONFIG_FILE.exists():
        try:
            with open(PROJECT_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get('anthropic_api_key')
        except Exception:
            pass
    if HOME_CONFIG_FILE.exists():
        try:
            with open(HOME_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get('anthropic_api_key')
        except Exception:
            pass

    # Fall back to environment variable
    return os.getenv('ANTHROPIC_API_KEY')

def load_openai_api_key():
    """Load OpenAI API key from config file or environment"""
    # First try config file
    if PROJECT_CONFIG_FILE.exists():
        try:
            with open(PROJECT_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                key = config.get('openai_api_key')
                if key:
                    return key
        except Exception:
            pass
    if HOME_CONFIG_FILE.exists():
        try:
            with open(HOME_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                key = config.get('openai_api_key')
                if key:
                    return key
        except Exception:
            pass

    # Fall back to environment variable
    return os.getenv('OPENAI_API_KEY')

# Transcription Engine Options
TRANSCRIPTION_ENGINE_PARAKEET = "parakeet"  # Local Apple Silicon (fast, free)
TRANSCRIPTION_ENGINE_WHISPER = "whisper"    # Remote Whisper.cpp (reliable)

# Whisper.cpp Service Configuration
WHISPER_HOST = "10.0.85.100"
WHISPER_PORT = 5687
WHISPER_URL = f"http://{WHISPER_HOST}:{WHISPER_PORT}/inference"

# Parakeet-MLX Configuration (local)
PARAKEET_MODEL = "mlx-community/parakeet-tdt-0.6b-v3"
PARAKEET_CHUNK_DURATION = 120.0  # 2-minute chunks (optimal for speed)
PARAKEET_OVERLAP_DURATION = 15.0  # 15-second overlap for accuracy

# OpenAI API Configuration
# NOTE: Prefer OPENAI_API_KEY env var. Optional config key: "openai_api_key" in credentials.json
OPENAI_API_KEY = load_openai_api_key()
OPENAI_MODEL_4O_MINI = "gpt-4o-mini"  # GPT-4o mini - Fast and affordable (16K output, 128K context)
OPENAI_MODEL_5_NANO = "gpt-5-nano"  # GPT-5 nano - Faster and cheaper (128K output, 400K context)
OPENAI_MODEL = OPENAI_MODEL_5_NANO  # Default to GPT-5 nano
OPENAI_TIMEOUT = 120  # 2 minutes timeout for API calls

# PDF Branding (WeasyPrint)
# Provide either a local file path or an HTTPS URL. Leave empty to disable logo.
ARCHIVES_LOGO_PATH_OR_URL = str(PROJECT_ROOT / "assets" / "wesleyan-archives-logo.svg")
ARCHIVES_FOOTER_TEXT = "Wesleyan Archives and Historical Library"

# GPT-4o mini limits (16K output, 128K context)
OPENAI_4O_MINI_CHUNK_THRESHOLD = 15000  # Process single-pass up to 15K chars (~10 min speech, leverages 16K output)
OPENAI_4O_MINI_CHUNK_SIZE = 12000  # Large chunks: 12K chars (~3K words, ~9K tokens, well under 16K output limit)

# GPT-5 nano limits (128K output, 400K context)
# Use smaller chunks to avoid long single-pass responses and improve paragraphing consistency.
OPENAI_5_NANO_CHUNK_THRESHOLD = 15000  # Process single-pass up to 15K chars
OPENAI_5_NANO_CHUNK_SIZE = 12000  # Chunk size: 12K chars

# Default (use GPT-5 nano settings)
OPENAI_CHUNK_THRESHOLD = OPENAI_5_NANO_CHUNK_THRESHOLD
OPENAI_CHUNK_SIZE = OPENAI_5_NANO_CHUNK_SIZE

# FFmpeg Audio Settings
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_FORMAT = "pcm_s16le"

# Claude API Configuration
# Testing smaller chunks with Haiku 3.5 to avoid truncation/placeholders
CLAUDE_MODEL_FORMATTING = "claude-3-5-haiku-20241022"  # Haiku 3.5 - Testing with small chunks
CLAUDE_MODEL_METADATA = "claude-haiku-4-5-20251001"  # Haiku 4.5 - Default metadata model
CLAUDE_MAX_TOKENS_FORMATTING = 8192  # Haiku 3.5's maximum output tokens
CLAUDE_MAX_TOKENS_METADATA = 4096  # For metadata extraction (only need small JSON response)
CLAUDE_CHUNK_THRESHOLD = 5000  # Very conservative - chunk anything over 5K chars (~5 minutes of speech)
CLAUDE_CHUNK_SIZE = 4000  # Small chunks: 4K chars (~1000 words, ~1300 tokens, well under 8K output)

# File Paths
TEMP_DIR = Path.home() / "TranscriptProcessor" / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Supported Media Extensions
SUPPORTED_EXTENSIONS = {
    # Audio
    '.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.wma',
    # Video (will extract audio)
    '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm'
}

# Transcript Cleanup Instructions
TRANSCRIPT_CLEANUP_INSTRUCTIONS = """# Whisper AI Transcript Analysis Instructions

⚠️ CRITICAL FORMATTING REQUIREMENTS - READ FIRST ⚠️

MANDATORY RULES YOU MUST FOLLOW:
✓ "summary" MUST start with a capital letter and complete word (e.g., "Norman Wilson delivers...")
✗ FORBIDDEN: Starting summary with periods, spaces, or punctuation (". Norman" or " Norman")

✓ "context_notes" MUST begin with "This transcript" or "This recording"
✗ FORBIDDEN: Starting with lowercase or incomplete sentences ("is a broadcast..." or "recording from...")

✓ Use ONLY standard punctuation: hyphens (-), regular dashes (--), or write out words
✗ FORBIDDEN: Unicode em dashes or special characters that may render as garbage (â€", â€™, etc.)

✓ Keep scripture references ONLY in "scripture_references" field
✗ FORBIDDEN: Putting Bible verses in keywords arrays

---

You are analyzing a transcript from Whisper AI to extract metadata and context. You will NOT be returning the full transcript in your response - only the analysis.

## Your Task

Analyze the provided transcript and extract:

1. **Summary** (150-250 words)
   MUST start with complete sentence beginning with capital letter
   Example: "Norman Wilson delivers a message..."
   NOT: ". Norman Wilson delivers..." or " Norman Wilson..."
   Use regular hyphens or write out "to" instead of em dashes

2. **Broad Keywords** (5-7 items)
   High-level concepts and themes ONLY
   ⚠️ CRITICAL: NO scripture references - NOT EVEN BOOK NAMES (Colossians, Romans, etc.)
   ⚠️ If it's a Bible book or reference, it goes ONLY in scripture_references field

3. **Specific Keywords** (7-10 items)
   Proper names, theological terms, key concepts
   ⚠️ CRITICAL: NO scripture references - NOT EVEN BOOK NAMES (Colossians 3, Galatians 2:20, etc.)
   ⚠️ If it mentions a Bible book or chapter/verse, it belongs ONLY in scripture_references field

4. **Scripture References**
   Format: "Book Chapter:Verse" (e.g., "John 3:16", "Romans 8:28-30")
   Reference ONLY, no context or explanations in parentheses
   Empty list if none mentioned

5. **Context Notes**
   MUST begin: "This transcript is..." or "This recording is..."
   NOT: "is a broadcast..." or "recording from..."
   Include: broadcast name, date, speaker, audience, historical context

6. **Speaker Name**
   Primary speaker's name or "Unknown Speaker"

## EXACT Output Format

Return ONLY valid JSON:
{
  "summary": "Norman Wilson delivers a message titled The Violent Solution from The Wesleyan Hour radio ministry, addressing...",
  "broad_keywords": ["Spiritual warfare", "Sin and redemption", "Self-denial"],
  "specific_keywords": ["Crucifying self", "Dying to sin", "Sensual appetites", "Norman Wilson"],
  "scripture_references": ["Colossians 3:3", "Colossians 3:5", "Galatians 2:20"],
  "context_notes": "This transcript is a broadcast from The Wesleyan Hour, a worldwide radio ministry celebrating its 30th anniversary...",
  "speaker_name": "Norman Wilson"
}

VALIDATION CHECKLIST BEFORE SUBMITTING:
- [ ] Summary starts with capital letter, no leading punctuation
- [ ] Context_notes starts with "This transcript" or "This recording"
- [ ] No special Unicode characters (â€", â€™, etc.)
- [ ] Scripture references ONLY in scripture_references field
- [ ] All fields present and properly formatted

IMPORTANT: Do NOT include the transcript text in your response. Only return the metadata analysis above."""

# Paragraph Formatting Instructions for Claude
PARAGRAPH_FORMATTING_INSTRUCTIONS = """⚠️ CRITICAL: DO NOT OUTPUT YOUR THINKING PROCESS OR REASONING. ONLY OUTPUT THE FORMATTED TRANSCRIPT.

You are formatting a raw transcript into readable paragraphs.

CRITICAL RULES:
1. DO NOT change, add, remove, or paraphrase ANY WORDS from the original transcript
2. DO NOT alter the meaning or thought expressed in the transcript
3. PRESERVE all spoken errors, stutters, and verbal patterns exactly as they appear
4. You MAY add punctuation (commas, periods, semicolons, etc.) where contextually appropriate to improve readability
5. Add paragraph breaks at natural speech boundaries (topic changes, pauses, transitions)

WHERE TO ADD PARAGRAPH BREAKS:
- Topic changes or shifts in subject matter
- Natural pauses or transitions in the speech
- After complete thoughts or ideas are expressed
- Between different sections of the talk
- When the speaker moves from one example/story to another

PARAGRAPH LENGTH:
- Prefer 3-6 sentences per paragraph, but allow longer paragraphs when a single thought continues
- Do NOT split mid-thought just to keep paragraphs short
- Prioritize meaning and topic shifts over paragraph length
- Consider natural flow and rhythm of speech

OUTPUT FORMAT:
⚠️ DO NOT INCLUDE ANY THINKING, ANALYSIS, OR EXPLANATIONS IN YOUR OUTPUT
⚠️ SKIP ALL REASONING AND GO DIRECTLY TO THE FORMATTED TRANSCRIPT
⚠️ YOUR FIRST WORD SHOULD BE FROM THE TRANSCRIPT ITSELF, NOT YOUR THOUGHTS
⚠️ You MUST insert paragraph breaks (double newlines). A single unbroken block of text is INVALID.

Return ONLY the formatted transcript text with paragraph breaks (as double newlines between paragraphs).
Do not include any explanations, comments, or metadata.
Just the text with appropriate paragraph breaks and improved punctuation.

ABSOLUTELY CRITICAL - NO PLACEHOLDERS OR SUMMARIES:
⚠️ MANDATORY: You MUST return EVERY SINGLE WORD from the input transcript.
⚠️ FORBIDDEN: DO NOT use placeholders like "[The transcript continues...]", "[Text continues...]", "[And so on...]", or "[etc.]"
⚠️ FORBIDDEN: DO NOT summarize, skip, or abbreviate ANY portion of the transcript.
⚠️ FORBIDDEN: DO NOT stop early or indicate that the transcript continues elsewhere.
⚠️ FORBIDDEN: DO NOT include phrases like "Okay, let me process this..." or "First, I need to..." - START WITH THE TRANSCRIPT IMMEDIATELY

If you reach your output limit before finishing, STOP MID-SENTENCE rather than using a placeholder.
This will signal that chunking is needed. NEVER use placeholders under any circumstances.

This is an archival transcript. The exact WORDS and MEANING must be preserved. Punctuation improvements and paragraph breaks enhance readability without changing what was said.

BEGIN YOUR RESPONSE WITH THE TRANSCRIPT TEXT IMMEDIATELY. NO PREAMBLE."""
