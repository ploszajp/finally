# FinAlly — status prac zespołu agentów

Prowadzi: team-lead. Plik aktualizowany przy każdym raporcie. Źródło prawdy kontraktów: `planning/API.md`, `planning/API_CHAT.md`, `planning/PLAN.md`.

Gałąź: `AgentTeams`. Ostatni checkpoint: `f60f1ea` (snapshot po awarii pierwszego przebiegu).

## Stan obszarów

| Obszar | Właściciel | Stan | Ostatnia weryfikacja | Blokery |
|---|---|---|---|---|
| Kontrakty (API.md, API_CHAT.md, PLAN §13) | team-lead | gotowe | 2026-11-28 | — |
| Warstwa DB (`backend/app/db/`) | backend-engineer | gotowe | 2026-11-28: testy db przechodzą | — |
| API / serwisy / `main.py` | backend-engineer | prawie gotowe | 2026-11-28: `ruff format --check` OK (65 plików) | — |
| LLM / czat (`backend/app/llm/`) | llm-engineer | w toku — brak `router.py`, serwisu czatu, testów `tests/llm/`; 1 błąd ruff (BLE001 `app/llm/client.py:58`) | 2026-11-28: 16 testów integracyjnych czatu nie przechodzi (`/api/chat` → 405) | — |
| Frontend (`frontend/`) | frontend-engineer | w toku — są pierwsze komponenty (Header, Watchlist, Sparkline, TimeSeriesChart, usePriceStream, lib/*) | nie zweryfikowano | — |
| Docker / skrypty | devops-engineer | pliki istnieją, obraz nigdy nie zbudowany | nie zweryfikowano | czeka na build frontendu |
| E2E (`test/`) | integration-tester | w toku — specyfikacje 01–06 istnieją | nie uruchomiono | czeka na frontend, `/api/chat`, obraz Docker |

### Wyniki weryfikacji backendu (2026-11-28, team-lead)

- `uv run pytest -q`: **16 failed, 187 passed, 1 skipped** (180 s). Wszystkie porażki to czat: `tests/integration/test_chat_flow.py`, `test_fresh_start.py::test_chat_history_starts_empty`, `test_persistence.py::test_restart_keeps_portfolio_watchlist_chat_and_history`.
- `uv run ruff check .`: 1 błąd — `app/llm/client.py:58:16 BLE001`.
- `uv run ruff format --check .`: OK.

## Następne kroki

1. llm-engineer: `app/llm/router.py` + serwis czatu wg `API_CHAT.md`, testy w `tests/llm/`, naprawa BLE001. Cel: 0 failed w backendzie.
2. frontend-engineer: wszystkie elementy UI z PLAN §10, testy vitest, `npm run build` / `npx vitest run` / `npm run lint` zielone.
3. devops-engineer: zbudować obraz, sprawdzić health, UI, SSE, trwałość wolumenu (po zielonym buildzie frontendu).
4. integration-tester: uruchomić E2E przeciw kontenerowi (`LLM_MOCK=true`).
5. team-lead: checkpoint commit po każdym zweryfikowanym kamieniu milowym.

## Dziennik

- **2026-11-28** — team-lead: start drugiego przebiegu po awarii. Zweryfikowano stan backendu (wyniki wyżej). Utworzono STATUS.md. Rozesłano zadania.
