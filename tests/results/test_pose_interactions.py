import pytest

from moldock.domain import (
    DockingTask,
    DomainValidationError,
    Pose,
    PoseInteraction,
    PoseInteractionKind,
)
from moldock.repositories import (
    InMemoryTaskRepository,
    PreparedReceptorBinding,
)
from moldock.results import (
    InMemoryScientificResultRepository,
    PdbqtInteractionParser,
    PdbqtPoseInteractionAnalyzer,
)
from moldock.storage import MemoryArtifactStore
from moldock.domain import PreparedReceptor


def atom(
    serial: int,
    atom_name: str,
    residue: str,
    chain: str,
    residue_number: int,
    x: float,
    y: float,
    z: float,
    charge: float,
    atom_type: str,
) -> bytes:
    return (
        f"ATOM  {serial:5d} {atom_name:<4} {residue:>3} {chain}"
        f"{residue_number:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00    "
        f"{charge:7.3f} {atom_type}\n"
    ).encode()


def pose_model(index: int) -> bytes:
    return (
        f"MODEL {index}\n".encode()
        + b"REMARK VINA RESULT: -10.0 0.0 0.0\n"
        + atom(1, "C1", "UNL", "L", 1, 3.5, 0.0, 0.0, 0.0, "C")
        + atom(2, "O1", "UNL", "L", 1, 2.5, 3.0, 0.0, -0.4, "OA")
        + atom(3, "N1", "UNL", "L", 1, 4.0, 6.0, 0.0, 0.5, "N")
        + b"ENDMDL\n"
    )


def receptor() -> bytes:
    return (
        atom(1, "CG1", "VAL", "A", 10, 0.0, 0.0, 0.0, 0.0, "C")
        + atom(2, "NZ", "LYS", "A", 20, 0.0, 3.0, 0.0, 0.2, "N")
        + atom(3, "HZ1", "LYS", "A", 20, 1.0, 3.0, 0.0, 0.1, "HD")
        + atom(4, "OD1", "ASP", "A", 30, 0.0, 6.0, 0.0, -0.5, "OA")
    )


class PreparedInputs:
    def __init__(self, binding):
        self.binding = binding

    def get_receptor(self, prepared_receptor_id):
        if (
            self.binding is not None
            and prepared_receptor_id
            == self.binding.prepared.prepared_receptor_id
        ):
            return self.binding
        return None

    def get_ligand(self, prepared_ligand_id):
        return None


def test_pdbqt_interaction_analyzer_persists_contact_chemistry():
    store = MemoryArtifactStore()
    receptor_blob = store.put(receptor())
    prepared_receptor = PreparedReceptor(
        receptor_id="rec_1",
        preparation_id="rprep_1",
        prepared_receptor_id="prec_1",
    )
    prepared_inputs = PreparedInputs(
        PreparedReceptorBinding(
            prepared=prepared_receptor,
            blob=receptor_blob,
        )
    )

    tasks = InMemoryTaskRepository()
    task = DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_id="plig_1",
        search_space_id="space_1",
    )
    tasks.register(task)

    science = InMemoryScientificResultRepository()
    pose = Pose(
        task_id=task.task_id,
        attempt_id="attempt_1",
        source_artifact_id="artifact_1",
        model_index=1,
        geometry_sha256="a" * 64,
    )
    science.register_pose(pose)

    analyzer = PdbqtPoseInteractionAnalyzer(
        task_repository=tasks,
        prepared_inputs=prepared_inputs,
        artifact_store=store,
        repository=science,
    )
    analyzer.analyze(
        task_id=task.task_id,
        attempt_id="attempt_1",
        pose_content=pose_model(1),
    )

    interactions = science.list_interactions_for_pose(pose.pose_id)
    kinds = {interaction.kind for interaction in interactions}

    assert PoseInteractionKind.CONTACT in kinds
    assert PoseInteractionKind.HYDROPHOBIC in kinds
    assert PoseInteractionKind.HYDROGEN_BOND in kinds
    assert PoseInteractionKind.SALT_BRIDGE in kinds

    hydrogen_bond = next(
        item
        for item in interactions
        if item.kind is PoseInteractionKind.HYDROGEN_BOND
    )
    assert hydrogen_bond.receptor_residue_id == "A:LYS20"
    assert hydrogen_bond.metadata["protein_is_donor"] is True
    assert hydrogen_bond.metadata["donor_angle_degrees"] == pytest.approx(180.0)

    salt_bridge = next(
        item
        for item in interactions
        if item.kind is PoseInteractionKind.SALT_BRIDGE
    )
    assert salt_bridge.receptor_residue_id == "A:ASP30"
    assert salt_bridge.metadata["putative"] is True


def test_interaction_analysis_is_idempotent():
    store = MemoryArtifactStore()
    receptor_blob = store.put(receptor())
    prepared_inputs = PreparedInputs(
        PreparedReceptorBinding(
            prepared=PreparedReceptor(
                receptor_id="rec_1",
                preparation_id="rprep_1",
                prepared_receptor_id="prec_1",
            ),
            blob=receptor_blob,
        )
    )
    tasks = InMemoryTaskRepository()
    task = DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_id="plig_1",
        search_space_id="space_1",
    )
    tasks.register(task)
    science = InMemoryScientificResultRepository()
    pose = Pose(
        task_id=task.task_id,
        attempt_id="attempt_1",
        source_artifact_id="artifact_1",
        model_index=1,
        geometry_sha256="b" * 64,
    )
    science.register_pose(pose)
    analyzer = PdbqtPoseInteractionAnalyzer(
        task_repository=tasks,
        prepared_inputs=prepared_inputs,
        artifact_store=store,
        repository=science,
    )

    analyzer.analyze(
        task_id=task.task_id,
        attempt_id="attempt_1",
        pose_content=pose_model(1),
    )
    first = science.list_interactions_for_pose(pose.pose_id)
    analyzer.analyze(
        task_id=task.task_id,
        attempt_id="attempt_1",
        pose_content=pose_model(1),
    )

    assert science.list_interactions_for_pose(pose.pose_id) == first


def test_interaction_parser_rejects_invalid_atom_record():
    with pytest.raises(Exception, match="invalid PDBQT atom"):
        PdbqtInteractionParser().parse_receptor(
            b"ATOM      broken\n"
        )



def test_interaction_analyzer_is_noop_without_persisted_poses():
    store = MemoryArtifactStore()
    science = InMemoryScientificResultRepository()
    analyzer = PdbqtPoseInteractionAnalyzer(
        task_repository=InMemoryTaskRepository(),
        prepared_inputs=PreparedInputs(
            PreparedReceptorBinding(
                prepared=PreparedReceptor(
                    receptor_id="rec_1",
                    preparation_id="rprep_1",
                    prepared_receptor_id="prec_1",
                ),
                blob=store.put(receptor()),
            )
        ),
        artifact_store=store,
        repository=science,
    )

    analyzer.analyze(
        task_id="missing",
        attempt_id="missing",
        pose_content=pose_model(1),
    )

    assert science.list_poses_for_attempt("missing") == ()


def test_interaction_analyzer_rejects_missing_task():
    science = InMemoryScientificResultRepository()
    science.register_pose(
        Pose(
            task_id="missing",
            attempt_id="attempt_1",
            source_artifact_id="artifact_1",
            model_index=1,
            geometry_sha256="c" * 64,
        )
    )
    with pytest.raises(DomainValidationError, match="task not found"):
        PdbqtPoseInteractionAnalyzer(
            task_repository=InMemoryTaskRepository(),
            prepared_inputs=PreparedInputs(None),
            artifact_store=MemoryArtifactStore(),
            repository=science,
        ).analyze(
            task_id="missing",
            attempt_id="attempt_1",
            pose_content=pose_model(1),
        )


def test_interaction_analyzer_rejects_missing_prepared_receptor():
    tasks = InMemoryTaskRepository()
    task = DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prec_missing",
        prepared_ligand_id="plig_1",
        search_space_id="space_1",
    )
    tasks.register(task)
    science = InMemoryScientificResultRepository()
    science.register_pose(
        Pose(
            task_id=task.task_id,
            attempt_id="attempt_1",
            source_artifact_id="artifact_1",
            model_index=1,
            geometry_sha256="d" * 64,
        )
    )

    with pytest.raises(DomainValidationError, match="prepared receptor not found"):
        PdbqtPoseInteractionAnalyzer(
            task_repository=tasks,
            prepared_inputs=PreparedInputs(None),
            artifact_store=MemoryArtifactStore(),
            repository=science,
        ).analyze(
            task_id=task.task_id,
            attempt_id="attempt_1",
            pose_content=pose_model(1),
        )


def test_interaction_analyzer_rejects_pose_model_mismatch():
    store = MemoryArtifactStore()
    tasks = InMemoryTaskRepository()
    task = DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_id="plig_1",
        search_space_id="space_1",
    )
    tasks.register(task)
    science = InMemoryScientificResultRepository()
    science.register_pose(
        Pose(
            task_id=task.task_id,
            attempt_id="attempt_1",
            source_artifact_id="artifact_1",
            model_index=2,
            geometry_sha256="e" * 64,
        )
    )
    binding = PreparedReceptorBinding(
        prepared=PreparedReceptor(
            receptor_id="rec_1",
            preparation_id="rprep_1",
            prepared_receptor_id="prec_1",
        ),
        blob=store.put(receptor()),
    )

    with pytest.raises(DomainValidationError, match="does not match"):
        PdbqtPoseInteractionAnalyzer(
            task_repository=tasks,
            prepared_inputs=PreparedInputs(binding),
            artifact_store=store,
            repository=science,
        ).analyze(
            task_id=task.task_id,
            attempt_id="attempt_1",
            pose_content=pose_model(1),
        )


def test_interaction_parser_rejects_empty_and_unterminated_models():
    parser = PdbqtInteractionParser()
    with pytest.raises(DomainValidationError, match="no MODEL"):
        parser.parse_pose_models(b"ATOM      1\n")

    with pytest.raises(DomainValidationError, match="unterminated MODEL"):
        parser.parse_pose_models(
            b"MODEL 1\n"
            + atom(1, "C1", "UNL", "L", 1, 0, 0, 0, 0, "C")
        )

    with pytest.raises(DomainValidationError, match="empty MODEL"):
        parser.parse_pose_models(b"MODEL 1\nENDMDL\n")


def test_putative_salt_bridge_requires_conservative_ligand_ionic_atom():
    store = MemoryArtifactStore()
    receptor_blob = store.put(receptor())
    prepared_inputs = PreparedInputs(
        PreparedReceptorBinding(
            prepared=PreparedReceptor(
                receptor_id="rec_1",
                preparation_id="rprep_1",
                prepared_receptor_id="prec_1",
            ),
            blob=receptor_blob,
        )
    )
    tasks = InMemoryTaskRepository()
    task = DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_id="plig_1",
        search_space_id="space_1",
    )
    tasks.register(task)
    science = InMemoryScientificResultRepository()
    pose = Pose(
        task_id=task.task_id,
        attempt_id="attempt_1",
        source_artifact_id="artifact_1",
        model_index=1,
        geometry_sha256="f" * 64,
    )
    science.register_pose(pose)

    PdbqtPoseInteractionAnalyzer(
        task_repository=tasks,
        prepared_inputs=prepared_inputs,
        artifact_store=store,
        repository=science,
    ).analyze(
        task_id=task.task_id,
        attempt_id="attempt_1",
        pose_content=pose_model(1),
    )

    salt_residues = {
        item.receptor_residue_id
        for item in science.list_interactions_for_pose(pose.pose_id)
        if item.kind is PoseInteractionKind.SALT_BRIDGE
    }
    assert salt_residues == {"A:ASP30"}


def test_memory_repository_rejects_unknown_and_conflicting_interactions(monkeypatch):
    import moldock.domain.interaction as interaction_module

    repo = InMemoryScientificResultRepository()
    interaction = PoseInteraction(
        pose_id="missing",
        kind=PoseInteractionKind.CONTACT,
        receptor_chain_id="A",
        receptor_residue_name="THR",
        receptor_residue_number="315",
        receptor_atom_name="OG1",
        ligand_atom_name="N1",
        distance_angstrom=3.0,
        method="pdbqt_geometric_interactions",
        method_version="1",
    )
    with pytest.raises(DomainValidationError, match="unknown pose"):
        repo.register_interaction(interaction)

    pose = Pose(
        task_id="task_1",
        attempt_id="attempt_1",
        source_artifact_id="artifact_1",
        model_index=1,
        geometry_sha256="1" * 64,
    )
    repo.register_pose(pose)
    monkeypatch.setattr(
        interaction_module,
        "content_id",
        lambda prefix, value: f"{prefix}_forced_collision",
    )
    first = PoseInteraction(
        pose_id=pose.pose_id,
        kind=PoseInteractionKind.CONTACT,
        receptor_chain_id="A",
        receptor_residue_name="THR",
        receptor_residue_number="315",
        receptor_atom_name="OG1",
        ligand_atom_name="N1",
        distance_angstrom=3.0,
        method="pdbqt_geometric_interactions",
        method_version="1",
    )
    second = PoseInteraction(
        pose_id=pose.pose_id,
        kind=PoseInteractionKind.CONTACT,
        receptor_chain_id="A",
        receptor_residue_name="THR",
        receptor_residue_number="315",
        receptor_atom_name="OG1",
        ligand_atom_name="N1",
        distance_angstrom=3.5,
        method="pdbqt_geometric_interactions",
        method_version="1",
    )
    repo.register_interaction(first)
    repo.register_interaction(first)
    with pytest.raises(DomainValidationError, match="conflicting"):
        repo.register_interaction(second)
