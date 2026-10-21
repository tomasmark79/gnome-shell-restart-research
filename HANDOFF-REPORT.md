> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Odmítnutí konkurenčních reloadů před nativní opravou

Následující [PROTECTED-SCOPE-REPORT.md](PROTECTED-SCOPE-REPORT.md) doplňuje
nativní ochranu synchronních backendových lifetime scope.

## Nalezená chyba a oprava

Vynucený souběh prokázal skutečnou chybu: po přerušení přenosu panelu mohl
`ReloadDesktopUi` zahájit rekonstrukci, přestože transakce stále čekala na
nativní opravu. [Běh před opravou](evidence/reports/handoff-before-fix/result.json)
skončil exit 1 s `ReloadDesktopUi entered the interrupted panel handoff`.
Vnější supervisor uklidil soukromý profil; tento běh není úspěšný test obnovy.

Nová společná kontrola odmítne `ReloadPanel`, `ReloadUI`, `ReloadTheme`,
`ReloadDesktopUi` a `PrepareRuntimeReset`, dokud existuje rozpracovaná panelová
transakce. Příprava ji kontroluje před nastavením vlastnických příznaků,
backendovými operacemi a rezervací nativního pokusu. Odmítnutí používá
`Gio.IOErrorEnum.BUSY`, takže očekávaný stav nevytváří neošetřenou JS chybu.
Čtení `Status` zůstává dostupné.

Klasifikace výsledku: **SHELL RELOAD**. Proces Shellu, GJS a Mutter přežívají;
`trueRestartDemonstrated=false`. Původní cíl úplného restartu zůstává otevřený.

## Jak test vynucuje souběh

Samostatný headless watchdogový balíček má výslovný testovací checkpoint
`TGNOME_TEST_HANDOFF=1`. Po přerušení callbacku nativní smyčka pozastaví opravu
a vystaví stav `held=true`. Rozpracovaný panelový journal zůstává dostupný.
Jiný proces potom skutečně volá uvedených pět D-Bus metod.

Test vyžaduje odmítnutí všech pěti, shodné registry, desktop, backendový model,
stage, počty UI objektů a nativní stav před/po. Nativní `attempts` i `uiCommits`
zůstávají 0. Během sekundové pauzy musí oba původní klienti dokončovat další
komunikace. Teprve potom test uvolní předání, nebo vyčká vlastní nativní lhůtu.

Pozastavení má osm sekund dlouhý nativní limit. Potvrzení zruší jeho zdroj
a naplánuje jedinou opravu. Vypršení samo provede tutéž opravu; kontrolní stav
zaznamená přesně jedno uvolnění. Nativní časovač i případný čekající idle zdroj
se při zastavení runtime odstraní. Testovací endpointy jsou přítomné pouze
v oddělené compile-time variantě se stávajícími headless a environment gates.

## Ověřené výsledky

Finální balíček:
`/nix/store/61pvcj1clddg57sj3b6gsq5q8yppg510-gnome-shell-50.5`.
Sestavení s `--cores 0` použilo `-j16`, compiler warnings: 0.

| Běh | Rozpracovaný stav | Způsob uvolnění | Výsledek |
| --- | --- | --- | --- |
| [adopting fixed](evidence/reports/handoff-adopting-fixed/result.json) | 1 z 9 indikátorů již převzal nový panel | Výslovné potvrzení; přibližně 1,281 s pozastavení | Pět odmítnutí, oprava, 3 UI commity, 65,0077 s soak |
| [detached deadline](evidence/reports/handoff-detached-deadline/result.json) | Všech 9 indikátorů odpojeno | Vlastní deadline; přibližně 8,008 s pozastavení | Pět odmítnutí, oprava, 3 UI commity; bez prodlouženého soaku |

Oba příkazy skončily exit 0. Oba reporty mají `passed=true`, vnější
`workerExitCode=0` a `privateProfileRemoved=true`. Ve druhém je navíc
`releaseMode=deadline`, `expired=true`; v prvním `expired=false`.
V obou případech je `held=false` a `releases=1` po obnově.

| Běh / klient | Zachovaná identita | Tick před/po |
| --- | --- | --- |
| adopting / Wayland | PID 2788629, fd 3, inode 7868851, windowId 10 | 3 → 416 |
| adopting / X11 | PID 2788642, fd 3, inode 7885376, windowId 2097156 | 1 → 417 |
| deadline / Wayland | PID 2790886, fd 3, inode 7869309, windowId 10 | 3 → 125 |
| deadline / X11 | PID 2790895, fd 3, inode 7888352, windowId 2097156 | 1 → 126 |

Shell PID byl v prvním běhu stále 2788294, ve druhém 2790565. Každý zachoval
svůj původní GJS epoch i XWayland identitu. Kontrola všech průběžných klientských
záznamů potvrdila zachování původních spojení a hashů neuloženého textu až do
následného záměrného psaní. Virtuální klávesnice upravila obě původní okna na
očekávané nové hashe; připojení dalších nových klientů také fungovalo.

Oba běhy potvrdily vrácení indikátorů do původních pozic, zničení a sběr
nedokončeného panelu a standardní kontroly finalizace dalších generací UI.
Watchdog doručil právě jedno přerušení a jeden nativní návrat. Vedle jedné
výslovně vyžadované diagnostiky přerušení byly další diagnostické problémy 0.
`nix flake check --cores 0` prošlo.

## Reprodukce

```sh
nix build --cores 0 -L .#interruption-shell --out-link result-interruption-shell
nix develop .#interruption --cores 0 -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --track-time --interrupt-js \
  --interrupt-operation panel-adopting --interrupt-handoff \
  --soak-seconds 65 --output artifacts/handoff-adopting-local
nix develop .#interruption --cores 0 -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --track-time --interrupt-js \
  --interrupt-operation panel-detached --interrupt-handoff --handoff-expiry \
  --output artifacts/handoff-deadline-local
nix flake check --cores 0
```

Změněné implementační soubory: `extension/extension.js`,
`shell/interruptRuntime.h`, `shell/tgnome-runtime.h`, `tests/isolated.py`.
Hostitelská konfigurace nebyla aktivována ani změněna. Všechny tři experimenty
uklidily své soukromé profily, soukromé Shell procesy byly sklizené a hostitelský
Shell zůstal PID 1350942 s původním executable. Systémový rollback není potřeba.

## Hranice a další krok

Důkaz se vztahuje na uvedených pět reload operací při živém panelovém journalu.
Neprokazuje pozastavení všech možných JS callbacků, vstupních událostí nebo
operací správce rozšíření. Nenahrazuje kontrolu konzistence jiných trvalých
modelů. Po dokončení panelové opravy platí běžný vlastněný protokol UI reloadu;
tento test nevynucuje všechny možné pořadí dalších požadavků v této fázi.

Další podstatnou hranicí je `_tgnomeWithBackendLifetime`: jeho čítač se dnes
vrací přes JS `finally`. Přerušení uprostřed takového scope by mohlo chybně
označovat další UI prostředky za trvalé. Je třeba na nativní hranici odmítnout
nebezpečné přerušení nebo mít ověřený způsob obnovy konkrétního backendového
stavu. Automatická detekce, Promise/nested vstupy, zámek, nový GJS runtime
a restart celého procesu zůstávají otevřené.
