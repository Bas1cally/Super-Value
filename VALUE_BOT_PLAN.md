# Value-Bet-Bot — Optimaler Bauplan

**Zweck:** Ein Bot, der bei **yeet.com** (deinem Buchmacher der Wahl) Quoten einsammelt, gegen "faire" Wahrscheinlichkeiten aus Sharp-Quoten (The Odds API) + KI-Adjustierung (News/Verletzungen/Aufstellungen) vergleicht und nur echte **Value-Signale ab Quote 1.5** ausgibt — inkl. Kombiwetten. **Keine Wettausführung, kein Geld, keine Bankroll — reine Signale per Telegram.**

**Konfiguration (von dir gewählt):**

- **Output:** Telegram-Bot (Push in Echtzeit)
- **Ziel-Buchmacher:** **yeet.com** (dezentral/on-chain) — hier suchen wir Value
- **Sharp-Referenz:** **The Odds API** (Pinnacle u.a. als faire Linie)
- **Value-Modell:** Sharp-Vergleich + KI-Adjustierung durch News/Lineups
- **Sportarten:** Alle verfügbaren
- **Einsätze:** keine — der Bot empfiehlt **keine** Stakes/Bankroll, nur den Value selbst
- **Hosting:** Hetzner VPS, Code auf GitHub (damit Claude Code arbeiten kann)

---

## 0. Realitäts-Check (bitte zuerst lesen)

Drei Dinge vorab, damit der Bot nicht auf falschen Erwartungen gebaut wird:

1. **"99% Chance" gibt es real nicht.** Echtes Value-Betting findet *kleine* Edges (typisch 2–8 % EV). Ein seriöses Signal lautet nicht "99 % auf Dodgers", sondern z.B. *"Dodgers ML @ 1.95 — faire Quote 1.80 → +8.3 % EV, Edge basiert auf Pinnacle-Linie + bestätigtem Lineup"*. Der Bot zeigt **EV % und geschätzten Edge**, keine Fantasie-Prozente. Genau das trennt einen profitablen Bot von einem Tippspiel.

2. **Quote ≥ 1.5 + Value sind zwei verschiedene Filter.** Eine 1.5-Quote ist nur dann ein Signal, wenn die *faire* Quote darunter liegt (z.B. fair 1.35 → die 1.5 ist Value). Der Bot filtert auf **beides gleichzeitig**: `Quote ≥ 1.5` UND `EV > Schwelle`.

3. **Die Quoten kommen aus zwei Welten.** Die *Sharp-Referenz* (faire Linie) zieht der Bot legal über **The Odds API** (Pinnacle u.a.). Die *Ziel-Quoten* kommen von **yeet.com** — einer dezentralen/on-chain Plattform ohne klassische API. Hier holt der Bot die Quoten entweder über die On-Chain-/Frontend-Datenquelle von yeet.com (siehe §2.1) oder per Scraping. Da yeet.com dezentral ist, gibt es i.d.R. keine aggressive Anti-Bot-Mauer wie bei Bet365/Tipico — das macht den Datenzugriff sogar einfacher und stabiler.

---

## 1. Gesamtarchitektur

Pipeline in 7 Schichten — jede ist ein eigener Service/Modul, lose gekoppelt über eine Datenbank + Message-Queue:

```
┌─────────────────────────────────────────────────────────────────┐
│  1. INGESTION          Quoten + Stats + News einsammeln          │
│     ├─ Sharp-Linie:  The Odds API (Pinnacle)                     │
│     ├─ Ziel-Quoten:  yeet.com (on-chain / frontend / scrape)     │
│     ├─ Stats-Clients (API-Football, Flashscore)                 │
│     └─ News/Injury-Feeds (RSS + LLM-Extraktion)                  │
├─────────────────────────────────────────────────────────────────┤
│  2. NORMALIZATION      Teams/Märkte/Events vereinheitlichen      │
│     └─ Entity-Resolution: "Bayern München"="FC Bayern"=ID 503    │
├─────────────────────────────────────────────────────────────────┤
│  3. FAIR-VALUE ENGINE  "Wahre" Wahrscheinlichkeit berechnen      │
│     ├─ No-Vig: Sharp-Quote (Pinnacle/Betfair) → faire p          │
│     └─ KI-Adjustierung: News/Injuries/Lineups → p-Delta          │
├─────────────────────────────────────────────────────────────────┤
│  4. VALUE CALCULATION  EV pro Markt, Filter (≥1.5, ≥3% EV)      │
├─────────────────────────────────────────────────────────────────┤
│  5. PARLAY BUILDER     Unabhängige Legs zu Kombis verrechnen     │
├─────────────────────────────────────────────────────────────────┤
│  6. SIGNAL / ALERTING  Telegram-Push, Dedup, Formatierung        │
├─────────────────────────────────────────────────────────────────┤
│  7. PERSISTENCE + TRACKING  Postgres: Odds-Historie, CLV, ROI    │
└─────────────────────────────────────────────────────────────────┘
        ▲                                                   │
        └──────────── SCHEDULER / ORCHESTRATOR ─────────────┘
                 (Polling-Loops, Rate-Limits, Retry)
```

**Tech-Stack (Empfehlung):**

| Bereich | Wahl | Begründung |
|---|---|---|
| Sprache | **Python 3.12** | Beste Ökosystem-Abdeckung für Stats/Scraping/LLM |
| Async/Scheduling | `asyncio` + `APScheduler` | Viele parallele API-Polls effizient |
| HTTP | `httpx` (async) | Robust, async, Retry-fähig |
| Scraping | `Playwright` | JS-Rendering, Anti-Bot-resistenter als requests |
| DB | **PostgreSQL** + `SQLAlchemy` | Odds-Zeitreihen, Joins, ACID |
| Cache/Queue | **Redis** | Dedup, Rate-Limit-Token, Pub/Sub für Alerts |
| LLM | Claude API (`anthropic`) | News/Lineup-Extraktion + Adjustierung |
| Telegram | `python-telegram-bot` | Ausgereift, async |
| Container | **Docker + docker-compose** | Reproduzierbar auf Hetzner |
| CI | GitHub Actions | Tests + Auto-Deploy auf VPS |

---

## 2. Schicht 1 — Daten-Ingestion

### 2.1 Quoten-Quellen (Odds)

Genau **zwei** Quoten-Quellen — bewusst schlank gehalten:

**A) Sharp-Referenz — The Odds API (`the-odds-api.com`):**

- Liefert über *eine* API die Quoten vieler Buchmacher inkl. **Pinnacle** — unsere "schärfste" Linie zur Berechnung der fairen Wahrscheinlichkeit (§4).
- Free-Tier zum Testen (begrenzte Request-Zahl/Monat), reicht für den Start. Deckt alle relevanten Sportarten + Pre-Match-Märkte.
- Wir nutzen **nur** den Teil, der für die faire Linie nötig ist (Pinnacle + ggf. ein zweiter Sharp-Bookie zur Mittelung) → spart Requests.

**B) Ziel-Quoten — yeet.com (dezentral/on-chain):**

- yeet.com hat keine klassische REST-API wie ein lizenzierter Bookie. Zugriffs-Optionen, in dieser Reihenfolge zu prüfen:
  1. **On-Chain / Subgraph:** Falls yeet.com Märkte on-chain abwickelt, Quoten direkt aus den Smart Contracts bzw. einem Subgraph (The Graph) lesen — die *sauberste und stabilste* Quelle, kein Scraping nötig.
  2. **Internes Frontend-API:** Browser-Netzwerk-Tab prüfen — viele dApps laden Quoten über eine JSON-Endpoint, die man direkt abfragen kann.
  3. **Playwright-Scraper** als Fallback, falls 1+2 nicht gehen.
- In eigenes Modul `sources/yeet/` kapseln, damit ein Bruch isoliert bleibt.

> **Designregel:** Beide Quellen implementieren dasselbe Interface `OddsSource.fetch() -> list[OddsRecord]`. Engine bleibt quellen-agnostisch; weitere Bookies später = nur neue Klasse.

> **Erster Klärungsschritt für Claude Code:** yeet.com inspizieren (On-Chain-Adressen / Subgraph / Frontend-Calls), um die beste der drei Optionen festzulegen. Das bestimmt das gesamte Ingestion-Modul.

### 2.2 Stats- & Info-Quellen (für die KI-Adjustierung)

- **API-Football / API-Sports** (`api-sports.io`) — Aufstellungen, Verletzungen, Form, H2H, Tabellen für Fußball + weitere Sportarten. Günstig, breit.
- **Flashscore** (Scraping) — Live-Scores, Aufstellungen, Statistiken als Cross-Check. Playwright, da JS-gerendert.
- **SportRadar / Stats Perform** — Profi-Daten (teuer, optional, Trial möglich).
- **News/Injury-Feeds:** Team-RSS, Reuters/AP-Sport, beat-Reporter-Twitter/X-Listen. Roh-Text → **Claude extrahiert** strukturierte Fakten (wer fällt aus, wer startet, Wetter, Motivation).

### 2.3 Ingestion-Regeln

- Polling-Intervalle nach Markt: Pre-Match alle 5–15 min, kurz vor Anpfiff 1–2 min, Lineups beim Veröffentlichungszeitpunkt (~1 h vorher).
- **Rate-Limits respektieren** (Redis-Token-Bucket pro API), exponential backoff bei 429.
- Jede Quote mit **Timestamp** speichern → Zeitreihe für CLV (siehe §8).

---

## 3. Schicht 2 — Normalisierung (der schwierigste Teil)

Verschiedene Quellen schreiben "Bayern" / "FC Bayern München" / "Bayern Munich". Ohne saubere Vereinheitlichung vergleicht der Bot Äpfel mit Birnen → Phantom-Value.

**Aufgaben:**

1. **Team-/Spieler-Mapping:** kanonische ID-Tabelle, Alias-Liste, Fuzzy-Matching (`rapidfuzz`) + LLM-Fallback für unklare Fälle. Manuelle Overrides in DB.
2. **Event-Matching:** Spiele über Quellen via (Sportart, Heim, Gast, Anstoßzeit ± Toleranz) zusammenführen → eine `event_id`.
3. **Markt-Mapping:** "1X2" / "Match Winner" / "Moneyline" / "ML" → kanonischer Markt-Key. Handicaps & Totals mit Linie normalisieren (z.B. `OVER_2.5`).
4. **Quoten-Format:** alles in **Dezimalquoten**.

> Ergebnis: eine Tabelle `quotes(event_id, market_key, selection_key, bookmaker, decimal_odds, ts)` — die einzige Wahrheit für die Engine.

---

## 4. Schicht 3 — Fair-Value Engine

### 4.1 Schritt A — No-Vig faire Wahrscheinlichkeit aus Sharp-Quote

Buchmacher bauen eine Marge ein (die Quoten-Summe der Gegenwahrscheinlichkeiten > 100 %). Wir nehmen die **schärfste** Quelle (Pinnacle, oder Betfair-Mittelpreis) und rechnen die Marge raus:

```
Roh-Wahrscheinlichkeit je Ausgang:  p_i = 1 / odds_i
Marge (Overround):                  M = Σ p_i
Faire Wahrscheinlichkeit:           p_fair_i = p_i / M
```

*Beispiel (2-Wege):* Pinnacle Dodgers 1.80 / Yankees 2.10 → p = 0.556 / 0.476, M = 1.032 → p_fair Dodgers = **0.538** (faire Quote 1.857).

Verfeinerung optional: **Power-/Shin-Methode** statt simpler Proportionalität (verteilt die Marge realistischer, besonders bei Außenseitern).

### 4.2 Schritt B — KI-Adjustierung (News/Injuries/Lineups)

Die Sharp-Linie ist die Basis. Darauf ein **begrenzter** Korrekturfaktor aus dem Info-Layer:

1. Claude bekommt strukturierten Kontext zum Event: bestätigte Aufstellung, Ausfälle (mit Wichtigkeit des Spielers), Form, Wetter, Reise/Rest, Motivation (Tabellensituation).
2. Claude liefert ein **kalibriertes p-Delta** mit Begründung + Confidence, z.B. "Star-Pitcher fällt überraschend aus → −4 % für Dodgers".
3. **Sicherheitsbegrenzung:** Delta wird gekappt (z.B. max ±6 %), damit eine LLM-Fehleinschätzung die Sharp-Linie nicht überstimmt. Wenn die Sharp-Quote die News schon eingepreist hat (Linie hat sich bewegt) → Delta gegen Null.

```
p_true = clip(p_fair + delta_KI, 0.01, 0.99)
```

> **Wichtig:** Wenn ein Buchmacher die Linie schon bewegt hat, *ist die Info bereits drin*. Der Bot prüft die Liniendynamik, um doppeltes Zählen zu vermeiden. Die KI bringt nur Mehrwert, wenn sie **schneller** als der Markt ist (z.B. frisch bestätigtes Lineup, das ein lahmer Bookmaker noch nicht verarbeitet hat).

---

## 5. Schicht 4 — Value-Berechnung & Filter

Für **jede yeet.com-Quote** gegen `p_true` (faire Wahrscheinlichkeit aus der Sharp-Linie):

```
EV  = p_true × odds_yeet − 1               (erwarteter Wert pro Einheit Einsatz)
Edge = p_true − (1 / odds_yeet)             (Wahrscheinlichkeits-Vorsprung)
```

**Signal nur wenn ALLE Bedingungen erfüllt:**

| Filter | Schwelle (konfigurierbar) |
|---|---|
| Mindestquote | `odds ≥ 1.5` |
| Mindest-EV | `EV ≥ 0.03` (3 %) |
| Mindest-Edge | `Edge ≥ 0.02` |
| Sharp-Referenz vorhanden | nur Märkte, die auch in The Odds API existieren |
| Zeitfenster | nicht zu früh (Linien unreif), nicht zu spät |
| KI-Confidence | ≥ Schwelle, sonst Signal nur "info" |

> **Kein Einsatz-/Bankroll-Vorschlag.** Der Bot empfiehlt bewusst **keine** Stakes oder Kelly-Größen — er liefert ausschließlich den Value (Pick, Quote, faire Quote, EV %, Edge, Grund). Was du daraus machst, ist deine Sache.

---

## 6. Schicht 5 — Parlay / Kombi-Builder

Kombis sind erlaubt. Logik:

1. Kandidaten = alle Einzel-Legs, die den Value-Filter (§5) bestehen.
2. **Nur (möglichst) unabhängige Legs** kombinieren — keine zwei Wetten aus demselben Spiel (korreliert) ohne korrekte Korrelationsbehandlung.
3. Kombinierte Größen:

```
odds_combo  = Π odds_i
p_combo     = Π p_true_i           (bei Unabhängigkeit)
EV_combo    = p_combo × odds_combo − 1
```

4. Begrenzung: max. N Legs (z.B. 2–4 — je mehr Legs, desto höher die Varianz und Fehlerfortpflanzung).
5. Nur Kombis ausgeben, deren `EV_combo` über einer **höheren** Schwelle liegt als Einzelwetten (z.B. ≥ 8 %), weil sich Unsicherheiten multiplizieren.

> Hinweis: Value-Kombis sind mathematisch nur dann sinnvoll, wenn **jedes** Leg für sich Value hat. Der Bot baut deshalb Kombis *ausschließlich* aus bereits validierten +EV-Legs — niemals Value-Leg + "Auffüller".

---

## 7. Schicht 6 — Telegram-Signal

**Bot-Setup:** via `@BotFather` Token holen, `python-telegram-bot`. User abonniert per `/start`; Chat-IDs in DB.

**Signal-Format (Beispiel):**

```
🟢 VALUE DETECTED — MLB
Yankees @ Dodgers · heute 02:10

Pick:  Dodgers Moneyline
yeet:  1.95
Fair:  1.80  (p_true 55.6%)
Edge:  +5.1 %   |   EV: +8.3 %

Grund: Pinnacle-Linie 1.82, bestätigtes
Lineup, Yankees-Closer angeschlagen.
Confidence: hoch
```

**Funktionen:**

- **Dedup** über Redis (kein Spam bei jedem Poll, nur bei *neuem* oder *verbessertem* Value).
- Befehle: `/value` (aktuelle Top-Signale), `/sport fussball`, `/minev 5`, `/stop`.
- **Re-Alert**, wenn sich eine Quote zu deinen Gunsten bewegt.
- Throttle + Prioritäts-Sortierung nach EV.

---

## 8. Schicht 7 — Persistenz & Validierung (das Wichtigste für Vertrauen)

Ohne Tracking weiß niemand, ob der Bot wirklich Value findet. Pflicht-Komponenten:

- **Odds-Historie** (Zeitreihe je Markt) → erlaubt **CLV-Messung** (Closing Line Value): War unsere Quote besser als die Schlussquote? **CLV ist der beste Frühindikator für langfristigen Profit** — viel schneller aussagekräftig als ROI.
- **Signal-Log:** jedes ausgegebene Signal mit p_true, EV, Quote, Zeitpunkt.
- **Result-Ingestion:** Endergebnisse holen, Signale settlen (Gewinn/Verlust).
- **Dashboards/Reports:** ROI, Trefferquote, CLV-Verteilung, EV-Realisierung — wöchentlich per Telegram.
- **Backtest-Harness:** Engine gegen historische Odds laufen lassen, um die Filter zu kalibrieren.

> **Vertrauens-Kriterium:** Erst nach 2–4 Wochen **Tracking** mit positivem CLV den Signalen ernsthaft trauen. Der Bot beweist sich an der Schlusslinie (war yeet.com-Quote besser als die spätere faire Schlussquote?), nicht an einzelnen Treffern. Da kein Geld im Spiel ist, ist das reines Mitschreiben — kostet nichts, sagt aber alles über die Qualität der Signale.

---

## 9. Infrastruktur (Hetzner + GitHub)

**Repo-Struktur:**

```
value-bot/
├─ sources/        the_odds_api/ , yeet/  (onchain|frontend|scraper)
├─ normalize/      entity-resolution, mappings
├─ engine/         novig.py, ki_adjust.py, value.py, parlay.py
├─ alerts/         telegram.py, formatting.py
├─ storage/        models.py (SQLAlchemy), migrations/
├─ scheduler/      jobs.py (APScheduler)
├─ backtest/
├─ config/         settings, thresholds (.env)
├─ tests/
├─ docker-compose.yml
└─ .github/workflows/  ci.yml, deploy.yml
```

**Hetzner-Setup:**

- Cloud-VPS (z.B. CX22/CPX21), Ubuntu, Docker + docker-compose.
- Container: `app`, `postgres`, `redis`, `scheduler`.
- **Secrets** in `.env` / Hetzner-Secrets, **nie** ins Repo (The-Odds-API-Key, Telegram-Token, ggf. RPC-Endpoint für yeet-On-Chain). `.gitignore` strikt.
- **Proxies** nur falls yeet.com doch gescraped werden muss — bei On-Chain/Frontend-API unnötig.
- **Monitoring:** Healthchecks, Uptime-Ping, Fehler-Alerts auf eigenen Telegram-Kanal, Log-Rotation.

**GitHub + Claude Code:**

- Privates Repo. Claude Code arbeitet auf Branches → PR → CI (Tests) → Merge.
- GitHub Actions: bei Merge auf `main` automatisch `ssh deploy` + `docker-compose up -d --build` auf Hetzner.
- Klare `CLAUDE.md` im Repo mit Konventionen, Test-Befehlen, Architektur — damit Claude Code konsistent baut.

---

## 10. Bau-Roadmap (Phasen für Claude Code)

| Phase | Inhalt | Ziel / "Definition of Done" |
|---|---|---|
| **0. Fundament** | Repo, Docker, Postgres, Redis, CLAUDE.md, CI | `docker-compose up` läuft, Tests grün |
| **1. yeet.com erschließen** | On-Chain/Subgraph/Frontend prüfen, Quoten in DB | yeet-Quoten landen normalisiert in DB |
| **2. Sharp-Linie anbinden** | The Odds API (Pinnacle) → DB, Event-Matching yeet↔Sharp | Beide Quellen pro Event gematcht |
| **3. No-Vig Engine + Filter** | Faire p, EV, Quote-≥1.5-Filter | Erste echte Value-Liste in Logs |
| **4. Telegram-Output** | Bot, Format, Dedup, Befehle | Signale kommen aufs Handy |
| **5. KI-Adjustierung** | News/Lineup-Ingestion, Claude-Delta, Kappung | p_true berücksichtigt Aufstellungen |
| **6. Parlay-Builder** | Kombis aus +EV-Legs | Valide Kombi-Signale |
| **7. Alle Sportarten** | weitere Ligen/Sportarten ausrollen | Breite Abdeckung |
| **8. Tracking & Backtest** | CLV, Trefferquote, Reports | Beweisbarer Edge an der Schlusslinie |

---

## 11. Risiken & Gegenmaßnahmen

| Risiko | Maßnahme |
|---|---|
| Phantom-Value durch schlechtes Matching | Strenge Normalisierung + Sharp-Referenzpflicht (§3) |
| LLM überschätzt Edge | Delta-Kappung, Liniendynamik-Check, Confidence-Gate (§4.2) |
| yeet.com-Datenzugriff bricht | On-Chain/Subgraph bevorzugen (stabiler als Scraping), Modul isolieren |
| yeet-Märkte ohne Sharp-Pendant | Solche Events filtern — ohne faire Referenz kein Signal |
| The-Odds-API-Limit (Free-Tier) | Nur Pinnacle-Märkte abfragen, Caching, sinnvolle Polling-Intervalle |
| Überschätztes Vertrauen in Signale | CLV-Tracking, bevor man den Signalen traut (§8) |
| Rechtliches | Bot **wettet nicht** und bewegt **kein Geld** — reine Info; je nach Land Glücksspielrecht selbst prüfen |

---

## 12. Offene Punkte für dich

1. **yeet.com-Datenzugang:** Wickelt yeet.com Wetten on-chain ab (gibt es Contract-Adressen / einen Subgraph)? Falls du das weißt, spart es Claude Code die Erkundung. Sonst inspiziert der Bot es selbst (Phase 1).
2. **The Odds API Free-Tier reicht?** Zum Start ja. Wenn viele Sportarten parallel + häufiges Polling gewünscht sind, kann das Monats-Limit knapp werden — dann später Bezahl-Tier.
3. **Welche Sportarten zuerst?** "Alle" ist das Ziel, aber Phase 1–6 baut man am besten an *einer* Sportart fertig (Vorschlag: die mit der besten yeet.com-Abdeckung) und rollt dann aus.

---

*Dieser Plan ist die Bau-Spezifikation. Nächster Schritt: Repo + Phase 0/1 von Claude Code aufsetzen lassen — sag Bescheid, wenn ich direkt das `CLAUDE.md` + die Repo-Struktur als Startpaket schreiben soll.*
