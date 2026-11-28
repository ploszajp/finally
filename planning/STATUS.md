# FinAlly — status prac zespołu agentów

Prowadzi: team-lead. Plik aktualizowany przy każdym raporcie. Źródło prawdy kontraktów: `planning/API.md`, `planning/API_CHAT.md`, `planning/PLAN.md`.

Gałąź: `AgentTeams`. **Stan: UKOŃCZONE (2026-11-28).** Końcowy commit kodu: `947a576`. Snapshot po awarii: `f60f1ea`.

## Stan obszarów

| Obszar | Właściciel | Stan | Ostatnia weryfikacja | Blokery |
|---|---|---|---|---|
| Kontrakty (API.md, API_CHAT.md, PLAN §12/§13) | team-lead | gotowe | 2026-11-28 | — |
| Warstwa DB (`backend/app/db/`) | backend-engineer | gotowe | 2026-11-28 team-lead: pełny pytest zielony | — |
| API / serwisy / `main.py` | backend-engineer | gotowe (w tym czyste zamykanie SSE: 0,2 s, bez tracebacku) | 2026-11-28 team-lead: pełny pytest zielony, ruff czysty | — |
| LLM / czat (`backend/app/llm/`) | llm-engineer | gotowe — router, serwis, 54 testy w `tests/llm/`; test z prawdziwym kluczem OK (9,9 s, poprawny structured output) | 2026-11-28 team-lead: **217 passed, 1 skipped**, `ruff check` i `ruff format --check` czyste (72 pliki) | — |
| Frontend (`frontend/`) | frontend-engineer | gotowe; sprawdzone ręcznie w przeglądarce z backendem (mock), także szerokość tabletu | 2026-11-28 team-lead: `npx vitest run` **39/39**, `npm run lint` czysty, `npm run build` OK | — |
| Docker / skrypty | devops-engineer | gotowe — obraz 582 MB, bez `.env` w obrazie, non-root | 2026-11-28 (raport devops): health, UI, SSE, `/api/chat` (mock), trwałość wolumenu `finally-data`, `docker stop` 2–4 s, skrypty idempotentne; team-lead: parse-check `.ps1`, tryb 100755 dla `.sh` | — |
| E2E (`test/`) | integration-tester | gotowe — **24/24 w Dockerze na HEAD `947a576`** | 2026-11-28 (raport): `build --no-cache finally-app` + `up --abort-on-container-exit --exit-code-from playwright` → **24 passed (30,6 s)**, exit 0, 0 flaky (wcześniej na `c5e50ee`: 24 passed, 36,8 s); team-lead: `tsc --noEmit` w test/ OK | — |

### Wyniki weryfikacji (team-lead)

- Backend (`947a576`): `uv run pytest -q` **275 passed, 1 skipped** (276 s; pominięty test SIGTERM tylko dla POSIX); `ruff check .` All checks passed; `ruff format --check .` 73 files already formatted. (Wcześniej na `5d84ee6`: 217 passed.)
- Frontend (`41edfac`): vitest 39/39, lint czysty, build OK.
- Na starcie przebiegu: 16 failed / 187 passed (brak routera czatu), 1 błąd ruff (BLE001).

## Znane drobne problemy / dalsze kroki

1. ~~Traceback CancelledError z SSE przy `docker stop`~~ — naprawione w `947a576` (decyzja użytkownika: zachować poprawkę).
2. Czat z prawdziwym LLM sprawdzony jednym wywołaniem; E2E używają trybu mock.
3. Massive API (prawdziwe notowania) — stretch goal, nietestowane bez klucza.
4. Next.js odmawia dwóch równoległych `next build` w `frontend/` — nie budować równolegle.

## Dziennik

- **2026-11-28** — Decyzja użytkownika: zachować poprawkę SSE. team-lead nałożył zapisaną łatkę backend-engineera i zweryfikował ją: pytest 275 passed / 1 skipped, ruff czysty. Commit `947a576`. integration-tester: finalny E2E w Dockerze na `947a576` → **24 passed (30,6 s), exit 0**. Kopia łatki usunięta.

- **2026-11-28** — **Zakończenie.** backend-engineer cofnął niezatwierdzoną poprawkę SSE (łatka zachowana poza repo). Selektor E2E na `position-quantity-{T}` zatwierdzony (`c5e50ee`). integration-tester: finalny E2E w Dockerze na czystym drzewie, obraz budowany od zera → **24 passed (36,8 s), exit 0**. Wszystkie kryteria ukończenia spełnione.

- **2026-11-28** — frontend-engineer: dodał `position-quantity-{T}` w tabeli pozycji. team-lead zweryfikował (vitest 39/39, lint, build; jednorazowa blokada `next build` po poprzednim buildzie, ponowna próba OK). Commit `41edfac`. Decyzja (main): szum CancelledError w SSE zostaje znanym drobnym problemem; backend-engineer cofa niezatwierdzoną zmianę w `stream.py`. Następnie integration-tester przełącza selektor na `position-quantity-{T}` i robi jeden finalny przebieg E2E w Dockerze.

- **2026-11-28** — integration-tester: E2E w Dockerze **24/24** (exit 0, bez retry). Pierwsza próba padła na `ERR_SSL_PROTOCOL_ERROR`: Chromium wymusza HTTPS dla całej domeny `.app` (HSTS preload), więc serwis `app` przemianowano na `finally-app`. To nie był błąd produktu. devops-engineer: `.playwright-mcp/` w `.gitignore`. W toku ostatnie drobne zmiany: `backend/app/market/stream.py` (ciche zamykanie SSE) i `PositionsTable.tsx`. Po nich team-lead robi finalną weryfikację i zamrożenie.

- **2026-11-28** — Raporty zbiorcze: llm-engineer (czat wg API_CHAT.md, 54 testy LLM, test z prawdziwym kluczem OK), backend-engineer (review wg API.md, 3 poprawki: obsługa NaN/Inf w 422, 404 dla nieznanych `/api/*` niezależnie od metody, limit ilości w serwisie; 16 nowych testów), frontend-engineer (vitest 39/39, poprawka „Object is disposed” w wykresie, usuwanie klasy flash po animacji), integration-tester (E2E 24/24 lokalnie, stabilne przy powtórzeniach). team-lead zweryfikował frontend (vitest 39/39, lint, build) i typy E2E. Commit `906ab55`. Uruchomiono finalny przebieg E2E w Dockerze.

- **2026-11-28** — team-lead: backend w całości zielony (217 passed, 1 skipped, ruff czysty). Commit `5d84ee6` (router i serwis czatu, testy LLM, testy brzegowe API). Kolejny etap: testy vitest frontendu i E2E.

- **2026-11-28** — devops-engineer: rebuild z HEAD `9df1c4b` w pełni zweryfikowany (kontener testowy). `docker build --check` bez ostrzeżeń, `.gitattributes` już wymusza LF dla .sh. W UI jest 29 `data-testid` z kontraktu. Trwałość: zakup 2 NVDA i dodanie PYPL przetrwały stop/start. `docker stop` 3,9 s przy otwartym SSE. **`/api/chat` działa już w obrazie** (mock: 200, `actions.error: null`). Strona Dockera nie ma otwartych zadań; zostaje jedynie niegroźny szum w logach (CancelledError z SSE).

- **2026-11-28** — devops-engineer: rebuild z nowym frontendem OK. Obraz ma 582 MB (wcześniej 906 MB). W obrazie nie ma `.env`. Przez `start_windows.ps1`: health 200, `/` serwuje UI terminala, SSE OK, trwałość wolumenu `finally-data` potwierdzona (historia snapshotów przetrwała restart), stop trwa 2–3 s. Czeka na finalny rebuild po `/api/chat`.

- **2026-11-28** — frontend-engineer: wszystkie widoki gotowe (Lightweight Charts v5, treemap na divach, hook SSE ze statusem połączenia). team-lead zweryfikował: build i lint zielone. Commit checkpointu. Odblokowano rebuild Dockera (devops) i E2E UI (integration-tester).

- **2026-11-28** — devops-engineer, faza 1: obraz `finally:latest` zbudowany i zweryfikowany w kontenerze testowym (health, `/` → HTML, SSE ze snapshotem, zakup 3 AAPL przetrwał stop/start, `docker stop` 3 s, uid 1000, HEALTHCHECK healthy, shellcheck czysty). Poprawki: cache uv w BuildKit mount (obraz 906 MB, w tym 349 MB cache; nowego rozmiaru jeszcze nie zmierzono), `stop_windows.ps1` kończy się kodem 0, skrypty start kończą się kodem 1, jeśli health nie odpowie w 30 s, `chmod +x` dla .sh. Bloker: frontend w trakcie edycji nie buduje się (`Can't resolve '@/components/Terminal'`). Uwagi dla backendu: hałaśliwy traceback CancelledError z SSE przy zamykaniu (niekrytyczny).

- **2026-11-28** — frontend-engineer: opublikował kontrakt `data-testid` (header, watchlist, wykresy, heatmapa, pozycje, pasek transakcji, czat). team-lead przekazał go integration-testerowi. Frontend zaczyna od layoutu i SSE.
- **2026-11-28** — PLAN §12/§13 zaktualizowany: test „SSE resilience” zastąpiony testem wskaźnika połączenia (blokada `/api/stream/prices` w przeglądarce, bez restartu serwera; `test/e2e/06-connection.spec.ts`).
- **2026-11-28** — team-lead: start drugiego przebiegu po awarii. Zweryfikowano stan backendu (wyniki wyżej). Utworzono STATUS.md. Rozesłano zadania.
