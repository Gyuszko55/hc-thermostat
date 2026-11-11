# <img src="images/icon.png" alt="HC Thermostat icon" width="44" align="absmiddle"> HC Thermostat (Heat Conductor Thermostat)

[English](README.md)

> **Béta.** Egy valódi ház fűtését vezérli, de minden rendszer más: egy új példány mindig **árnyék módban** indul
> (számol és összevet, nem kapcsol semmit). Csak akkor élesítsd, ha átnézted a döntéseit, és legyen független
> tartalék termosztát is (lásd Biztonság). A fűtési görbét, a hűtést és az újabb hőforrásokat (hőtárolós kályha,
> távfűtés, fan-coil, pellet / puffer) eddig csak szimulátorban és próba-példányon teszteltük.

A HC Thermostat a Home Assistant fűtési **felügyelője**, egyszerű rendszerekhez beépített szabályozóval. Nem akarja leváltani a jó termosztát-integrációkat: föléjük kerül, eldönti, mit csináljon a ház, és megmondja, miért.

## Alapok

- **Árnyék mód (alapértelmezett):** mindent kiszámol, semmit nem kapcsol, és összeveti magát a valódi fűtéssel.
- **Saját szabályozó:** TPI vagy PID, PWM-mel, be-ki reléhez; a minimális futási időt és szünetet egyik algoritmus sem írhatja felül.
- **Külső termosztát:** bármely `climate` entitás célhőfokát és üzemmódját állítja.
- **Felügyelet:** jelenlét és éjszakai ütemezés, szünet nyitott ablaknál, nyári pihenő, fagyvédelem, tartalék üzem érzékelő-kiesésnél, újraindítás-védelem, hibafigyelés, opcionális felfűtés.
- **Döntésnapló** magyarul és angolul.
- **Vezérlési mátrix:** a hőtermelőből és a hidraulikából javaslatot ad. Ez szakmai alapbeállítás, nem helyettesíti a gépész méretezését.

## Beállító varázsló (0.21.0)

Oldalsáv-panel, **HC beállítás** (csak adminnak), hat lépésben: mit állítunk be (új vagy meglévő példány) →
hőforrás → rendszer és szabályozás, a javaslati mátrix értékelésével és indoklásával → eszközök (csak a
választott szabályozáshoz kellő mezők, előre kitöltött javaslatokkal) → az ezekből kiszámolt beállítások,
mindegyik indoklással és átírható (ciklus és minimális égés a rendszerből, a klíma lépésköze és határai, a gáz
m³-enkénti hője, a kazán alapjárata és égése a fogyasztásmérő két napjából, helyiség-hőmérők) → összefoglaló és
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

- **Kétállású, hosszú futással** (`onoff` vezérlés): a hőszivattyú termosztát-bemenetét a cél alatt bekapcsolja, a
  cél elérésekor kikapcsolja – nincs szaggatás; a legrövidebb futás és szünet állítható (20 / 10 perc).
- **Leolvasztás és melegvíz-készítés:** választható jelzők (bináris szenzor, kapcsoló vagy üzemmód-szenzor). Amíg
  a hőszivattyú leolvaszt vagy melegvizet készít, a hibafigyelés vár, és az egészségfigyelés nem riaszt.

## Moduláló kazán zónákkal (0.27.0)

- Minden zóna-példány közzéteszi, mekkora előremenőt kér a saját görbéje (`flow_request`: padlózóna lapos és
  alacsony, radiátoros zóna meredekebb, plusz korrekció, amíg a szoba a cél alatt van).
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

## Szelepfejes (TRV) szobák: saját cél és kalibrálás (0.30.0)

- Egyzónás rendszerben minden TRV-s szoba eltolást kaphat a ház céljához (beállítások, „Szelepfejes (TRV) szobák”
  lépés: pl. háló −2 °C, fürdő +1 °C) – így is követi az ütemezést (éjszaka, távollét).
- Kalibrálás (nem kötelező): a fej a forró radiátor mellett mér, ezért korán zár. Ahol a szobában saját hőmérő is
  van, a fej − szoba eltérést lassan követi (30 perces simítás, legfeljebb ±5 °C), és a fejre írt célt ennyivel
  korrigálja. A csak kalibrálásból adódó változást legfeljebb félóránként írja ki.
- A fejen kézzel átállított cél továbbra is megmarad, amíg a szoba célja nem változik. A helyiségek szenzor
  `trv_rooms` attribútuma fejenként mutatja a célt, az eltolást és a kalibrálást.

## Hőtárolós kályha és vezérelt áram (0.31.0)

- Új hőforrás a **hőtárolós kályha** (helyiségben lévő egység, `storage` vezérlés): a vezérelt áramos ablakban
  (alapból 22:00–06:00) annyit tölt, amennyit a kinti napi átlag kér ((cél − kint) / (cél − méretezési hőfok), plusz
  a felhasználó korrekciója; kinti mérés nélkül teljesen), és a töltést az ablak végére időzíti. A töltés kezdetekor
  az arány rögzül. Fagyveszélynél teljesen tölt, ha van áram.
- Nem kötelező kisütő ventilátor / csappantyú: bekapcsol, ha a szoba 0,3 °C-kal a cél alatt van, kikapcsol a célnál;
  nyitott ablaknál, szezonon kívül és kikapcsolt állapotban ki.
- **Vezérelt áram jelzése** (bármely elektromos fűtésnél, nem kötelező): amíg nincs áram, semmit nem kapcsol, a
  szabályozó nem gyűjt fölösleges igényt, és a döntés szövege megmondja, miért.
- **Áramjel mellett (0.39.2)** a hőtárolós kályha a ténylegesen töltött órákat számolja, és az ablakon belül minden
  áramos blokkot kihasznál, amíg a kiszámolt óraszám össze nem jön (a vezérelt áram több blokkban jön; az ablak
  végére időzített töltés egy kieső blokkal elveszne). Áramjel nélkül marad az ablak végére időzítés.

## Távfűtés és fan-coil (0.32.0)

- **Távfűtés** (új hőforrás): lakásonkénti zónaszelep TPI-vel / PID-del, hosszú, nyugodt ciklussal (30 perc, legalább
  10 perc nyitva), vagy szelepfejek külső termosztát módban. Nem kötelező **visszatérő-korlát**: visszatérő-szenzorral
  és `return_max` beállítással a szelep zárva marad, amíg a visszatérő víz ilyen meleg (3 °C hiszterézis).
- **Fan-coil** (új rendszer, bármely vizes hőforrásról – hőszivattyúról is): a vízszelepet TPI / PID kapcsolja, a
  ventilátor (`fan` entitás, százalékban) nyitott szelepnél `fan_min_pct` + az igény szerint forog, zárás után 2 percig
  utánfut; hőcserélő-szenzorral megvárja, amíg az 30 °C-ra melegszik (nem fúj hideget).

## Pellet kazán és puffertartály (0.33.0)

- **Pellet kazán** (új hőforrás): kétállású vezérlés hosszú futásokkal – legalább 45 perc, 20 perc szünet –, mert
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
mérés korával), minden belső érték, a kazán állapota, szobák és szelepfejek, minden beállítás és a napló. Hogy melyik
adat melyik elemnél jelenik meg, azt egyetlen **adat-mátrix** adja meg (`hc-info-panel.js`, `INFO`: elem, felirat,
érték, és a címkék, hogy milyen rendszernél érvényes); a panel a mátrixot is kilistázza. Az oldalsávból vagy
`/hc-info?entity=climate.x` címmel nyílik – a [HC Dial Card](https://github.com/Gyuszko55/hc-dial-card) (1.14+)
„i” ikonja így nyitja meg.

## Padlótemperálás (0.35.0)

- Választható kényelmi funkció padlófűtéshez (vizes vagy elektromos, TPI / PID / kétállású, padlószenzorral): amíg a
  szoba elég meleg, a padlót a szoba célja + 2 °C-on tartja (`floor_temper_offset`), így a padló meleg marad.
- Megadható éjszakai érték (`floor_temper_night`): éjjel és alvás presetben ez a padló célja.
- A padló célja − 0,3 °C alatt indul, a célnál áll le; a minimális futás és szünet érvényes. Leáll, ha a szoba 0,5 °C-kal
  a célja fölé ér (`floor_temper_room_margin`; nagyobb érték melegebb padlót, de nagyobb szobai ingadozást és
  többletfogyasztást ad), és nyitott ablaknál, kikapcsolva, nyáron nem fűt. A padlóhőfok-limit
  mindig előbbre való, és a tanulás ezekből a futásokból nem tanul.

## Kiesett szobahőmérő: a padló meleg marad (0.36.0)

- Padlófűtés padlószenzorral (TPI / PID / kétállású): ha a szobahőmérő kiesik, a padlót a padlószenzor szerint a
  szoba célja + a temperálás eltérése (vagy az éjszakai érték) hőfokán tartja – a kazán vak 35 %-a, illetve
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

- A relés példány (TPI / PID / kétállású) az igényt egy potenciálmentes fali termosztáttól is veheti, bináris
  szenzoron, input_booleanen vagy kapcsolón át (`demand_entity`): érintkező be – fűt, ki – nem fűt. A szobahőmérő
  ekkor elhagyható.
- A fagyvédelem (a szobahőmérő, ennek hiányában a padlószenzor szerint), az újraindítás utáni várakozás, a kikapcsolás,
  a nyitott ablak és a nyári pihenő előbbre való; a padlóhőfok-limit és a padlótemperálás erre is érvényes (a nem kérő
  fali termosztát „célon” számít). Nincs felfűtés és utómelegedés, a szabályozó áll. Ha az érintkező nem elérhető: szobahőmérővel
  a példány arról és a saját céljáról szabályoz, amíg az érintkező vissza nem jön (0.39.2); szobahőmérő nélkül a
  kiesett hőmérő tartalék üzeme (padlószenzorral a padló szerint).
- Szobahőmérő nélkül a padlótemperálás csak az éjszakai abszolút értékkel megy, annak idejében (0.39.2): a „szobacél
  + eltérés” a fali termosztát ellen fűtene, annak saját beállítása van.

## Heti szivattyú-átmozgatás (0.39.0)

- A keringető szivattyú entitással megadott központi kazán hetente egyszer (alapból hétfő 10:00, 60 mp) egyedül
  járatja a szivattyút, ha az 7 napja állt – így nyáron sem ragad be. Csak ha a kazán áll és egy zóna sem kér; a kazán
  emiatt soha nem indul, és újraindítás után az első percekben nincs átmozgatás. Hogy a szivattyú mikor ment utoljára,
  azt újraindítás után is tudja. `central_pump_exercise_s` (0 = ki), `_weekday`, `_time`, `_idle_days`; a központi
  döntés mutatja a `pump_exercise`-t és a végét, a következő és a legutóbbi futást. (A puffer szerep nem hajt
  szivattyút.)

## Biztonság

A program nem helyettesíti a kazán saját védelmeit. Tarts független tartalékot is, például alacsonyra állított, párhuzamosan kötött hagyományos szobatermosztátot. Használat saját felelősségre (MIT, garancia nélkül).

Az éles mód külön, megerősített lépés a beállításokban. Ilyenkor ugyanazt a kimenetet más nem vezérelheti.

## Telepítés

**HACS (egyéni tároló):** HACS → ⋮ → Egyéni tárolók → `https://github.com/Gyuszko55/hc-thermostat`, típus
*Integráció* → **HC Thermostat** letöltése → a Home Assistant újraindítása → Beállítások → Eszközök és
szolgáltatások → Integráció hozzáadása → **HC Thermostat** (az első példány után a **HC setup** oldalsávi panel is).

**Kézzel:** másold a `custom_components/hc_thermostat` mappát a konfiguráció `custom_components` mappájába, és
indítsd újra.

A kerek termosztát kártya külön projekt: [hc-dial-card](https://github.com/Gyuszko55/hc-dial-card).

## Tesztek

```sh
python -m pytest
```

A `tests/sim.py` szimulátor Home Assistant nélkül futtatja a döntési magot.
