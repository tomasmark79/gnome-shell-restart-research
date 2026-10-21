> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Nový UI global a trvalý nativní backend

Navazující [PANEL-REALM-REPORT.md](PANEL-REALM-REPORT.md) již převádí skutečný
panel Shellu na tuto hranici a opravuje zadržování realmů v JIT cache, které
samostatný třígenerační test neodhalil. Níže zůstávají důkazy samostatné etapy.

Stav k 21. říjnu 2026: **RESEARCH PROTOTYPE**. Samostatný GJS experiment
prokázal výměnu tří UI globalů s vlastními ES moduly, bootstrapem, Promise
a timer callbacky. Trvalý nativní GType, jeho vfunc i tentýž objekt mohou
volat postupně nové UI implementace. Odpojené UI globaly se uvolnily.

Nejde zatím o nový desktop GNOME Shellu. JSContext, SpiderMonkey runtime,
proces a nativní registry zůstávají původní. Tento experiment nevytváří
kompozitor ani grafické klienty a neprokazuje jejich přežití při výměně globalu
v opravdovém Shellu. Dosavadní klientské testy z
[předchozí etapy](NATIVE-CLOSURE-REPORT.md) ověřují jiný mechanismus:
rekonstrukci UI ve stejném globalu.

## Zjištěná hranice

Připnuté GJS 1.88.1 vytváří jeden výchozí a jeden interní global.
`gjs/global.cpp` již obsahuje interní konstruktor dalšího výchozího globalu,
včetně samostatných registrů modulů. Samotné vytvoření globalu ale nestačí:

- `gjs/internal.cpp:gjs_internal_compile_module()` vstupuje do
  `AutoMainRealm`. Standardní loader by závislosti nového UI kompiloval
  do původního globalu.
- `gjs/module.cpp:import_native_module_sync()` také vstupuje do
  `AutoMainRealm`. V tomto experimentu je to záměrná hranice: nativní GI
  bindingy a jejich kanonické JS prototypy zůstávají v backendu.
- `gi/private.cpp` odmítá znovu registrovat existující jméno GType.
  Životnost GType nekončí sběrem JS objektů.

Autoritou je realizovaný zdroj
`/nix/store/c5il8xcpwhinm6jzzpp4xl3bz7z71vnz-gjs-1.88.1.tar.xz`.

## Implementace

[shell/gjsRealm.cpp.inc](shell/gjsRealm.cpp.inc) přidává soukromý embedding
symbol pouze do nové varianty `realm-gjs`. Vytvoří global ve stejném
compartmentu, ponechá kořenový legacy importer backendu a vytvoří samostatný
ES module loader. Nový loader má vlastní registry a kompilátor alokovaný
v cílovém realmu; kompilátor nepoužívá `AutoMainRealm`. Kopíruje mapu
handlerů schémat z původního loaderu.

Vrácený JSObject musí volající okamžitě rootovat. Funkce ověřuje vlákno
vlastníka a stav zániku kontextu. Symbol nemá veřejný header ani GIR API.
Tato varianta není připojena k dosavadním Shell balíčkům ani k CLI.

[tests/realm-probe.cpp](tests/realm-probe.cpp) načte v každé generaci stejné
URI vstupního i závislého modulu. Kontroluje identitu jejich globalu,
novou JS třídu, samostatné provedení modulu a totožnost původního nativního
objektu i jeho kanonické GI třídy. Zavede skutečný ESM bootstrap GJS
včetně TextEncoder, console a timerů. Dokončí Promise → timer řetězec
a skutečný callback `Gio.Cancellable`, jehož nativní registraci následně odstraní.

Varianta s delegátem registruje `TgnomeStableRealmEnumerator` pouze v backendu.
Stejná instance `Gio.FileEnumerator` a stejná backendová třída přežijí všechny
tři generace. Volání nativního `next_file()` projde C vfunc trampolínou do
nového UI delegáta a vrátí jméno příslušné generace. Po odpojení delegáta
tentýž nativní vstup vrátí `G_IO_ERROR_BUSY`; další generace jej opět obslouží.
Jde o syntetický enumerátor bez čtení adresáře.

## Výsledky a kontrolní případy

Úplný strojový důkaz je v
[artifacts/realm-verified/result.json](evidence/reports/realm-verified/result.json).

| Případ | Pozorovaný výsledek |
| --- | --- |
| `plain` | Tři samostatné grafy modulů; všechny tři globaly, markery a tokeny se uvolnily. |
| `gtype` | První registrace typu uspěla, další dvě skončily očekávanou duplicitou. První global i jeho modulové objekty zůstaly zadržené; další dva globaly se uvolnily. |
| `delegate` | Stejný backendový GType/vfunc/objekt obsloužil tři nové UI implementace. Po odpojení se všechny tři UI globaly a jejich sledované objekty uvolnily. |
| `delegate-held` | Záměrně ponechaný poslední delegát zadržel poslední global i modulové objekty. První dvě generace se uvolnily. Pozorovatel tedy rozpoznal známou chybu vlastnictví. |

Všechny čtyři případy skončily exit 0, bez stderr, bez překročení limitu
a s odstraněným soukromým profilem. U `gtype` úspěch testu znamená
**potvrzení překážky**, nikoli podporu opakované registrace typu.

GC kontroly používají WeakRef v backendu, odstranění silných kořenů,
`ClearKeptObjects`, šest GC průchodů a zpracování GLib úloh. Tyto výsledky
platí pro konkrétní sledované objekty, nikoli jako důkaz nepřítomnosti všech
nativních úniků paměti.

Finální probe je
`/nix/store/f7rj5kfqi201n6q0ihb7i582hvclcchc-tgnome-realm-probe-0.1`.
Nové GJS je
`/nix/store/d13jmmrfsd62aw0j1m06ji1n9gyqwgg6-tgnome-realm-gjs-1.88.1`.
Jeho sestavení prošlo všemi 77 nakonfigurovanými upstream testy, 0 selhání.
GTK4 testy nejsou v připnuté konfiguraci zapnuté. Kompilace použila
`--cores 0`, v logu `-j16`.

Finální `nix flake check --cores 0 -L` skončilo exit 0; kontroly využily
již realizované výsledky včetně nového `checks.x86_64-linux.realm`.
Samostatně spuštěný supervisor mimo Nix build také prošel všemi čtyřmi
případy a vytvořil obsahově shodný JSON výsledek.

Při vývoji selhal delegovaný test na opakované deklaraci globálního
`let busy`. Oprava omezila proměnnou na blok. Chybová větev také odhalila,
že je nutné enumerátor zavřít před zánikem kontextu: jinak dispose vyvolal
`close_fn` během GC a GJS callback odmítlo. Probe nyní zavírá objekt před
disposalem i po neúspěšném případu. Finální kontroly vyžadují prázdný stderr.

## Reprodukce a vrácení změny

```sh
nix build --cores 0 -L .#realm-probe --out-link result-realm-probe
python3 tests/realm-supervisor.py \
  ./result-realm-probe/bin/tgnome-realm-probe \
  ./tests/realm-modules /tmp/tgnome-realm-local.json
nix flake check --cores 0 -L
```

Supervisor nastavuje vlastní dočasné HOME/XDG adresáře, odstraňuje display
proměnné, obě D-Bus adresy směruje na neexistující soukromé sockety,
vypíná core dump a každému dítěti dává vlastní procesní skupinu a limit
20 sekund. Děti vždy sklidí. Hostitelský Shell zůstal původní PID 1350942;
neproběhla aktivace NixOS ani nahrazení relace. Odstranění odkazu
`result-realm-probe` odstraní pouze GC root experimentálního balíčku.

Změny: `flake.nix`, nový `shell/gjsRealm.cpp.inc`, `tests/realm-probe.cpp`,
`tests/realm-supervisor.py`, `tests/realm-modules/entry.js`,
`tests/realm-modules/state.js`, uložený výsledek a dokumentace.

## Další krok k celému Shellu

Nový global se samostatným module grafem už není pouze hypotéza.
Zbývá převést skutečnou komponentu GNOME Shellu na tuto hranici: trvalý
kanonický GType/vfunc/backend a odpojitelnou UI implementaci v novém realmu.
Rozhodující další test musí použít skutečné St/Clutter UI v izolovaném Shellu,
sledovat sběr původního realmu a zachovat původní Wayland/XWayland klienty.

Stávající `GObject.registerClass` v UI nelze jednoduše opakovat v novém globalu.
Je třeba explicitní plán vlastnictví každého takového typu, callbacku a vfunc.
Sdílený legacy importer také nemá samostatné UI generace. Nejsou ověřené
libovolné dynamic imports, rozšíření, přerušené Promise úlohy ani obnova po
chybě během výměny realmu v Shellu. Stejný JSContext a hlavní smyčka zůstávají
společnou doménou selhání. Nativní deadlock a pád procesu vyžadují další
architektonickou hranici; tento experiment je neřeší.
