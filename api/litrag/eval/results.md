# Retrieval eval, 2026-10-08

40 paraphrased questions with a known source and PDF page range (eval/questions.jsonl): 20 on the papers, the COMSOL model and Chen, 10 on Lieberman, 10 on Bittencourt (added 2026-10-08). A hit means a top-5 passage comes from that source and overlaps those pages, so a correct answer from a different book (for example Bittencourt answering the Chen question on what counts as a plasma) still scores as a miss.

| Mode | hit@1 | hit@5 | MRR |
|---|---|---|---|
| Keyword only (BM25) | 0.42 | 0.78 | 0.56 |
| EmbeddingGemma only | 0.38 | 0.85 | 0.55 |
| **Hybrid (RRF, default)** | **0.60** | **0.93** | **0.72** |

By subset, hybrid: the original 30 questions score hit@1 0.63, hit@5 0.90, MRR 0.74 (on 2026-10-07, before Bittencourt was indexed: 0.63, 0.93, 0.75; the extra miss is a Lieberman sheath question whose answer page dropped from rank 5 to 6 as the corpus grew). The 10 Bittencourt questions score hit@1 0.50, hit@5 1.00, MRR 0.67; in the 5 where the answer page is not first, the top passage is a nearby Bittencourt page (2) or a Lieberman page (3).

## Hybrid run, per question

```
rank 1  | At what pressure, gas flow and coil power does the CF4/O2 ICP referenc | top: COMSOL App. Library (CF4/O2 ICP). Model of a CF4/O2 Inductively Couple
rank 2  | Which silicon surface sites are solved for in the COMSOL etching model | top: COMSOL App. Library (CF4/O2 ICP). Model of a CF4/O2 Inductively Couple
rank 1  | Where does the CF4/O2 reaction set in the COMSOL model come from?      | top: COMSOL App. Library (CF4/O2 ICP). Model of a CF4/O2 Inductively Couple
rank 1  | How does the predicted silicon etch rate change when the RF bias volta | top: COMSOL App. Library (CF4/O2 ICP). Model of a CF4/O2 Inductively Couple
rank 1  | How large was the simulation dataset used to train the ICP surrogate,  | top: Shahbazian et al. (2025). Artificial intelligence-driven optimization 
rank 4  | What neural network architecture and training settings were used for t | top: Shahbazian et al. (2025). Artificial intelligence-driven optimization 
rank 1  | How was the optimum predicted by the surrogate checked against the ful | top: Shahbazian et al. (2025). Artificial intelligence-driven optimization 
rank 1  | How does the 3D etch simulator move the surface over time?             | top: Ertl & Selberherr (2009). Three-Dimensional Plasma Etching Simulation 
rank 5  | How are the particle fluxes inside the etched feature computed in 3D?  | top: Ertl & Selberherr (2009). Three-Dimensional Plasma Etching Simulation 
MISS    | What surface coverage model is used for fluorine and oxygen in SF6/O2  | top: Ertl & Selberherr (2009). Three-Dimensional Plasma Etching Simulation 
rank 1  | Which quantum chemistry method and basis set were used to compute fluo | top: Dwivedi et al. (2023). Orientation-dependent etching of silicon by flu
rank 1  | Why does molecular fluorine etch Si(111) more slowly than Si(100)?     | top: Dwivedi et al. (2023). Orientation-dependent etching of silicon by flu
rank 4  | Is the REBO interatomic potential accurate for F2 dissociative chemiso | top: Dwivedi et al. (2023). Orientation-dependent etching of silicon by flu
rank 2  | How does the neural master equation approach represent unknown transit | top: Nath et al. (2025). A neural master equation framework for multiscale 
rank 1  | Where is the code for the neural master equation surface kinetics mode | top: Nath et al. (2025). A neural master equation framework for multiscale 
rank 1  | What ion energies are typically used in plasma atomic layer etching of | top: Wang & Fang (2022). Real-time time-dependent DFT study of laser-enhanc
rank 1  | Which electronic transition dominates photo-assisted desorption of SiC | top: Wang et al. (2023). Mechanism of photo-assisted atomic layer etching o
rank 2  | What condition must hold for an ionized gas to count as a plasma?      | top: Bittencourt (2004). Fundamentals of Plasma Physics, 3rd ed. p. 1, PDF 
rank 1  | How much ionization does the Saha equation predict for room-temperatur | top: Chen (1984), ch. 1. Introduction to Plasma Physics and Controlled Fusi
rank 1  | What sets the thickness of the shielding cloud around a charged grid i | top: Chen (1984), ch. 1. Introduction to Plasma Physics and Controlled Fusi
rank 2  | What condition on the ion velocity at the sheath edge is needed for a  | top: Lieberman & Lichtenberg (2005). Principles of Plasma Discharges and Ma
rank 2  | In a global model of an electropositive discharge, how is the electron | top: Lieberman & Lichtenberg (2005). Principles of Plasma Discharges and Ma
rank 1  | How do you get the plasma density from the absorbed power in a uniform | top: Lieberman & Lichtenberg (2005). Principles of Plasma Discharges and Ma
MISS    | What limits the current through a high-voltage collisionless sheath?   | top: Lieberman & Lichtenberg (2005). Principles of Plasma Discharges and Ma
rank 1  | How much can energetic ion bombardment increase the fluorine-atom etch | top: Lieberman & Lichtenberg (2005). Principles of Plasma Discharges and Ma
rank 1  | What decides whether a fluorocarbon discharge etches the substrate or  | top: Lieberman & Lichtenberg (2005). Principles of Plasma Discharges and Ma
rank 1  | How is adsorption and desorption on a surface modeled with Langmuir ki | top: Lieberman & Lichtenberg (2005). Principles of Plasma Discharges and Ma
rank 1  | What is the collisional energy lost per electron-ion pair created and  | top: Lieberman & Lichtenberg (2005). Principles of Plasma Discharges and Ma
rank 1  | Why does the etch rate drop when more etchable wafer area is exposed?  | top: Lieberman & Lichtenberg (2005). Principles of Plasma Discharges and Ma
MISS    | How can the electron energy distribution be obtained from a Langmuir p | top: Lieberman & Lichtenberg (2005). Principles of Plasma Discharges and Ma
rank 1  | Which particles escape from a magnetic bottle, and what sets the angle | top: Bittencourt (2004). Fundamentals of Plasma Physics, 3rd ed. p. 80, PDF
rank 1  | Why does the polarization plane of a radio wave rotate as it crosses t | top: Bittencourt (2004). Fundamentals of Plasma Physics, 3rd ed. pp. 445-44
rank 2  | How much current must flow along a plasma column to confine it with it | top: Lieberman & Lichtenberg (2005). Principles of Plasma Discharges and Ma
rank 1  | What transverse wave runs along the field lines of a conducting fluid  | top: Bittencourt (2004). Fundamentals of Plasma Physics, 3rd ed. pp. 376-37
rank 1  | Why does a longitudinal electron wave in a hot collisionless plasma lo | top: Bittencourt (2004). Fundamentals of Plasma Physics, 3rd ed. pp. 501-50
rank 5  | Why do electrons and ions leave a plasma at one common rate between th | top: Bittencourt (2004). Fundamentals of Plasma Physics, 3rd ed. pp. 255-25
rank 2  | Which way do ions and electrons drift when the magnetic field strength | top: Bittencourt (2004). Fundamentals of Plasma Physics, 3rd ed. pp. 111-11
rank 3  | How is the collision term derived when many small-angle Coulomb deflec | top: Lieberman & Lichtenberg (2005). Principles of Plasma Discharges and Ma
rank 5  | What characteristic frequency combines the electron plasma frequency a | top: Lieberman & Lichtenberg (2005). Principles of Plasma Discharges and Ma
rank 1  | Why does the wave amplitude grow when two counterstreaming electron be | top: Bittencourt (2004). Fundamentals of Plasma Physics, 3rd ed. pp. 505-50

mode=hybrid  questions=40 (skipped 0 for unindexed sources)
hit@1=0.60  hit@5=0.93  MRR=0.72
```
