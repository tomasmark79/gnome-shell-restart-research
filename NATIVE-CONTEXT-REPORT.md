> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Fáze 28 — výměna GJS kontextu přes stabilní nativní GType

Datum: 21. října 2026. Klasifikace: **RESEARCH PROTOTYPE**.

**Výsledek: izolovaná nativní hranice splnila akceptační podmínky.** Jeden
`GFileEnumerator` přežil tři postupně vytvořené a zrušené `GjsContext`.
V každém kontextu fungoval skutečný GI/vfunc průchod, nativně vyvolaný vfunc
i signál s novým JS callbackem. Slabé odkazy prokázaly zánik starého globálu,
markeru, vfunc delegáta, signal callbacku a JS wrapperu zachovaného nativního
objektu. Stejná pozitivní cesta prošla Valgrindem bez hlášených chybných
přístupů do paměti při níže uvedeném nastavení.

**Restart GNOME Shellu, Mutteru ani procesu tím prokázán nebyl.** Existující
Shell z fáze 27 stále používá původní kontext a JS vlastněné GTypes. Negativní
kontrola právě tohoto vlastnického vzoru reprodukovala SIGSEGV při vyvolání
starého vfuncu po zániku jeho kontextu. Tato fáze je uzavřena; další fáze ani
plán se zde nezavádí.

## Autoritativní výsledky

Úplný strojový výsledek včetně debuggerového backtrace:
[`artifacts/native-type-verified/result.json`](evidence/reports/native-type-verified/result.json).
Je bajtově shodný s výsledkem check fáze sestaveného balíčku.
SHA-256: `5a04c95017f2d84a0fac92b433120129c0019ef32fe5555324efbe75a9a0889d`.

| Poslední relevantní ověření | Skutečný výsledek |
| --- | --- |
| Build `native-type-probe` a jeho check fáze | exit 0, všechny tři případy přijaty |
| `native` | exit 0, stderr prázdný, 3 generace, tentýž objekt `0x55555558d820` |
| `native-valgrind` | exit 0, stderr prázdný, 3 generace, tentýž objekt `0x96498e0` |
| `js-owned` | exit −11 / SIGSEGV po úspěšném novém obalení původního objektu, při vstupu do starého vfuncu |
| Opakování negativní kontroly pod GDB | SIGSEGV ve stejné cestě přes `GjsCallbackTrampoline::callback_closure` |
| Upstream testy nové varianty GJS | `Ok: 77`, `Fail: 0`; GTK4 testy zůstávají vypnuté konfigurací balíčku |
| Deadliny / úklid | žádný timeout; všechny soukromé profily odstraněny; podprocesy vyzvednuty |

Adresy objektů se porovnávají pouze uvnitř jednoho procesu. Rozdílná adresa
pod Valgrindem je očekávaná. `passed: true` u `js-owned` znamená ověřenou
negativní kontrolu, nikoli úspěšnou výměnu kontextu pro JS vlastněný GType.

Realizované výstupy:

- Probe: `/nix/store/558s749argz15dghc84c6886ig3yl1f0-tgnome-native-type-probe-0.1`.
- GJS: `/nix/store/k5p3ci05vz1kfqdxgq8nkkbp044yhv19-tgnome-native-type-gjs-1.88.1`.
- GJS testovací derivace: `/nix/store/3nhi8qzdxkhrsq87cs7a87k1sisxppq0-tgnome-native-type-gjs-1.88.1.drv`.

GJS je připnutý na 1.88.1, SpiderMonkey na 140.14.0. Nová varianta dědí
dosavadní experimentální interruption patch a přidává pouze soukromý pomocný
ABI pro převod GObject/GValue. GI/vfunc implementace se touto fází nemění.
Negativní kontrola tedy není testem čistého, nepatchovaného upstream balíčku.
Testovací nástroje z téhož připnutého nixpkgs: GDB 17.2, Valgrind 3.26.0,
Python 3.13.15.

## Reprodukovatelný původní problém

Negativní kontrola zaregistruje JS podtřídu `Gio.FileEnumerator` s GType
`TgnomeContextOwnedEnumerator`. Její `vfunc_next_file` volá JS funkci
`uiNextName` a vrací skutečný `Gio.FileInfo`. Nativní host přes dočasný
`GValue` získá vlastní silnou referenci na tento objekt. Před zrušením kontextu
vfunc správně vrací `old-context`.

Po posledním hostitelském `g_object_unref(context)` kontrola zaznamená
GObject weak-notify původního kontextu a vynulování slabých JS odkazů na jeho
globál i funkci `uiNextName`. Pak vytvoří nový kontext, importuje Gio/GObject,
definuje novou funkci vracející `replacement-context` a úspěšně v něm obalí
**tentýž nativní objekt**. Samotné vytvoření nového wrapperu problém neřeší.
Následující `g_file_enumerator_next_file()` skončí SIGSEGV.

Přežil nativní `GFileEnumerator` držený explicitní hostitelskou referencí
a jeho trvale registrovaný GType s vfunc vstupem do původního GJS trampoline.
Původní JS funkce nepřežila: slabý odkaz byl vymazán. Nová funkce se do starého
vtable automaticky nedosadí. Není tedy správné tento výsledek popsat jako
zadržení původního kontextu; selhává **platnost a přesměrování nativního vfunc
vstupu po uvolnění kontextu, který jej vytvořil**.

Přesná cesta posledního debuggerového běhu, od volajícího k místu pádu:

```text
main -> negative                         native-type-probe.cpp:243 / :234
  -> expect_name                         native-type-probe.cpp:131
  -> g_file_enumerator_next_file
  -> ffi_closure_unix64
  -> ffi_closure_unix64_inner
  -> GjsCallbackTrampoline::create_closure()::<lambda>::_FUN
  -> GjsCallbackTrampoline::callback_closure
  -> gi_callable_info_load_return_type   SIGSEGV
```

Zdroj `gi/function.cpp` načítá návratový typ z `m_info` na začátku
`callback_closure`, ještě před kontrolou `is_valid()`. Backtrace dokládá pád
při tomto přístupu. Přesná historie uvolnění alokace trampoline/GI metadata
nebyla změřena; označit konkrétní alokaci za prokázané use-after-free by
překračovalo dostupný důkaz. Bezpečné opětovné použití JS registrovaného vfuncu
nicméně přímo vyvrací reprodukovaný pád. Tato fáze tento mechanismus neopravuje.

Minimální reprodukční jádro je v `negative()` v
[`tests/native-type-probe.cpp`](tests/native-type-probe.cpp): zaregistrovat
jeden JS GType se dvěma vfuncy (`next_file`, `close_fn`), podržet jednu nativní
instanci, zahodit první kontext, vytvořit druhý a znovu zavolat `next_file`.
Nejsou potřeba Shell, Clutter, widgety, Wayland ani další UI realmy.

## Nativní varianta a přímé důkazy životnosti

`NativeEnumerator` je C++ podtřída `GFileEnumerator`, registrovaná pomocí
`G_DEFINE_TYPE` před prvním kontextem. Nativní třída obsahuje výhradně C++
adresy `next_file`, `close_fn` a nativní popis signálu `pulse`. Trvale neukládá
žádný JS callable, JSContext, kořenovaný JS objekt ani JS class data.

Host drží jedinou instanci napříč třemi generacemi. Borrowed ukazatel `active`
označuje právě připojený `GjsContext`; před jeho uvolněním se nastaví na null.
Vfunc na vlastnickém vlákně vstoupí přes `gjs_context_run_in_realm` do právě
aktivního globálu a teprve tam vyhledá `uiNextName`. `JS::Rooted` hodnoty jsou
jen lokální a jejich životnost končí před zrušením kontextu. Během mezery vfunc
vrací `G_IO_ERROR_BUSY` a nedereferencuje starý kontext.

Každá generace přímo ověřuje:

1. Čerstvý globál neobsahuje staré `uiEpoch`.
2. Volání `backend.next_file(null)` vede přes skutečné GI do C++ vfuncu a zpět
   do aktuálního JS delegáta, s výsledkem `ui-N:1`.
3. Nativní volání stejného objektu vrátí `ui-N:2`.
4. Nativní `g_signal_emit` vyvolá nový JS signal callback právě jednou;
   callback ověří aktuální generaci.
5. Před teardownem se JS handler odpojí a nativní kontrola potvrdí, že na
   `pulse` nezůstal připojen žádný handler.
6. Po dokončeném `g_object_unref(context)` jsou všechny sledované JS odkazy
   null, weak-notify kontextu proběhl a identita i GType nativního objektu
   zůstávají stejné. Teprve poté se vytváří další kontext.

V obou pozitivních bězích byly v **každé ze tří generací** zaznamenány dva
weak sweep callbacky a `globalCleared`, `markerCleared`, `callbackCleared`,
`wrapperCleared`, `signalCallbackCleared`, `released` rovné `true`.
Pozorování používá skutečné slabé `JS::Heap<JSObject*>` odkazy aktualizované
`JS_UpdateWeakPointerAfterGC`; tyto sloty nejsou GC kořeny.

Nativní GObject dostane weak-notify až při závěrečném hostitelském unref,
po všech třech kontextech. Celkem se ověří šest úspěšných vfunc volání,
tři signálová volání a čtyři mezery bez kontextu. Objekt se během žádné
z těchto mezer nezavírá; na konci se explicitně zavře a uvolní.

Pole JSON `contextsFinalized` a `nativeFinalized` jsou počty **GObject
weak-notify oznámení**, nikoli instrumentace přepsané metody `finalize`.
Weak-notify samostatně nelze zaměňovat za měření okamžiku uvolnění všech bajtů
GObject. Důkaz ukončení JS životnosti zde navíc tvoří současné vymazání pěti
slabých JS odkazů a dokončený synchronní teardown. Ověřený zdroj
`GjsContextPrivate::dispose()` odstraní kořeny a volá `JS_DestroyContext`;
nejde o odhad podle velikosti haldy. Adresy alokátor může znovu použít, proto
se zánik kontextů nedokazuje rozdílnými adresami.

## Inventář vlastníků a možných návratových referencí

Před implementací byly přečteny hranice fází 27/28 v `PLAN.md`, existující
generátory Panel/dateMenu, soukromý realm bridge a příslušné GJS části.
Následující inventář rozlišuje původní implementaci od izolovaného důkazu.

| Vlastník / reference | Riziko zadržení nebo neplatného callbacku | Zpracování v tomto experimentu |
| --- | --- | --- |
| Původní ShellGlobal, GjsContext a jeho main/internal globals | Kontekstové kořeny, importer, GI native registry, moduly a source maps zachovávají původní backend | Ve stávajícím Shellu zůstávají; experiment ShellGlobal vůbec nevytváří |
| Kanonický Panel a osm dateMenu GTypes z fáze 27 | JS prototypy, metody, konstrukce a libffi vfunc trampolines patří původnímu kontextu | Negativní kontrola izoluje stejný vzor na jediném JS GType; pozitivní typ je celý nativní |
| `_tgnomeUiBackend`, Main/služby, rodičovské JS třídy, realm loader | Silné backend vazby propojují UI globály s původním kontextem a jeho GI registry | Do nového experimentu se nepřenášejí; žádné další UI realmy nevznikají |
| dateMenu WeakMaps, scope, instance sety, constructor stack a odložený úklid | Samotné WeakMaps nejsou silné kořeny klíčů, scope a instance grafy však mohou držet implementace | V izolovaném probe nejsou; nejsou tím migrovány nebo nově ověřeny |
| Nativní emitery a GClosure ze signal spojení, včetně dříve žurnálovaných AppSystem/model spojení | GClosure uchovává callable a jeho kontextovou příslušnost; odpojení patří do teardown kontraktu | Jediný experimentální JS handler `pulse` se explicitně odpojí a ověří se nepřítomnost handleru |
| GLib zdroje, async GI closures, Promise jobs, callback/provenance registry | Mohou uchovávat callable nebo původní JSContext i při odloženém vyvolání | Probe je nevytváří; GJS vlastní interní zdroje ukončuje jeho dispose. Přenos rozpracovaného async provozu neověřen |
| JS `FinalizationRegistry` a payloady z předchozích realm testů | Pozorovatel nesmí sám držet sledovaný cíl | Nový probe používá externí slabé SpiderMonkey sloty a GObject weak-notify, bez JS FReg |
| Experimentální nativní instance, její vtable a signál `pulse` | Musí být nezávislé na obou kontextech | Hostitelská silná reference, statické C++ funkce, čistě nativní signal metadata |
| Vlastnost `container` instance (`GFile`) | Nativní vlastněná reference | Dočasný hostitelský ref se uvolní po konstrukci; dál ji vlastní enumerátor; neobsahuje JS callback |
| Dočasné `GValue`, GJS wrapper, GI typ/prototyp cache a toggle refs | Mohly by uchovat původní wrapper nebo přístup do starého kontextu | GValue se ihned unsetne; lokální JS roots skončí; slabý wrapper je po dispose null; další kontext vytvoří vlastní wrapper |
| Globální `active`, lokální dispatch data a dočasné `GFileInfo` | Nebezpečí borrowed ukazatele po teardownu nebo přežití lokálních roots | `active=null` před unref; jediná vlastnická thread; dispatch je synchronní; každý info se unrefne |
| Weak callback data a JS slabé sloty | Pozorovatel musí přežít všechny GC callbacky svého runtime | Data jsou na stacku do návratu z context unref; aktualizují se jen nenulové sloty; runtime pak callbacky zruší |

Tabulka je inventářem mechanismů relevantních k této hranici, nikoli tvrzením,
že byly všechny živé objekty skutečné Shell relace migrovány nebo spočítány.
Žádná taková integrace v této fázi neproběhla.

## Valgrind, chyby při přípravě a omezení důkazu

Pozitivní případ byl skutečně spuštěn příkazem odpovídajícím:

```sh
valgrind --quiet --error-exitcode=97 --leak-check=no \
  --undef-value-errors=no --smc-check=all-non-file \
  ./tgnome-native-type-probe native
```

Výsledek: exit 0, prázdný stderr, všechny lifetime/vfunc/signal assertions
prošly. Žádná paměťová chyba zahrnutá tímto nastavením nebyla hlášena.
`--quiet` neprodukuje závěrečnou statistiku; neexistující číselný
`ERROR SUMMARY` se zde nedoplňuje. Leak check byl vypnutý a hlášení
nedefinovaných hodnot také; jejich nepřítomnost ani úplná absence chyb ve
všech možných cestách tím prokázána není. Negativní případ byl měřen GDB,
nikoli Valgrindem.

Během sestavení experimentu byly opraveny dvě chyby harnessu: převod GValue
vyžaduje předchozí import Gio/GObject v každém novém kontextu; doplněné
weak sloty se nesmějí předat sweep helperu jako null. Dočasný pád v samotném
weak pozorovateli nebyl přijat jako negativní důkaz. Poslední uložený výsledek
obsahuje opravený pozorovatel a znovu reprodukovaný pád v původním GI/vfunc
řetězci. V konečných pozitivních bězích nejsou chyby ani varování. GDB
závěrečného negativního běhu nevydal varování o automatickém načítání skriptů;
auto-load je výslovně vypnutý.

Předpoklady pozitivního kontraktu: jedno vlastnické vlákno, synchronní vfunc,
žádný rozpracovaný callback při odpojení, úplný seznam zde existujících
handlerů a explicitní hostitelská reference na nativní objekt. Neověřeno:
souběžný teardown, cizí vlákna, neukončené async operace, obnova po libovolné
JS výjimce, více současných kontextů, libovolné typy St/Clutter, skutečný
Shell runtime a procesová havárie. Valgrind důkaz je omezen na vykonané cesty.

## Izolace a vztah k restartu GNOME Shellu

Supervisor spouští každý případ v oddělené process group s dočasným HOME/XDG
profilem, bez DISPLAY/WAYLAND_DISPLAY/XAUTHORITY a s adresami neexistujících
session/system D-Bus socketů. Core dumpy jsou vypnuté. Deadliny jsou 20 s
pro běžné procesy a debugger a 60 s pro Valgrind; případný timeout by vedl
ke kill celé skupiny a neúspěšnému výsledku. V konečném běhu nenastal.
Jde o samostatný nativní proces bez připojení ke grafické relaci, nikoli
o zvláštní bezpečnostní sandbox proti úmyslnému obcházení těchto omezení.

Aktivní Shell zůstal PID `1350942` s executable
`/nix/store/8m77m1b9n4z4lv00l7d5455lkfbqy5jg-gnome-shell-50.5/bin/.gnome-shell-wrapped`.
Nebyla provedena aktivace NixOS, výměna desktopového balíčku, logout, zásah
do GDM ani restart běžícího Shellu. Nové balíčky jsou samostatné výstupy Nix
store a lokální out-link.

V této fázi nebyl spuštěn compositor ani Wayland klient a nebylo měřeno
přežití Wayland spojení. Dřívější
[protokol fáze 27](DATE-MENU-REALM-REPORT.md) doložil přežití původních
Wayland/XWayland spojení při rekonstrukci UI se stejným procesem, kompozitorem
a GJS kontextem. Tyto historické výsledky se zde neopakovaly a nepovyšují se
na důkaz restartu procesu. Úspěšný build, klientský PID, tento Valgrind ani
výměna kontextu v samostatném probe takový důkaz neposkytují.

## Soubory a reprodukce

Změny provedené touto fází:

- `flake.nix`: samostatné balíčky `native-type-gjs` a `native-type-probe`,
  check fáze a potřebné testovací nástroje; původní realm/Shell balíčky zachovány.
- `shell/gjsNativeType.cpp.inc`: nový soukromý převod existujícího GObject
  do/z globálu kontextu přes GValue; bez instalovaného veřejného ABI nebo GIR.
- `tests/native-type-probe.cpp`: nativní GType, tři kontexty, rozšířené slabé
  odkazy, reálný GI/vfunc/signal provoz a minimální negativní kontrola.
- `tests/native-type-supervisor.py`: izolace, deadliny, Valgrind, GDB a přesné
  přijetí očekávaného negativního výsledku.
- `artifacts/native-type-verified/result.json`: nezměněná kopie posledního
  check výsledku včetně backtrace.
- `NATIVE-CONTEXT-REPORT.md`: tento jediný finální protokol fáze.
- `result-native-type-probe`: lokální out-link na sestavený balíček.

Příkazy z kořene workspace:

```sh
# --cores 0 zpřístupní všechna dostupná jádra; stroj má 16 logických CPU.
# path: obejde filtrování zatím netrackovaných souborů lokálním Gitem.
nix build path:.#native-type-probe --cores 0 -L --out-link result-native-type-probe
cat result-native-type-probe/share/tgnome/native-type-report.json

# Izolovaná reprodukce negativní kontroly včetně kontrolních běhů:
nix shell --impure --expr \
  'let f = builtins.getFlake ("path:" + toString ./.); p = import f.inputs.nixpkgs { system = "x86_64-linux"; }; in [ p.python3 p.gdb p.valgrind ]' \
  --command python3 tests/native-type-supervisor.py \
  ./result-native-type-probe/bin/tgnome-native-type-probe /tmp/tgnome-native-type-reproduction.json

# Výpis již uskutečněných upstream testů bez jejich opakování:
nix log /nix/store/3nhi8qzdxkhrsq87cs7a87k1sisxppq0-tgnome-native-type-gjs-1.88.1.drv
```

Supervisorový příkaz spouští i kontrolní pozitivní a Valgrind případ, aby
byla reprodukce izolovaná a všechny podprocesy uklizené; tyto příkazy jsou
návodem, nikoli tvrzením o dalším běhu po finálním ověření. Oba vstupy používají
`path:`, aby reprodukci neovlivnilo Git filtrování netrackovaných souborů.

Závěr: pro tento nativně vlastněný GType je prokázaná opakovaná výměna
celého GJS kontextu při zachování nativní instance a uvolnění starých JS
objektů. Pro dosavadní JS registrované GTypes stejný postup bezpečný není.
Celý GNOME Shell ani compositor restartován nebyl. Práce na této fázi končí.
