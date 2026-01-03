#!/usr/bin/env python3
"""
Performance Benchmarking Script

Submits a grid of jobs with varying parameters to collect training data
for improving time/VRAM prediction accuracy.

Usage:
    # Run image benchmarks only (default)
    python scripts/benchmark_performance.py

    # Test with small batch
    python scripts/benchmark_performance.py --batch-size 6

    # Include video benchmarks (slow!)
    python scripts/benchmark_performance.py --test-videos

    # Quick test mode
    python scripts/benchmark_performance.py --quick
"""

import argparse
import asyncio
import csv
import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class BenchmarkConfig:
    """Configuration for benchmark run"""

    client_url: str = "http://localhost:8000"
    worker_name: str = "local"

    # Image parameters
    image_resolutions: list[tuple[int, int]] = field(
        default_factory=lambda: [(832, 480), (1280, 704), (1920, 1080)]
    )
    image_guidance_scales: list[float] = field(default_factory=lambda: [0.3, 3.0, 8.0])
    image_step_counts: list[int] = field(default_factory=lambda: [3, 6, 10, 20])

    # Video parameters (optional)
    video_resolutions: list[tuple[int, int]] = field(
        default_factory=lambda: [(832, 480), (1280, 704)]
    )
    video_durations: list[int] = field(default_factory=lambda: [3, 5])
    video_step_counts: list[int] = field(default_factory=lambda: [15, 30])

    # Control
    test_images: bool = True
    test_videos: bool = False  # Slow, opt-in
    seed: int = 42
    batch_size: int | None = None  # None = all, or set to N for testing
    output_dir: Path = field(default_factory=lambda: Path("benchmark_output"))

    # Prompts
    image_prompt: str = "a red cube on a blue surface"
    video_prompt: str = "the cube rotates slowly"


class PerformanceBenchmark:
    """Benchmark runner for performance data collection"""

    def __init__(self, config: BenchmarkConfig):
        self.config = config
        self.results: list[dict[str, Any]] = []
        self.start_time = time.time()
        self.completed_count = 0
        self.total_count = 0

        # Create output directory
        self.config.output_dir.mkdir(exist_ok=True)

    async def check_worker_health(self) -> bool:
        """Verify worker is online before starting"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.config.client_url}/api/workers/{self.config.worker_name}/health"
                )
                response.raise_for_status()
                data = response.json()
                return data.get("status") == "healthy"
        except Exception as e:
            print(f"❌ Worker health check failed: {e}")
            return False

    async def submit_image_job(
        self, width: int, height: int, steps: int, guidance: float
    ) -> str:
        """Submit image job and return job_id"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.config.client_url}/api/jobs/image",
                data={
                    "prompt": self.config.image_prompt,
                    "worker": self.config.worker_name,
                    "width": width,
                    "height": height,
                    "steps": steps,
                    "guidance": guidance,
                    "seed": self.config.seed,
                    "tags": json.dumps(["benchmark"]),
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["job_id"]

    async def submit_video_job(
        self, width: int, height: int, duration: int, steps: int
    ) -> str:
        """Submit video job and return job_id"""
        # First, generate a source image for video
        print("  Generating source image for video...")
        source_job_id = await self.submit_image_job(width, height, 6, 0.3)
        await self.poll_job_completion(source_job_id, silent=True)

        # Get the run_id from the completed job
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.config.client_url}/api/jobs/{source_job_id}"
            )
            data = response.json()
            # API returns "results" (plural) not "result"
            source_run_id = data["results"]["worker_run_id"]

        # Submit video job
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.config.client_url}/api/jobs/video",
                data={
                    "prompt": self.config.video_prompt,
                    "worker": self.config.worker_name,
                    "source_run_id": source_run_id,
                    "duration_seconds": duration,
                    "fps": 12,
                    "steps": steps,
                    "guidance": 3.0,
                    "resolution": "480p" if width == 832 else "720p",
                    "seed": self.config.seed,
                    "tags": json.dumps(["benchmark"]),
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["job_id"]

    async def poll_job_completion(
        self, job_id: str, silent: bool = False
    ) -> dict[str, Any]:
        """Poll until job completes, return metadata"""
        poll_interval = 2.0  # seconds

        while True:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.config.client_url}/api/jobs/{job_id}"
                )
                data = response.json()

                status = data.get("status")

                if status == "complete":  # API returns "complete" not "completed"
                    # API returns "results" (plural) not "result"
                    # Extract the run_id from results
                    results = data.get("results", {})
                    return {
                        "run_id": results.get("worker_run_id"),
                        "local_run_id": results.get("local_run_id"),
                    }
                elif status == "failed":
                    error = data.get("error", "Unknown error")
                    raise RuntimeError(f"Job failed: {error}")

                # Still running, wait and retry
                if not silent:
                    print(".", end="", flush=True)
                await asyncio.sleep(poll_interval)

    def query_job_performance(self, run_id: str) -> dict[str, Any] | None:
        """Query database for actual performance metrics"""
        db_path = Path("outputs/runs.db")
        if not db_path.exists():
            print(f"⚠ Database not found: {db_path}")
            return None

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT
                    id, type, model_id, gpu_arch,
                    width, height, num_inference_steps, guidance_scale,
                    vram_predicted_total, vram_actual_total,
                    time_predicted_seconds, seconds_elapsed,
                    inference_seconds
                FROM runs
                WHERE id = ?
                """,
                (run_id,),
            )
            row = cursor.fetchone()
            conn.close()

            if row:
                return dict(row)
            return None
        except Exception as e:
            print(f"⚠ Database query failed: {e}")
            return None

    async def run_image_benchmarks(self):
        """Run image generation benchmark grid"""
        print("🖼️  Running image benchmarks...")

        # Calculate total
        combinations = []
        for width, height in self.config.image_resolutions:
            for guidance in self.config.image_guidance_scales:
                for steps in self.config.image_step_counts:
                    combinations.append((width, height, guidance, steps))

        # Apply batch size limit
        if self.config.batch_size:
            combinations = combinations[: self.config.batch_size]

        self.total_count += len(combinations)
        print(f"  {len(combinations)} combinations to test")

        for i, (width, height, guidance, steps) in enumerate(combinations, 1):
            print(
                f"\n[{i}/{len(combinations)}] {width}×{height} @{steps} steps, guidance={guidance}",
                end=" ",
                flush=True,
            )

            try:
                # Submit job
                job_id = await self.submit_image_job(width, height, steps, guidance)

                # Wait for completion
                result = await self.poll_job_completion(job_id)
                run_id = result["run_id"]

                # Query performance data
                perf_data = self.query_job_performance(run_id)

                if perf_data:
                    actual_time = perf_data.get("seconds_elapsed", 0)
                    predicted_time = perf_data.get("time_predicted_seconds", 0)
                    time_per_step = actual_time / steps if steps > 0 else 0

                    print(
                        f" ✓ {actual_time:.1f}s (predicted: {predicted_time:.1f}s, {time_per_step:.2f}s/step)"
                    )

                    # Store result
                    self.results.append(
                        {
                            "type": "image",
                            "job_id": job_id,
                            "run_id": run_id,
                            "width": width,
                            "height": height,
                            "steps": steps,
                            "guidance": guidance,
                            **perf_data,
                            "time_per_step": time_per_step,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                    self.completed_count += 1

                    # Save incremental results
                    self.save_results_incremental()
                else:
                    print(" ⚠ No performance data")

            except Exception as e:
                print(f" ❌ Failed: {e}")
                continue

    async def run_video_benchmarks(self):
        """Run video generation benchmark grid"""
        print("\n\n🎬 Running video benchmarks...")

        # Calculate total
        combinations = []
        for width, height in self.config.video_resolutions:
            for duration in self.config.video_durations:
                for steps in self.config.video_step_counts:
                    combinations.append((width, height, duration, steps))

        # Apply batch size limit
        if self.config.batch_size:
            combinations = combinations[: self.config.batch_size]

        self.total_count += len(combinations)
        print(f"  {len(combinations)} combinations to test")

        for i, (width, height, duration, steps) in enumerate(combinations, 1):
            print(
                f"\n[{i}/{len(combinations)}] {width}×{height} {duration}s @{steps} steps",
                end=" ",
                flush=True,
            )

            try:
                # Submit job
                job_id = await self.submit_video_job(width, height, duration, steps)

                # Wait for completion
                result = await self.poll_job_completion(job_id)
                run_id = result["run_id"]

                # Query performance data
                perf_data = self.query_job_performance(run_id)

                if perf_data:
                    actual_time = perf_data.get("seconds_elapsed", 0)
                    predicted_time = perf_data.get("time_predicted_seconds", 0)
                    time_per_step = actual_time / steps if steps > 0 else 0

                    print(
                        f" ✓ {actual_time:.1f}s (predicted: {predicted_time:.1f}s, {time_per_step:.2f}s/step)"
                    )

                    # Store result
                    self.results.append(
                        {
                            "type": "video",
                            "job_id": job_id,
                            "run_id": run_id,
                            "width": width,
                            "height": height,
                            "duration": duration,
                            "steps": steps,
                            **perf_data,
                            "time_per_step": time_per_step,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                    self.completed_count += 1

                    # Save incremental results
                    self.save_results_incremental()
                else:
                    print(" ⚠ No performance data")

            except Exception as e:
                print(f" ❌ Failed: {e}")
                continue

    def save_results_incremental(self):
        """Save results after each job (for crash recovery)"""
        output_path = self.config.output_dir / "benchmark_results.json"
        with open(output_path, "w") as f:
            json.dump(
                {
                    "config": {
                        "test_images": self.config.test_images,
                        "test_videos": self.config.test_videos,
                        "batch_size": self.config.batch_size,
                    },
                    "completed": self.completed_count,
                    "total": self.total_count,
                    "results": self.results,
                },
                f,
                indent=2,
            )

    def analyze_results(self):
        """Analyze collected data and generate report"""
        print(f"\n\n📊 Analyzing {len(self.results)} samples...")

        if not self.results:
            print("❌ No results to analyze")
            return

        # Export CSV
        self._export_csv()

        # Calculate per-configuration statistics
        self._calculate_statistics()

        # Generate recommendations
        self._generate_recommendations()

    def _export_csv(self):
        """Export results to CSV"""
        csv_path = self.config.output_dir / "benchmark_results.csv"

        with open(csv_path, "w", newline="") as f:
            if not self.results:
                return

            fieldnames = list(self.results[0].keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.results)

        print(f"  ✓ CSV exported: {csv_path}")

    def _calculate_statistics(self):
        """Calculate per-resolution/guidance statistics"""
        # Group by configuration
        configs = {}

        for result in self.results:
            if result["type"] == "image":
                key = (
                    result["width"],
                    result["height"],
                    result.get("guidance_scale", 0),
                )
            else:  # video
                key = (result["width"], result["height"], result.get("duration", 0))

            if key not in configs:
                configs[key] = []
            configs[key].append(result)

        # Calculate statistics for each configuration
        stats_path = self.config.output_dir / "benchmark_statistics.txt"
        with open(stats_path, "w") as f:
            f.write("Performance Statistics by Configuration\n")
            f.write("=" * 60 + "\n\n")

            for key, samples in configs.items():
                if len(key) == 3 and isinstance(key[2], float):
                    # Image
                    w, h, guidance = key
                    f.write(f"Image {w}×{h} @ guidance={guidance}\n")
                else:
                    # Video
                    w, h, duration = key
                    f.write(f"Video {w}×{h} @ {duration}s\n")

                f.write("-" * 40 + "\n")

                # Calculate average time per step
                times_per_step = [s["time_per_step"] for s in samples if s.get("time_per_step")]
                if times_per_step:
                    avg_time_per_step = sum(times_per_step) / len(times_per_step)
                    f.write(f"  Avg time per step: {avg_time_per_step:.3f}s\n")

                # Calculate prediction errors
                errors = []
                for s in samples:
                    if s.get("seconds_elapsed") and s.get("time_predicted_seconds"):
                        actual = s["seconds_elapsed"]
                        predicted = s["time_predicted_seconds"]
                        error_pct = abs(actual - predicted) / actual * 100
                        errors.append(error_pct)

                if errors:
                    avg_error = sum(errors) / len(errors)
                    f.write(f"  Avg prediction error: {avg_error:.1f}%\n")

                f.write(f"  Samples: {len(samples)}\n\n")

        print(f"  ✓ Statistics: {stats_path}")

    def _generate_recommendations(self):
        """Generate recommendations for improving predictions"""
        rec_path = self.config.output_dir / "benchmark_recommendations.txt"

        with open(rec_path, "w") as f:
            f.write("Performance Prediction Recommendations\n")
            f.write("=" * 60 + "\n\n")

            f.write("Based on collected benchmark data:\n\n")

            # Group image results by resolution
            image_results = [r for r in self.results if r["type"] == "image"]

            if image_results:
                f.write("IMAGE GENERATION:\n")
                f.write("-" * 40 + "\n")

                # Calculate overall average time per step
                all_times_per_step = [
                    r["time_per_step"]
                    for r in image_results
                    if r.get("time_per_step")
                ]
                if all_times_per_step:
                    avg = sum(all_times_per_step) / len(all_times_per_step)
                    f.write(f"Average time per step: {avg:.3f}s\n")
                    f.write(
                        f"Suggestion: Update base step time coefficient to {avg:.4f}\n\n"
                    )

            # Group video results
            video_results = [r for r in self.results if r["type"] == "video"]

            if video_results:
                f.write("VIDEO GENERATION:\n")
                f.write("-" * 40 + "\n")

                all_times_per_step = [
                    r["time_per_step"]
                    for r in video_results
                    if r.get("time_per_step")
                ]
                if all_times_per_step:
                    avg = sum(all_times_per_step) / len(all_times_per_step)
                    f.write(f"Average time per step: {avg:.3f}s\n")
                    f.write(
                        f"Suggestion: Update video step time coefficient to {avg:.4f}\n\n"
                    )

            f.write("\nNext steps:\n")
            f.write("1. Review statistics in benchmark_statistics.txt\n")
            f.write("2. Update coefficients in src/mydiffuser/client/performance_estimator.py\n")
            f.write("3. Retrain models on /admin/performance dashboard\n")

        print(f"  ✓ Recommendations: {rec_path}")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Performance benchmarking tool")
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Limit number of samples (for testing)",
    )
    parser.add_argument(
        "--test-videos",
        action="store_true",
        help="Include video benchmarks (slow!)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick test mode (6 image samples only)",
    )
    args = parser.parse_args()

    # Configure
    config = BenchmarkConfig()

    if args.quick:
        config.batch_size = 6
        config.test_videos = False
    elif args.batch_size:
        config.batch_size = args.batch_size

    if args.test_videos:
        config.test_videos = True

    # Run benchmark
    benchmark = PerformanceBenchmark(config)

    print("=" * 60)
    print("PERFORMANCE BENCHMARKING")
    print("=" * 60)
    print(f"Client: {config.client_url}")
    print(f"Worker: {config.worker_name}")
    print(f"Image tests: {config.test_images}")
    print(f"Video tests: {config.test_videos}")
    if config.batch_size:
        print(f"Batch size: {config.batch_size}")
    print()

    # Check worker health
    print("Checking worker health...", end=" ", flush=True)
    if not await benchmark.check_worker_health():
        print("\n❌ Worker not available. Start the worker and try again.")
        return 1
    print("✓")

    try:
        # Run benchmarks
        if config.test_images:
            await benchmark.run_image_benchmarks()

        if config.test_videos:
            await benchmark.run_video_benchmarks()

        # Analyze results
        benchmark.analyze_results()

        # Summary
        elapsed = time.time() - benchmark.start_time
        print("\n" + "=" * 60)
        print("BENCHMARK COMPLETE")
        print("=" * 60)
        print(f"Completed: {benchmark.completed_count} jobs")
        print(f"Total time: {elapsed / 60:.1f} minutes")
        print(f"Output directory: {config.output_dir}")
        print()
        print("Next steps:")
        print("1. Review benchmark_statistics.txt")
        print("2. Review benchmark_recommendations.txt")
        print("3. Update performance_estimator.py coefficients")
        print("4. Retrain models on /admin/performance dashboard")

        return 0

    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted by user")
        print(f"Partial results saved: {benchmark.completed_count} jobs")
        benchmark.save_results_incremental()
        return 130

    except Exception as e:
        print(f"\n\n❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
