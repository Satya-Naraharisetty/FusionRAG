import csv
import hashlib
import json
import os
import random

import yaml

from app.evaluation.domain.models import EvaluationDataset, EvaluationSample


class DatasetLoader:
    """
    Dataset Loader to parse, validate, hash, sample, and split evaluation datasets.
    Supports JSON, JSONL, CSV, and YAML formats.
    """

    def load_dataset(self, file_path: str, dataset_id: str, version: str, description: str | None = None) -> EvaluationDataset:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Dataset file not found: {file_path}")

        _, ext = os.path.splitext(file_path.lower())
        raw_samples = []

        if ext == ".json":
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    raw_samples = data
                elif isinstance(data, dict) and "samples" in data:
                    raw_samples = data["samples"]
                    if not description and "description" in data:
                        description = data["description"]
                else:
                    raise ValueError("JSON dataset must be a list of samples or a dict with a 'samples' key.")

        elif ext == ".jsonl":
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        raw_samples.append(json.loads(line))

        elif ext in (".yaml", ".yml"):
            with open(file_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, list):
                    raw_samples = data
                elif isinstance(data, dict) and "samples" in data:
                    raw_samples = data["samples"]
                    if not description and "description" in data:
                        description = data["description"]
                else:
                    raise ValueError("YAML dataset must be a list of samples or a dict with a 'samples' key.")

        elif ext == ".csv":
            with open(file_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Parse CSV fields into appropriate structures
                    sample_dict = dict(row)
                    
                    # Convert list-like strings
                    for list_field in ["ground_truth_context", "expected_tools", "expected_citations", "expected_documents"]:
                        if sample_dict.get(list_field):
                            try:
                                val = json.loads(sample_dict[list_field])
                                if isinstance(val, list):
                                    sample_dict[list_field] = val
                                else:
                                    sample_dict[list_field] = [str(val)]
                            except Exception:
                                sample_dict[list_field] = [x.strip() for x in sample_dict[list_field].split(",") if x.strip()]

                    # Convert boolean fields
                    for bool_field in ["retrieval_required", "tools_required", "conversation_required"]:
                        if bool_field in sample_dict:
                            sample_dict[bool_field] = sample_dict[bool_field].lower() in ("true", "1", "yes")

                    # Parse conversation history
                    if sample_dict.get("conversation_history"):
                        try:
                            sample_dict["conversation_history"] = json.loads(sample_dict["conversation_history"])
                        except Exception:
                            sample_dict["conversation_history"] = []

                    # Parse metadata
                    if sample_dict.get("metadata"):
                        try:
                            sample_dict["metadata"] = json.loads(sample_dict["metadata"])
                        except Exception:
                            sample_dict["metadata"] = {}

                    raw_samples.append(sample_dict)

        else:
            raise ValueError(f"Unsupported file format: {ext}. Supported formats: JSON, JSONL, YAML, CSV")

        # Parse and validate samples
        samples = []
        for i, raw in enumerate(raw_samples):
            # Guarantee ID
            if "id" not in raw or not raw["id"]:
                raw["id"] = f"{dataset_id}-{version}-{i}"
            
            # Basic validation
            if "question" not in raw or not raw["question"]:
                raise ValueError(f"Sample at index {i} is missing required 'question' field.")

            sample = EvaluationSample(**raw)
            samples.append(sample)

        # Compute dataset hash based on canonical samples content
        dataset_hash = self.compute_hash(samples)

        return EvaluationDataset(
            dataset_id=dataset_id,
            version=version,
            hash=dataset_hash,
            sample_count=len(samples),
            description=description,
            samples=samples
        )

    def compute_hash(self, samples: list[EvaluationSample]) -> str:
        """
        Compute a stable SHA256 hash of the list of samples to track versioning changes.
        """
        hasher = hashlib.sha256()
        for sample in sorted(samples, key=lambda s: s.id):
            sample_str = f"{sample.id}:{sample.question}:{sample.expected_answer or ''}"
            hasher.update(sample_str.encode("utf-8"))
        return hasher.hexdigest()

    def validate_dataset(self, dataset: EvaluationDataset) -> bool:
        """
        Run schema and content consistency checks on the dataset.
        """
        if not dataset.dataset_id or not dataset.version:
            return False
        if len(dataset.samples) != dataset.sample_count:
            return False
        for s in dataset.samples:
            if not s.id or not s.question:
                return False
        return True

    def split_train_test(self, dataset: EvaluationDataset, test_size: float = 0.2, seed: int = 42) -> tuple[EvaluationDataset, EvaluationDataset]:
        """
        Split a dataset into train and test datasets.
        """
        if not (0.0 < test_size < 1.0):
            raise ValueError("test_size must be between 0.0 and 1.0")

        random.seed(seed)
        shuffled = list(dataset.samples)
        random.shuffle(shuffled)

        split_idx = int(len(shuffled) * (1.0 - test_size))
        train_samples = shuffled[:split_idx]
        test_samples = shuffled[split_idx:]

        train_ds = EvaluationDataset(
            dataset_id=f"{dataset.dataset_id}-train",
            version=dataset.version,
            hash=self.compute_hash(train_samples),
            sample_count=len(train_samples),
            description=f"Train split of {dataset.dataset_id}",
            samples=train_samples
        )

        test_ds = EvaluationDataset(
            dataset_id=f"{dataset.dataset_id}-test",
            version=dataset.version,
            hash=self.compute_hash(test_samples),
            sample_count=len(test_samples),
            description=f"Test split of {dataset.dataset_id}",
            samples=test_samples
        )

        return train_ds, test_ds

    def sampling(self, dataset: EvaluationDataset, n: int, seed: int = 42) -> EvaluationDataset:
        """
        Return a subset of n random samples.
        """
        if n >= len(dataset.samples):
            return dataset

        random.seed(seed)
        sampled_samples = random.sample(dataset.samples, n)

        return EvaluationDataset(
            dataset_id=f"{dataset.dataset_id}-sample-{n}",
            version=dataset.version,
            hash=self.compute_hash(sampled_samples),
            sample_count=len(sampled_samples),
            description=f"Sampled subset of size {n} from {dataset.dataset_id}",
            samples=sampled_samples
        )

    def filtering(
        self,
        dataset: EvaluationDataset,
        difficulty: str | None = None,
        tags: list[str] | None = None,
        topic: str | None = None,
        retrieval_required: bool | None = None,
        tools_required: bool | None = None,
        conversation_required: bool | None = None
    ) -> EvaluationDataset:
        """
        Filter samples by difficulty, tags, topic, and capability flags.
        """
        filtered_samples = []
        for s in dataset.samples:
            if difficulty and s.difficulty != difficulty:
                continue
            if topic and s.topic != topic:
                continue
            if retrieval_required is not None and s.retrieval_required != retrieval_required:
                continue
            if tools_required is not None and s.tools_required != tools_required:
                continue
            if conversation_required is not None and s.conversation_required != conversation_required:
                continue
            if tags:
                sample_tags = s.metadata.get("tags", [])
                if not any(t in sample_tags for t in tags):
                    continue
            filtered_samples.append(s)

        return EvaluationDataset(
            dataset_id=f"{dataset.dataset_id}-filtered",
            version=dataset.version,
            hash=self.compute_hash(filtered_samples),
            sample_count=len(filtered_samples),
            description=f"Filtered subset of {dataset.dataset_id}",
            samples=filtered_samples
        )
