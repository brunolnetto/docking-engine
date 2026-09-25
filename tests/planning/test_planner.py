import pytest

from moldock.domain import (
    DockingExperiment,
    DomainValidationError,
    PreparedLigand,
    PreparedReceptor,
)
from moldock.planning import TaskPlanner


def make_experiment(**overrides) -> DockingExperiment:
    values = dict(
        receptor_id="rec_1",
        ligand_set_id="lib_1",
        search_space_id="space_1",
        backend="vina",
        backend_version="1.2.7",
        receptor_preparation_id="rprep_1",
        ligand_preparation_id="lprep_1",
        parameters={"exhaustiveness": 8},
    )
    values.update(overrides)
    return DockingExperiment(**values)


def make_receptor(**overrides) -> PreparedReceptor:
    values = dict(
        receptor_id="rec_1",
        preparation_id="rprep_1",
        prepared_receptor_id="prepared_rec_1",
    )
    values.update(overrides)
    return PreparedReceptor(**values)


def make_ligand(
    ligand_id: str = "lig_1",
    prepared_ligand_id: str = "prepared_lig_1",
    **overrides,
) -> PreparedLigand:
    values = dict(
        ligand_id=ligand_id,
        preparation_id="lprep_1",
        prepared_ligand_id=prepared_ligand_id,
    )
    values.update(overrides)
    return PreparedLigand(**values)


def test_one_prepared_ligand_produces_one_task():
    experiment = make_experiment()
    manifest = TaskPlanner.plan(
        experiment,
        make_receptor(),
        [make_ligand()],
    )

    assert manifest.experiment_id == experiment.experiment_id
    assert manifest.task_count == 1
    task = manifest.tasks[0]
    assert task.receptor_id == "rec_1"
    assert task.ligand_id == "lig_1"
    assert task.prepared_receptor_id == "prepared_rec_1"
    assert task.prepared_ligand_id == "prepared_lig_1"
    assert task.search_space_id == "space_1"


def test_n_prepared_ligands_produce_n_tasks():
    ligands = [
        make_ligand("lig_1", "prepared_lig_1"),
        make_ligand("lig_2", "prepared_lig_2"),
        make_ligand("lig_3", "prepared_lig_3"),
    ]

    manifest = TaskPlanner.plan(make_experiment(), make_receptor(), ligands)

    assert manifest.task_count == 3


def test_planning_is_deterministic_across_input_order():
    experiment = make_experiment()
    receptor = make_receptor()
    a = make_ligand("lig_a", "prepared_a")
    b = make_ligand("lig_b", "prepared_b")

    left = TaskPlanner.plan(experiment, receptor, [a, b])
    right = TaskPlanner.plan(experiment, receptor, [b, a])

    assert left.manifest_id == right.manifest_id
    assert [task.task_id for task in left.tasks] == [
        task.task_id for task in right.tasks
    ]


def test_exact_duplicate_prepared_ligand_does_not_duplicate_work():
    ligand = make_ligand()

    manifest = TaskPlanner.plan(
        make_experiment(),
        make_receptor(),
        [ligand, ligand],
    )

    assert manifest.task_count == 1


def test_task_identity_changes_when_prepared_ligand_changes():
    experiment = make_experiment()
    receptor = make_receptor()

    first = TaskPlanner.plan(
        experiment,
        receptor,
        [make_ligand(prepared_ligand_id="prepared_v1")],
    )
    second = TaskPlanner.plan(
        experiment,
        receptor,
        [make_ligand(prepared_ligand_id="prepared_v2")],
    )

    assert first.tasks[0].task_id != second.tasks[0].task_id


def test_receptor_must_match_experiment_source():
    with pytest.raises(DomainValidationError):
        TaskPlanner.plan(
            make_experiment(),
            make_receptor(receptor_id="rec_other"),
            [make_ligand()],
        )


def test_receptor_preparation_must_match_experiment():
    with pytest.raises(DomainValidationError):
        TaskPlanner.plan(
            make_experiment(),
            make_receptor(preparation_id="rprep_other"),
            [make_ligand()],
        )


def test_ligand_preparation_must_match_experiment():
    with pytest.raises(DomainValidationError):
        TaskPlanner.plan(
            make_experiment(),
            make_receptor(),
            [make_ligand(preparation_id="lprep_other")],
        )


def test_planner_rejects_task_identity_collision_with_different_provenance():
    first = make_ligand("source_a", "same_prepared_artifact")
    second = make_ligand("source_b", "same_prepared_artifact")

    with pytest.raises(DomainValidationError):
        TaskPlanner.plan(
            make_experiment(),
            make_receptor(),
            [first, second],
        )


def test_completed_tasks_can_be_excluded_purely_from_manifest():
    experiment = make_experiment()
    receptor = make_receptor()
    ligands = [
        make_ligand("lig_1", "prepared_lig_1"),
        make_ligand("lig_2", "prepared_lig_2"),
    ]
    manifest = TaskPlanner.plan(experiment, receptor, ligands)

    pending = manifest.pending_tasks({manifest.tasks[0].task_id})

    assert pending == (manifest.tasks[1],)
    assert manifest.task_count == 2


def test_planner_accepts_empty_ligand_collection():
    manifest = TaskPlanner.plan(make_experiment(), make_receptor(), [])

    assert manifest.task_count == 0
