> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Ochrana pozdějšího běhu backendových callbacků

Následující [NATIVE-CLOSURE-REPORT.md](NATIVE-CLOSURE-REPORT.md) zachycuje původ
ochrany přímo v GJS closure a rozšiřuje důkaz na další GI async vstupy.

## Výsledek

Registrace callbacku uvnitř backendového lifetime helperu už není jediným
chráněným okamžikem. Ve vývojovém watchdogovém Shellu se ochrana obnovuje také
při pozdějším spuštění zachycených GLib a GObject callbacků. Testy prokázaly
odmítnutí přerušení timeoutu, explicitního GLib Source i signálu emitovaného
přímo z nativního C, zatímco původní registrační scope již byl uzavřený.

Ochrana běhu je oddělená od vlastnictví nových objektů: JS hloubka alokací
zůstává 0, návratový objekt callbacku se neukládá mezi trvalé vlastníky a pozdější
UI signál se při reloadu odpojí. Ve všech třech bězích přežila původní
Wayland/XWayland spojení tři následné rekonstrukce UI.

Jde o ochranu kritické práce, **nikoli obnovu nekonečně zablokovaného backendu**.
Klasifikace běhů je **SHELL RELOAD** kvůli následným běžným rekonstrukcím UI;
`controlledBlockedJsRecovered=false`, `protectedBackendInterruptionRefused=true`,
`trueRestartDemonstrated=false`. Proces, GJS runtime a Mutter se nemění.

## Nalezená mezera

[Test před opravou](evidence/reports/delayed-backend-before-fix/result.json) skutečně
doručil přerušení pozdějšímu timeoutu: `delivered=1`, `denied=0`, příznaky
potvrdily vstup a přeskočené `finally`. Jeho registrace přitom proběhla
v backendovém helperu. Samotná synchronní ochrana z předchozí fáze tedy nestačila.
Celý negativní běh skončil exit 1 a uklidil svůj soukromý profil.

## Implementace

`_tgnomeWithBackendExecution()` chrání pouze běh nativním čítačem. Nenavyšuje
JS hloubku vlastnictví a nepřidává návratové hodnoty do `_tgnomeDurableOwners`.
Factory helper `_tgnomeWithBackendLifetime()` jej používá navíc se svým původním
účtováním životnosti. Tím se nezaměňuje ochrana callbacku za požadavek držet
všechny jeho nové objekty trvale.

Při registraci v backendovém scope může soukromá varianta zachytit ochranu pro:

- GLib idle/timeout convenience funkce;
- `GLib.Source.set_callback()` a `attach()`; token v WeakMap nedrží Source
  silnou referencí a callback nepotřebuje zachytit samotný Source objekt;
- GObject `connect` a `connect_after`;
- vybrané trvalé JS emitery a DBusProxy `connectSignal` ve stávajícím registru.

Obálka předává původní `this`, argumenty a návratovou hodnotu. Přímé testy
zablokování v této fázi pokrývají první tři rodiny; vybrané JS/DBus root emitery
nemají samostatný fault checkpoint. Obálky se podle přítomnosti nativního mostu
aktivují v `interruption-shell`; běžný stable/VM balíček most nemá.

Watchdog se nyní ozbrojí až nativním mostem z počátku skutečně testovaného
callbacku. Chyba jeho registrace tedy nezpůsobí přerušení náhodné pozdější práce.
Helper C++ byl přesunut z executable do soukromé knihovny Shellu, aby jej sdílel
main.c i úzký introspektovaný most. Příkaz `InterruptUiProbe` nyní potvrzuje
`scheduled=true`; samotné ozbrojení nastává při vstupu callbacku. Jednorázový
limit a vypnutí/join vlákna zůstávají zachované.

## Finální ověření

Balíček: `/nix/store/lkxcm0ksq17pmad8lbxsz60ahcv99szi-gnome-shell-50.5`.
Kompilace s `--cores 0` použila `-j16`, compiler warnings: 0.

| Test | Nativní hloubka při callbacku | JS hloubka vlastnictví | Výsledek |
| --- | --- | --- | --- |
| [Timeout](evidence/reports/durable-timer-verified/result.json) | 2, kvůli vnořeným GLib convenience obálkám | 0 | Odmítnutí, dokončené finally, 65,0076 s soak |
| [Explicitní Source](evidence/reports/durable-source-verified/result.json) | 1 | 0 | Odmítnutí, dokončené finally, zachovaná validace neplatného callbacku |
| [Nativní GObject signál](evidence/reports/durable-signal-verified/result.json) | 1 | 0 | Odmítnutí, dokončené finally; C emituje přímo, bez staršího JS rámce |

Všechny tři příkazy skončily exit 0 a reportují `passed=true`, vnější
`workerExitCode=0`, `privateProfileRemoved=true`. V každém je `delivered=0`,
`denied=1`, `nativeResumptions=0`. Čítače se vrátí na 0, callback dokončí práci,
návratový objekt se sebere GC a pozdější UI signál se odpojí při reloadu.
Diagnostické problémy jsou 0. Source a signál neměly prodloužený soak.

| Běh / klient | Zachovaná identita | Tick před/po |
| --- | --- | --- |
| timeout / Wayland | PID 2887356, fd 3, inode 8065082, windowId 10 | 3 → 409 |
| timeout / X11 | PID 2887368, fd 3, inode 8031007, windowId 2097156 | 1 → 414 |
| Source / Wayland | PID 2888527, fd 3, inode 8045143, windowId 10 | 3 → 85 |
| Source / X11 | PID 2888590, fd 3, inode 8060871, windowId 2097156 | 1 → 89 |
| signál / Wayland | PID 2888576, fd 3, inode 8065393, windowId 10 | 3 → 86 |
| signál / X11 | PID 2888653, fd 3, inode 8045177, windowId 2097156 | 1 → 90 |

Shell PID zůstaly 2887037, 2887630 a 2887750. Každý běh zachoval svůj původní
GJS epoch, XWayland identitu a hashe neuloženého textu až do následného záměrného
testu psaní. Původní okna potom přijala nativní virtuální klávesnici a očekávaný
nový text; další nové klienty šlo také připojit a zavřít.

[Regrese panelu s kontrolou stavů rozšíření](evidence/reports/durable-panel-state-gated/result.json)
také prošla. Povolený UI přenos lze stále přerušit, původní panel opravit,
náhradní panel zničit a sebrat a UI třikrát rekonstruovat. Pět konkurenčních
reloadů bylo v handoffu odmítnuto. Bylo potvrzeno 12 dokončených ACTIVE/INACTIVE
přechodů správce rozšíření. Vnější exit 0, odstraněný profil, diagnostiky 0.

## Neúspěšné a nejisté experimenty

- [První signálový přípravek](evidence/reports/delayed-signal-fixed/result.json)
  zaměnil `Gio.Cancellable.connect` za obecné připojení GObject signálu.
  Callback nevznikl a tehdejší časové ozbrojení přerušilo jinou práci Shellu.
  Oprava používá explicitní GObject prototype a ozbrojuje až skutečný vstup.
- [Kontrola neplatného Source callbacku](evidence/reports/durable-source-complete/result.json)
  nezachytila očekávanou chybu: připnuté GJS odmítá `set_callback(null)`.
  Watchdog zůstal neozbrojený. Finální test očekávané odmítnutí kontroluje
  (`invalidCallbackRejected=true`) a poté registruje platnou funkci.
- [Jeden panelový regresní běh](evidence/reports/durable-panel-verified/result.json)
  dokončil tři rekonstrukce, ale po disable/enable se nevrátil extension endpoint.
  [Forenzní opakování](evidence/reports/durable-panel-forensic/result.json) prošlo.
  Příčina tohoto jednotlivého výpadku nebyla jednoznačně prokázána. Fixture
  nyní čeká na skutečné stavy a enabled příznak z GetExtensionInfo, nejen na
  přítomnost endpointu: upstream může exportovat objekt již při ACTIVATING.
  Nejde o tvrzení, že byla opravena obecná chyba správce rozšíření.

Při doplňování této kontroly byla také opravena interpretace GDBus odpovědi:
`(true,)` není Python literal. Neúspěšné přípravné běhy nejsou zahrnuté mezi
úspěšné důkazy obnovy. Všechny pracovaly pouze se soukromými procesy a profily.

## Reprodukce a změny

```sh
nix build --cores 0 -L .#interruption-shell --out-link result-interruption-shell
nix develop .#interruption --cores 0 -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --track-time --interrupt-js \
  --interrupt-operation backend-delayed --soak-seconds 65 \
  --output artifacts/durable-timer-local
# Stejný příkaz s backend-source nebo backend-signal ověří zbývající vstupy.
nix develop .#interruption --cores 0 -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --track-time --interrupt-js \
  --interrupt-operation panel-adopting --interrupt-handoff \
  --output artifacts/durable-panel-local
nix flake check --cores 0
```

Změny: `shell/stableRegistry.js`, `shell/runtimeInit.js`,
`shell/interruptRuntime.h`, `shell/interruptGlobal.c.inc`,
`shell/tgnome-runtime.h`, `shell/interrupt-shell.patch`, `flake.nix`,
`tests/isolated.py` a dokumentace. Soukromé Shell procesy byly sklizené;
hostitelský Shell zůstává původní PID 1350942 s původním executable.
NixOS konfigurace se neaktivovala, systémový rollback není potřeba.
Finální `nix flake check --cores 0` skončilo exit 0 a `all checks passed!`;
aktualizovaný test supervisoru byl znovu sestavený a ostatní výstupy byly
k dispozici z předchozích úspěšných kontrol.

## Další architektonická práce

Tyto obálky nepokrývají libovolný GI async callback, specializované callbackové
API jako `Gio.Cancellable.connect`, všechny bus-watch/name-own handlery ani
automaticky celý řetězec práce naplánované z backendového callbacku. Nelze je
zobecnit na bezpečný automatický watchdog všech vstupů Shellu.

Připnuté GJS má společný konstruktor a vstup `Gjs::Closure` v `gi/closure.cpp`.
Další krok je prověřit nativní evidenci původu callbacků na této hranici místo
dalšího rozšiřování povrchových JS obálek. Je nutné zachovat oddělení ochrany
provádění a životnosti alokací a ověřit další skutečné GI callbacky.
Nekonečný chráněný backend, Promise/nested vstupy, native deadlock/crash a celý
nový GJS runtime/proces stále vyžadují silnější restartovatelnou hranici.
