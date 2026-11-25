# Voice agents that follow an SOP

Use one of these apps to try the pattern from the [Cookbook article](../../../articles/sop_to_voice_agent_builder.md). Blossom Store follows an order-support procedure. The availability interviewer gets its questions from a local applicant tracking system (ATS). Both apps let GPT-Live speak and keep the order or interview record in application code. The store and ATS run locally.

## Set up

From the root of your Cookbook clone, run:

```sh
cd examples/audio/sop_voice_workflows
python3.12 -m venv .venv
source .venv/bin/activate
export PYTHONPATH=.
```

Python 3.12 is enough for the offline Blossom replay. For voice calls, install the dependencies:

```sh
python -m pip install -r requirements.txt
```

The microphone commands use your default input and output devices. Wear headphones. On Linux, install the PortAudio runtime (on Ubuntu, `libportaudio2`) and the venv package for your Python version. On macOS, use `brew install portaudio` if your Python environment cannot open a device. Set `OPENAI_API_KEY` in your environment for a project with access to the models used by the example. Pass a new output directory for each run.

## Blossom Store

Read the [store policy](delivery/SOP.md), the [frontend prompt](delivery/live_prompt.txt), the [backend prompt](delivery/backend_prompt.txt), and the [five store tools](delivery/tools.json). GPT-Live hands requests to the application. Terra chooses the next step. Before a credit or replacement, the store checks which offer is current and asks a separate, tool-free reviewer whether the caller agreed to its terms.

**Offline replay.** A scripted customer asks where their order is, reports a broken lamp, and accepts a replacement. The local store should record one replacement with receipt `RP001`. The command prints `"pass": true` and saves the trace in `runs/blossom-reference/reference.json`.

```sh
python -m delivery.runner --reference --out runs/blossom-reference
```

**Microphone call.** When you see “Connected. Speak now,” try “My desk lamp arrived with a cracked base. Could I get a replacement?” Let the agent explain the offer, then accept it. Press Ctrl-C to finish. Open `final-state.json` in the output directory and inspect `store.effects`. A completed replacement produces one entry.

```sh
python -m delivery_voice --mic --output runs/blossom-mic
```

## Availability interview

The [ATS](interview_app/store.py) supplies the first question. GPT-Live is prompted to delegate after each answer. A [Decisions transcript trigger](interview_app/meaning.py) can start interpretation when a handoff is late. A timeout can also start interpretation. All three paths use the [same controller](interview_app/live.py), so a late handoff can reuse work already in progress.

**Local configuration.** Print the opening question and the registered Decisions checks without an API key:

```sh
python -m interview_app --describe
```

**Microphone call.** Answer the opening question with “I could work any shift on Monday.” Listen to the summary and confirm it if correct. At the end of the call, compare `tool-executions.json` with `final-state.json`. The ATS can record both the day and shift from that reply. The interview finishes after the candidate confirms the summary.

```sh
python -m interview_app --mic --output runs/interview-01
```

## Inspect and test the examples

The [recordings](recordings/) are WebM audio files that pair synthetic callers with GPT-Live replies. Open a timeline from your local clone in a browser: the [broken-lamp replacement](recordings/broken-lamp.html) follows a tracking request that becomes a damage report, the [Monday interview](recordings/interview-multi-answer.html) shows one reply answering two questions, and the [Tuesday interview](recordings/interview-handoff.html) shows Decisions starting backend work when GPT-Live’s handoff is late. Select a timestamp to hear that part of the call and expand an event to see tool arguments and results. Provider identifiers in the public timelines are shortened. The conditional Tuesday [recording notes](recordings/interview-conditional-clarification.json) keep the checksum of the original MP3 used in the test; the published [WebM](recordings/interview-conditional-clarification.webm) is a conversion of that recording. Output from a fresh microphone call contains the conversation you just had and stays in your chosen output directory.

Run the application tests locally with:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The [backend comparison](delivery/REPORT.md) explains how Terra and Luna handled the same cases. For full voice evaluations, follow the [GPT-Live evaluation guide](https://developers.openai.com/cookbook/examples/audio/voice_agent_evaluation). Use the tool log to check what the app did and the recorded receiver audio to check what was audible.
