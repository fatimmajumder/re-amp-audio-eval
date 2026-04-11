from __future__ import annotations

import json
from pathlib import Path

from .schemas import DatasetAvailability, PublicDataset

PUBLIC_DATASET_REGISTRY = [
    PublicDataset(
        dataset_id="mini_speech_commands",
        name="Mini Speech Commands",
        domain="speech",
        provider="TensorFlow",
        description="Compact keyword-spotting dataset that is ideal for smoke tests, CI checks, and local demos.",
        source_url="https://www.tensorflow.org/tutorials/audio/simple_audio",
        download_url="https://storage.googleapis.com/download.tensorflow.org/data/mini_speech_commands.zip",
        license_name="CC BY 4.0",
        access_mode="direct",
        download_size="~182 MB",
        tasks=["keyword spotting", "speech robustness", "latency smoke tests"],
        recommended_benchmarks=["audio_robustness_suite", "dialogue_and_foley"],
        notes=[
            "Best quick-start choice for validating the downloader and end-to-end evaluation loop.",
            "Pairs well with noisy-speech and overlap scenarios for RE-AMP demos.",
        ],
    ),
    PublicDataset(
        dataset_id="librispeech_test_clean",
        name="LibriSpeech Test-Clean",
        domain="speech",
        provider="OpenSLR",
        description="Clean read-speech benchmark commonly used for ASR and speech-generation evaluations.",
        source_url="https://www.openslr.org/12",
        download_url="https://www.openslr.org/resources/12/test-clean.tar.gz",
        license_name="CC BY 4.0",
        access_mode="direct",
        download_size="~346 MB",
        tasks=["speech generation", "voice consistency", "transcript-conditioned evaluation"],
        recommended_benchmarks=["dialogue_and_foley", "audio_robustness_suite"],
        notes=[
            "Useful when you want longer-form clean speech instead of command words.",
            "Good fit for background-noise, reverb, and microphone-distance stressors.",
        ],
    ),
    PublicDataset(
        dataset_id="nsynth",
        name="NSynth",
        domain="music",
        provider="Magenta",
        description="Large-scale musical note dataset for testing timbre stability, pitch control, and synthesis artifacts.",
        source_url="https://magenta.tensorflow.org/datasets/nsynth",
        download_url="https://storage.googleapis.com/magentadata/datasets/nsynth/nsynth-test.jsonwav.tar.gz",
        license_name="CC BY 4.0",
        access_mode="direct",
        download_size="~3.5 GB",
        tasks=["timbre transfer", "pitch control", "instrument synthesis"],
        recommended_benchmarks=["studio_mix_stability"],
        notes=[
            "Heavy download, but excellent for pitch drift and transient artifact evaluation.",
            "Prefer the test split when validating pipelines locally.",
        ],
    ),
    PublicDataset(
        dataset_id="maestro",
        name="MAESTRO",
        domain="music",
        provider="Magenta",
        description="Aligned piano performances with MIDI and audio, useful for long-form timing and dynamic-range checks.",
        source_url="https://magenta.tensorflow.org/datasets/maestro",
        download_url="https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0.zip",
        license_name="CC BY-NC 4.0",
        access_mode="direct",
        download_size="~131 GB",
        tasks=["music generation", "timing stability", "expressive dynamics"],
        recommended_benchmarks=["studio_mix_stability"],
        notes=[
            "Best suited for offline evaluations or subset extraction because of its size.",
            "Strong benchmark for tempo variation and long-sequence coherence.",
        ],
    ),
    PublicDataset(
        dataset_id="fsd50k",
        name="FSD50K",
        domain="sound-events",
        provider="Freesound",
        description="Large open sound-event corpus for robustness testing across environmental and household audio.",
        source_url="https://annotator.freesound.org/fsd/release/FSD50K/",
        download_url="https://zenodo.org/records/4060432",
        license_name="CC BY 4.0 and CC BY-NC",
        access_mode="direct",
        download_size="~6.5 GB",
        tasks=["sound-event robustness", "ambient contamination", "non-speech failure analysis"],
        recommended_benchmarks=["audio_robustness_suite", "dialogue_and_foley"],
        notes=[
            "Good public source for adverse-condition clips that are still easy to cite and share.",
            "Useful when you need environmental audio rather than speech or music.",
        ],
    ),
    PublicDataset(
        dataset_id="musdb18_hq",
        name="MUSDB18-HQ",
        domain="music",
        provider="SIGSEP",
        description="Multitrack music benchmark used for source separation and mix translation analysis.",
        source_url="https://sigsep.github.io/datasets/musdb.html",
        download_url="https://sigsep.github.io/datasets/musdb.html",
        license_name="Research-only",
        access_mode="request",
        download_size="~22 GB",
        tasks=["source separation", "mix robustness", "mastering QA"],
        recommended_benchmarks=["studio_mix_stability"],
        notes=[
            "Access is controlled, so RE-AMP treats it as a documented source rather than a one-click download.",
            "Strong fit for clipping, codec, and stereo-image evaluation workflows.",
        ],
    ),
    PublicDataset(
        dataset_id="audioset",
        name="AudioSet",
        domain="sound-events",
        provider="Google",
        description="Massive ontology-driven audio-event index built from YouTube segments.",
        source_url="https://research.google.com/audioset/",
        download_url="https://research.google.com/audioset/",
        license_name="YouTube terms plus AudioSet annotations",
        access_mode="streaming",
        download_size="Metadata index",
        tasks=["audio tagging", "long-tail event discovery", "retrieval-conditioned testing"],
        recommended_benchmarks=["audio_robustness_suite"],
        notes=[
            "Best consumed as metadata plus downloaded YouTube segments rather than a single archive.",
            "Useful for future large-scale red-team sampling even if local smoke tests use smaller datasets.",
        ],
    ),
]


def build_public_datasets(root: Path) -> list[PublicDataset]:
    datasets: list[PublicDataset] = []
    for dataset in PUBLIC_DATASET_REGISTRY:
        availability = _load_dataset_availability(root, dataset.dataset_id)
        datasets.append(dataset.model_copy(update={"availability": availability}, deep=True))
    return datasets


def get_public_dataset(root: Path, dataset_id: str) -> PublicDataset | None:
    for dataset in build_public_datasets(root):
        if dataset.dataset_id == dataset_id:
            return dataset
    return None


def _load_dataset_availability(root: Path, dataset_id: str) -> DatasetAvailability:
    manifest_path = root / dataset_id / "manifest.json"
    if not manifest_path.exists():
        return DatasetAvailability()

    payload = json.loads(manifest_path.read_text())
    return DatasetAvailability(
        status="downloaded",
        local_path=payload.get("local_path"),
        manifest_path=str(manifest_path),
        downloaded_at=payload.get("downloaded_at"),
        audio_file_count=int(payload.get("audio_file_count", 0)),
        sample_files=list(payload.get("sample_files", [])),
    )
