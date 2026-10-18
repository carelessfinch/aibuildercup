# ViennaPS 2D SF6/O2 trench etch smoke test. Needs: pip install ViennaPS "ViennaLS==5.8.5" (ViennaLS 5.9.0 breaks the import).
import viennaps as ps, time
ps.setDimension(2); d=ps.d2
ps.Length.setUnit("um"); ps.Time.setUnit("s")
ps.Logger.setLogLevel(ps.LogLevel.WARNING)
print([m for m in dir(d.DomainSetup) if not m.startswith('_')][:20])
dom=d.Domain(gridDelta=0.03, xExtent=1.0, yExtent=1.0)
d.MakeTrench(dom, trenchWidth=0.25, trenchDepth=0.0, maskHeight=0.3).apply()
model=d.SF6O2Etching(ionFlux=10.0, etchantFlux=1000.0, oxygenFlux=100.0, meanIonEnergy=100.0)
t=time.time()
p=d.Process(dom, model, 30.0)  # time units
p.apply()
print("solve s", round(time.time()-t,1))
dom.saveSurfaceMesh("trench.vtp", True)
