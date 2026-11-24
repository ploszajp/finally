# Review planu FinAlly (PLAN.md)

*Review z 2026-11-24. Uzupełnia sekcję 13 w PLAN.md: tych 10 punktów tu nie powtarzam. Poniżej są luki, sprzeczności i ryzyka, których tam nie ma, a na końcu uwagi do samej sekcji 13. Priorytety: **[B]** blokuje start agentów, **[W]** trzeba ustalić przed implementacją danego modułu, **[N]** drobiazg.*

---

## A. Architektura i runtime

1. **[B] Jeden proces uvicorn.** Cache cen, symulator i zadanie snapshotów żyją w pamięci procesu. Przy `--workers N` każdy worker ma własny symulator: SSE pokazuje inną cenę niż ta, po której wykona się transakcja, a snapshoty zapisują się N razy. W §11 trzeba wpisać: `uvicorn ... --workers 1` i zakaz `--reload` w obrazie produkcyjnym.

2. **[B] Blokowanie event loopa.** Kod ze skilla cerebras używa synchronicznego `litellm.completion`. Wywołany w `async def` zatrzyma cały event loop na czas odpowiedzi LLM (sekundy), więc SSE przestanie wysyłać ceny, a symulator przestanie tykać. To samo dotyczy synchronicznego `sqlite3` w handlerach `async`. Reguła do planu: LLM przez `litellm.acompletion` (albo endpoint zdefiniowany jako `def`, który trafia do threadpoola), a DB w endpointach `def` albo przez `aiosqlite`/`run_in_threadpool`.

3. **[W] Konfiguracja SQLite.** Do zapisu są jednocześnie trzy źródła: endpointy, zadanie snapshotów co 30 s i czat. Sekcja 13 #10 mówi o transakcjach, ale brakuje `PRAGMA journal_mode=WAL`, `busy_timeout` i zasady „jedno połączenie na żądanie” (połączenia `sqlite3` nie wolno współdzielić między wątkami bez `check_same_thread=False`). Brakuje też zmiennej `DB_PATH` (domyślnie `/app/db/finally.db`), bez której testy jednostkowe i lokalny dev piszą do produkcyjnej bazy.

4. **[W] Restart serwera resetuje ceny.** Symulator po restarcie startuje od cen seedowych, a `avg_cost` pozycji pochodzi z poprzedniej sesji. Wynik: P&L i wykres wartości portfela skaczą po każdym restarcie kontenera. Do wyboru: (a) akceptujemy i piszemy to w planie, (b) przy starcie seedujemy symulator ostatnią ceną transakcji/snapshotu z DB, (c) zapisujemy ostatnie ceny w tabeli. Rekomendacja: (b), bo jest tanie.

5. **[W] Cena startowa dla dowolnego tickera.** Plan podaje ceny seedowe tylko dla 10 domyślnych tickerów. Co symulator robi po dodaniu PYPL? Potrzebna reguła, np. słownik ~50 znanych tickerów z cenami, a dla reszty deterministyczna cena z hasha tickera (np. 20–500 USD), zmienność domyślna i brak korelacji.

6. **[B] Cena dostępna od razu po dodaniu tickera.** Sekcja 13 #5b każe najpierw wykonać zmiany watchlisty, potem transakcje. Ale nowy ticker dostaje cenę dopiero w następnym ticku (~500 ms, a z Massive nawet 15 s), więc „dodaj PYPL i kup 10” i tak skończy się błędem „brak ceny”. Wymaganie: `add_ticker()` synchronicznie wstawia cenę początkową do cache (w symulatorze od razu, w Massive przez jednorazowe zapytanie). To samo dla ręcznego `POST /api/watchlist`, który i tak ma zwracać najnowszą cenę.

7. **[W] Parametry GBM.** „~500 ms” i „configurable drift/volatility” bez jednostek łatwo daje albo zamrożone, albo eksplodujące ceny. Trzeba zapisać, że σ i μ są roczne, a `dt = 0.5 / (252 * 6.5 * 3600)` (lub świadomie przyspieszony czas, np. ×N dla efektu demo). Do tego mechanizm korelacji (np. wspólny czynnik sektorowy albo Cholesky), częstotliwość „eventów” (np. p≈0.001 na tick na ticker) i zaokrąglanie cen do centów.

8. **[W] Limit watchlisty.** LLM ma „proaktywnie zarządzać watchlistą”, a limitu brak. Proponuję maks. ~30 tickerów (błąd po przekroczeniu) i regułę w prompcie, że LLM dodaje tylko na prośbę użytkownika albo z wyraźnym uzasadnieniem.

## B. SSE i dane w czasie rzeczywistym

9. **[W] Szczegóły techniczne SSE, poza formatem z sekcji 13 #2:**
   - nagłówki `Cache-Control: no-cache`, `X-Accel-Buffering: no`; **nie** dodawać `GZipMiddleware` do całej aplikacji, bo buforuje strumień;
   - heartbeat (komentarz `: ping` co ~15 s), żeby proxy (App Runner, Render) nie zrywały bezczynnego połączenia, co jest ważne przy Massive z odświeżaniem co 15 s;
   - pole `retry:` (np. 2000 ms) dla EventSource;
   - wykrywanie rozłączenia klienta (`request.is_disconnected()` albo `sse-starlette`) i krótki `timeout_graceful_shutdown` w uvicorn, bo otwarte strumienie potrafią przytrzymać zatrzymanie kontenera aż do SIGKILL.

10. **[W] Duplikaty przy Massive.** SSE wysyła co ~500 ms, a Massive odświeża co 15 s. Żeby flash nie odpalał się bez zmiany ceny, trzeba ustalić, czy serwer wysyła tylko tickery ze zmienioną ceną (wtedy kierunek „flat” nie występuje), czy wszystko, a frontend porównuje sam. Rekomendacja: wysyłać tylko zmiany, a pełny stan tylko przy (re)connect.

11. **[W] Wskaźnik połączenia: mapowanie stanów.** `EventSource` przechodzi w `CLOSED` tylko przy odpowiedzi innej niż 200 lub złym content-type. Przy padniętym serwerze zostaje w `CONNECTING` w nieskończoność, więc „czerwony” praktycznie nigdy się nie pokaże. Trzeba zdefiniować regułę, np. żółty = `CONNECTING` krócej niż 10 s, czerwony = dłużej niż 10 s albo `CLOSED` (wtedy ręczny reconnect z backoffem).

12. **[W] Pusty wykres główny po wejściu na stronę.** Sparkline'y i wykres wybranego tickera budują się wyłącznie z SSE od załadowania strony. Po odświeżeniu albo kliknięciu tickera przez pierwsze minuty wykres jest pusty, co psuje wrażenie z demo i utrudnia test E2E. Rekomendacja: backend trzyma w cache ring buffer (np. ostatnie 300 punktów na ticker) i wystawia `GET /api/prices/{ticker}/history` albo dołącza bufor do pierwszego zdarzenia SSE.

13. **[W] Kto liczy wartość „live”?** Nagłówek ma pokazywać wartość portfela aktualizowaną na żywo, ale `/api/portfolio` to snapshot. Do ustalenia: frontend przelicza `cash + Σ qty × cena_z_SSE` (rekomendowane, bez dodatkowego ruchu) czy co N sekund odpytuje `/api/portfolio`. To samo dotyczy P&L w tabeli pozycji i heatmapy.

14. **[W] Odświeżanie stanu po akcjach czatu.** Po odpowiedzi `/api/chat` z wykonanymi transakcjami albo zmianami watchlisty frontend musi ponownie pobrać portfolio, watchlistę i historię. Trzeba to zapisać jako kontrakt, np. „jeśli `actions` niepuste, odśwież wszystkie trzy zasoby”, albo zwracać nowy stan portfela w odpowiedzi czatu.

## C. Dane i historia

15. **[W] Retencja `portfolio_snapshots`.** Co 30 s to ~2900 wierszy dziennie, bez ograniczenia. `GET /api/portfolio/history` nie ma parametrów zakresu ani limitu. Proponuję `?limit=` lub `?since=`, domyślnie ostatnie 24 h, i ewentualny downsampling po stronie serwera. Do tego: snapshot co 30 s ma się nie zapisywać, dopóki cache nie ma cen dla wszystkich pozycji (inaczej przy starcie zapisze się zaniżona wartość).

16. **[N] Niespójność schematu.** §7 mówi „wszystkie tabele mają kolumnę `user_id`”, a `users_profile` jej nie ma (używa `id`). Wystarczy dopisać wyjątek.

17. **[N] Znaczniki czasu w całym systemie.** Sekcja 13 #2 ustala format tylko dla SSE. Proponuję jedną regułę dla DB, API i SSE: ISO 8601 UTC z `Z`, a frontend konwertuje na czas lokalny. Lightweight Charts oczekuje sekund epoch (`UTCTimestamp`), więc konwersja ma być po stronie frontendu.

18. **[N] Pieniądze jako `REAL`.** Sekcja 13 #10 proponuje zaokrąglanie. Uzupełnienie: przy porównaniach („czy wystarczy gotówki”, „czy sprzedaż całej pozycji”) używać tolerancji (np. `1e-6`), bo inaczej sprzedaż „wszystkich” 0.3 akcji kupionych jako 0.1+0.2 zostawi wiersz z ilością rzędu 1e-17.

## D. LLM

19. **[W] Routing providera.** Skill ustawia `{"provider": {"order": ["cerebras"]}}` bez `allow_fallbacks: false`. Gdy Cerebras jest niedostępny, OpenRouter po cichu przełączy się na innego providera (wolniejszego, być może bez wsparcia `json_schema`). Trzeba świadomie wybrać: fallback dozwolony (i wtedy obsłużyć niepoprawny JSON, patrz sekcja 13 #6) albo `allow_fallbacks: false` i jasny błąd.

20. **[W] Kontekst dla LLM.** Plan nie określa formatu kontekstu portfela (JSON czy tabela tekstowa) ani tego, że LLM dostaje ceny, więc może przeliczyć „kup za 500 USD” na `quantity`. Zapisać: kontekst jako zwięzły JSON z cenami, ilościami, P&L i gotówką; LLM zawsze podaje `quantity` w akcjach (ułamkowe dozwolone, zaokrąglone do 4 miejsc).

21. **[W] Typy w schemacie.** W schemacie strict użyć `enum` dla `side` (buy/sell) i `action` (add/remove) oraz `additionalProperties: false`. Pydantic z `Literal[...]` to wygeneruje. Ograniczenia typu `minimum`/`gt` nie zawsze są wspierane w strict mode providerów, więc walidację `quantity > 0` zostawić w kodzie, nie w schemacie.

22. **[N] Model rozumujący.** `gpt-oss-120b` generuje tokeny reasoning. Skill używa `reasoning_effort="low"`; warto wpisać to do planu jako wymaganie (latencja) i ustawić timeout wywołania (np. 30 s).

## E. Frontend i build

23. **[B] Workflow developerski bez Dockera.** Plan opisuje tylko obraz produkcyjny. W dev frontend (`next dev`, port 3000) i backend (port 8000) to różne originy, a `rewrites` w `next.config` nie działają z `output: 'export'`. Do ustalenia: (a) w dev zmienna `NEXT_PUBLIC_API_BASE=http://localhost:8000` plus CORS włączony w FastAPI tylko w trybie dev, albo (b) `rewrites` warunkowo tylko w trybie development. Uwaga: proxy `next dev` potrafi buforować SSE, więc dla EventSource bezpieczniej łączyć się bezpośrednio z :8000.

24. **[W] Serwowanie eksportu Next.js przez FastAPI.** Doprecyzować: `StaticFiles(directory="static", html=True)` montowany na `/` **po** wszystkich routerach `/api`. Nieznane `/api/*` muszą zwracać JSON 404, nie `index.html`. W Next ustawić `images: { unoptimized: true }` (eksport nie wspiera optymalizacji obrazów) i ewentualnie `trailingSlash`.

25. **[W] Heatmapa: definicje.** (a) Czy gotówka jest prostokątem w heatmapie i czy wchodzi do mianownika „wagi”? (b) Skala koloru: P&L % względem `avg_cost`, nasycenie obcięte np. do ±10%, szary dla 0. (c) Stan pusty (brak pozycji) też wymaga projektu, bo tak wygląda pierwsze uruchomienie.

26. **[W] Konwencja selektorów dla E2E.** Agenci frontendu i testów potrzebują wspólnego kontraktu `data-testid` (np. `watchlist-row-{TICKER}`, `price-{TICKER}`, `cash-balance`, `portfolio-total`, `trade-ticker`, `trade-qty`, `btn-buy`, `btn-sell`, `chat-input`, `chat-message`, `connection-status` z atrybutem `data-state`). Najlepiej dopisać listę do `planning/API.md` albo osobnego pliku.

27. **[N] Licencja Lightweight Charts.** Wymaga atrybucji TradingView (domyślnie logo w wykresie, opcja `attributionLogo`). Warto o tym wspomnieć, żeby agent nie wyłączył atrybucji bez dodania linku.

## F. Testy

28. **[B] Determinizm symulatora w E2E.** Losowe ceny i „eventy” 2–5% utrudniają asercje typu „gotówka spadła o X”. Potrzebne: zmienna `SIM_SEED` (deterministyczny generator) i/lub `SIM_EVENTS=false`, a testy porównują gotówkę z ceną zwróconą w odpowiedzi transakcji, a nie z ceną odczytaną z UI chwilę wcześniej.

29. **[B] Izolacja stanu między testami.** Baza jest trwała, więc testy zależą od kolejności (kupno w jednym teście zmienia saldo w „Fresh start”). Do wyboru: świeży wolumen/plik DB na każde uruchomienie `docker-compose.test.yml` plus testy, które nie zakładają stanu początkowego, albo endpoint `POST /api/test/reset` dostępny tylko w trybie testowym (`TEST_MODE=true`).

30. **[N] Healthcheck.** `python:3.12-slim` nie ma `curl`. `HEALTHCHECK` w Dockerfile/compose musi używać Pythona (`urllib.request`) albo trzeba doinstalować curl. Playwright w compose powinien czekać na `service_healthy`.

## G. Bezpieczeństwo i deployment

31. **[W] Wdrożenie w chmurze bez auth.** §11 sugeruje App Runner/Render. Publiczny URL bez logowania oznacza, że każdy może zużywać kredyt OpenRouter przez `/api/chat` i modyfikować jedyny portfel. Zapisać: deploy publiczny tylko z basic auth / tokenem w env albo z rate limitem czatu, a lokalnie mapować port na `127.0.0.1:8000:8000`.

32. **[N] Higiena repo.** (a) `db/` nie zawiera `.gitkeep` (git nie śledzi pustych katalogów), a `.gitignore` nie ignoruje `db/*.db`, `*.db-wal`, `*.db-shm`. (b) Brak `.env.example`, o którym mówi §4. (c) Pusty katalog „Nowy folder” w korzeniu do usunięcia. (d) Dodać `.dockerignore` (`node_modules`, `.next`, `.venv`, `db/`, `.env`), żeby klucz API nie trafił do warstwy obrazu.

## H. Proces agentowy

33. **[W] Brak podziału pracy i kolejności agentów.** Plan mówi, że agenci komunikują się przez pliki w `planning/`, ale nie ma listy agentów, właścicieli katalogów, kolejności (kontrakt API → backend i frontend równolegle → E2E) ani definicji „gotowe” (np. testy przechodzą, `docker build` działa). Proponuję krótką sekcję „Workflow agentów” z właścicielem każdego katalogu i zasadą, że zmiana kontraktu w `planning/API.md` wymaga wpisu w `planning/CHANGELOG.md`.

---

## Uwagi do sekcji 13

- **#8d jest częściowo błędny.** Recharts **ma** komponent `<Treemap>`, więc zdanie „żadna z bibliotek nie pokrywa treemapy” jest nieprawdziwe. Prawdą jest, że Recharts renderuje SVG, nie canvas. Rekomendacja treemapy z divów nadal ma sens ze względu na testowalność, ale uzasadnienie trzeba poprawić.
- **#5b jest niekompletny:** sama kolejność „watchlista, potem transakcje” nie wystarczy bez synchronicznego seedowania ceny przy dodaniu tickera (patrz A6).
- **#3 jest niekompletny:** skoro strumień obejmuje sumę watchlisty i pozycji, frontend musi filtrować wiersze watchlisty i nie dodawać automatycznie tickerów spoza niej. Trzeba też ustalić, czy ticker usunięty z watchlisty, ale trzymany w pozycji, ma nadal mieć sparkline.
- **#10:** do zasad zaokrąglania dodać tolerancję porównań dla floatów (patrz C18).
- **Uproszczenie „docker compose up -d”** jest sprzeczne z §3 („no docker-compose for production”) i §2 („single Docker command”). Jeśli przyjmujemy compose, trzeba poprawić tabelę w §3. Jeśli nie, skrypty powinny używać `docker run`.
- **Uproszczenie „Massive jako stretch goal”:** popieram. Dodatkowo warto sprawdzić, czy endpoint snapshotu (wiele tickerów w jednym wywołaniu) jest w ogóle dostępny na darmowym planie, i opisać zachowanie poza godzinami sesji (ceny stoją, co wygląda jak awaria).
- Pozostałe punkty (#1, #2, #4, #6, #7, #9) są trafne i nie mam do nich zastrzeżeń.

## Kolejność rozstrzygania (sugestia)

1. Przed startem jakiegokolwiek agenta: sekcja 13 #1–#5 oraz A1, A2, A6, E23, F28, F29.
2. Przed implementacją modułu: pozostałe punkty [W] z danego obszaru.
3. Na bieżąco: punkty [N].
