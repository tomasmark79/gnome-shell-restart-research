> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Obnova rozpracovaného přenosu panelu po přerušení JS

Následující [HANDOFF-REPORT.md](HANDOFF-REPORT.md) doplňuje vynucený souběh:
odhalil a opravil přijetí reloadu před nativním vypořádáním transakce.

## Výsledek

Test nyní přerušuje skutečnou synchronní operaci Shellu: `Main.reloadPanel()`.
Po odpojení indikátorů, případně po jejich částečném převzetí novým panelem,
se callback zablokuje. Watchdog přeruší jeho JS bez vykonání `catch` a `finally`.
Nativní obnova dohledá rozpracovanou transakci, vrátí indikátory původnímu
panelu, zničí nedokončený panel a teprve potom požádá o rekonstrukci UI.

Oba scénáře prošly. Původní Wayland/XWayland klienti zachovali spojení, okna
a data. Klasifikace zůstává **SHELL RELOAD**, `trueRestartDemonstrated=false`.
Nejde o nový GJS kontext ani restart procesu či kompozitoru.

## Změna vlastnictví

Předchozí `replacePanel()` držel náhradní panel a seznam indikátorů pouze
v lokálních proměnných. Při běžné výjimce jej zachránil `catch`; neodchytitelné
přerušení JS tuto větev přeskočí. Samotný návrat nativní smyčky proto nestačil
jako důkaz, že jde obnovit i rozpracovaná operace.

`panelLifecycle.js` nyní před mutací publikuje modulový záznam transakce:
původní panel, náhradní panel, seznam indikátorů a fázi. Nový přenos při
existující transakci odmítne. Záznam žije i po odstranění přerušeného JS rámce.

`recoverInterruptedPanelTransfer()` odstraní částečné vazby náhradního panelu,
zničí jej a vrátí indikátory do původních boxů. Kontroluje jejich role,
konkrétní rodiče, pozice a viditelnost. Teprve po potvrzení obnovy zruší
modulový záznam. Běžná zachytitelná chyba používá tutéž opravnou cestu.

Samostatný watchdogový Shell volá tuto opravu z nativní smyčky před požadavkem
`ReloadDesktopUi`. Nejprve odstraní testovací checkpoint, aby při pozdějším
přenosu nevznikla další nekonečná smyčka. Pokud oprava vyhodí chybu, nativní kód
zaznamená terminální karanténu a nepožádá o automatický reload. Tato negativní
větev zatím nemá vlastní runtime test.

Zničení sleduje skutečný `destroy` signál, uvolnění samostatný
`FinalizationRegistry`. Historický záznam obsahuje pouze data, nikoli aktéry.
Úspěšný návrat funkce se tedy nezaměňuje za důkaz sběru objektu.

## Ověřené běhy

Balíček Shellu:
`/nix/store/z81zcmgadlxjk6cna4n30hllcaplx35k-gnome-shell-50.5`.
Kompilace prošla s `--cores 0`, v logu `-j16`, bez compiler warnings.
GJS i SpiderMonkey zůstávají připnuté podle předchozí fáze.

| Scénář | Stav v okamžiku přerušení | Výsledek |
| --- | --- | --- |
| `panel-detached` | 9 odpojených indikátorů, nový panel převzal 0 | Všechny vráceny, náhradní panel zničen a sebrán GC |
| `panel-adopting` | 9 indikátorů v transakci, nový panel již převzal 1 | Částečné vazby odstraněny, všechny vráceny, náhradní panel zničen a sebrán GC |

Autoritativní výsledky:

- [Odpojený panel](evidence/reports/panel-interrupt-detached-1/result.json), vnější supervisor (not exported: `artifacts/panel-interrupt-detached-1/supervisor.json`).
- [Částečné převzetí](evidence/reports/panel-interrupt-adopting-1/result.json), vnější supervisor (not exported: `artifacts/panel-interrupt-adopting-1/supervisor.json`).

Oba celé příkazy skončily exit 0. Oba výsledky mají `passed=true`,
`controlledInterruptedPanelTransferRecovered=true`, vnější `workerExitCode=0`
a `privateProfileRemoved=true`.

| Běh | Zachované klientské identity | Průběžné komunikace před/po |
| --- | --- | --- |
| detached / Wayland | PID 2761352, fd 3, inode 7835500, windowId 10 | tick 3 → 84 |
| detached / X11 | PID 2761362, fd 3, inode 7818015, windowId 2097156 | tick 1 → 85 |
| adopting / Wayland | PID 2763407, fd 3, inode 7820980, windowId 10 | tick 3 → 410 |
| adopting / X11 | PID 2763431, fd 3, inode 7847449, windowId 2097156 | tick 1 → 411 |

Shell PID zůstal v prvním běhu 2761025 a ve druhém 2763094. V každém běhu
zůstal stejný GJS epoch a XWayland identita. Hashe neuložených dat zůstaly
stejné až do záměrného následného testu psaní; nativní virtuální klávesnice
potom úspěšně upravila obě původní okna. Pozdní nové klienty také šlo připojit.

Každý běh dokončil tři UI rekonstrukce. Sledované registry, stage, desktopový
stav, menu a zachované backendové modely prošly kontrolami. Standardní gate
potvrdila 39 sebraných sledovaných objektů včetně kontrol; navíc samostatná
evidence potvrdila sběr rozpracovaného náhradního panelu. Tři držené backendové
kontroly zůstaly živé.

Watchdog pokaždé doručil právě jedno přerušení a zaznamenal jeden nativní návrat;
opakovaný požadavek byl odmítnut. Jedna očekávaná diagnostika přerušení je
výslovně vyžadovaná; další diagnostické problémy byly 0.

Adopting běh zahrnuje 65,0083 s sledování opožděných callbacků. Detached běh
prodloužený soak neměl. Oba zahrnují také výchozí regrese deseti běžných přenosů
panelu a jedné zachytitelné chyby převzetí. `nix flake check --cores 0` prošlo.

## Reprodukce

```sh
nix build --cores 0 -L .#interruption-shell --out-link result-interruption-shell
nix develop .#interruption --cores 0 -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --track-time --interrupt-js \
  --interrupt-operation panel-detached --output artifacts/panel-detached-local
nix develop .#interruption --cores 0 -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --track-time --interrupt-js \
  --interrupt-operation panel-adopting --soak-seconds 65 \
  --output artifacts/panel-adopting-local
nix flake check --cores 0
```

Změněné implementační soubory: `shell/panelLifecycle.js`,
`shell/mainLifecycle.js`, `shell/interruptRuntime.h`, `extension/extension.js`
a `tests/isolated.py`. Journal a stav jsou součástí panelové vývojové vrstvy;
checkpointy a watchdog zůstávají omezené na explicitní izolovaný experiment.
Hostitelská konfigurace se neměnila. Soukromé Shell procesy byly sklizené;
hostitelský Shell zůstává původní PID 1350942 s původním executable.
Testy uklidily vlastní profily, systémový rollback není potřeba.

## Přesné hranice důkazu a další krok

Prokázaná je obnova dvou vybraných bodů synchronního přenosu panelu. Nelze ji
zobecnit na přerušení destrukce původního panelu, libovolný konstruktor,
backendový model, Promise job ani nativní C operaci. Watchdog je stále
výslovně ozbrojený, nikoli obecný detektor všech zablokování.

Další hranicí je serializace mezi přerušeným callbackem a nativním převzetím:
tento test nevynucuje konkurenční UI požadavek v této mezeře. Je třeba ověřit,
že nemůže převzít rozpracovanou transakci ani zahájit druhý reload. Následuje
odmítnutí přerušení nekonzistentních backendových scope a bezpečná detekce
selhání známých vstupů. Automatická obnova zámku, úplný nový GJS runtime,
nativní pád a restart celého procesu zůstávají samostatné otevřené oblasti.
