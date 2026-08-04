import argparse
import asyncio
import os
import sys

# Ensure backend directory is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.evaluation.datasets.dataset_loader import DatasetLoader
from app.evaluation.runners.ragas_provider import RagasProvider


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline evaluation on a dataset.")
    parser.add_argument("--dataset", required=True, help="Path to dataset file (JSON, JSONL, YAML, CSV).")
    parser.add_argument("--dataset-id", default="cli-dataset", help="Dataset ID for versioning.")
    parser.add_argument("--version", default="1.0.0", help="Dataset version.")
    parser.add_argument("--mock", action="store_true", help="Run in mock/stub mode without LLM calls.")
    parser.add_argument("--metrics", default="faithfulness,answer_relevancy", help="Comma-separated metrics to run.")
    args = parser.parse_args()

    loader = DatasetLoader()
    try:
        dataset = loader.load_dataset(args.dataset, args.dataset_id, args.version)
    except Exception as e:
        print(f"Error loading dataset: {e}")
        sys.exit(1)

    print(f"Loaded dataset '{dataset.dataset_id}' (v{dataset.version}) with {dataset.sample_count} samples.")
    print(f"Dataset Hash: {dataset.hash}")

    provider = RagasProvider()
    metrics_list = [m.strip() for m in args.metrics.split(",") if m.strip()]

    print(f"Evaluating samples using Ragas on metrics: {metrics_list}...")
    results = await provider.evaluate(dataset.samples, metrics_list, mock=args.mock)

    # Print summary of results
    print("\n" + "=" * 40)
    print("EVALUATION RESULT SUMMARY")
    print("=" * 40)
    
    # Calculate averages
    averages = {}
    for r in results:
        for m in r.metrics:
            averages[m.name] = averages.get(m.name, []) + [m.score]

    for name, scores in averages.items():
        avg = sum(scores) / len(scores) if scores else 0.0
        print(f"{name}: {avg:.3f}")
    print("=" * 40)


if __name__ == "__main__":
    asyncio.run(main())
