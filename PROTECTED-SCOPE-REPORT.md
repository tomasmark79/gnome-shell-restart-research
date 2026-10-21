> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Nativní ochrana backendového lifetime scope před přerušením

Následující [DURABLE-CALLBACK-REPORT.md](DURABLE-CALLBACK-REPORT.md) dokládá
mezeru při pozdějším spuštění callbacku a doplňuje ochranu vybraných vstupů.

## Výsledek a přesná klasifikace

Watchdog nyní odmítne přerušení uvnitř synchronního
`_tgnomeWithBackendLifetime()`. Autoritativní čítač je v nativním GJS, takže
interrupt hook nemusí spouštět JS, aby zjistil, zda by přeskočení `finally`
poškodilo vlastnictví prostředků. Vnořené scope se počítají odděleně.

V izolovaném Shellu test zaznamenal nativní i JS hloubku 2, jedno odmítnuté
přerušení, normální dokončení konečné operace a návrat obou čítačů na 0.
Později připojený UI signál nebyl chybně klasifikován jako trvalý a reload jej
odpojil. Původní klienti přežili tři následné UI rekonstrukce a 65sekundový soak.

To je **ochrana před nekonzistentním přerušením, nikoli obnova nekonečného
backendového zablokování**. Test výslovně hlásí
`protectedBackendInterruptionRefused=true`, `controlledBlockedJsRecovered=false`.
Klasifikace běhu je **SHELL RELOAD**, protože následně proběhly běžné reloady UI.
`trueRestartDemonstrated=false`; nový runtime ani proces nevznikl.

## Implementace

Privátní patch GJS přidává owner-thread API pro vstup/výstup z chráněného scope
a čtení hloubky. Neplatný pop, přetečení a cizí vlákno nesmějí změnit čítač.
Hodnota patří konkrétnímu GjsContext. `mark_interrupt()` odmítne nenulovou
hloubku vedle dosavadních kontrol vnoření, Promise jobs a modulových vstupů.
Neoznačené fatální chyby si zachovávají původní chování.

`interruptGlobal.c.inc` poskytuje úzký introspektovaný most přes ShellGlobal
k jeho vlastnímu GJS kontextu. Nepotřebuje vytvářet JS wrapper samotného
GjsContext. Most je přidaný pouze do `interruption-shell`; při zapnutém
experimentu vyžaduje headless backend.

`stableRegistry.js` vstoupí do nativní ochrany před zvýšením JS lifetime čítače.
Ve `finally` nejprve sníží JS čítač a potom opustí nativní ochranu. Nativní
čtení proto nikdy nepovolí přerušení v okamžiku, kdy by JS ještě považoval
prostředky za backendové. Běžný stable/VM balíček tento most nemá a nepoužívá
watchdog; dostupnost metody je kontrolovaná.

## Samostatný GJS test

Finální runtime:
`/nix/store/k97rlwwfqz118fs28bygxl7h6f8abxgg-tgnome-gjs-1.88.1`.
Upstream testy: 77 úspěšných, 0 selhání. Kompilace s `--cores 0` použila `-j16`.

Report:
`/nix/store/26nzayabwyifdsmhn2x5an172pyinac4-tgnome-interrupt-probe-0.1/share/tgnome/interrupt-report.json`.

Upravená varianta má 11 procesů a celkové `passed=true` ve smyslu
charakterizačních očekávání:

- Konečný chráněný eval odmítl požadavek, dokončil JS `finally`, vrátil hloubku
  2 → 1 → 0 a odmítl podtečení.
- Následujících pět povolených přerušení ve stejném kontextu stále fungovalo.
- Cizí vlákno nemohlo nastavit značku ani otevřít chráněný scope.
- Nekonečný chráněný eval odmítl přerušení a zůstal zablokovaný. Po dvou
  sekundách jej ukončil vnější supervisor SIGTERM vlastní procesní skupině.
  `timedOut=true` je očekávaná negativní charakterizace, nikoli obnova.
- Zůstaly zachované kontroly ostatních nepodporovaných vstupů a původního
  fatálního chování neoznačeného přerušení. Všechny procesy byly sklizené
  a jejich runtime profily odstraněné.

## Skutečný Shell a zachování klientů

Balíček:
`/nix/store/iz4aw9kqy6ml7b8bhpnwcsxmdj9wind6-gnome-shell-50.5`.

[Backend scope výsledek](evidence/reports/protected-backend-scope/result.json)
má `passed=true`, vnější `workerExitCode=0`, `privateProfileRemoved=true`.
Testovaný callback trvá konečných 1700 ms, používá skutečný lifetime helper
dvakrát vnořený a po jeho dokončení připojí signál ke stálému stage.

| Kontrola | Výsledek |
| --- | --- |
| Hloubka uvnitř helperu | JS 2, nativní 2 |
| Watchdog | delivered 0, denied 1, nativeResumptions 0 |
| JS `finally` | Dokončen |
| Hloubka po helperu i po třech generacích UI | JS 0, nativní 0 |
| Nový signál po helperu | Celkový počet +1, počet permanentních nezměněn |
| Signál po reloadu | Odpojen; registry opět odpovídají výchozímu stavu |
| Opožděné callbacky | 65,0081 s, diagnostické problémy 0 |

Shell PID zůstal 2812118, GJS epoch
`09915b3e-24e6-43a1-ad5c-63fe67d69369`. Wayland klient zachoval PID 2812427,
fd 3, inode 7931032, windowId 10; tick 3 → 409. X11 klient zachoval PID 2812454,
fd 3, inode 7931040, windowId 2097156; tick 1 → 414. Původní hashe neuložených
dat zůstaly stejné až do záměrného testu psaní. Původní okna pak přijala
virtuální klávesnici a očekávaný nový text; pozdní klienti také fungovali.

[Regrese přerušení panelu](evidence/reports/protected-panel-regression/result.json)
také prošla: chráněné backendové scope jsou již uzavřené, skutečný přenos
panelu lze přerušit a opravit. Pět konkurenčních reloadů bylo během handoffu
odmítnuto, panel zničen a sebrán, UI třikrát obnoveno. Původní Wayland/X11
spojení přežila; nativní hloubka na konci 0 a diagnostické problémy 0. Tato
regrese neměla prodloužený soak.

Oba soukromé Shell procesy byly sklizené. Hostitelský Shell nadále měl původní
PID 1350942 a executable. `nix flake check --cores 0` prošlo, včetně baseline
a aktualizovaného standalone testu.

## Reprodukce a změny

```sh
nix build --cores 0 -L .#interrupt-probe --out-link result-interrupt-probe
nix build --cores 0 -L .#interruption-shell --out-link result-interruption-shell
nix develop .#interruption --cores 0 -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --track-time --interrupt-js \
  --interrupt-operation backend-finite --soak-seconds 65 \
  --output artifacts/protected-backend-local
nix develop .#interruption --cores 0 -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --track-time --interrupt-js \
  --interrupt-operation panel-adopting --interrupt-handoff \
  --output artifacts/protected-panel-local
nix flake check --cores 0
```

Změněné soubory: `shell/gjs-interruption.patch`, `shell/interruptGlobal.c.inc`,
`shell/stableRegistry.js`, `shell/interruptRuntime.h`, `flake.nix`,
`extension/extension.js`, `tests/interrupt-probe.cpp`,
`tests/interrupt-supervisor.py`, `tests/isolated.py` a dokumentace.
Testy používají soukromé profily a headless výstupy. NixOS konfigurace ani
hostitelská relace se neaktivovaly; systémový rollback není potřeba.

## Další architektonická hranice

Tato ochrana platí po dobu synchronního volání lifetime helperu. Registrace
callbacku uvnitř backendového scope sama nezaručuje ochranu při jeho pozdějším
spuštění. Je třeba auditovat a případně přenést ochranu na skutečné trvalé
GLib/signal callbacky; samotné označení prostředku jako permanentního nestačí.
Promise jobs a nepodporované vnoření jsou stále odmítané odděleně.

Nekonečný backendový scope tento prototyp neobnoví. Pro takové selhání,
nativní deadlock, pád procesu a úplnou výměnu GJS potřebuje původní cíl silnější
hranici mezi restartovatelnou částí Shellu a vlastníkem kompozitoru/spojení.
Ochrana před poškozením vlastnictví je předpoklad této práce, nikoli její
náhrada nebo dokončení.
