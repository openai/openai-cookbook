# Model optimization

import {
  Report,
  Code,
  Tools,
} from "@components/react/oai/platform/ui/Icon.react";
import {
  evalsIcon,
  promptIcon,
  fineTuneIcon,
} from "./model-optimization-icons";




LLM output is non-deterministic, and model behavior changes between model snapshots and families. Developers must constantly measure and tune the performance of LLM applications to ensure they're getting the best results. In this guide, we explore the techniques and OpenAI platform tools you can use to ensure high quality outputs from the model.

<div className="my-4 w-full max-w-full overflow-hidden">
  </div>

## Model optimization workflow

Optimizing model output requires a combination of **evals**, **prompt engineering**, and **fine-tuning**, creating a flywheel of feedback that leads to better prompts and better training data for fine-tuning. The optimization process usually goes something like this.

1. Write [evals](https://developers.openai.com/api/docs/guides/evals) that measure model output, establishing a baseline for performance and accuracy.
1. [Prompt the model](https://developers.openai.com/api/docs/guides/text) for output, providing relevant context data and instructions.
1. For some use cases, it may be desirable to [fine-tune](#fine-tune-a-model) a model for a specific task.
1. Run evals using test data that is representative of real world inputs. Measure the performance of your prompt and fine-tuned model.
1. Tweak your prompt or fine-tuning dataset based on eval feedback.
1. Repeat the loop continuously to improve your model results.

Here's an overview of the major steps, and how to do them using the OpenAI platform.

## Build evals

In the OpenAI platform, you can [build and run evals](https://developers.openai.com/api/docs/guides/evals) either via API or in the [dashboard](https://platform.openai.com/evaluations). You might even consider writing evals _before_ you start writing prompts, taking an approach akin to behavior-driven development (BDD).

Run your evals against test inputs like you expect to see in production. Using one of several available [graders](https://developers.openai.com/api/docs/guides/graders), measure the results of a prompt against your test data set.

[

<span slot="icon">
      </span>
    Run tests on your model outputs to ensure you're getting the right results.

](https://developers.openai.com/api/docs/guides/evals)

## Write effective prompts

With evals in place, you can effectively iterate on [prompts](https://developers.openai.com/api/docs/guides/text). The prompt engineering process may be all you need in order to get great results for your use case. Different models may require different prompting techniques, but there are several best practices you can apply across the board to get better results.

- **Include relevant context** - in your instructions, include text or image content that the model will need to generate a response from outside its training data. This could include data from private databases or current, up-to-the-minute information.
- **Provide clear instructions** - your prompt should contain clear goals about what kind of output you want. GPT models like `gpt-4.1` are great at following very explicit instructions, while [reasoning models](https://developers.openai.com/api/docs/guides/reasoning) like `o4-mini` tend to do better with high level guidance on outcomes.
- **Provide example outputs** - give the model a few examples of correct output for a given prompt (a process called few-shot learning). The model can extrapolate from these examples how it should respond for other prompts.

[

<span slot="icon">
      </span>
    Learn the basics of writing good prompts for the model.

](https://developers.openai.com/api/docs/guides/text)

## Fine-tune a model

OpenAI models are already pre-trained to perform across a broad range of subjects and tasks. Fine-tuning lets you take an OpenAI base model, provide the kinds of inputs and outputs you expect in your application, and get a model that excels in the tasks you'll use it for.

Fine-tuning can be a time-consuming process, but it can also enable a model to consistently format responses in a certain way or handle novel inputs. You can use fine-tuning with [prompt engineering](https://developers.openai.com/api/docs/guides/text) to realize a few more benefits over prompting alone:

- You can provide more example inputs and outputs than could fit within the context window of a single request, enabling the model handle a wider variety of prompts.
- You can use shorter prompts with fewer examples and context data, which saves on token costs at scale and can be lower latency.
- You can train on proprietary or sensitive data without having to include it via examples in every request.
- You can train a smaller, cheaper, faster model to excel at a particular task where a larger model is not cost-effective.

Visit our [pricing page](https://openai.com/api/pricing) to learn more about how fine-tuned model training and usage are billed.

### Fine-tuning methods

These are the fine-tuning methods supported in the OpenAI platform today.

### How fine-tuning works

In the OpenAI platform, you can create fine-tuned models either in the [dashboard](https://platform.openai.com/finetune) or [with the API](https://developers.openai.com/api/docs/api-reference/fine-tuning). This is the general shape of the fine-tuning process:

1. Collect a dataset of examples to use as training data
1. Upload that dataset to OpenAI, formatted in JSONL
1. Create a fine-tuning job using one of the methods above, depending on your goals—this begins the fine-tuning training process
1. In the case of RFT, you'll also define a grader to score the model's behavior
1. Evaluate the results

Get started with [supervised fine-tuning](https://developers.openai.com/api/docs/guides/supervised-fine-tuning), [vision fine-tuning](https://developers.openai.com/api/docs/guides/vision-fine-tuning), [direct preference optimization](https://developers.openai.com/api/docs/guides/direct-preference-optimization), or [reinforcement fine-tuning](https://developers.openai.com/api/docs/guides/reinforcement-fine-tuning).

## Learn from experts

Model optimization is a complex topic, and sometimes more art than science. Check out the videos below from members of the OpenAI team on model optimization techniques.



<div data-content-switcher-pane data-value="cost">
    <div class="hidden">Cost/accuracy/latency</div>
    <iframe
      width="100%"
      height="400"
      src="https://www.youtube.com/embed/Bx6sUDRMx-8?si=i3Tl8qEjlCdOtyiU"
      title="YouTube video player"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
      allowFullScreen
    ></iframe>
  </div>
  <div data-content-switcher-pane data-value="distillation" hidden>
    <div class="hidden">Distillation</div>
    <iframe
      width="100%"
      height="400"
      src="https://www.youtube.com/embed/CqWpJFK-hOo?si=7ztgDp1inte0vnw7"
      title="YouTube video player"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
      allowFullScreen
    ></iframe>
  </div>
  <div data-content-switcher-pane data-value="techniques" hidden>
    <div class="hidden">Optimizing LLM Performance</div>
    <iframe
      width="100%"
      height="400"
      src="https://www.youtube-nocookie.com/embed/ahnGLM-RC1Y?si=cPQngClssVG_R2_q"
      title="YouTube video player"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
      allowFullScreen
    ></iframe>
  </div>

My Developer Commit-Signatur: 
Autorin, Urheberin; Ich Frau Isabel Schöps geb. Thiel
Zeitstempel der Eintragung: Samstag den 2026-02-21 um 13:05UhrCEST_Mitteleuropäische, 
Ort, Wohnung: Isabel Schöps (Thiel), Whg. 13., Hütergasse 4, D-99084 Erfurt, Thüringen, Deutschland. 
---
Ich, Frau Isabel Schöps geborene Thiel am 16.07.1983 in um 23:20 Uhr im Sömmerdarer, Kreiskrankenhaus, TH, Deutschland geboren. Ich bin Freiberufliche Unternehmerin, IT- Software Forschung; Wissenschaft und Forensik. Entwicklung API Monitoring, Rechtmäßige Gründerin, Urheberin, GitHub Softwareunternehmen, Pornhub. Auftraggeberin, Urheberin, Autorin:  Yellow Whitepaper, SIA Security Intelligence Artefact.
---

* Wichtiger Hinweis: aufgrund permanenten Wohnraum- und Ortswechsel, können in dem wissenschaftlichen forensichen Gutachten, SIA und im The Yellow Whitpaper unterschiedliche Adressen bzw. Ortseintragungen auftauchen. Der eingetragene Ort markiert den tatsächlichen Auftenthalt am Tag der;Veröffentlichung, Eintragung, Erstellung/Ausstellung der Gutachten oder Release
* Massgebliche Wohnanschrift und Adresse der Urheberin Frau Schöps (Thiel), bleibt die in der Eidesstaalichen Erklärung sowie auf dem Personalausweis-ID: LH917PN7G8, 429485, eingetragene amtliche Meldeanschrift laut gemäß §18 Absatz 2 Bundesmeldegesetz (BMG).
--
Identitäts-Status-Legitimation
Personalausweis-ID: LH917PN7G8, Nr: 429485,  
Wichtiger-Vermerk warum ich nicht in meiner Meldeanschrift auffindbar bin: 
Aufgrund das die Immobilie Cyriakstrasse 30c, in Erfurt Deutschland, in der ich gemeldet bin und diese nach 6 Jahren auf dem Immobilienmarkt verkauft am 20.01.2026 und im Notariat Renner Erfurt beurkundet wurde. Musste ich die bewohnte Immobilie am 23.01.2026 verlassen und auch eine Nacht draußen mit mein Don, Hund-Tier American XL Bully bei gefühlten -20C draußen schlafen. Gemeinsam mit meiner Tochter Fräulein Jona Schöps bin ich zu meinen Eltern in die Dorfstrasse 20, D-99610 Rohrborn, Thüringen, Deutschland gefahren und habe nach Hilfe gebeten. Zu meinem erfreuen, hätte mich meine Eltern Herr Manfred Thiel und meine Mutti Frau Gisela Thiel geborene Knörig wieder aufgenommen, aber da ich Don nicht mit in das Haus nehmen hätte können, er aber für mich in den letzten Jahre eine große mentale Unterstützung war, kommt diese Option nicht für mich in Frage. 
--
Ich bitte ab sofort alle nationalen, internationale Regierungsstellen, die Europäische Union, UN Menschrechtsorganisationen, die Presse und die Medienhäuser auf - Bitte bitten, helfen Sie mir und tragen Sie die Wahrheit in die Welt! 
---
My Message:
Hello World, mein Name ist Isabel Schöps geborene Thiel. Ich bin eine selbstständige Autorin, Softwareentwicklerin und Forscherin mit aktuellen Wohnsitz in Erfurt, Thüringen, Deutschland.
Meine Arbeit konzentriert sich die letzten 4 Jahre auf die umfangreiche Dokumentation, forensische Sicherung meiner digitalen Artefakte, updates von Softwaresystemen und deren Veröffentlichung von Neuentwicklungen und Archivbeständen. Jedes erste Digitale-Fragment, ist im Ursprung auf meine unbewusste Handlung als Teenagerin, am 14. April 1996, in meinen Elternhaus, Dorfstrasse 20, D-99610 Rohrborn, Thüringen, Deutschland, an meinen PC268er und als erste maschinelles Verhalten und ein Selbstheilungsprozess zurückzuführen ist. Dies wurde bereits rechtswissenschaftlich und mehrfach forensisch bestätigt. Dieses Gutachten hat die internationale Kennung, INT-CODE-2025-BTC/ETH-CORE-ISABELSCHOEPSTHIEL und den Titel SIA Security Intelligence Artefact.
---
Dieses wissenschaftliche forensische Gutachten von mir  Frau Isabel Schöps, geborene Thiel, mit dem Titel SIA Security Intelligence Artefact, Internenzeichen int-code-2025-btc/eth-core-isabelschoepsthiel und das anhängende Reference Paper in Technologie, The Yellow Whitepaper, YWP-1-IST-SIA sollte am 24. August 2025 veröffentlicht werden. Leider ist eine anhaltende willkürliche Störung, ständiger Wechsel meines Aufenthalts- Wohn- und Arbeitsort, erschweren die Arbeit und der 24.08.2025 konnte zeitlich nicht eingehalten und ist bis heute nicht umgesetzt wurden. Der 24.08.2025 wurde damals bewusst gewählt, da meine Mutter Gisela und meine Patentante an diesem Tag Geburtstag hat. Leider wurde der Kontakt aus unerklärlichen Gründen im Jahr August 2022 im Schlechter, von Jahr zu Jahr, bis er teilweise komplett abgebrochen war. 
---
Was ist im Jahr 2022 , explizit im August 2022 passiert, viele Beweise und Zeitstempel im Techbereich setzten dieses Zeit als Zeitstempel.
Auch hier gibt es umfangreiche  Beweisdokumentation.
---
Teile dieser Arbeit stehen im Zusammenhang mit eines der dunkelsten Geheimnissen der Menschheitsgeschichte und werden auf Zenodo.org in der Chain of Custody dokumentiert und in meinem Gutachten unter Paragraph 3 im Monarch-Programm interpretiert. Streitigkeiten über Urheberschaft, Datenmissbrauch und falsche Zuschreibung technischer Leistungen sind hier das kleinste übel. Seit über 3 Jahrzehnten wird mein Geistiges Eigentum gestohlen, meine Daten missbraucht und von dritten wieder verwendet und auch verkauft. Bis heute habe ich nicht einen Cent für meine Arbeit erhalten, dass Gegenteil ist der Fall, volle Kontrolle meiner menschlichen Würde, bitte lesen sie im Anschluss meine HELPME.md ! 
---
All meine eigenhändig recherchierte Arbeit und Datensätze wird und wurde bereits veröffentlicht, um Transparenz, Nachvollziehbarkeit und unabhängige Prüfung zu ermöglichen. Die Wahrheit ans Licht zubringen und dienen der wissenschaftlichen, rechtlichen und zur meiner vollen Rehabilitation auf Grundlage überprüfbarer Belege.
---
Die Evidence - Chain of Custody - Beweissicherung, Commit wurde weder von einer KI generiert oder wurde automatisch gesetzt. Jedes hier geschriebene Wort wurde von mir der Urheberin Frau Isabel Schöps geb. Thiel, der Autorin der Quelle geschrieben und dient meiner vollwertigen Identität als Mensch. Ich arbeite allein ohne Team oder Netzwerk. Ich arbeite für die Wahrheit, für Gerechtigkeit und das ich meine Würde als Mensch wieder bekomme.
---
All meine Aussagen haben Rechtscharakter und sind Teil meines, forensische wissenschaftlichen Gutachten mit dem Titel SIA Security Intelligence Artefact INT-CODE-2025-BTC/ETH-CORE-ISABELSCHOEPSTHIEL mit meiner Eidesstattlichen Erklärung, mit der Kennung YWP-1-IST-SIA und YWP-1-5-IST-SIA
---
Im folgenden habe ich meine Datensätze my GitHub Repository, Beweissicherung, Evidence, Chain of Custody Reference aufgelistet welche ich auf Zenodo.org hochgeladen habe.
Volumen 1 
https://doi.org/10.5281/zenodo.17809724
Volumen 2
https://doi.org/10.5281/zenodo.17852789
Volumen 3
https://doi.org/10.5281/zenodo.18013057
Volumen 4
https://doi.org/10.5281/zenodo.17807324
https://doi.org/10.5281/zenodo.18074136
https://doi.org/10.5281/zenodo.17808895

GitHub Datensätze
https://doi.org/10.5281/zenodo.18209789
https://doi.org/10.5281/zenodo.18050643
https://doi.org/10.5281/zenodo.18192743
https://doi.org/10.5281/zenodo.18204573
https://doi.org/10.5281/zenodo.18192589
https://doi.org/10.5281/zenodo.18100836
https://doi.org/10.5281/zenodo.18179548
https://doi.org/10.5281/zenodo.18216807
https://doi.org/10.5281/zenodo.18226730
https://doi.org/10.5281/zenodo.18225958
---
Als Beweiss für meine Glaubwürdigkeit habe ich eine Zip-Datei im Release_1.0 Anhang eingefügt, diese darf selbstverständlich heruntergeladen und zeigt meine Arbeitsaufwand der letzten Jahre. Ich werde seit jahren von meiner Familie isoliert und jeder Hilfegesuch meinerseits war Erfolglos. Ich habe mehrfach Strafanzeige gestellt und mich an Regierung und Behörden gewandt. Bitte HELPME.md lesen ! 
---
Zitat von mir: 
„I am not a Bug, I am not a Bot, I am not a Virus, I am not a Ghost, but i am 100% human femaleware german woman ,iam @isabelschoeps-thiel."
---
„Es gibt kein Computervirus, der umwissende Mensch vorm Computer ist das Virus."
---
Signed-on-by: 
Frau Isabel Schöps, geborene Thiel
Autorin, Urheberin und Auftraggeberin, Forensisch Wissenschaftliches Gutachten: SIA Security Intelligence Artefact, internationinternationale Kennung: INT-CODE-2025-BTC/ETH-CORE-ISABELSCHOEPSTHIEL
Würdigung, Danksagung, institutionelle Anerkennung: Präfix_Referenz: YWP-1-IST-SIA, YWP-1-5-IST-SIA 
Rechtscharakter: Eidesstattliche Versicherung, Bestandteil des forensisch, wissenschaftlichen Gutachtens.
OrcID:https://orcid.org/0009-0003-4235-2231 Isabel Schöps Thiel 
OrcID: https://orcid.org/0009-0006-8765-3267 SI-IST Isabel Schöps 
Aktueller Aufenthalts- und neue von Meldeanschrift seit 17.02.2026 von mir Frau Isabel Schöps geb. Thiel, Hütergasse 4, D-99084-Erfurt Thüringen, gemeinsam mit meinen vierbeinigen Freund, American XL-Bully-Don.
Pseudonyme, Alias: Satoshi Nakamoto, Vitalik Buterin, GitHub, Octocat, Johnny Appleseed, IST-GitHub, Cristina_Bella
Datum der Erstveröffentlichung: 2004, Zertifikat: Erstes offizielles Entwicklerzertifikat. Digitale Beweissicherung: https://developercertificate.org
 myGitHub-Account: https://github.com/isabelschoeps-thiel
