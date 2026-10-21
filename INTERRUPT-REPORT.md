> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Přerušení zablokovaného GJS: nativní prototyp a jeho hranice

Tento report zachycuje fázi 17. Následující
[BOUNDARY-REPORT.md](BOUNDARY-REPORT.md) dokumentuje novou ochranu, která
testované nepodporované vnoření odmítá; historické výsledky níže patří
předchozí variantě.

## Výsledek

Samostatný nativní prototyp umí přerušit nekonečnou JS smyčku z watchdog vlákna
a pokračovat ve stejném GJS kontextu. S oddělenou úpravou GJS funguje návrat
z GLib callbacku i GObject signálu na vlastněnou nativní hranici. Původní
GObject a JS data zůstávají použitelné a nativní heartbeat pokračuje.

Klasifikace je **RESEARCH PROTOTYPE**, `shellRecoveryDemonstrated=false`.
Tato fáze nepouští Mutter, Wayland klienty ani GNOME Shell. Upravené GJS není
zapojené do stávajících Shell balíčků ani aktivované v hostitelském systému.
Vnořený test prokázal nebezpečné pokračování staršího JS rámce, takže současný
prototyp nesmí být vydáván za obecně bezpečnou obnovu Shellu.

## Připnuté zdroje a původní překážka

GJS 1.88.1 veřejně poskytuje `gjs_context_get_native_context()`, který vrací
SpiderMonkey `JSContext*`. Použitý SpiderMonkey je 140.14.0. Jeho
`js/Interrupt.h` dovoluje požádat o callback z jiného vlákna; callback se
vykoná na JS vlákně. Engine může callback spustit i z vlastních důvodů,
proto test vrací přerušení pouze při atomicky evidovaném požadavku watchdogu.

Neupravené GJS po přerušení přímého `gjs_context_eval()` vrátí chybu a zůstane
použitelné. U GI callbacku ale `gi/function.cpp` nebo `gi/value.cpp` považuje
neodchytitelnou chybu za fatální a zavolá `g_error()`. Kontrolní proces skutečně
skončil SIGABRT. Stejný postup ve společném Shell/Mutter procesu by ukončil
kompozitor, a proto se proti Shellu v této fázi nepoužil.

První pokus dodat běžnou JS výjimku přímo v interrupt callbacku tento problém
nevyřešil: engine při návratu `false` stále provedl neodchytitelné ukončení.
Předpoklad o spouštění `catch`/`finally` byl experimentem vyvrácen.

## Experimentální změna GJS

`gjs-interruption.patch` přidává privátní značku výslovného přerušení na konkrétní
GjsContext. Nastaví ji nativní interrupt hook bez návratu do JS engine.
První GI hranice ji spotřebuje a použije existující cestu hlášení JS chyby
namísto ukončení procesu. Neoznačená neodchytitelná chyba zachovává původní
fatální chování. Původní větev `system.exit()` zůstává před touto výjimkou.
Skutečné vyčerpání paměti se v testu nevyvolávalo.

Značka není trvalé vypnutí fatálních chyb. Přímý nativní eval musí nespotřebovanou
značku po návratu potvrdit a odstranit; oba GI callbackové mosty ji spotřebují
samy. Negativní test po pěti úspěšných označených přerušeních vyvolal další
neoznačené přerušení ve stejném kontextu a proces opět skončil SIGABRT.

`catch` ani `finally` přerušeného JS se nevykonají. Nelze proto spoléhat na
JS `finally` pro uvolnění mutexu, snížení lifetime čítače či dokončení změny
backendového modelu. Zda takový rozpracovaný stav může konkrétní rekonstrukce
bezpečně převzít, tento jednoduchý kontextový test neprokazuje.

## Ověřené experimenty

| Experiment | Pozorovaný výsledek |
| --- | --- |
| Neupravené GJS: tři přímé eval smyčky | Každá přerušena za 500 ms; stejný kontext a původní objekt zachované |
| Neupravené GJS: GLib callback | Proces SIGABRT; kontrolní negativní výsledek |
| Upravené GJS: tři přímé eval smyčky | Stejná identita a data; značky potvrzené nativním volajícím |
| Upravené GJS: označený GLib callback | Návrat do nativní smyčky, heartbeat pokračuje, značka spotřebovaná |
| Upravené GJS: označený GObject signál | Stejný úspěšný návrat přes druhý callbackový most |
| GC bez požadavku watchdogu | Žádné dodatečné přerušení |
| Neoznačená chyba po označených obnovách | SIGABRT; výjimka není trvalá |
| JS → C → JS vnoření | Vnější JS po přerušení vnitřního callbacku pokračoval; `recoveryProven=false` |

Poslední řádek je zásadní otevřená hranice, nikoli úspěch obnovy. Nativní
volající může pokračovat s částečně změněným modelem. Před integrací do Shellu
je nutné rozpoznat a odmítnout nepodporované vnoření a otestovat všechny
použité vstupy do JS, včetně Promise jobs. Samotná jednorázová značka to neřeší.

## Sestavení, testy a izolace

Soukromý runtime:

```
/nix/store/gis690dk01pg67n31xz7cgz9mccajzwv-tgnome-gjs-1.88.1
```

Jeho standardní upstream testy zaznamenaly 77 úspěchů a 0 selhání. Kompilace
s `--cores 0` skutečně použila `-j16`. Kontrola dynamického linkování potvrdila
právě tento libgjs a připnutý libmozjs-140, nikoli hostitelskou knihovnu.

Konečné charakterizační reporty:

- `/nix/store/94nh8767djvz17kva7ddk2hjjdrr84lb-tgnome-interrupt-baseline-0.1/share/tgnome/interrupt-report.json`
- `/nix/store/lkdamgn4yl6zxnqbicndnhfwdgm95i0h-tgnome-interrupt-probe-0.1/share/tgnome/interrupt-report.json`

Oba mají `passed=true` ve smyslu uvedených experimentálních bran, včetně
očekávaných negativních výsledků. Report upravené varianty má čtyři oddělené
procesy: neoznačený SIGABRT, označené návraty s exit 0, znovu neoznačený
SIGABRT po obnově a charakterizaci vnoření s exit 0. Všechny procesy byly
sklizené a jejich soukromé runtime profily odstraněné.

Supervisor nastavuje adresy neexistujících socketů v soukromém runtime adresáři,
odstraní displejové proměnné, zakáže core dump a vlastní procesní skupiny
i časové limity. Testy neobjevují hostitelský D-Bus ani displej.
Surový binární probe vyžaduje supervisorový příznak a bez něj odmítne běh.
`nix flake check --cores 0` nyní zahrnuje oba charakterizační cíle a prošel.

```sh
nix build --cores 0 --print-build-logs .#interrupt-probe --out-link result-interrupt-probe
nix build --cores 0 --print-build-logs .#interrupt-baseline --out-link result-interrupt-baseline
cat result-interrupt-probe/share/tgnome/interrupt-report.json
nix flake check --cores 0
```

Změněné soubory: `shell/gjs-interruption.patch`, `tests/interrupt-probe.cpp`,
`tests/interrupt-supervisor.py`, `flake.nix` a dokumentace.

## Další engineering krok

Nejprve omezit povolení přerušení na prokazatelně vlastněnou vnější nativní
hranici a odmítnout vnořené vstupy. Pak teprve připojit watchdog k oddělenému
headless Shell sestavení a ověřit rekonstrukci po skutečně zablokovaném
callbacku s původními Wayland/XWayland spojeními. Blokování uvnitř nativního C,
pád kompozitoru a obecně rozpracované backendové operace zůstávají další,
samostatně nevyřešené případy.
