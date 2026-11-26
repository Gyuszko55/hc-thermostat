# <img src="images/icon.png" alt="HC Thermostat icon" width="44" align="absmiddle"> HC Thermostat (Heat Conductor Thermostat)

[English](README.md)

> **Béta.** Egy valódi ház fűtését vezérli, de minden rendszer más: egy új példány mindig **árnyék módban** indul
> (számol és összevet, nem kapcsol semmit). Csak akkor élesítsd, ha átnézted a döntéseit, és legyen független
> tartalék termosztát is (lásd Biztonság). Hogy mit és hogyan teszteltünk, az alábbi táblázat mutatja.

## Mit teszteltünk

| Hőtermelő / rendszer | Hogyan tesztelve |
|---|---|
| On-off gázkazán, radiátorok (TPI / PID reléről) | **Élesben**, egy valódi házban, 2026 ősze óta naponta |
| Szelepfejek egy helyiségben (Sonoff TRV Gen2, Zigbee2MQTT) | **Élesben**, egy helyiség, 2026-11-11 óta |
| Klíma (`ac` vezérlés, Gree) | **Élesben**, 2026-11-09 óta |
| Elektromos fűtőtest reléről (olajradiátor) | Valódi eszköz, többnyire árnyék módban (röviden élesben) |
| Moduláló / OpenThermes kazán, fűtési görbe | **Próba-példány**: szimulált kazán és ház egy élő Home Assistantban, valós időjárással |
| Hőszivattyú fan-coillal | **Próba-példány**: szimulált, mint fent |
| Távfűtéses lakás, csak szelepfejek (SONOFF TRVZB + SNZB-02 Zigbee2MQTT-n) | **Próba-példány**: szimulált fejek és hőmérők a Zigbee2MQTT entitásneveivel és értékeivel, élő Home Assistantban |
| Hőtárolós kályha, távfűtés, pellet / puffer, padlófűtés és -hűtés, elektromos padló, központi zónák | **Csak szimulátor és tesztek** |

Élesítés előtt az árnyék mód és a döntésnapló mutatja meg, hogyan viszonyul a HC a saját vezérlésedhez: az egyezési
százalék azt mutatja, milyen gyakran döntött volna ugyanúgy.

A HC Thermostat a Home Assistant fűtési **felügyelője**, egyszerű rendszerekhez beépített szabályozóval. Nem akarja leváltani a jó termosztát-integrációkat: föléjük kerül, eldönti, mit csináljon a ház, és megmondja, miért.

## Első lépések

### Gyors kezdés

**Feltételek:** Home Assistant **2026.10** vagy újabb; egy helyiséghőmérő, és amit a HC kapcsol vagy állít (relé:
`switch` / `input_boolean`, meglévő `climate` termosztát vagy klíma, vagy előremenő cél `number`). A °C és a °F is
működik: a °F-os mérést átszámolja, és amit egy termosztátra ír, a rendszer mértékegységében küldi.

1. **Telepítés:** HACS → ⋮ → Egyéni tárolók → `https://github.com/Gyuszko55/hc-thermostat`, típus *Integráció* →
   **HC Thermostat** letöltése → a Home Assistant **újraindítása**.
2. **Felvétel:** Beállítások → Eszközök és szolgáltatások → Integráció hozzáadása → **HC Thermostat** → válaszd a
   **beállító varázslót (ajánlott)** – egy hivatkozás megnyitja a **HC beállítás** panelt (kiszámolt beállítások és
   helyiségek; rendszergazdáknak) –, vagy a kézi beállítást: név, hőforrás és rendszer, eszközök (ahol lehet, előre
   kitöltve, a többi lenyitható), végül a célok és az időzítés.
3. **Figyeld árnyék módban:** az új példány számol és naplózza, mit tenne, de nem kapcsol. A **HC info** panel és a
   döntés-szenzor megmondja, miért.
4. **Élesítés:** Beállítások → Eszközök és szolgáltatások → HC Thermostat → **Konfigurálás** → **Élesítés**, a
   megerősítés bejelölésével. (A varázsló összefoglalóján az új példány élesen is indítható.) Vissza árnyékba
   ugyanígy.

**Jelenlét** (`presence_entities`): otthon, ha bármelyik `home`, `on`, `otthon` (otthon lévő `person` /
`device_tracker`, bekapcsolt bináris szenzor); szabadság: `vacation`, `szabadság`, `szabadsag`; minden más (zóna neve,
`not_home`, `off`) távol. Jelenlét-entitás nélkül a ház mindig otthon van. `input_select` vagy `sensor`
forrásnál a beállítások (*Funkciók*) felkínálják a forrás saját értékeit – kiválasztod, melyik jelent otthont
(`presence_home_states`) és melyik szabadságot (`presence_vacation_states`); ezek a beépített szavak mellett számítanak.
Amíg nincs kiválasztva semmi, egy nem ismert érték egyszer figyelmeztetést ír a naplóba (és távollétnek számít).

**Példány törlése:** a HC semmit nem ír vissza – a szelepfej vagy a kezelt termosztát megtartja az utolsó célt, amit
a HC küldött, a relé úgy marad. Szükség esetén állítsd kézzel. Az utolsó példány törlésével a HC panelek is
eltűnnek az oldalsávról (a következő példánnyal visszajönnek).

### Telepítés

**HACS (egyéni tároló):** HACS → ⋮ → Egyéni tárolók → `https://github.com/Gyuszko55/hc-thermostat`, típus
*Integráció* → **HC Thermostat** letöltése → a Home Assistant újraindítása → Beállítások → Eszközök és
szolgáltatások → Integráció hozzáadása → **HC Thermostat** (az első lépés felajánlja a **HC beállítás** varázslót).

**Kézzel:** másold a `custom_components/hc_thermostat` mappát a konfiguráció `custom_components` mappájába, és
indítsd újra.

A kerek termosztát kártya külön projekt: [hc-dial-card](https://github.com/Gyuszko55/hc-dial-card).

### Beállító varázsló

Oldalsáv-panel, **HC beállítás** (csak adminnak), hat lépésben: mit állítunk be (új vagy meglévő példány) →
hőforrás → rendszer és szabályozás, a javaslati mátrix értékelésével és indoklásával → eszközök (csak a
választott szabályozáshoz kellő mezők, előre kitöltött javaslatokkal) → az ezekből kiszámolt beállítások,
mindegyik indoklással és átírható (ciklus és minimális égés a rendszerből, a klíma lépésköze és határai, a gáz
m³-enkénti hője, a kazán alapjárata és égése a fogyasztásmérő két napjából, helyiséghőmérők) → összefoglaló és
mentés. Új példány mindig árnyék módban indul. A panel az első HC-példány után jelenik meg (az elsőt a
Beállítások → Eszközök és szolgáltatások alatt kell felvenni).

### Egyszerűbb beállítás

- **Kézi beállítás, eszközök lépés:** fent csak az van, ami az első beállításhoz kell – helyiséghőmérő (vagy fali
  termosztát érintkezője), amit a HC kapcsol vagy állít, kinti hőmérő, ablakok, jelenlét. A mérők, a másik hőforrás,
  a padló, a hőszivattyú és a célhő forrása a **Továbbiak (nem kötelező)** részben nyitható le. Ahol a Home Assistant
  elég adatot ad, a választók előre ki vannak töltve: kinti hőmérő (a neve vagy a helye szerint kinti, különben
  időjárás-entitás), a nappali hőmérője (vagy az egyetlen szóba jövő), minden személy a jelenléthez, a gázóra, ha
  pontosan egy van (gázkazánnál). Relét vagy termosztátot sosem tölt ki.
- **Beállítások:** fent az üzemmód, a célok és az éjszaka; a többi témánként lenyitható – *Szabályozás és időzítés*,
  *Funkciók*, *Védelmek*, *Padló*, *A hőtermelő jelei és teljesítménye*, *Energia és költség*, *Csatlakozó tér*,
  *Mérések*. A tárolás a régi (egy szinten), meglévő példánynál semmi nem változik.
- **Vezérlés módosítása** (beállítások menü): pl. egy relés példány **külső termosztátra** állítása új példány
  nélkül – ugyanaz a lista, mint a felvételnél, utána az, amit az új vezérlés kapcsol vagy állít. A példány árnyék
  módba kerül, minden más beállítás marad. A helyiségek csak TPI / PID vezérléssel működnek: előbb vedd ki őket.
- **Tüzelőanyag szám helyett:** a `heat_fuel` (automatikus, földgáz m³, PB-gáz kg, fűtőolaj l, pellet kg, villany
  kWh, egyéni) és a `heat_efficiency` (%) kiszámolja az energiatényezőt; az automatikus a mérő mértékegységét nézi
  (m³, kWh, MJ, GJ), mérő nélkül a hőtermelőt. A korábban mentett példány megtartja a számát (egyéni).

## Mit csinál a HC

### Funkciók

**Hőforrások és rendszerek**
- Gázkazán (be-ki), moduláló kazán fűtési görbével, elektromos fűtő, elektromos padlófűtés, hőszivattyú, klíma, hőtárolós kályha, távfűtés, pellet kazán.
- Radiátor, vizes vagy elektromos padló (egy helyiség vagy zónák), fan-coil, helyiségben álló egység; központi kazán zónákkal, puffertartály szerep (rétegzett, legfeljebb négy hőmérő) és pufferből fűtő keverőkörök (árnyék).

**Szabályozás**
- Saját szabályozó: TPI vagy PID PWM-mel, on-off vezérlés hosszú futásokkal, időjáráskövető fűtési görbe, vagy külső termosztát / klíma vezérlése a célértékén át.
- Minimális futási idő és szünet, amit egyik algoritmus sem írhat felül; árnyék-szabályozó a másik algoritmussal, összehasonlításhoz.
- Árnyék mód (számol, nem kapcsol) vagy éles mód, példányonként.

**Kényelem és jelenlét**
- Presetek (komfort, otthon, alvás, eco, távol, szabadság, felfűtés) saját lejárattal; éjszakai ütemezés.
- Jelenlét példányonként: a ház a háztartást, egy helyiség egy személyt követhet (lásd lent).
- Felfűtés, ami az utómelegedéssel együtt áll meg a célnál; tanulja az utómelegedést, a perc/fok arányt és a tartást.
- Célhő átvétele fali termosztátból vagy number entitásból; vezetékes fali termosztát kontaktusa mint fűtésigény.

**Padlófűtés**
- Padlóhőfok-limit a burkolat és a szenzor helye szerint, padlótemperálás (meleg padló), padló szerinti tartalék a helyiséghőmérő kiesésekor, padlóhűtés harmatpont-védelemmel.

**Helyiségek és zónák**
- Egy kazán helyiségei: a vezető helyiség vezérli a kazánt, minden más helyiség saját HC termosztátot kap – szelepfejes helyiség saját céllal, a helyiség hőmérőihez kalibrálva és helyiségenkénti jelenléttel, a szelepfej nélküli helyiség a házat követi; szelepfejes (TRV) helyiségek saját eltolással és kalibrálással; zónánkénti előremenő-kérés és -plafon a központi moduláló kazánnál; elektromos zónák közös terheléskorlátja; csatlakozó tér (nyitott ajtó) és olcsóbb hőforrás javaslat.

**Biztonság és felügyelet**
- Szünet nyitott ablaknál (érzékelő vagy gyors hőesés), nyári pihenő, fagyvédelem, újraindítás-védelem, hihetetlen mérések kiszűrése, tartalék üzem érzékelő-kiesésnél.
- Kazán-egészség a fogyasztásból és a lángjelzésből (nem reagál, nem gyújt be, taktol, parancs nélküli égés, túlfűtés), fűtési hiba jelző.
- Heti szelep- és szivattyúmozgatás; vezérelt áram jelzése; távfűtésnél visszatérő-korlát.

**Eszközök**
- Beállító varázsló az oldalsávban, HC info panel (a rendszer rajza minden adattal), döntésnapló és szövegek magyarul és angolul, hőveszteség- és hőigény-becslés, költség-összevetés.
- Kerek termosztát kártya hozzá: [HC Dial Card](https://github.com/Gyuszko55/hc-dial-card).

### Alapok

- **Árnyék mód (alapértelmezett):** mindent kiszámol, semmit nem kapcsol, és összeveti magát a valódi fűtéssel.
- **Saját szabályozó:** TPI vagy PID, PWM-mel, be-ki reléhez; a minimális futási időt és szünetet egyik algoritmus sem írhatja felül.
- **Gyors felzárkózás:** ha egy helyiség tartósan (30 percig, padlón 2 óráig) legalább 0,5 °C-kal a cél alatt van, a
  teljes ciklust kapja PWM-szünet nélkül, amíg 0,2 °C-on belül nem ér. A tartós elmaradást kompenzáló eltolás óránként
  tanul (legfeljebb 0,02 óránként), a TPI erőssége naponta. A TPI két együtthatója a Szabályozás részben állítható.
- **Alacsony hőfokú felzárkózás** (0.74.0, alapból ki, Szabályozás rész): ha a helyiséget ellátó összes keverőkör
  tartósan (15 percig) 45 °C alatti előremenőt kér – a kör kért céljáról van szó, nem a mért vagy a puffer miatt
  korlátozott értékről –, a felzárkózás 0,3 °C-tól indul, radiátornál 30 perc, padlónál (ha a helyiség egyik köre
  padló) 2 óra után, és 0,1 °C-on (padlón 0,2 °C-on) belül áll le. Köradat nélkül a helyiség saját küszöbei maradnak.
  A panel mutatja a kört, a besorolást, a használt küszöböket, a várakozást és az utolsó kilépés okát.
- **Mért válasz:** a panel a szokásos, legalább 10 perces futásokból mutatja, hány perc után melegszik a helyiség,
  milyen gyorsan, mennyi az utánfűtés, és milyen gyorsan hűl vissza. Csak kijelzés, nem szabályoz belőle.
- **Külső termosztát:** bármely `climate` entitás célhőfokát és üzemmódját állítja.
- **Életvédelmi leállítás** (0.77.0, opcionális): füst, tűz, gáz, CO és víz bemenetek (a bekötött biztonsági lánc
  segédkontaktusa, érzékelők) minden HC-példányt leállítanak (0.78.2: a saját bemenet nélkülieket is), mindenek
  felett, kézi nyugtázásig reteszelve; a valódi
  leállítás a bekötött láncé (gázszelep, kontaktor, vízszelep), a HC ezt soha nem helyettesíti. A 0.78.2 óta a
  leállítás árnyék módban, „HC felügyelet szüneteltetve” mellett, az indulás utáni türelmi időben, ütközés esetén és
  hibás döntési lépésnél is kiíródik.
- **Helyi védő** (0.76.0, opcionális): a relé melletti Shelly Gen3 / Gen4 script bérletként kapja a HC parancsát, és a
  saját hőmérője szerint vezérel tovább, ha a Home Assistant vagy a HC kiesik – lásd [guard/README.md](guard/README.md).
- **Felügyelet:** jelenlét és éjszakai ütemezés, szünet nyitott ablaknál, nyári pihenő, fagyvédelem, tartalék üzem érzékelő-kiesésnél, újraindítás-védelem, hibafigyelés, opcionális felfűtés.
- **Döntésnapló** magyarul és angolul.
- **A ház AI-elemzése** (nem kötelező, a saját AI Task entitásoddal – Beállítások → Funkciók): a HC minden reggel
  kiszámolja a naplóból az egész ház előző napját (helyiség-hőmérsékletek, cél alatti és túlfűtött órák, fűtési idő és
  indítások, döntések, energia és költség – mért vagy becsült), az AI ezekből pontszámot, összefoglalót, megfigyeléseket
  és teendőket ír. A házrajzon az **AI** gombra nyílik meg a jelentés; az *Elemzés most* azonnal elkészíti (legfeljebb 15 percenként és naponta
  6-szor – mindegyik egy MI-hívás). Csak javasol,
  semmit nem állít át. Szenzor, gomb és `hc_thermostat_ai_report` esemény is jár hozzá.
- **Vezérlési mátrix:** a hőtermelőből és a hidraulikából javaslatot ad. Ez szakmai alapbeállítás, nem helyettesíti a gépész méretezését.

### Döntési sor

Mit olvas, hogyan dönt és mit számol ki a HC három szinten – hőforrás, végrehajtás, fűtőkészülék és helyiség –,
a hőforrás × fűtőkészülék mátrixszal: [DECISION_CHAIN.hu.md](DECISION_CHAIN.hu.md) (a kódból generálva).

## Napi használat

- **Cél módosítása:** a termosztát-kártyán, vagy **Konfigurálás → Célok és időzítés** – az otthoni, éjszakai,
  távolléti és szabadság-cél, a fagyhatár és az éjszaka kezdete és vége egy rövid lapon, mentéskor azonnal érvényes.
- **Hétvégi éjszaka:** ugyanitt egy nem kötelező *hétvégi éjszaka* (kezdet és vég) a szombat és vasárnap reggel véget
  érő éjszakákra – pl. 23:30-kor lefekvés, az éjszakai cél 08:00-ig. Üresen olyan, mint hétköznap.
- **Heti program (0.72.0):** a **HC info** panelen, *Presetek* → *Heti program beállítása*: egy 7 napos rács, amelyen
  15 perces lépésben festheted a *Komfort*, *Otthon*, *Éjszaka* és *Eco* szinteket (*Hétfő → K–P*, *Szombat → V* és
  minta segít). A szint hőmérséklete ugyanitt átírható, és minden sávja követi. Mentve a program lép az éjszakai sáv
  helyébe (az optimális indítás ilyenkor az éjszaka utáni szintre céloz); a *Program törlése* visszahozza az éjszakai
  sávot. A saját TRV-fejes helyiség ugyanígy saját programot kaphat (a helyiség oldalán); ha eddig a házat követte,
  saját időzítésűvé válik, a ház céljaiból (plusz az eltéréséből) indulva. A jelenlét (távol, szabadság), a preset és a
  kézzel állított cél továbbra is felülírja a programot.
- **Presetek:** *Otthon*, *Alvás*, *Távol*, *Szabadság* (és ahol van, *Komfort* / *Eco*) a termosztáton; a kézzel
  állított cél a következő ütemezett váltásig tart.
- **Miért (nem) fűt?** A *Döntés* szenzor egy mondatban megmondja (pl. „Nem fűt: a ház elérte a célt”); minden
  felhasználó látja, ezért érdemes dashboardra tenni. A **HC info** panel (rendszergazdáknak) a teljes képet mutatja.

### HC info panel

Oldalsávi panel, **HC info** (csak adminoknak, csak olvas): egy példány minden adata. A fűtési rendszere a típusa
szerint lerajzolva (kazán, hőszivattyú, távfűtési hőközpont, pellet, elektromos, hőtároló, klíma; radiátor,
szelepfej, padló, fan-coil; központi kazán a zónáival, puffertartály), minden elem mellett a saját adataival; a rajz
mellett a döntés, presetek és célok, a bemeneti és kimeneti eszközök élő állapottal, a bemenetek, amikre döntött (a
mérés korával), minden belső érték, a kazán állapota, helyiségek és szelepfejek, minden beállítás és a napló. Hogy melyik
adat melyik elemnél jelenik meg, azt egyetlen **adat-mátrix** adja meg (`hc-info-panel.js`, `INFO`: elem, felirat,
érték, és a címkék, hogy milyen rendszernél érvényes); a panel a mátrixot is kilistázza. Az oldalsávból vagy
`/hc-info?entity=climate.x` címmel nyílik – a [HC Dial Card](https://github.com/Gyuszko55/hc-dial-card) (1.14+)
„i” ikonja így nyitja meg.

**A házrajz.** Az egyzónás és a zóna-példány a házaként jelenik meg, képeskönyv-stílusú metszetben: a
hőforrás a kazánházban (kazán a lángjával, hőszivattyú, távhő, pellet, elektromos, klíma, hőtároló) előremenő és
visszatérő csövekkel minden helyiségbe, a helyiségek hőmérő-kijelzővel (mért → cél, ≈ ha a helyiség a ház célját követi),
radiátor, padlófűtés vagy egység, szelepfejek (fej mérése → fej célja), nyitott ablak, helyiségenkénti jelenlét, a vezető
helyiség (★), a kinti hőmérséklet és 24 órás átlaga, a háztartás jelenléte, nappal / éjszaka a nap szerint, és a
`heat_energy_entity` mérő mai gáza (m³) vagy hőenergiája (kWh) helyi éjféltől (recorder-statisztika, különben az
állapottörténet; 5 percenként olvasva). A helyiségek a gazda helyiséglistájából jönnek, **annak sorrendjében**:
alsó sor először, a kazánház mellett, balról jobbra, aztán felfelé; ha a területekhez Home Assistant-szintek tartoznak,
a szintek adják az emeleteket. A sorrend a beállításokban (Helyiségek → a helyiség lenyílója → helye a házrajzon) vagy a
varázsló Helyiségek kártyáján a ↑ ↓ gombokkal módosítható. Utánuk jönnek a más felsorolt szenzorral (ablaknyitás-hőmérő,
külön zóna) rendelkező helyiségek. Bármelyik elemre kattintva a panel az adatkártyájához görget (kint, HC vezérlő,
vezető helyiség, hőforrás / gáz); helyiségre vagy szelepfejre a helyiség saját kártyája nyílik. Világos / sötét a Home
Assistant téma szerint, telefonon is elfér, „mozgás csökkentése” mellett nem mozog. A központi és a puffer-példány
megtartja a vonalas rajzot.

**Fűtési rendszerek a rajzon.** Minden hőforrás úgy jelenik meg, ahogy épül: a **pelletkazán** pirosan,
tűzajtóval, mellette a pellettároló (töltöttsége a `fuel_level_entity` szerint) és az adagolócsiga; a **hőszivattyú**
beltéri egységgel, puffertartállyal és – padlókörökkel – osztó-gyűjtővel, kint a kültéri egység a felvett
teljesítménnyel; az **elektromos padlófűtés** (elektromos fűtő padlós rendszeren) a padlókba fektetett fűtőkábelként,
egy kis villamos helyiség elosztójából és termosztátjából táplálva; a **hőtárolós kályhák** minden helyiségben, az
elosztóból és a vezérelt áram mérőórájáról bekötve. **A távfűtés lakás egy társasházban**, nem önálló ház: nincs tető és
kert, fölötte és alatta a szomszéd lakások, a falban a ház felszálló vezetékei. A bekötés a beállításokban adható meg
(eszközök → *Távhő bekötése*): **lakásállomás** hőcserélővel és hőmennyiségmérővel, vagy **radiátorok a felszállón** –
elzárók és a lakás hőmennyiségmérője az előszobában, minden radiátoron költségosztó.

**Pufferes rendszer a rajzon.** Puffertartályos, keverőkörös, hőszivattyú-koordinációs házban ezek a
kazánházban jelennek meg, sosem helyiségként: a tartály a rétegeivel, töltöttségével és tárolt kWh-jával, minden
keverőkör keverőszelepként az előremenő céljával, a hőszivattyú kültéri egysége a tartály csőkígyójára kötve, fa jel
esetén a fatüzelésű kazán. A helyiségi zónák csak a helyiségüket hozzák (a példány nevével); a radiátoros és a
padlófűtési körben is szereplő zóna egy helyiség mindkét hőleadóval.

**Áttekintés, rendszerrajz, fűtési görbe.** Több példányból álló háznál a HC info panelen három nézet van: a
rajz, az *Áttekintés* (hőforrások, puffer, keverőkörök, helyiségek, vezérlési módok, figyelmeztetések és hogy miért kér
hőt a rendszer, egy oldalon) és a *Rendszerrajz*, amely a példányok kapcsolataiból épül (hőszivattyú → csőkígyó,
fatüzelésű kazán, puffer-rétegek, keverőszelepek az előremenő céllal, körönként a helyiségek). A keverőkör adatlapján
grafikonon látszik a fűtési görbe, a beállítási űrlapon pedig táblázatban, amelyet a *Csak előnézet* mentés nélkül
újraszámol.

**Pufferes beállítás és fatüzelés hőmérőből.** A HC setup panelen külön *Pufferes rendszer* útvonal van: a
puffert, a csőkígyós hőszivattyút, a fatüzelést, a radiátoros / padlófűtési kört és a helyiségeket (a két körön lévő
helyiség egy zóna) egyszer kell leírni, a HC létrehozza és összeköti a helyiségzónákat, a puffert, a köröket és a
hőszivattyú-koordinációt, árnyék módban. A fatüzelés közvetlen jel nélkül a kazán hőmérőjéből is felismerhető, két
küszöbbel és megerősítési idővel (`wood_temp_entity`).

**A keverőkör célja és a szivattyú-engedély két külön érték.** TPI/PWM-szünetben a kör előremenő célja az
időjárásgörbén marad, a kör zónáinak legmagasabb céljával számolva; már nem esik a 20 °C-os alap helyiség-hőfokra.
Hogy keringjen-e a víz, azt a kör hőigénye mondja meg (*Kör tartós igény* `binary_sensor`, és `pump_enable` a cél
érzékelőjén): a PLC erre állítsa le a kör szivattyúját, és a keverőszelepet csak futó szivattyúnál mozgassa. A régi
működés a *Szünetben is a zónák céljával számol* kapcsoló kikapcsolásával kérhető. A puffer, a keverőkörei és a
hőszivattyú-koordináció a kapcsolataik alapján egy házba kerülnek (a beállításaikban is van ház-mező), a
hőforrás-figyelés pedig csak akkor mond *nincs adat*-ot, ha egy beállított teljesítménymérő vagy lángjel kiesett.

**Kazánházi rendszerrajz.** A pufferes rendszer kazánházi áttekintőként rajzolódik: kint a hőszivattyú a
puffer csőkígyóján, a fatüzelésű kazán, a puffer rétegei és hőmérői, külön előremenő és visszatérő vezeték, körönként
keringető szivattyú és keverőszelep, a helyiségek ikonokkal, jelmagyarázat. Választható, csak megjelenített adatok: a
HMV-tároló szivattyúja, hőmérője és villanyfűtése (a puffer beállításaiban), valamint a PLC által jelzett
keringetőszivattyú és mért előremenő (a keverőkör beállításaiban).

**Puffer-korlát, kerekített hőszivattyú-cél, célgrafikon.** A pufferre kötött keverőkör (a beállításaiban bekapcsolva; alapból ki) a keverőnek legfeljebb
a puffer teteje − ráhagyás értéket adja ki (hűlő puffernél azonnal lejjebb, melegedéskor fokozatosan vissza), a
hőszivattyú-koordináció viszont továbbra is a korlát nélküli igényt kapja; a hiányzó hőmérséklet látszik. A
hőszivattyúnak kiírt cél 0,5 °C-ra vagy egész fokra felfelé kerekíthető. A HC info panel 24 órás grafikonon mutatja a
hőszivattyú nyers, kiadott, kiküldött és visszajelzett célját, valamint a mért vizet. Háznév a puffer, a keverőkör és a
hőszivattyú beállításaiban is megadható.

**Felügyelet.** A tartós hőforrás-hiba (nem gyújt be, taktol, fűtési hiba …) magától megjelenik a Home
Assistant *Javítások* között. Telefonos értesítéshez importáld a blueprintet: [HC – értesítés hiba esetén](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FGyuszko55%2Fhc-thermostat%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fhc_thermostat%2Fhc_problem_notify.yaml).
Hibajelentéshez a példány ⋮ menüjéből diagnosztika tölthető le. A leggyakoribb módosításnak – célok és az éjszaka
ideje – saját rövid menüpontja van: *Célok és időzítés*.

**Igény szerinti puffertöltés.** A klasszikus szabály (indul, ha a puffer teteje a körök igénye alá esik,
vagy a töltöttség a küszöb alá) mellett a hőszivattyú-koordináció egy igény szerinti szabályt is számol: akkor indít,
amikor a tetőnek még van állítható tartaléka az igény fölött, és csak akkor áll le, ha egy alsóbb réteg is eléri az
igény + leállítási tartalékot (legfeljebb amit a csőkígyó el tud érni). Előbb is indít, ha a puffer egyenletesen hűl,
és ezzel az ütemmel a tartalék a hőszivattyú előfutási idején belül (alapból 60 perc) elfogyna – ennyi idő kell, mire
a csőkígyó hője felér. A kettő egymás mellett látszik; egy beállítás dönti el, melyik vezérel (alapból a klasszikus).

## Hőforrások és rendszerek

### Hőszivattyú

- **On-off, hosszú futással** (`onoff` vezérlés): a hőszivattyú termosztát-bemenetét a cél alatt bekapcsolja, a
  cél elérésekor kikapcsolja – nincs szaggatás; a legrövidebb futás és szünet állítható (20 / 10 perc).
- **Leolvasztás és melegvíz-készítés:** választható jelzők (bináris szenzor, kapcsoló vagy üzemmód-szenzor). Amíg
  a hőszivattyú leolvaszt vagy melegvizet készít, a hibafigyelés vár, és az egészségfigyelés nem riaszt.   üzemmód-szenzornál a beállítások (*Eszközök*) felkínálják az értékeit – kiválasztod, melyik jelent leolvasztást /
  melegvizet (`hp_busy_states`), a beépített `on`, `defrost`, `dhw`, `hot_water`, `hmv` … mellett.

### Moduláló kazán zónákkal

- Minden zóna-példány közzéteszi, mekkora előremenőt kér a saját görbéje (`flow_request`: padlózóna lapos és
  alacsony, radiátoros zóna meredekebb, plusz korrekció, amíg a helyiség a cél alatt van).
- A központi példány a kazán futása alatt a **nyitott, igénylő zónák legnagyobb kérését** írja egy előremenő-alapjel
  entitásba (number / input_number, nem kötelező); a többi zóna a szelepével fojt. Ha egy zóna sem kér értéket,
  `central_flow_default`; határok: `central_flow_min` / `central_flow_max`.
- Radiátorral közös vízről táplált padlókörhöz továbbra is kell saját keverőszelep – a padlóhőfok-limit marad.

### Elektromos padlófűtés, padlóhőfok-limit, célhő forrás

- **Elektromos padlófűtés** (fűtőszőnyeg vagy fűtőkábel a padló alatt): ajánlott kombináció, TPI vagy PID + PWM a
  relén, alapból 30 perces ciklussal és 5 perces minimummal.
- **Padlóhőfok-limit:** padlószenzor és maximum (elektromos padlónál alapból 27 °C). E fölött a relé azonnal
  kikapcsol, bármit mond a szabályozó, és 1 °C-kal alatta kapcsol vissza. Elektromos padlónál a padlószenzor
  kötelező: friss érték nélkül nem fűt. Vizes padlónál a limit választható.
- **Kiesett benti hőmérő:** elektromos fűtő (és elektromos padló) vakon nem fűt (0 %, a kazán 35 %-os tartaléka
  helyett); a padlószenzor ilyenkor is véd a fagy ellen.
- **Célhő forrása:** fali termosztát (vagy number), amelynek a célját a példány kézi célként átveszi a következő
  ütemezett váltásig – így több zóna is követhet egy tekerőt. Amit egy HC-példány maga írt oda, azt nem veszi át.

### Elektromos zónák terheléskorlátja

- Több elektromos zóna (relé vagy okosdugalj, TPI / PID) osztozhat egy teljesítménykereten, pl. a főbiztosítékon:
  minden zónán add meg a fűtőtest teljesítményét és ugyanazt a `load_limit_kw` korlátot. Egy zóna csak akkor
  kapcsol be, ha a teljesítménye belefér.
- Az elutasított zóna vár (érkezési sorrendben), és a PWM-ciklusa akkor indul, amikor sorra kerül – a teljes
  fűtési idejét megkapja, a zónák pedig elcsúsztatva fűtenek, nem egyszerre kapcsolnak be. Amelyik szünet
  nélkül fűt, a következő ciklusa elején átadja a helyét a várakozónak. A kikapcsolást semmi nem tartja vissza; a
  fagyvédelemre is vonatkozik a korlát (a biztosíték fizikai).
- Csak az éles példányok számítanak; a döntés szövege kiírja, ha egy zóna a sorára vár.

### Hőtárolós kályha és vezérelt áram

- Új hőforrás a **hőtárolós kályha** (helyiségben lévő egység, `storage` vezérlés): a vezérelt áramos ablakban
  (alapból 22:00–06:00) annyit tölt, amennyit a kinti napi átlag kér ((cél − kint) / (cél − méretezési hőfok), plusz
  a felhasználó korrekciója; kinti mérés nélkül teljesen), és a töltést az ablak végére időzíti. A töltés kezdetekor
  az arány rögzül. Fagyveszélynél teljesen tölt, ha van áram.
- Nem kötelező kisütő ventilátor / csappantyú: bekapcsol, ha a helyiség 0,3 °C-kal a cél alatt van, kikapcsol a célnál;
  nyitott ablaknál, szezonon kívül és kikapcsolt állapotban ki.
- **Vezérelt áram jelzése** (bármely elektromos fűtésnél, nem kötelező): amíg nincs áram, semmit nem kapcsol, a
  szabályozó nem gyűjt fölösleges igényt, és a döntés szövege megmondja, miért.
- **Áramjel mellett** a hőtárolós kályha a ténylegesen töltött órákat számolja, és az ablakon belül minden
  áramos blokkot kihasznál, amíg a kiszámolt óraszám össze nem jön (a vezérelt áram több blokkban jön; az ablak
  végére időzített töltés egy kieső blokkal elveszne). Áramjel nélkül marad az ablak végére időzítés.

### Távfűtés és fan-coil

- **Távfűtés** (új hőforrás): lakásonkénti zónaszelep TPI-vel / PID-del, hosszú, nyugodt ciklussal (30 perc, legalább
  10 perc nyitva), vagy szelepfejek külső termosztát módban. Nem kötelező **visszatérő-korlát**: visszatérő-szenzorral
  és `return_max` beállítással a szelep zárva marad, amíg a visszatérő víz ilyen meleg (3 °C hiszterézis).
- **Csak szelepfejek** (távfűtés radiátorokkal, zónaszelep és kazán nélkül – társasházi lakás): a HC nem kapcsol
  semmit. A helyiségek fejei a helyiség célját kapják (menetrend, eltérés vagy saját program, jelenlét, ablak), és ahol
  a fej külső hőmérsékletet fogad (SONOFF TRVZB Zigbee2MQTT-n: `external_temperature_input`, a
  `temperature_sensor_select` = `remote_temperature`), a HC beírja a helyiség hőmérőjét, és a fejet erre állítja. Ha a
  helyiség hőmérője kiesik és a fej `remote_source_offline`-ra vált, a HC a fej saját mérésén tanult eltérésre áll
  vissza (az első 30 percben tanul, csak utána vált). A kikapcsolt termosztát vagy a nyári üzem minden fejet
  fagyvédelmi célra állít, a vezető helyiség nyitott ablaka az ő fejeit. A varázsló ennél a vezérlésnél nem kér relét,
  lángjelzőt, gázmérőt.
- **Fan-coil** (új rendszer, bármely vizes hőforrásról – hőszivattyúról is): a vízszelepet TPI / PID kapcsolja, a
  ventilátor (`fan` entitás, százalékban) nyitott szelepnél `fan_min_pct` + az igény szerint forog, zárás után 2 percig
  utánfut; hőcserélő-szenzorral megvárja, amíg az 30 °C-ra melegszik (nem fúj hideget).

### Külső vezérlésű hőtermelő, hasznos fűtés késése

- **Külső vezérlésű hőtermelő** (új hőforrás, „csak zónaszelep”): a hőt egy PLC, a hőszivattyú saját vezérlése vagy egy
  saját logikájú kazán adja, ez indítja a szivattyúkat is; a HC csak a helyiség zónaszelepét kapcsolja (TPI / PID + PWM,
  alapból 30 perces ciklus, padlón hosszú ciklus). Égésjelzőt, áramfelvételt, kazán-állapotot nem kér és nem mutat.
- **Hasznos fűtés késése** (`valve_delay_s`, a felvételkor és a beállításokban, TPI / PID): a termoelektromos szelep kb.
  5 perc alatt nyit, a szivattyút a saját vezérlése pl. 5 perccel az igény után indítja – minden nyitás első 10 perce
  nem fűt. Ha megadod, minden nyitás ennyivel hosszabb, a minimális bekapcsolási idő a hasznos részre vonatkozik, és a
  túl kicsi igény **a következő ciklusokra gyűlik**, amíg megér egy nyitást (igény nélkül törlődik). Szimulációban (15
  perces ciklus, 10 perc holtidő, 24 óra) nélküle a nyitások negyede–fele véget ért, mielőtt hő érkezett volna, vele
  egy sem, és a helyiség kb. kétszer közelebb maradt a céljához.
- **Időzítési javaslat:** szelepkésésnél a panel jelzi, ha a ciklus rövidebb hat késésnyinél, vagy a minimális futás
  kettőnél, és javasol: radiátornál legalább 30, padlónál legalább 60 perces ciklust.
- **Felvétel:** az „Integráció hozzáadása” előbb a varázslót (a panelje rögtön elérhető, példány nélkül is) vagy a kézi
  utat kínálja; a kézi út végén új **Alapbeállítások** lépés: célok, éjszaka, ciklus, minimális be- / kikapcsolási idő,
  hasznos fűtés késése.

### Vezetékes fali termosztát mint igény

- A relés példány (TPI / PID / on-off) az igényt egy potenciálmentes fali termosztáttól is veheti, bináris
  szenzoron, input_booleanen vagy kapcsolón át (`demand_entity`): érintkező be – fűt, ki – nem fűt. A helyiséghőmérő
  ekkor elhagyható.
- A fagyvédelem (a helyiséghőmérő, ennek hiányában a padlószenzor szerint), az újraindítás utáni várakozás, a kikapcsolás,
  a nyitott ablak és a nyári pihenő előbbre való; a padlóhőfok-limit és a padlótemperálás erre is érvényes (a nem kérő
  fali termosztát „célon” számít). Nincs felfűtés és utómelegedés, a szabályozó áll. Ha az érintkező nem elérhető: helyiséghőmérővel
  a példány arról és a saját céljáról szabályoz, amíg az érintkező vissza nem jön; helyiséghőmérő nélkül a
  kiesett hőmérő tartalék üzeme (padlószenzorral a padló szerint).
- Helyiséghőmérő nélkül a padlótemperálás csak az éjszakai abszolút értékkel megy, annak idejében: a „helyiségcél
  + eltérés” a fali termosztát ellen fűtene, annak saját beállítása van.

### Meglévő termosztát-integrációk kezelése

- Külső vezérléssel a HC egy meglévő climate entitást vezérel – Smart Thermostat, Better Thermostat, generic
  thermostat, klíma –, és az integráció közben önállóan is működhet. A HC felismeri az integrációt
  (`managed_platform`, `managed_adapter`), és a célt az entitás saját lépésközére és tartományára igazítja.
- A kezelt termosztáton közvetlenül állított célt a HC kézi célként átveszi a következő ütemezett váltásig; ha valaki
  kikapcsolja, a HC kikapcsolva hagyja (csak a fagyvédelem fűt), amíg valaki vissza nem kapcsolja. Opció:
  `adopt_manual` (be). Amit a HC maga ír, azt sosem veszi át. Klíma-vezérlésnél nem él.
- A „HC felügyelet szünetel” kapcsoló (külső és klíma-vezérlés) minden írást leállít a kezelt termosztát felé; a HC
  közben is dönt és naplóz. Kikapcsolásakor a termosztát aktuális célja kézi cél lesz – nincs visszaugrás.
- Lángérzékelő nélkül a kezelt termosztát `hvac_action` jelzése mutatja, fűt-e valóban.
- Az integráció saját presetjeit a HC még nem használja (célhőt küld); ez egy későbbi szakaszban jön. Relés
  (TPI, PID, on-off vezérlés) példányoknak nincs szünet-kapcsolójuk.

## Helyiségek, jelenlét, szelepfejek

### Egy kazán helyiségei

„Egy helyiség, egy hőmérő (vagy hőmérő-csoport), egy vagy több szelepfej vagy nincs – viszont egy kazán.” Az egyzónás
példány (TPI / PID) a ház: a kazánt a **vezető helyiség** vezérli (szabályozó szelepfej nélküli helyiség, általában a nappali;
a hőmérője a ház hőmérője, `indoor_entity`). A ház célja a menetrend, a presetek és a háztartás jelenléte, mint eddig.
Minden más helyiség **saját HC termosztátot** kap (`climate.<helyiség>_hc`, „<Helyiség> HC” eszköz a helyiség területén, a gazda
példány eszköze alatt):

- **Hőmérők:** egy vagy egy csoport – az elérhetők átlaga, a kiesett kimarad. A vezető helyiség csoportjának átlaga a
  kazánt is vezérli.
- **Szelepfejes helyiség:** a fejekkel szabályoz. Minden fej a helyiség célját kapja, a helyiség hőmérőihez kalibrálva (a fenti
  kalibrálás); egy fej követhet más hőmérőt vagy a sajátját (kalibrálás nélkül); hőmérő nélküli helyiségben a fejek a
  saját mérésük szerint dolgoznak. Opcionális rövid égés-kérés (a meglévő helyiségigény) **helyiségenként, alapból kikapcsolva**,
  és csak amíg a ház nincs a saját célja fölött.
- **Szelepfej nélküli helyiség:** csak a kazánon át fűthető: a termosztátja a ház célját mutatja, a rajta beállított célt
  érthető üzenettel elutasítja, radiátorszelep-tanácsot kap, és a kazánt soha nem vezérli.
- **Csak mért helyiség:** a ház egy helyisége hőmérővel, de ennek a hőforrásnak a fűtőteste nélkül (előtér,
  kamra, vagy egy helyiség, amit egy másik példány fűt): pipáld be a *Nincs fűtőteste ennek a hőforrásnak – csak mérés*
  jelölést. A házrajzon látszik a hőmérsékletével, de nem kap célt, saját termosztátot, radiátorszelep-tanácsot és
  szelepfejet. A vezető helyiség mindig fűtött.
- **A helyiség célja:** *követi* = a ház célja + eltérés (éjszaka, távollét, presetek és a ház kézi célja is), vagy *saját* =
  saját otthon / éjszakai / távolléti hőfok és éjszakai időszak (a háztartás szabadságon: a ház szabadság-célja).
- **Jelenlét helyiségenként (opcionális):** olyan források, amelyek állapota a helyiség területe (telefonos helyiség-követő,
  pl. Bermuda – a terület neve vagy `area_id`-ja; input_select), és mozgás-/jelenlétérzékelők (be = jelen van); a
  források kiválasztásával dől el, kinek a jelenléte számít. Jelen van → a helyiség célja; `absent_min` (15) percig senki →
  cél − `setback` (2 °C), a fagyhatár alá soha; ha a háztartás távol vagy szabadságon van, a háztartás célja számít,
  csökkentés nélkül. Újraindítás-biztos: az ismeretlen forrás a korábbi állapotot tartja, a távollét órája túléli az
  újraindítást, és indulás után 5 percig a „senki” nem indítja el.
- **Kézi cél / preset** (Automatikus, Jelen van, Távol) a helyiség termosztátján a helyiség automatikus céljának következő
  változásáig tart (menetrend, jelenlét, a követett házcél), mint a háznál. A helyiség termosztátja kikapcsolható (a
  fejek a fagyhatárt kapják).

**Hol állítható:** a beállítások **Helyiségek** menüpontjában – (1) kipipálod az otthon azon területeit, amelyek
helyiségek (mindegyik mellett látszik, mi van benne), (2) helyiségenként egy lenyíló: a terület hőmérői, szelepfejei,
jelenlét-forrásai és ablak-/ajtóérzékelői jelölőnégyzetekkel (az új helyiségnél előre bepipálva), felül a vezető helyiség; cél,
jelenlét, égés-kérés és fejenkénti kalibrálás csak a szelepfejes helyiségnél, (3) a saját menetrendek; csak a helyiségeket menti.
A beállító varázsló „Helyiségek” kártyája ugyanígy működik (egy vagy több helyiség, a területek jelölőnégyzetes listája –
magától semmi nincs bepipálva). A szelepfej nélküli helyiség neve **megfigyelt helyiség**.

- **Ablak / ajtó helyiségenként:** szelepfejes helyiségben az érzékelői csak a helyiség saját fejeit zárják le
  (fagyvédelmi cél az ablak-késleltetés után); a vezető és a megfigyelt helyiségben a kazánt állítják le, mint a példány
  ablaklistája.
- **Helyiség-csoportok:** ha egy helyiségben két vagy több hőmérő / jelenlét-forrás / nyitásérzékelő van, a HC saját
  csoport-entitást hoz létre (átlaghőmérséklet, valaki jelen van, bármelyik nyitva) a helyiség eszközén; a helyiséggel
  együtt változik. Egy `rooms` listaként és
`leading_room` kulcsként kerül a példány beállításaiba; mellé a régi kulcsok is (`room_sensors`, `room_trvs`,
`trv_sensors`, `trv_offsets`, `room_trv_demand`), így a kártyák és egy visszaállás is működik.

**Frissítés:** `rooms` nélkül a lista a régi beállításokból áll elő, terület szerint csoportosítva, pontosan a régi
működéssel: minden helyiség a ház célját követi a saját eltérésével, jelenlét nélkül, a fejek megtartják a hőmérőjüket és
amit tanultak, a helyiségigény is marad. Példa: fő hőmérő a nappaliban, konyhai hőmérő konyhai szelepfejjel, hálószobai
hőmérő → Nappali (vezető), Konyha (szelepfejes, kalibrált) és Hálószoba (csak a kazánon át) – két új termosztát:
`climate.konyha_hc` és `climate.haloszoba_hc`.

A HC info a helyiségeket a gazda példány alatt sorolja; a helyiség termosztátja (vagy egy feje) a gazdát nyitja meg helyiség-résszel
(hőmérséklet, cél és indoka, jelenlét, fejek, kalibrálás, tanács). A kerek [HC Dial Card](https://github.com/Gyuszko55/hc-dial-card)
külön HACS frontend-tároló: a kiadott 1.14.0 „i” gombja megnyitja a HC infót; a helyiségekhez kötődő funkciók (a helyiség termosztátjának
„i” gombja a helyiséget mutatja, a szelepfejes helyiség radiátor ikont kap, a szelepfej nélküli helyiség csak olvasható) a
következő kiadásával jönnek. A kártya újabb, tesztelésre szánt példánya e tároló `frontend/` mappájában van.

### Jelenlét helyiségenként

- Minden példánynak saját jelenlét-entitásai vannak (`presence_entities`): személy, bináris érzékelő, input_boolean,
  vagy bármi, ami otthon / on / Otthon, illetve vacation / Szabadság állapotot mond. Ha több van megadva, a példány
  otthon van, amíg bármelyik otthon van; távol, ha egyik sincs; szabadságon, ha valamelyik ezt mondja.
- Így az egész ház követheti a háztartást, egy helyiség pedig egyetlen személyt: ha ő nincs otthon, csak az ő
  helyisége áll a Távol (később Szabadság) célra, a ház többi része ugyanúgy fűt; hazaérve a helyiség visszaáll a saját
  céljára. Ugyanúgy működik, mint a ház szintű jelenlét-szabályozás.
- Példák: nagy családi házban a nem otthon lévő nagyobb gyerek szobája csökkentett fűtésen marad; panzióban,
  szállodában a ki nem adott vendégszoba (vendégszobánként egy input_boolean vagy foglalási érzékelő) csökkentett célon marad, a
  kiadott rendesen fűt.
- A Távol és Szabadság célja és a kézzel választott preset időtartama példányonként állítható.

### Szelepfejes (TRV) helyiségek: saját cél és kalibrálás

- Egyzónás rendszerben minden TRV-s helyiség eltolást kaphat a ház céljához (beállítások, „Szelepfejes (TRV) helyiségek”
  lépés: pl. háló −2 °C, fürdő +1 °C) – így is követi az ütemezést (éjszaka, távollét).
- Kalibrálás (nem kötelező): a fej a forró radiátor mellett mér, ezért korán zár. Ahol a helyiségben saját hőmérő is
  van, a fej − helyiség eltérést lassan követi (30 perces simítás, legfeljebb ±5 °C), és a fejre írt célt ennyivel
  korrigálja. A csak kalibrálásból adódó változást legfeljebb félóránként írja ki.
- Fejenkénti hőmérő: a beállítások („Szelepfejes (TRV) helyiségek” lépés) és a beállító varázsló
  („Szelepfejek (TRV)”) minden fejhez felkínálja „A fej saját hőmérője” (nincs kalibrálás) vagy egy külső hőmérő
  választását – a lista a fej területén lévő hőmérőket mutatja (a fej saját entitásai nélkül; ha ott nincs, az
  összeset). Mentése: `trv_sensors` (fej → szenzor). A korábban mentett példány változatlanul működik, amíg újra
  nem mented (`trv_calibration` be: a fej területének hőmérői). Másik hőmérőnél a tanult eltérés újraindul.
  A HC info és a tárcsás kártya „i” gombja szelepfejről is a gazda példányt nyitja.
- A fejen kézzel átállított cél továbbra is megmarad, amíg a helyiség célja nem változik. A helyiségek szenzor
  `trv_rooms` attribútuma fejenként mutatja a célt, az eltolást és a kalibrálást.

### Kiesett helyiséghőmérő: a padló meleg marad

- Padlófűtés padlószenzorral (TPI / PID / on-off): ha a helyiséghőmérő kiesik, a padlót a padlószenzor szerint a
  helyiség célja + a temperálás eltérése (vagy az éjszakai érték) hőfokán tartja – a kazán vak 35 %-a, illetve
  elektromos padlónál a fűtés nélküli állapot helyett. Alapból be van kapcsolva (`floor_fallback`).
- A fagyvédelem előbbre való, a padlóhőfok-limit mindig érvényes, nyitott ablaknál szünetel; padlóhőfok nélkül
  minden a régi módon működik.

## Padlófűtés és -hűtés

### Padlótemperálás

- Választható kényelmi funkció padlófűtéshez (vizes vagy elektromos, TPI / PID / on-off, padlószenzorral): amíg a
  helyiség elég meleg, a padlót a helyiség célja + 2 °C-on tartja (`floor_temper_offset`), így a padló meleg marad.
- Megadható éjszakai érték (`floor_temper_night`): éjjel és alvás presetben ez a padló célja.
- A padló célja − 0,3 °C alatt indul, a célnál áll le; a minimális futás és szünet érvényes. Leáll, ha a helyiség 0,5 °C-kal
  a célja fölé ér (`floor_temper_room_margin`; nagyobb érték melegebb padlót, de a helyiségben nagyobb ingadozást és
  többletfogyasztást ad), és nyitott ablaknál, kikapcsolva, nyáron nem fűt. A padlóhőfok-limit
  mindig előbbre való, és a tanulás ezekből a futásokból nem tanul.

### Padlóhőfok-limit a burkolat és a szenzor helye szerint

- Add meg a burkolatot (csempe, laminált, fa/parketta, vinyl, szőnyeg) és hogy hol ül a padlószenzor (a burkolat
  alatt, az esztrichben a csövek között, cső fölött), a limitet hagyd 0-n: a limit táblázatból jön – a burkolat alatt
  csempénél 29 °C, a többinél 27 °C, az esztrichben 29 / 33 / 31 (vinyl) °C, cső fölött 36 °C (a mélyebben ülő szenzor
  melegebbet mér). Elektromos padlónál mindig a burkolat alatti érték; burkolat nélkül elektromos padlónál 27 °C, vizes padlónál 29 °C.
  Ezek kiinduló értékek, a mélyebb helyek (esztrich, cső fölött) határai becslések: nem garantálják, hogy a felszín
  27 °C alatt marad. Fa, parketta és laminált burkolatnál burkolat alatti (felszíni) szenzort ajánlunk. A beírt
  limit mindig előbbre való.
- A burkolatból jön a temperálás eltérése is: csempénél 2 °C, a többinél 3 °C.
- Az új űrlapok 0-val (burkolat szerint) indulnak; a már elmentett limit marad. A HC info panel mutatja az érvényes
  limitet és hogy honnan jön.

### Padlóhűtés harmatpont-védelemmel

- Padlós, megfordítható hőszivattyú (görbe vagy ki/be vezérlés) nyáron, amikor a fűtési szezon szünetel, hűteni is
  tud: `target_cool` + 0,5 °C fölött indul, és amíg a helyiség `target_cool` − 0,5 °C alá nem hűl.
- A harmatpontot a benti hőfokból és a páratartalomból számolja (páratartalom-szenzor kötelező). A víz és a padló
  mindig a harmatpont + `dew_margin` (2 °C) fölött marad: görbe módban a hűtési előremenőt (`cool_flow`, 18 °C)
  ennyire megemeli, és ha még a `cool_flow_max` (22 °C) sem lenne biztonságos, leáll („túl párás”). Padlószenzorral a
  biztonságos határon vagy a `floor_min_cool` (19 °C) értéken szünetel; ki/be vezérlésnél a padlószenzor kötelező.
- Nem kötelező: a hőszivattyú hűtés-kapcsolója (nyáron végig be, fűtési szezonban ki) és külön hűtési előremenő-
  alapjel. Leálláskor a legmelegebb értéket írja, sosem a leghidegebbet. A beállításokban kapcsolható be.

## Puffertartály, keverőkörök, hőszivattyú

### Pellet kazán és puffertartály

- **Pellet kazán** (új hőforrás): on-off vezérlés hosszú futásokkal – legalább 45 perc, 20 perc szünet –, mert
  lassan gyújt és ég ki; az állapotfigyelés az áramfelvétele szerint ítél, és kivárja a kiégést.
- **Puffertartály** (új szerep, a központi kazánhoz hasonlóan): a tartály felső (és ha van, alsó) hőmérője szerint
  kapcsolja a hőforrást: a töltés akkor indul, ha a teteje `buffer_on` (45 °C) vagy hidegebb, és mindig addig tart,
  amíg az alja el nem éri a `buffer_off` (65 °C) értéket; új töltés 20 perc szünet után. Megadott zónáknál csak
  zónaigénynél indul; fagyveszélynél (teteje ≤ 8 °C) mindenképp tölt; felső hőmérő nélkül nem tölt. A körök a
  tartályból rendes HC-zónaként fűtenek. Döntés-szenzor és „hőforrás kérés” bináris szenzor.

### Egy ház, több hőforrás

Egy házban több hőforrás is lehet – fali kazán, pelletkazán, hőszivattyú, klíma, olajradiátor –, mindegyik a saját
HC-példányával. A HC info **egy házként** mutatja őket: a gazda rajzán minden helyiséggel és minden hőforrással,
példányonként külön egyhelyiséges ház helyett.

- **Mely példányok egy ház:** automatikusan az az egyhelyiséges példány (klíma, fűtőtest), amelynek a helyisége egy
  másik, több helyiséges példány helyiségének vagy csatlakozó terének a területén van – de nem annak vezető
  helyiségében: két, ugyanarról a helyiségről vezérelt példány egymás alternatívája (árnyék próba), nem két része. Az
  azonos **otthon-nevű** példányok is egy házat alkotnak (a legtöbb helyiségű rajzol). Központi kazán vagy puffertartály
  oda kerül, ahol a zónái többsége van. A beállításokban (*Csatlakozó tér, közös ház*) a **Melyik ház része** mezőben
  kézzel is választható: automatikus, önálló ház, vagy egy másik példány háza.
- **A rajz:** a tagok helyiségei a gazdáéhoz csatlakoznak (amit csak egy tag ismer, új helyiségként kerül be); abban a
  helyiségben, amit a gazda nem fűt (csak mért, vagy a csatlakozó tere), a tag fűtőteste látszik – pl. a terasz klímája
  a céljával, a HC által küldött beállítással és az egység saját mérésével; abban, amit a gazda is fűt, a tag eszköze a
  sajátja mellett (olajradiátor a radiátor mellett, klíma fent a falon). A vizet fűtő hőforrások egymás mellett állnak a
  gépházban; a hőszivattyú és a klíma kültéri egységei egy oldalon egymás fölött. Egy tag részére kattintva az a példány
  nyílik meg.
- **A választóban** a tag a háza alatt szerepel (*Klíma · Kazán házában*); a tag oldala az egész házat mutatja a saját
  helyiségével kiemelve, a *Hőforrások a házban* szakasz pedig minden hőforrást felsorol a döntésével és a mérésével.
- Csak a megjelenítést érinti: minden példány a saját hőforrását szabályozza, mint eddig. Két, **ugyanazon** a
  vízkörön lévő hőforrás közti átváltást (hőszivattyú tartalék kazánnal) ez nem kapcsolja; a meglévő *más hőforrás*
  (olcsóbb forrás, `yield_margin`) továbbra is visszaléptetheti a kazánt, amíg a klíma fűt.
- **A klíma segíti a házat** (`assist_climate`): ha a ház HC-ja szerint a klíma az olcsóbb hőforrás, és nyitva a
  köztük lévő ajtó, a klíma a ház célja felé fűt a saját helyiségéé helyett. Csak akkor kezdi, ha az ajtó
  `assist_delay_s` (10 perc) óta folyamatosan nyitva van – egy gyors ki-be járás nem emeli –, és közben a klímára írt cél
  legfeljebb `assist_max_setpoint` (22 °C); 0 bármelyiket kikapcsolja.

### Rétegzett puffer és keverőkörök

Olyan házhoz, ahol egy vagy több hőforrás (fatüzelésű kazán, csőkígyón át töltő hőszivattyú) közös puffertartályt tölt,
és abból külön körök fűtenek (radiátor, padló), mindegyik saját szivattyúval és keverőszeleppel. A helyiségek
megtartják a saját HC-zónáikat; a PLC / keverő vezérli tovább a szelepet, a szivattyút és a védelmeket. **Árnyék módban
semmit nem ír** – kiszámol és megmutat; az írás lent.

- **Rétegzett puffertartály:** legfeljebb négy hőmérő (felső, felső-középső, alsó-középső, alsó) a térfogatarányával
  (0 = egyenlő), a térfogat és egy alaphőfok (25 °C) alapján *Puffer tárolt hő* (kWh), *Puffer töltöttség* (%) és
  *Puffer trend* (töltődik / merül / állandó). A tartály meglévő töltöttség-szenzorát változtatás nélkül átveszi (a
  `method` attribútum jelzi). Négy pontból ez becslés, gyors töltés vagy merülés közben különösen.
- **Keverőkör** (szerep: *Keverőkör pufferből*): a zónái, a kinti hőmérő, a puffer-példány, amelyből fűt, és a kör
  típusa – radiátoros (meredekség 1,2, 30–55 °C) vagy padlófűtés (meredekség 0,5, 22–36 °C). A nyers előremenő cél a
  görbe a **tartós** igényű zónák legmagasabb céljánál (az utóbbi 30 percben kértek, így egy TPI-szünet nem ejti ki)
  plusz helyiség-korrekció (kp × a legnagyobb hiány, legfeljebb 3 °C hiányig), a kör határain belül. A padló maximuma a
  víz előremenő-korlátja, nem a padló felületi korlátja.
- **Előremenő a helyiségek tartós elmaradásából** (`circuit_room_trim`, alapból ki): óránként mérlegel. Ha a kör
  zónáinak többsége szinte végig fűtött és mégis a cél alatt maradt, az előremenő 0,5 °C-ot emelkedik; ha mind
  könnyen tartotta a célját (az idő kevesebb mint felében fűtve), csökken; legfeljebb ±5 °C, újraindítás után is
  megmarad. Így a hőleadást elsősorban a víz hőmérséklete szabályozza, nem a relék gyakori kapcsolása. A túl hideg
  puffer (korlátoz) nem számít elmaradásnak.
- **A kiadott cél ritkán változik:** legalább 1,5 °C eltérés, 10 percig tartósan, az előző módosítás után legalább 25
  perccel, egy lépésben legfeljebb 3 °C emelés (csökkentés korlát nélkül); a lecsökkentett maximum azonnal érvényes;
  2 percig tartó 5 °C-os eltérés nem vár. Kinti mérés nélkül a cél marad. Minden érték állítható. A *Kör előremenő
  cél* a kiadott értéket mutatja, mellette a nyers célt, a visszatartás okát és a legkorábbi következő módosítást.
- **A puffer egy körnek:** a teteje eléri-e a cél + 2 °C-ot, és mennyi a használható hő az elég meleg rétegekben a
  kör visszatérőjéig.
- **Kör felügyelete** (`circuit_watch`, alapból be; csak figyel, semmit nem ír, a PLC-be nem avatkozik bele): ha a
  szivattyú és/vagy az előremenő hőmérő meg van adva, a HC követi a *hőigény → elindul a szivattyú → megmozdul az
  előremenő* láncot. Normális, ha a szivattyú `circuit_watch_pump_s` (10 perc – a PLC 5 perces indulási késleltetése
  belefér) alatt indul, és az előremenő a szivattyú indulásától `circuit_watch_flow_s` (15 perc) alatt
  `circuit_watch_flow_c`-vel (1 °C) elmozdul vagy 2 °C-on belül megközelíti a célt. Ha egy lépés tovább elmarad, az
  bejegyzés a Javítások között (magától eltűnik), sárga a rendszerrajzon és figyelmeztetés az áttekintésben. Ha a
  szivattyú állapota nem ismert, abból nem lesz jelzés.
- A célok kiírása a PLC-be: lent (felügyelt próba, egy író); a hőszivattyú-koordináció ezt követi.

### Hőszivattyú-koordináció pufferhez

Fatüzelésű kazán mellett a puffert (csőkígyón át vagy közvetlenül) töltő hőszivattyúhoz. A *Hőszivattyú-koordináció
pufferhez* szerep a puffer-példányt, a keverőköreit és a kinti hőmérsékletet olvassa (ha megadod: fut-e a hőszivattyú,
és a fatüzelés jelét), és – semmit nem írva – három külön dolgot mutat: a hőigényt, az ON/OFF kérést és az előremenő
célt.

- **Cél:** a körök igénye + csőkígyó-tartalék (5 °C) + a korrekciód (−8…+8 °C, a *Hőszivattyú korrekció* number –
  olyan géphez, amely 42 °C-os parancsra 38 °C-ot ad), a határokon belül; ha nincs mit termelni, a legalacsonyabb.
  Ritkán változik (2 °C, 10 perc, 45 perc, egyszerre legfeljebb +3 °C).
- **Új töltés teljes céllal** (`hp_charge_jump`, alapból be): töltés indulásakor, és ha töltés közben a kompresszor a
  cél alatt leáll, a kiadott cél azonnal a számított értékre ugrik; a ritkítás csak a töltésen belüli változásokat
  simítja. A „fut” jel teljesítménymérőnél `hp_running_w` (100 W) felett számít működésnek.
- **Fűt, készenlét vagy nem ismert:** teljesítménymérőnél `hp_standby_w` (10 W) és `hp_running_w` között a gép
  készenlétben van (fagyvédelem vagy keringetés miatt bekapcsolva, a kompresszor áll); a 15 perce nem frissült „fut”
  mérés nem ismert. A rendszerrajz, a panel és a koordináció ugyanazt az állapotot használja (készenlét = nem fut).
- **A hőszivattyú saját célja a rendszerrajzon:** *beállítva* (amit a gép visszajelez), *HC kéri* (kiküldött, árnyékban
  a kiadott) és *számolt*; írás közben a 10 percig tartó, 0,4 °C-nál nagyobb eltérés sárga, és figyelmeztetés – a HC
  és a gép nem ugyanazt a célt használja.
- **Fa elsőbbsége:** a fatüzelés jele, vagy a puffer melegedése, miközben tudjuk, hogy a hőszivattyú áll, visszatartja
  az indítást. A `hp_wood_first` mellett (alapból be): alacsony töltöttségnél sem indít, és a már futó felfűtés is leáll;
  csak a puffer fagyhatára előzi meg, a hidegben-ON és a tartalék ON a legalacsonyabb céllal marad.
- **Hidegben-ON** (alapból ki, csak vízzel töltött monoblokkhoz): +5 °C alatt ON igény nélkül is, tartós +7 °C után
  oldódik; ez nyer a **hosszú igénymentes leállítással** szemben (24 óra igény nélkül OFF, ha *igény nélkül is ON*;
  „igény nélkül” = se kör- / helyiségigény, se puffer-hőigény, a töltést is beleértve).
  Nem helyettesíti a gép saját fagyvédelmét, a gyártói előírásokat és a független biztonsági megoldást.
- **Automatikus nyári/téli üzem** (`hp_auto_summer`, alapból ki): 24 óra helyiség-igény nélkül (körök /
  zónák – nem a puffer) a puffert már nem tartja melegen (nincs alacsony töltöttség miatti indítás, nincs készenlét,
  legalacsonyabb cél); a fagyhatár továbbra is fűt, a hidegben-ON ettől független. Vissza téli üzembe, ha a körök
  igénye 30 percig megszakítás nélkül tart, és a végén egy helyiség még kér. *Nyári üzem* és opcionális heti
  *Megjáratás esedékes* bináris szenzor (és kimenet) a PLC-nek – a szivattyúkat, szelepeket a PLC járatja meg.
- Kiesett bemenetnél a legutóbbi kérés marad. A gép / a PLC felé írás: lent.
- **Hőmennyiségmérés és COP** (0.75.0, opcionális, *Hőmennyiségmérés és COP* szakasz): a víz előremenő (Outlet) és
  visszatérő (Inlet) hőmérsékletéből és a vízáramból (l/perc) a HC méri, mennyi hőt visz el a vízkör a hőszivattyúból:
  kW = l/perc × ΔT × 0,06977 (tiszta víz; glikolos keverékhez szorzó). Szenzorok: *hőteljesítmény* (kW), *termelt
  hőenergia* (kWh, folyamatosan növekvő – ez kell az Energia irányítópultra), *hőenergia ma* (ennek része, a kettőt ne
  add össze), *aktuális COP* és *COP ma*. Energiát csak két, legfeljebb 2 percre lévő érvényes mérés között ad
  (trapézszabály): hiányzó, állott (5 perc), lehetetlen mérés, újraindítás vagy álló víz semmit nem ad, nem pótol;
  negatív ΔT = 0 kW. **Kompresszorüzemi szűrés (külön DEV-javítás):** a termelt hőteljesítményt és kWh-t
  csak igazolt kompresszorüzemben számlálja, hogy a kompresszor nélküli fagyvédelmi keringetés
  és az egész fokos hőmérők miatti látszólagos ΔT ne növelje a termelt energiát.
  Elsődleges a külön megadható **kompresszorfrekvencia (Hz)**: friss >0 Hz esetén termelés, 0 Hz esetén
  nincs termelés. Üresen a „fut” jel Hz-értékét veszi át, ha létezik; ennek hiányában a
  villamos teljesítménymérő **alapból 200 W-os, külön állítható küszöbét** használja.
  A 200 W kizárólag a **mérőre** hat, nem változtatja meg a hőszivattyú vezérlésének futásküszöbét.
  Ha **sem wattmérő, sem Hz-jel nincs megadva** (például csak be/ki „fut” jel van), a hőmérés a
  korábbiak szerint megy tovább, de a termelés „nem igazolt” jelzést kap (`heat_confirmed: false`), COP nélkül.
  Megadott, de hiányzó vagy 5 percnél régebbi üzemjel mellett szünetel a termelt kWh számlálása;
  álló és járó kompresszor közötti átmenetben nincs fél mintaintervallumnyi fantomenergia.
  A nyers vízoldali teljesítmény külön diagnosztikai adatként megmarad.
  A COP a „fut” jel teljesítménymérését (vagy egy külön wattmérőt) használja; az aktuális COP az
  aktív futás utolsó 10 percének hőenergiája osztva a villamos energiájával (egy futásban 5 perc után), ha nem fűt
  (nincs áramlás, készenlét, leolvasztás, állott mérő), nem elérhető – soha nem 0 vagy végtelen; a *COP ma* a nap
  hőenergiája osztva a nap villamos energiájával ugyanazokon az időszakokon, a lefedettséggel. Egész fokos hőmérőkkel
  3 °C ΔT ± 33 % – a panel kiírja. A számláló újraindításon át megmarad; 0-ról csak új példánnyal indul (az összeg a
  Fejlesztői eszközök → Statisztika oldalon javítható). A hőszivattyú-grafikon a COP-ot jobb oldali tengelyen mutatja
  (kikapcsolható).

### A célok kiírása: felügyelt próba, egy író

A *keverőkör* és a *hőszivattyú-koordináció* árnyék módban indul. A beállításaikban (első oldal) az írás
**felügyelt próbára** (a megadott óráig ír, alapból 4, utána magától vissza árnyékba, értesítéssel) vagy **éles**
módra kapcsolható; mindkettőhöz kimeneti entitás és megerősítés kell.

- Amit ír: a kör előremenő célja (PLC number / input_number vagy egy climate célja); a hőszivattyú előremenő célja,
  ON/OFF-ja (switch / input_boolean / climate) és egy nem kötelező hőigény-jel. Mást nem – a keverők, a szivattyúk és
  a védelmek a PLC-nél, a hőszivattyú fagyvédelme a gépnél marad.
- **Egy célnak egy írója:** a HC csak eltérésnél ír; ha más megváltoztatja az értéket, a HC nem ír bele, és értesít,
  amíg az érték újra az övé nem lesz. A PLC-t úgy kell beállítani, hogy a HC regiszterét ne írja maga is.
- **Visszaigazolási türelmi idő** (`write_confirm_s`, 60 mp): a lassú eszköz (pl. Tuya) ennyi idő alatt
  jelezheti vissza a beírt értéket; addig a HC nem ír újra, és a késve érkező vagy régi értéket sem veszi ütközésnek. Ha
  az eszköz nem veszi át az értéket, legfeljebb még 3-szor írja, utána leáll (*nem fogadta el*) és értesít.
- **Felügyelt visszaállítás** (hőszivattyú-koordináció, 0.73.0, alapból ki – *Tartós eltérés visszaállítása ennyi
  perc után*): ha a gép ennyi ideig más célt vagy be/ki állapotot tart, mint amit a HC kér (az appjában átállították,
  vagy kikapcsolás után a saját alapértékével indult, mint egy Tuya gép), a HC újra beírja a sajátját – azt, amit
  éppen kér, így a biztonsági tiltások, a fagyvédelem és a fatüzelés elsőbbsége továbbra is előbb jön –, legfeljebb
  *Visszaállítási próbák* számszor (3), ugyanilyen távolságban; ha egy visszaállítás ennyi ideig kitart, a számlálás
  újraindul. Ha egyik sem segített, bekapcsol a *Hőszivattyú nem követi* hibaszenzor, Javítások-bejegyzés és értesítés
  jön, a rendszerrajz pirosan mutatja, és a HC nem írja tovább azt az értéket, amíg mást nem kér, vagy a gép magától
  vissza nem áll. Ha egy ideig kézzel akarod állítani a gépet, használd az *Írás szüneteltetése* kapcsolót.
  Bekapcsolt visszaállításnál a climate be/ki kimenet üzemmódja is számít (*auto* a *heat* helyett eltérés); az első
  tartós eltérés figyelmeztetés (értesítés, borostyán), a sikertelen visszaállítások hiba (szenzor, Javítások, piros).
- Climate-kimenetre a cél a saját lépésére kerekítve és a min/max között megy; ha egy eszköz nem elérhető
  volt, és az alapértékével jön vissza, a HC újraírja, nem veszi idegen írónak.
- Indulás után 2 percig nem ír; a keep-alive időkorlátos PLC-nek változatlan értéket is újraküld; az *Írás
  szüneteltetve* kapcsoló azonnal leállít minden írást.
- Ha a Home Assistant leáll, nem ír semmit: a PLC saját görbéje és biztonságos tartaléküzeme maradjon meg.

## Ház-modell, mérések, karbantartás

### Ház-modell: hőveszteség, szabad hő, időállandó

- **Hőveszteség-tényező és szabad hő:** egyenes a tanult napokon át (a napi hő a bent − kint átlagos különbség
  függvényében). A meredeksége a **H** hőveszteség-tényező (W/K), a tengelymetszete a **szabad hő** (emberek, gépek,
  nap; kW): a hőigény H × (cél − kint) − szabad hő. Eddig az egyszerű arány a szabad hőt a veszteségbe olvasztotta:
  abban az időben jó volt, amikor tanulta, hidegben viszont nagyjából a felét adta a valós igénynek. Az egyeneshez
  legalább tíz nap kell, legalább 4 K különbséggel; addig az arány marad. *Hőveszteség-tényező* szenzor: forrás
  (`fit`, `manual`, `ratio`), szabad hő, egyensúlyi pont (e fölötti kinti hőmérsékletnél nem kell fűteni), az
  illesztett egyenes és az egyszerű arány.
- **Időállandó, τ** (*Időállandó (τ)* szenzor, óra): fűtés nélkül a helyiség exponenciálisan közelít az egyensúlyi
  hőmérséklethez (kint + szabad hő / H). Legalább 3 órás, égés nélküli szakaszokból tanulja (az utolsó égés után egy
  órával kezdve, zárt ablaknál; az utolsó 21 mediánja). H-val együtt: fokonként tárolt hő (τ × H).
- **Kézi értékek** (Beállítások → *Ház-modell*): `house_loss_w_k`, `house_gains_kw`, `house_tau_h` – pl. egy év
  gázleolvasásaiból. Ezek a kiindulás: a kézi H 14 tanult napnak, a τ 5 szakasznak számít. **Ház-modell
  újratanulása** gomb szigetelés vagy ablakcsere után: a napok és a szakaszok törlődnek, és az aznapi előtti
  statisztikát sem használja újra.
- **Optimális indítás** (`optimal_start`, alapból ki; TPI, PID, on-off): az éjszaka vége előtt annyival korábban kezdi
  a nappali célt, hogy addigra elérje a helyiség – a τ-val becsült lehűlés az éjszaka végéig, a felfűtésekből tanult
  égési perc/fok és az `optimal_start_lag_min` a radiátoroknak; legfeljebb `optimal_start_max_min` (120 perc)
  korábban. Ha elindult, az éjszaka végéig tart (újraindításon át is).
- **Kivárás célcsökkenés előtt, előrejelzéssel:** ismert τ-val az ütemezett célcsökkenés előtt legfeljebb
  `pre_change_max_s` (2 óra) ideig nem indít új égést, ha a helyiség magára hagyva is a váltás utáni cél felett és a
  mostani cél alatt legfeljebb `pre_change_sag` (0,5 °C) marad. A `pre_change_s`-en belül az egyszerű szabály érvényes;
  ismert τ-nál ott is legfeljebb `pre_change_sag`-nyit hűlhet a helyiség (egy könnyűszerkezetes ház 30 perc
  alatt ~1 °C-ot veszít).
- **Penészkockázat** a helyiség leghidegebb pontján (sarok, áthidaló): felületi hőmérséklet = kint + `mould_frsi` ×
  (bent − kint) (régi fal 0,7, szigetelt 0,75–0,8); ott 80 % felett nő a penész. A szenzor mutatja a felület
  hőmérsékletét és páratartalmát, és a legnagyobb penészmentes páratartalmat a helyiségben. A helyiségek
  páratartalom-érzékelőit a hőmérőik eszközéről egyszer, magától felveszi (a helyiségek űrlapján kivehetők).
- **HC info panel:** új *Ház-modell* rész mindezzel.
- **Energetikai besorolás, becslés:** ha megadod az alapterületet (`house_area_m2`), a HC a 9/2023 ÉKM
  rendelet skáláján (A+++ … I) becsli az épület besorolását a tanult hőveszteségből és szabad hőből, a kinti hőmérő
  elmúlt évéből, a hőforrás hatásfokából vagy COP-jából, a melegvízből és a segédáramból (`dhw_kwh_year`,
  `aux_kwh_year`), a primer tényezővel (gáz 1,1, villany 2,3, távhő 1,38, biomassza 0,6; a `primary_factor`
  felülírja). Szenzor és sor a HC info panelen; nem tanúsítvány. az év egy másik, hosszabb adatsorú kinti
  hőmérőből is jöhet (`rating_outdoor_entity`); azokat a napokat, amelyekre nincs átlag, a szabványos magyar évből pótolja.
  **A skála, a primer tényezők és a szabványos év magyar**: más országban a besorolás csak tájékoztató (a
  `primary_factor` ott az adott ország értékére állítandó).

### Mérések

Nem kötelező plusz adatok a **Beállítások → Mérések** részben (az utolsó lenyitható rész) (csak az adott hőforrásé). Tájékoztató jellegűek: a HC
info panel mutatja őket (*Mérések*, és helyiségenként), a fűtési döntést nem változtatják meg.
- **Hőforrás:** víznyomás, valós előremenő / visszatérő (ΔT), moduláció vagy kompresszor %, hibakód, melegvíz-jelző
  (kombi kazánnál is), füstgáz és tüzelőanyag-szint (pellet), maghőmérséklet (hőtárolós), a külső vezérlésű hőtermelő
  állapota.
- **COP** hőszivattyúnál: add meg a hőmennyiségmérőjét (*leadott hő*, kWh) az energiamérője mellé – ma, 7 nap és a
  szezon a két mérő napi növekedéséből.
- **Indítások és üzemidő** minden relés / lángjelzős példánynál, napra, hétre, szezonra.
- **Helyiségek** (helyiségek űrlapja): radiátor-hőmérők – kap-e meleget, vagy hideg, miközben a helyiség fűtést kér –
  és páratartalom-szenzorok – harmatpont és penész-kockázat.
- **Jelzések** a „Kazán probléma” szenzoron: alacsony / magas víznyomás, kevés tüzelőanyag, túl sűrű kapcsolgatás,
  hibakód, túl sokáig hideg radiátor (a határok ugyanitt).
- **Szenzorok:** Indítások ma, Üzemidő ma, COP ma, ΔT, Penész-kockázat (helyiségenként is).

### Heti szivattyú-átmozgatás

- A keringető szivattyú entitással megadott központi kazán hetente egyszer (alapból hétfő 10:00, 60 mp) egyedül
  járatja a szivattyút, ha az 7 napja állt – így nyáron sem ragad be. Csak ha a kazán áll és egy zóna sem kér; a kazán
  emiatt soha nem indul, és újraindítás után az első percekben nincs átmozgatás. Hogy a szivattyú mikor ment utoljára,
  azt újraindítás után is tudja. `central_pump_exercise_s` (0 = ki), `_weekday`, `_time`, `_idle_days`; a központi
  döntés mutatja a `pump_exercise`-t és a végét, a következő és a legutóbbi futást. (A puffer szerep nem hajt
  szivattyút.)

## Felügyelet és biztonság

- **A hibák maguktól megjelennek a Home Assistant *Javítások* között:** kiesett vagy befagyott érzékelő (10 perc után),
  és a hőforrás, amely nem gyújt be, nem reagál a relére, taktol, túlfűt vagy nem tudja tartani a házat (5 perc után).
  A bejegyzés magától eltűnik, amint minden rendben van.
- **Telefonos értesítés:** importáld a blueprintet –
  [HC – értesítés hiba esetén](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FGyuszko55%2Fhc-thermostat%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fhc_thermostat%2Fhc_problem_notify.yaml)
  –, és válaszd ki a *Kazán probléma* / *Fűtési hiba* szenzorokat és a telefonodat.
- **Hibajelentés:** Beállítások → Eszközök és szolgáltatások → HC Thermostat → ⋮ → **Diagnosztika letöltése** (a háznév
  ki van takarva; megosztás előtt nézd át).

### Biztonság

A program nem helyettesíti a kazán saját védelmeit. Tarts független tartalékot is, például alacsonyra állított, párhuzamosan kötött hagyományos helyiségtermosztátot. Használat saját felelősségre (MIT, garancia nélkül).

Az éles mód külön, megerősített lépés (Konfigurálás → Élesítés). Ilyenkor ugyanazt a kimenetet más nem vezérelheti.
ha maga a döntés háromszor egymás után hibára fut (belső hiba), a HC lekapcsolja a kimenetét és a hiba-szenzor
bekapcsol, amíg egy döntés újra sikerül.
a tartós érzékelőhiba (`sensor_problem_after_s`, 10 perc) a Home Assistant *Javítások* listájában is
megjelenik, és magától eltűnik, ha minden rendben; a hiba- és a döntés-szenzor `degraded_since` attribútuma mutatja,
mióta. A `nan` vagy `inf` állapotú szenzor „nincs adat”. Ha a HC beállításaiban szereplő entitást átnevezed, a HC
követi az új azonosítóra (és újratölt), nem veszíti el.

### Állítható határok

- **Fűtési idény** (*Funkciók*): szünetel, ha a napi kinti középhőmérséklet `season_off_above` (15 °C) fölé megy, és
  újraindul `season_on_below` (13 °C) alatt. Jól szigetelt háznál lehet kevesebb, régi háznál több.
- **Legalacsonyabb hihető helyiséghőmérséklet** (*Védelem*, `plaus_indoor_min`, 3 °C): ez alatt a helyiség hőmérője
  hibásnak számít. Sosem lehet magasabb a fagyvédelmi cél mínusz 2 °C-nál, hogy egy valóban hideg helyiségben a
  fagyvédelem elinduljon; fűtetlen hétvégi háznál lehet alacsonyabb.
- **Földgáz fűtőértéke** (*Energia*, `gas_heating_value`, 9,61 kWh/m³ = a magyar számlák 34,6 MJ/m³-e): mindenhol ezt
  használja, ahol a gáz m³-ben számít, az automatikus tüzelőanyagnál is. Más országban a számlán szereplő érték
  (MJ/m³ ÷ 3,6).

## Beállítások

A példány **Konfigurálás** gombja egy menüt nyit:

- **Célok és időzítés** – a célok és az éjszaka (hétköznap és hétvége); a leggyakoribb módosítás.
- **Beállítások** – minden más, lenyitható szekciókban. A finomhangolás (*Szabályozás*, *Energia*, *Csatlakozó tér*,
  *Ház*, *Mérések*) csak a felhasználói profilban bekapcsolt **Haladó mód** mellett látszik; nélküle a mentés ezeket
  változatlanul hagyja.
- **Helyiségek** – egy kazán helyiségei, hőmérőik, szelepfejeik, jelenlét és ablakok.
- **Vezérlés módosítása** – más vezérlés új példány nélkül.
- **Élesítés / Vissza árnyék módba** – csak itt változik az üzemmód, megerősítéssel.

Minden mező alatt rövid magyarázat van az űrlapon.

## Tesztek

```sh
python -m pytest
```

A `tests/sim.py` szimulátor Home Assistant nélkül futtatja a döntési magot. három háztípust ismer (`HOUSES`):
a radiátoros házat, amelyen a HC készült, egy nehéz, padlólemezes házat hőszivattyúval, és egy könnyű, gyors házat
konvektorokkal / fan-coilokkal; a `Run(resolution=0.1)` úgy kerekíti a helyiség hőmérsékletét, mint egy valódi hőmérő.
A `tests/test_house_types_521.py` mindhármon ellenőrzi a szabályozást, a beragadt hőmérő felismerését, a csökkentés
előtti tartást és a felfűtés-rásegítést.

**Padlófűtés alapértékei (a szimulátor alapján):** a padlós példány csökkentés előtt 2 órát tart
(`pre_change_s`; az esztrich az utolsó órák hőjét a váltás után adja le), a beragadt hőmérő vizsgálata 8 órát vár, és
a céltól 1 °C-on belüli értéket nem ítéli meg (`frozen_band`) – szabályozott helyiségben a padló mellett egy 0,1 °C-os
érték akár 17 óráig, teljes teljesítményű felfűtésnél akár 5 óráig is állhat. A kézzel megadott érték továbbra is
elsőbbséget élvez.

## Verziótörténet

Mi melyik verzióban változott: [CHANGELOG.md](CHANGELOG.md).

## Szerzők és licenc

- **Gyuszko55** – szerző
- **Krissz55555** (Krisztián) – társszerző: a pufferes ház, a hőszivattyú-koordináció és a keverőkörök az ő
  rendszere, tesztjei és kérései nyomán alakultak

A HC Thermostat a 0.71.1-es verziótól a **GNU Affero General Public License v3.0** (AGPL-3.0-only) alatt érhető el –
lásd [LICENSE](LICENSE) és [NOTICE](NOTICE). Szabadon használhatod, módosíthatod és továbbadhatod; a módosított
változatot, ha másnak továbbadod vagy hálózaton másoknak futtatod, ugyanezzel a licenccel, a forráskóddal együtt kell
elérhetővé tenned. A 0.71.0-ig kiadott verziók megtartják az MIT licencet, amellyel megjelentek.
