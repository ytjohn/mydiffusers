#!/usr/bin/env python3
"""
VRAM Baseline Measurement Script

This script measures actual VRAM usage for different generation scenarios
and compares them against our predictions. Run this to calibrate the
VRAM predictor with your specific hardware and model configurations.
"""

import os
import time
import json
import torch
import gc
import argparse
from typing import Dict, Any, List
from pathlib import Path
import logging

# Add project root to path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from mydiffuser.utils.vram_predictor import vram_predictor
from mydiffuser.config import configure_torch_backends
from mydiffuser.inference.state import (
    ensure_image_generator,
    ensure_video_generator,
    unload_model,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VRAMBenchmark:
    """Measures actual VRAM usage vs predicted usage"""

    def __init__(self, test_14b: bool = False):
        self.results = []
        self.predictor = vram_predictor
        self.test_14b = test_14b
        configure_torch_backends()

        if self.test_14b:
            logger.warning("⚠️  14B testing enabled - requires 32GB+ VRAM!")
        else:
            logger.info("14B testing disabled - set --test-14b or TEST_14B=1 to enable")

    def _get_memory_info(self) -> Dict[str, float]:
        """Get current GPU memory info"""
        if not torch.cuda.is_available():
            return {
                "error": 0.0,
                "allocated_gb": 0.0,
                "reserved_gb": 0.0,
                "free_gb": 0.0,
                "total_gb": 0.0,
                "used_gb": 0.0,
            }

        allocated = torch.cuda.memory_allocated() / (1024**3)
        reserved = torch.cuda.memory_reserved() / (1024**3)
        free, total = torch.cuda.mem_get_info()

        return {
            "allocated_gb": allocated,
            "reserved_gb": reserved,
            "free_gb": free / (1024**3),
            "total_gb": total / (1024**3),
            "used_gb": (total - free) / (1024**3),
        }

    def _measure_memory_delta(self, operation_func, description: str) -> Dict[str, Any]:
        """Measure memory delta for a specific operation"""
        logger.info(f"Measuring: {description}")

        # Force cleanup
        torch.cuda.empty_cache()
        gc.collect()

        # Baseline memory
        baseline = self._get_memory_info()

        # Run operation
        start_time = time.time()
        operation_func()
        torch.cuda.synchronize()
        end_time = time.time()

        # Post-operation memory
        post = self._get_memory_info()

        delta = {
            "description": description,
            "duration_sec": end_time - start_time,
            "baseline_gb": baseline.get("used_gb", 0),
            "post_gb": post.get("used_gb", 0),
            "delta_gb": post.get("used_gb", 0) - baseline.get("used_gb", 0),
            "baseline_memory": baseline,
            "post_memory": post,
        }

        return delta

    def benchmark_image_models(self) -> List[Dict[str, Any]]:
        """Benchmark image generation VRAM usage"""
        results = []

        # Test parameters
        test_cases = [
            {"width": 512, "height": 512, "steps": 4},
            {"width": 832, "height": 480, "steps": 4},  # draft preset
            {"width": 1280, "height": 704, "steps": 8},  # final preset
            {"width": 1024, "height": 1024, "steps": 20},
        ]

        for params in test_cases:
            # Unload any existing models
            unload_model("image")

            # Predict usage
            predicted = self.predictor.estimate_image_vram(
                width=params["width"],
                height=params["height"],
                num_inference_steps=params["steps"],
            )

            # Measure actual usage
            def load_and_run():
                gen = ensure_image_generator()
                # Just load, don't actually generate
                return gen

            measurement = self._measure_memory_delta(
                load_and_run,
                f"Image model load: {params['width']}x{params['height']}@{params['steps']}steps",
            )

            result = {
                **params,
                "type": "image_model_load",
                "predicted_gb": predicted.total_estimate_gb,
                "measured_gb": measurement["delta_gb"],
                "accuracy": abs(predicted.total_estimate_gb - measurement["delta_gb"]),
                "details": measurement,
            }

            results.append(result)
            logger.info(
                f"Image: {predicted.total_estimate_gb:.1f}GB predicted, {measurement['delta_gb']:.1f}GB measured"
            )

        return results

    def benchmark_video_models(self) -> List[Dict[str, Any]]:
        """Benchmark video generation VRAM usage"""
        results = []

        # Test parameters
        test_cases = [
            {"model": "5B", "width": 832, "height": 480, "frames": 16, "steps": 15},
            {
                "model": "5B",
                "width": 832,
                "height": 480,
                "frames": 36,
                "steps": 15,
            },  # 3s @ 12fps
        ]

        # Add 14B tests only if explicitly enabled
        if hasattr(self, "test_14b") and self.test_14b:
            test_cases.extend(
                [
                    {
                        "model": "14B",
                        "width": 1280,
                        "height": 704,
                        "frames": 16,
                        "steps": 30,
                    },
                    {
                        "model": "14B",
                        "width": 1280,
                        "height": 704,
                        "frames": 80,
                        "steps": 30,
                    },  # 5s @ 16fps
                ]
            )

        for params in test_cases:
            # Unload any existing models
            unload_model("video")

            # Predict usage
            model_name = f"wan-2.1-{params['model'].lower()}"
            predicted = self.predictor.estimate_video_vram(
                model_name=model_name,
                width=params["width"],
                height=params["height"],
                num_frames=params["frames"],
                num_inference_steps=params["steps"],
            )

            # Measure actual usage
            def load_video_model():
                from mydiffuser.config import VIDEO_MODELS

                model_id = VIDEO_MODELS.get(params["model"], VIDEO_MODELS["5B"])
                gen = ensure_video_generator(model_id=model_id)
                return gen

            measurement = self._measure_memory_delta(
                load_video_model,
                f"Video model load: {params['model']} {params['width']}x{params['height']}@{params['frames']}frames",
            )

            result = {
                **params,
                "type": "video_model_load",
                "predicted_gb": predicted.total_estimate_gb,
                "measured_gb": measurement["delta_gb"],
                "accuracy": abs(predicted.total_estimate_gb - measurement["delta_gb"]),
                "details": measurement,
            }

            results.append(result)
            logger.info(
                f"Video {params['model']}: {predicted.total_estimate_gb:.1f}GB predicted, {measurement['delta_gb']:.1f}GB measured"
            )

        return results

    def benchmark_assistant_models(self) -> List[Dict[str, Any]]:
        """Benchmark prompt assistant VRAM usage"""
        results = []

        # Test parameters
        test_cases = [
            {"model": "qwen2-vl-7b"},
        ]

        for params in test_cases:
            # Skip if not enough VRAM
            free_gb = self._get_memory_info().get("free_gb", 0)
            if free_gb < 25:
                logger.warning(
                    f"Skipping assistant test - insufficient VRAM ({free_gb:.1f}GB free)"
                )
                continue

            # Unload any existing models
            unload_model("assistant")

            # Predict usage
            predicted = self.predictor.estimate_assistant_vram(model_name="qwen2-vl-7b")

            # Measure actual usage
            def load_assistant():
                from mydiffuser.inference.state import ensure_prompt_assistant

                return ensure_prompt_assistant()

            measurement = self._measure_memory_delta(
                load_assistant, f"Assistant model load: {params['model']}"
            )

            result = {
                **params,
                "type": "assistant_model_load",
                "predicted_gb": predicted.total_estimate_gb,
                "measured_gb": measurement["delta_gb"],
                "accuracy": abs(predicted.total_estimate_gb - measurement["delta_gb"]),
                "details": measurement,
            }

            results.append(result)
            logger.info(
                f"Assistant: {predicted.total_estimate_gb:.1f}GB predicted, {measurement['delta_gb']:.1f}GB measured"
            )

        return results

    def run_all_benchmarks(self) -> Dict[str, Any]:
        """Run complete VRAM benchmark suite"""
        logger.info("Starting VRAM baseline measurement...")

        # System info
        system_info = {
            "cuda_available": torch.cuda.is_available(),
            "device_name": torch.cuda.get_device_name(0)
            if torch.cuda.is_available()
            else "CPU",
            "total_memory_gb": torch.cuda.get_device_properties(0).total_memory
            / (1024**3)
            if torch.cuda.is_available()
            else 0,
            "timestamp": time.time(),
        }

        all_results = {"system_info": system_info, "benchmarks": {}}

        if not torch.cuda.is_available():
            logger.error("CUDA not available, skipping benchmarks")
            return all_results

        try:
            # Image benchmarks
            logger.info("Running image model benchmarks...")
            all_results["benchmarks"]["image"] = self.benchmark_image_models()

            # Video benchmarks
            logger.info("Running video model benchmarks...")
            all_results["benchmarks"]["video"] = self.benchmark_video_models()

            # Assistant benchmarks
            logger.info("Running assistant model benchmarks...")
            all_results["benchmarks"]["assistant"] = self.benchmark_assistant_models()

            # Calculate accuracy stats
            all_results["accuracy_stats"] = self._calculate_accuracy_stats(
                all_results["benchmarks"]
            )

            # Save results
            self.save_results(all_results)

            logger.info("VRAM baseline measurement complete!")

        except Exception as e:
            logger.error(f"Benchmark failed: {e}")
            all_results["error"] = str(e)

        return all_results

    def _calculate_accuracy_stats(
        self, benchmarks: Dict[str, List[Dict]]
    ) -> Dict[str, Any]:
        """Calculate prediction accuracy statistics"""
        all_measurements = []
        for category in benchmarks.values():
            all_measurements.extend(category)

        if not all_measurements:
            return {"error": "No measurements available"}

        accuracies = [m["accuracy"] for m in all_measurements]

        return {
            "total_measurements": len(all_measurements),
            "mean_absolute_error": sum(accuracies) / len(accuracies),
            "max_error": max(accuracies),
            "min_error": min(accuracies),
            "accuracy_percentage": 100
            - (sum(accuracies) / len(accuracies) / 10 * 100),  # Rough accuracy %
        }

    def save_results(self, results: Dict[str, Any]):
        """Save benchmark results to file"""
        output_path = Path("vram_baseline_results.json")

        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        logger.info(f"Results saved to {output_path}")

        # Also save a summary
        summary_path = Path("vram_baseline_summary.txt")
        with open(summary_path, "w") as f:
            f.write("VRAM Baseline Measurement Summary\n")
            f.write("=" * 40 + "\n\n")

            if "system_info" in results:
                info = results["system_info"]
                f.write(f"Device: {info['device_name']}\n")
                f.write(f"Total VRAM: {info['total_memory_gb']:.1f} GB\n\n")

            if "accuracy_stats" in results:
                stats = results["accuracy_stats"]
                f.write(f"Prediction Accuracy: {stats['accuracy_percentage']:.1f}%\n")
                f.write(
                    f"Mean Absolute Error: {stats['mean_absolute_error']:.2f} GB\n\n"
                )

            for category, measurements in results["benchmarks"].items():
                f.write(f"{category.upper()} MODELS:\n")
                f.write("-" * 20 + "\n")
                for m in measurements:
                    f.write(
                        f"{m['width']}x{m['height']}@{m.get('steps', 1)}: "
                        f"{m['predicted_gb']:.1f}GB predicted, "
                        f"{m['measured_gb']:.1f}GB measured "
                        f"({abs(m['predicted_gb'] - m['measured_gb']):.1f}GB error)\n"
                    )
                f.write("\n")

        logger.info(f"Summary saved to {summary_path}")


def main():
    """Run VRAM baseline measurement"""
    parser = argparse.ArgumentParser(description="VRAM baseline measurement tool")
    parser.add_argument(
        "--test-14b",
        action="store_true",
        help="Enable 14B model testing (requires 32GB+ VRAM)",
    )
    args = parser.parse_args()

    # Also check environment variable
    test_14b = args.test_14b or os.environ.get("TEST_14B", "").lower() in [
        "true",
        "1",
        "yes",
    ]

    benchmark = VRAMBenchmark(test_14b=test_14b)
    results = benchmark.run_all_benchmarks()

    # Print summary
    print("\n" + "=" * 50)
    print("VRAM BASELINE MEASUREMENT SUMMARY")
    print("=" * 50)

    if "system_info" in results:
        info = results["system_info"]
        print(f"Device: {info['device_name']}")
        print(f"Total VRAM: {info['total_memory_gb']:.1f} GB")

    if "accuracy_stats" in results:
        stats = results["accuracy_stats"]
        print(f"Prediction Accuracy: {stats['accuracy_percentage']:.1f}%")
        print(f"Mean Absolute Error: {stats['mean_absolute_error']:.2f} GB")

    print("\n" + "-" * 30)
    print("MEASURED VRAM USAGE:")
    print("-" * 30)

    for category, measurements in results["benchmarks"].items():
        print(f"\n{category.upper()}:")
        for m in measurements:
            if "width" in m and "height" in m:
                print(
                    f"  {m['width']}x{m['height']}@{m.get('steps', 1)}: "
                    f"{m['measured_gb']:.1f}GB"
                )
            else:
                print(f"  {m.get('model', 'model')}: {m['measured_gb']:.1f}GB")


if __name__ == "__main__":
    main()
