import { type FormEvent, useState } from "react";

const DEMO_RECIPE = `{\n  "power_W": 100,\n  "pressure_mTorr": 15,\n  "CF4_sccm": 40,\n  "O2_sccm": 10\n}`;

export default function FourMForm({
  onSubmit,
  disabled
}: {
  onSubmit: (payload: unknown) => void;
  disabled: boolean;
}) {
  const [caseId, setCaseId] = useState("cf4o2_icp_100w");
  const [question, setQuestion] = useState("How does ion flux change across the 0–100 V bias sweep?");
  const [radius, setRadius] = useState("150");
  const [height, setHeight] = useState("120");
  const [chuck, setChuck] = useState("100 mm cathode");
  const [diagnostics, setDiagnostics] = useState("Langmuir probe, OES");
  const [wafer, setWafer] = useState("Si");
  const [stack, setStack] = useState("SiO2, SiN");
  const [recipe, setRecipe] = useState(DEMO_RECIPE);
  const [metrology, setMetrology] = useState("SEM depth, optical CD");
  const [experience, setExperience] = useState("");
  const [shift, setShift] = useState("");
  const [notes, setNotes] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const parsedRecipe = JSON.parse(recipe) as Record<string, unknown>;
      onSubmit({
        case_id: caseId,
        question,
        machine: {
          chamber_radius_mm: Number(radius) || null,
          reactor_height_mm: Number(height) || null,
          chuck: chuck || null,
          diagnostics: split(diagnostics)
        },
        material: { wafer, stack: split(stack) },
        method: { recipe: parsedRecipe, metrology: split(metrology) },
        man:
          experience || shift || notes
            ? {
                operator_experience: experience === "junior" || experience === "senior" ? experience : null,
                shift: shift || null,
                notes: notes || null
              }
            : null,
        source: "form"
      });
    } catch {
      setFormError("Recipe must be valid JSON, for example \"power_W\": 100.");
    }
  }

  return (
    <form className="panel input-panel" onSubmit={submit} aria-label="4M experiment brief">
      <h2>Experiment brief</h2>
      <div className="field">
        <label htmlFor="case-id">Case name</label>
        <input id="case-id" required value={caseId} onChange={(event) => setCaseId(event.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="question">Question</label>
        <textarea id="question" required rows={3} value={question} onChange={(event) => setQuestion(event.target.value)} />
      </div>

      <fieldset>
        <legend>Machine</legend>
        <div className="pair">
          <Field id="radius" label="Radius (mm)" value={radius} onChange={setRadius} type="number" />
          <Field id="height" label="Height (mm)" value={height} onChange={setHeight} type="number" />
        </div>
        <Field id="chuck" label="Chuck" value={chuck} onChange={setChuck} />
        <Field
          id="diagnostics"
          label="Diagnostics, comma-separated"
          value={diagnostics}
          onChange={setDiagnostics}
        />
      </fieldset>

      <fieldset>
        <legend>Material</legend>
        <Field id="wafer" label="Wafer" value={wafer} onChange={setWafer} />
        <Field id="stack" label="Stack, comma-separated" value={stack} onChange={setStack} />
      </fieldset>

      <fieldset>
        <legend>Method</legend>
        <div className="field">
          <label htmlFor="recipe">Recipe JSON</label>
          <textarea
            id="recipe"
            required
            rows={5}
            spellCheck="false"
            value={recipe}
            onChange={(event) => setRecipe(event.target.value)}
          />
        </div>
        <Field
          id="metrology"
          label="Metrology, comma-separated"
          value={metrology}
          onChange={setMetrology}
        />
      </fieldset>

      <fieldset>
        <legend>Man, optional</legend>
        <div className="field">
          <label htmlFor="experience">Operator experience</label>
          <select id="experience" value={experience} onChange={(event) => setExperience(event.target.value)}>
            <option value="">Not supplied</option>
            <option value="junior">Junior</option>
            <option value="senior">Senior</option>
          </select>
        </div>
        <Field id="shift" label="Shift" value={shift} onChange={setShift} />
        <Field id="notes" label="Notes" value={notes} onChange={setNotes} />
      </fieldset>

      {formError && (
        <p role="alert" className="form-error">{formError}</p>
      )}
      <button type="submit" disabled={disabled}>Start the research run</button>
    </form>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  type = "text"
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} type={type} value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}

function split(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
