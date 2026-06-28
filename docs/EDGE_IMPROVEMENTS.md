# Edge-Verbesserungen gegenüber dem Ursprungsplan

Der ursprüngliche `VALUE_BOT_PLAN.md` rechnet die faire Linie mit **simpler
proportionaler No-Vig-Methode** (§4.1) und vergleicht gegen **eine einzelne
Pinnacle-Quote**. Beides erzeugt systematisch zu viele falsche und zu wenige
echte Signale. Diese Engine-Implementierung adressiert genau das. Vier Hebel,
alle in `engine/` und mit festen Zahlenbeispielen in `tests/engine/` belegt.

---

## 1. Bessere faire Wahrscheinlichkeit → genauerer Edge

Die proportionale Methode (`p_i = (1/odds_i) / M`) verteilt die Buchmacher-Marge
gleichmäßig und **überschätzt dadurch Favoriten** bzw. unterschätzt Außenseiter
(Favorite-Longshot-Bias). Folge: Phantom-Value auf Außenseiter-Quoten.

`engine/novig.py` bietet fünf Methoden über ein gemeinsames Interface:

| Methode | Idee | Effekt auf den Edge |
|---|---|---|
| `multiplicative` | proportional (Baseline des Plans) | margen-naiv, FLB-verzerrt |
| `additive` | gleicher Margen-Absolutbetrag je Ausgang | besser bei knappen Märkten |
| `power` | `Σ (1/odds)^k = 1` | korrigiert FLB |
| **`shin`** *(Default)* | Marge = Schutz gegen Anteil `z` informierter Wetter | empirisch genaueste faire `p` |
| `odds_ratio` | konstantes Quotenverhältnis `c` | robuste Alternative |

**Beleg (2-Wege 1.80 / 2.10):** der Favorit bekommt fair
multiplikativ `0.5385`, Shin `0.5397`, Power `0.5403` — Shin/Power geben dem
Favoriten mehr und dem Außenseiter entsprechend weniger Wahrscheinlichkeit. Wer
gegen die multiplikative Linie bewertet, sieht auf Außenseitern einen Edge, den
es real nicht gibt.

## 2. Multi-Book-Sharp-Consensus → weniger Rauschen

`engine/consensus.py` de-vigged **mehrere** Sharp-Bücher und mittelt die fairen
Wahrscheinlichkeiten **gewichtet** (Pinnacle am schwersten, Default in
`config/settings.py`). Eine einzelne Quote ist verrauscht (Latenz,
Einzelfehlbepreisung); der gewichtete Consensus senkt die Varianz der fairen
Linie und macht den gemessenen Edge verlässlicher.

## 3. Robust-Modus → killt methodenabhängigen Phantom-Value

`engine/value.py::evaluate_value_robust` de-vigged denselben Sharp-Markt mit
**mehreren Methoden** und gibt ein Signal nur frei, wenn der Edge unter **allen**
besteht. Berichtet wird die **konservativste** Methode (kleinster EV) — der Edge
wird so nie überzeichnet.

**Beleg (Außenseiter @ 3.20 gegen Sharp 1.45 / 2.90):** multiplikativ zeigt
EV +6.7 % / Edge +2.1 % → Signal. Shin/Power scheitern am Edge → der
Robust-Modus **verwirft** das Signal. Das ist „weniger, aber echtere" Value.

## 4. KI-Delta mit Line-Movement-Dämpfung → kein Doppelzählen

`engine/ki_adjust.py` wendet das LLM-Delta sicher an: harte **Kappung** auf
±`cap`, **Confidence-Gate**, und — neu gegenüber dem Plan-Konzept — eine
**Line-Movement-Dämpfung**: hat sich die Sharp-Linie bereits in Delta-Richtung
bewegt, ist die News teilweise eingepreist und das Delta wird um die Bewegung
reduziert. Der KI-Edge zählt nur, soweit die KI *schneller* als der Markt war.

---

## Netto-Effekt

- **Mehr echter Value:** genauere faire `p` (Shin) deckt Value auf, den die
  naive Methode auf Favoriten verschenkt.
- **Bessere Edge-Qualität:** Robust-Modus + Consensus + Dämpfung entfernen die
  drei häufigsten Phantom-Value-Quellen (Methodenwahl, Einzelbuch-Rauschen,
  Doppelzählen von News).

Alle Schwellen und die Methodenwahl sind in `config/settings.py` konfigurierbar
— keine Magic Numbers im Code.
