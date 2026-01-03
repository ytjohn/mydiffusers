#!/usr/bin/env python3
"""
VRAM Calculator - Test arbitrary parameters

This script demonstrates how the enhanced VRAM predictor
calculates memory usage for any combination of parameters.
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mydiffuser.utils.vram_predictor import vram_predictor


def test_arbitrary_parameters():
    """Test VRAM predictions for various parameter combinations"""

    print("🧮 VRAM Calculator - Arbitrary Parameter Testing")
    print("=" * 50)

    # Test cases based on your baseline
    test_cases = [
        # Image generation variations
        {
            "type": "image",
            "name": "High-res portrait",
            "width": 1024,
            "height": 1536,
            "steps": 20,
            "guidance": 7.5,
        },
        {
            "type": "image",
            "name": "Quick draft",
            "width": 512,
            "height": 512,
            "steps": 4,
            "guidance": 0.0,
        },
        # Video generation variations
        {
            "type": "video",
            "name": "Short 720p video",
            "model": "5B",
            "width": 1280,
            "height": 704,
            "frames": 16,
            "steps": 15,
            "guidance": 3.0,
        },
        {
            "type": "video",
            "name": "Long 720p video",
            "model": "5B",
            "width": 1280,
            "height": 704,
            "frames": 240,  # 10s @ 24fps
            "steps": 30,
            "guidance": 5.0,
        },
        {
            "type": "video",
            "name": "Ultra-long 1080p",
            "model": "5B",
            "width": 1920,
            "height": 1080,
            "frames": 300,  # 10s @ 30fps
            "steps": 50,
            "guidance": 7.0,
        },
        # Assistant variations
        {
            "type": "assistant",
            "name": "Quick prompt",
            "model": "qwen2-vl-7b",
            "max_length": 512,
        },
        {
            "type": "assistant",
            "name": "Detailed analysis",
            "model": "qwen2-vl-7b",
            "max_length": 2048,
        },
    ]

    for case in test_cases:
        print(f"\n📊 {case['name']}:")

        if case["type"] == "image":
            estimate = vram_predictor.estimate_image_vram(
                width=case["width"],
                height=case["height"],
                num_inference_steps=case["steps"],
                guidance_scale=case["guidance"],
            )

            print(f"   Resolution: {case['width']}x{case['height']}")
            print(f"   Steps: {case['steps']}, Guidance: {case['guidance']}")

        elif case["type"] == "video":
            estimate = vram_predictor.estimate_video_vram(
                model_name=f"wan-2.1-{case['model'].lower()}",
                width=case["width"],
                height=case["height"],
                num_frames=case["frames"],
                num_inference_steps=case["steps"],
                guidance_scale=case["guidance"],
            )

            duration = case["frames"] / 24  # Assume 24fps
            print(f"   Resolution: {case['width']}x{case['height']}")
            print(f"   Duration: {duration:.1f}s ({case['frames']} frames)")
            print(f"   Steps: {case['steps']}, Guidance: {case['guidance']}")

        elif case["type"] == "assistant":
            estimate = vram_predictor.estimate_assistant_vram(
                model_name=case["model"], max_sequence_length=case["max_length"]
            )

            print(f"   Model: {case['model']}")
            print(f"   Max sequence: {case['max_length']}")

        print(f"   📈 Estimated VRAM: {estimate.total_estimate_gb:.1f} GB")
        print(f"   ✅ Safe: {'Yes' if estimate.is_safe else 'No'}")
        if not estimate.is_safe:
            print(f"   ⚠️  Available: {estimate.available_gb:.1f} GB")


def interactive_calculator():
    """Interactive VRAM calculator"""
    print("\n🔧 Interactive VRAM Calculator")
    print("Enter parameters to calculate VRAM usage")

    while True:
        print("\nChoose type:")
        print("1. Image generation")
        print("2. Video generation")
        print("3. Assistant query")
        print("4. Exit")

        choice = input("Selection (1-4): ").strip()

        if choice == "4":
            break
        elif choice == "1":
            width = int(input("Width (pixels): "))
            height = int(input("Height (pixels): "))
            steps = int(input("Inference steps: "))
            guidance = float(input("Guidance scale (0.0-7.5): "))

            estimate = vram_predictor.estimate_image_vram(
                width=width,
                height=height,
                num_inference_steps=steps,
                guidance_scale=guidance,
            )

        elif choice == "2":
            model = input("Model (5B/14B): ").strip()
            width = int(input("Width (pixels): "))
            height = int(input("Height (pixels): "))
            fps = int(input("FPS: "))
            duration = float(input("Duration (seconds): "))
            steps = int(input("Inference steps: "))
            guidance = float(input("Guidance scale (0.0-7.5): "))

            frames = fps * duration
            estimate = vram_predictor.estimate_video_vram(
                model_name=f"wan-2.1-{model.lower()}",
                width=width,
                height=height,
                num_frames=frames,
                num_inference_steps=steps,
                guidance_scale=guidance,
            )

        elif choice == "3":
            model = input("Model (7B/2B): ").strip()
            max_len = int(input("Max sequence length: "))

            estimate = vram_predictor.estimate_assistant_vram(
                model_name=f"qwen2-vl-{model.lower()}", max_sequence_length=max_len
            )
        else:
            continue

        print(f"\n🎯 Result: {estimate.total_estimate_gb:.1f} GB VRAM required")
        print(f"Available: {estimate.available_gb:.1f} GB")
        print(f"Status: {'✅ Safe' if estimate.is_safe else '⚠️  Insufficient VRAM'}")


if __name__ == "__main__":
    # Run preset tests
    test_arbitrary_parameters()

    # Offer interactive mode
    if input("\nRun interactive calculator? (y/n): ").lower().startswith("y"):
        interactive_calculator()
