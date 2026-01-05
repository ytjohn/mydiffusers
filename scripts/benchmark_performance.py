#!/usr/bin/env python3
"""
Performance Benchmarking Script

Submits a grid of jobs with varying parameters to collect training data
for improving time/VRAM prediction accuracy.

Usage:
    # Image benchmarks only (default, memory-safe)
    python scripts/benchmark_performance.py

    # Explicit images-only
    python scripts/benchmark_performance.py --images-only

    # Video benchmarks only (run separately for memory safety)
    python scripts/benchmark_performance.py --videos-only

    # Both in one run (may cause memory pressure in lazy mode)
    python scripts/benchmark_performance.py --test-videos

    # Test with small batch
    python scripts/benchmark_performance.py --batch-size 6

    # Quick test mode (6 image samples)
    python scripts/benchmark_performance.py --quick

    # Filter by resolution (e.g., only test 720p videos)
    python scripts/benchmark_performance.py --videos-only --resolution 720p

    # Filter by multiple criteria
    python scripts/benchmark_performance.py --videos-only --resolution 1280x704 --duration 3 --steps 30

    # Skip to specific test (e.g., start at test #6)
    python scripts/benchmark_performance.py --videos-only --start-index 6
"""

import argparse
import asyncio
import csv
import json
import random
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

def randomSeed():
    return random.randint(20, 999999)

@dataclass
class BenchmarkConfig:
    """Configuration for benchmark run"""

    client_url: str = "http://localhost:8000"
    worker_name: str = "local"

    # Image parameters
    # More resolutions to test pixel dependency hypothesis
    # Current model assumes pixels^0.0, but 768x768 and 1280x704 show slower times
    image_resolutions: list[tuple[int, int]] = field(
        default_factory=lambda: [
            (832, 480),    # baseline (228 samples)
            (480, 832),    # portrait (17 samples)
            (768, 768),    # square small (7 samples, 3.2s/step - slower!)
            (1024, 1024),  # square medium (NEW - test square hypothesis)
            (1280, 704),   # 720p (1 sample, 6.3s/step - much slower!)
            (1920, 1088),  # 1080p (NEW - test high-res)
        ]
    )
    # More guidance scales to check if guidance affects timing
    image_guidance_scales: list[float] = field(
        default_factory=lambda: [0.3, 3.0, 8.0]
    )
    # More step variations for better linear fit (especially 2, 5, 7, 8, 12, 15)
    image_step_counts: list[int] = field(
        default_factory=lambda: [1, 2, 4, 6, 8, 10, 15, 20]
    )

    # Video parameters (optional)
    video_resolutions: list[tuple[int, int]] = field(
        default_factory=lambda: [(832, 480), (1280, 704)]
    )
    video_durations: list[int] = field(default_factory=lambda: [3, 5])
    video_step_counts: list[int] = field(default_factory=lambda: [15, 30])

    # Control
    test_images: bool = True
    test_videos: bool = False  # Slow, opt-in
    # seed: int = 42
    # make seed a random number for each run between 1 and 100
    seed: int = randomSeed()
    batch_size: int | None = None  # None = all, or set to N for testing
    output_dir: Path = field(default_factory=lambda: Path("benchmark_output"))

    # Prompts
    image_prompt: str = "dc comics animation realistic style. batman hacking" \
    " on a computer in a datacenter while fending off female and male villain distractions. " \
    " computer screens are visible. dramatic lighting, " \
    " high detail, intricate, sharp focus, digital art"
    video_prompt: str = "the shadows grow longer"


class PerformanceBenchmark:
    """Benchmark runner for performance data collection"""

    def __init__(self, config: BenchmarkConfig, filters: dict[str, Any] | None = None):
        self.config = config
        self.filters = filters or {}
        self.results: list[dict[str, Any]] = []
        self.start_time = time.time()
        self.completed_count = 0
        self.total_count = 0

        # Validate configuration
        self._validate_config()

        # Create output directory
        self.config.output_dir.mkdir(exist_ok=True)

    def _validate_config(self):
        """Validate configuration parameters"""
        # Check image resolutions (height must be divisible by 16)
        for width, height in self.config.image_resolutions:
            if height % 16 != 0:
                msg = f"Image resolution {width}x{height}: height must be divisible by 16"
                raise ValueError(msg)

        # Check video resolutions (height must be divisible by 16)
        if self.config.test_videos:
            for width, height in self.config.video_resolutions:
                if height % 16 != 0:
                    msg = f"Video resolution {width}x{height}: height must be divisible by 16"
                    raise ValueError(msg)

    def _parse_resolution(self, res_str: str) -> tuple[int, int] | None:
        """Parse resolution string to (width, height) tuple

        Supports:
        - WIDTHxHEIGHT (e.g., '1280x704')
        - Preset names (e.g., '480p', '720p', '1080p')
        """
        # Common presets
        presets = {
            "480p": (832, 480),
            "720p": (1280, 704),
            "1080p": (1920, 1088),
        }

        # Check if it's a preset
        if res_str.lower() in presets:
            return presets[res_str.lower()]

        # Try parsing WIDTHxHEIGHT
        if 'x' in res_str.lower():
            try:
                width, height = res_str.lower().split('x')
                return (int(width), int(height))
            except (ValueError, AttributeError):
                pass

        return None

    def _apply_filters(self, combinations: list[tuple]) -> list[tuple]:
        """Apply filters to combination list"""
        if not self.filters:
            return combinations

        filtered = []
        for combo in combinations:
            width, height = combo[0], combo[1]

            # Check resolution filter
            if "resolution" in self.filters:
                target_res = self._parse_resolution(self.filters["resolution"])
                if target_res and (width, height) != target_res:
                    continue

            # Check duration filter (for video)
            if "duration" in self.filters and len(combo) >= 3:
                duration = combo[2]
                if duration != self.filters["duration"]:
                    continue

            # Check steps filter
            if "steps" in self.filters:
                steps = combo[-1]  # Steps is always last element
                if steps != self.filters["steps"]:
                    continue

            filtered.append(combo)

        return filtered

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

    async def check_for_active_jobs(self) -> tuple[bool, int]:
        """Check if worker has active jobs (running or queued)

        Returns:
            (has_jobs, queued_count): True if jobs exist, and count of queued jobs
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.config.client_url}/api/workers/{self.config.worker_name}/health"
                )
                response.raise_for_status()
                data = response.json()

                queued = data.get("queued_jobs", 0)
                running = data.get("running_job")

                has_jobs = queued > 0 or running is not None
                return has_jobs, queued
        except Exception as e:
            print(f"⚠ Could not check for active jobs: {e}")
            return False, 0

    async def unload_model(self, model_type: str):
        """Unload a specific model from worker

        Args:
            model_type: "image", "video", or "assistant"
        """
        try:
            # Get worker endpoint from health
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.config.client_url}/api/workers/{self.config.worker_name}/health"
                )
                health = response.json()
                worker_endpoint = health.get("endpoint", "http://localhost:8001")

            # Call unload endpoint on worker directly
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(f"{worker_endpoint}/unload/{model_type}")
                response.raise_for_status()
        except Exception as e:
            # Non-fatal, just log it
            print(f"⚠ Failed to unload {model_type} model: {e}")

    async def get_image_estimate(
        self, width: int, height: int, steps: int, guidance: float
    ) -> float:
        """Get time estimate for image job from API"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.config.client_url}/api/estimate",
                    json={
                        "type": "image",
                        "model_id": "Tongyi-MAI/Z-Image-Turbo",
                        "parameters": {
                            "width": width,
                            "height": height,
                            "num_inference_steps": steps,
                            "guidance_scale": guidance,
                        },
                        "worker_id": self.config.worker_name,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data.get("time_estimate_seconds", 300.0)
        except Exception as e:
            print(f"⚠ Estimate failed: {e}, using fallback")
            return 300.0  # Fallback to 5 minutes

    async def get_video_estimate(
        self, width: int, height: int, duration: int, steps: int
    ) -> float:
        """Get time estimate for video job from API"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.config.client_url}/api/estimate",
                    json={
                        "type": "video",
                        "model_id": "Wan-AI/Wan2.2-TI2V-5B-Diffusers",
                        "parameters": {
                            "width": width,
                            "height": height,
                            "duration_seconds": duration,
                            "num_inference_steps": steps,
                            "fps": 12,
                        },
                        "worker_id": self.config.worker_name,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data.get("time_estimate_seconds", 600.0)
        except Exception as e:
            print(f"⚠ Estimate failed: {e}, using fallback")
            return 600.0  # Fallback to 10 minutes

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
                    "seed": randomSeed(),
                    "tags": json.dumps(["benchmark"]),
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["job_id"]

    async def find_baseline_image(self, width: int, height: int) -> str | None:
        """Find existing baseline image for this resolution"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Query for existing baseline images with this resolution
                # Get multiple results since API does partial tag matching
                response = await client.get(
                    f"{self.config.client_url}/api/runs",
                    params={
                        "tags": "benchmark_baseline",
                        "type": "image",
                        "width": width,
                        "height": height,
                        "limit": 10,
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    runs = data.get("runs", [])
                    # Find first image that actually has the benchmark_baseline tag
                    for run in runs:
                        tags = run.get("tags", [])
                        if "benchmark_baseline" in tags:
                            return run.get("id")
        except Exception:
            pass
        return None

    async def generate_source_image(self, width: int, height: int, baseline: bool = False) -> str:
        """Generate a source image for video and return worker_run_id

        Args:
            width: Image width
            height: Image height
            baseline: If True, tag as benchmark_baseline for reuse
        """
        tags = ["benchmark", "video_source"]
        if baseline:
            tags.append("benchmark_baseline")

        # Submit with appropriate tags
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.config.client_url}/api/jobs/image",
                data={
                    "prompt": self.config.image_prompt,
                    "worker": self.config.worker_name,
                    "width": width,
                    "height": height,
                    "steps": 6,
                    "guidance": 0.3,
                    "seed": randomSeed(),
                    "tags": json.dumps(tags),
                },
            )
            response.raise_for_status()
            data = response.json()
            job_id = data["job_id"]

        result = await self.poll_job_completion(job_id, silent=True)
        return result.get("run_id")

    async def submit_video_job(
        self, width: int, height: int, duration: int, steps: int, source_run_id: str
    ) -> str:
        """Submit video job with pre-generated source image"""

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
                    "seed": randomSeed(),
                    "tags": json.dumps(["benchmark"]),
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["job_id"]

    async def poll_job_completion(
        self, job_id: str, silent: bool = False, max_wait: int = 600
    ) -> dict[str, Any]:
        """Poll until job completes, return metadata

        Args:
            job_id: Job ID to poll
            silent: If True, don't print progress dots
            max_wait: Maximum time to wait in seconds (default 600 = 10 min)
        """
        poll_interval = 2.0  # seconds
        start_time = time.time()

        while True:
            # Check if we've exceeded max wait time
            elapsed = time.time() - start_time
            if elapsed > max_wait:
                raise TimeoutError(f"Job {job_id} did not complete within {max_wait}s")

            async with httpx.AsyncClient(timeout=30.0) as client:
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

    async def warmup_image_model(self):
        """Check if image model is loaded, warmup if needed"""
        print("🔥 Checking image model...", end=" ", flush=True)

        # Check if model is already loaded
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.config.client_url}/api/workers/{self.config.worker_name}/health"
                )
                health = response.json()
                if health.get("models_loaded", {}).get("image"):
                    print("✓ (already loaded)")
                    return
        except Exception:
            pass  # If health check fails, proceed with warmup

        # Model not loaded, submit minimal warmup job
        print("loading...", end=" ", flush=True)
        try:
            # Submit smallest possible job (480p, 1 step for fastest load)
            # Allow up to 120s for model loading (first load can be slow)
            job_id = await self.submit_image_job(832, 480, 1, 0.3)
            await self.poll_job_completion(job_id, silent=True, max_wait=120)
            print("✓")
        except Exception as e:
            # Model may have loaded even if we got an error
            print(f"⚠ (error: {type(e).__name__})")

    async def warmup_video_model(self):
        """Check if video model is loaded, warmup if needed"""
        print("🔥 Checking video model...", end=" ", flush=True)

        # Check if model is already loaded
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.config.client_url}/api/workers/{self.config.worker_name}/health"
                )
                health = response.json()
                if health.get("models_loaded", {}).get("video"):
                    print("✓ (already loaded)")
                    return
        except Exception:
            pass  # If health check fails, proceed with warmup

        # Model not loaded, submit minimal warmup job
        print("loading...", end=" ", flush=True)
        try:
            # Generate source image first (minimal job)
            source_run_id = await self.generate_source_image(832, 480)
            if not source_run_id:
                raise RuntimeError("Failed to generate source image for warmup")

            # Submit MINIMAL video job: 480p, 1 second, 8 steps (fastest possible)
            # Allow up to 30 minutes for first load - MIOpen VAE kernel compilation can take 20-30 min
            job_id = await self.submit_video_job(832, 480, 1, 8, source_run_id)
            print(f"[warmup job:{job_id[:8]}]", end=" ", flush=True)
            await self.poll_job_completion(job_id, silent=True, max_wait=1800)
            print("✓")
        except Exception as e:
            # Model may have loaded even if we got an error
            print(f"⚠ (error: {type(e).__name__})")

    async def run_image_benchmarks(self):
        """Run image generation benchmark grid"""
        # Warmup model first
        await self.warmup_image_model()

        print("🖼️  Running image benchmarks...")

        # Calculate total
        combinations = []
        for width, height in self.config.image_resolutions:
            for guidance in self.config.image_guidance_scales:
                for steps in self.config.image_step_counts:
                    combinations.append((width, height, guidance, steps))

        # Apply filters
        combinations = self._apply_filters(combinations)

        # Apply start index (1-based to 0-based)
        start_idx = self.filters.get("start_index", 1) - 1
        if start_idx > 0:
            combinations = combinations[start_idx:]

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
                # Get estimate BEFORE submitting job (to track prediction accuracy)
                estimated_time = await self.get_image_estimate(width, height, steps, guidance)
                print(f"(est: {estimated_time:.1f}s)", end=" ", flush=True)

                # Submit job
                job_id = await self.submit_image_job(width, height, steps, guidance)
                print(f"[job:{job_id[:8]}]", end=" ", flush=True)

                # Wait for completion
                result = await self.poll_job_completion(job_id)
                run_id = result.get("run_id")

                if not run_id:
                    raise RuntimeError("No worker_run_id in response (model may not be loaded)")

                # Query performance data
                perf_data = self.query_job_performance(run_id)

                if perf_data:
                    actual_time = perf_data.get("seconds_elapsed", 0)
                    # Use our pre-submission estimate, not the database value
                    predicted_time = estimated_time
                    time_per_step = actual_time / steps if steps > 0 else 0
                    error_pct = ((actual_time - predicted_time) / predicted_time * 100) if predicted_time > 0 else 0

                    print(
                        f"✓ {actual_time:.1f}s ({error_pct:+.0f}%, {time_per_step:.2f}s/step) [run:{run_id}]"
                    )

                    # Store result with our explicit estimate (override database value)
                    result_data = {
                        "type": "image",
                        "job_id": job_id,
                        "run_id": run_id,
                        "width": width,
                        "height": height,
                        "steps": steps,
                        "guidance": guidance,
                        **perf_data,
                        "time_predicted_seconds": predicted_time,  # Override with our pre-submission estimate
                        "time_per_step": time_per_step,
                        "timestamp": datetime.now().isoformat(),
                    }
                    self.results.append(result_data)
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
        print()
        print("🎬 Running video benchmarks...")

        # Check for baseline source images BEFORE loading models
        print("  Checking for baseline source images...", end=" ", flush=True)
        source_images = {}
        unique_resolutions = set(
            (width, height) for width, height in self.config.video_resolutions
        )

        # Check which baselines exist
        missing_baselines = []
        for width, height in unique_resolutions:
            source_run_id = await self.find_baseline_image(width, height)
            if source_run_id:
                source_images[(width, height)] = source_run_id
            else:
                missing_baselines.append((width, height))

        if not missing_baselines:
            print(f"✓ (all {len(source_images)} found)")
        else:
            print(f"({len(source_images)} found, {len(missing_baselines)} needed)")

            # Need to generate baselines - ensure image model is loaded
            print("  Ensuring image model loaded for baseline generation...", end=" ", flush=True)
            await self.warmup_image_model()
            print("✓")

            # Generate missing baselines
            print("  Generating baseline images...", end=" ", flush=True)
            for width, height in missing_baselines:
                source_run_id = await self.generate_source_image(width, height, baseline=True)
                if source_run_id:
                    source_images[(width, height)] = source_run_id
                else:
                    raise RuntimeError(f"Failed to generate baseline for {width}×{height}")
            print(f"✓ ({len(missing_baselines)} generated)")

            # Unload image model before loading video
            print("  Unloading image model...", end=" ", flush=True)
            await self.unload_model("image")
            print("✓")

        # Now load video model
        await self.warmup_video_model()

        # Calculate total
        combinations = []
        for width, height in self.config.video_resolutions:
            for duration in self.config.video_durations:
                for steps in self.config.video_step_counts:
                    combinations.append((width, height, duration, steps))

        # Apply filters
        combinations = self._apply_filters(combinations)

        # Apply start index (1-based to 0-based)
        start_idx = self.filters.get("start_index", 1) - 1
        if start_idx > 0:
            combinations = combinations[start_idx:]

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
                # Get estimate BEFORE submitting job (to track prediction accuracy)
                estimated_time = await self.get_video_estimate(width, height, duration, steps)
                print(f"(est: {estimated_time:.1f}s)", end=" ", flush=True)

                # Get pre-generated source image for this resolution
                source_run_id = source_images[(width, height)]

                # Submit job
                job_id = await self.submit_video_job(width, height, duration, steps, source_run_id)
                print(f"[job:{job_id[:8]}]", end=" ", flush=True)

                # Wait for completion
                result = await self.poll_job_completion(job_id)
                run_id = result["run_id"]

                # Query performance data
                perf_data = self.query_job_performance(run_id)

                if perf_data:
                    actual_time = perf_data.get("seconds_elapsed", 0)
                    # Use our pre-submission estimate, not the database value
                    predicted_time = estimated_time
                    time_per_step = actual_time / steps if steps > 0 else 0
                    error_pct = ((actual_time - predicted_time) / predicted_time * 100) if predicted_time > 0 else 0

                    print(
                        f"✓ {actual_time:.1f}s ({error_pct:+.0f}%, {time_per_step:.2f}s/step) [run:{run_id}]"
                    )

                    # Store result with our explicit estimate (override database value)
                    result_data = {
                        "type": "video",
                        "job_id": job_id,
                        "run_id": run_id,
                        "width": width,
                        "height": height,
                        "duration": duration,
                        "steps": steps,
                        **perf_data,
                        "time_predicted_seconds": predicted_time,  # Override with our pre-submission estimate
                        "time_per_step": time_per_step,
                        "timestamp": datetime.now().isoformat(),
                    }
                    self.results.append(result_data)
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

    # Test selection (mutually exclusive)
    test_group = parser.add_mutually_exclusive_group()
    test_group.add_argument(
        "--images-only",
        action="store_true",
        help="Run only image benchmarks",
    )
    test_group.add_argument(
        "--videos-only",
        action="store_true",
        help="Run only video benchmarks",
    )
    test_group.add_argument(
        "--test-videos",
        action="store_true",
        help="Run both image and video benchmarks (may cause memory pressure)",
    )

    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick test mode (6 image samples only)",
    )

    # Filtering options
    parser.add_argument(
        "--resolution",
        type=str,
        help="Filter by resolution (e.g., '1280x704' or '720p')",
    )
    parser.add_argument(
        "--duration",
        type=int,
        help="Filter video tests by duration (e.g., 3 or 5)",
    )
    parser.add_argument(
        "--steps",
        type=int,
        help="Filter tests by step count (e.g., 15 or 30)",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=1,
        help="Start from specific test index (1-based)",
    )

    args = parser.parse_args()

    # Configure
    config = BenchmarkConfig()

    # Handle test selection
    if args.images_only:
        config.test_images = True
        config.test_videos = False
    elif args.videos_only:
        config.test_images = False
        config.test_videos = True
    elif args.test_videos:
        config.test_images = True
        config.test_videos = True
    # else: default is images only (test_images=True, test_videos=False)

    # Handle batch size and quick mode
    if args.quick:
        config.batch_size = 6
    elif args.batch_size:
        config.batch_size = args.batch_size

    # Build filters
    filters = {}
    if args.resolution:
        filters["resolution"] = args.resolution
    if args.duration:
        filters["duration"] = args.duration
    if args.steps:
        filters["steps"] = args.steps
    if args.start_index != 1:
        filters["start_index"] = args.start_index

    # Run benchmark
    benchmark = PerformanceBenchmark(config, filters)

    print("=" * 60)
    print("PERFORMANCE BENCHMARKING")
    print("=" * 60)
    print(f"Client: {config.client_url}")
    print(f"Worker: {config.worker_name}")
    print(f"Image tests: {config.test_images}")
    print(f"Video tests: {config.test_videos}")
    if config.batch_size:
        print(f"Batch size: {config.batch_size}")
    if filters:
        print(f"Filters: {filters}")
    print()

    # Check worker health
    print("Checking worker health...", end=" ", flush=True)
    if not await benchmark.check_worker_health():
        print("\n❌ Worker not available. Start the worker and try again.")
        return 1
    print("✓")

    # Check for active jobs (benchmark needs exclusive access)
    has_jobs, _ = await benchmark.check_for_active_jobs()
    if has_jobs:
        print("\n❌ Worker has active jobs (running or queued)")
        print("   Benchmarks need exclusive worker access for accurate timing.")
        print("   Please wait for jobs to complete or cancel them, then retry.")
        return 1

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
