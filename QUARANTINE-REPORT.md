> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Stav restartovatelného GNOME Shell a ověření karantény

## Kolik práce ještě zbývá

Komplexní implementace ještě vyžaduje zásadní architektonickou práci.
Máme funkční laboratorní obnovu velké části desktopového UI se zachováním
kompozitoru, stejného GJS kontextu a původních Wayland/X11 klientů.
Nemáme obecný restart celého Shellu ani obnovu po zablokování GJS či pádu
kompozitoru. Procento dokončení ani termín nelze z dosavadních testů poctivě určit.

Zbývají čtyři hlavní oblasti:

1. **Silnější hranice obnovy.** Vyřešit obnovu nefunkčního JS runtime bez ztráty
   Wayland serveru, zdrojů a klientských spojení. Pokus o výměnu celého GJS
   kontextu narazil na registrace typů a callbacky do zrušeného kontextu;
   současná implementace kontext ponechává. Pád nativního kompozitoru je další,
   samostatně nevyřešená hranice.
2. **Bezpečnost relace.** Oddělit trvalé vlastnictví zámku, autentizace a vstupu
   od obnovovaného UI a ověřit přechody s reálným GDM/PAM/logind ve VM.
   Soukromý headless test s náhradním logind tento důkaz neposkytuje.
3. **Úplnost stavů a prostředků.** Doplnit výjimkově bezpečnou konstrukci,
   asynchronní služby, rozpracované notifikace a vstup, sdílení/nahrávání,
   libovolná rozšíření, více monitorů a fyzická zařízení. Vybrané objekty
   prošly kontrolou sběru paměti; úplný audit všeho z toho neplyne.
4. **Provozní ověření a integrace.** Celá VM relace, opakované dlouhé běhy,
   různé okamžiky selhání a reprodukovatelná integrace do NixOS. Ověření
   fyzické relace musí následovat až po těchto krocích a samostatném schválení.

Nejbližší milník je kompletní VM scénář pro bezpečnost zámku a autentizace.
Současný výsledek je výzkumná implementace řízeného reloadu UI.

## Dvanáctá fáze: neodpovídající úklid

Nativní pětisekundový limit konstrukce vyvolá zrušení kandidáta. Pokud JS
nepotvrdí úklid během dalších dvou sekund, transakce přejde do
`ui-cancellation-timeout`: `uiActive=false`, `uiQuarantined=true`.
Veřejný reload i nativní zkušební vstup odmítají nové pokusy bez změny čítačů.
Pozdní oznámení úspěchu karanténu nezruší.

Pozdní potvrzení úklidu může karanténu uvolnit pouze pro aktuální identitu
kandidáta, od vlastního Shell D-Bus spojení, s potvrzenou připraveností a
ověřenými interními příznaky dokončeného úklidu. Výsledkem je `ui-failed`;
automatické opakování se již nespustí. Teprve nový explicitní požadavek může
postavit další UI. Toto platí pro testovanou větev vypršení lhůty úklidu,
nikoli pro každé možné selhání úklidu.

Tři negativní potvrzení byla odmítnuta bez změny nativního stavu: stará identita
kandidáta, nepotvrzená připravenost a tvrzená připravenost před skutečným úklidem.
Injekce `never` čeká na nevyřešený Promise; JS a nativní smyčka zůstávají
responzivní. Nejde o test synchronně zablokovaného JS ani nativního kódu.

## Výsledky

Všechny následující běhy mají `passed=true`, `workerExitCode=0`, odstraněný
soukromý profil a nulový počet problémů ve sledované diagnostice:

| Artefakt v `artifacts/` | Ověřený výsledek |
| --- | --- |
| `quarantine-delayed-verified` | Opožděný úklid, žádné automatické opakování, explicitní obnova UI, následné sledování 65,007 s |
| `quarantine-never-verified` | Karanténa stabilní 65,535 s, původní klienti dál komunikují; UI neobnoveno |
| `quarantine-normal-regression` | Dvě běžná vypršení konstrukce, právě jedno automatické opakování a následná explicitní obnova |
| `quarantine-preparation-regression` | Řízená chyba po deaktivaci starého UI, dokončení směrem vpřed a tři úspěšné konstrukce |
| `quarantine-terminal-frame` | Krátký terminální scénář včetně skutečného snímku `desktop-quarantined.png` |

U opožděného úklidu konečný stav uvádí tři externí pokusy, dvě potvrzená UI,
jedno vypršení, jednu karanténu a nula automatických opakování. Kontrola
finalizace potvrdila 36 vybraných starých UI objektů, včetně neúspěšného
kandidáta, s nezávislými retenčními kontrolami. Fungovaly původní nabídky,
overview a editace obou původních klientů stejnou virtuální klávesnicí.
Obvyklá kontrola prostředků a přímých potomků stage zůstala splněná.

Terminální scénář má pouze jednu potvrzenou generaci a dvě konstrukce.
Klasifikace je `RESEARCH PROTOTYPE`, `desktopUiReloadDemonstrated=false`.
Původní PID, spojení, identita oken a obsah klientů zůstaly zachované a jejich
komunikační čítače rostly. To dokazuje omezení dalšího poškození, nikoli návrat
funkčního desktopu. Vzhled zachyceného snímku sám obnovu neprokazuje.

První opožděný test selhal na časování kontrolního oznámení: přišlo ještě během
dvousekundové lhůty rušení. Pro tento scénář se kontrolní oznámení přesunulo
na osmou sekundu; běžné testy zachovávají původních sedm sekund.

Všechny uvedené běhy použily:

```
/nix/store/9mm0w8982h09d4s3xmlb689pb89d25w7-gnome-shell-50.5/bin/.gnome-shell-wrapped
```

Derivace: `/nix/store/1qz8qff12wj3hfi9sdyvdmll828c4b1d-gnome-shell-50.5.drv`.
Kompilace s `--cores 0` skutečně použila `-j16`. Lokální patche vyžadují
`--fuzz=0`; vlastní upstream patche Nixpkgs mají původní samostatnou politiku.
`nix flake check --cores 0` prošel. Po bězích nezůstal soukromý testovací Shell
ani worker. Hostitelský Shell zůstal původní proces PID 1350942; neproběhla
aktivace NixOS, odhlášení ani restart služby.

Implementace: `shell/tgnome-runtime.h`, `shell/stableMain.js`,
`extension/extension.js`, `tests/isolated.py`. Předchozí měření a omezení jsou
v [CONSTRUCTION-REPORT.md](CONSTRUCTION-REPORT.md).
