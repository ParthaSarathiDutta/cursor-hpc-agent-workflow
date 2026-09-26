"""Deterministic IterativeRunController."""

from __future__ import annotations

from blast_lib.config_types import UIConfig
from blast_lib.iterative_loop.ho_report_utils import count_scored_trials, sync_and_report_path
from blast_lib.iterative_loop.range_agent import RangeAgent
from blast_lib.iterative_loop.batch_submit_agent import BatchSubmitAgent
from blast_lib.iterative_loop.remote_sync import mirror_remote_to_local
from blast_lib.iterative_loop.slurm_timing import allocation_met_walltime, fetch_job_elapsed_seconds
from blast_lib.iterative_loop.state import (
    ACTIVE_PHASES,
    IterativeLoopState,
    Phase,
    begin_batch_workflow,
    load_state,
    save_state,
)
from blast_lib.iterative_loop.submit_agent import InteractiveSubmitResult, SubmitAgent
from blast_lib.remote import RemoteError


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
        self.batch_submit_agent = BatchSubmitAgent(config)

    def submit_batch_workflow(
        self,
        run_folder: str,
        walltime: str,
        total_cycles: int,
    ) -> IterativeLoopState:
        result = self.batch_submit_agent.submit(
            run_folder,
            walltime=walltime,
            total_cycles=total_cycles,
        )
        if not result.ok:
            state = load_state(self.config)
            return self._fail(state, result.message)
        begin_batch_workflow(
            self.config,
            run_folder=run_folder,
            walltime=walltime,
            total_cycles=total_cycles,
            workflow_id=result.workflow_id or "",
        )
        return mirror_remote_to_local(self.config, run_folder)

    def sync_from_remote(self, run_folder: str | None = None) -> IterativeLoopState:
        state = load_state(self.config)
        folder = run_folder or state.run_folder
        if not folder:
            return state
        return mirror_remote_to_local(self.config, folder)

    def tick(self) -> IterativeLoopState:
        state = load_state(self.config)
        if state.phase in (Phase.IDLE, Phase.COMPLETED, Phase.FAILED, Phase.STOPPED):
            return state

        if state.execution_mode == "batch" and state.phase in (
            Phase.QUEUED_ON_NERSC,
            Phase.RUNNING_ON_NERSC,
        ):
            return self.sync_from_remote()

        if state.phase == Phase.RUNNING_INTERACTIVE and state.interactive_launch_started:
            return self.fail_stale_interactive_launch(state)

        try:
            if state.phase == Phase.SUBMITTING:
                state = self._tick_submitting(state)
            elif state.phase == Phase.ANALYZING_BEST_SET:
                state = self._tick_analyzing(state)
            elif state.phase == Phase.UPDATING_RANGES:
                state = self._tick_updating_ranges(state)
            elif state.phase == Phase.STARTING_NEXT_CYCLE:
                state = self._tick_next_cycle(state)
        except RemoteError as exc:
            state.touch(phase=Phase.FAILED, error=str(exc), status_message="SSH / remote error.")
            save_state(self.config, state)

        return load_state(self.config)

    def fail_stale_interactive_launch(self, state: IterativeLoopState | None = None) -> IterativeLoopState:
        state = state or load_state(self.config)
        return self._fail(
            state,
            "Recovery required: interactive launch was in progress when the runner stopped. "
            "Check Perlmutter (squeue --me), then reset this workflow before starting again.",
        )

    def finish_interactive_cycle(self, result: InteractiveSubmitResult) -> IterativeLoopState:
        state = load_state(self.config)
        if state.phase != Phase.RUNNING_INTERACTIVE:
            return state

        alloc = result.allocation_job_id
        state.touch(
            last_launch_returncode=result.returncode,
            interactive_launch_started=False,
            active_job_id=alloc,
            slurm_state="INTERACTIVE_FINISHED" if result.returncode == 0 else f"EXIT_{result.returncode}",
            status_message="Interactive allocation finished. Checking ho.report…",
        )
        save_state(self.config, state)

        if state.stop_requested:
            return self._stop_after_allocation(state)

        before = state.scored_trial_count_before
        if before is None:
            return self._fail(state, "Missing scored_trial_count_before for this cycle")

        job_id = alloc or state.active_job_id
        if not job_id:
            return self._fail(state, "No Slurm job id in interactive log — cannot verify walltime.")

        elapsed_sec = fetch_job_elapsed_seconds(self.config, job_id)
        if elapsed_sec is None:
            return self._fail(state, f"Could not read sacct Elapsed for job {job_id}.")

        met, required_sec = allocation_met_walltime(elapsed_sec, state.walltime)
        state.touch(last_slurm_elapsed_sec=elapsed_sec)
        save_state(self.config, state)
        if not met:
            return self._fail(
                state,
                f"Allocation too short: sacct elapsed {elapsed_sec}s "
                f"(need ≥{required_sec}s walltime {state.walltime}, 5s slack). "
                f"Cycle not complete.",
            )

        try:
            rp = sync_and_report_path(self.config, state.run_folder)
            after = count_scored_trials(rp)
        except (RemoteError, OSError, FileNotFoundError) as exc:
            return self._fail(state, f"Post-allocation sync failed: {exc}")

        state.touch(scored_trial_count_after=after)
        if after <= before:
            return self._fail(
                state,
                f"No new scored trials after interactive run "
                f"(before={before}, after={after}). Range update skipped.",
            )

        state.touch(
            phase=Phase.ANALYZING_BEST_SET,
            status_message="Finding best set…",
        )
        save_state(self.config, state)
        return self._advance_through_range_and_maybe_next()

    def _advance_through_range_and_maybe_next(self) -> IterativeLoopState:
        """Run analyzing + range ticks until waiting on runner or terminal."""
        for _ in range(8):
            state = load_state(self.config)
            if state.phase == Phase.ANALYZING_BEST_SET:
                self._tick_analyzing(state)
            elif state.phase == Phase.UPDATING_RANGES:
                self._tick_updating_ranges(state)
            elif state.phase == Phase.STARTING_NEXT_CYCLE:
                self._tick_next_cycle(state)
            elif state.phase in (Phase.COMPLETED, Phase.FAILED, Phase.STOPPED, Phase.SUBMITTING):
                break
            else:
                break
        return load_state(self.config)

    def _fail(self, state: IterativeLoopState, message: str) -> IterativeLoopState:
        state.touch(phase=Phase.FAILED, error=message, status_message=message, interactive_launch_started=False)
        save_state(self.config, state)
        return state

    def _stop_after_allocation(self, state: IterativeLoopState) -> IterativeLoopState:
        state.touch(
            phase=Phase.STOPPED,
            interactive_launch_started=False,
            status_message="Stopped after current interactive allocation (stop was requested).",
            error=None,
        )
        save_state(self.config, state)
        return state

    def _tick_submitting(self, state: IterativeLoopState) -> IterativeLoopState:
        if state.stop_requested:
            state.touch(phase=Phase.STOPPED, status_message="Stopped — will not start a new cycle.")
            save_state(self.config, state)
            return state

        folder = state.run_folder
        try:
            rp = sync_and_report_path(self.config, folder)
            before = count_scored_trials(rp)
        except (RemoteError, OSError, FileNotFoundError) as exc:
            return self._fail(state, f"Cannot read ho.report before launch: {exc}")

        try:
            self.submit_agent.prepare_input(folder)
        except Exception as exc:  # noqa: BLE001
            return self._fail(state, f"Could not write input.txt: {exc}")

        state.touch(
            scored_trial_count_before=before,
            phase=Phase.RUNNING_INTERACTIVE,
            interactive_launch_started=False,
            active_job_id=None,
            status_message=f"Cycle {state.current_cycle}/{state.total_cycles}: requesting interactive GPUs…",
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

        if state.stop_requested:
            state.touch(
                phase=Phase.STOPPED,
                last_completed_cycle=state.current_cycle,
                status_message="Stopped after completing this cycle (stop was requested).",
            )
            save_state(self.config, state)
            return state

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
        if state.stop_requested:
            state.touch(phase=Phase.STOPPED, status_message="Stopped — will not start another cycle.")
            save_state(self.config, state)
            return state

        next_cycle = state.current_cycle + 1
        state.touch(
            last_completed_cycle=state.current_cycle,
            current_cycle=next_cycle,
            active_job_id=None,
            scored_trial_count_before=None,
            scored_trial_count_after=None,
            interactive_launch_started=False,
            phase=Phase.SUBMITTING,
            status_message=f"Starting cycle {next_cycle}/{state.total_cycles}…",
        )
        save_state(self.config, state)
        return state


def is_workflow_active(state: IterativeLoopState) -> bool:
    return state.phase in ACTIVE_PHASES
