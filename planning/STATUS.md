# FinAlly — status prac zespołu agentów

Prowadzi: team-lead. Plik aktualizowany przy każdym raporcie. Źródło prawdy kontraktów: `planning/API.md`, `planning/API_CHAT.md`, `planning/PLAN.md`.

Gałąź: `AgentTeams`. Ostatni checkpoint: `cf0edac` (frontend: wszystkie widoki). Snapshot po awarii: `f60f1ea`.

## Stan obszarów

| Obszar | Właściciel | Stan | Ostatnia weryfikacja | Blokery |
|---|---|---|---|---|
| Kontrakty (API.md, API_CHAT.md, PLAN §13) | team-lead | gotowe | 2026-11-28 | — |
| Warstwa DB (`backend/app/db/`) | backend-engineer | gotowe | 2026-11-28: testy db przechodzą | — |
| API / serwisy / `main.py` | backend-engineer | prawie gotowe | 2026-11-28: `ruff format --check` OK (65 plików) | — |
| LLM / czat (`backend/app/llm/`) | llm-engineer | w toku — brak `router.py`, serwisu czatu, testów `tests/llm/`; 1 błąd ruff (BLE001 `app/llm/client.py:58`) | 2026-11-28: 16 testów integracyjnych czatu nie przechodzi (`/api/chat` → 405) | — |
| Frontend (`frontend/`) | frontend-engineer | wszystkie widoki napisane (watchlist, wykres główny, P&L, heatmapa, pozycje, pasek transakcji, czat, header); brak testów vitest | 2026-11-28 team-lead: `npm run build` OK (out/index.html), `npm run lint` czysty | testy vitest i ręczna weryfikacja z backendem w toku |
| Docker / skrypty | devops-engineer | obraz z pełnym UI buduje się i działa (582 MB); poprawki w Dockerfile i skryptach zatwierdzone | 2026-11-28 (raport devops, rebuild z UI): health, UI terminala, SSE, trwałość wolumenu, `docker stop` 3 s, non-root, skrypty idempotentne; team-lead: parse-check skryptów .ps1 OK, tryb 100755 dla .sh | finalny rebuild po `/api/chat` |
| E2E (`test/`) | integration-tester | w toku — specyfikacje 01–06 istnieją | nie uruchomiono | czeka na frontend, `/api/chat`, obraz Docker |

### Wyniki weryfikacji backendu (2026-11-28, team-lead)

- `uv run pytest -q`: **16 failed, 187 passed, 1 skipped** (180 s). Wszystkie porażki to czat: `tests/integration/test_chat_flow.py`, `test_fresh_start.py::test_chat_history_starts_empty`, `test_persistence.py::test_restart_keeps_portfolio_watchlist_chat_and_history`.
- `uv run ruff check .`: 1 błąd — `app/llm/client.py:58:16 BLE001`.
- `uv run ruff format --check .`: OK.

## Następne kroki

1. llm-engineer: `app/llm/router.py` + serwis czatu wg `API_CHAT.md`, testy w `tests/llm/`, naprawa BLE001. Cel: 0 failed w backendzie.
2. frontend-engineer: wszystkie elementy UI z PLAN §10, testy vitest, `npm run build` / `npx vitest run` / `npm run lint` zielone.
3. devops-engineer: finalny rebuild i weryfikacja po gotowym `/api/chat` i testach frontendu (obraz z UI już zweryfikowany).
4. integration-tester: uruchomić E2E przeciw kontenerowi (`LLM_MOCK=true`).
5. team-lead: checkpoint commit po każdym zweryfikowanym kamieniu milowym.

## Dziennik

- **2026-11-28** — devops-engineer: rebuild z nowym frontendem OK. Obraz ma 582 MB (wcześniej 906 MB). W obrazie nie ma `.env`. Przez `start_windows.ps1`: health 200, `/` serwuje UI terminala, SSE OK, trwałość wolumenu `finally-data` potwierdzona (historia snapshotów przetrwała restart), stop trwa 2–3 s. Czeka na finalny rebuild po `/api/chat`.

- **2026-11-28** — frontend-engineer: wszystkie widoki gotowe (Lightweight Charts v5, treemap na divach, hook SSE ze statusem połączenia). team-lead zweryfikował: build i lint zielone. Commit checkpointu. Odblokowano rebuild Dockera (devops) i E2E UI (integration-tester).

- **2026-11-28** — devops-engineer, faza 1: obraz `finally:latest` zbudowany i zweryfikowany w kontenerze testowym (health, `/` → HTML, SSE ze snapshotem, zakup 3 AAPL przetrwał stop/start, `docker stop` 3 s, uid 1000, HEALTHCHECK healthy, shellcheck czysty). Poprawki: cache uv w BuildKit mount (obraz 906 MB, w tym 349 MB cache; nowego rozmiaru jeszcze nie zmierzono), `stop_windows.ps1` kończy się kodem 0, skrypty start kończą się kodem 1, jeśli health nie odpowie w 30 s, `chmod +x` dla .sh. Bloker: frontend w trakcie edycji nie buduje się (`Can't resolve '@/components/Terminal'`). Uwagi dla backendu: hałaśliwy traceback CancelledError z SSE przy zamykaniu (niekrytyczny).

- **2026-11-28** — frontend-engineer: opublikował kontrakt `data-testid` (header, watchlist, wykresy, heatmapa, pozycje, pasek transakcji, czat). team-lead przekazał go integration-testerowi. Frontend zaczyna od layoutu i SSE.
- **2026-11-28** — PLAN §12/§13 zaktualizowany: test „SSE resilience” zastąpiony testem wskaźnika połączenia (blokada `/api/stream/prices` w przeglądarce, bez restartu serwera; `test/e2e/06-connection.spec.ts`).
- **2026-11-28** — team-lead: start drugiego przebiegu po awarii. Zweryfikowano stan backendu (wyniki wyżej). Utworzono STATUS.md. Rozesłano zadania.
