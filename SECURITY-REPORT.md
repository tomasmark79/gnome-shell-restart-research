> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# VM základ pro zámek a autentizaci

## Účel a hranice

Samostatný cíl `security-vm` sestavuje a spouští NixOS VM s GNOME 50.5,
skutečným GDM, PAM, AccountsService a logind. Používá původní Shell z připnutých
Nixpkgs. Neprokazuje bezpečnost reloadu upraveného Shellu; nejprve ověřuje,
že testovací prostředí skutečně rozpozná zamčení a nesprávné heslo.
Klasifikace této fáze je **RESEARCH PROTOTYPE**.

VM není importována do hostitelské konfigurace. Příkazy pro zámek, hesla a
správu procesů vykonává NixOS test driver uvnitř hostovaného systému.
`--unsafe-mode` zpřístupňuje Eval pouze v této jednorázové testovací VM,
stejně jako upstream NixOS GNOME test. Veřejné testovací heslo patří pouze
dočasnému účtu `alice` ve VM.

## Ověřované podmínky

1. GDM přihlásí uživatele do Wayland relace, kterou eviduje skutečný logind.
2. Dva GTK klienti zaznamenávají původní PID, socket FD/inode, identitu okna,
   hash náhodného neuloženého textu a čítač komunikace. Wayland klient používá
   `wl_display_roundtrip`, XWayland klient `XSync`.
3. Zamčení přes `loginctl lock-session` aktivuje ScreenShield a `LockedHint`.
4. Nesprávné heslo zadané virtuální klávesnicí QEMU vyvolá skutečné selhání PAM
   a desktop zůstane zamčený.
5. Správné heslo projde přes GDM verifier a vrátí uživatele do stejné relace.
6. Oba klienti během zamčení a po odemčení dál komunikují přes původní spojení
   a zachovají neuložený text. Shell PID a logind session ID zůstávají stejné.

Výsledek, úplný guest journal a klientské záznamy test kopíruje do
`evidence/tgnome-evidence/`. Tři snímky zachycují desktop před zamčením,
zámek po nesprávném hesle a desktop po odemčení. O ukončení všech guest
procesů a VM se stará test driver.

## Spuštění

```sh
nix build --cores 0 --print-build-logs .#security-vm --out-link result-security-vm
cat result-security-vm/evidence/tgnome-evidence/result.json
```

Cíl je úmyslně oddělený od běžných `flake check`; potřebuje virtualizaci a
několik GiB RAM. Běžné kontroly zůstávají dostupné příkazem
`nix flake check --cores 0`. Kompilace používají všechna dostupná vlákna,
VM samotná má čtyři virtuální CPU a 4 GiB RAM.

Zdrojové soubory jsou `tests/vm-security.nix`, `tests/vm-security.py` a
nový balíček ve `flake.nix`. Zdroj klientského probe je nyní omezen na
`probe.c`, aby změna testovacího skriptu zbytečně nepřestavovala klienta
a celou návaznou VM konfiguraci.

## Dosavadní chyby testovacího nástroje

První sestavení driveru odmítla kontrola typů kvůli příliš úzkému typu
výsledkového slovníku. Další běh odhalil rozdíl mezi GVariant `true/false`
a Python `True/False`. Poté se ukázalo dvojí JSON kódování: Shell Eval již
svůj výsledek serializuje. Tyto chyby byly opraveny bez vypínání typových
kontrol či lintu. Samy o sobě neposkytují výsledek autentizačního testu.

## Ověřený výsledek

Konečný běh prošel všemi čtyřmi podtesty, kontrolou typů i lintem.
Skript běžel 29,41 s; driver poté ukončil svoji QEMU VM. Výsledek:

```
/nix/store/pyj1qq6acdm89iawy3gljwfp142jhrsd-vm-test-run-tgnome-security-baseline
```

Hostovaný Shell měl před zamčením i po odemčení PID 979 a logind session ID
`1`, typu Wayland, s `CanLock=yes`. Chybné heslo zaznamenal skutečný
`pam_unix(gdm-password:auth)`; ScreenShield zůstal aktivní v `unlock-dialog`.
Správné heslo vrátilo stav `user`, `locked=false`, `active=false` a odstranilo
`LockedHint`. Snímky nesprávného hesla a následného desktopu byly také vizuálně
zkontrolovány.

| Klient | Původní PID | Socket inode | Identita okna | Komunikační čítač před → po |
| --- | --- | --- | --- | --- |
| Wayland | 1584 | 16501 | 34 | 10 → 43 |
| XWayland | 1680 | 15559 | 12582915 | 4 → 38 |

FD, inode, PID, identita okna i hash neuloženého textu zůstaly v obou případech
stejné. Čítače vzrostly i při zamčení. `passed=true` zde znamená splnění
autentizačního baseline, nikoli reload nebo restart Shellu.

Následný `nix flake check --cores 0` prošel. Hostitelský Shell zůstal PID
1350942; nedošlo k aktivaci systému ani zásahu do hostitelského GDM či logind.

## Další krok

Následná fáze je již zaznamenána v [VM-RELOAD-REPORT.md](VM-RELOAD-REPORT.md):
upravený Shell prošel řízenou obnovou a následným skutečným zámkem a odemčením.
Závody příchodu zámku během obnovy tím stále nejsou ověřené.

Po úspěšném baseline připojit upravený Shell v přísně VM vymezené variantě,
ověřit odmítnutí reloadu při zámku a závod příchodu zámku během obnovy.
Pak oddělit trvalé vlastnictví bezpečnostních objektů od obnovovaného UI.
Současné headless testy s náhradním logind ani tento baseline bez reloadu
neprokazují bezpečnost tohoto přechodu. Obnova zablokovaného GJS a nativního
pádu zůstává samostatná architektonická práce.
