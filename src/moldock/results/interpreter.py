from __future__ import annotations

from typing import Protocol, runtime_checkable

from moldock.domain import ArtifactMetadata
from moldock.storage import ArtifactStore

from .analysis import PoseScientificAnalyzer
from .interactions import PoseInteractionAnalyzer
from .parser import VinaResultParser
from .repository import ScientificResultRepository


@runtime_checkable
class ScientificResultInterpreter(Protocol):
    def interpret(
        self,
        *,
        task_id: str,
        artifact: ArtifactMetadata,
    ) -> None: ...


class NullScientificResultInterpreter:
    def interpret(
        self,
        *,
        task_id: str,
        artifact: ArtifactMetadata,
    ) -> None:
        return None


class VinaResultInterpreter:
    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        repository: ScientificResultRepository,
        method_version: str,
        parser: VinaResultParser | None = None,
        analyzer: PoseScientificAnalyzer | None = None,
        interaction_analyzer: PoseInteractionAnalyzer | None = None,
    ) -> None:
        self._store = artifact_store
        self._repository = repository
        self._method_version = method_version
        self._parser = parser or VinaResultParser()
        self._analyzer = analyzer or PoseScientificAnalyzer(
            repository=repository
        )
        self._interaction_analyzer = interaction_analyzer

    def interpret(
        self,
        *,
        task_id: str,
        artifact: ArtifactMetadata,
    ) -> None:
        if artifact.kind != "docking_pose":
            return

        content = self._store.read(artifact.uri)
        parsed = self._parser.parse(
            task_id=task_id,
            attempt_id=artifact.producer_attempt_id,
            source_artifact_id=artifact.artifact_id,
            content=content,
            method_version=self._method_version,
        )

        for pose in parsed.poses:
            self._repository.register_pose(pose)
        for score in parsed.scores:
            self._repository.register_score(score)
        for ranking in parsed.rankings:
            self._repository.register_ranking(ranking)

        self._analyzer.analyze(
            attempt_id=artifact.producer_attempt_id,
            content=content,
        )
        if self._interaction_analyzer is not None:
            self._interaction_analyzer.analyze(
                task_id=task_id,
                attempt_id=artifact.producer_attempt_id,
                pose_content=content,
            )
