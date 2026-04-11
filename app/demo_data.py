from __future__ import annotations

from .schemas import (
    BenchmarkScenario,
    BenchmarkTemplate,
    CatalogResponse,
    ModelCard,
    PublicDataset,
    RunCreate,
    WorkspaceRecord,
)

SCENARIO_LIBRARY = [
    BenchmarkScenario(
        name="background_noise",
        difficulty="medium",
        category="contamination",
        description="Tests resilience to street noise, HVAC bleed, and room tone shifts.",
        tags=["noise", "contamination", "mix"],
        weight=1.0,
    ),
    BenchmarkScenario(
        name="reverb_shift",
        difficulty="medium",
        category="acoustics",
        description="Checks whether generation quality holds across different room reflections.",
        tags=["impulse-response", "room-sim"],
        weight=1.0,
    ),
    BenchmarkScenario(
        name="codec_degradation",
        difficulty="hard",
        category="compression",
        description="Measures degradation after export and platform compression steps.",
        tags=["mp3", "aac", "lossy"],
        weight=1.2,
    ),
    BenchmarkScenario(
        name="transient_clipping",
        difficulty="hard",
        category="artifacts",
        description="Flags brittle peaks, clipping, and drum transient smearing.",
        tags=["peaks", "mastering"],
        weight=1.1,
    ),
    BenchmarkScenario(
        name="tempo_variation",
        difficulty="easy",
        category="temporal",
        description="Validates prompt adherence when tempo or groove changes mid-sequence.",
        tags=["tempo", "structure"],
        weight=0.9,
    ),
    BenchmarkScenario(
        name="speaker_overlap",
        difficulty="hard",
        category="separation",
        description="Stress test for dialogue overlap and source separation quality.",
        tags=["dialogue", "overlap", "speech"],
        weight=1.15,
    ),
    BenchmarkScenario(
        name="microphone_distance",
        difficulty="medium",
        category="spatial",
        description="Compares tonal stability across near-field and far-field capture styles.",
        tags=["spatial", "perspective"],
        weight=1.0,
    ),
    BenchmarkScenario(
        name="pitch_drift",
        difficulty="medium",
        category="tonality",
        description="Checks for tuning drift during long-form harmonic generation.",
        tags=["pitch", "harmonics"],
        weight=1.05,
    ),
]

BENCHMARK_TEMPLATES = [
    BenchmarkTemplate(
        benchmark_name="audio_robustness_suite",
        dataset_name="synthetic-acoustic-suite",
        description="Balanced benchmark for acoustic shifts, noise, compression, and timing stability.",
        default_scenarios=[
            "background_noise",
            "reverb_shift",
            "codec_degradation",
            "tempo_variation",
        ],
        target_metrics=["aggregate robustness", "artifact rate", "latency"],
    ),
    BenchmarkTemplate(
        benchmark_name="studio_mix_stability",
        dataset_name="multitrack-room-shifts",
        description="Focuses on mix translation, clipping risk, and mastering resilience.",
        default_scenarios=[
            "transient_clipping",
            "codec_degradation",
            "microphone_distance",
            "pitch_drift",
        ],
        target_metrics=["similarity", "artifact rate", "failure rate"],
    ),
    BenchmarkTemplate(
        benchmark_name="dialogue_and_foley",
        dataset_name="foley-scene-slices",
        description="Evaluates speech overlap, ambience changes, and event timing.",
        default_scenarios=[
            "speaker_overlap",
            "background_noise",
            "tempo_variation",
            "microphone_distance",
        ],
        target_metrics=["speech clarity", "timing", "robustness"],
    ),
]

MODEL_CARDS = [
    ModelCard(
        name="reamp-studio-alpha",
        family="diffusion-audio",
        provider="RE-AMP Labs",
        description="Fast baseline tuned for prompt adherence and short-form clips.",
        strengths=["low latency", "clean transient handling", "predictable prompt following"],
    ),
    ModelCard(
        name="reamp-studio-beta",
        family="transformer-audio",
        provider="RE-AMP Labs",
        description="Higher-capacity candidate aimed at spatial realism and long-form structure.",
        strengths=["spatial texture", "narrative continuity", "stereo image stability"],
    ),
    ModelCard(
        name="audioforge-ensemble",
        family="hybrid-ensemble",
        provider="AudioForge",
        description="External benchmark target with stronger mastering polish but slower inference.",
        strengths=["artifact resistance", "export quality", "compression resilience"],
    ),
]


def build_catalog(public_datasets: list[PublicDataset] | None = None) -> CatalogResponse:
    return CatalogResponse(
        benchmark_templates=BENCHMARK_TEMPLATES,
        models=MODEL_CARDS,
        scenario_library=SCENARIO_LIBRARY,
        public_datasets=public_datasets or [],
    )


def resolve_scenarios(payload: RunCreate) -> list[BenchmarkScenario]:
    library = {scenario.name: scenario for scenario in SCENARIO_LIBRARY}
    template_lookup = {template.benchmark_name: template for template in BENCHMARK_TEMPLATES}

    requested = payload.scenarios
    if not requested:
        template = template_lookup.get(payload.benchmark_name)
        if template:
            requested = [library[name] for name in template.default_scenarios if name in library]

    resolved: list[BenchmarkScenario] = []
    for scenario in requested:
        base = library.get(scenario.name)
        if not base:
            resolved.append(scenario)
            continue

        resolved.append(
            BenchmarkScenario(
                name=base.name,
                difficulty=scenario.difficulty or base.difficulty,
                modality=scenario.modality or base.modality,
                category=scenario.category or base.category,
                description=scenario.description or base.description,
                tags=scenario.tags or base.tags,
                weight=scenario.weight if scenario.weight != 1.0 else base.weight,
            )
        )

    return resolved


def resolve_dataset_name(payload: RunCreate) -> str:
    if payload.dataset_name:
        return payload.dataset_name

    template_lookup = {template.benchmark_name: template for template in BENCHMARK_TEMPLATES}
    template = template_lookup.get(payload.benchmark_name)
    return template.dataset_name if template else "synthetic-acoustic-suite"


def build_seed_workspaces() -> list[WorkspaceRecord]:
    return [
        WorkspaceRecord(
            workspace_id="core-audio-lab",
            name="Core Audio Lab",
            description="Primary sandbox for day-to-day robustness sweeps and dashboard QA.",
            owner="Fatim Majumder",
            focus_areas=["regression triage", "prompt adherence", "artifact drift"],
            default_benchmark="audio_robustness_suite",
            default_model="reamp-studio-alpha",
            dataset_preferences=["mini_speech_commands", "librispeech_test_clean"],
        ),
        WorkspaceRecord(
            workspace_id="music-evaluation",
            name="Music Evaluation",
            description="Long-form mix and mastering workspace tuned for music-generation stress tests.",
            owner="Fatim Majumder",
            focus_areas=["stereo image", "mastering polish", "tempo drift"],
            default_benchmark="studio_mix_stability",
            default_model="reamp-studio-beta",
            dataset_preferences=["maestro", "musdb18_hq"],
        ),
        WorkspaceRecord(
            workspace_id="speech-red-team",
            name="Speech Red Team",
            description="Speech-first lane for overlap, noise contamination, and command robustness checks.",
            owner="Fatim Majumder",
            focus_areas=["speaker overlap", "noisy speech", "keyword failures"],
            default_benchmark="dialogue_and_foley",
            default_model="audioforge-ensemble",
            dataset_preferences=["mini_speech_commands", "fsd50k", "audioset"],
        ),
    ]


def build_seed_payloads() -> list[RunCreate]:
    return [
        RunCreate(
            benchmark_name="audio_robustness_suite",
            model_name="reamp-studio-alpha",
            dataset_name="Mini Speech Commands",
            public_dataset_id="mini_speech_commands",
            workspace_id="core-audio-lab",
            seed=7,
            notes="Seeded baseline for dashboard exploration.",
        ),
        RunCreate(
            benchmark_name="studio_mix_stability",
            model_name="reamp-studio-beta",
            dataset_name="MAESTRO",
            public_dataset_id="maestro",
            workspace_id="music-evaluation",
            seed=11,
            notes="Higher-capacity candidate run focused on mastering robustness.",
        ),
        RunCreate(
            benchmark_name="dialogue_and_foley",
            model_name="audioforge-ensemble",
            dataset_name="FSD50K",
            public_dataset_id="fsd50k",
            workspace_id="speech-red-team",
            seed=19,
            notes="External comparison model with stronger artifact control.",
        ),
    ]
