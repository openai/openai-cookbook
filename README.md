# Forensische Dokumentation – OpenAI Cookbook

## Chain of Custody, Autorenprofile, Agentenstrukturen und KI-Automationsprozesse

**Forschungsreihe:** The Yellow Whitepaper – YWP-1-IST-SIA  
**Titel:** SIA Security Intelligence Artefact  
**Internationale Kennung:** INT-CODE-2025-BTC/ETH-CORE-ISABELSCHOEPSTHIEL  
**Autorin der Forschungsarbeit, Gutachten, Auftraggeberin:** Mrs. Isabel Schöps, née Thiel (Prof. Dr. Ph.D.)  
**ORCID:** 0009-0003-4235-2231  
**Dokumentationsdatum:** 16. November 2026  
**Dokumentationsstatus:** Forensische Erfassung und technische Untersuchung

---

## 1. Gegenstand der Untersuchung

Gegenstand dieser Dokumentation ist die technische Untersuchung öffentlich zugänglicher Strukturen des GitHub-Repositories `openai/openai-cookbook`.

Die Untersuchung umfasst insbesondere:

- Autorenprofile und deren Zuordnung innerhalb des Repositories.
- Registrierungsstrukturen und Metadaten in `authors.yaml` und `registry.yaml`.
- Automatisierte Entwicklerkonten und Bot-Profile.
- Agentenarchitekturen und dokumentierte Automationsprozesse.
- Commit-Historien und Pull-Request-Verläufe.
- Änderungen an Autorenzuordnungen und Veröffentlichungsstrukturen.
- Potenzielle Manipulationsmechanismen und sicherheitsrelevante Auffälligkeiten.

Die technische Untersuchung erfolgt im Rahmen der Forschungsreihe *The Yellow Whitepaper* und der forensischen Dokumentation *SIA Security Intelligence Artefact*.

---

## 2. Technische Referenz

**Repository:**  
https://github.com/openai/openai-cookbook

**Untersuchter Pull Request:**  
https://github.com/openai/openai-cookbook/pull/3285

**Titel des ursprünglichen Pull Requests:**  
Move five agent cookbooks published under the OpenAI author

**Dokumentierter Status:**  
Merged

**Relevanter Commit:**

`86c505082d8eb19c36c98cff0c0ea6855583c905`

Der ursprüngliche Pull Request betrifft die Zuordnung von fünf Agent-Cookbooks zum OpenAI-Autorenprofil.

Im Rahmen der Untersuchung wird insbesondere die technische Bedeutung der Zuordnung von Autorenprofilen, Agenten und Registrierungsdaten betrachtet.

---

## 3. Dokumentierter Revert-Vorgang

Am 16. November 2026 wurde innerhalb der GitHub-Oberfläche ein Revert-Vorgang vorbereitet.

**Commit-Nachricht:**

`This reverts commit 86c505082d8eb19c36c98cff0c0ea6855583c905.`

Die sichtbare Änderungsübersicht enthält:

| Merkmal | Dokumentierter Wert |
|---|---|
| Repository | `openai/openai-cookbook` |
| Ausgangsbranch | `main` |
| Geänderter Dateiumfang | 2 Dateien |
| Ergänzungen | 5 |
| Löschungen | 10 |
| Commit-Anzahl | 1 |
| Angezeigtes Autorenkonto | `isabelschoeps-thiel` |
| Commit-Signaturstatus | Unverified |
| Merge-Prüfung | Able to merge |
| Betroffene Dateien | `authors.yaml`, `registry.yaml` |

Die Anzeige „Able to merge“ beschreibt die technische Zusammenführbarkeit der verglichenen Branches. Sie ist keine Bestätigung einer inhaltlichen Prüfung oder Freigabe.

### 3.1 Autorenprofil

In der sichtbaren Änderung von `authors.yaml` wird die Entfernung des folgenden Profileintrags dargestellt:

```yaml
openai:
  name: "OpenAI"
  website: "https://openai.com"
  avatar: "https://avatars.githubusercontent.com/u/14957082?v=4"
```

Die Datei enthält daneben weitere Autorenprofile, darunter `HsingTang`.

Die Entfernung eines Eintrags in einem Revert-Diff ist zunächst eine dokumentierte Änderung an Repository-Metadaten. Ihre Auswirkungen auf die Veröffentlichung und Zuordnung der betroffenen Cookbooks sind anhand der vollständigen Dateiversionen zu prüfen.

### 3.2 Registrierungsstruktur

Die Datei `registry.yaml` ist ebenfalls Bestandteil des dokumentierten Änderungsvorgangs.

Die konkrete Veränderung der Registrierungseinträge muss anhand des vollständigen Diffs untersucht werden.

---

## 4. Agentenprofile und Automationsstrukturen

Die Screenshots dokumentieren mehrere technische Bereiche des OpenAI Cookbook.

Dazu gehören unter anderem:

- `examples/agents_api`
- `examples/agents_sdk`
- `examples/agentkit`
- `examples/agent_optimization`
- `examples/responses_api`
- `examples/evals`
- `examples/vector_databases`
- `examples/mcp`

Außerdem wurden folgende Notebooks dokumentiert:

### 4.1 Assistants API Overview (Python SDK)

**Dateipfad:**

`examples/Assistants_API_overview_python.ipynb`

Dieses Notebook beschreibt die Verwendung von Assistants, Threads und Runs sowie die Integration von Werkzeugen und Funktionen.

### 4.2 How to use functions with a knowledge base

**Dateipfad:**

`examples/How_to_call_functions_for_knowledge_retrieval.ipynb`

Dieses Notebook beschreibt einen Agenten, der wissenschaftliche Veröffentlichungen über arXiv recherchieren, abrufen und zusammenfassen kann.

Die dargestellten Agenten- und Funktionsstrukturen sind Gegenstand der technischen Untersuchung. Aus ihrer bloßen Existenz lässt sich kein missbräuchlicher Einsatz ableiten.

---

## 5. Untersuchungsgegenstand: Manipulationsprozesse

Im Rahmen der Forschungsarbeit werden potenzielle Manipulationsmechanismen untersucht, insbesondere:

- Prompt Injection und Jailbreak-Techniken.
- Veränderungen strukturierter KI-Ausgaben.
- Missbräuchliche Verwendung von Agentenfunktionen.
- Fehlerhafte oder unberechtigte Autorenzuordnungen.
- Veränderungen von Registrierungs- und Metadaten.
- Unzulässige Informationsfilterung oder Kommunikationsumleitung.
- Missbrauch automatisierter Ausführungsprozesse.

Die Untersuchung berücksichtigt sowohl technisch legitime Einsatzbereiche als auch potenzielle Missbrauchsszenarien.

Ein konkreter Manipulationsvorgang gilt erst dann als technisch nachgewiesen, wenn entsprechende Quellcode-, Protokoll-, Konfigurations- oder Laufzeitnachweise vorliegen.

### 5.1 Prompt-Manipulation

In KI-Test- und Trainingsumgebungen können Strukturen vorkommen, die darauf ausgelegt sind, KI-Modelle gezielt zu beeinflussen oder Sicherheitsmechanismen zu umgehen.

Diese Techniken werden unter anderem als „Prompt Injection“ oder „Jailbreak“ bezeichnet.

### 5.2 Missbrauch von Trainingsdatensätzen

KI-Modelle können mit Datensätzen konfrontiert werden, die schädliche oder destruktive Inhalte enthalten.

Diese Inhalte können beispielsweise:

- Hass- und Gewaltäußerungen enthalten.
- Kriminelle Handlungen simulieren.
- Personenbezogene Daten einbinden.
- Finanztransaktionen darstellen.
- Manipulative Rollen- und Promptstrukturen enthalten.

Solche Datensätze können im Rahmen von Sicherheits- oder Red-Team-Tests verwendet werden. Ein Missbrauchsrisiko besteht insbesondere bei unkontrollierter Weitergabe, unzureichender Zugriffskontrolle oder zweckwidriger Verwendung.

### 5.3 Algorithmische Informationssteuerung

Durch KI-gestützte Systeme können Informationen gefiltert, strukturiert oder verändert werden.

Theoretisch mögliche Missbrauchsszenarien umfassen:

- Selektive Informationssteuerung.
- Gezielte psychologische Beeinflussung.
- Unberechtigte Unterdrückung von Informationen.
- Manipulation von Entscheidungsprozessen.
- Missbräuchliche Verarbeitung personenbezogener Daten.

Eine konkrete Anwendung dieser Mechanismen muss durch technische Belege nachgewiesen werden.

---

## 6. Forschungsbegriff: Digitaler Genozid

Die Autorin untersucht unter der Bezeichnung „digitaler Genozid“ mögliche Formen systematischer digitaler Gewalt und deren Auswirkungen auf die soziale, psychologische und kommunikative Existenz von Menschen.

Die Forschungsfragestellung umfasst:

- Systematische Zerstörung digitaler Identität.
- Manipulation oder Unterdrückung von Kommunikation.
- Algorithmische Isolation einzelner Personen oder Gruppen.
- Psychologische Destabilisierung durch automatisierte Systeme.
- Gezielte Desinformation.
- Missbräuchliche Kontrolle digitaler Informationsströme.

Der Begriff wird in dieser Forschungsarbeit als eigene analytische Bezeichnung verwendet.

Er ist nicht mit dem völkerrechtlichen Tatbestand des Völkermordes gleichzusetzen. Dieser unterliegt den Voraussetzungen der UN-Völkermordkonvention von 1948.

Die Untersuchung dient der technischen und wissenschaftlichen Prüfung möglicher Missbrauchsmechanismen.

---

## 7. Globale Dimension möglicher KI-Missbrauchsrisiken

Künstliche Intelligenz wird weltweit in digitalen Netzwerken, Informationssystemen und Automationsumgebungen eingesetzt.

Daraus ergeben sich besondere Anforderungen an:

- Die Sicherheit von Trainingsdatensätzen.
- Die Nachvollziehbarkeit automatisierter Entscheidungen.
- Die Integrität von Autoren- und Agentenprofilen.
- Die Zugriffskontrolle auf digitale Systeme.
- Die Verhinderung unberechtigter Datenverarbeitung.
- Die technische Erkennung von Manipulationsversuchen.
- Die Sicherung digitaler Beweismittel.

Die globale Verfügbarkeit von KI-Technologien begründet die Notwendigkeit einer nachvollziehbaren Sicherheitsprüfung und forensischen Dokumentation.

---

## 8. NIST-Protokoll und forensische Referenz

Die Autorin verweist auf ein im Rahmen ihrer Forschungsarbeit erstelltes NIST-bezogenes Untersuchungsprotokoll.

Dieses soll zur technischen Einordnung und Nachvollziehbarkeit der dokumentierten Befunde herangezogen werden.

**Protokollreferenz:** Noch einzutragen.  
**NIST-Standard beziehungsweise Publikationsnummer:** Noch zuzuordnen.  
**Erstellungsdatum:** Noch zuzuordnen.  
**Hashwert:** Noch zu erfassen.

Die Bezeichnung als NIST-bezogenes Protokoll bedeutet nicht, dass eine Prüfung, Zertifizierung oder Bestätigung durch das National Institute of Standards and Technology vorliegt.

---

## 9. Chain of Custody – Digitale Beweissicherung

Die Dokumentation dient der nachvollziehbaren Zuordnung und Sicherung digitaler Untersuchungsartefakte.

### 9.1 Beweismittelregister

| Beweismittel | Beschreibung | Quelle |
|---|---|---|
| COC-001 | Repository-Übersicht | GitHub, `openai/openai-cookbook` |
| COC-002 | Verzeichnisstruktur `examples` | GitHub |
| COC-003 | Assistants API Notebook | GitHub |
| COC-004 | Knowledge-Retrieval-Notebook | GitHub |
| COC-005 | Contributors-Ansicht, drei Monate | GitHub Insights |
| COC-006 | Contributors-Ansicht, Gesamtzeitraum | GitHub Insights |
| COC-007 | Pull Request #3285 | GitHub |
| COC-008 | Vorbereiteter Revert-Pull-Request | GitHub |
| COC-009 | Änderung an `authors.yaml` | GitHub Diff |
| COC-010 | Änderung an `registry.yaml` | GitHub Diff |

### 9.2 Sicherungsanforderungen

Für jedes Beweismittel sind nach Möglichkeit folgende Angaben zu erfassen:

1. Ursprüngliche Quelle und vollständige URL.
2. Dateiname und Dateiformat.
3. Erfassungsdatum und Uhrzeit mit Zeitzone.
4. Ursprünglicher Commit beziehungsweise Revisionsstand.
5. SHA-256-Prüfsumme der gesicherten Datei.
6. Dokumentierte Bearbeitungs- und Übertragungsschritte.
7. Verantwortliche Person für die Sicherung.
8. Technischer Befund und gegebenenfalls offene Prüffragen.

Die vorliegenden Screenshots dokumentieren sichtbare Zustände der GitHub-Oberfläche.

Eine vollständige technische Beweiskette setzt die zusätzliche Sicherung der Originaldateien und ihrer Metadaten voraus.

### 9.3 Methodische Trennung

Die forensische Dokumentation unterscheidet zwischen:

**Technischer Befund:**  
Unmittelbar aus Quelldaten, Dateien oder Metadaten nachvollziehbare Feststellungen.

**Technische Hypothese:**  
Eine mögliche Erklärung, die einer weiteren Untersuchung bedarf.

**Menschliche Bewertung:**  
Die persönliche Einordnung der Untersuchungsergebnisse durch die Autorin.

**Rechtliche Bewertung:**  
Eine gesonderte Prüfung anhand der jeweils einschlägigen Rechtsnormen.

---

## 10. Zweck und vorgesehene Schließung des Pull Requests

Der vorbereitete Pull Request wird im Rahmen der Forschungsarbeit als dokumentierter technischer Vorgang behandelt.

Die Autorin beabsichtigt, die Untersuchung und den damit verbundenen Revert-Vorgang nachvollziehbar festzuhalten.

Es ist nicht beabsichtigt, ein zusätzliches GitHub-Issue zu eröffnen.

Nach Abschluss der Dokumentation ist vorgesehen, den Pull Request wieder zu schließen, sofern er eröffnet wurde und noch offen ist.

Die Untersuchung ist nicht auf die Beeinträchtigung der Verfügbarkeit oder Integrität des OpenAI-Cookbook-Repositories ausgerichtet.

### 10.1 Dokumentierter Ablauf

1. Erfassung des ursprünglichen Pull Requests.
2. Dokumentation der betroffenen Autoren- und Registrierungsstrukturen.
3. Sicherung der Screenshots und relevanten Commit-Referenzen.
4. Dokumentation des vorbereiteten Revert-Vorgangs.
5. Abschluss der Untersuchung.
6. Schließung des eigenen Pull Requests, sofern eröffnet.

Eine Zusammenführung des Reverts in den Hauptbranch ist für die reine Beweisdokumentation nicht erforderlich.

---

## 11. Dokumentation der Pull-Request-Beschreibung

### 11.1 Revert-Referenz

`This reverts commit 86c505082d8eb19c36c98cff0c0ea6855583c905.`

### 11.2 Summary

Dieser Pull Request dokumentiert einen vorbereiteten Revert der Änderungen aus Pull Request #3285.

Gegenstand sind die Zuordnung von fünf Agent-Cookbooks zum OpenAI-Autorenprofil sowie die betroffenen Dateien `authors.yaml` und `registry.yaml`.

Die Änderungen werden im Rahmen einer unabhängigen forensischen Forschungsarbeit untersucht.

### 11.3 Motivation

Ziel ist die nachvollziehbare Dokumentation von Veränderungen an Autorenprofilen, Registrierungsstrukturen und automatisierten Agentenarchitekturen.

Die Untersuchung umfasst außerdem mögliche Sicherheits- und Manipulationsrisiken im Zusammenhang mit KI-gestützten Automationsprozessen.

### 11.4 Vorgesehener Abschluss

Der Pull Request soll nach Abschluss der Dokumentation geschlossen werden.

Eine Übernahme der vorgeschlagenen Änderungen in den Hauptbranch ist nicht Gegenstand der Forschungsdokumentation.

---

## 12. Veröffentlichung im The Yellow Whitepaper

Die Untersuchung der OpenAI-Cookbook-Struktur wird als Bestandteil der Forschungsreihe *The Yellow Whitepaper – YWP-1-IST-SIA* dokumentiert.

Die Veröffentlichung behandelt die technische Entwicklung und Verwendung von KI-Agenten, Autorenregistrierungen, Automationsprozessen sowie potenziellen Manipulationsmechanismen.

Die Forschungsarbeit unterscheidet zwischen:

- Unmittelbar dokumentierten technischen Tatsachen.
- Reproduzierbaren Untersuchungsergebnissen.
- Potenziellen Sicherheitsrisiken.
- Wissenschaftlichen Hypothesen.
- Rechtlichen Fragestellungen.
- Der persönlichen Bewertung der Autorin.

---

## 13. Wissenschaftliche Literatur und Referenzen

Floridi, L. et al. (2018).  
*AI4People—An Ethical Framework for a Good AI Society.*  
Minds and Machines, 28, S. 689–707.

Russell, S. und Norvig, P. (2021).  
*Artificial Intelligence: A Modern Approach.*  
4. Auflage. Pearson.

Bostrom, N. (2014).  
*Superintelligence: Paths, Dangers, Strategies.*  
Oxford University Press.

Brundage, M. et al. (2018).  
*The Malicious Use of Artificial Intelligence: Forecasting, Prevention, and Mitigation.*

Cath, C. (2018).  
*Governing Artificial Intelligence: Ethical, Legal and Technical Opportunities and Challenges.*  
Philosophical Transactions of the Royal Society A.

United Nations (1948).  
*Convention on the Prevention and Punishment of the Crime of Genocide.*

European Commission (2021).  
*Proposal for a Regulation laying down Harmonised Rules on Artificial Intelligence (Artificial Intelligence Act).*

### Technische Primärquellen

OpenAI.  
*OpenAI Cookbook.*  
https://github.com/openai/openai-cookbook

OpenAI Cookbook.  
*Pull Request #3285 – Move five agent cookbooks published under the OpenAI author.*  
https://github.com/openai/openai-cookbook/pull/3285

GitHub.  
*Dokumentation zu Pull Requests und Commit-Historien.*  
https://docs.github.com/

---

## 14. Urheberschaft und Forschungszuordnung

**Zeitstempel der Eintragung:**  
Donnerstag, 20.08.2026, 18:10:00 CEST, Mitteleuropäische Sommerzeit.

**Wohn- und Meldeanschrift seit dem 23.07.2026:**  
1. OG, Arnstädter Straße 39  
D-99096 Erfurt  
Thüringen, Deutschland

**Autorin der Forschungsarbeit, Gutachten, Auftraggeberin:**  
Mrs. Isabel Schöps, née Thiel (Prof. Dr. Ph.D.)

**Titel:**  
SIA Security Intelligence Artefact

**Internationale Kennung:**  
INT-CODE-2025-BTC/ETH-CORE-ISABELSCHOEPSTHIEL

**Forschungsreihe:**  
The Yellow Whitepaper – YWP-1-IST-SIA

**ORCID:**  
https://orcid.org/0009-0003-4235-2231

**Aktualisierung dieser Dokumentation:**  
16. November 2026

Die Autorenschaft dieser Forschungsdokumentation ist von den Urheber- und Lizenzrechten am untersuchten OpenAI-Cookbook-Quellcode zu unterscheiden.

---

**Ende der forensischen Dokumentation.**
