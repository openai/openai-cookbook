"""RUN-specific validation of the shared, portable scenario contract."""

from __future__ import annotations

from pathlib import Path

from shared.scenarios import Scenario, ScenarioDataset, load_scenario_dataset


def validate_run_scenario(scenario: Scenario) -> Scenario:
    """Keep full-duplex examples genuinely interactive and independently gradable."""

    if scenario.interaction != "multi_turn":
        raise ValueError("RUN restaurant scenarios must declare multi_turn interaction")
    if scenario.simulation_parameters is None:
        raise ValueError("RUN restaurant scenarios require simulation parameters")
    substantive = [item for item in scenario.simulation_parameters.agenda if item.action not in {"finish", "wait"}]
    if len(substantive) < 2:
        raise ValueError("RUN scenarios must include at least two substantive caller agenda objectives")
    if not scenario.simulation_parameters.known_facts:
        raise ValueError("RUN scenarios must include caller-owned known facts")
    if scenario.expected.golden_path.turns < 7:
        raise ValueError("RUN restaurant scenarios must define at least seven substantive golden-path turns")
    delegations = scenario.expected.golden_path.delegations
    if delegations is None:
        raise ValueError("RUN scenarios must define expected.golden_path.delegations")
    if scenario.expected.requires_delegation and delegations == 0:
        raise ValueError("required delegation needs a positive golden-path delegation count")
    if scenario.expected.forbids_delegation and delegations != 0:
        raise ValueError("forbidden delegation needs a zero golden-path delegation count")
    return scenario


def load_run_dataset(path: Path) -> ScenarioDataset:
    """Load the common JSON schema and apply RUN-only conversation requirements."""

    dataset = load_scenario_dataset(path)
    for scenario in dataset.scenarios:
        if scenario.interaction == "multi_turn":
            validate_run_scenario(scenario)
    return dataset
