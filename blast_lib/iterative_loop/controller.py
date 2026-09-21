"""Deterministic IterativeRunController."""

from __future__ import annotations

from blast_lib.config_types import UIConfig
from blast_lib.iterative_loop.ho_report_utils import count_scored_trials, sync_and_report_path
from blast_lib.iterative_loop.range_agent import RangeAgent
from blast_lib.iterative_loop.state import (
    ACTIVE_PHASES,
    IterativeLoopState,
    Phase,
    load_state,
    save_state,
)
from blast_lib.iterative_loop.submit_agent import SubmitAgent
from blast_lib.remote import RemoteError
from blast_lib.slurm_monitor import query_job_status


class IterativeRunController:
    def __init__(
        self,
        config: UIConfig,
        *,
        submit_agent: SubmitAgent | None = None,
        range_agent: RangeAgent | None = None,
    ) -> None:
        self.config = config
        self.submit_agent = submit_agent or SubmitAgent(config)
        self.range_agent = range_agent or RangeAgent(config)

    def tick(self) -> IterativeLoopState:
        state = load_state(self.config)
        if state.phase in (Phase.IDLE, Phase.COMPLETED, Phase.FAILED, Phase.STOPPED):
            return state

        try:
            if state.phase == Phase.SUBMITTING:
                state = self._tick_submitting(state)
            elif state.phase == Phase.WAITING_FOR_JOB:
                state = self._tick_waiting(state)
            elif state.phase == Phase.ANALYZING_BEST_SET:
                state = self._tick_analyzing(state)
            elif state.phase == Phase.UPDATING_RANGES:
                state = self._tick_updating_ranges(state)
            elif state.phase == Phase.STARTING_NEXT_CYCLE:
                state = self._tick_next_cycle(state)
        except RemoteError as exc:
            state.touch(phase=Phase.FAILED, error=str(exc), status_message="SSH / remote error.")
            save_state(self.config, state)

        return state

    def _fail(self, state: IterativeLoopState, message: str) -> IterativeLoopState:
        state.touch(phase=Phase.FAILED, error=message, status_message=message)
        save_state(self.config, state)
        return state

    def _tick_submitting(self, state: IterativeLoopState) -> IterativeLoopState:
        if state.active_job_id:
            state.touch(
                phase=Phase.WAITING_FOR_JOB,
                status_message=f"Job {state.active_job_id} queued or running…",
            )
            save_state(self.config, state)
            return state

        folder = state.run_folder
        try:
            rp = sync_and_report_path(self.config, folder)
            before = count_scored_trials(rp)
        except (RemoteError, OSError, FileNotFoundError) as exc:
            return self._fail(state, f"Cannot read ho.report before submit: {exc}")

        state.touch(
            scored_trial_count_before=before,
            status_message=f"Submitting cycle {state.current_cycle}/{state.total_cycles}…",
        )
        save_state(self.config, state)

        try:
            job_id = self.submit_agent.submit(folder, state.walltime)
        except Exception as exc:  # noqa: BLE001 — submit failures must not advance cycle
            return self._fail(state, f"Submit failed: {exc}")

        state.touch(
            active_job_id=job_id,
            phase=Phase.WAITING_FOR_JOB,
            slurm_state="SUBMITTED",
            status_message=f"Submitted job {job_id}. Waiting for completion…",
        )
        save_state(self.config, state)
        return state

    def _tick_waiting(self, state: IterativeLoopState) -> IterativeLoopState:
        job_id = state.active_job_id
        if not job_id:
            return self._fail(state, "WAITING_FOR_JOB without active_job_id")

        status = query_job_status(self.config, job_id)
        if status.active:
            label = status.queue_state or "RUNNING"
            state.touch(slurm_state=label, status_message=f"Job {job_id} — {label}…")
            save_state(self.config, state)
            return state

        sacct = status.sacct_state or "NOT_IN_QUEUE"
        state.touch(slurm_state=sacct, status_message=f"Job {job_id} finished ({sacct}). Checking ho.report…")
        save_state(self.config, state)

        before = state.scored_trial_count_before
        if before is None:
            return self._fail(state, "Missing scored_trial_count_before for this cycle")

        try:
            rp = sync_and_report_path(self.config, state.run_folder)
            after = count_scored_trials(rp)
        except (RemoteError, OSError, FileNotFoundError) as exc:
            return self._fail(state, f"Post-job sync failed: {exc}")

        state.touch(scored_trial_count_after=after)
        if after <= before:
            return self._fail(
                state,
                f"No new scored trials after job {job_id} "
                f"(before={before}, after={after}). Range update skipped.",
            )

        state.touch(
            phase=Phase.ANALYZING_BEST_SET,
            status_message="Job finished. Finding best set…",
        )
        save_state(self.config, state)
        return state

    def _tick_analyzing(self, state: IterativeLoopState) -> IterativeLoopState:
        state.touch(
            phase=Phase.UPDATING_RANGES,
            status_message="Updating parameter ranges (changemodel.json.py)…",
        )
        save_state(self.config, state)
        return state

    def _tick_updating_ranges(self, state: IterativeLoopState) -> IterativeLoopState:
        result = self.range_agent.run(state.run_folder, report_already_synced=True)
        if not result.ok:
            state.touch(last_range_update="FAILED")
            return self._fail(state, f"Range update failed: {result.message}")

        state.touch(
            last_range_update="COMPLETED",
            last_best_score=result.best_score,
            last_best_iteration=result.best_iteration,
            status_message="Range update complete.",
        )
        save_state(self.config, state)

        if state.current_cycle >= state.total_cycles:
            state.touch(
                phase=Phase.COMPLETED,
                last_completed_cycle=state.current_cycle,
                active_job_id=None,
                status_message=f"Workflow complete — {state.total_cycles} cycle(s) finished.",
            )
            save_state(self.config, state)
            return state

        state.touch(phase=Phase.STARTING_NEXT_CYCLE, status_message="Starting next cycle…")
        save_state(self.config, state)
        return state

    def _tick_next_cycle(self, state: IterativeLoopState) -> IterativeLoopState:
        next_cycle = state.current_cycle + 1
        state.touch(
            last_completed_cycle=state.current_cycle,
            current_cycle=next_cycle,
            active_job_id=None,
            scored_trial_count_before=None,
            scored_trial_count_after=None,
            phase=Phase.SUBMITTING,
            status_message=f"Starting cycle {next_cycle}/{state.total_cycles}…",
        )
        save_state(self.config, state)
        return state


def is_workflow_active(state: IterativeLoopState) -> bool:
    return state.phase in ACTIVE_PHASES
