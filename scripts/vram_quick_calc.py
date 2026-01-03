#!/usr/bin/env python3
"""
Quick VRAM Calculator - Arbitrary Parameters

Usage: python vram_quick_calc.py --type image --width 1024 --height 1024 --steps 20
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mydiffuser.utils.vram_predictor import vram_predictor


def main():
    parser = argparse.ArgumentParser(description="Quick VRAM calculator")
    parser.add_argument(
        "--type",
        choices=["image", "video", "assistant"],
        required=True,
        help="Generation type",
    )
    parser.add_argument("--width", type=int, default=512, help="Image/video width")
    parser.add_argument("--height", type=int, default=512, help="Image/video height")
    parser.add_argument("--steps", type=int, default=20, help="Inference steps")
    parser.add_argument("--guidance", type=float, default=0.0, help="Guidance scale")
    parser.add_argument("--frames", type=int, default=16, help="Video frames")
    parser.add_argument(
        "--model", choices=["5B", "14B"], default="5B", help="Video model size"
    )
    parser.add_argument("--batch", type=int, default=1, help="Batch size")
    parser.add_argument(
        "--dtype", choices=["float16", "float32", "bfloat16"], default="float16"
    )

    args = parser.parse_args()

    if args.type == "image":
        estimate = vram_predictor.estimate_image_vram(
            width=args.width,
            height=args.height,
            num_inference_steps=args.steps,
            guidance_scale=args.guidance,
            dtype=args.dtype,
            batch_size=args.batch,
        )

    elif args.type == "video":
        estimate = vram_predictor.estimate_video_vram(
            model_name=f"wan-2.1-{args.model.lower()}",
            width=args.width,
            height=args.height,
            num_frames=args.frames,
            num_inference_steps=args.steps,
            guidance_scale=args.guidance,
            dtype=args.dtype,
            batch_size=args.batch,
        )

    elif args.type == "assistant":
        estimate = vram_predictor.estimate_assistant_vram(
            model_name="qwen2-vl-7b", max_sequence_length=args.steps
        )

    print(f"🎯 {args.type.upper()} Generation:")
    if args.type in ["image", "video"]:
        print(f"   Resolution: {args.width}x{args.height}")
    if args.type == "video":
        print(f"   Duration: {args.frames / 24:.1f}s ({args.frames} frames)")
        print(f"   Model: {args.model}")
    print(f"   Steps: {args.steps}, Guidance: {args.guidance}")
    print(f"   Batch: {args.batch}, Dtype: {args.dtype}")
    print(f"   📈 VRAM Required: {estimate.total_estimate_gb:.1f} GB")
    print(f"   ✅ Safe: {'Yes' if estimate.is_safe else 'No'}")
    print(f"   Available: {estimate.available_gb:.1f} GB")


if __name__ == "__main__":
    main()
