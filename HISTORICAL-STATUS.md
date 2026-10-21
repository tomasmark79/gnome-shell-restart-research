> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Current status: complete Shell runtime replacement

The separate complete-context implementation now passes an isolated end-to-end
test and a native-backend NixOS VM test. Three actual GjsContext replacements
retain the same Mutter process and original Wayland/XWayland client sockets.
Post-recovery input, overview, menus and new windows work. Retired callback
counts reach zero, and the repeated cycles do not add GTypes or vfunc bridges.
The VM also verifies logind locking and actual GDM/PAM authentication after
replacement. See [FULL-CONTEXT-RECOVERY.md](FULL-CONTEXT-RECOVERY.md) for commands,
evidence, implementation and the remaining scope limitations.

The stable UI reconstruction fallback remains available and unchanged in
scope. The separate publication workspace is `../gnome-shell-restart-nix`.
No host configuration has been activated and no active desktop was restarted.

## Historical status before complete-context reattachment


Navazující implementace z 21. října 2026 přidává `recover-desktop-ui`: obnovu
uklizeného neúspěšného UI přes přeživší nativní supervisor, bez závislosti na
rozšíření nebo UI D-Bus endpointu. Nativní API kontroluje identitu neúspěšného
kandidáta, stav úklidu a finální publikaci nové generace. Funguje také při
vypnutém rozšíření na zamykací obrazovce; ověřovací běhy a přesný rozsah jsou
v [RECOVERY-ACCEPTANCE.md](RECOVERY-ACCEPTANCE.md).

Úplná sada `artifacts/recovery-verified/result.json` prošla všemi osmi případy:
dvakrát vyčerpané opravné pokusy, dvakrát karanténa s pozdním úklidem,
přerušený přenos panelu, negativní reset kontextu, nativní GType kontroly
s Valgrindem/debuggerem a skutečný GDM/logind/PAM cyklus ve VM. Pět headless
obnov prošlo 65sekundovým sledováním. Původní Wayland/XWayland klienti zůstali
připojení a po obnově komunikovali. Výsledek přesto výslovně uvádí
`originalObjectiveAchieved=false`: ověřena je alternativa obnovy UI.

Úplný restart zůstává neimplementovaný. Nový izolovaný reset skutečně
finalizoval původní GjsContext, ale bootstrap selhal na existujícím statickém
GType `Gjs_TransientSignalHolder`. Mutter a původní klientská spojení přežila.
Předchozí nativní GType experiment tedy neodstranil blokátor celého Shellu.

Za podporovanou laboratorní alternativu je vybrána větev `stable`, která
zachovává Main/GJS/backend. Větev s komponentovými realmy při novém běhu
neprošla kontrolou sběru starého panelového realmu; její dřívější úspěšný běh
není považovaný za důkaz spolehlivé obnovy.

## Historický přehled před navazující implementací

Stav k 21. říjnu 2026: **funguje experimentální obnova desktopového UI, úplný restart celého Shellu zatím implementovaný není. Zbývá podstatná architektonická část, nikoli jen dokončení testů.**

## Co už je prokázané

- Rekonstrukce desktopového UI při zachování běžícího Mutteru a původních Wayland i XWayland spojení testovacích aplikací.
- Ohraničené opravné pokusy, časové limity přípravy a asynchronní konstrukce, karanténa a odmítnutí nepodporovaných operací.
- Izolované VM testy skutečného zamknutí a PAM odemknutí, včetně příchodu požadavku na zamknutí během obnovy a při nepřítomnosti ScreenShield.
- Oddělený experimentální Shell nyní přežil i přerušení nekonečného GLib JS callbacku a nativně vyvolal rekonstrukci UI. Původní Wayland/XWayland spojení a data přežila 65sekundové sledování; jde o výslovně ozbrojený testovací callback.

Tyto výsledky mají klasifikaci **SHELL RELOAD** a u přerušování GJS **RESEARCH PROTOTYPE**. Neprokazují restart procesu ani kompozitoru.

## Co ještě zbývá

| Oblast | Zbývající práce a význam |
| --- | --- |
| Obnova po zablokovaném JS | Řízený callback v izolovaném Shellu již prošel. Zbývá obecná detekce ve známých bezpečných vstupech a zotavení po rozpracované operaci; nepodporované vnoření a Promise jobs ochrana odmítá bez obnovy. |
| Rozpracovaný stav | Panel má journal a odmítání souběhu. GJS closure nově zachytí ochranu při vytvoření, včetně ověřených GI async a řetězených callbacků. Běžná JS volání, Promise tok a neoznačené callbacky stále nejsou univerzálně pokryté; nejde o obecný rollback. |
| Bezpečnost a běžný provoz | Doplnit zamknutí během terminální karantény, další vstupy zamykání a přechody autentizace; rozšířit ověření monitorů, vstupu, rozšíření a dlouhodobých opakování. |
| Celý JS runtime | Panel a osm tříd datumového menu běží s implementacemi v nových realmech. Prošla JS rodičovská konstrukce, typované signály a sběr starých wrapperů/realmů. GType a jejich JS callbacky však stále vlastní původní kontext. Celý UI module graf, Main, JSContext a proces nejsou nahrazené. |
| Nativní zamrznutí nebo pád procesu | JS watchdog neřeší zablokování v C ani pád Mutteru. Pro zachování spojení při restartu celého procesu je potřeba zásadní změna hranice mezi kompozitorem a restartovatelným Shellem. Tato architektura zatím implementovaná není. |
| Nasazení | Dokončit regresní a provozní ověření, způsob aktualizací a návratu a následně zvlášť schválený test fyzické relace. Hostitelská relace nebyla nahrazena. |

## Aktuální rozpracovaná změna

Hranice nově zahrnuje osm tříd datumového menu, včetně původního `super._init`, nativních vfunc, typovaných GI signálů a vykreslení. Tři obnovy sebraly 24 starých JS wrapperů a tři datumové realmy; vložená chyba s opravou sebrala 32 wrapperů a čtyři realmy. Původní klienti, text a virtuální vstup přežili i 65sekundové sledování. Podrobnosti jsou v [DATE-MENU-REALM-REPORT.md](DATE-MENU-REALM-REPORT.md). Main, kanonické GType callbacky a celý JSContext zůstávají původní.

## Realistický rozsah

K prakticky použitelnému **reloadu a obnově UI** zbývají především tři velké milníky: obnova po skutečně zablokovaném JS v Shellu, dokončení bezpečnostních a provozních scénářů a ověření integrace pro nasazení.

K **restartu celého procesu se zachováním původních aplikací a jejich spojení** zbývá navíc hlavní architektonická změna. Tuto část nelze poctivě označit za téměř hotovou. Počet dokončených experimentálních fází neodpovídá procentu celkového cíle; nejrizikovější hranice zůstávají před námi. Spolehlivý odhad v hodinách nebo dnech zatím nemám.

Nejbližší rozhodující krok bude: **ověřit nativní GType/vfunc bridge bez vazby na původní JS kontext a zachovat tentýž nativní objekt při skutečné výměně GjsContextu.** Samotné další komponentové realmy neprokazují výměnu celého runtime. Použití nové hranice pro celý desktop zůstává otevřené.

Kompilace nadále používají maximum dostupných vláken (`--cores 0`, zde 16).
