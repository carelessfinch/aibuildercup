# Geometric 2D Bosch (DRIE) cycle prototype in ViennaPS: C4F8 passivation -> ion depassivation -> SF6 isotropic Si etch.
# Target from the team's 4M template: 5 um wide trench, 10 um photoresist mask, ~80 um deep. Rates are placeholders
# that the Postdoc agent would calibrate against SEM depth/CD. Needs: pip install ViennaPS "ViennaLS==5.8.5"
import viennaps as ps, time, sys
ps.setDimension(2); d=ps.d2; M=ps.Material
ps.Length.setUnit("um"); ps.Time.setUnit("s"); ps.Logger.setLogLevel(ps.LogLevel.ERROR)
cycles=int(sys.argv[1]) if len(sys.argv)>1 else 80
dom=d.Domain(gridDelta=0.1, xExtent=12.0, yExtent=12.0)
d.MakeTrench(dom, trenchWidth=5.0, trenchDepth=0.0, maskHeight=10.0).apply()
t0=time.time()
for c in range(cycles):
    dom.duplicateTopLevelSet(M.Polymer)
    d.Process(dom, d.IsotropicProcess(rate=0.1), 1.0).apply()                        # passivation
    d.Process(dom, d.DirectionalProcess([0.,-1.,0.], -0.3, 0.0, M.Mask, True), 1.0).apply()  # floor clear
    d.Process(dom, d.IsotropicProcess(-0.8, [M.Mask, M.Polymer]), 1.0).apply()       # Si etch
    dom.removeMaterial(M.Polymer)
depth=-dom.getBoundingBox()[0][1]
print(f"{cycles} cycles in {time.time()-t0:.1f}s, depth {depth:.1f} um, aspect ratio {depth/5.0:.1f}")
dom.saveSurfaceMesh("bosch_profile.vtp", True)
