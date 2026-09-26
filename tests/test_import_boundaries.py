def test_repository_and_execution_packages_import_before_pipeline():
    import importlib
    import sys

    for name in (
        "moldock.pipeline",
        "moldock.pipeline.offline",
        "moldock.repositories",
        "moldock.execution",
    ):
        sys.modules.pop(name, None)

    repositories = importlib.import_module("moldock.repositories")
    execution = importlib.import_module("moldock.execution")
    pipeline = importlib.import_module("moldock.pipeline")

    assert repositories.RunManifestRepository is not None
    assert execution.Worker is not None
    assert pipeline.RunManifest is not None
