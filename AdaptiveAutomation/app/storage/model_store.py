from models.state_predictor import ModelStore


def build_model_store(path: str = "/data/model.json") -> ModelStore:
    return ModelStore(path)
