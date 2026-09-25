from __future__ import annotations

from collections.abc import Iterable

from moldock.domain import (
    DockingExperiment,
    DockingTask,
    DomainValidationError,
    PreparedLigand,
    PreparedReceptor,
)

from .manifest import TaskManifest


class TaskPlanner:
    @staticmethod
    def plan(
        experiment: DockingExperiment,
        receptor: PreparedReceptor,
        ligands: Iterable[PreparedLigand],
    ) -> TaskManifest:
        TaskPlanner._validate_receptor(experiment, receptor)

        tasks_by_id: dict[str, DockingTask] = {}

        for ligand in ligands:
            if ligand.preparation_id != experiment.ligand_preparation_id:
                raise DomainValidationError(
                    "ligand preparation does not match experiment"
                )

            task = DockingTask(
                experiment_id=experiment.experiment_id,
                receptor_id=receptor.receptor_id,
                ligand_id=ligand.ligand_id,
                prepared_receptor_id=receptor.prepared_receptor_id,
                prepared_ligand_id=ligand.prepared_ligand_id,
                search_space_id=experiment.search_space_id,
            )

            existing = tasks_by_id.get(task.task_id)
            if existing is None:
                tasks_by_id[task.task_id] = task
                continue

            if existing != task:
                raise DomainValidationError(
                    "task identity collision has conflicting provenance"
                )

        return TaskManifest(experiment.experiment_id, tasks_by_id.values())

    @staticmethod
    def _validate_receptor(
        experiment: DockingExperiment,
        receptor: PreparedReceptor,
    ) -> None:
        if receptor.receptor_id != experiment.receptor_id:
            raise DomainValidationError(
                "prepared receptor does not match experiment receptor"
            )
        if receptor.preparation_id != experiment.receptor_preparation_id:
            raise DomainValidationError(
                "receptor preparation does not match experiment"
            )
