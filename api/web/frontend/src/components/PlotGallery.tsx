export default function PlotGallery({ urls }: { urls: string[] }) {
  if (urls.length === 0) {
    return (
      <section className="plots">
        <h2>Physics plots</h2>
        <p className="empty">Electron density, temperature and ion-flux plots appear after the sweep finishes.</p>
      </section>
    );
  }

  return (
    <section className="plots">
      <h2>Physics plots</h2>
      <div className="plot-grid">
        {urls.map((url) => {
          const filename = url.split("/").at(-1) ?? "plot";
          const label = filename.replace(".svg", "").replace(/-/g, " ");
          return (
            <figure key={url}>
              <img src={url} alt={`${label} plot`} />
              <figcaption>{label}</figcaption>
            </figure>
          );
        })}
      </div>
    </section>
  );
}
