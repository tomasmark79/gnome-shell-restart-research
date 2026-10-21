> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Nativní evidence původu callbacků v GJS

## Výsledek

GJS nyní ukládá do každé nativní `Gjs::Closure`, zda vznikla při chráněném
provádění. Při pozdějším volání tuto ochranu obnoví a C++ RAII ji zase uzavře.
Ochrana tak funguje také pro skutečné GI callbacky, které dosavadní JS obálky
nepokrývaly: dokončení asynchronního GIO volání a specializované
`Gio.Cancellable.connect`.

Test prokázal i přenos na další asynchronní callback vytvořený z chráněného
callbacku při nulové JS hloubce vlastnictví. Návratové objekty se nadále uvolní
a pozdější UI prostředky nepřežívají reload. Duplicitní ochranné JS obálky
běžných GLib timeoutů a GObject signálů byly odstraněny; potřebná evidence
jejich vlastnictví zůstává.

Klasifikace zůstává **SHELL RELOAD**, `trueRestartDemonstrated=false`.
Backendové testy přerušení odmítají a operace normálně doběhnou; neprokazují
obnovu nekonečného backendového zablokování. GJS kontext i kompozitor zůstávají
původní. Regrese současně prokazuje, že vybraný UI přenos lze stále přerušit
a obnovit.

## Důkaz původní mezery

[Negativní běh se starým GJS](evidence/reports/native-provenance-before/result.json)
použil nový přípravek asynchronního GIO volání se starou realizovanou vývojovou
obálkou a přesně zvoleným starým Shell balíčkem. Callback dokončil odpověď
soukromého D-Bus `Peer.Ping` a vstoupil do smyčky. Watchdog doručil přerušení:
`delivered=1`, `denied=0`, `fixtureFlags=1`; JS `finally` se přeskočilo.
Dosavadní povrchové obálky tedy tento GI vstup nechránily.

Negativní běh skončil exit 1, jeho profil byl odstraněn. Nejde o úspěch obnovy.

## Implementace a hranice odpovědnosti

`gi/closure.h` přidává jediný nativní boolean. Konstruktor v `gi/closure.cpp`
zachytí aktuální nativní ochranu; společný `invoke()` vstoupí do chráněného
scope ještě před JS voláním. RAII uloží pouze vypůjčený kontext na zásobníku,
nepřidává trvalé kořeny callbacku ani kontextu. Původní GJS invalidace a
finalizace closure zůstávají zachované.

Ochrana provádění zůstává oddělená od životnosti alokací. Nativní bit nepřidává
návratový objekt mezi backendové vlastníky ani nezvyšuje JS allocation scope.
Metadata znamenají původ při vytvoření nativní closure, nikoli univerzální
poznání všech backendových metod.

Při interní chybě vstupu/výstupu scope se nastaví fault latch a další označené
přerušení se odmítá. Tato pojistná větev nebyla samostatně injektována;
řádné uzavření po běžné JS výjimce má vlastní runtime test.

Čistě JS emitery stále potřebují svou obálku. U Source zůstává pomocná evidence
pro případ, kdy se registrace callbacku a backendové připojení zdroje časově
liší. Tento rozdíl není důvodem tvrdit, že jsou všechny vstupy automaticky
pokryté.

## Samostatné GJS ověření

Runtime: `/nix/store/6flc3sc5dbxgjdbarbgm77pqzf9im4rp-tgnome-gjs-1.88.1`.
Report: `/nix/store/d4xd8z5x7bqfdkfz0zw5jir54p2kwr9v-tgnome-interrupt-probe-0.1/share/tgnome/interrupt-report.json`.

Nový `native-closure` proces nemá Shell ani povrchové lifecycle obálky:

| Experiment | Výsledek |
| --- | --- |
| Timer registrovaný při nativní ochraně, spuštěný po uzavření registrace | Přerušení odmítnuto, JS finally dokončeno |
| Stejně registrovaný signál emitovaný přímo z C | Přerušení odmítnuto, JS finally dokončeno |
| Chráněný callback vyhodí běžnou JS výjimku | Nativní scope se uzavře na 0 |
| Následující nechráněný nekonečný callback | Přerušen; nativní heartbeat pokračuje a původní objekt zůstává použitelný |

Všechny čtyři případy prošly. Celý report obsahuje 12 procesů včetně dřívějších
negativních kontrol a má `passed=true`; všechny procesy byly sklizené a profily
odstraněné. Očekávané SIGABRT a vnější ukončení nepodporovaných smyček se stále
nezaměňují za úspěšnou obnovu.

Upstream konfigurace Nixpkgs zaznamenala 77 úspěšných testů a 0 selhání.
GTK4 testy v této konfiguraci nejsou zapnuté; build to výslovně hlásí. Další
varování pocházejí z upstream WarnLib introspekčních přípravků. GJS i Shell
se kompilovaly s `--cores 0`, v logu `-j16`.

## Ověření skutečného Shellu

Finální balíček: `/nix/store/mbkhf29wdjn3l5hxqnzph2rmnpj3h3h0-gnome-shell-50.5`.
Shell sestavení nemělo compiler warnings.

| Běh | Podstatný důkaz |
| --- | --- |
| [Asynchronní GIO](evidence/reports/closure-async-verified/result.json) | `call_finish` dokončeno, nativní hloubka 1, JS hloubka 0; 65,0069 s soak |
| [Cancellable callback](evidence/reports/closure-cancellable-verified/result.json) | Specializované connect API, callback z C, nativní hloubka 1 a JS 0 |
| [Řetězení GIO](evidence/reports/closure-chain-verified/result.json) | První i následný async callback chráněný při JS hloubce 0 |
| [Timeout](evidence/reports/closure-timer-verified/result.json) | Nativní hloubka 1 po odstranění duplicitní JS ochrany |
| [Přenos panelu](evidence/reports/closure-panel-verified/result.json) | Povolené UI přerušení, oprava journalu, odmítnutí souběhu a sběr náhradního panelu |

Všechny příkazy skončily exit 0 a reporty mají `passed=true`, vnější
`workerExitCode=0`, `privateProfileRemoved=true`. Každý dokončil tři UI
rekonstrukce a kontrolu původních Wayland/X11 spojení, textu, virtuálního
vstupu, registrů a vybraného GC. Diagnostické problémy byly 0; pouze panelový
test výslovně očekává jednu diagnostiku skutečného přerušení. Ostatní běhy
vedle GIO soaku neměly prodloužené pozorování.

Reprezentativní GIO běh zachoval Shell PID 2963381. Wayland klient měl stále
PID 2963904, fd 3, inode 8197033, windowId 10, tick 3 → 410. X11 klient měl
stále PID 2964012, fd 3, inode 8198680, windowId 2097156, tick 1 → 414.
V každém běhu zůstal původní GJS epoch i XWayland identita. Hashe neuložených
dat zůstaly stejné až do následného záměrného testu psaní; potom původní okna
přijala očekávaný nový text.

V backendových případech je `delivered=0`, `denied=1`, `nativeResumptions=0`.
Čítače se po práci vrátily na 0, návratové objekty byly sebrané a pozdější UI
signály odpojené. Ochrana nezůstala trvale zapnutá pro celý kontext.
Finální `nix flake check --cores 0` prošlo.

## Reprodukce a změny

```sh
nix build --cores 0 -L .#interrupt-probe --out-link result-interrupt-probe
nix build --cores 0 -L .#interruption-shell --out-link result-interruption-shell
nix develop .#interruption --cores 0 -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --track-time --interrupt-js \
  --interrupt-operation backend-async --soak-seconds 65 \
  --output artifacts/native-async-local
# Další vstupy: backend-cancellable, backend-chain, backend-delayed.
nix develop .#interruption --cores 0 -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --track-time --interrupt-js \
  --interrupt-operation panel-adopting --interrupt-handoff \
  --output artifacts/native-panel-local
nix flake check --cores 0
```

Změny: `shell/gjs-interruption.patch`, `shell/runtimeInit.js`,
`shell/stableRegistry.js`, `shell/interruptRuntime.h`,
`tests/interrupt-probe.cpp`, `tests/interrupt-supervisor.py`, `tests/isolated.py`
a dokumentace. Všechny soukromé Shell procesy byly sklizené. Hostitelský Shell
zůstal PID 1350942 s původním executable; NixOS se neaktivoval a systémový
rollback není potřeba.

## Další krok k původnímu cíli

Callback vytvořený mimo chráněný scope tuto značku nedostane. Neřeší se tím
automaticky obyčejné JS volání backendové metody, celý tok přes Promise/await,
nativní deadlock nebo pád procesu. Nekonečná chráněná operace stále blokuje
společnou smyčku; odmítnutí jejího přerušení není restart.

Další práce má přejít ke skutečné výměně UI runtime/global/module grafu při
zachování vlastníka kompozitoru a spojení. Je potřeba prověřit vlastnictví
nativních GType, vfunc a callback vazeb a existující překážku opakované
registrace typů. Čerstvý UI realm je zatím hypotéza k ověření, ne prokázaná
restartovatelná hranice. Další přidávání odmítacích podmínek samo původní cíl
nesplní.
