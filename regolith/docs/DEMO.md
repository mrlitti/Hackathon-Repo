# Regolith: 4-minute demo

Start the app (`cd regolith/backend && uvicorn app:app`), open http://127.0.0.1:8000 in a full-screen
browser window, and let the globe load for about 10 seconds before you begin.

## 0:00 – The problem (20 s)

> Astronauts on Mars will have limited time and limited sample space. Holding an APXS reading of a rock,
> they need to know on the spot: is this rock new, what is it, and what else is around here, including
> water? NASA and the Canadian Space Agency have about 20 years of answers in their archives. Regolith
> puts them in the astronaut's hands.

Point at the header: 2,475 APXS measurements from 3 rovers. Curiosity's APXS is Canada's contribution.

## 0:20 – Take a reading (40 s)

1. Under **Field reading**, pick **Calcium-sulfate vein** and press **Simulate**.
   > This loads a real Curiosity measurement with its own instrument noise added, as if an astronaut
   > had just measured it, and places us a few hundred metres away.
2. Point at the sliders: each runs over the range APXS actually measured; the tick marks typical Mars.
3. Press **Find match**.
   > Regolith found the source rock among all 2,475 and the map flies to it. Veins like this are well
   > sampled, so the verdict is usually duplicate: skip it and save the sample slot.

## 1:00 – Why, and what's next (50 s)

Scroll the verdict card.
- **Why your reading looks like this:** groundwater deposited gypsum in cracks, with the NASA release.
- **Likely minerals:** an upper bound on calcium sulfate (often 30–55% for a vein), from the mineral formulas.
- **What you'll likely find within 1 km**, with its tested reliability.
- **Water you could extract:** about 20 L per tonne of soil at Gale, calibrated on Curiosity's own soil-heating result.

Click the first match to show the rock card: NASA's close-up photo, composition and X-ray spectrum.

## 1:50 – The map (40 s)

1. Turn on **Prospect zones**.
   > These come only from orbit: Odyssey's gamma-ray maps and MOLA elevation. Violet is likely salt
   > basins, teal water-rich ground, green potassium-rich ground. Gale and Gusev sit in a salt zone,
   > and Curiosity really did find salt there; Meridiani is in a water zone, where Opportunity found sulfates.
2. Click any empty spot for a forecast of that place.
3. Turn zones off, choose **Element map → Chlorine**: orbit and rover data side by side.

## 2:30 – Plan the walk (30 s)

In **Plan an EVA**, press **Example start**, leave 4 hours and 15°, and press **Plan route**.
> Regolith walks the real HiRISE terrain of Gale crater: eight stops, eight different rare deposit types,
> about 2 km, back with half an hour in reserve. The slope model passes the test of Curiosity's own route.

## 3:00 – The Canadian instrument (30 s)

Open **Spectrum lab**. Kythira loads with a quarter of its counting time.
> This is the raw X-ray spectrum from the CSA's APXS. Even from a quick-look reading, Regolith finds the rock
> from its spectrum alone, labels every element line, and compares it with the CSA's lab standards.

Slide **Counting time** down to 10%: it still finds Kythira.

## 3:30 – Can you trust it? (30 s)

Open **Data & methods**.
> Every source is NASA or CSA, listed here. And every claim is tested on data it never saw: a
> re-measured rock is found 91.5% of the time; the deposit type is right 99% of the time; the
> 1-km forecast beats always guessing basalt, and its percentages match how often things really turn up.

Close with:
> Regolith helps future Mars astronauts decide which rocks to sample and where to find resources, using
> every rock NASA's rovers have measured with the APXS.

## If something goes wrong

- **Globe is blank or slow:** the imagery streams live from NASA Mars Trek; wait a few seconds, or switch
  **Mars globe → Surface layer** to *Viking color mosaic*.
- **Lost on the map:** press **Esc** to clear a selection, or **Mars globe → Reset view**.
- **No internet:** matching, verdicts, predictions and the Deposits and Data & methods tabs still work
  (they use the local data). The 3D globe, its imagery and the rover photos need the network.
