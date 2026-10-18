// Static source metadata for the demo client only. With a real API the UI
// reads the live list from /v1/sources (see hooks/useIndexedSources).
export const INDEXED_SOURCES = [
  { source_id: "lieberman2005", kind: "textbook", title: "Principles of Plasma Discharges and Materials Processing", authors: "M. A. Lieberman, A. J. Lichtenberg", year: 2005, pages: 757 },
  { source_id: "popov1996", kind: "textbook", title: "High Density Plasma Sources: Design, Physics and Performance", authors: "O. A. Popov", year: 1996, pages: 456 },
  { source_id: "flamm1989", kind: "textbook", title: "Plasma Etching in Semiconductor Fabrication", authors: "D. L. Flamm, D. M. Manos", year: 1989, pages: 512 },
  { source_id: "donnelly2013", kind: "paper", title: "Atomic Layer Etching: Mechanism and Applications", authors: "V. M. Donnelly, A. Kornblit", year: 2013, pages: 320 },
  { source_id: "roth2001", kind: "textbook", title: "Industrial Plasma Engineering: Nonthermal Microplasmas", authors: "J. Reece Roth", year: 2001, pages: 680 },
  { source_id: "gottscho1984", kind: "paper", title: "Plasma Chemistry and Diagnostics in Microelectronics Processing", authors: "R. A. Gottscho, V. M. Donnelly", year: 1984, pages: 290 },
  { source_id: "kushner2009", kind: "paper", title: "Modelling and Simulation of Low-Temperature Plasmas", authors: "M. J. Kushner", year: 2009, pages: 410 },
  { source_id: "hoekstra1998", kind: "paper", title: "Aspect-Ratio-Dependent Etching (ARDE) and Microtrenching", authors: "R. J. Hoekstra, M. J. Kushner", year: 1998, pages: 185 },
  { source_id: "coburn1979", kind: "paper", title: "Fluorocarbon Polymerization in Plasma Etching of SiO2", authors: "J. W. Coburn, H. F. Winters", year: 1979, pages: 140 },
  { source_id: "tachi1988", kind: "vendor_model", title: "Cryogenic Etching of Silicon and Dielectrics", authors: "S. Tachi, K. Tsujimoto, S. Okudaira", year: 1988, pages: 210 },
];

export const AGENTS = {
  literature_assistant: {
    id: "literature_assistant",
    name: "Literature Assistant",
    short: "Literature",
    description: "Answers from the indexed books and papers, with page-level citations.",
    heading: "Ask the plasma literature.",
    lede: "Grounded answers on plasma physics and semiconductor etching, with citations that open the exact page in the indexed textbooks and papers.",
    placeholder: "Ask a question about plasma physics or etching…",
  },
  professor_reviewer: {
    id: "professor_reviewer",
    name: "Professor Reviewer",
    short: "Reviewer",
    description: "Checks a simulation setup against the literature and returns a verdict.",
    heading: "Have your setup reviewed.",
    lede: "Paste a plasma or etch simulation setup. The reviewer checks each assumption against the literature and returns PASS, REVISE or ESCALATE with the changes required.",
    placeholder: "Paste a simulation setup or result to review…",
  },
};

export const QUICK_PROMPTS = {
  literature_assistant: [
    "Why is Te nearly independent of power in a global model?",
    "Explain fluorocarbon passivation in SiO2 etching",
    "What causes aspect-ratio-dependent etching (ARDE)?",
  ],
  professor_reviewer: [
    "Review my ICP etch setup: 10 mTorr, 500 W, Te fixed at 4 eV, fluid model",
    "Validate a cryogenic SF6/O2 silicon etch recipe at −110 °C",
  ],
};
