from src.run_pipeline import run


def run_update() -> dict:
    run()
    return {"status": "completed"}
