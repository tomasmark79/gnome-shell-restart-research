> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Obnova UI v GNOME VM se skutečným zámkem a PAM

## Výsledek a rozsah

Upravený GNOME Shell 50.5 nyní prošel řízenou obnovou desktopového UI v NixOS
Wayland VM s reálným GDM, logind a PAM. Následně se stejná relace zamkla,
odmítla chybné heslo a odemkla správným heslem. Původní Wayland i XWayland
klient zachovaly spojení, okna a neuložený text.

Klasifikace je **SHELL RELOAD**. Stejný Shell proces, GJS kontext a Mutter
zůstávají živé. Obnova zablokovaného JS nebo pádu kompozitoru není vyřešená.
Tento scénář zatím neověřuje příchod požadavku na zámek během přípravy,
konstrukce nebo nápravného pokusu. Bezpečnost těchto závodů zůstává otevřená;
stávající výsledek neopravňuje k použití ve fyzické relaci.

## Vymezení VM varianty

Balíček používaný pouze cílem `security-reload-vm` přidává kompilátorovou
definici `TGNOME_SECURITY_VM`. Nativní neheadless vstup vyžaduje současně:

- tuto zvláštní kompilaci;
- SMBIOS product name `TgnomeSecurityFixture`;
- běžný soubor `/etc/tgnome-vm-fixture` vlastněný UID 0, bez zápisu skupiny
  či ostatních a s přesným obsahem `security-reload-v1\n`;
- původní laboratorní příznak povolení resetu a nepřepsaný zdroj Shell JS.

Nativní kontrola se provádí při startu procesu. Teprve poté nastaví neměnný
JS příznak pro veřejnou metodu reloadu. Samotná proměnná prostředí tuto
výjimku nezpřístupní. Běžný `stable-shell` nadále vyžaduje headless backend.
Testovací virtuální klávesnice a zachytávání snímků přes rozšíření si zachovaly
své headless omezení; VM používá klávesnici a snímky QEMU test driveru.

## Co první VM běh odhalil

První obnova UI doběhla, ale následné zamčení zavolalo starý ScreenShield
a několik starých indikátorů. Journal obsahoval přístupy ke zničeným objektům
v `screenShield.js`, `unlockDialog.js`, kalendáři a indikátorech.
Trvalé JS emitery a `DBusProxy.connectSignal()` obcházely evidenci původně
zaměřenou na GObject signály. Headless fixture bez skutečného zamykání to
neodhalila. Test současně potřeboval zachytit stderr odmítnutého RPC.

Nová evidence sleduje vybrané trvalé JS emitery a přihlášení k D-Bus signálům
odděleně od nativních GObject ID. SessionMode, LoginManager, aktuální logind
session proxy a smartcard manager nyní odpojí své přechodné UI odběratele.
Trvalé odběry hlavního modulu a správy komponent zůstávají při reloadu živé.

ScreenShield před zničením UI zruší čekající inhibitor, uzavře držený stream
a odpojí presence signál. Pozdní dokončení inicializace presence, získání
logind session nebo inhibitoru nemůže znovu připojit zrušený ScreenShield.
Samostatná finalizační kontrola ověřuje i tento starý objekt.

První regrese se silnější evidencí našla o jeden odběr SessionMode méně:
správce komponent je trvalý, ale jeho konstruktor nebyl v backendovém scope.
To je opravené explicitním zařazením správce mezi backendové služby.
Kontrola inventáře nebyla oslabena.

## Testovací sekvence

Test přihlásí skutečnou GDM Wayland relaci, otevře oba klienty a provede jeden
veřejný reload. Ověří nativní potvrzení, generaci UI, původní PID a spojení
klientů i stejné logind session ID. Potom zamkne relaci přes logind.

Při zámku veřejné RPC odmítne D-Bus: běžný životní cyklus GNOME rozšíření
je v `unlock-dialog` deaktivuje. Nativní zkušební vstup odmítne neprovedenou
přípravu. Oba pokusy nechají nativní stav beze změny a relace zůstane zamčená.
Test proto netvrdí, že veřejná metoda běží uvnitř zamčené relace.

Chybné heslo prokazatelně odmítne `pam_unix(gdm-password:auth)`, správné heslo
odemkne tutéž relaci. Na konci se musí uvolnit všech 13 sledovaných starých UI
objektů a nezávislé kontrolní objekty se musí chovat podle očekávání.
Journal původního Shell PID od zahájení reloadu nesmí obsahovat sledované
JS chyby, přístupy ke zničeným objektům ani kritickou diagnostiku.

## Reprodukce a artefakty

Konečný běh `passed=true` má výstup:

```
/nix/store/96pnwxmnf5dv5s0gn15mrm8vf0px3lkn-vm-test-run-tgnome-security-reload
```

Použil VM balíček
`/nix/store/dkg8hwxrrzf6vfhsggv98jabv4gh0ccm-gnome-shell-50.5`, derivaci
`/nix/store/737in0cap3w702rmyxlb5419sny628vz-gnome-shell-50.5.drv`.
Kompilace s `--cores 0` skutečně běžela s `-j16`. Konečný driver prošel
kontrolou typů a lintem a dokončil test za 30,30 s, poté ukončil svoji VM.

Shell měl před obnovou i po odemčení PID 980 a logind session ID `1`.
Nativní protokol zaznamenal jeden pokus a jeden commit, bez opakování,
timeoutu či selhání. `securityVm=true`; sledovaná diagnostika je prázdná.
Všech 13 vybraných starých UI objektů se uvolnilo, včetně ScreenShieldu;
obě nezávislé retenční kontroly dopadly podle očekávání.

| Klient | Původní PID | Socket inode | Komunikační čítač před → po |
| --- | --- | --- | --- |
| Wayland | 1591 | 14747 | 9 → 51 |
| XWayland | 1681 | 15591 | 4 → 45 |

V obou případech zůstaly stejné také FD, identita okna a hash neuloženého textu.
Snímky po chybném hesle a po odemčení byly vizuálně zkontrolovány.

Navazující headless testy používají běžný balíček
`/nix/store/gqcr8jialg5fkdd46q2ssfw3dnzy5qpd-gnome-shell-50.5`:

| Artefakt v `artifacts/` | Výsledek |
| --- | --- |
| `security-roots-headless-final` | Tři commity, 36 vybraných starých objektů uvolněno, shodné inventáře, sledování 65,007 s |
| `security-roots-partial-regression` | Chyba po panelu, právě jedno automatické opakování, tři commity, 45 vybraných starých objektů uvolněno |

Oba mají `passed=true`, `workerExitCode=0`, odstraněný soukromý profil,
nulovou sledovanou diagnostiku a `securityVm=false`. `nix flake check --cores 0`
prošel. Po testech nezůstala soukromá VM ani Shell worker. Hostitelský Shell
zůstal původní PID 1350942, bez systémové aktivace či restartu služeb.

```sh
nix build --cores 0 --print-build-logs .#security-reload-vm --out-link result-security-reload-vm
cat result-security-reload-vm/evidence/tgnome-evidence/result.json
nix flake check --cores 0
```

Snímky `desktop-after-ui-reload.png`, `wrong-password-still-locked.png` a
`desktop-after-unlock.png`, klientské JSONL a úplný guest journal jsou ve
výsledku VM testu. Původní nepatchovaný autentizační baseline zůstává
samostatným cílem `security-vm`; viz [SECURITY-REPORT.md](SECURITY-REPORT.md).

Implementace mění `flake.nix`, `extension/extension.js`,
`shell/tgnome-runtime.h`, `shell/stableRegistry.js`, `shell/stableMain.js`,
`shell/stableScreenShield.js`, `shell/security-lifetime.patch`,
`tests/vm-security.nix` a `tests/vm-security.py`.

## Následující hranice

Následná [fáze závodů zámku](LOCK-RACE-REPORT.md) již ověřuje přijatý zámek
během přípravy i čekající konstrukce s timeoutem a nápravou. Popsala a opravila
ztrátu zamčeného stavu při proudu kláves a doplnila nezávislou clonu.
Výsledek tohoto původního jednoduššího scénáře zůstává oddělený.

Další krok je řízeně doručovat zámek během přípravy i během konstrukce UI
a ověřovat stav, vstup a renderování při selhání. Odběry jsou nyní uklizené,
ale bezpečnostní stav ještě nemá samostatný trvalý životní cyklus mimo UI.
Další otevřené oblasti zahrnují monitorové změny, sdílení, obecná rozšíření,
úplnost konstruktorů a silnější hranici obnovy nefunkčního GJS.
