"""ML lifecycle API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from dfat.api.dependencies import (
    get_artefact_repository,
    get_auto_retrainer,
    get_dataset_builder,
    get_experiment_tracker,
    get_ml_predictor,
    get_model_registry,
    get_model_trainer,
    require_permission,
    require_role,
)
from dfat.api.schemas.extension import (
    ExperimentResponse,
    MLPredictRequest,
    MLPredictResponse,
    MLRetrainResponse,
    MLTrainRequest,
    MLTrainResponse,
    TrainedModelResponse,
)
from dfat.database.models.user import UserORM
from dfat.database.repositories.artefact_repo import SQLAlchemyArtefactRepository
from dfat.ml.dataset_builder import EmptyTrainingDatasetError, MLDatasetBuilder
from dfat.ml.experiment_tracker import ExperimentNotFoundError, ExperimentTracker
from dfat.ml.model_registry import ModelRegistry
from dfat.ml.models import (
    AnomalyDetector,
    IOCPredictor,
    MalwareClassifier,
    ProcessSuspicionScorer,
)
from dfat.ml.predictor import MLPredictor
from dfat.ml.retrainer import AutoRetrainer
from dfat.ml.trainer import ModelTrainer, TrainingError

router = APIRouter(prefix="/ml", tags=["ML"])

_MODEL_CLASSES = {
    "MalwareClassifier": MalwareClassifier,
    "AnomalyDetector": AnomalyDetector,
    "ProcessSuspicionScorer": ProcessSuspicionScorer,
    "IOCPredictor": IOCPredictor,
}


def _to_model_response(model) -> TrainedModelResponse:
    return TrainedModelResponse(
        model_id=model.model_id,
        model_name=model.model_name,
        version=model.version,
        model_path=str(model.model_path),
        training_dataset=model.training_dataset,
        metrics=dict(model.metrics),
        hyperparameters=dict(model.hyperparameters),
        feature_names=list(model.feature_names),
        trained_at=model.trained_at,
    )


def _to_experiment_response(record) -> ExperimentResponse:
    return ExperimentResponse(
        experiment_id=record.experiment_id,
        model_name=record.model_name,
        dataset_name=record.dataset_name,
        status=record.status,
        hyperparameters=dict(record.hyperparameters),
        metrics=dict(record.metrics),
        started_at=record.started_at,
        completed_at=record.completed_at,
        duration_seconds=record.duration_seconds,
        artifact_paths=list(record.artifact_paths),
    )


@router.get("/models", response_model=list[TrainedModelResponse])
async def list_models(
    _: UserORM = Depends(require_permission("ml", "read")),
    registry: ModelRegistry = Depends(get_model_registry),
) -> list[TrainedModelResponse]:
    """List all registered trained models."""
    return [_to_model_response(item) for item in registry.list_models()]


@router.get("/models/{model_name}/latest", response_model=TrainedModelResponse)
async def get_latest_model(
    model_name: str,
    _: UserORM = Depends(require_permission("ml", "read")),
    registry: ModelRegistry = Depends(get_model_registry),
) -> TrainedModelResponse:
    """Return the latest version of a trained model."""
    model = registry.get_latest(model_name)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No trained model found for {model_name!r}",
        )
    return _to_model_response(model)


@router.post("/train", response_model=MLTrainResponse, status_code=status.HTTP_200_OK)
async def train_model(
    body: MLTrainRequest,
    _: UserORM = Depends(require_role(["admin"])),
    builder: MLDatasetBuilder = Depends(get_dataset_builder),
    trainer: ModelTrainer = Depends(get_model_trainer),
    registry: ModelRegistry = Depends(get_model_registry),
) -> MLTrainResponse:
    """Trigger manual model training (admin only)."""
    model_class = _MODEL_CLASSES.get(body.model_name)
    if model_class is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown model name: {body.model_name}",
        )
    try:
        training_data = await builder.build_training_dataset(
            body.model_name,
            source_datasets=body.source_datasets,
        )
        trained = await trainer.train(
            model_class,
            training_data,
            hyperparameters=body.hyperparameters,
        )
        registry.register(trained)
    except EmptyTrainingDatasetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TrainingError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return MLTrainResponse(
        model_name=trained.model_name,
        model_id=trained.model_id,
        version=trained.version,
        metrics=dict(trained.metrics),
    )


@router.post("/retrain", response_model=MLRetrainResponse)
async def retrain_models(
    _: UserORM = Depends(require_role(["admin"])),
    retrainer: AutoRetrainer = Depends(get_auto_retrainer),
) -> MLRetrainResponse:
    """Run the auto-retrain threshold check (admin only)."""
    retrained = await retrainer.check_and_retrain()
    return MLRetrainResponse(retrained_models=retrained)


@router.get("/experiments", response_model=list[ExperimentResponse])
async def list_experiments(
    model_name: str | None = Query(default=None),
    _: UserORM = Depends(require_permission("ml", "read")),
    tracker: ExperimentTracker = Depends(get_experiment_tracker),
) -> list[ExperimentResponse]:
    """List ML experiment records."""
    return [_to_experiment_response(item) for item in tracker.list_experiments(model_name)]


@router.get("/experiments/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(
    experiment_id: str,
    _: UserORM = Depends(require_permission("ml", "read")),
    tracker: ExperimentTracker = Depends(get_experiment_tracker),
) -> ExperimentResponse:
    """Return a single experiment record."""
    try:
        record = tracker.get_experiment(experiment_id)
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_experiment_response(record)


@router.post("/predict", response_model=MLPredictResponse)
async def predict_artefacts(
    body: MLPredictRequest,
    _: UserORM = Depends(require_permission("ml", "read")),
    predictor: MLPredictor = Depends(get_ml_predictor),
    artefact_repo: SQLAlchemyArtefactRepository = Depends(get_artefact_repository),
) -> MLPredictResponse:
    """Run ML inference for one or more artefacts."""
    predictions = []
    for artefact_id in body.artefact_ids:
        artefact = await artefact_repo.get_by_artefact_id(artefact_id)
        if artefact is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Artefact not found: {artefact_id}",
            )
        try:
            prediction = await predictor.predict(body.model_name, artefact)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        predictions.append(prediction)
    return MLPredictResponse(model_name=body.model_name, predictions=predictions)
