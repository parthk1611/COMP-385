"""Publish current export evidence without rewriting historical experiment reports."""
from .common import OUTPUT, alert_policy, read_json, write_json


def publish():
    evidence = {
        "model_metadata": read_json(OUTPUT / "model_metadata.json"),
        "verification": read_json(OUTPUT / "verification.json"),
        "training": read_json(OUTPUT / "training.json"),
        "policy": alert_policy(),
        "performance": None,
        "note": "No global reserved-year evaluation recomputed; historical experiment reports are unchanged.",
    }
    write_json(OUTPUT / "demo_evidence.json", evidence)
    print(f"Published current demo evidence to {OUTPUT / 'demo_evidence.json'}")


if __name__ == "__main__":
    publish()
