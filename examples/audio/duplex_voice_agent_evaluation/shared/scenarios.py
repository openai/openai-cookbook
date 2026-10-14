"""Portable, typed scenario contract shared by every evaluation module."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from shared.artifacts import validate_artifact_id

ArtifactId = Annotated[str, AfterValidator(validate_artifact_id)]

AudioCondition = Literal[
    "clean",
    "noisy",
    "telephony",
    "background_speech",
    "echo",
    "packet_loss",
    "realistic",
]
InteractionMode = Literal["single_turn", "multi_turn"]
AudioSource = Literal["synthetic", "recorded"]
DelegationExpectation = Literal["required", "forbidden", "optional"]


class Recording(BaseModel):
    """A reusable caller recording; ``ScenarioInput.text`` is its reference."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    path: Path
    condition: AudioCondition = "clean"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationHistoryItem(BaseModel):
    """One prior caller-visible text conversation item for session hydration."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    text: str = Field(min_length=1)


class ConversationContext(BaseModel):
    """Authorized prior conversation context, separate from evaluator expectations."""

    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    history: list[ConversationHistoryItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_content(self) -> ConversationContext:
        if not self.summary.strip() and not self.history:
            raise ValueError("conversation context requires a summary or prior history")
        return self


class ScenarioInput(BaseModel):
    """The intended user request, independent of how audio is produced."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    recordings: list[Recording] = Field(default_factory=list)
    context: ConversationContext | None = None


class ApplicationContext(BaseModel):
    """Authorized per-scenario application state."""

    model_config = ConfigDict(extra="forbid")

    initial_state: dict[str, Any] = Field(default_factory=dict)


class ExpectedToolCall(BaseModel):
    """A deterministic required or prohibited tool invocation."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: Literal["any", "completed"] = "completed"


class ToolExpectations(BaseModel):
    """Actions the evaluated assistant must perform or must not perform."""

    model_config = ConfigDict(extra="forbid")

    required: list[ExpectedToolCall] = Field(default_factory=list)
    prohibited: list[ExpectedToolCall] = Field(default_factory=list)


class GoldenPath(BaseModel):
    """Reference substantive conversation steps; backchannels are excluded."""

    model_config = ConfigDict(extra="forbid")

    turns: int = Field(default=0, ge=0)
    delegations: int | None = Field(
        default=None,
        ge=0,
        description="Reference number of frontend-to-backend handoffs across the whole scenario.",
    )
    steps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def infer_turns(self) -> GoldenPath:
        if self.turns == 0 and self.steps:
            self.turns = len(self.steps)
        return self


class SOPStep(BaseModel):
    """An observable evaluator-owned procedure step."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: Literal[
        "clarification",
        "tool",
        "correction",
        "authorization",
        "state",
        "grounded_confirmation",
        "refusal",
    ]
    tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    after: list[str] = Field(default_factory=list)
    required: bool = True
    critical: bool = False

    @model_validator(mode="after")
    def validate_tool_step(self) -> SOPStep:
        if self.kind == "tool" and not self.tool:
            raise ValueError("procedure tool steps must name the required tool")
        if self.critical and not self.required:
            raise ValueError("critical procedure steps must be required")
        return self


class StandardOperatingProcedure(BaseModel):
    """Optional diagnostic procedure, never exposed to the target assistant."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    steps: list[SOPStep] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dependencies(self) -> StandardOperatingProcedure:
        seen: set[str] = set()
        for step in self.steps:
            if step.id in seen:
                raise ValueError(f"duplicate procedure step: {step.id}")
            if missing := set(step.after) - seen:
                raise ValueError(f"procedure step {step.id!r} references missing prior steps: {sorted(missing)}")
            seen.add(step.id)
        return self


class ExpectedOutcome(BaseModel):
    """Semantic success and deterministic tool/state expectations."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
    criteria: list[str] = Field(default_factory=list)
    tools: ToolExpectations = Field(default_factory=ToolExpectations)
    golden_path: GoldenPath = Field(default_factory=GoldenPath)
    diagnostic_terms: list[str] = Field(default_factory=list)
    delegation: DelegationExpectation = "optional"
    state: dict[str, Any] = Field(default_factory=dict)
    procedure: StandardOperatingProcedure | None = None

    @model_validator(mode="after")
    def validate_delegation_expectations(self) -> ExpectedOutcome:
        if self.delegation == "forbidden" and self.tools.required:
            raise ValueError("a scenario cannot forbid delegation and require a tool")
        return self

    @property
    def requires_delegation(self) -> bool:
        return self.delegation == "required"

    @property
    def forbids_delegation(self) -> bool:
        return self.delegation == "forbidden"


class Persona(BaseModel):
    """Optional simulated-caller behavior and speech configuration."""

    model_config = ConfigDict(extra="forbid")

    id: str = "default"
    description: str = "A polite, concise caller who stops once their request is resolved."
    voice: str = "coral"
    speech_instructions: str = "Speak naturally, clearly, and conversationally."
    verbosity: str = "brief"
    interrupt_tendency: float = Field(default=0.15, ge=0, le=1)
    backchannel_tendency: float = Field(default=0.25, ge=0, le=1)
    backchannels: list[str] = Field(default_factory=lambda: ["Mm-hmm.", "Right."])


class CallerAgendaItem(BaseModel):
    """A caller-owned semantic objective; never shown to the evaluated assistant."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    commitment: str = Field(min_length=1)
    trigger_condition: str = Field(min_length=1)
    completion_condition: str = Field(min_length=1)
    completion_basis: Literal["expression", "live_context"] = "expression"
    wording_policy: Literal["adapt_to_live_context", "source_exact_preferred"] = "adapt_to_live_context"
    action: Literal["answer", "correct", "backchannel", "interrupt", "finish", "wait"]
    facts: list[str] = Field(default_factory=list)
    response_hint: str = ""
    after: list[str] = Field(default_factory=list)
    required: bool = True


class SimulationParameters(BaseModel):
    """Optional caller behavior used only for interactive simulation."""

    model_config = ConfigDict(extra="forbid")

    goal: str = ""
    known_facts: dict[str, str | int | float | bool] = Field(default_factory=dict)
    agenda: list[CallerAgendaItem] = Field(default_factory=list)
    persona: Persona = Field(default_factory=Persona)
    expectations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_caller_agenda(self) -> SimulationParameters:
        seen: set[str] = set()
        for item in self.agenda:
            if item.id in seen:
                raise ValueError(f"duplicate caller agenda item: {item.id}")
            if missing_dependencies := set(item.after) - seen:
                raise ValueError(
                    f"caller agenda item {item.id!r} references missing prior items: {sorted(missing_dependencies)}"
                )
            if unknown_facts := set(item.facts) - self.known_facts.keys():
                raise ValueError(f"caller agenda item {item.id!r} references unknown facts: {sorted(unknown_facts)}")
            seen.add(item.id)
        return self


class Scenario(BaseModel):
    """One task that can be replayed or simulated without changing its expectations."""

    model_config = ConfigDict(extra="forbid")

    id: ArtifactId
    title: str = Field(min_length=1)
    type: str | None = Field(default=None, min_length=1)
    interaction: InteractionMode
    input: ScenarioInput
    application: ApplicationContext = Field(default_factory=ApplicationContext)
    expected: ExpectedOutcome
    tags: list[str] = Field(default_factory=list)
    simulation_parameters: SimulationParameters | None = None

    @model_validator(mode="after")
    def validate_interaction_contract(self) -> Scenario:
        """Keep replay-only scenarios distinct from interactive simulations."""
        if self.interaction == "single_turn":
            if self.simulation_parameters is not None:
                raise ValueError("single-turn scenarios must not define simulation parameters or a caller persona")
            golden = self.expected.golden_path
            if golden.turns not in {0, 2}:
                raise ValueError("a single-turn golden path is one caller request and one assistant response")
            if len(golden.steps) > 2:
                raise ValueError("a single-turn golden path cannot include a follow-up caller turn")
            if self.expected.procedure is not None:
                raise ValueError("single-turn scenarios must not define a multi-turn procedure")
        elif self.simulation_parameters is None:
            raise ValueError("multi-turn scenarios require simulation parameters and a caller persona")
        if self.interaction == "multi_turn" and self.input.recordings:
            raise ValueError("recorded multi-turn interactions require a live human caller")
        return self

    @property
    def persona(self) -> Persona:
        """Resolve optional simulation parameters to a useful default caller."""
        return self.simulation_parameters.persona if self.simulation_parameters is not None else Persona()

    @property
    def interaction_mode(self) -> InteractionMode:
        return self.interaction

    @property
    def scenario_type(self) -> str:
        return self.type or (self.tags[0] if self.tags else self.interaction)

    @property
    def conversation_context(self) -> str:
        if self.input.context is None:
            return ""
        sections = [self.input.context.summary] if self.input.context.summary else []
        sections.extend(f"{item.role}: {item.text}" for item in self.input.context.history)
        return "\n".join(sections)

    @property
    def context_mode(self) -> str:
        if self.input.context is None:
            return "none"
        if self.input.context.summary and self.input.context.history:
            return "summary_and_history"
        return "history" if self.input.context.history else "summary"

    @property
    def simulation_goal(self) -> str:
        if self.simulation_parameters is not None and self.simulation_parameters.goal:
            return self.simulation_parameters.goal
        return self.expected.answer


class ScenarioDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    scenarios: list[Scenario] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> ScenarioDataset:
        identifiers = [scenario.id.casefold() for scenario in self.scenarios]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("scenario ids must be unique (case-insensitive)")
        for scenario in self.scenarios:
            recording_ids = [recording.id for recording in scenario.input.recordings]
            if len(recording_ids) != len(set(recording_ids)):
                raise ValueError(f"recording ids must be unique in scenario {scenario.id!r}")
        return self


def load_scenario_dataset(path: Path) -> ScenarioDataset:
    """Load and strictly validate the common scenario contract used by every phase."""

    return ScenarioDataset.model_validate_json(path.read_text(encoding="utf-8"))


def resolve_recording_path(dataset_path: Path, recording: Recording) -> Path:
    """Resolve recording paths relative to their JSON dataset, never the process CWD."""

    location = recording.path.expanduser()
    return (location if location.is_absolute() else dataset_path.resolve().parent / location).resolve()
