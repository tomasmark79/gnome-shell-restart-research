> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Datumové menu: osm UI tříd v novém realmu

21. října 2026: **SHELL RELOAD v rozšířeném testovaném rozsahu**.
Implementace osmi tříd z `dateMenu.js` nyní běží ve společném novém UI realmu.
Prošla původní konstrukce přes JS rodičovskou třídu, nativní vfunc, typované
signály, skutečné vykreslení i úklid vadného kandidáta. Celý GJS kontext,
kanonické GType, Main a proces zůstávají původní. Úplný restart Shellu tím
implementovaný není; celek zůstává **RESEARCH PROTOTYPE**.

## Implementovaná hranice

[shell/buildDateMenuRealm.py](shell/buildDateMenuRealm.py) z připnutého
GNOME Shellu 50.5 při sestavení vytvoří nové implementační prototypy pro:
TodayButton, EventsSection, WorldClocksSection, WeatherSection,
MessagesIndicator, FreezableBinLayout, CalendarColumnLayout a DateMenuButton.
Původní těla metod včetně `super` zůstávají zachovaná. GType se registrují
jednou v trvalém backendu; další generace znovu vytváří pouze UI implementaci.

Kanonické `_init` nejprve přiřadí JS wrapperu scope pomocí backendového WeakMap.
Před původním `super._init()` nečte ani nezapisuje nativní vlastnosti ještě
neinicializovaného GObject. Originální UI implementace pak provede původní
konstrukci. Vnořené widgety dostanou stejný scope přes explicitní továrnu
a ohraničený konstrukční zásobník s `finally` úklidem.

DateMenuButton správně zůstává nativním potomkem
`Gjs_ui_panelMenu_PanelMenuButton`; jeho typ je
`Gjs_ui_dateMenu_DateMenuButton`. Rodičovská implementace PanelMenu, Calendar,
Weather, formátovací služby a ClocksProxy stále patří trvalému backendu.
Date používá kanonický backendový konstruktor, aby předávaná data nepřinesla
cizí nativní prototyp do trvalých skriptů. Nejde o nový celý UI module graf.

Scope eviduje vlastní odběry událostí mimo vlastněné Clutter herce.
Při zániku root widgetu je odpojí a zakáže další konstrukci v tomto scopu.
Po dokončení rekurzivního nativního destroy uvolní odkazy na všech osm objektů.
Tento krátký idle cleanup je vlastněný backendem, takže jej úklid právě
rušené UI generace nezruší. FinalizationRegistry samostatně sleduje global,
implementaci a každý z osmi JS wrapperů. Záznamy neobsahují sledované objekty.

## Konkrétní nalezené chyby

- **WorldClocks zadržoval starý realm přes systém aplikací.** Heap ukázal
  nativní emitter → bound callback → starý widget → jeho `_locations` pole
  a UI global. Nový komponentový journal odpojí také tento odběr; samotný
  destroy panelu nestačil. Důkaz: [původní běh](evidence/reports/date-realm-rendered/result.json)
  a heap (not exported: `artifacts/date-realm-rendered/date-menu-generation-1.heap`).
- **Prázdný nativní registr neumožnil převést typovaný argument signálu.**
  `gi/repo.cpp:lookup_namespace()` hledá GI podle aktuálního globalu callbacku.
  Původní nový global měl prázdný native registry, přestože ES import používal
  kanonické GI bindingy. Signál s `GLib.DateTime` hlásil
  `No gi property in native registry`. Nové realmy nyní sdílí nativní registr
  backendu. Registry ES modulů a source map zůstávají oddělené.
- **Trvalý GIO skript držel cizí prototyp parametrů.** Po vložené chybě se
  všechny widgetové wrappery uvolnily, ale jeden realm zůstal. Heap vedl do
  `Gio.Settings._init` a jeho `cacheir-object` odkazu na prototyp UI objektu.
  Kód GJS používá mimo jiné `prop in props`. Parametry Settings se nyní
  kopírují do obyčejného backendového objektu. Důkaz:
  [běh](evidence/reports/date-realm-panel-failure-heap/result.json) a
  heap (not exported: `artifacts/date-realm-panel-failure-heap/date-menu-generation-2.heap`).

Při vývoji se také opravilo chybné jméno namespace ve stavovém endpointu
a doplnily původní globální překladové funkce `N_` a `C_`. Původní okamžité
otevření/zavření menu neprokazovalo alokaci; nový test nechá menu vykreslit,
pořídí screenshot a kontroluje skutečná vfunc volání.

## Silnější testy skutečného chování

Nový soukromý endpoint otevře datumové menu, přepne kalendář na zítřek
a vyšle nativní `clicked` signál tlačítka „Dnes“. Ověří návrat na dnešek,
provedení UI `vfunc_clicked` a doručení obou typovaných
`selected-date-changed` událostí do EventsSection. Pouhé přežití procesu
nebo změna interního data kalendáře tento test nesplní.

Samostatný GJS probe nyní také přenáší `GLib.DateTime` jako boxed argument
nativního signálu do každého nového realmu. S prázdným registrem všechny čtyři
režimy selhaly, po opravě všechny prošly, včetně původních GC kontrol:
negativní důkaz (not exported: `artifacts/typed-boxed-negative/result.json`),
[opravený důkaz](evidence/reports/typed-boxed-verified/result.json).

## Finální výsledky

| Běh | Prokázaný výsledek |
| --- | --- |
| [Běžná obnova a soak](evidence/reports/date-menu-realms-verified/result.json) | 10 výměn panelu, rollback po chybě při adopci, 3 obnovy celého UI, 65,0076 s sledování. Sebrány 3 staré datumové realmy a všech 24 sledovaných JS wrapperů. |
| [Vadný kandidát](evidence/reports/date-menu-realms-failure-verified/result.json) | Chyba po konstrukci panelu při druhém požadavku, jeden opravný pokus, celkem 3 úspěšné UI commity. Sebrány všechny 4 staré datumové realmy a 32 wrapperů včetně vadného kandidáta. |

Oba příkazy skončily exit 0; `passed=true`, `workerExitCode=0`,
`privateProfileRemoved=true`, diagnostické problémy 0. V běžném průchodu bylo
také sebráno 14 starých panelových realmů; v chybovém 15. Živá aktuální
generace v obou případech zůstala nesebranou kontrolou. Všech 12/11 vlastních
odběrů každého starého datumového scopu bylo odpojeno bez chyby.

GC dokazuje zánik sledovaných JS wrapperů a realmů. Nenahrazuje měření
finalizace všech nativních GObject, GPU prostředků nebo celého procesu.
Vložená chyba nastává po dokončení konstrukce panelu, nikoli uprostřed
libovolného `super._init` nebo nativního volání.

Soak běh zachoval Shell PID **3161700**, původní XWayland a tyto klienty:

| Klient | PID | fd / inode | windowId | Tick před → po |
| --- | --- | --- | --- | --- |
| Wayland | 3162114 | 3 / 8533637 | 10 | 3 → 430 |
| X11 přes XWayland | 3162335 | 3 / 8548524 | 2097156 | 1 → 427 |

Hashe neuloženého textu zůstaly stejné; následný nativní virtuální vstup
v obou původních oknech vytvořil očekávaný nový text. Prošly kontroly oken,
workspace, monitorů, backendových modelů, nových klientů a stavu UI registrací.
Při panelové části se počet nativních GType nezměnil: **986 → 986**.
Otevřené menu po třetí obnově je vidět na
snímku (not exported: `artifacts/date-menu-realms-verified/date-menu-generation-3.png`).

Testovaný Shell:
`/nix/store/3c91y87dbgav2rp43xk1rn8gcq2vh4jv-gnome-shell-50.5`.
GJS: `/nix/store/dbpxvaa4b1c1lknwicgsvcssqavia6jp-tgnome-realm-gjs-1.88.1`.
GJS prošlo 77 nakonfigurovanými upstream testy, 0 selhání; GTK4 testy zůstávají
vypnuté podle připnutého balíčku. Použito `--cores 0`, ověřeno `-j16`.
Finální `nix flake check --cores 0 -L` prošlo.

## Reprodukce a změny

```sh
nix build --cores 0 -L .#realm-shell --out-link result-realm-shell
nix build --cores 0 -L .#realm-probe --out-link result-realm-probe
nix develop .#realm --cores 0 -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --track-time --soak-seconds 65 \
  --output artifacts/date-menu-local
nix develop .#realm --cores 0 -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --track-time \
  --ui-failure once --ui-failure-stage after-panel \
  --output artifacts/date-menu-failure-local
nix flake check --cores 0 -L
```

Přibyl `shell/buildDateMenuRealm.py`. Změny jsou dále v `flake.nix`,
`shell/gjsRealm.cpp.inc`, `shell/buildPanelRealm.py`, `extension/extension.js`,
`tests/isolated.py`, `tests/realm-probe.cpp`, `tests/realm-modules/entry.js`,
`tests/realm-supervisor.py`, důkazech a dokumentaci.
Testy používají soukromý bus a profily, mock logind a headless rendering.
Hostitelský Shell zůstal PID 1350942 s původním executable. NixOS se
neaktivoval. Odstranění result odkazů odstraní jen lokální GC rooty;
systémový rollback není potřeba.

## Další hranice k původnímu cíli

Jsou prokázané skutečné třídy, JS dědičnost, typované callbacky a úklid dvou
komponent. Kanonické GType ale stále vlastní JS funkce v původním GJS kontextu.
Jeho zahození zatím není bezpečné. Další rozhodující krok má ověřit nativní
GType/vfunc bridge bez vlastnictví původním JS kontextem a zachování stejného
nativního objektu při skutečné výměně kontextu. To je další experiment,
nikoli již dosažená vlastnost.

Celý UI module graf, libovolná přerušená konstrukce, nativní deadlock/pád,
rozšíření a bezpečnost nové varianty při zamykání stále nejsou pokryté.
Fyzická relace nebyla nahrazena; starší VM testy novou variantu neověřují.
