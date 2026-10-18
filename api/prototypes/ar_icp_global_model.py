# 0D argon ICP global model (Lieberman & Lichtenberg ch.10 style) - feasibility check
import numpy as np
from scipy.optimize import brentq
e=1.602e-19; kB=1.381e-23; M=40*1.6605e-27
def Kiz(Te): return 2.34e-14*Te**0.59*np.exp(-17.44/Te)
def Kex(Te): return 2.48e-14*Te**0.33*np.exp(-12.78/Te)
def Kel(Te): return 2.336e-14*Te**1.609*np.exp(0.0618*np.log(Te)**2-0.1171*np.log(Te)**3)
def run(P_W, p_mTorr, R=0.15, L=0.10, Tg=300, eta=0.8):
    ng=p_mTorr*0.1333/(kB*Tg); lam=1/(ng*1e-18)
    hl=0.86/np.sqrt(3+L/(2*lam)); hr=0.8/np.sqrt(4+R/lam)
    deff=R*L/(2*(R*hr+L*hl)); A=2*np.pi*R**2+2*np.pi*R*L; V=np.pi*R**2*L
    Te=brentq(lambda T: Kiz(T)*ng*deff-np.sqrt(e*T/M),0.5,20)
    uB=np.sqrt(e*Te/M)
    Ec=(15.76*Kiz(Te)+12.14*Kex(Te)+3*9.109e-31/M*Te*Kel(Te))/Kiz(Te)
    ET=Ec+2*Te+Te*0.5*np.log(M/(2*np.pi*9.109e-31))+0.5*Te
    n0=eta*P_W/(e*uB*ET*(hl*2*np.pi*R**2+hr*2*np.pi*R*L))
    ion_flux=hl*n0*uB; Ei=Te*(0.5+0.5*np.log(M/(2*np.pi*9.109e-31)))
    return dict(Te_eV=Te, ne_m3=n0, ion_flux_m2s=ion_flux, ion_energy_eV=Ei)
for P in (100,300,500):
    print(P,"W 10 mTorr",{k:f"{v:.3g}" for k,v in run(P,10).items()})
