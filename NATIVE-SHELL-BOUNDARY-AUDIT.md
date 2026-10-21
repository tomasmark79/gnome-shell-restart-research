> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Fáze 29 — audit přenositelnosti nativní hranice do GNOME Shellu

**Klasifikace: RESEARCH / READ-ONLY AUDIT. Datum: 21. října 2026.**

**Rozhodnutí: GO pro jediný izolovaný experiment se skutečným `St.Adjustment`
z knihovny GNOME Shellu. NO-GO pro výměnu kontextu celého Shellu nebo jeho
živého UI.** Doporučený objekt je samostatná nativní instance s `actor=NULL`,
bez transitions, bez rodičovského ScrollView a bez inicializace ShellGlobal.
Nejde o nový napodobený GType z testu ani o objekt převzatý z aktivní relace.

Audit našel konkrétní překážku přenosu: **silná reference sama nestačí**.
`StScrollView::dispose` explicitně disponuje své adjustments, i když na ně
někdo jiný drží reference. Druhá překážka je globální: `ShellGlobal` vlastní
GjsContext a nativní plugin za běhu volá do JS přes WM signály, rozhraní
dialogů a input vfuncy. Zde chybí doložený kontrakt pro interval bez JS.

V této fázi vznikl pouze tento dokument. Žádný kandidát nebyl implementován
ani spuštěn, žádný build nebo dříve úspěšný runtime test se neopakoval.

## 1. Z čeho audit vychází

Zkontrolovány byly aktuální derivace, pomocný ABI i zdrojové testy fáze 28,
generátory Panel/dateMenu a native-loop patch, hranice v `PLAN.md` a reporty
fází 27/28, persistent-context rekonstrukce a nativních hranic. Aktuální
implementace má tyto oddělené větve:

| Větev | Skutečný obsah a důsledek |
| --- | --- |
| `realmGjs` → `realmShell` | `flake.nix:85–90,140–173`; původní GJS kontext, nové UI globály, kanonické JS GTypes. Není příjemcem ABI fáze 28. |
| `nativeTypeGjs` → `nativeTypeProbe` | `flake.nix:91–117`; soukromý GValue bridge a samostatný `GFileEnumerator` probe. Žádný Shell ani St v buildInputs tohoto probe. |
| Starší reset větev | `shell/runtimeGlobal.c.inc:11–21` umí clear/new členu `js_context`; `shell/tgnome-runtime.h:302–320` rozlišuje in-place rekonstrukci od resetu. Přítomnost reset kódu není důkazem jeho bezpečnosti. |
| Nativní Mutter loop | `shell/native-loop.patch:23–44` přesouvá hlavní loop mimo eval JS. Odděluje zásobník loopu, nikoli životnost všech callbacků. |

Soubor `PLAN.md` končí požadavkem na experiment fáze 28; jeho starší věta
„Next test…“ nebyla považována za aktuální stav. Rozhodující je
[finální protokol fáze 28](NATIVE-CONTEXT-REPORT.md) a skutečný
[výsledek](evidence/reports/native-type-verified/result.json), který byl znovu pouze
přečten a bajtově porovnán s check výsledkem realizovaného balíčku.

Uložený pozitivní běh i Valgrind běh mají exit 0, prázdný stderr, tři generace,
jedinou nativní adresu v každém procesu a všech pět slabých JS odkazů vymazaných
po každém kontextu. Negativní běh má exit −11, úspěšné nové obalení objektu
a debuggerový pád:

```text
g_file_enumerator_next_file
  -> ffi_closure_unix64 -> ffi_closure_unix64_inner
  -> GjsCallbackTrampoline::create_closure()::<lambda>::_FUN
  -> GjsCallbackTrampoline::callback_closure
  -> gi_callable_info_load_return_type   SIGSEGV
```

Přežil nativní objekt a vfunc vstup jeho JS registrovaného GType; původní JS
funkce i globál byly uvolněny. U konkrétní alokace trampoline/GI metadata
nebylo změřeno, kdy byla uvolněna. Tento audit proto neoznačuje přesnou
alokaci za diagnostikované use-after-free. Prokazatelně selhalo bezpečné
vyvolání původního nativního vfunc vstupu po zániku jeho JS vlastníka.

Historické výsledky fáze 27 prokazují rekonstrukci UI a zachování původních
klientských spojení při stejném Shell/Mutter/GJS runtime; report to výslovně
uvádí na řádcích 4–8. Neprokazují přežití výměny GjsContext. V uložených
`date-menu-realms-verified` i `date-menu-realms-failure-verified` je `passed=true`.
Audit nezavedl nové Wayland měření.

## 2. Přesné zdroje a význam odkazů

Čísla řádků `S:`, `G:`, `M:` níže odkazují na členy připnutých zdrojových
archivů, nikoli na přibližné řádky jiné upstream verze. Lokální patche mohou
řádky v sestaveném stromu posunout; jsou uváděny zvlášť.

| Značka | Archiv / kořen členu |
| --- | --- |
| S | `/nix/store/spl25qj4dh6z96rv3jhkmqhya2610rrl-gnome-shell-50.5.tar.xz` / `gnome-shell-50.5/` |
| G | `/nix/store/c5il8xcpwhinm6jzzpp4xl3bz7z71vnz-gjs-1.88.1.tar.xz` / `gjs-1.88.1/` |
| M | `/nix/store/qcp1zwmxr9kd5l8zqawz658ffjb7c0lk-mutter-50.5.tar.xz` / `mutter-50.5/` |

`flake.nix:3` připíná nixpkgs na
`8ce73368d1efd4d657e9064d29b144a52046b4e8`. Shell i Mutter jsou 50.5,
jejich API/typelib verze je **18**, nikoli 50 (`S:meson.build:13`,
`M:meson.build:10`). GJS je 1.88.1, SpiderMonkey 140.14.0.

Ověřené realizované knihovny pocházejí z
`/nix/store/3c91y87dbgav2rp43xk1rn8gcq2vh4jv-gnome-shell-50.5/lib/gnome-shell`:
`libst-18.so`, `libshell-18.so`, `St-18.typelib`, `Shell-18.typelib`.
`readelf --dyn-syms` potvrdil exporty `st_adjustment_get_type`,
`st_adjustment_new`, `st_adjustment_get_value`, `st_adjustment_set_value`
a `st_adjustment_get_actor`. Knihovny nebyly pro tento audit načteny do probe.

Kontrolní SHA-256 obsahu vybraných členů archivů:

| Člen | SHA-256 |
| --- | --- |
| S:`src/st/st-adjustment.c` | `b53cb789623a740d6fbcda23b5145a7168a84f289a8bfeeb14290c48d9613f4c` |
| S:`src/st/st-scroll-view.c` | `460fe2c327c645d3a3a2d94f8b62e35e10915190de400a5d6f6eb5aa57b5f362` |
| S:`src/shell-global.c` | `04dcb740f01ca3d9e31a59ee97f9182cafcb58c3414387afc97d0b73a6ed2d20` |
| G:`gi/object.cpp` | `b9028ac507624c99f3f81996309b546b820e3d97edc2c5a4b04e848658e249ee` |
| M:`src/wayland/meta-wayland.c` | `a23489662e0311e14f312191729094f4a318d8f4c1335a8ad4220d0a1e8f00cd` |

## 3. Mapa objektů, vlastníků a callbacků

„Nativní typ“ zde znamená nativní registraci GType/vtable, nikoli automatický
příslib nezávislé životnosti. Externí GClosure, JS podtřída, explicitní dispose
nebo vlastnictví cizího backendu mohou tuto nezávislost omezit.

| Objekt / typ | Registrace, vlastník a relevantní vstupy | Vztah ke GjsContext a důkaz |
| --- | --- | --- |
| `MetaContext`, `MetaBackend`, `MetaDisplay`, compositor a stage | Nativní Mutter graf. MetaContext drží display, backend a Wayland compositor; backend poskytuje stage. | Vlastnictví je nativní, ale emitery mohou mít JS handlery. `M:src/core/meta-context.c:88–91,467–470,792–810`; `S:src/shell-global.c:984–996`. Context nesmí být zrušen jako součást JS teardownu. |
| `MetaWaylandCompositor`, `wl_display`, klienti | Nativní GObject vlastní serverový `wl_display`; ten není GObject. Surface/resource a frame callbacks mají protokolový životní cyklus. | `M:src/wayland/meta-wayland.c:104–105,821–856,874–878`; shutdown volá `wl_display_destroy_clients`, finalizace `wl_display_destroy`. To jsou nepřijatelné cesty pro zachování spojení. |
| `MetaWaylandSurface`, `MetaWindowActor` | Nativní GTypes; surface obsluhuje `wl_resource`, actor je nativní podtřída Clutter.Actor řízená compositor/window grafem. | `M:src/wayland/meta-wayland-surface.c:95–103,1838–1841`; `M:src/compositor/meta-window-actor.c:134–136,637…`. JS animace a signály nad nimi jsou další kontextové vazby. Držení actor pointeru neuchová samo protokolové spojení. |
| `ShellGlobal` | Nativní GType; drží `GjsContext`, settings, WM, app-system/tracker/cache/usage. Plugin, context/display/backend/stage jsou navázány z Mutteru. | Přímý vlastnický cyklus se JS globálem je zdokumentován v `S:src/shell-global.c:65,436–438,459–466,677–687`. `_shell_global_destroy_gjs_context` je shutdown helper `(skip)`, nikoli API bezpečného přepojení za provozu. |
| `GnomeShellPlugin`, `ShellWM` | Nativní plugin vfuncy map/minimize/destroy/switch_workspace volají nativní WM emise. ShellGlobal drží WM; WM má `MetaPlugin*`. | `S:src/gnome-shell-plugin.c:62–70,91–158,233…`; `S:src/shell-wm.c:13–17,42,64–205`. JS `WindowManager` připojuje handlery a volá `completed_*`: `S:js/ui/windowManager.js:500–537,1162–1164,1219–1221`. Vynechaný completion během mezery není bezpečný fallback. |
| `ShellAppSystem`, `ShellWindowTracker` | Nativní singletony vlastněné ShellGlobal, aplikace/window mapy a nativní cache/display/window signály. | `S:src/shell-global.c:1676–1694`; `S:src/shell-app-system.c:63,303–305,328–330`; `S:src/shell-window-tracker.c:49,566–569,626–631,675–682`. Nativní existence může pokračovat, JS odběratele je nutné explicitně odpojit. Nelze předpokládat, že nejsou kořenem starých callbacků. |
| `StWidget` a čistě nativní potomci | Nativní typ; allocate/paint/map/unmap/input vfuncy jsou C; actor graf, theme/texture cache a animace drží další vazby. | `S:src/st/st-widget.c:128,563–564,893–911,1611–1618,1692–1696`. Nativní base class nechrání JS podtřídu, jejíž vlastní vtable ukazuje do GJS. Destroy rodiče může zničit aktory bez ohledu na externí ref. |
| `StAdjustment` | Nativní GObject s `ClutterAnimatable`; číselný stav, slabý `actor`, vlastní transition hash. GObject get/set/constructed/dispose/dispatch vfuncy jsou C. | `S:src/st/st-adjustment.c:41–64,100–110,215–231,281–333`. Bez actoru/transitions nemá v prohlédnuté implementaci cestu na ShellGlobal/GjsContext. Přidané JS signal closures jsou přesto kontextové. |
| Adjustment uvnitř `StScrollView` | ScrollView vytváří a vlastní oba adjustments, scrollbar a child graf je používají. | `S:src/st/st-scroll-view.c:1015–1034`; při dispose na adjustments volá `g_object_run_dispose`, pak clear (`259–267`). Externí ref brání uvolnění paměti, nikoli dispose. Tento vlastnický vzor je z doporučení vyloučen. |
| `ShellBlurEffect` | Nativní Clutter.Effect, native set_actor/paint_node, Cogl framebuffer/pipeline/texture graf. | `S:src/shell-blur-effect.c:69–92,111–119,196–202,781–787`. Skutečné použití získává stage/backend/CoglContext přes ShellGlobal. Bez grafického backendu nelze hodnotit jeho relevantní paint vfunc. |
| Panel a osm dateMenu tříd | Kanonické typy stále vytváří `GObject.registerClass`; vlastní instance/prototypy/metody zůstávají v backend GJS. UI realmy jsou delegáti. | `shell/buildPanelRealm.py:32–60`; `shell/buildDateMenuRealm.py:64,82–83,131–150,214–221`; sdílený GI registry v `shell/gjsRealm.cpp.inc:67–70`. WeakMaps a disconnect journal řeší scoped UI, nikoli uvolnění kanonického kontextu. |
| InputMethod a WM dialogy | JS GTypes implementují nativní vfunc rozhraní, která může dál volat Mutter/Clutter. | `S:js/misc/inputMethod.js:20–24,197–333`; `S:js/ui/closeDialog.js:14–19,112,142,171`; `S:js/ui/inhibitShortcutsDialog.js:20–25,115,152`. Nestačí schovat UI: starý vfunc vstup musí přestat být dosažitelný nebo mít nativního vlastníka. |
| GJS wrapper / ObjectPrototype / vfunc trampoline | Wrapper asociace v qdata, toggle refs, prototypové vfunc closures a GI metadata. | `G:gi/object.cpp:2194–2199,2337–2360,2413–2423,2586–2611,3866–3884`. Registrace JS vfunc zapisuje trampoline pointer do nativního vtable. Invalidation callback pouze odstraňuje closure z `m_vfuncs` (`3890–3893`); není zde doloženo přepojení vtable na novou JS implementaci. |
| GClosure, GI async callback, GLib zdroj a Promise job | Closure ukládá konkrétní `JSContext*` a callable; některé jsou kořenované/notifikované, jiné traceuje scope object. | `G:gi/closure.cpp:26–50,89–114`; `G:gi/function.cpp:301–316,711–729`; `G:gjs/context.cpp:433–489`. Zrušení kontextu zastavuje jeho job queue a uvolňuje kořeny; nenahrazuje doménový cancel/drain protokol pro živý Shell. |

Závěr mapy: **nativní životnost a kontextová životnost jsou dvě různé osy**.
Čistý nativní leaf s hostitelským vlastníkem je možný. Nativní serverový graf
s připojenými JS callbacky není po výměně kontextu automaticky použitelný.
Tabulka je audit relevantních zdrojových hranic, nikoli kompletní snapshot
všech objektů aktivní relace nebo tvrzení o úplném pokrytí každého modulu.

## 4. Nejvýše tři kandidáti

| Kandidát | Rozhodnutí pro první experiment | Důvod |
| --- | --- | --- |
| **1. Samostatný `St.Adjustment`** | **Doporučený jediný kandidát — GO** | Skutečná třída v dodané `libst-18.so`, existující GIR, stav a synchronní native property vfuncy, `notify::value`/`changed`, nullable actor. Lze oddělit od scene graphu a dokázat zachování instance/stavu. |
| 2. `Shell.BlurEffect` | NO-GO pro první experiment | Důkaz pouhých property změn by obešel podstatný paint vfunc; jeho provedení potřebuje ShellGlobal/stage/Cogl graf a synchronizaci renderingu. To není nejmenší izolovaný důkaz. |
| 3. `Shell.WM` | NO-GO pro první experiment | Dává přímou hranici Mutter→Shell, ale vyžaduje správné dokončení operací, synchronní návraty, dialogy a fallback během absence JS. Bez tohoto kontraktu může pozdržet nebo zablokovat správu skutečných oken. |

`St` je skutečný toolkit v repozitáři a balíčku GNOME Shellu, nikoli namespace
`Shell.*`. GO tedy znamená test reálné knihovní implementace Shellu v odděleném
procesu. Neznamená test na existující instanci živého Shellu ani svolení
spustit reset jeho kontextu.

### Proč právě oddělený St.Adjustment

`st_adjustment_new` výslovně anotuje actor jako `(nullable)`
(`S:src/st/st-adjustment.c:451–482`). `set_actor` používá pouze weak ref,
žádnou silnou vazbu (`215–231`). `set_value` synchronně aktualizuje stav
a vyvolává notify (`510–532`); změna upper vede přes native property dispatch
na `changed` (`297–333,668–681`). Typ je přímo používán skutečným
`StScrollView` (`1015–1026`), takže nejde o vymyšlenou testovací náhradu.

Má ale dvě záměrně nezahrnuté vrstvy: transition closures drží adjustment,
transition a stopped handler (`st-adjustment.c:92–96,953–1004,1073–1084`),
a `js/ui/environment.js:348–363` přidává JS `ease`/`easeAsync`. Experiment
nesmí importovat tento UI environment ani spouštět transitions. Výsledkem
nebude důkaz přenosu animačního životního cyklu nebo JS overridu vfuncu.

**Hypotéza H1, dosud nespouštěná:** konstrukce a základní property operace
nad actor-less adjustmentem projdou bez inicializovaného Clutter backendu.
Kódové cesty tomu odpovídají; samotné načtení GI metadata H1 neprokazuje.
Pokud první kontrola H1 selže, experiment má skončit s konkrétní chybou.
Nesmí se potichu rozšířit na start celého Shellu nebo připojit hostitelský
display, aby se dosáhlo zeleného výsledku.

## 5. ABI, GIR, reference, teardown a závody

**GJS ABI.** Fáze 28 exportuje pouze soukromé
`gjs_context_tgnome_native_object` (`shell/gjsNativeType.cpp.inc:5–28`).
Používá interní `GjsContextPrivate`, `AutoMainRealm` a GI value konverze.
Není to stabilní veřejný embedding ABI ani součást GIR. Pro doporučený test
lze použít tutéž přesně připnutou variantu GJS; není důvod měnit GJS vfunc
implementaci, přidávat obecný rebinding JS GTypes nebo měnit veřejné ABI St.
Každá jiná verze GJS/SpiderMonkey by vyžadovala nové ověření.

**Dvě GJS varianty v jednom procesu.** `readelf -d` potvrzuje, že `libst-18.so`
nemá přímé `DT_NEEDED` na libgjs, zatímco `libshell-18.so` jej má. St má
závislosti na libmutter/Clutter/Cogl. Není tedy správné přidat Shell GIR
z `realmShell` do probe s `nativeTypeGjs` a předpokládat identitu GJS jen kvůli
stejnému SONAME `libgjs.so.0`. Pro malý test se má použít pouze St/Clutter/Meta
metadata; načtené knihovny je nutné ověřit uvnitř izolovaného procesu.
Přímá absence libgjs v `DT_NEEDED` není důkaz, že ji žádná budoucí transitivní
nebo dynamická cesta nenačte. H2: jediná zvolená libgjs v novém probe — neověřeno.

**GIR a balení.** `S:src/st/meson.build:194–214,233–245` sestavuje samostatnou
shared library a namespace `St`, version `18`, s Clutter/Meta závislostmi.
`gi-inspect-typelib St --typelib-version=18 --print-shlibs --print-typelibs`
po doplnění cest z existujícího binárního wrapperu skončil exit 0. Metadata
ukazují přesně na výše uvedenou `libst-18.so`; načtené typelib závislosti jsou:

```text
GL-1.0, xlib-2.0, HarfBuzz-0.0, xfixes-4.0, GModule-2.0,
GObject-2.0, Clutter-18, GDesktopEnums-3.0, Mtk-18, freetype2-2.0,
GLib-2.0, cairo-1.0, Atk-1.0, Gio-2.0, Meta-18, Cogl-18,
Graphene-1.0, Pango-1.0, GdkPixbuf-2.0
```

Pouze St a Mutter adresář nestačily: konkrétní chyba byla chybějící
`xlib-2.0.typelib`. Existující wrapper poskytuje i
`/nix/store/a1kncrkc0j17h8qfnayxhhax0jdqm8vz-gobject-introspection-1.86.0/lib/girepository-1.0`.
Tato závislost je vyřešitelná deklarací testovacího prostředí, bez instalace
desktopu. Správný GI flag je `--typelib-version`, starý `--version=18` byl
odmítnut parserem. Metadata inspekce nespustila GJS ani neinstanciovala St.

**Reference.** C++ host musí vlastnit skutečný objekt před prvním kontextem
a až do posledního ověření. GValue má dočasný ref a musí být unset; getter
helperu vrací novou referenci přes `g_value_dup_object`, kterou musí volající
vyvážit. JS wrapper a jeho prototyp nesmějí být uloženy v trvalém nativním
payloadu. Actor-less adjustment není floating actor a nevyžaduje přenos do
scene graphu. Nesmí se na něm během přechodu volat `g_object_run_dispose`.

**Callbacky a teardown.** Každý JS handler musí mít zaznamenané ID a být
odpojen před context unref; trvalý čistě C callback nesmí obsahovat ukazatel
na starý JSContext. `G:gi/object.cpp:2586–2611` ruší asociaci wrapperu,
invaliduje jeho closures a uvolňuje native ref; nenahrazuje přepojení
libovolného externího callback payloadu. Starý JS delegát ani staré pole
handlerů se nesmí přenést jako součást „stabilní“ hranice.

**Reentrance a závody.** `S:src/main.c:653–665` výslovně upozorňuje, že
konstrukce GjsContext iteruje defaultní main loop; proto se při bootu Shellu
dělá před Meta setupem. Za provozu již běžícího Mutteru může taková iterace
doručit událost ve fázi rozpojení. Přesun loopu do C tento závod neodstraňuje.
Pro samostatný adjustment test se žádný compositor, actor, async operace ani
timeline nespouští a vše běží na jediném vlastnickém vlákně. Pro celý Shell
chybí nativní bariéra vstupů, vypořádání in-flight operací i bezpečné fallbacky.

## 6. Nejmenší navržený experiment a akceptační kritéria

Následuje specifikace doporučeného experimentu, nikoli jeho implementace
nebo popis již dosaženého výsledku.

Host použije skutečný export `st_adjustment_new(NULL, 5, 0, 100, 1, 10, 0)`
z auditované knihovny. Vytvoří ho **jednou před prvním GjsContext**, drží
silnou C referenci, native weak-notify a vlastní nativní identifikační token
v qdata. Žádná kopie `st-adjustment.c`, nový náhradní GType ani JS podtřída.
Tři kontexty pak postupně importují St-18 a obalí tutéž instanci přes ABI
fáze 28. Po každém teardownu následuje nativní property operace bez JS.

| Gate | Přesná podmínka PASS |
| --- | --- |
| A — původ a izolace | H1 projde bez ShellGlobal, backend setupu, display a D-Bus relace; objekt pochází z auditované `libst-18.so`. Proces má jedinou zvolenou variantu libgjs a odpovídající API-18 knihovny. Chybějící typelib nebo backend požadavek se hlásí, neobchází aktivní relací. |
| B — nativní identita | Jediné vytvoření objektu; stejný `GObject*`, přesný `ST_TYPE_ADJUSTMENT`, stejný qdata token a stejné native class/interface vfunc adresy před/po všech kontextech. Žádný nativní dispose/weak-notify před závěrečným uvolněním. Pouhá shoda GType nebo nově sestaveného JS stavu nevyhovuje. |
| C — skutečný vfunc provoz | V každém kontextu použít GI property zápis `value=10*N`, čtení z JS i C; změnu `upper=100+N` ověřit přes native `set_property` → `dispatch_properties_changed`. GDB/tracing konkrétních C funkcí nebo jednoznačné native instrumentation musí potvrdit tyto vfunc vstupy také v druhém a třetím kontextu. Nepřepisovat vtable JS funkcí. `ClutterAnimatable.get_actor` může potvrdit native interface dispatch a vrátit NULL; sám tento bezstavový výsledek nestačí. |
| D — callbacky nového kontextu | Nové JS handlery `notify::value` a `changed` ověří generaci. Pro připojené handlery: JS změna value vyvolá právě jeden value callback, změna upper právě jeden changed callback; native změna value na `10*N+1` druhý value callback v témže novém kontextu. Žádný callback ze starší generace. |
| E — životnost kontextu a JS | Po odpojení obou JS handler IDs a návratu všech JS/C stack frame uvolnit kontext; před vytvořením dalšího musí proběhnout jeho GObject weak-notify a musí být null slabé odkazy na starý globál, marker, wrapper a oba callable objekty. Zkontrolovat dokončený teardown, nikoli jen nižší heap nebo novou adresu. Weak-notify nezaměňovat za samostatnou instrumentaci `finalize`. |
| F — mezera bez JS | Přesná JS handler IDs nejsou připojena. Host nastaví value na `40+N` a ověří native čtení i trvalý čistě C callback. Následující kontext tento stav přečte před jakýmkoli vlastním zápisem. U čistě native property není během mezery potřeba BUSY; není to JS delegovaný FileEnumerator z fáze 28. |
| G — negativní kontroly | Lifetime gate musí odmítnout záměrně ponechanou referenci na starý GjsContext, ještě před vytvořením dalšího. Existující nezměněná JS-GType kontrola fáze 28 zůstane oddělená a její pád se nesmí přičítat pozitivnímu St případu. Výsledky mají zvlášť uvést, které kontroly byly spuštěny a které pouze převzaty z uložené evidence. |
| H — ukončení a paměť | Po třetím kontextu a poslední gap kontrole uvolnit hostitelský ref: native weak-notify právě jednou. Pozitivní běh exit 0, bez nečekaných GLib/GJS varování a bez timeoutu. Valgrind nad stejnými vykonanými cestami bez invalid read/write/free; uvést přesné flags a nepovažovat vypnutý leak/undefined-value check za důkaz jejich čistoty. |

V každé generaci musí log obsahovat identitu, nativní stav před/po, počty
handler volání, zánik kontextu a weak výsledky; jinak nelze odlišit výměnu
runtime od dalšího UI realmu. Prostředí a supervisor mohou navázat na fázi 28:
samostatné procesní skupiny, soukromý HOME/XDG, absentní bus sockety,
vypnuté core dumpy, 20s deadline pro běžný proces a 60s pro Valgrind.

Tento PASS by doložil **opakované použití reálného native typu GNOME Shellu
po výměně celého GJS kontextu v samostatném embeddingu**. Nedoložil by
zachování ShellGlobal, grafického scene graphu ani Wayland spojení při
výměně kontextu běžícího Shellu. Pro takové tvrzení by byly nutné nové důkazy
z izolovaného compositoru; tento audit je nenahrazuje ani nepovoluje zásah
do aktivního desktopu.

## 7. Rizika a nevyřešené závislosti

| Riziko / závislost | Stav a důsledek |
| --- | --- |
| H1: actor-less St bez Clutter backendu | Zdrojově odůvodněno, runtime neověřeno. První stop gate; důvod pro malý experiment, nikoli pro deklaraci hotového přenosu. |
| H2: jednotná GJS a GI closure knihovna | ELF a metadata přečteny, konkrétní budoucí proces neexistuje. Nutná kontrola načtených map; `realmShell` a `nativeTypeGjs` nejsou jedna sestavená větev. |
| Explicitní dispose vlastníkem | Prokázaná konkrétní cesta ScrollView → adjustment. Doporučení ji obchází oddělenou instancí; přenos vlastnictví skutečného scroll UI není vyřešen. |
| JS registrované GTypes a interfaces | Fáze 28 je přímo negativní důkaz. Native base class ani nové UI realmy nepřepíšou starý vfunc trampoline. Týká se i input/dialog rozhraní, nejen viditelných aktorů. |
| ShellGlobal cyklus a další konzumenti jeho kontextu | `_destroy_gjs_context` pouze clearne člen; existují i profiler/getter/eval vazby (`S:src/main.c:264–267,290–291,693–696`). Úplný provozní handoff neověřen. |
| WM completion, keybinding a input během mezery | Nativní fallback, queue/drain a ochrana proti dvojímu completion chybějí jako doložený kontrakt; NO-GO pro první živý WM experiment. |
| Reentrance při konstrukci GJS a event/render vstupy | Boot kód problém výslovně zná. Pro živý Mutter neověřena quiescence; potenciální závod bez ohledu na zachování PID. |
| Transitions, async GI, Promise jobs, sources | Zvolený leaf test je nevytváří; jejich obecná přenositelnost ani cancellation pokrytí nejsou prokázány. |
| Nativní knihovna vs. skutečná grafická relace | Výsledek nad St nesmí být interpretován jako whole-Shell restart. Wayland server/resource graph musí zůstat zachován samostatně. |

## 8. Ověřitelnost auditu a zachování workspace

Audit provedl čtení archivů, `readelf`, parsing uložených JSON a inspekci
typelib metadata. **Žádný nový runtime test, kompilace, restart nebo aktivace.**
Původní důkaz fáze 28 má SHA-256
`5a04c95017f2d84a0fac92b433120129c0019ef32fe5555324efbe75a9a0889d`.
Jeho historický Valgrind používal `--leak-check=no --undef-value-errors=no`;
audit jej nepřekládá na obecný důkaz bezchybnosti nebo nepřítomnosti leaků.

Před vytvořením tohoto dokumentu byl spočten manifest 2561 existujících
souborů/symlinků workspace, bez `.git` a tohoto reportu. Jeho SHA-256 byl
`18c8175a49dc351d0e3d14320fea6fe4442797bc431a01b9fdabc27e56884d39`.
Stejný výpočet po zápisu dokumentu má ověřit, že implementace, reproduktory,
derivace i dřívější artefakty zůstaly zachované. Report je jediný zamýšlený
nový soubor; `PLAN.md` ani jiné reporty se nemění.

Vybrané příkazy pro nezávislou reprodukci pouze read-only části:

```sh
tar -xOf /nix/store/spl25qj4dh6z96rv3jhkmqhya2610rrl-gnome-shell-50.5.tar.xz \
  gnome-shell-50.5/src/st/st-adjustment.c | nl -ba
tar -xOf /nix/store/spl25qj4dh6z96rv3jhkmqhya2610rrl-gnome-shell-50.5.tar.xz \
  gnome-shell-50.5/src/st/st-scroll-view.c | nl -ba
tar -xOf /nix/store/c5il8xcpwhinm6jzzpp4xl3bz7z71vnz-gjs-1.88.1.tar.xz \
  gjs-1.88.1/gi/object.cpp | nl -ba
readelf -d /nix/store/3c91y87dbgav2rp43xk1rn8gcq2vh4jv-gnome-shell-50.5/lib/gnome-shell/libst-18.so
readelf --dyn-syms --wide /nix/store/3c91y87dbgav2rp43xk1rn8gcq2vh4jv-gnome-shell-50.5/lib/gnome-shell/libst-18.so
```

Pro metadata kontrolu je nutný úplný `GI_TYPELIB_PATH`. Níže uvedený Python
čte adresáře z existujícího **binárního** Nix wrapperu; nespouští Shell:

```python
from pathlib import Path
import os, re, subprocess

pkg = Path('/nix/store/3c91y87dbgav2rp43xk1rn8gcq2vh4jv-gnome-shell-50.5')
raw = (pkg / 'bin/gnome-shell').read_bytes()
paths = [p for chunk in re.findall(rb'/nix/store/[A-Za-z0-9_+./:-]+', raw)
         for p in chunk.decode().split(':')]
dirs = list(dict.fromkeys(p for p in paths
                         if Path(p).is_dir() and any(Path(p).glob('*.typelib'))))
dirs += [str(pkg / 'lib/gnome-shell'),
         '/nix/store/qr8g2wi8xf4rmx6amf15qhlwyf85khph-mutter-50.5/lib/mutter-18']
env = dict(os.environ, GI_TYPELIB_PATH=':'.join(dirs))
subprocess.run(['gi-inspect-typelib', 'St', '--typelib-version=18',
                '--print-shlibs', '--print-typelibs'], env=env, check=True)
```

Rozhodnutí zůstává úzce vymezené: **GO pro native St.Adjustment leaf
experiment; NO-GO pro runtime výměnu kontextu skutečné Shell relace.** Přínos
auditu spočívá v konkrétním existujícím typu, ověřených exportech/GI závislostech,
identifikovaném parent-dispose problému a testovatelných gates, nikoli
v dalším tvrzení o úspěšném restartu.
