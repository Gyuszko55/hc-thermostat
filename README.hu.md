# <img src="images/icon.png" alt="HC Thermostat icon" width="44" align="absmiddle"> HC Thermostat (Heat Conductor Thermostat)

[English](README.md)

> **Béta.** Egy valódi ház fűtését vezérli, de minden rendszer más: egy új példány mindig **árnyék módban** indul
> (számol és összevet, nem kapcsol semmit). Csak akkor élesítsd, ha átnézted a döntéseit, és legyen független
> tartalék termosztát is (lásd Biztonság). A fűtési görbét, a hűtést és az újabb hőforrásokat (hőtárolós kályha,
> távfűtés, fan-coil, pellet / puffer) eddig csak szimulátorban és próba-példányon teszteltük.

A HC Thermostat a Home Assistant fűtési **felügyelője**, egyszerű rendszerekhez beépített szabályozóval. Nem akarja leváltani a jó termosztát-integrációkat: föléjük kerül, eldönti, mit csináljon a ház, és megmondja, miért.

## Gyors kezdés

**Feltételek:** Home Assistant **2026.10** vagy újabb; egy helyiséghőmérő, és amit a HC kapcsol vagy állít (relé:
`switch` / `input_boolean`, meglévő `climate` termosztát vagy klíma, vagy előremenő cél `number`). A °C és a °F is
működik (0.45.0): a °F-os mérést átszámolja, és amit egy termosztátra ír, a rendszer mértékegységében küldi.

1. **Telepítés:** HACS → ⋮ → Egyéni tárolók → `https://github.com/Gyuszko55/hc-thermostat`, típus *Integráció* →
   **HC Thermostat** letöltése → a Home Assistant **újraindítása**.
2. **Felvétel:** Beállítások → Eszközök és szolgáltatások → Integráció hozzáadása → **HC Thermostat** → válaszd a
   **beállító varázslót (ajánlott)** – egy hivatkozás megnyitja a **HC beállítás** panelt (kiszámolt beállítások és
   helyiségek; rendszergazdáknak) –, vagy a kézi beállítást: név, hőforrás és rendszer, eszközök, végül a célok és az
   időzítés.
3. **Figyeld árnyék módban:** az új példány számol és naplózza, mit tenne, de nem kapcsol. A **HC info** panel és a
   döntés-szenzor megmondja, miért.
4. **Élesítés:** Beállítások → Eszközök és szolgáltatások → HC Thermostat → **Konfigurálás** → **Élesítés**, a
   megerősítés bejelölésével. (A varázsló összefoglalóján az új példány élesen is indítható.) Vissza árnyékba
   ugyanígy.

**Jelenlét** (`presence_entities`): otthon, ha bármelyik `home`, `on`, `otthon` (otthon lévő `person` /
`device_tracker`, bekapcsolt bináris szenzor); szabadság: `vacation`, `szabadság`, `szabadsag`; minden más (zóna neve,
`not_home`, `off`) távol. Jelenlét-entitás nélkül a ház mindig otthon van.

**Példány törlése:** a HC semmit nem ír vissza – a szelepfej vagy a kezelt termosztát megtartja az utolsó célt, amit
a HC küldött, a relé úgy marad. Szükség esetén állítsd kézzel. Az utolsó példány törlésével a HC panelek is
eltűnnek az oldalsávról (a következő példánnyal visszajönnek).

## Döntési sor

Mit olvas, hogyan dönt és mit számol ki a HC három szinten – hőforrás, végrehajtás, fűtőkészülék és helyiség –,
a hőforrás × fűtőkészülék mátrixszal: [DECISION_CHAIN.hu.md](DECISION_CHAIN.hu.md) (a kódból generálva).

## Funkciók

**Hőforrások és rendszerek**
- Gázkazán (be-ki), moduláló kazán fűtési görbével, elektromos fűtő, elektromos padlófűtés, hőszivattyú, klíma, hőtárolós kályha, távfűtés, pellet kazán.
- Radiátor, vizes vagy elektromos padló (egy helyiség vagy zónák), fan-coil, helyiségben álló egység; központi kazán zónákkal és puffertartály szerep.

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
- Egy kazán helyiségei (0.43.0): a vezető helyiség vezérli a kazánt, minden más helyiség saját HC termosztátot kap – szelepfejes helyiség saját céllal, a helyiség hőmérőihez kalibrálva és helyiségenkénti jelenléttel, a szelepfej nélküli helyiség a házat követi; szelepfejes (TRV) helyiségek saját eltolással és kalibrálással; zónánkénti előremenő-kérés és -plafon a központi moduláló kazánnál; elektromos zónák közös terheléskorlátja; csatlakozó tér (nyitott ajtó) és olcsóbb hőforrás javaslat.

**Biztonság és felügyelet**
- Szünet nyitott ablaknál (érzékelő vagy gyors hőesés), nyári pihenő, fagyvédelem, újraindítás-védelem, hihetetlen mérések kiszűrése, tartalék üzem érzékelő-kiesésnél.
- Kazán-egészség a fogyasztásból és a lángjelzésből (nem reagál, nem gyújt be, taktol, parancs nélküli égés, túlfűtés), fűtési hiba jelző.
- Heti szelep- és szivattyúmozgatás; vezérelt áram jelzése; távfűtésnél visszatérő-korlát.

**Eszközök**
- Beállító varázsló az oldalsávban, HC info panel (a rendszer rajza minden adattal), döntésnapló és szövegek magyarul és angolul, hőveszteség- és hőigény-becslés, költség-összevetés.
- Kerek termosztát kártya hozzá: [HC Dial Card](https://github.com/Gyuszko55/hc-dial-card).

## Alapok

- **Árnyék mód (alapértelmezett):** mindent kiszámol, semmit nem kapcsol, és összeveti magát a valódi fűtéssel.
- **Saját szabályozó:** TPI vagy PID, PWM-mel, be-ki reléhez; a minimális futási időt és szünetet egyik algoritmus sem írhatja felül.
- **Külső termosztát:** bármely `climate` entitás célhőfokát és üzemmódját állítja.
- **Felügyelet:** jelenlét és éjszakai ütemezés, szünet nyitott ablaknál, nyári pihenő, fagyvédelem, tartalék üzem érzékelő-kiesésnél, újraindítás-védelem, hibafigyelés, opcionális felfűtés.
- **Döntésnapló** magyarul és angolul.
- **Vezérlési mátrix:** a hőtermelőből és a hidraulikából javaslatot ad. Ez szakmai alapbeállítás, nem helyettesíti a gépész méretezését.

## Jelenlét helyiségenként

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

## Beállító varázsló (0.21.0)

Oldalsáv-panel, **HC beállítás** (csak adminnak), hat lépésben: mit állítunk be (új vagy meglévő példány) →
hőforrás → rendszer és szabályozás, a javaslati mátrix értékelésével és indoklásával → eszközök (csak a
választott szabályozáshoz kellő mezők, előre kitöltött javaslatokkal) → az ezekből kiszámolt beállítások,
mindegyik indoklással és átírható (ciklus és minimális égés a rendszerből, a klíma lépésköze és határai, a gáz
m³-enkénti hője, a kazán alapjárata és égése a fogyasztásmérő két napjából, helyiséghőmérők) → összefoglaló és
mentés. Új példány mindig árnyék módban indul. A panel az első HC-példány után jelenik meg (az elsőt a
Beállítások → Eszközök és szolgáltatások alatt kell felvenni).

## Elektromos padlófűtés, padlóhőfok-limit, célhő forrás (0.25.0)

- **Elektromos padlófűtés** (fűtőszőnyeg vagy fűtőkábel a padló alatt): ajánlott kombináció, TPI vagy PID + PWM a
  relén, alapból 30 perces ciklussal és 5 perces minimummal.
- **Padlóhőfok-limit:** padlószenzor és maximum (elektromos padlónál alapból 27 °C). E fölött a relé azonnal
  kikapcsol, bármit mond a szabályozó, és 1 °C-kal alatta kapcsol vissza. Elektromos padlónál a padlószenzor
  kötelező: friss érték nélkül nem fűt. Vizes padlónál a limit választható.
- **Kiesett benti hőmérő:** elektromos fűtő (és elektromos padló) vakon nem fűt (0 %, a kazán 35 %-os tartaléka
  helyett); a padlószenzor ilyenkor is véd a fagy ellen.
- **Célhő forrása:** fali termosztát (vagy number), amelynek a célját a példány kézi célként átveszi a következő
  ütemezett váltásig – így több zóna is követhet egy tekerőt. Amit egy HC-példány maga írt oda, azt nem veszi át.

## Hőszivattyú (0.26.0)

- **On-off, hosszú futással** (`onoff` vezérlés): a hőszivattyú termosztát-bemenetét a cél alatt bekapcsolja, a
  cél elérésekor kikapcsolja – nincs szaggatás; a legrövidebb futás és szünet állítható (20 / 10 perc).
- **Leolvasztás és melegvíz-készítés:** választható jelzők (bináris szenzor, kapcsoló vagy üzemmód-szenzor). Amíg
  a hőszivattyú leolvaszt vagy melegvizet készít, a hibafigyelés vár, és az egészségfigyelés nem riaszt.

## Moduláló kazán zónákkal (0.27.0)

- Minden zóna-példány közzéteszi, mekkora előremenőt kér a saját görbéje (`flow_request`: padlózóna lapos és
  alacsony, radiátoros zóna meredekebb, plusz korrekció, amíg a helyiség a cél alatt van).
- A központi példány a kazán futása alatt a **nyitott, igénylő zónák legnagyobb kérését** írja egy előremenő-alapjel
  entitásba (number / input_number, nem kötelező); a többi zóna a szelepével fojt. Ha egy zóna sem kér értéket,
  `central_flow_default`; határok: `central_flow_min` / `central_flow_max`.
- Radiátorral közös vízről táplált padlókörhöz továbbra is kell saját keverőszelep – a padlóhőfok-limit marad.

## Elektromos zónák terheléskorlátja (0.28.0)

- Több elektromos zóna (relé vagy okosdugalj, TPI / PID) osztozhat egy teljesítménykereten, pl. a főbiztosítékon:
  minden zónán add meg a fűtőtest teljesítményét és ugyanazt a `load_limit_kw` korlátot. Egy zóna csak akkor
  kapcsol be, ha a teljesítménye belefér.
- Az elutasított zóna vár (érkezési sorrendben), és a PWM-ciklusa akkor indul, amikor sorra kerül – a teljes
  fűtési idejét megkapja, a zónák pedig elcsúsztatva fűtenek, nem egyszerre kapcsolnak be. Amelyik szünet
  nélkül fűt, a következő ciklusa elején átadja a helyét a várakozónak. A kikapcsolást semmi nem tartja vissza; a
  fagyvédelemre is vonatkozik a korlát (a biztosíték fizikai).
- Csak az éles példányok számítanak; a döntés szövege kiírja, ha egy zóna a sorára vár.

## Padlóhűtés harmatpont-védelemmel (0.29.0)

- Padlós, megfordítható hőszivattyú (görbe vagy ki/be vezérlés) nyáron, amikor a fűtési szezon szünetel, hűteni is
  tud: `target_cool` + 0,5 °C fölött indul, és amíg a helyiség `target_cool` − 0,5 °C alá nem hűl.
- A harmatpontot a benti hőfokból és a páratartalomból számolja (páratartalom-szenzor kötelező). A víz és a padló
  mindig a harmatpont + `dew_margin` (2 °C) fölött marad: görbe módban a hűtési előremenőt (`cool_flow`, 18 °C)
  ennyire megemeli, és ha még a `cool_flow_max` (22 °C) sem lenne biztonságos, leáll („túl párás”). Padlószenzorral a
  biztonságos határon vagy a `floor_min_cool` (19 °C) értéken szünetel; ki/be vezérlésnél a padlószenzor kötelező.
- Nem kötelező: a hőszivattyú hűtés-kapcsolója (nyáron végig be, fűtési szezonban ki) és külön hűtési előremenő-
  alapjel. Leálláskor a legmelegebb értéket írja, sosem a leghidegebbet. A beállításokban kapcsolható be.

## Szelepfejes (TRV) helyiségek: saját cél és kalibrálás (0.30.0)

- Egyzónás rendszerben minden TRV-s helyiség eltolást kaphat a ház céljához (beállítások, „Szelepfejes (TRV) helyiségek”
  lépés: pl. háló −2 °C, fürdő +1 °C) – így is követi az ütemezést (éjszaka, távollét).
- Kalibrálás (nem kötelező): a fej a forró radiátor mellett mér, ezért korán zár. Ahol a helyiségben saját hőmérő is
  van, a fej − helyiség eltérést lassan követi (30 perces simítás, legfeljebb ±5 °C), és a fejre írt célt ennyivel
  korrigálja. A csak kalibrálásból adódó változást legfeljebb félóránként írja ki.
- Fejenkénti hőmérő (0.42.0): a beállítások („Szelepfejes (TRV) helyiségek” lépés) és a beállító varázsló
  („Szelepfejek (TRV)”) minden fejhez felkínálja „A fej saját hőmérője” (nincs kalibrálás) vagy egy külső hőmérő
  választását – a lista a fej területén lévő hőmérőket mutatja (a fej saját entitásai nélkül; ha ott nincs, az
  összeset). Mentése: `trv_sensors` (fej → szenzor). A korábban mentett példány változatlanul működik, amíg újra
  nem mented (`trv_calibration` be: a fej területének hőmérői). Másik hőmérőnél a tanult eltérés újraindul.
  A HC info és a tárcsás kártya „i” gombja szelepfejről is a gazda példányt nyitja.
- A fejen kézzel átállított cél továbbra is megmarad, amíg a helyiség célja nem változik. A helyiségek szenzor
  `trv_rooms` attribútuma fejenként mutatja a célt, az eltolást és a kalibrálást.

## Hőtárolós kályha és vezérelt áram (0.31.0)

- Új hőforrás a **hőtárolós kályha** (helyiségben lévő egység, `storage` vezérlés): a vezérelt áramos ablakban
  (alapból 22:00–06:00) annyit tölt, amennyit a kinti napi átlag kér ((cél − kint) / (cél − méretezési hőfok), plusz
  a felhasználó korrekciója; kinti mérés nélkül teljesen), és a töltést az ablak végére időzíti. A töltés kezdetekor
  az arány rögzül. Fagyveszélynél teljesen tölt, ha van áram.
- Nem kötelező kisütő ventilátor / csappantyú: bekapcsol, ha a helyiség 0,3 °C-kal a cél alatt van, kikapcsol a célnál;
  nyitott ablaknál, szezonon kívül és kikapcsolt állapotban ki.
- **Vezérelt áram jelzése** (bármely elektromos fűtésnél, nem kötelező): amíg nincs áram, semmit nem kapcsol, a
  szabályozó nem gyűjt fölösleges igényt, és a döntés szövege megmondja, miért.
- **Áramjel mellett (0.39.2)** a hőtárolós kályha a ténylegesen töltött órákat számolja, és az ablakon belül minden
  áramos blokkot kihasznál, amíg a kiszámolt óraszám össze nem jön (a vezérelt áram több blokkban jön; az ablak
  végére időzített töltés egy kieső blokkal elveszne). Áramjel nélkül marad az ablak végére időzítés.

## Külső vezérlésű hőtermelő, hasznos fűtés késése (0.47.0)

- **Külső vezérlésű hőtermelő** (új hőforrás, „csak zónaszelep”): a hőt egy PLC, a hőszivattyú saját vezérlése vagy egy
  saját logikájú kazán adja, ez indítja a szivattyúkat is; a HC csak a helyiség zónaszelepét kapcsolja (TPI / PID + PWM,
  alapból 30 perces ciklus, padlón hosszú ciklus). Égésjelzőt, áramfelvételt, kazán-állapotot nem kér és nem mutat.
- **Hasznos fűtés késése** (`valve_delay_s`, a felvételkor és a beállításokban, TPI / PID): a termoelektromos szelep kb.
  5 perc alatt nyit, a szivattyút a saját vezérlése pl. 5 perccel az igény után indítja – minden nyitás első 10 perce
  nem fűt. Ha megadod, minden nyitás ennyivel hosszabb, a minimális bekapcsolási idő a hasznos részre vonatkozik, és a
  túl kicsi igény **a következő ciklusokra gyűlik**, amíg megér egy nyitást (igény nélkül törlődik). Szimulációban (15
  perces ciklus, 10 perc holtidő, 24 óra) nélküle a nyitások negyede–fele véget ért, mielőtt hő érkezett volna, vele
  egy sem, és a helyiség kb. kétszer közelebb maradt a céljához.
- **Felvétel:** az „Integráció hozzáadása” előbb a varázslót (a panelje rögtön elérhető, példány nélkül is) vagy a kézi
  utat kínálja; a kézi út végén új **Alapbeállítások** lépés: célok, éjszaka, ciklus, minimális be- / kikapcsolási idő,
  hasznos fűtés késése.

## Mérések (0.48.0)

Nem kötelező plusz adatok a **Beállítások → Mérések** részben (csak az adott hőforrásé). Tájékoztató jellegűek: a HC
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

## Távfűtés és fan-coil (0.32.0)

- **Távfűtés** (új hőforrás): lakásonkénti zónaszelep TPI-vel / PID-del, hosszú, nyugodt ciklussal (30 perc, legalább
  10 perc nyitva), vagy szelepfejek külső termosztát módban. Nem kötelező **visszatérő-korlát**: visszatérő-szenzorral
  és `return_max` beállítással a szelep zárva marad, amíg a visszatérő víz ilyen meleg (3 °C hiszterézis).
- **Fan-coil** (új rendszer, bármely vizes hőforrásról – hőszivattyúról is): a vízszelepet TPI / PID kapcsolja, a
  ventilátor (`fan` entitás, százalékban) nyitott szelepnél `fan_min_pct` + az igény szerint forog, zárás után 2 percig
  utánfut; hőcserélő-szenzorral megvárja, amíg az 30 °C-ra melegszik (nem fúj hideget).

## Pellet kazán és puffertartály (0.33.0)

- **Pellet kazán** (új hőforrás): on-off vezérlés hosszú futásokkal – legalább 45 perc, 20 perc szünet –, mert
  lassan gyújt és ég ki; az állapotfigyelés az áramfelvétele szerint ítél, és kivárja a kiégést.
- **Puffertartály** (új szerep, a központi kazánhoz hasonlóan): a tartály felső (és ha van, alsó) hőmérője szerint
  kapcsolja a hőforrást: a töltés akkor indul, ha a teteje `buffer_on` (45 °C) vagy hidegebb, és mindig addig tart,
  amíg az alja el nem éri a `buffer_off` (65 °C) értéket; új töltés 20 perc szünet után. Megadott zónáknál csak
  zónaigénynél indul; fagyveszélynél (teteje ≤ 8 °C) mindenképp tölt; felső hőmérő nélkül nem tölt. A körök a
  tartályból rendes HC-zónaként fűtenek. Döntés-szenzor és „hőforrás kérés” bináris szenzor.

## HC info panel (0.34.0)

Oldalsávi panel, **HC info** (csak adminoknak, csak olvas): egy példány minden adata. A fűtési rendszere a típusa
szerint lerajzolva (kazán, hőszivattyú, távfűtési hőközpont, pellet, elektromos, hőtároló, klíma; radiátor,
szelepfej, padló, fan-coil; központi kazán a zónáival, puffertartály), minden elem mellett a saját adataival; a rajz
mellett a döntés, presetek és célok, a bemeneti és kimeneti eszközök élő állapottal, a bemenetek, amikre döntött (a
mérés korával), minden belső érték, a kazán állapota, helyiségek és szelepfejek, minden beállítás és a napló. Hogy melyik
adat melyik elemnél jelenik meg, azt egyetlen **adat-mátrix** adja meg (`hc-info-panel.js`, `INFO`: elem, felirat,
érték, és a címkék, hogy milyen rendszernél érvényes); a panel a mátrixot is kilistázza. Az oldalsávból vagy
`/hc-info?entity=climate.x` címmel nyílik – a [HC Dial Card](https://github.com/Gyuszko55/hc-dial-card) (1.14+)
„i” ikonja így nyitja meg.

**A házrajz (0.44.0).** Az egyzónás és a zóna-példány a házaként jelenik meg, képeskönyv-stílusú metszetben: a
hőforrás a kazánházban (kazán a lángjával, hőszivattyú, távhő, pellet, elektromos, klíma, hőtároló) előremenő és
visszatérő csövekkel minden helyiségbe, a helyiségek hőmérő-kijelzővel (mért → cél, ≈ ha a helyiség a ház célját követi),
radiátor, padlófűtés vagy egység, szelepfejek (fej mérése → fej célja), nyitott ablak, helyiségenkénti jelenlét, a vezető
helyiség (★), a kinti hőmérséklet és 24 órás átlaga, a háztartás jelenléte, nappal / éjszaka a nap szerint, és a
`heat_energy_entity` mérő mai gáza (m³) vagy hőenergiája (kWh) helyi éjféltől (recorder-statisztika, különben az
állapottörténet; 5 percenként olvasva). A helyiségek a gazda helyiséglistájából (0.43.0) jönnek, **annak sorrendjében**:
alsó sor először, a kazánház mellett, balról jobbra, aztán felfelé; ha a területekhez Home Assistant-szintek tartoznak,
a szintek adják az emeleteket. A sorrend a beállításokban (Helyiségek → a helyiség lenyílója → helye a házrajzon) vagy a
varázsló Helyiségek kártyáján a ↑ ↓ gombokkal módosítható. Utánuk jönnek a más felsorolt szenzorral (ablaknyitás-hőmérő,
külön zóna) rendelkező helyiségek. Bármelyik elemre kattintva a panel az adatkártyájához görget (kint, HC vezérlő,
vezető helyiség, hőforrás / gáz); helyiségre vagy szelepfejre a helyiség saját kártyája nyílik. Világos / sötét a Home
Assistant téma szerint, telefonon is elfér, „mozgás csökkentése” mellett nem mozog. A központi és a puffer-példány
megtartja a vonalas rajzot.

## Padlótemperálás (0.35.0)

- Választható kényelmi funkció padlófűtéshez (vizes vagy elektromos, TPI / PID / on-off, padlószenzorral): amíg a
  helyiség elég meleg, a padlót a helyiség célja + 2 °C-on tartja (`floor_temper_offset`), így a padló meleg marad.
- Megadható éjszakai érték (`floor_temper_night`): éjjel és alvás presetben ez a padló célja.
- A padló célja − 0,3 °C alatt indul, a célnál áll le; a minimális futás és szünet érvényes. Leáll, ha a helyiség 0,5 °C-kal
  a célja fölé ér (`floor_temper_room_margin`; nagyobb érték melegebb padlót, de a helyiségben nagyobb ingadozást és
  többletfogyasztást ad), és nyitott ablaknál, kikapcsolva, nyáron nem fűt. A padlóhőfok-limit
  mindig előbbre való, és a tanulás ezekből a futásokból nem tanul.

## Kiesett helyiséghőmérő: a padló meleg marad (0.36.0)

- Padlófűtés padlószenzorral (TPI / PID / on-off): ha a helyiséghőmérő kiesik, a padlót a padlószenzor szerint a
  helyiség célja + a temperálás eltérése (vagy az éjszakai érték) hőfokán tartja – a kazán vak 35 %-a, illetve
  elektromos padlónál a fűtés nélküli állapot helyett. Alapból be van kapcsolva (`floor_fallback`).
- A fagyvédelem előbbre való, a padlóhőfok-limit mindig érvényes, nyitott ablaknál szünetel; padlóhőfok nélkül
  minden a régi módon működik.

## Padlóhőfok-limit a burkolat és a szenzor helye szerint (0.37.0)

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

## Vezetékes fali termosztát mint igény (0.38.0)

- A relés példány (TPI / PID / on-off) az igényt egy potenciálmentes fali termosztáttól is veheti, bináris
  szenzoron, input_booleanen vagy kapcsolón át (`demand_entity`): érintkező be – fűt, ki – nem fűt. A helyiséghőmérő
  ekkor elhagyható.
- A fagyvédelem (a helyiséghőmérő, ennek hiányában a padlószenzor szerint), az újraindítás utáni várakozás, a kikapcsolás,
  a nyitott ablak és a nyári pihenő előbbre való; a padlóhőfok-limit és a padlótemperálás erre is érvényes (a nem kérő
  fali termosztát „célon” számít). Nincs felfűtés és utómelegedés, a szabályozó áll. Ha az érintkező nem elérhető: helyiséghőmérővel
  a példány arról és a saját céljáról szabályoz, amíg az érintkező vissza nem jön (0.39.2); helyiséghőmérő nélkül a
  kiesett hőmérő tartalék üzeme (padlószenzorral a padló szerint).
- Helyiséghőmérő nélkül a padlótemperálás csak az éjszakai abszolút értékkel megy, annak idejében (0.39.2): a „helyiségcél
  + eltérés” a fali termosztát ellen fűtene, annak saját beállítása van.

## Heti szivattyú-átmozgatás (0.39.0)

- A keringető szivattyú entitással megadott központi kazán hetente egyszer (alapból hétfő 10:00, 60 mp) egyedül
  járatja a szivattyút, ha az 7 napja állt – így nyáron sem ragad be. Csak ha a kazán áll és egy zóna sem kér; a kazán
  emiatt soha nem indul, és újraindítás után az első percekben nincs átmozgatás. Hogy a szivattyú mikor ment utoljára,
  azt újraindítás után is tudja. `central_pump_exercise_s` (0 = ki), `_weekday`, `_time`, `_idle_days`; a központi
  döntés mutatja a `pump_exercise`-t és a végét, a következő és a legutóbbi futást. (A puffer szerep nem hajt
  szivattyút.)

## Meglévő termosztát-integrációk kezelése (0.42.0)

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

## Egy kazán helyiségei (0.43.0)

„Egy helyiség, egy hőmérő (vagy hőmérő-csoport), egy vagy több szelepfej vagy nincs – viszont egy kazán.” Az egyzónás
példány (TPI / PID) a ház: a kazánt a **vezető helyiség** vezérli (szabályozó szelepfej nélküli helyiség, általában a nappali;
a hőmérője a ház hőmérője, `indoor_entity`). A ház célja a menetrend, a presetek és a háztartás jelenléte, mint eddig.
Minden más helyiség **saját HC termosztátot** kap (`climate.<helyiség>_hc`, „<Helyiség> HC” eszköz a helyiség területén, a gazda
példány eszköze alatt):

- **Hőmérők:** egy vagy egy csoport – az elérhetők átlaga, a kiesett kimarad. A vezető helyiség csoportjának átlaga a
  kazánt is vezérli.
- **Szelepfejes helyiség:** a fejekkel szabályoz. Minden fej a helyiség célját kapja, a helyiség hőmérőihez kalibrálva (a 0.30.0
  kalibrálás); egy fej követhet más hőmérőt vagy a sajátját (kalibrálás nélkül); hőmérő nélküli helyiségben a fejek a
  saját mérésük szerint dolgoznak. Opcionális rövid égés-kérés (a meglévő helyiségigény) **helyiségenként, alapból kikapcsolva**,
  és csak amíg a ház nincs a saját célja fölött.
- **Szelepfej nélküli helyiség:** csak a kazánon át fűthető: a termosztátja a ház célját mutatja, a rajta beállított célt
  érthető üzenettel elutasítja, radiátorszelep-tanácsot kap, és a kazánt soha nem vezérli.
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

**Hol állítható (0.46.0):** a beállítások **Helyiségek** menüpontjában – (1) kipipálod az otthon azon területeit, amelyek
helyiségek (mindegyik mellett látszik, mi van benne), (2) helyiségenként egy lenyíló: a terület hőmérői, szelepfejei,
jelenlét-forrásai és ablak-/ajtóérzékelői jelölőnégyzetekkel (az új helyiségnél előre bepipálva), felül a vezető helyiség; cél,
jelenlét, égés-kérés és fejenkénti kalibrálás csak a szelepfejes helyiségnél, (3) a saját menetrendek; csak a helyiségeket menti.
A beállító varázsló „Helyiségek” kártyája ugyanígy működik (egy vagy több helyiség, a területek jelölőnégyzetes listája –
magától semmi nincs bepipálva). A szelepfej nélküli helyiség neve **megfigyelt helyiség**.

- **Ablak / ajtó helyiségenként (0.46.0):** szelepfejes helyiségben az érzékelői csak a helyiség saját fejeit zárják le
  (fagyvédelmi cél az ablak-késleltetés után); a vezető és a megfigyelt helyiségben a kazánt állítják le, mint a példány
  ablaklistája.
- **Helyiség-csoportok (0.46.0):** ha egy helyiségben két vagy több hőmérő / jelenlét-forrás / nyitásérzékelő van, a HC saját
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

## Biztonság

A program nem helyettesíti a kazán saját védelmeit. Tarts független tartalékot is, például alacsonyra állított, párhuzamosan kötött hagyományos helyiségtermosztátot. Használat saját felelősségre (MIT, garancia nélkül).

Az éles mód külön, megerősített lépés (Konfigurálás → Élesítés). Ilyenkor ugyanazt a kimenetet más nem vezérelheti.
0.45.0: ha maga a döntés háromszor egymás után hibára fut (belső hiba), a HC lekapcsolja a kimenetét és a hiba-szenzor
bekapcsol, amíg egy döntés újra sikerül.

## Telepítés

**HACS (egyéni tároló):** HACS → ⋮ → Egyéni tárolók → `https://github.com/Gyuszko55/hc-thermostat`, típus
*Integráció* → **HC Thermostat** letöltése → a Home Assistant újraindítása → Beállítások → Eszközök és
szolgáltatások → Integráció hozzáadása → **HC Thermostat** (az első lépés felajánlja a **HC beállítás** varázslót, 0.47.0).

**Kézzel:** másold a `custom_components/hc_thermostat` mappát a konfiguráció `custom_components` mappájába, és
indítsd újra.

A kerek termosztát kártya külön projekt: [hc-dial-card](https://github.com/Gyuszko55/hc-dial-card).

## Tesztek

```sh
python -m pytest
```

A `tests/sim.py` szimulátor Home Assistant nélkül futtatja a döntési magot.
