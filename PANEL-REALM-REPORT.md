> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Skutečný panel GNOME Shellu v nových UI realmech

Navazující [DATE-MENU-REALM-REPORT.md](DATE-MENU-REALM-REPORT.md) rozšiřuje
hranici na osm tříd datumového menu a JS rodičovskou konstrukci. Přidává
typované GI signály, vlastní journal odběrů a GC jednotlivých wrapperů.

21. října 2026: **SHELL RELOAD panelu s výměnou jeho implementačního globalu**.
Celkově jde stále o **RESEARCH PROTOTYPE** restartovatelného Shellu.
Úplný restart Shellu, JSContextu ani procesu není implementovaný.

Nová varianta `realm-shell` přenesla metody skutečného panelu do nového GJS
globalu. Kanonický GType panelu a jeho nativní vfunc trampolíny zůstávají
v původním globalu. Původní Mutter, Wayland server a klientská spojení přežila
deset výměn panelu, vloženou chybu a následné tři rekonstrukce desktopového UI.
Všech čtrnáct odpojených realmů panelu se v rozšířeném testu uvolnilo z paměti.

## Jak se změnila skutečná komponenta

[shell/buildPanelRealm.py](shell/buildPanelRealm.py) při sestavení zpracuje
připnutý Panel z GNOME Shellu 50.5 po aplikaci dosavadních lifecycle oprav.
Původní těla metod přesune do samostatného resource ES modulu
`ui/tgnomePanelRealm.js`. Tento modul neregistruje další GType. Zachovává
chování panelu, včetně rozložení, menu, gest a vazeb na session mode.

Trvalá třída `Panel` dál dědí z `St.Widget`. Konstruktor vytvoří nový realm
a předá mu explicitní backendové bindingy: kanonické GI typy, Main namespace,
menu/focus služby a konstruktory zachovaných indikátorů. Vfunc, ostatní metody
a `boxOpacity` předávají volání do nové implementace. Po nativním signálu
`destroy` panel odpojí odkaz na implementaci. Záznamy GC obsahují pouze
primitivní hodnoty; finalizéry samostatně sledují global a implementační objekt.

[shell/panelRealmGlobal.c.inc](shell/panelRealmGlobal.c.inc) povoluje instalaci
soukromého JS loaderu pouze v headless backendu s `TGNOME_ALLOW_UI_REALMS=1`.
GJS helper přijímá pouze pevně určený lokální resource modul panelu. Má vlastní
registry modulů, ale sdílí kanonické nativní bindingy backendu. Stejný JSContext
a stejný SpiderMonkey runtime zůstávají živé; realm není bezpečnostní izolace.

Tato hranice nezahrnuje implementace ActivitiesButton, DateMenu, QuickSettings,
jejich další widgety ani Main. Tyto moduly a jejich GType zůstávají původní.
Výměna celého UI runtime bude vyžadovat převést i jejich vlastnictví a dědičnost.

## Opravené skutečné zadržování realmů

Původní třígenerační [samostatný experiment](REALM-REPORT.md) tuto chybu
neodhalil. Delší běh skutečného panelu ji prokázal:

1. Volání `foreignMethod.apply(...)` a `foreignMethod.call(...)` použila
   nativní funkce z nového realmu. Heap ukázal trvalé skripty s `cacheir-object`
   odkazy na objekty tohoto realmu. Forwardery nyní používají kanonické
   backendové `Reflect.apply`.
2. Zůstávaly další realmy. Heap ukázal silnou cestu z interního GJS loaderu,
   jeho `moduleLoadHook` skriptu a JIT cache přes cizí `Map.prototype` do UI
   globalu. Nové registry jsou proto samostatné Map instance vytvořené
   v trvalém interním realmu. Jejich obsah je stále oddělený pro každé UI.

Analýza odlišovala `cacheir-weak-*` hrany od silných hran; samotná cesta
přes slabou cache se nepovažovala za důkaz vlastnictví. Prodloužení kontroly
z šesti na třicet GC průchodů chybu nevyřešilo. Po opravách se všech jedenáct
odpojených panelových realmů uvolnilo už při prvním průchodu.

Zachované negativní běhy a heap důkazy:
[původní retainery](evidence/reports/panel-realm-retainers/result.json),
heap (not exported: `artifacts/panel-realm-retainers/panel-realms.heap`),
[po opravě forwarderů](evidence/reports/panel-realm-reflect/result.json),
druhý heap (not exported: `artifacts/panel-realm-reflect/panel-realms.heap`).
Následný běh s kanonickými Map registry prošel GC, ale odmítl první načtení
`ClutterShaderEffect` a `StScrollViewFade` jako nové typy. Finální test otevírá
menu již před výchozím měřením; nejde o opakované generování JS GType.

## Finální ověření

| Běh | Výsledek |
| --- | --- |
| [Panel](evidence/reports/panel-realm-verified/result.json) | 10 výměn, obnova po chybě při adopci, 12 vytvořených realmů, 11 odpojených a sebraných; 1 živý kontrolní realm. Počet nativních typů 985 → 985. |
| [Celé UI a soak](evidence/reports/panel-realm-ui-reload/result.json) | Totéž, poté 3 desktopové rekonstrukce. Nakonec 15 realmů, 14 odpojených a sebraných, 1 živý. Soak 65,0065 s. |

Oba vnější příkazy skončily exit 0. Reporty mají `passed=true`,
`supervisor.workerExitCode=0` a `privateProfileRemoved=true`.
Po každé výměně test ověřil skutečná volání alokační a preferred-width vfunc,
funkční menu, počet panelových kontejnerů a focus skupin i zachování indikátorů.
Vadný kandidát byl zničen, jeho realm se uvolnil a původní panel se obnovil.

Rozšířený běh zachoval Shell PID **3040837** a původní XWayland identitu.
Jeho klienti zachovali PID, fd, inode a původní okna:

| Klient | PID | fd / inode | windowId | Tick před → po soaku |
| --- | --- | --- | --- | --- |
| Wayland | 3041153 | 3 / 8342653 | 10 | 3 → 428 |
| X11 přes XWayland | 3041178 | 3 / 8340604 | 2097156 | 1 → 425 |

Hashe neuloženého textu zůstaly stejné. Následný nativní virtuální vstup změnil
text na očekávané hodnoty v obou původních oknech. Test zachoval identity
backendových modelů, GJS epoch, monitory, workspace a relevantní desktopový
stav. Uložil snímky desktopu/overview a ověřil také pozdější nové klienty.
GJS kontexty se nefinalizovaly. Pozdější nárůst na 989 nativních typů patří
virtuálnímu vstupu, pixel bufferu a GVfs warmupu, nikoli novým GType panelu.

Testovaný Shell:
`/nix/store/92lji79rnnwy3m40pg0zkzw42i8p69ch-gnome-shell-50.5`.
Použité GJS:
`/nix/store/4cdrdq2cxdd5p5lnn39jmlpg93r5qda3-tgnome-realm-gjs-1.88.1`.
GJS prošlo 77 nakonfigurovanými upstream testy, 0 selhání; GTK4 testy jsou
v připnuté konfiguraci vypnuté. Kompilace používá `--cores 0`, ověřeno `-j16`.
Finální `nix flake check --cores 0 -L` prošlo včetně čtyř samostatných realm
kontrol a dosavadních automatických kontrol projektu.

## Reprodukce a soubory

```sh
nix build --cores 0 -L .#realm-shell --out-link result-realm-shell
nix build --cores 0 -L .#realm-probe --out-link result-realm-probe
nix develop .#realm --cores 0 -c python3 tests/isolated.py \
  --output artifacts/panel-realm-local
nix develop .#realm --cores 0 -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --track-time --soak-seconds 65 \
  --output artifacts/panel-realm-ui-local
nix flake check --cores 0 -L
```

Nové soubory: `shell/buildPanelRealm.py`, `shell/panelRealmGlobal.c.inc`
a tento report. Upravené: `shell/gjsRealm.cpp.inc`, `flake.nix`,
`extension/extension.js`, `tests/isolated.py` a stavová dokumentace.
Balíček `interruption-shell` zůstal původní
`/nix/store/mbkhf29wdjn3l5hxqnzph2rmnpj3h3h0-gnome-shell-50.5`.
Refaktor Nix výrazu umožňuje stejnou variantu sestavit s vybraným GJS.

Testy používaly vlastní bus, mock logind, headless monitor, softwarové
vykreslování a dočasné profily. Žádná aktivace NixOS ani změna hostitelské
relace neproběhla. Pro odstranění lokálních GC rootů stačí odstranit odkazy
`result-realm-shell` a `result-realm-probe`; systémový rollback není potřeba.

## Co zbývá k hlavnímu cíli

Teď je prokázaná hranice **skutečné komponenty**, nejen syntetického GI objektu.
Další práce musí tuto hranici rozšířit na widgety s JS rodičovskými třídami
a na jejich modely/služby. Je nutné řešit volání `super`, konstrukci GObject,
stabilní metadata typu a odpojení všech callbacků před výměnou jejich realmu.

Stále nejsou prokázané: nový celý UI module graf, výměna JSContextu, restart
procesu, obnova po nativním deadlocku/pádu ani bezpečná obecná výměna za běhu
při rozpracovaném callbacku. VM zámkové testy starších variant neověřují tuto
novou variantu; bezpečnostní a provozní přechody je nutné znovu prověřit po
rozšíření hranice. Fyzická relace nebyla tímto balíčkem nahrazena.
