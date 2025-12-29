"""HTTP client for communicating with remote workers."""

import io
import logging
import tarfile
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

logger = logging.getLogger(__name__)


class WorkerClient:
    """HTTP client for submitting jobs and fetching results from workers."""

    def __init__(self, endpoint: str, timeout: float = 300.0):
        """Initialize worker client.

        Args:
            endpoint: Worker base URL (e.g., "http://localhost:8001")
            timeout: Request timeout in seconds (default 5 minutes for long-running jobs)
        """
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> "WorkerClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def health(self, timeout: float = 5.0) -> dict[str, Any]:
        """Check worker health and capabilities.

        Args:
            timeout: Health check timeout in seconds (default 5s for quick checks)

        Returns:
            Health status dict with capabilities, GPU info, etc.

        Raises:
            httpx.HTTPError: If worker is unreachable or unhealthy
            httpx.TimeoutException: If worker doesn't respond within timeout
        """
        response = self._client.get(f"{self.endpoint}/health", timeout=timeout)
        response.raise_for_status()
        return response.json()

    def submit_image_job(
        self,
        prompt: str,
        height: int,
        width: int,
        seed: int,
        num_inference_steps: int,
        guidance_scale: float,
    ) -> str:
        """Submit an image generation job to the worker.

        Args:
            prompt: Text prompt for image generation
            height: Image height in pixels
            width: Image width in pixels
            seed: Random seed for reproducibility
            num_inference_steps: Inference steps
            guidance_scale: Guidance scale

        Returns:
            Job ID (UUID string)

        Raises:
            httpx.HTTPError: If submission fails
        """
        import json

        request_data = {
            "prompt": prompt,
            "height": height,
            "width": width,
            "seed": seed,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
        }

        response = self._client.post(
            f"{self.endpoint}/jobs",
            data={
                "type": "image",
                "request_json": json.dumps(request_data),
            },
        )
        response.raise_for_status()
        result = response.json()
        job_id = result["job_id"]
        logger.info(f"Submitted image job to {self.endpoint}: {job_id}")
        return job_id

    def submit_video_job(
        self,
        prompt: str,
        source_image: Image.Image,
        seed: int,
        source_run_id: str | None,
        duration_seconds: int,
        fps: int,
        num_inference_steps: int,
        guidance_scale: float,
    ) -> str:
        """Submit a video generation job to the worker.

        Args:
            prompt: Text prompt for video generation
            source_image: Source image for I2V
            seed: Random seed for reproducibility
            source_run_id: Optional source run ID for tracking
            duration_seconds: Duration in seconds
            fps: Frames per second
            num_inference_steps: Inference steps
            guidance_scale: Guidance scale

        Returns:
            Job ID (UUID string)

        Raises:
            httpx.HTTPError: If submission fails
        """
        import json

        request_data = {
            "prompt": prompt,
            "seed": seed,
            "source_run_id": source_run_id,
            "duration_seconds": duration_seconds,
            "fps": fps,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
        }

        # Convert image to bytes
        img_buffer = io.BytesIO()
        source_image.save(img_buffer, format="PNG")
        img_buffer.seek(0)

        response = self._client.post(
            f"{self.endpoint}/jobs",
            data={
                "type": "video",
                "request_json": json.dumps(request_data),
            },
            files={
                "image": ("image.png", img_buffer, "image/png"),
            },
        )
        response.raise_for_status()
        result = response.json()
        job_id = result["job_id"]
        logger.info(f"Submitted video job to {self.endpoint}: {job_id}")
        return job_id

    def get_status(self, job_id: str) -> dict[str, Any]:
        """Get job status and progress.

        Args:
            job_id: Job ID returned from submit_*_job()

        Returns:
            Status dict with progress, step count, run_id, etc.

        Raises:
            httpx.HTTPError: If job not found or request fails
        """
        response = self._client.get(f"{self.endpoint}/jobs/{job_id}/status")
        response.raise_for_status()
        return response.json()

    def fetch_results(self, job_id: str, extract_to: Path) -> Path:
        """Fetch job results and extract to local directory.

        Args:
            job_id: Job ID to fetch results for
            extract_to: Directory to extract results to (will be created)

        Returns:
            Path to extracted run directory

        Raises:
            httpx.HTTPError: If job not complete or fetch fails
            RuntimeError: If extraction fails
        """
        # First check if job is complete
        status = self.get_status(job_id)
        if status["status"] != "complete":
            raise RuntimeError(
                f"Job not complete (status: {status['status']}). "
                f"Cannot fetch results yet."
            )

        run_id = status.get("run_id")
        if not run_id:
            raise RuntimeError("Job complete but no run_id available")

        # Download tar.gz
        logger.info(f"Fetching results for job {job_id} (run {run_id})...")
        response = self._client.get(f"{self.endpoint}/jobs/{job_id}/files")
        response.raise_for_status()

        # Extract tar.gz to target directory
        extract_to.mkdir(parents=True, exist_ok=True)

        try:
            with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tar:
                tar.extractall(extract_to, filter="data")
                logger.info(f"Extracted {len(tar.getmembers())} files to {extract_to}")
        except Exception as e:
            raise RuntimeError(f"Failed to extract results: {e}") from e

        return extract_to

    def delete_job(self, job_id: str) -> None:
        """Delete job results from worker (cleanup).

        Args:
            job_id: Job ID to delete

        Raises:
            httpx.HTTPError: If deletion fails
        """
        response = self._client.delete(f"{self.endpoint}/jobs/{job_id}")
        response.raise_for_status()
        logger.info(f"Deleted job {job_id} from worker")
