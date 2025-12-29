"""Job queue management for worker.

Implements FIFO queue to process jobs one at a time.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Any

from mydiffuser.worker import state

logger = logging.getLogger(__name__)


@dataclass
class QueuedJob:
    """A job waiting in the queue."""

    job_id: str
    job_type: str  # "image" or "video"
    executor: Callable[[], Any]  # Function to execute the job


class JobQueue:
    """FIFO queue for processing jobs sequentially."""

    def __init__(self):
        self.queue: asyncio.Queue[QueuedJob] = asyncio.Queue()
        self.processor_task: asyncio.Task | None = None
        self.current_job_id: str | None = None

    def start_processor(self):
        """Start the background queue processor."""
        if self.processor_task is None or self.processor_task.done():
            self.processor_task = asyncio.create_task(self._process_queue())
            logger.info("Queue processor started")

    async def _process_queue(self):
        """Process jobs from queue one at a time."""
        logger.info("Queue processor running")
        while True:
            # Get next job from queue (blocks until available)
            queued_job = await self.queue.get()
            self.current_job_id = queued_job.job_id

            try:
                logger.info(
                    f"[{queued_job.job_id}] Starting {queued_job.job_type} job "
                    f"(queue size: {self.queue.qsize()})"
                )

                # Update status from "queued" to "pending" (about to start)
                progress = state.get_progress(queued_job.job_id)
                if progress:
                    progress.status = "pending"
                    progress.message = "Starting job..."

                # Execute the job
                await queued_job.executor()

                logger.info(f"[{queued_job.job_id}] Job completed")

            except Exception as e:
                logger.exception(f"[{queued_job.job_id}] Job failed in queue processor")
                state.mark_failed(queued_job.job_id, str(e))

            finally:
                self.current_job_id = None
                self.queue.task_done()

    async def submit(self, job_id: str, job_type: str, executor: Callable[[], Any]):
        """Submit a job to the queue.

        Args:
            job_id: Unique job identifier
            job_type: "image" or "video"
            executor: Async function to execute the job
        """
        queued_job = QueuedJob(job_id=job_id, job_type=job_type, executor=executor)

        # Initialize job progress with "queued" status
        state.job_progress[job_id] = state.JobProgress(
            status="queued",
            progress=0.0,
            current_step=0,
            total_steps=0,  # Will be set when job starts
            message=f"Queued (position: {self.queue.qsize() + 1})",
        )

        await self.queue.put(queued_job)
        logger.info(
            f"[{job_id}] Job queued at position {self.queue.qsize()} "
            f"(queue size: {self.queue.qsize()})"
        )

    def get_queue_size(self) -> int:
        """Get current number of jobs in queue."""
        return self.queue.qsize()

    def get_current_job_id(self) -> str | None:
        """Get the currently executing job ID."""
        return self.current_job_id


# Global job queue instance
job_queue = JobQueue()
