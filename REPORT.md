> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Výsledek experimentu — 20. října 2026

Aktuální implementace už obsahuje lokálně patchovaný GNOME Shell s obnovou
skutečného panelového kontejneru. Podrobnosti, příkazy a důkazy druhé etapy
jsou v [PANEL-REPORT.md](PANEL-REPORT.md). Jde o **SHELL RELOAD omezený na panel**,
nikoli restart celého Shellu nebo compositoru. Hlavní cíl zůstává otevřený.

Třetí etapa testuje výměnu celého GJS kontextu při zachování nativního Mutteru;
její důkazy a neúspěšné integrační brány jsou v [RUNTIME-REPORT.md](RUNTIME-REPORT.md).

Čtvrtá etapa obnovuje instance desktopového UI ve stejném GJS kontextu a
ponechává vybrané backendové modely. Tři obnovy, původní Wayland/XWayland
spojení, text v testovacích aplikacích, otevření dalších oken a následné
65sekundové pozorování prošly v oddělené headless relaci. Důkazy, opravené
chyby vlastnictví i další audit registrací shrnuje
[STABLE-REPORT.md](STABLE-REPORT.md). Jde o **SHELL RELOAD v testovaném rozsahu**;
bezpečný restart celé živé relace ani úplná obnova po selhání prokázány nejsou.
Kompilace používají všech 16 dostupných vláken (`--cores 0`, ověřeno `-j16`).

Pátá etapa doplnila ověřování zániku starých objektů a opravila konkrétní
reference z pozadí, vstupních obsluh a gest. V konečném průchodu se uvolnilo
všech 24 sledovaných starých objektů UI napříč třemi generacemi. Prošel také
65sekundový test opožděných událostí a úklid soukromého stromu procesů.
Podrobnosti a kontrolní experimenty jsou v
[OWNERSHIP-REPORT.md](OWNERSHIP-REPORT.md). Obnova po selhání celého UI a
ověření bezpečnosti zámku a vstupu zůstávají dalšími kroky.

Šestá etapa (21. října) přidala nejvýš jeden opravný pokus po chybě při obnově
UI. Prošly scénáře s jednou chybou i se dvěma chybami, zastavením automatického
opakování a následným výslovným požadavkem. Původní spojení aplikací přežila;
oba scénáře prošly i 65sekundovým pozorováním. Kontroly také odmítají souběžnou
přípravu a vyčerpaný limit před změnou UI. Přesný rozsah a zbývající mezery
popisuje [RECOVERY-REPORT.md](RECOVERY-REPORT.md); nejde o rollback starých
objektů ani o prokázanou obnovu po libovolné chybě uprostřed konstrukce.

Sedmá etapa ověřila virtuální klávesnici přímo v nativním vstupu soukromého
compositoru: Super/Escape ovládaly overview před obnovou i po ní a původní
Wayland/XWayland okna přijala přesně očekávaný text. Zařízení i původní sockety
zůstaly stejné. Oba chybové scénáře prošly 65sekundovým testem, včetně zániku
40 sledovaných starých objektů UI. Skutečné PNG plochy a overview byly také
vizuálně zkontrolovány. Podrobnosti jsou v [INPUT-REPORT.md](INPUT-REPORT.md);
fyzická zařízení a autentizace zamčené relace tím prokázány nejsou.

Následující text je záznam první etapy před implementací patche panelu.

**RESEARCH PROTOTYPE. Hlavní cíl skutečného restartu GNOME Shellu se zachováním
původních spojení aplikací zatím není splněn.**

Implementace a testy prokazují obnovu malé komponenty UI vlastněné rozšířením
a samostatné načtení tématu. Celý Shell, JavaScriptový kontext ani compositor
se při nich nerestartují. Obnova relace ani opětovné spuštění aplikací nejsou
implementovány. Cíl nesmí být považován za dokončený na základě těchto testů.

## Zjištěné prostředí

| Součást | Zjištěná hodnota |
| --- | --- |
| NixOS | `26.05.20261018.8ce7336` (Yarara) |
| GNOME Shell / Mutter | `50.5` / `50.5` |
| GJS | `1.88.1` |
| XWayland v testu | `24.1.14` |
| Hostitelská relace | Wayland, GNOME; potvrzeno prostředím běžícího Shellu |
| GPU | AMD Phoenix1 `1002:15bf`, ovladač `amdgpu` |
| nixpkgs | `8ce73368d1efd4d657e9064d29b144a52046b4e8` |
| Zdrojový commit Shellu, tag 50.5 | `dd8bec9326c2416e7b65b8bc9db4e62126a4fe8b` |
| Zdrojový commit Mutteru, tag 50.5 | `c28623c8d29c7b61ec744cdfdbec36f5e7faef1c` |

Prázdný pracovní adresář neměl Git ani vlastní flake. Existující systémový flake
v `<redacted-local-system-configuration>` sloužil pouze k přečtení zámku vstupů. Tento proces
agenta neměl nastavený uživatelský D-Bus ani Wayland display. Nebyl připojen
k hostitelskému D-Bus za účelem testovacích změn.

Instalovaný Shell: `/nix/store/8m77m1b9n4z4lv00l7d5455lkfbqy5jg-gnome-shell-50.5`.
Derivace Shellu: `/nix/store/sbw8z8jx1zq6y9yah8z0bvslg218w8qv-gnome-shell-50.5.drv`.
Derivace Mutteru: `/nix/store/81ayhd9pv599f7m5y97fxzkrs4fn90yz-mutter-50.5.drv`.
Mutter nemá v této derivaci dodatečné patche. Shell má Nixpkgs patche pro cesty,
služby, GIR a GDM; dva jejich soubory nebyly při prvním čtení přítomné ve store.
Z toho nevyvozuji úplný audit každého downstream patche. Testovaný binární Shell
pochází ze stejné store cesty jako živý Shell.

Přesné release archivy z derivací byly následně získány přes Nix a analyzovány:

| Archiv | SHA-256 souboru |
| --- | --- |
| `gnome-shell-50.5.tar.xz` | `fc74beea859ec7364b4d706c58f53a240b7ccb00e3f22fc24c1adccd7d135010` |
| `mutter-50.5.tar.xz` | `72fa5a78347b03a6e99a27dbdb5fa5cc3b388b23eea73ce45012818db98b7941` |

## Přesná architektonická překážka

Mutter vlastní instanci `wl_display`, objekty protokolu a klientská spojení
uvnitř procesu Shellu. Při přípravě ukončení volá
`wl_display_destroy_clients()`; při finalizaci zničí samotný `wl_display`.
Dokládá to [Mutter 50.5, meta-wayland.c](https://github.com/GNOME/mutter/blob/50.5/src/wayland/meta-wayland.c#L817),
řádky 817–856; vytvoření serveru je na řádku 874. Ani zachování naslouchacího
socketu by neuchovalo stav existujících `wl_resource`, serialů, surface, bufferů
a probíhajících transakcí. Závěr o nedostatečnosti samotného předání socketu je
architektonický úsudek, nikoli provedený experiment s předáním procesu.

[Shell main.c](https://github.com/GNOME/gnome-shell/blob/50.5/src/main.c#L690)
spouští modul UI v jednom GJS kontextu a po ukončení hlavní smyčky zničí GJS
a následně Mutter. To není rozhraní pro opětovný start UI za běhu.
[main.js](https://github.com/GNOME/gnome-shell/blob/50.5/js/ui/main.js#L198)
inicializuje mnoho vzájemně provázaných singletonů: layout, správu oken, panel,
screen shield, input method, screenshot UI, správce času a D-Bus služby.
Zaregistruje také signály na dlouho žijících objektech. Chybí jeden odpovídající
postup, který by všechny tyto registrace, služby a reference před novou
inicializací úplně odstranil. Opětovné zavolání inicializace by proto nebylo
bezpečným restartem. Samotné zničení GJS neřeší převzetí nativních objektů,
callbacků a zabezpečení zamčené relace novým kontextem.

Pro původní klientská spojení musí přežít proces se serverem a jeho protokolový
stav, Mutter context/display/backend, klientské prostředky, správa oken,
renderovací prostředky a u X11 aplikací také jejich XWayland. Restart celého
procesu by potřeboval zásadně jinou architekturu nebo úplný přenos tohoto stavu;
takové rozhraní nebylo v analyzované 50.5 nalezeno. Samostatný proces UI by navíc
potřeboval nové rozhraní místo přímých odkazů na Clutter/Mutter objekty.

## Posouzení strategií a existující API

- **A — část UI:** upstream již umí načíst téma. Run dialog `rt` volá
  `Main.reloadThemeResource()` a `Main.loadTheme()`; viz
  [runDialog.js](https://github.com/GNOME/gnome-shell/blob/50.5/js/ui/runDialog.js#L50).
  To reinitializuje vzhled, nikoli celý Shell. Implementace tento postup
  zpřístupňuje přes úzce vymezenou D-Bus metodu.
- **Rozšíření:** veřejná metoda `ReloadExtension` výslovně vrací NOT_SUPPORTED;
  viz [shellDBus.js](https://github.com/GNOME/gnome-shell/blob/50.5/js/ui/shellDBus.js#L485).
  Disable/enable může obnovit objekty rozšíření, ale nezaručuje načtení změněného
  ES modulu. [extensionSystem.js](https://github.com/GNOME/gnome-shell/blob/50.5/js/ui/extensionSystem.js#L444)
  zaznamenává již importované moduly a používá dynamický import stejné URI.
- **B — hranice životního cyklu:** realizovaný prototyp ponechává supervisor,
  GJS a Mutter naživu a zavádí explicitní `constructor/destroy` pro vlastní
  indikátor. Ověřuje jednu malou hranici vlastnictví, kterou by větší refaktoring
  potřeboval. Nezavádí separaci procesů ani tuto hranici pro standardní panel,
  overview, window manager nebo celý Shell.
- **C — obnova relace:** zatím neimplementována. Opětovné spuštění aplikací
  neobnoví původní Wayland spojení ani obecně neuložená data. Tento výsledek
  nesmí být zaměněn za splnění požadovaného restartu; požadavek na praktický
  fallback zůstává otevřený stejně jako hlavní cíl.

Historickou diskusi dokládá [upstream issue 1011](https://gitlab.gnome.org/GNOME/gnome-shell/-/issues/1011).
Přímé načtení issue 5634 a Mutter MR 1794 v tomto běhu selhalo HTTP 406;
jejich současný obsah ani stav nebyl ověřen. Závěry výše stojí na zdrojích 50.5,
nikoli na předpokládaném řešení v těchto diskusích. Vývojový postup s Devkitem
potvrzuje [dokumentace Shellu 50.5](https://github.com/GNOME/gnome-shell/blob/50.5/docs/building-and-running.md).
Pro automatický test byl použit podporovaný headless režim z `--help`, protože
agent neměl připojený rodičovský Wayland display.

## Implementace a změněné soubory

Všechny soubory projektu jsou nové:

| Soubor | Účel |
| --- | --- |
| `flake.nix`, `flake.lock` | Připnuté balíky, vývojové prostředí, build a bezpečnostní kontroly |
| `extension/extension.js` | Supervisor, restartovatelný indikátor, D-Bus a jednorázový návrat po chybě |
| `extension/metadata.json` | Rozšíření pouze pro GNOME 50 |
| `tgnome.py` | CLI s přesnými operacemi a odmítnutím nepodporovaných akcí |
| `tests/probe.c` | Skutečná GTK okna s Wayland/X11 backendem a měřením původních spojení |
| `tests/isolated.py` | Izolovaný integrační test, evidence a úklid vlastních procesů |
| `tests/test_safety.py` | Ověření odmítnutí nepodporovaných operací, bus discovery a timeoutu |
| `PLAN.md`, `README.md`, `REPORT.md`, `.gitignore` | Plán, reprodukce, výsledek a ignorované lokální artefakty |

Supervisor vlastní jeden exportovaný D-Bus objekt. Restartovatelná část vlastní
jeden `PanelMenu.Button` s popiskem. Při obnově zničí starý objekt a vytvoří nový.
Při chybě zkusí jednou obnovit poslední generaci; žádný nekonečný retry se
nespouští. Metody přijímají pouze pevně definované operace. Nepoužívají Eval,
nezabíjejí procesy a nemění konfiguraci systému. Bezpečnostní hranicí je
uživatelská session bus; nejde o izolaci nedůvěryhodných aplikací stejného UID.

## Build a testy

Prošly:

```sh
nix build .#default .#extension .#probe --no-link
nix build .#upstream-sources .#shell .#mutter .#probe --no-link
nix flake check
nix develop -c python3 tests/isolated.py --output artifacts/final
```

Byl zkompilován C klient a zabalen CLI i rozšíření. Nemodifikovaný Shell a Mutter
byly realizovány z Nix store/cache; neproběhla kompilace upraveného compositoru.
`nix flake check` spustil tři bezpečnostní unittesty a kontrolu balíku.

Konečná evidence je v [artifacts/final/result.json](evidence/reports/final/result.json)
a sousedních logách. Před ukončením testovacího prostředí bylo naměřeno:

| Objekt | Před / po |
| --- | --- |
| Shell | Stejný PID; `shellBefore.pid == shellAfter.pid` |
| Wayland klient | PID `1632610`, FD `3`, socket inode `5733298`, surface ID `10` beze změny; tick 3 → 15 |
| XWayland klient | PID `1632619`, FD `3`, socket inode `5752862`, XID `2097156` beze změny; tick 1 → 13 |
| XWayland server | PID `1632621`, startTime `13486889` beze změny |
| Vlastněné UI objekty | 26 vytvořeno, 25 zničeno, 1 aktivní po všech lifecycle cyklech |
| Okna a desktop | Shodné stabilní ID oken, frame rect, workspace, focus a monitor 1280×720 |

Wayland klient provádí `wl_display_roundtrip()` na původním nativním display;
X11 klient provádí `XSync()`. Klientský kód neobsahuje reconnect ani opětovné
vytvoření okna. Test tedy kontroluje více než přežití procesu. Celkem provedl
21 úspěšných rekonstrukcí indikátoru, jednu vloženou chybu s návratem,
jedno načtení tématu, tři disable/enable cykly rozšíření a odmítnutí všech tří
nepodporovaných CLI operací. Po úklidu už žádný ze čtyř sledovaných testovacích
procesů neexistoval; původní hostitelský Shell PID `1350942` nadále existoval.

Průběžné neúspěchy a omezení testů:

- První test kontroloval pouze Wayland, protože detekční výraz neodpovídal
  hlášení `Using public X11 display`. Byl opraven a XWayland je nyní povinný.
- Rozšířený test v `artifacts/validated` selhal kvůli chybné cestě objektu API
  rozšíření. Podle zdrojů byla opravena na `/org/gnome/Shell`; konečný test prošel.
- Dvě první diagnostiky derivací předpokládaly staré schéma JSON Nixu.
  Po přečtení skutečného schématu se přešlo na `derivations` a `inputs.drvs`.
- Vložená konstrukční chyba vyvolává očekávanou D-Bus výjimku v logu Shellu.
  Test ji explicitně očekává a ověřuje funkční návrat.
- Log izolovaného desktopu obsahuje chybějící session-manager služby a hlášení
  související s neúplnou headless relací. Není to plnohodnotná přihlášená relace.
- Nastaveno `LIBGL_ALWAYS_SOFTWARE=1`, ale Mutter otevřel render node amdgpu
  bez modesettingu. Čistě CPU rendering nebyl nezávisle prokázán.

Fyzická relace, více monitorů, screen lock, dlouhodobá spotřeba paměti a
libovolné aplikace nebyly testovány. Počty dokazují úklid vlastněných indikátorů,
nikoli nepřítomnost všech možných nativních úniků. Compositor se v testu nikdy
nezastavil; jeho crash recovery tento výsledek neřeší.

## Lokální použití a vrácení změn

Přesné příkazy a význam jednotlivých CLI operací jsou v [README.md](README.md).
Zapnutí prototypu pro test provádí přímo `tests/isolated.py` v dočasných XDG
adresářích. Nepoužívá se NixOS switch ani instalace do živého desktopu.
Po testu se soukromé procesy a dočasná konfigurace odstraní. Pro rollback
systému není co provádět. Případný odkaz na zdroje lze odstranit příkazem
`rm -f result-sources`; adresáře důkazů lze ponechat pro porovnání.

## Novější ověřené fáze

Následující práce rozšířila původní experiment přes panel a rekonstrukci desktop
UI až k úklidu vybraných objektů, omezenému zotavení po chybě a nativnímu
virtuálnímu vstupu. Podrobnosti zachovávají jednotlivé zprávy odkazované v README.
Nejnovější [OWNED-REPORT.md](OWNED-REPORT.md) dokládá jediný CLI požadavek,
který Shell dokončí i po zániku volajícího, odmítnutí souběhu i cizích řídicích
volání a oba scénáře chyb s 65sekundovým sledováním. Jde stále o SHELL RELOAD
v izolovaném headless prostředí, se zachovaným GJS a compositorem. Kompletní
bezpečný restart Shellu zatím prokázán není.

[PARTIAL-REPORT.md](PARTIAL-REPORT.md) pokračuje chybou během vytváření UI,
včetně výjimky uvnitř konstruktoru overview před přiřazením do Main. Popisuje
evidenci neúplného kandidáta, odstranění tolerantní aplikace lokálních patchů
a opravy asynchronních IBus vazeb na dosud neexistující klávesnici. Tato fáze
stále neprokazuje obecnou bezpečnost libovolného konstruktoru ani zotavení ze
zablokovaného GJS nebo chyby přípravy po změně stavu.

[PREPARATION-REPORT.md](PREPARATION-REPORT.md) doplňuje zachování modelu času
relace, pětisekundový limit nemutující přípravy a synchronní nativní commit.
Ověřuje odmítnutí před změnou UI, dokončení po uvolnění zkratek i odstavení
rozšíření a pozdní dokončení zrušené operace. Řízený reload UI je robustnější;
restart celého procesu, zablokovaný GJS a bezpečnost zámku zůstávají nevyřešené.

[CONSTRUCTION-REPORT.md](CONSTRUCTION-REPORT.md) přidává limit čekající konstrukce,
identitu kandidáta a odmítnutí jeho pozdního potvrzení i během dalšího pokusu.
Silnější kontrola našla samostatný indikátor screencastu ponechaný na stage a
zadržené kandidáty přes `global.context`; obojí má nyní explicitní úklid.
Dva konečné běhy prošly 65sekundovým sledováním i zachováním původních spojení.
Následný [QUARANTINE-REPORT.md](QUARANTINE-REPORT.md) již ověřuje terminální
karanténu při neodpovídajícím úklidu i explicitní obnovu po jeho pozdním dokončení.
Samotná trvalá karanténa UI neobnovuje. Report také shrnuje zbývající zásadní
práci pro úplný restart, bezpečnost relace a ověření ve VM.

[SECURITY-REPORT.md](SECURITY-REPORT.md) přidává úspěšný baseline ve skutečné
NixOS GNOME VM: logind zamčení, odmítnutí chybného hesla přes PAM a odemčení
správným heslem při zachování původních klientských spojení a textu.
Tento běh používá původní Shell; ověření bezpečnosti upraveného reloadu
v takové relaci je následující krok.

[VM-RELOAD-REPORT.md](VM-RELOAD-REPORT.md) tento krok rozšiřuje o řízenou obnovu
upraveného UI a následný skutečný zámek a PAM odemčení. Odhalila se a opravila
stará přihlášení k událostem SessionMode a logind, která headless test neviděl.
Původní klienti přežívají a starý ScreenShield projde kontrolou finalizace.
Zámek doručený přímo během konstrukce či nápravného pokusu zůstává neověřený.

[LOCK-RACE-REPORT.md](LOCK-RACE-REPORT.md) nyní přidává skutečné VM scénáře pro
přijatý zámek během přípravy a konstrukce s timeoutem a nápravou. Proud kláves
odhalil ztrátu zamčeného stavu; VM varianta teď drží požadavek a vstupní clonu
mimo jednotlivé UI kandidáty. Finální testy zachovají klientské hashe a projdou
PAM i kontrolou úklidu. Doručení zámku při chybějícím ScreenShieldu a obnova
zablokovaného GJS zůstávají otevřené.

[DURABLE-LOCK-REPORT.md](DURABLE-LOCK-REPORT.md) již prokazuje logind Lock
v mezeře bez ScreenShieldu. Backendový odběr uchová požadavek, nezávislá clona
chrání nápravu a nové UI zámek převezme. VM i headless regrese prošly;
další nalezená chyba předčasného uvolnění kalendářového proxy je opravená.
Jiné vstupy zámku, terminální karanténa se zámkem a zablokovaný GJS stále
potřebují další implementaci a ověření.

[INTERRUPT-REPORT.md](INTERRUPT-REPORT.md) posouvá výzkum zablokovaného JS:
samostatný watchdog přeruší skutečnou nekonečnou smyčku a soukromá úprava GJS
umožní označený návrat z GLib/GObject callbacku bez ztráty kontextu. Neoznačená
chyba stále ukončí kontrolní proces. Vnořený JS ale může pokračovat po částečné
změně modelu a `finally` se nevykoná. Výsledek je výzkumný prototyp;
před zapojením do odděleného Shellu potřebuje ochranu nativních vstupních hranic.

[BOUNDARY-REPORT.md](BOUNDARY-REPORT.md) tuto ochranu doplňuje: šest testovaných
nepodporovaných vstupů odmítne, povolené nativní callbacky zůstávají přerušitelné.
Běžné vnoření a konečný Promise job správně vrátí stav ochrany. Nové testy,
baseline a 77 upstream GJS testů prošly. Odmítnuté smyčky ale ukončuje vnější
supervisor; nejde o jejich obnovu. Integrace watchdogu do izolovaného Shellu
a zachování klientů při skutečném JS zablokování zůstává dalším krokem.

[SHELL-INTERRUPT-REPORT.md](SHELL-INTERRUPT-REPORT.md) dokládá další krok:
oddělený Shell s privátním GJS přežil přerušení skutečné nekonečné smyčky
v GLib callbacku, nativně požádal o rekonstrukci UI a zachoval původní klienty.
Prošel vstup, registry, vybraná finalizace a 65sekundové sledování. Tento
jednorázově ozbrojený callback nemění rozpracovaný backendový model;
obecná detekce a obnova takových operací, Promise jobs, zámku během přerušení
a pádu procesu zůstávají otevřené. Klasifikace je stále SHELL RELOAD.

[PANEL-INTERRUPT-REPORT.md](PANEL-INTERRUPT-REPORT.md) prokazuje obnovu dvou
rozpracovaných přenosů panelu. Modulový journal přežije přerušený JS rámec,
nativní obnova vrátí devět indikátorů, zničí a uvolní nedokončený panel
a poté obnoví UI. Oba běhy zachovaly původní klienty, druhý prošel 65sekundovým
sledováním. Konkurenční převzetí v mezeře před nativní opravou a obecně
rozpracované backendové operace zatím nejsou pokryté.

[HANDOFF-REPORT.md](HANDOFF-REPORT.md) doplňuje skutečný souběh v mezeře před
nativní opravou. Test před opravou prokázal chybný přijatý ReloadDesktopUi;
společná kontrola nyní odmítá pět reload/přípravných operací bez změny stavu.
Výslovné potvrzení i vlastní osmivteřinový deadline obnoví transakci právě
jednou. Oba běhy zachovaly klienty; první má 65sekundové sledování. Nejde
o blokování všech callbacků ani o obnovu libovolného backendového scope.

[PROTECTED-SCOPE-REPORT.md](PROTECTED-SCOPE-REPORT.md) doplňuje nativní čítač
chráněných synchronních backendových scope. Test prokázal odmítnutí přerušení,
řádné uzavření vnoření a správnou klasifikaci i úklid následného UI signálu.
Původní klienti přežili tři reloady a 65sekundové sledování; regrese skutečného
přerušení panelu také prošla. Nekonečný chráněný scope se neobnovuje a pozdější
spouštění trvalých callbacků ještě vyžaduje audit.

[DURABLE-CALLBACK-REPORT.md](DURABLE-CALLBACK-REPORT.md) prokazuje skutečnou
mezeru mezi registrací a pozdějším callbackem a přidává ochranu vybraných
GLib/GObject vstupů. Timeout, Source i signál emitovaný z C prošly s nulovou
JS hloubkou vlastnictví, uvolněným návratovým objektem a odpojeným pozdějším
UI signálem. Původní klienti přežili tři reloady; timeout měl 65sekundový soak.
Report zaznamenává také chyby přípravku a jeden nepravidelný výpadek extension
endpointu. Regrese se skutečnými stavy správce rozšíření prošla. Obecné GI async
vstupy a nový runtime/proces zůstávají další architektonickou prací.

[NATIVE-CLOSURE-REPORT.md](NATIVE-CLOSURE-REPORT.md) přesouvá zachycení ochrany
do GJS closure. Nové GI async, specializované cancellation a řetězené callbacky
prošly při nativní hloubce 1 a JS allocation hloubce 0. Dřívější JS obálky
timeoutů/GObject signálů byly odstraněné. Samostatný test ověřil také běžnou
výjimku a následné povolené přerušení. Pět reálných headless běhů zachovalo
klienty; GIO případ má 65sekundový soak. Další krok má cílit na skutečně nový
UI runtime/global a vlastnictví GType, nikoli jen na další odmítání přerušení.

[REALM-REPORT.md](REALM-REPORT.md) přidává samostatný důkaz nových UI globalů
se samostatnými ES module grafy, bootstrapem a Promise/timer callbacky.
Tři odpojené generace se uvolnily při zachování kanonických GI backendů.
Registrace GType v prvním globalu jej naopak zadržela a další registrace
selhaly. Trvalý backendový GType/vfunc/objekt s vyměnitelným UI delegátem
prošel třemi generacemi; kontrola se zadrženým delegátem únik odhalila.
Jde o **RESEARCH PROTOTYPE mimo Shell**. Další krok je skutečná St/Clutter
komponenta a ověření původních klientů při výměně realmu v izolovaném Shellu.

[PANEL-REALM-REPORT.md](PANEL-REALM-REPORT.md) tuto hranici nově ověřuje na
skutečném panelu Shellu. Jeho GType/vfunc zůstávají kanonické, implementace
metod běží v novém realmu. Deset výměn, rollback vadného kandidáta a tři
následné obnovy UI prošly s původními klienty a 65sekundovým sledováním.
Čtrnáct odpojených panelových globalů se uvolnilo; opravily se přitom
konkrétní retainery v JIT cache. Jde stále o omezený **SHELL RELOAD**.
Další widgety, Main, GJS kontext i proces zůstávají původní.

[DATE-MENU-REALM-REPORT.md](DATE-MENU-REALM-REPORT.md) přenáší osm tříd
datumového menu do vlastního realmu a ověřuje původní konstrukci přes JS
rodiče. Typované GI signály, nativní vfunc a vykreslení prošly. Běžná obnova
sebrala 24 starých wrapperů a tři realmy, chybová cesta 32 wrapperů a čtyři
realmy včetně vadného kandidáta. Původní klienti a jejich data přežili i soak.
Opravy řeší konkrétní odběry a prototypy zadržované backendem. Kanonické
GType i jejich callbacky jsou stále v původním GJS kontextu; další hranice
musí odstranit toto vlastnictví před skutečnou výměnou celého kontextu.

## Původní doporučení po první fázi

Přesunout skutečnou komponentu GNOME UI pod ověřený životní cyklus vlastnictví:
nejprve definovat explicitní teardown pro panel a všechny jeho odběratele,
signály, klávesové zkratky, menu a D-Bus vazby, a připojit tento integrační test
k lokálnímu overlay upraveného Shellu 50.5. Nejdříve musí být prokázána obnova
této skutečné komponenty se stejnými okny; teprve pak rozšiřovat hranici na
overview, správu vstupu a další služby. Screen shield a window management musí
mít bezpečný trvalý ownership mimo obnovovanou část. Kompletní restart GJS
nebo procesu zůstává samostatný, podstatně větší architektonický úkol.
