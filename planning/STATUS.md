# FinAlly — status prac zespołu agentów

Prowadzi: team-lead. Plik aktualizowany przy każdym raporcie. Źródło prawdy kontraktów: `planning/API.md`, `planning/API_CHAT.md`, `planning/PLAN.md`.

Gałąź: `AgentTeams`. Ostatni checkpoint: `cf0edac` (frontend: wszystkie widoki). Snapshot po awarii: `f60f1ea`.

## Stan obszarów

| Obszar | Właściciel | Stan | Ostatnia weryfikacja | Blokery |
|---|---|---|---|---|
| Kontrakty (API.md, API_CHAT.md, PLAN §13) | team-lead | gotowe | 2026-11-28 | — |
| Warstwa DB (`backend/app/db/`) | backend-engineer | gotowe | 2026-11-28: testy db przechodzą | — |
| API / serwisy / `main.py` | backend-engineer | gotowe (opcjonalnie: wyciszenie CancelledError SSE przy zamykaniu) | 2026-11-28 team-lead: pełny pytest zielony, ruff czysty | — |
| LLM / czat (`backend/app/llm/`) | llm-engineer | gotowe — router, serwis, 54 testy w `tests/llm/`; test z prawdziwym kluczem OK (9,9 s, poprawny structured output) | 2026-11-28 team-lead: **217 passed, 1 skipped**, `ruff check` i `ruff format --check` czyste (72 pliki) | — |
| Frontend (`frontend/`) | frontend-engineer | gotowe; sprawdzone ręcznie w przeglądarce z backendem (mock) | 2026-11-28 team-lead: `npx vitest run` **39/39**, `npm run lint` czysty, `npm run build` OK | — |
| Docker / skrypty | devops-engineer | obraz z pełnym UI buduje się i działa (582 MB); poprawki w Dockerfile i skryptach zatwierdzone | 2026-11-28 (raport devops, rebuild z UI): health, UI terminala, SSE, trwałość wolumenu, `docker stop` 3 s, non-root, skrypty idempotentne; team-lead: parse-check skryptów .ps1 OK, tryb 100755 dla .sh | finalny rebuild po `/api/chat` |
| E2E (`test/`) | integration-tester | 24 testy (01–06) zielone lokalnie; trwa finalny przebieg przez `docker-compose.test.yml` | 2026-11-28 (raport): lokalnie 24/24 w 32,5 s, `--repeat-each=3` 57/57; team-lead: `tsc --noEmit` w test/ OK | — |

### Wyniki weryfikacji backendu (2026-11-28, team-lead)

- **Druga weryfikacja:** `uv run pytest -q`: **217 passed, 1 skipped** (401 s); `ruff check .`: All checks passed; `ruff format --check .`: 72 files already formatted. Commit `5d84ee6`.
- Pierwsza weryfikacja (start przebiegu): `uv run pytest -q`: **16 failed, 187 passed, 1 skipped** (180 s). Wszystkie porażki to czat: `tests/integration/test_chat_flow.py`, `test_fresh_start.py::test_chat_history_starts_empty`, `test_persistence.py::test_restart_keeps_portfolio_watchlist_chat_and_history`.
- `uv run ruff check .`: 1 błąd — `app/llm/client.py:58:16 BLE001`.
- `uv run ruff format --check .`: OK.

## Następne kroki

1. integration-tester: finalny przebieg E2E przez `test/docker-compose.test.yml` na obrazie z HEAD (`LLM_MOCK=true`, świeży wolumen testowy).
2. team-lead: po zielonym E2E końcowy commit, finalny STATUS i podsumowanie dla użytkownika.
3. Opcjonalnie: backend-engineer — ciche zamykanie SSE (CancelledError w logach); integration-tester/frontend — `position-quantity-{T}` zamiast selektora po kolumnie.

## Dziennik

- **2026-11-28** — Raporty zbiorcze: llm-engineer (czat wg API_CHAT.md, 54 testy LLM, test z prawdziwym kluczem OK), backend-engineer (review wg API.md, 3 poprawki: obsługa NaN/Inf w 422, 404 dla nieznanych `/api/*` niezależnie od metody, limit ilości w serwisie; 16 nowych testów), frontend-engineer (vitest 39/39, poprawka „Object is disposed” w wykresie, usuwanie klasy flash po animacji), integration-tester (E2E 24/24 lokalnie, stabilne przy powtórzeniach). team-lead zweryfikował frontend (vitest 39/39, lint, build) i typy E2E. Commit `906ab55`. Uruchomiono finalny przebieg E2E w Dockerze.

- **2026-11-28** — team-lead: backend w całości zielony (217 passed, 1 skipped, ruff czysty). Commit `5d84ee6` (router i serwis czatu, testy LLM, testy brzegowe API). Kolejny etap: testy vitest frontendu i E2E.

- **2026-11-28** — devops-engineer: rebuild z HEAD `9df1c4b` w pełni zweryfikowany (kontener testowy). `docker build --check` bez ostrzeżeń, `.gitattributes` już wymusza LF dla .sh. W UI jest 29 `data-testid` z kontraktu. Trwałość: zakup 2 NVDA i dodanie PYPL przetrwały stop/start. `docker stop` 3,9 s przy otwartym SSE. **`/api/chat` działa już w obrazie** (mock: 200, `actions.error: null`). Strona Dockera nie ma otwartych zadań; zostaje jedynie niegroźny szum w logach (CancelledError z SSE).

- **2026-11-28** — devops-engineer: rebuild z nowym frontendem OK. Obraz ma 582 MB (wcześniej 906 MB). W obrazie nie ma `.env`. Przez `start_windows.ps1`: health 200, `/` serwuje UI terminala, SSE OK, trwałość wolumenu `finally-data` potwierdzona (historia snapshotów przetrwała restart), stop trwa 2–3 s. Czeka na finalny rebuild po `/api/chat`.

- **2026-11-28** — frontend-engineer: wszystkie widoki gotowe (Lightweight Charts v5, treemap na divach, hook SSE ze statusem połączenia). team-lead zweryfikował: build i lint zielone. Commit checkpointu. Odblokowano rebuild Dockera (devops) i E2E UI (integration-tester).

- **2026-11-28** — devops-engineer, faza 1: obraz `finally:latest` zbudowany i zweryfikowany w kontenerze testowym (health, `/` → HTML, SSE ze snapshotem, zakup 3 AAPL przetrwał stop/start, `docker stop` 3 s, uid 1000, HEALTHCHECK healthy, shellcheck czysty). Poprawki: cache uv w BuildKit mount (obraz 906 MB, w tym 349 MB cache; nowego rozmiaru jeszcze nie zmierzono), `stop_windows.ps1` kończy się kodem 0, skrypty start kończą się kodem 1, jeśli health nie odpowie w 30 s, `chmod +x` dla .sh. Bloker: frontend w trakcie edycji nie buduje się (`Can't resolve '@/components/Terminal'`). Uwagi dla backendu: hałaśliwy traceback CancelledError z SSE przy zamykaniu (niekrytyczny).

- **2026-11-28** — frontend-engineer: opublikował kontrakt `data-testid` (header, watchlist, wykresy, heatmapa, pozycje, pasek transakcji, czat). team-lead przekazał go integration-testerowi. Frontend zaczyna od layoutu i SSE.
- **2026-11-28** — PLAN §12/§13 zaktualizowany: test „SSE resilience” zastąpiony testem wskaźnika połączenia (blokada `/api/stream/prices` w przeglądarce, bez restartu serwera; `test/e2e/06-connection.spec.ts`).
- **2026-11-28** — team-lead: start drugiego przebiegu po awarii. Zweryfikowano stan backendu (wyniki wyżej). Utworzono STATUS.md. Rozesłano zadania.
