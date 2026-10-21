> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Ochrana nativních hranic přerušení GJS

Tento report popisuje samostatnou fázi 18. Následující
[SHELL-INTERRUPT-REPORT.md](SHELL-INTERRUPT-REPORT.md) zapojuje tuto GJS
variantu do odděleného headless Shellu a dokládá obnovu řízeného callbacku.

## Výsledek

Nová varianta samostatného GJS prototypu odmítá přerušení ve všech šesti
testovaných nepodporovaných vstupech. Povolené přímé eval a nativně vyvolané
GLib/GObject callbacky se nadále podaří přerušit se zachováním kontextu,
původního objektu a pokračujícího nativního heartbeat.

Klasifikace: **RESEARCH PROTOTYPE**, `shellRecoveryDemonstrated=false`.
Žádný Shell balíček tuto variantu GJS zatím nepoužívá. Tento test neobsahuje
Mutter ani Wayland klienty. Cíl úplného restartu zůstává nesplněný.

## Změna oproti předchozí fázi

[INTERRUPT-REPORT.md](INTERRUPT-REPORT.md) zaznamenal, že po přerušení vnitřního
callbacku mohl pokračovat starší JS rámec. Nová ochrana takové přerušení
odmítne; netvrdí, že bezpečně obnoví jeho rozpracovaný stav.

`gjs_context_tgnome_mark_interrupt()` nyní vrací boolean. Volající musí při
odmítnutí pokračovat bez přerušení engine. Povolení vyžaduje současně:

- vlastnické JS vlákno;
- právě jeden sledovaný vstup do JS, který patří mezi povolené hranice;
- nepřítomnost staršího JS volajícího při vstupu podle
  `JS::DescribeScriptedCaller()`;
- nepřítomnost nevyzvednuté značky předchozího přerušení.

RAII objekt sleduje hloubku a obnovuje předchozí stav při návratu. Je vložen
do přímého eval a společného vstupu GJS Closure. Modulový eval, Promise jobs
a main-loop hook mají výslovně nepovolenou hranici. Čítač pokrývá sledované
vnoření; kontrola engine navíc zachytí testovaný vstup přes surové JS API,
který obchází `gjs_context_eval()`.

To je konzervativní politika pro připnuté GJS 1.88.1 a SpiderMonkey 140.14.0.
Nejde o důkaz všech možných embedderů, skrytých aktivací nebo nativních operací.
`catch` a `finally` přerušeného JS se stále nevykonají.

## Výsledky

| Scénář | Výsledek |
| --- | --- |
| Běžný vnořený GObject callback a konečný Promise job | Oba dokončeny; následné povolené přerušení funguje, původní data zachována |
| Tři přímé nekonečné eval | Tři přerušení po přibližně 500 ms, stejný kontext a původní objekt |
| GLib callback a nativně emitovaný GObject signál | Oba označené návraty do nativní smyčky úspěšné |
| GC bez požadavku watchdogu | Žádné dodatečné přerušení |
| Neoznačený callback po pěti označených přerušeních | Očekávaný SIGABRT; výjimka z fatální politiky není trvalá |
| JS → C → JS | Přerušení odmítnuto |
| Vnořená GLib smyčka se starším JS rámcem | Přerušení odmítnuto |
| Nekonečný Promise job | Přerušení odmítnuto |
| Nekonečný modulový eval | Přerušení odmítnuto |
| Surový JS API vstup se zpětným GObject callbackem | Přerušení odmítnuto |
| Nesledovaný surový JS API eval | Přerušení odmítnuto |
| Pokus nastavit značku z cizího vlákna | Odmítnut, proces normálně dokončen, původní data zachována |

**Odmítnutí není obnova.** Šest nepodporovaných smyček zůstalo zablokovaných.
Po dvou sekundách je ukončil vnější supervisor signálem SIGTERM vlastní
procesní skupině. V každém reportu je `timedOut=true`, událost
`interrupt-denied` a žádná `interrupt-delivered`. Tento postup by nebyl
přípustný pro skutečný společný proces Shell/Mutter se zachováním klientů.

Report upravené varianty obsahuje 10 procesů, baseline jeden. Všechny byly
sklizené a jejich soukromé runtime profily odstraněné. `passed=true` znamená
splnění charakterizačních očekávání včetně očekávaných negativních výsledků.

## Sestavení a autoritativní artefakty

GJS s ochranou:

`/nix/store/mg2lakhqrm438li6vk6gijjgd183nswk-tgnome-gjs-1.88.1`

Jeho upstream testy: **77 úspěšných, 0 selhání**. Kompilace použila
`--cores 0`, v logu skutečně `-j16`.

Finální reporty:

- Upravený runtime: `/nix/store/xlhn8wmh9arbvrdxafvbbnnvqgx7880h-tgnome-interrupt-probe-0.1/share/tgnome/interrupt-report.json`
- Baseline: `/nix/store/259wmn11dl761min7vc5fdl7nkxb5azr-tgnome-interrupt-baseline-0.1/share/tgnome/interrupt-report.json`

První sestavení nového testovacího programu selhalo na ignorované návratové
hodnotě `gjs_context_eval_module()` při `-Werror`. Program nyní návratovou
hodnotu zaznamená; obě finální sestavení i jejich checkPhase prošly.
Následné `nix flake check --cores 0` skončilo exit 0 a `all checks passed!`;
ověřované výstupy již byly sestavené, takže neprovádělo nové běhy testů.

```sh
nix build --cores 0 -L .#interrupt-probe --out-link result-interrupt-probe
nix build --cores 0 -L .#interrupt-baseline --out-link result-interrupt-baseline
cat result-interrupt-probe/share/tgnome/interrupt-report.json
nix flake check --cores 0
```

Změny této fáze: `shell/gjs-interruption.patch`, `tests/interrupt-probe.cpp`,
`tests/interrupt-supervisor.py` a dokumentace. Stávající Shell balíčky,
VM varianty a hostitelská konfigurace zůstávají oddělené od experimentální GJS
varianty. Hostitelský Shell při kontrole stále měl původní PID 1350942
a původní executable.

## Další krok k původnímu cíli

Vytvořit samostatný headless Shell balíček s tímto GJS, nativním watchdogem
a přesně omezeným testovacím callbackem. `native-loop.patch` již vrací
modulový init před spuštěním dlouhodobé nativní Mutter smyčky; watchdog proto
musí být připojen až po návratu inicializačního eval, nikoli uvnitř modulu.

Při povoleném přerušení musí nativní smyčka převzít řízení a vyvolat vlastněnou
rekonstrukci UI. Je třeba prověřit stav registrů zdrojů a lifetime čítačů,
protože JS úklid se při přerušení přeskočí. Následující integrační test musí
zachovat původní sockety, okna, neuložená testovací data a vstup Wayland/XWayland
klientů. Bez tohoto experimentu není obnova zablokovaného Shellu prokázaná.

Nativní C deadlock, pád procesu a restart celého kompozitoru zůstávají další
architektonické hranice; odmítnuté vnořené a Promise vstupy tento prototyp
neumí obnovit.
