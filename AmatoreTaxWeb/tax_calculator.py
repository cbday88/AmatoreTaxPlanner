from dataclasses import dataclass

BRACKETS = {
    "S":   [(0,.10),(11600,.12),(47150,.22),(100525,.24),(191950,.32),(243725,.35),(609350,.37)],
    "MFJ": [(0,.10),(23200,.12),(94300,.22),(201050,.24),(383900,.32),(487450,.35),(731200,.37)],
    "HOH": [(0,.10),(16550,.12),(63100,.22),(100500,.24),(191950,.32),(243700,.35),(609350,.37)],
}
STANDARD_DED = {"S":14600,"MFJ":29200,"HOH":21900}
SS_WAGE_BASE=168_600
SE_MULTIPLIER=0.9235
MEDICARE_RATE=0.029
SOCSEC_RATE=0.124

@dataclass
class Inputs:
    status:str
    wages:float
    sch_c:float
    other_income:float
    itemized:float
    reasonable_comp:float=0.0
    s_corp:bool=False

def taxable_income(status,wages,sch_c,other_income,itemized):
    std=STANDARD_DED[status]
    return max(0.0,wages+sch_c+other_income-max(std,itemized))

def federal_tax(taxable,status):
    tax=0.0;br=BRACKETS[status]
    for i,(start,rate) in enumerate(br):
        end=br[i+1][0] if i+1 < len(br) else float("inf")
        if taxable>start:
            taxed=min(taxable,end)-start
            if taxed>0: tax += taxed*rate
        else:
            break
    return round(tax,2)

def se_tax_from_sch_c(sch_c):
    if sch_c<=0: return 0.0
    base=sch_c*SE_MULTIPLIER
    return round(min(base,SS_WAGE_BASE)*SOCSEC_RATE + base*MEDICARE_RATE,2)

def qbi_from_sch_c(sch_c_after_rc,status,wages,other_income,itemized):
    if sch_c_after_rc<=0: return 0.0
    taxable_before=max(0.0,wages+sch_c_after_rc+other_income-max(STANDARD_DED[status],itemized))
    return round(min(0.2*sch_c_after_rc,taxable_before),2)

def compute_baseline(inp):
    ti=taxable_income(inp.status,inp.wages,inp.sch_c,inp.other_income,inp.itemized)
    se=se_tax_from_sch_c(inp.sch_c)
    qbi=qbi_from_sch_c(inp.sch_c,inp.status,inp.wages,inp.other_income,inp.itemized)
    ti_qbi=max(0,ti-qbi)
    fed=federal_tax(ti_qbi,inp.status)
    total=fed+se
    return {"taxable_income":ti_qbi,"federal_tax":fed,"se_tax":se,"qbi":qbi,"total_tax":total}

def compute_scenario(inp):
    if inp.s_corp:
        sch=max(0,inp.sch_c - inp.reasonable_comp)
        se=0.0
        qbi=qbi_from_sch_c(sch,inp.status,inp.wages+inp.reasonable_comp,inp.other_income,inp.itemized)
        ti=taxable_income(inp.status,inp.wages+inp.reasonable_comp,sch,inp.other_income,inp.itemized)
        ti_qbi=max(0,ti-qbi)
        fed=federal_tax(ti_qbi,inp.status)
        total=fed+se
        return {"taxable_income":ti_qbi,"federal_tax":fed,"se_tax":se,"qbi":qbi,"total_tax":total}
    else:
        return compute_baseline(inp)
