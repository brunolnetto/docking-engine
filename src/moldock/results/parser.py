from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from moldock.domain import Pose, PoseRanking, PoseScore, ScoreKind


_MODEL = re.compile(rb"^MODEL\s+(\d+)\s*$")
_RESULT_PREFIX = b"REMARK VINA RESULT:"
_RESULT = re.compile(
    rb"^REMARK VINA RESULT:\s+"
    rb"([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)\s+"
    rb"([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)\s+"
    rb"([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)\s*$"
)


class VinaResultParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedScientificResult:
    poses: tuple[Pose, ...]
    scores: tuple[PoseScore, ...]
    rankings: tuple[PoseRanking, ...]


class VinaResultParser:
    def parse(
        self,
        *,
        task_id: str,
        attempt_id: str,
        source_artifact_id: str,
        content: bytes,
        method_version: str,
    ) -> ParsedScientificResult:
        blocks = self._model_blocks(content)
        if not blocks:
            raise VinaResultParseError("no MODEL blocks found")

        poses: list[Pose] = []
        scores: list[PoseScore] = []
        rankings: list[PoseRanking] = []

        for rank, (model_index, block) in enumerate(blocks, start=1):
            result_lines = [
                line
                for line in block.splitlines()
                if line.startswith(_RESULT_PREFIX)
            ]
            if not result_lines:
                raise VinaResultParseError(
                    f"MODEL {model_index} missing VINA RESULT"
                )
            if len(result_lines) > 1:
                raise VinaResultParseError(
                    f"MODEL {model_index} has multiple VINA RESULT records"
                )

            match = _RESULT.match(result_lines[0])
            if match is None:
                raise VinaResultParseError(
                    f"MODEL {model_index} has invalid VINA RESULT"
                )

            affinity, rmsd_lb, rmsd_ub = (
                float(match.group(index)) for index in (1, 2, 3)
            )

            geometry = self._canonical_geometry(block)
            pose = Pose(
                task_id=task_id,
                attempt_id=attempt_id,
                source_artifact_id=source_artifact_id,
                model_index=model_index,
                geometry_sha256=hashlib.sha256(geometry).hexdigest(),
            )
            poses.append(pose)
            scores.append(
                PoseScore(
                    pose_id=pose.pose_id,
                    kind=ScoreKind.VINA_AFFINITY,
                    value=affinity,
                    unit="kcal/mol",
                    method="vina",
                    method_version=method_version,
                    metadata={
                        "rmsd_lb": rmsd_lb,
                        "rmsd_ub": rmsd_ub,
                    },
                )
            )
            rankings.append(
                PoseRanking(
                    pose_id=pose.pose_id,
                    rank=rank,
                    method=ScoreKind.VINA_AFFINITY.value,
                )
            )

        return ParsedScientificResult(
            poses=tuple(poses),
            scores=tuple(scores),
            rankings=tuple(rankings),
        )

    @staticmethod
    def _canonical_geometry(block: bytes) -> bytes:
        geometry_lines = [
            line.rstrip(b"\r\n")
            for line in block.splitlines()
            if line.startswith((b"ATOM", b"HETATM"))
        ]
        return b"\n".join(geometry_lines)

    def _model_blocks(self, content: bytes) -> list[tuple[int, bytes]]:
        blocks: list[tuple[int, bytes]] = []
        current_index: int | None = None
        current_lines: list[bytes] = []

        for line in content.splitlines(keepends=True):
            stripped = line.rstrip(b"\r\n")
            model = _MODEL.match(stripped)

            if model is not None:
                if current_index is not None:
                    raise VinaResultParseError(
                        f"unterminated MODEL {current_index}"
                    )
                current_index = int(model.group(1))
                current_lines = [line]
                continue

            if stripped == b"ENDMDL":
                if current_index is None:
                    continue
                current_lines.append(line)
                blocks.append((current_index, b"".join(current_lines)))
                current_index = None
                current_lines = []
                continue

            if current_index is not None:
                current_lines.append(line)

        if current_index is not None:
            raise VinaResultParseError(f"unterminated MODEL {current_index}")

        return blocks
