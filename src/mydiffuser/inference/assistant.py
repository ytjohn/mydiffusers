"""Prompt assistant using Qwen2-VL for image analysis and prompt suggestions.

This module provides AI-powered prompt improvement suggestions by analyzing
generated images and identifying issues with composition, character interactions,
anatomy, and style.
"""

import logging
from typing import Any

import torch
from PIL import Image
from qwen_vl_utils import process_vision_info
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

logger = logging.getLogger(__name__)

# Model configuration
MODEL_ID = "Qwen/Qwen2-VL-2B-Instruct"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# System prompt for the assistant
SYSTEM_PROMPT = """You are an expert at analyzing AI-generated images and improving prompts for Stable Diffusion models.

Your task: Analyze the provided image and its generation prompt, then suggest 2-3 improved prompts.

**Analysis approach:**
1. Identify what worked (composition, style, lighting, anatomy)
2. Identify issues (floating limbs, disconnected characters, anatomy errors, lighting problems)
3. Suggest specific keyword additions/changes to fix issues

**For character interactions:**
- Suggest shared objects or activities ("both holding rope", "dancing together")
- Add spatial anchors ("B directly behind A", "faces 6 inches apart")
- Specify limb placement ("A's arms around B's waist", "hands clasped at hip level")

**For anatomy issues:**
- Add constraints ("5 fingers each", "anatomically correct hands")
- Suggest hiding problem areas ("hands behind back", "hands in pockets")

**For composition/lighting:**
- Camera/framing terms ("85mm portrait", "shallow DOF", "rule of thirds")
- Lighting direction ("soft backlighting", "rim light separating figures")

**Response format:**
1. Brief analysis (2-3 sentences)
2. 2-3 specific prompt suggestions with rationales
3. General tips for this type of generation

Always explain WHY each change might help."""


class PromptAssistant:
    """Vision-language model for analyzing images and suggesting prompt improvements."""

    def __init__(self):
        self.model: Qwen2VLForConditionalGeneration | None = None
        self.processor: Any | None = None
        self.device = DEVICE

    def load(self) -> None:
        """Load the Qwen2-VL model and processor."""
        if self.model is not None:
            logger.info("Prompt assistant already loaded")
            return

        logger.info(f"Loading Qwen2-VL model ({MODEL_ID}) on {self.device}...")

        # Load processor
        self.processor = AutoProcessor.from_pretrained(MODEL_ID)

        # Load model
        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.bfloat16 if self.device == "cuda" else torch.float32,
            device_map="auto" if self.device == "cuda" else None,
        )

        if self.device == "cpu":
            self.model = self.model.to("cpu")

        logger.info(f"Qwen2-VL loaded successfully on {self.device}")

        # Log memory usage if on GPU
        if self.device == "cuda" and torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated() / (1024**3)
            reserved = torch.cuda.memory_reserved() / (1024**3)
            logger.info(f"GPU memory: {allocated:.2f} GiB allocated, {reserved:.2f} GiB reserved")

    def unload(self) -> None:
        """Unload the model and free memory."""
        if self.model is None:
            return

        logger.info("Unloading prompt assistant...")

        # Move to CPU and delete
        if self.device == "cuda":
            self.model = self.model.to("cpu")

        del self.model
        del self.processor
        self.model = None
        self.processor = None

        # Clear GPU cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

        logger.info("Prompt assistant unloaded")

    def analyze_image(
        self,
        image: Image.Image,
        current_prompt: str,
        issue: str | None = None,
        max_new_tokens: int = 512,
    ) -> dict[str, Any]:
        """Analyze an image and provide prompt improvement suggestions.

        Args:
            image: PIL Image to analyze
            current_prompt: The prompt that generated this image
            issue: Optional user-described issue (e.g., "arms are floating")
            max_new_tokens: Maximum tokens to generate

        Returns:
            Dict with keys:
                - analysis: str - Analysis of what worked and what didn't
                - suggestions: list[dict] - List of prompt suggestions with rationales
                - tips: list[str] - General tips
                - raw_response: str - Full model response
        """
        if self.model is None or self.processor is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Build user message
        user_message = f"Analyze this AI-generated image.\n\nOriginal prompt: {current_prompt}"
        if issue:
            user_message += f"\n\nReported issue: {issue}"
        user_message += "\n\nProvide analysis and 2-3 improved prompt suggestions."

        # Prepare messages for Qwen2-VL format
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": user_message},
                ],
            }
        ]

        # Apply chat template
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        # Process vision info
        image_inputs, video_inputs = process_vision_info(messages)

        # Prepare inputs
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )

        # Move to device
        inputs = inputs.to(self.device)

        # Generate response
        logger.info("Generating prompt suggestions...")
        with torch.no_grad():
            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,  # Deterministic for consistency
            )

        # Trim input tokens and decode
        generated_ids_trimmed = [
            out_ids[len(in_ids):]
            for in_ids, out_ids in zip(inputs.input_ids, generated_ids, strict=False)
        ]
        response_text = self.processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False
        )[0]

        logger.info(f"Generated response ({len(response_text)} chars)")

        # Parse response (simple parsing - could be improved with structured output)
        parsed = self._parse_response(response_text)
        parsed['raw_response'] = response_text

        return parsed

    def _parse_response(self, response: str) -> dict[str, Any]:
        """Parse the model's response into structured format.

        This is a simple parser. For production, consider using structured
        output formats or more robust parsing.
        """
        # For now, return a simple structure
        # In a full implementation, you'd parse out:
        # - Analysis section
        # - Individual suggestions with rationales
        # - Tips section

        response.strip().split('\n')

        return {
            'analysis': response[:200] + "..." if len(response) > 200 else response,
            'suggestions': [
                {
                    'prompt': "Enhanced version of original prompt",
                    'rationale': "See full response for details"
                }
            ],
            'tips': ["See raw response for full suggestions"],
        }


# Global singleton instance
_assistant: PromptAssistant | None = None


def get_assistant() -> PromptAssistant:
    """Get the global prompt assistant instance."""
    global _assistant
    if _assistant is None:
        _assistant = PromptAssistant()
    return _assistant


def ensure_assistant_loaded() -> PromptAssistant:
    """Ensure the assistant is loaded and return it."""
    assistant = get_assistant()
    if assistant.model is None:
        assistant.load()
    return assistant
